"""Behavioral coverage for defensive runtime paths that must stay measurable."""

from __future__ import annotations

import builtins
import importlib.util
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

from app.core import metrics, observability
from app.utils import files
from app.utils.retry import RetryExhausted, retry_async


def _load_without_prometheus(
    source_module: ModuleType,
    alias: str,
) -> ModuleType:
    """Execute a module in isolation with its optional Prometheus import absent."""

    source_path = source_module.__file__
    assert source_path is not None
    spec = importlib.util.spec_from_file_location(alias, source_path)
    assert spec is not None
    assert spec.loader is not None
    isolated = importlib.util.module_from_spec(spec)
    original_import = builtins.__import__

    def guarded_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "prometheus_client":
            raise ImportError("prometheus-client unavailable")
        return original_import(name, *args, **kwargs)

    sys.modules[alias] = isolated
    try:
        with patch.object(builtins, "__import__", guarded_import):
            spec.loader.exec_module(isolated)
    finally:
        sys.modules.pop(alias, None)
    return isolated


@pytest.mark.parametrize(
    ("source_module", "alias", "error_message"),
    [
        (metrics, "tests._metrics_without_prometheus", "expose metrics"),
        (
            observability,
            "tests._observability_without_prometheus",
            "worker metrics",
        ),
    ],
)
def test_optional_prometheus_fallback_is_explicit_and_fail_closed(
    source_module: ModuleType,
    alias: str,
    error_message: str,
) -> None:
    isolated = _load_without_prometheus(source_module, alias)

    assert isolated.REGISTRY is None
    assert isolated.Counter is None
    assert isolated.Gauge is None
    assert isolated.Histogram is None
    with pytest.raises(RuntimeError, match=error_message):
        isolated.generate_latest()


@pytest.mark.asyncio
async def test_cache_metrics_records_failure_without_optional_health_gauge() -> None:
    from app.deps.cache import RedisCache

    backend = MagicMock(spec=RedisCache)
    backend._get_client = AsyncMock(side_effect=ConnectionError("redis unavailable"))
    record_command = MagicMock()

    with (
        patch("app.deps.cache.get_cache", return_value=backend),
        patch.object(metrics, "_CACHE_ENTRIES", MagicMock()),
        patch.object(metrics, "_CACHE_MEMORY_BYTES", None),
        patch.object(metrics, "_REDIS_HEALTH", None),
        patch.object(metrics, "record_redis_command", record_command),
    ):
        await metrics._record_cache_metrics()

    record_command.assert_called_once_with("ping", 0.0, success=False)


def test_system_metrics_tolerates_independent_cpu_and_gpu_failures() -> None:
    with (
        patch.object(metrics, "_CPU_LOAD", MagicMock()),
        patch.object(metrics, "_GPU_LOAD", None),
        patch.object(metrics.psutil, "cpu_percent", side_effect=OSError("cpu")),
    ):
        metrics._record_system_metrics()

    with (
        patch.object(metrics, "_CPU_LOAD", None),
        patch.object(metrics, "_GPU_LOAD", MagicMock()),
        patch.object(metrics, "_load_gputil", side_effect=RuntimeError("gpu")),
    ):
        metrics._record_system_metrics()


def test_notification_metrics_registry_tolerates_observability_import_failure() -> None:
    original_import = builtins.__import__

    def guarded_import(name: str, *args: object, **kwargs: object) -> object:
        fromlist = kwargs.get("fromlist", args[2] if len(args) > 2 else ())
        if name == "app.core" and "observability" in (fromlist or ()):
            raise ImportError("observability unavailable")
        return original_import(name, *args, **kwargs)

    with (
        patch.object(metrics, "REGISTRY", MagicMock()),
        patch.object(builtins, "__import__", guarded_import),
    ):
        metrics._ensure_notification_queue_metrics_registry()


def test_notification_metrics_registry_tolerates_queue_import_failure() -> None:
    registry = MagicMock()
    current = SimpleNamespace(registry=object())
    fresh = object()
    original_import = builtins.__import__

    def guarded_import(name: str, *args: object, **kwargs: object) -> object:
        fromlist = kwargs.get("fromlist", args[2] if len(args) > 2 else ())
        if name == "app.services" and "notification_queue" in (fromlist or ()):
            raise ImportError("notification queue unavailable")
        return original_import(name, *args, **kwargs)

    with (
        patch.object(metrics, "REGISTRY", registry),
        patch.object(
            observability,
            "get_notification_queue_metrics",
            return_value=current,
        ),
        patch.object(
            observability,
            "reinitialize_notification_queue_metrics",
            return_value=fresh,
        ) as reinitialize,
        patch.object(builtins, "__import__", guarded_import),
    ):
        metrics._ensure_notification_queue_metrics_registry()

    reinitialize.assert_called_once_with(registry=registry)


def test_configure_metrics_tolerates_optional_observability_import_failure() -> None:
    app = FastAPI()
    original_import = builtins.__import__

    def guarded_import(name: str, *args: object, **kwargs: object) -> object:
        if name in {
            "app.core.observability",
            "opentelemetry.exporter.prometheus",
        }:
            raise ImportError(f"{name} unavailable")
        return original_import(name, *args, **kwargs)

    with (
        patch.object(metrics.settings, "enable_metrics_endpoint", False),
        patch.object(builtins, "__import__", guarded_import),
    ):
        metrics.configure_metrics(app)

    assert app.state._metrics_configured is True
    assert any(route.path == "/metrics" for route in app.routes)


def test_detect_mime_type_uses_signature_when_legacy_magic_fallback_fails() -> None:
    detector = MagicMock()
    detector.from_buffer.side_effect = AttributeError("legacy API")
    legacy_from_buffer = MagicMock(side_effect=OSError("libmagic failure"))

    with (
        patch.object(files, "_magic_mime_detector", detector),
        patch.object(
            files,
            "_magic_module",
            SimpleNamespace(from_buffer=legacy_from_buffer),
        ),
    ):
        detected = files.detect_mime_type(b"%PDF-1.7 payload")

    assert detected == "application/pdf"
    legacy_from_buffer.assert_called_once_with(b"%PDF-1.7 payload", mime=True)


def test_detect_mime_type_uses_signature_when_detector_raises() -> None:
    detector = MagicMock()
    detector.from_buffer.side_effect = RuntimeError("libmagic failure")

    with patch.object(files, "_magic_mime_detector", detector):
        assert files.detect_mime_type(b"%PDF-1.7 payload") == "application/pdf"


@pytest.mark.asyncio
async def test_retry_with_zero_attempts_reports_empty_exhaustion() -> None:
    operation = AsyncMock(return_value="unreachable")

    with pytest.raises(RetryExhausted) as exc_info:
        await retry_async(operation, max_attempts=0)

    assert exc_info.value.attempts == 0
    assert exc_info.value.last_error is None
    operation.assert_not_awaited()
