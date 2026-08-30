"""Behavioral coverage closure for observability and worker metrics."""

from __future__ import annotations

import asyncio
import builtins
import logging
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.trace import TracerProvider
from prometheus_client import CollectorRegistry


@pytest.fixture
def restore_notification_queue_metrics_state():
    from app.core import observability

    previous = observability._notification_queue_metrics
    yield
    observability._notification_queue_metrics = previous


@pytest.fixture(autouse=True)
def reset_owned_otel_lifecycle() -> None:
    from app.core import observability

    observability.shutdown_observability()
    observability._otel_shutdown = False
    observability._otel_configured = False
    observability._otel_tracer_provider = None
    observability._otel_meter_provider = None
    yield
    observability.shutdown_observability()
    observability._otel_shutdown = False
    observability._otel_configured = False
    observability._otel_tracer_provider = None
    observability._otel_meter_provider = None


def test_observability_header_and_logging_helpers(monkeypatch) -> None:
    from app.core import observability
    from app.core.config import settings

    assert observability._resolve_headers("") == {}
    assert observability._resolve_headers("broken,,=empty,key=,valid=value") == {
        "valid": "value"
    }

    with patch.object(observability, "_configure_structured_logging") as configure:
        monkeypatch.setattr(settings, "log_level", "INFO")
        monkeypatch.setattr(settings, "environment", "testing")
        observability._configure_logging()
    configure.assert_called_once_with(level=logging.INFO, json_output=False)


def test_observability_context_helpers_cover_trace_and_request_fallbacks() -> None:
    from app.core import observability

    request_token = observability._request_id_ctx.set("request-id")
    trace_token = observability._trace_id_ctx.set("trace-id")
    invalid_span = MagicMock()
    invalid_span.get_span_context.return_value = SimpleNamespace(is_valid=False)
    try:
        assert observability.get_request_id() == "request-id"
        assert observability.get_trace_id() == "trace-id"
        with patch.object(
            observability.trace, "get_current_span", return_value=invalid_span
        ):
            assert observability._resolve_current_trace_id() == "trace-id"
        observability._trace_id_ctx.set(None)
        with patch.object(
            observability.trace, "get_current_span", return_value=invalid_span
        ):
            assert observability._resolve_current_trace_id() == "request-id"
        observability._request_id_ctx.set(None)
        with patch.object(
            observability.trace, "get_current_span", return_value=invalid_span
        ):
            assert observability._resolve_current_trace_id() is None
    finally:
        observability._request_id_ctx.reset(request_token)
        observability._trace_id_ctx.reset(trace_token)


def test_observability_import_without_sentry_sdk_uses_optional_fallbacks() -> None:
    from app.core import observability

    with patch.dict(sys.modules, {"sentry_sdk": None}):
        namespace = runpy.run_path(
            str(Path(observability.__file__)), run_name="observability_without_sentry"
        )
    assert namespace["sentry_init"] is None
    assert namespace["FastApiIntegration"] is None
    assert namespace["LoggingIntegration"] is None
    assert namespace["SentrySpanProcessor"] is None

    real_import = builtins.__import__

    def fail_sentry_otel_import(name, *args, **kwargs):
        if name == "sentry_sdk.integrations.opentelemetry":
            raise ImportError("optional Sentry OpenTelemetry integration unavailable")
        return real_import(name, *args, **kwargs)

    with patch.object(builtins, "__import__", side_effect=fail_sentry_otel_import):
        namespace = runpy.run_path(
            str(Path(observability.__file__)),
            run_name="observability_without_sentry_otel",
        )
    assert namespace["sentry_init"] is not None
    assert namespace["SentrySpanProcessor"] is None


def test_observability_import_without_prometheus_uses_fallback() -> None:
    from app.core import observability

    source_path = Path(observability.__file__)
    real_import = builtins.__import__

    def fail_prometheus_import(name, *args, **kwargs):
        if name == "prometheus_client":
            raise ImportError("optional prometheus-client unavailable")
        return real_import(name, *args, **kwargs)

    with patch.object(builtins, "__import__", side_effect=fail_prometheus_import):
        namespace = runpy.run_path(
            str(source_path),
            run_name="observability_without_prometheus",
        )
    assert namespace["CollectorRegistry"] is None
    with pytest.raises(RuntimeError, match="prometheus-client"):
        namespace["generate_latest"]()


def test_sentry_configuration_supports_noop_and_trace_processor(monkeypatch) -> None:
    from app.core import observability
    from app.core.config import settings

    monkeypatch.setattr(settings, "sentry_dsn", "")
    with patch.object(observability, "sentry_init") as sentry_init:
        observability._configure_sentry(None)
    sentry_init.assert_not_called()

    monkeypatch.setattr(settings, "sentry_dsn", "https://dsn@example/1")
    monkeypatch.setattr(settings, "sentry_environment", "testing")
    monkeypatch.setattr(settings, "sentry_traces_sample_rate", 0.5)
    monkeypatch.setattr(settings, "sentry_profiles_sample_rate", 0.25)
    monkeypatch.setattr(settings, "service_version", "  ")
    tracer = MagicMock()
    processor = MagicMock()
    with (
        patch.object(observability, "sentry_init") as sentry_init,
        patch.object(observability, "LoggingIntegration"),
        patch.object(observability, "FastApiIntegration"),
        patch.object(observability, "SentrySpanProcessor", return_value=processor),
    ):
        observability._configure_sentry(tracer)
    sentry_init.assert_called_once()
    tracer.add_span_processor.assert_called_once_with(processor)

    with (
        patch.object(observability, "sentry_init"),
        patch.object(observability, "SentrySpanProcessor", None),
    ):
        observability._configure_sentry(None)


def test_resource_attributes_cover_optional_version(monkeypatch) -> None:
    from app.core import observability
    from app.core.config import settings

    monkeypatch.setattr(settings, "otel_service_name", "service")
    monkeypatch.setattr(settings, "environment", "testing")
    monkeypatch.setattr(settings, "service_version", "  ")
    without_version = observability._build_otel_resource_attributes()
    assert "service.version" not in without_version

    monkeypatch.setattr(settings, "service_version", "1.2.3")
    with_version = observability._build_otel_resource_attributes()
    assert with_version["service.version"] == "1.2.3"


def _otel_settings(*, metrics: bool = False, logs: bool = False) -> MagicMock:
    settings = MagicMock()
    settings.enable_otel = True
    settings.enable_otel_metrics = metrics
    settings.enable_otel_logs = logs
    settings.otel_exporter_otlp_endpoint = ""
    settings.otel_exporter_otlp_headers = ""
    settings.otel_trace_sampler_ratio = 0.5
    settings.otel_service_name = "test-service"
    settings.environment = "testing"
    settings.service_version = ""
    return settings


def test_configure_otel_handles_disabled_optional_pipelines() -> None:
    from app.core import observability

    observability._otel_configured = False
    observability._sqlalchemy_instrumented = False

    settings = _otel_settings(metrics=False, logs=False)
    provider = MagicMock()
    meter_provider = MagicMock()
    with (
        patch.object(observability, "settings", settings),
        patch.object(observability, "TracerProvider", return_value=provider),
        patch.object(observability, "MeterProvider", return_value=meter_provider),
        patch.object(observability, "OTLPSpanExporter"),
        patch.object(observability, "trace"),
        patch.object(observability, "metrics"),
        patch.object(observability, "set_global_textmap"),
        patch.object(observability, "SQLAlchemyInstrumentor") as sqlalchemy,
        patch.object(observability, "RedisInstrumentor"),
        patch.object(observability, "HTTPXClientInstrumentor"),
    ):
        result = observability._configure_otel(MagicMock())
    assert result is provider
    assert observability._otel_configured is True
    assert observability._sqlalchemy_instrumented is True
    sqlalchemy.return_value.instrument.assert_called_once()
    observability._otel_configured = False
    observability._sqlalchemy_instrumented = True
    with (
        patch.object(observability, "settings", settings),
        patch.object(observability, "TracerProvider", return_value=provider),
        patch.object(observability, "MeterProvider", return_value=meter_provider),
        patch.object(observability, "OTLPSpanExporter"),
        patch.object(observability, "trace"),
        patch.object(observability, "metrics"),
        patch.object(observability, "set_global_textmap"),
        patch.object(observability, "SQLAlchemyInstrumentor") as skipped_sqlalchemy,
        patch.object(observability, "RedisInstrumentor"),
        patch.object(observability, "HTTPXClientInstrumentor"),
    ):
        observability._configure_otel(MagicMock())
    skipped_sqlalchemy.return_value.instrument.assert_not_called()
    observability._otel_configured = False
    observability._sqlalchemy_instrumented = False


def test_configure_otel_existing_provider_marks_lifecycle_configured() -> None:
    from app.core import observability

    provider = MagicMock()
    observability._otel_configured = False
    observability._otel_tracer_provider = provider
    with patch.object(observability, "settings", MagicMock(enable_otel=True)):
        assert observability._configure_otel(MagicMock()) is provider
    assert observability._otel_configured is True


def test_configure_otel_uses_clamped_sampler_ratio_and_exact_span_processor() -> None:
    from app.core import observability

    settings = _otel_settings(metrics=False, logs=False)
    settings.otel_trace_sampler_ratio = 1.5
    tracer_provider = MagicMock()
    meter_provider = MagicMock()
    span_exporter = MagicMock()
    batch_processor = MagicMock()
    resource = MagicMock(name="otel-resource")
    with (
        patch.object(observability, "settings", settings),
        patch.object(observability, "_create_otel_resource", return_value=resource),
        patch.object(
            observability, "TracerProvider", return_value=tracer_provider
        ) as tracer_provider_factory,
        patch.object(observability, "MeterProvider", return_value=meter_provider),
        patch.object(observability, "OTLPSpanExporter", return_value=span_exporter),
        patch.object(
            observability, "BatchSpanProcessor", return_value=batch_processor
        ) as batch,
        patch.object(observability, "TraceIdRatioBased") as ratio,
        patch.object(observability, "ParentBased") as parent,
        patch.object(observability, "trace"),
        patch.object(observability, "metrics"),
        patch.object(observability, "set_global_textmap"),
        patch.object(observability, "SQLAlchemyInstrumentor"),
        patch.object(observability, "RedisInstrumentor"),
        patch.object(observability, "HTTPXClientInstrumentor"),
    ):
        assert observability._configure_otel(MagicMock()) is tracer_provider

    ratio.assert_called_once_with(1.0)
    parent.assert_called_once_with(ratio.return_value)
    tracer_provider_factory.assert_called_once_with(
        resource=resource, sampler=parent.return_value
    )
    batch.assert_called_once_with(span_exporter)
    tracer_provider.add_span_processor.assert_called_once_with(batch_processor)


def test_configure_otel_optional_pipelines_without_endpoint_or_headers() -> None:
    from app.core import observability

    observability._otel_configured = False
    observability._sqlalchemy_instrumented = False
    settings = _otel_settings(metrics=True, logs=True)
    provider = MagicMock()
    meter_provider = MagicMock()
    logger_provider = MagicMock()
    with (
        patch.object(observability, "settings", settings),
        patch.object(observability, "TracerProvider", return_value=provider),
        patch.object(observability, "MeterProvider", return_value=meter_provider),
        patch.object(observability, "OTLPSpanExporter"),
        patch.object(observability, "OTLPMetricExporter") as metric_exporter,
        patch.object(observability, "OTLPLogExporter") as log_exporter,
        patch.object(observability, "PeriodicExportingMetricReader"),
        patch.object(observability, "LoggerProvider", return_value=logger_provider),
        patch.object(observability, "BatchLogRecordProcessor"),
        patch.object(observability, "LoggingHandler", return_value=MagicMock()),
        patch.object(observability.logging, "getLogger", return_value=MagicMock()),
        patch.object(observability, "trace"),
        patch.object(observability, "metrics"),
        patch.object(observability, "set_global_textmap"),
        patch.object(observability, "set_logger_provider"),
        patch.object(observability, "SQLAlchemyInstrumentor"),
        patch.object(observability, "RedisInstrumentor"),
        patch.object(observability, "HTTPXClientInstrumentor"),
    ):
        observability._configure_otel(MagicMock())
    metric_exporter.assert_called_once_with(timeout=0.75)
    log_exporter.assert_called_once_with(timeout=0.75)
    observability._otel_configured = False
    observability._sqlalchemy_instrumented = False


def test_configure_otel_returns_none_when_disabled() -> None:
    """Disabled OTEL must skip provider creation before touching exporters."""
    from app.core import observability

    observability._otel_configured = False
    with patch.object(observability, "settings", MagicMock(enable_otel=False)):
        assert observability._configure_otel(MagicMock()) is None
    assert observability._otel_configured is False


def test_configure_observability_short_circuits_configured_app() -> None:
    from app.core import observability

    app = MagicMock()
    app.state.observability_configured = True
    with (
        patch.object(observability, "_configure_logging") as configure_logging,
        patch.object(observability, "_configure_otel") as configure_otel,
    ):
        observability.configure_observability(app, engine=MagicMock())
    configure_logging.assert_not_called()
    configure_otel.assert_not_called()


def test_configure_observability_without_otel_does_not_instrument() -> None:
    from app.core import observability

    app = MagicMock()
    app.state.observability_configured = False
    app.state.otel_instrumented = False
    settings = MagicMock(enable_otel=False)
    with (
        patch.object(observability, "settings", settings),
        patch.object(observability, "_configure_logging"),
        patch.object(observability, "_configure_otel", return_value=None),
        patch.object(observability, "_configure_sentry"),
        patch.object(observability.FastAPIInstrumentor, "instrument_app") as instrument,
    ):
        observability.configure_observability(app, engine=MagicMock())
    instrument.assert_not_called()
    assert app.state.observability_configured is True


def test_configure_observability_instruments_with_owned_providers() -> None:
    from app.core import observability

    app = MagicMock()
    app.state.observability_configured = False
    app.state.otel_instrumented = False
    owned_tracer = MagicMock()
    owned_meter = MagicMock()
    foreign_tracer = MagicMock()
    foreign_meter = MagicMock()
    with (
        patch.object(observability, "_configure_logging"),
        patch.object(observability, "_configure_otel", return_value=owned_tracer),
        patch.object(observability, "_configure_sentry"),
        patch.object(observability, "_otel_meter_provider", owned_meter),
        patch.object(
            observability.trace,
            "get_tracer_provider",
            return_value=foreign_tracer,
        ),
        patch.object(
            observability.metrics,
            "get_meter_provider",
            return_value=foreign_meter,
        ),
        patch.object(observability.FastAPIInstrumentor, "instrument_app") as instrument,
    ):
        observability.configure_observability(app, engine=MagicMock())

    instrument.assert_called_once_with(
        app,
        tracer_provider=owned_tracer,
        meter_provider=owned_meter,
    )


def test_configure_observability_missing_marker_uses_explicit_false_default() -> None:
    from app.core import observability

    app = FastAPI()
    provider = MagicMock()
    with (
        patch.object(observability, "_configure_logging"),
        patch.object(observability, "_configure_otel", return_value=provider),
        patch.object(observability, "_configure_sentry"),
        patch.object(observability.FastAPIInstrumentor, "instrument_app") as instrument,
        patch.object(observability, "_otel_meter_provider", MagicMock()),
    ):
        observability.configure_observability(app, engine=MagicMock())

    instrument.assert_called_once()


def test_configure_observability_after_shutdown_does_not_reuse_dead_globals() -> None:
    from app.core import observability

    app = MagicMock()
    app.state.observability_configured = False
    app.state.otel_instrumented = False
    observability._otel_configured = False
    observability._otel_shutdown = True
    observability._otel_tracer_provider = None
    observability._otel_meter_provider = None
    settings = MagicMock(enable_otel=True)
    try:
        with (
            patch.object(observability, "settings", settings),
            patch.object(observability, "_configure_logging"),
            patch.object(observability, "_configure_sentry") as configure_sentry,
            patch.object(
                observability.FastAPIInstrumentor, "instrument_app"
            ) as instrument,
        ):
            observability.configure_observability(app, engine=MagicMock())
    finally:
        observability._otel_shutdown = False

    configure_sentry.assert_called_once_with(None)
    instrument.assert_not_called()
    assert app.state.otel_instrumented is False
    assert app.state.observability_configured is True


def test_shutdown_observability_shuts_down_registered_providers() -> None:
    from app.core import observability

    tracer = TracerProvider()
    meter = MeterProvider()
    handler = MagicMock()
    logger_provider = MagicMock()
    with (
        patch.object(observability.trace, "get_tracer_provider", return_value=tracer),
        patch.object(observability.metrics, "get_meter_provider", return_value=meter),
        patch.object(observability.logging, "getLogger", return_value=MagicMock()),
        patch.object(observability, "_otel_logging_handler", handler),
        patch.object(observability, "_otel_logger_provider", logger_provider),
        patch.object(observability, "_otel_tracer_provider", tracer),
        patch.object(observability, "_otel_meter_provider", meter),
        patch.object(observability, "_otel_shutdown", False),
    ):
        observability.shutdown_observability()
    assert observability._otel_configured is False

    with (
        patch.object(
            observability.trace, "get_tracer_provider", return_value=MagicMock()
        ),
        patch.object(
            observability.metrics, "get_meter_provider", return_value=MagicMock()
        ),
        patch.object(observability, "_otel_logging_handler", None),
        patch.object(observability, "_otel_logger_provider", None),
    ):
        observability.shutdown_observability()


def test_shutdown_observability_owns_providers_rejected_by_otel_globals() -> None:
    """Locally created providers must not outlive a rejected global install."""
    from app.core import observability

    class TrackedProvider:
        instances: ClassVar[list[TrackedProvider]] = []

        def __init__(self, *args: object, **kwargs: object) -> None:
            self.shutdown_calls = 0
            self.shutdown_kwargs: list[dict[str, object]] = []
            self.__class__.instances.append(self)

        def add_span_processor(self, _processor: object) -> None:
            return None

        def shutdown(self, *args: object, **kwargs: object) -> None:
            self.shutdown_calls += 1
            self.shutdown_kwargs.append(kwargs)

    foreign_tracer = TrackedProvider()
    foreign_meter = TrackedProvider()
    TrackedProvider.instances.clear()
    settings = _otel_settings(metrics=False, logs=False)
    observability._otel_configured = False
    observability._otel_shutdown = False
    observability._sqlalchemy_instrumented = True

    with (
        patch.object(observability, "settings", settings),
        patch.object(observability, "TracerProvider", TrackedProvider),
        patch.object(observability, "MeterProvider", TrackedProvider),
        patch.object(observability, "OTLPSpanExporter"),
        patch.object(observability, "BatchSpanProcessor"),
        patch.object(observability, "_create_otel_resource", return_value=MagicMock()),
        patch.object(observability.trace, "set_tracer_provider") as set_tracer_provider,
        patch.object(observability.metrics, "set_meter_provider") as set_meter_provider,
        patch.object(
            observability.trace,
            "get_tracer_provider",
            return_value=foreign_tracer,
        ),
        patch.object(
            observability.metrics,
            "get_meter_provider",
            return_value=foreign_meter,
        ),
        patch.object(observability, "set_global_textmap"),
        patch.object(observability, "RedisInstrumentor"),
        patch.object(observability, "HTTPXClientInstrumentor"),
    ):
        local_tracer = observability._configure_otel(MagicMock())
        local_meter = TrackedProvider.instances[-1]
        observability.shutdown_observability()
        observability.shutdown_observability()
        refused = observability._configure_otel(MagicMock())

    assert local_tracer is TrackedProvider.instances[0]
    assert local_tracer.shutdown_calls == 1
    assert local_meter.shutdown_calls == 1
    assert local_tracer.shutdown_kwargs == [{"timeout_millis": 1200}]
    assert local_meter.shutdown_kwargs == [{"timeout_millis": 1200}]
    assert foreign_tracer.shutdown_calls == 0
    assert foreign_meter.shutdown_calls == 0
    assert refused is None
    assert len(TrackedProvider.instances) == 2
    set_tracer_provider.assert_called_once_with(local_tracer)
    set_meter_provider.assert_called_once_with(local_meter)


def test_configure_otel_partial_failure_shuts_down_created_providers() -> None:
    """A failed startup must not orphan exporter workers or permit a retry."""
    from app.core import observability

    tracer_provider = MagicMock()
    meter_provider = MagicMock()
    settings = _otel_settings(metrics=True, logs=False)
    observability._otel_shutdown = False
    observability._otel_configured = False
    observability._otel_tracer_provider = None
    observability._otel_meter_provider = None

    with (
        patch.object(observability, "settings", settings),
        patch.object(observability, "TracerProvider", return_value=tracer_provider),
        patch.object(observability, "MeterProvider", return_value=meter_provider),
        patch.object(observability, "OTLPSpanExporter"),
        patch.object(observability, "BatchSpanProcessor"),
        patch.object(observability, "OTLPMetricExporter"),
        patch.object(observability, "PeriodicExportingMetricReader"),
        patch.object(observability, "_create_otel_resource", return_value=MagicMock()),
        patch.object(observability.trace, "set_tracer_provider"),
        patch.object(
            observability.metrics,
            "set_meter_provider",
            side_effect=RuntimeError("global provider registration failed"),
        ),
        patch.object(observability, "set_global_textmap"),
    ):
        with pytest.raises(RuntimeError, match="global provider registration failed"):
            observability._configure_otel(MagicMock())

    tracer_provider.shutdown.assert_called_once_with(timeout_millis=1200)
    meter_provider.shutdown.assert_called_once_with(timeout_millis=1200)
    assert observability._otel_tracer_provider is None
    assert observability._otel_meter_provider is None
    assert observability._otel_configured is False
    assert observability._otel_shutdown is True
    observability._shutdown_otel_provider(None)


def test_configure_otel_partial_failure_removes_logging_handler() -> None:
    from app.core import observability

    tracer_provider = MagicMock()
    meter_provider = MagicMock()
    logger_provider = MagicMock()
    logging_handler = MagicMock()
    settings = _otel_settings(metrics=False, logs=True)
    observability._otel_shutdown = False
    observability._otel_configured = False
    observability._otel_tracer_provider = None
    observability._otel_meter_provider = None
    root_logger = MagicMock()

    with (
        patch.object(observability, "settings", settings),
        patch.object(observability, "TracerProvider", return_value=tracer_provider),
        patch.object(observability, "MeterProvider", return_value=meter_provider),
        patch.object(observability, "LoggerProvider", return_value=logger_provider),
        patch.object(observability, "LoggingHandler", return_value=logging_handler),
        patch.object(observability, "OTLPSpanExporter"),
        patch.object(observability, "BatchSpanProcessor"),
        patch.object(observability, "OTLPLogExporter"),
        patch.object(observability, "BatchLogRecordProcessor"),
        patch.object(observability, "_create_otel_resource", return_value=MagicMock()),
        patch.object(observability.trace, "set_tracer_provider"),
        patch.object(observability.metrics, "set_meter_provider"),
        patch.object(observability, "set_logger_provider"),
        patch.object(observability, "set_global_textmap"),
        patch.object(observability.logging, "getLogger", return_value=root_logger),
        patch.object(observability, "_sqlalchemy_instrumented", True),
        patch.object(
            observability.RedisInstrumentor,
            "instrument",
            side_effect=ValueError("instrumentation failed"),
        ),
    ):
        with pytest.raises(ValueError, match="instrumentation failed"):
            observability._configure_otel(MagicMock())

    root_logger.addHandler.assert_called_once_with(logging_handler)
    root_logger.removeHandler.assert_called_once_with(logging_handler)
    logger_provider.shutdown.assert_called_once_with(timeout_millis=1200)
    meter_provider.shutdown.assert_called_once_with(timeout_millis=1200)
    tracer_provider.shutdown.assert_called_once_with(timeout_millis=1200)


def test_worker_metrics_lifecycle_and_status() -> None:
    from app.core import observability

    worker = observability.create_worker_metrics("worker-name")
    assert worker.name == "worker-name"
    assert worker.last_run is not None
    assert worker.status == "ok"

    worker.record_success(notifications_created=2)
    assert worker.last_success is not None
    assert worker.status == "ok"
    worker.record_failure()
    assert worker.last_failure is not None
    assert worker.status == "degraded"

    worker.record_success()
    assert worker.status == "ok"
    assert observability._sanitize_metric_name("---") == "worker"


def test_create_worker_metrics_requires_prometheus() -> None:
    from app.core import observability

    with (
        patch.object(observability, "CollectorRegistry", None),
        patch.object(observability, "Counter", None),
        patch.object(observability, "Gauge", None),
    ):
        with pytest.raises(RuntimeError, match="prometheus-client"):
            observability.create_worker_metrics("worker")


@pytest.mark.asyncio
async def test_periodic_task_tracking_records_success_failure_cancel_and_values() -> (
    None
):
    from app.core import observability

    metrics = observability.get_periodic_task_metrics(
        "closure-periodic", registry=CollectorRegistry()
    )
    async with metrics.track_execution() as run:
        run.observe_deleted(None)
        run.observe_deleted([1, None, "2", -3])
        run.observe_deleted("4")
    assert run.deleted_total == 7

    with pytest.raises(RuntimeError, match="failure"):
        async with metrics.track_execution():
            raise RuntimeError("failure")

    with pytest.raises(asyncio.CancelledError):
        async with metrics.track_execution():
            raise asyncio.CancelledError

    async with metrics.track_execution():
        pass

    with patch.object(observability, "Counter", None):
        with pytest.raises(RuntimeError, match="prometheus-client"):
            observability.get_periodic_task_metrics(
                "no-periodic-metrics", registry=CollectorRegistry()
            )


@pytest.mark.asyncio
async def test_worker_monitoring_app_exposes_health_and_metrics() -> None:
    from app.core import observability

    worker = observability.create_worker_metrics("http-worker")
    app = observability.create_worker_monitoring_app(
        worker_name="http-worker", metrics=worker
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        health = await client.get("/healthz")
        metrics_response = await client.get("/metrics")
    assert health.status_code == 200
    assert health.json()["worker"] == "http-worker"
    assert metrics_response.status_code == 200


@pytest.mark.asyncio
async def test_worker_monitoring_server_validates_port_and_handles_bool_started() -> (
    None
):
    from app.core import observability

    with pytest.raises(ValueError, match="positive"):
        await observability.start_worker_monitoring_server(
            FastAPI(), host="127.0.0.1", port=0
        )

    server = MagicMock(started=False, should_exit=False)

    async def serve() -> None:
        server.started = True

    server.serve = serve
    with patch.object(observability.uvicorn, "Server", return_value=server):
        stop = await observability.start_worker_monitoring_server(
            FastAPI(), host="127.0.0.1", port=9001
        )
        await stop()
        await stop()
    assert server.should_exit is True

    never_started = MagicMock(started=False, should_exit=False)

    async def serve_without_starting() -> None:
        return None

    never_started.serve = serve_without_starting
    with (
        patch.object(observability.uvicorn, "Server", return_value=never_started),
        patch.object(observability.asyncio, "sleep", new=AsyncMock()),
    ):
        stop = await observability.start_worker_monitoring_server(
            FastAPI(), host="127.0.0.1", port=9002
        )
        await stop()


def test_worker_observability_without_otel_or_name() -> None:
    from app.core import observability

    with (
        patch.object(observability, "_configure_logging"),
        patch.object(observability, "settings", MagicMock(enable_otel=False)),
    ):
        observability.configure_worker_observability()

    settings = MagicMock(enable_otel=True)
    with (
        patch.object(observability, "_configure_logging"),
        patch.object(observability, "settings", settings),
        patch.object(observability, "_configure_otel", return_value=None),
        patch.object(observability.logging, "getLogger", return_value=MagicMock()),
    ):
        observability.configure_worker_observability(worker_name="worker")


def test_notification_queue_metrics_reset_and_reinitialize(
    restore_notification_queue_metrics_state,
) -> None:
    from app.core import observability

    registry = CollectorRegistry()
    queue_metrics = observability.create_notification_queue_metrics(registry=registry)
    queue_metrics.dropped_jobs_total.labels(kind="test").inc()
    queue_metrics.reset()
    assert queue_metrics.queue_size is not None

    queue_metrics.oldest_dead_letter_age_seconds = None
    with patch.object(
        observability, "create_notification_queue_metrics", return_value=queue_metrics
    ):
        queue_metrics.reset()

    previous = observability._notification_queue_metrics
    observability._notification_queue_metrics = None
    marker = object()
    with patch.object(
        observability,
        "create_notification_queue_metrics",
        return_value=marker,
    ) as create:
        assert observability.get_notification_queue_metrics() is marker
        assert observability.get_notification_queue_metrics() is marker
    create.assert_called_once()
    observability._notification_queue_metrics = previous

    previous_bundle = SimpleNamespace(
        queue_size=MagicMock(),
        dropped_jobs_total=MagicMock(),
        failed_jobs_total=MagicMock(),
        enqueue_failures_total=MagicMock(),
        processed_jobs_total=MagicMock(),
        processing_latency_seconds=MagicMock(),
        queue_wait_time_seconds=MagicMock(),
        retry_delay_seconds=MagicMock(),
        dead_lettered_jobs=MagicMock(),
        oldest_dead_letter_age_seconds=MagicMock(),
        registry=MagicMock(),
    )
    fresh = object()
    with (
        patch.object(observability, "_notification_queue_metrics", previous_bundle),
        patch.object(
            observability, "create_notification_queue_metrics", return_value=fresh
        ),
    ):
        assert (
            observability.reinitialize_notification_queue_metrics(registry=registry)
            is fresh
        )
    previous_bundle.registry.unregister.assert_called()

    previous_bundle_without_age = SimpleNamespace(
        queue_size=MagicMock(),
        dropped_jobs_total=MagicMock(),
        failed_jobs_total=MagicMock(),
        enqueue_failures_total=MagicMock(),
        processed_jobs_total=MagicMock(),
        processing_latency_seconds=MagicMock(),
        queue_wait_time_seconds=MagicMock(),
        retry_delay_seconds=MagicMock(),
        dead_lettered_jobs=MagicMock(),
        oldest_dead_letter_age_seconds=None,
        registry=MagicMock(),
    )
    with (
        patch.object(
            observability,
            "_notification_queue_metrics",
            previous_bundle_without_age,
        ),
        patch.object(
            observability, "create_notification_queue_metrics", return_value=fresh
        ),
    ):
        assert (
            observability.reinitialize_notification_queue_metrics(registry=registry)
            is fresh
        )
    previous_bundle_without_age.registry.unregister.assert_called()

    observability._notification_queue_metrics = None
    marker = object()
    lock = MagicMock()
    lock.__enter__.side_effect = lambda: setattr(
        observability, "_notification_queue_metrics", marker
    )
    with (
        patch.object(observability, "_notification_queue_metrics_lock", lock),
        patch.object(observability, "create_notification_queue_metrics") as create,
    ):
        assert observability.get_notification_queue_metrics() is marker
    create.assert_not_called()

    previous = observability._notification_queue_metrics
    observability._notification_queue_metrics = None
    with (
        patch.object(observability, "Gauge", None),
        patch.object(observability, "Counter", None),
        patch.object(observability, "Histogram", None),
        patch.object(observability, "CollectorRegistry", None),
        patch.object(observability, "REGISTRY", None),
    ):
        with pytest.raises(RuntimeError, match="prometheus-client"):
            observability.get_notification_queue_metrics()
    observability._notification_queue_metrics = previous

    observability._notification_queue_metrics = None
    with patch.object(
        observability, "create_notification_queue_metrics", return_value=fresh
    ):
        assert (
            observability.reinitialize_notification_queue_metrics(registry=registry)
            is fresh
        )


def test_notification_queue_metrics_require_prometheus() -> None:
    from app.core import observability

    with (
        patch.object(observability, "Gauge", None),
        patch.object(observability, "Counter", None),
        patch.object(observability, "Histogram", None),
        patch.object(observability, "CollectorRegistry", None),
        patch.object(observability, "REGISTRY", None),
    ):
        with pytest.raises(RuntimeError, match="prometheus-client"):
            observability.create_notification_queue_metrics()
