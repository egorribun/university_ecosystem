"""Behavioral coverage closure for metrics runtime and access controls."""

from __future__ import annotations

import base64
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import Response


def _request(
    *,
    path: str = "/metrics",
    client: tuple[str, int] | None = ("127.0.0.1", 12345),
    headers: dict[str, str] | None = None,
) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "root_path": "",
        "headers": [
            (name.lower().encode("latin-1"), value.encode("latin-1"))
            for name, value in (headers or {}).items()
        ],
        "client": client,
        "server": ("testserver", 80),
        "scheme": "http",
    }
    return Request(scope)


def test_metric_factory_reuses_existing_collectors_and_reraises_unknown_duplicates() -> (
    None
):
    from app.core import metrics

    existing = object()
    registry = SimpleNamespace(_names_to_collectors={"existing_metric": existing})
    with patch.object(metrics, "REGISTRY", registry):
        assert (
            metrics._get_or_create_metric(MagicMock(), "existing_metric", "doc")
            is existing
        )

        class DuplicateMetric:
            def __init__(self, *_args, **_kwargs):
                raise ValueError("duplicate metric")

        assert (
            metrics._get_or_create_metric(DuplicateMetric, "existing_metric", "doc")
            is existing
        )

        with pytest.raises(ValueError, match="duplicate metric"):
            metrics._get_or_create_metric(DuplicateMetric, "unknown_metric", "doc")

        class RegisterThenDuplicate:
            def __init__(self, name, *_args, **_kwargs):
                registry._names_to_collectors[name] = existing
                raise ValueError("registered duplicate metric")

        assert (
            metrics._get_or_create_metric(
                RegisterThenDuplicate, "registered_metric", "doc"
            )
            is existing
        )

    assert metrics._get_or_create_metric(None, "disabled_metric", "doc") is None


def test_optional_event_metric_recorders_swallow_backend_errors() -> None:
    from app.core import metrics

    failing = MagicMock()
    failing.labels.side_effect = RuntimeError("metric backend unavailable")
    with (
        patch.object(metrics, "_SPICEDB_WATCH_EVENTS", failing),
        patch.object(metrics, "_WS_HUB_SESSIONS_REVOKED", failing),
        patch.object(metrics, "_ABAC_ACCESS_DENIED", failing),
    ):
        metrics.record_spicedb_watch_event()
        metrics.record_ws_hub_session_revoked()
        metrics.record_abac_access_denied()

    with (
        patch.object(metrics, "_SPICEDB_WATCH_EVENTS", None),
        patch.object(metrics, "_WS_HUB_SESSIONS_REVOKED", None),
        patch.object(metrics, "_ABAC_ACCESS_DENIED", None),
    ):
        metrics.record_spicedb_watch_event()
        metrics.record_ws_hub_session_revoked()
        metrics.record_abac_access_denied()


def test_metric_recorders_fail_closed_when_prometheus_is_unavailable() -> None:
    from app.core import metrics

    names = (
        "_BACKGROUND_TASK_ERRORS",
        "_LOGIN_SUCCESS",
        "_LOGIN_FAILURE",
        "_NOTIFICATIONS_DELIVERED",
        "_NOTIFICATIONS_FAILED",
        "_EVENT_REGISTRATIONS",
        "_ACTIVE_USERS",
        "_MFA_ADOPTION",
        "_PRESENCE_EVENTS",
        "_PRESENCE_THROTTLED",
        "_CSP_REPORTS",
        "_CHAT_MESSAGES_TOTAL",
        "_WS_CONNECTIONS_ACTIVE",
        "_CACHE_HITS",
        "_CACHE_MISSES",
        "_CIRCUIT_BREAKER_STATE",
        "_CIRCUIT_BREAKER_TRIPS",
    )
    with patch.multiple(metrics, **{name: None for name in names}):
        metrics.record_background_task_error("worker")
        metrics.record_login_success()
        metrics.record_login_failure()
        metrics.record_notification_delivered("email")
        metrics.record_notification_failed("email", "timeout")
        metrics.record_event_registration()
        metrics.set_active_users(1)
        metrics.set_mfa_adoption(1)
        metrics.record_presence_event("online", "web")
        metrics.record_presence_throttled("online", "web")
        metrics.record_csp_report("blocked")
        metrics.record_chat_message("direct")
        metrics.set_ws_connections_active("/ws", 1)
        metrics.inc_ws_connections("/ws")
        metrics.dec_ws_connections("/ws")
        metrics.record_cache_hit()
        metrics.record_cache_miss()
        metrics.record_circuit_breaker_state("redis", "open")
        metrics.record_circuit_breaker_trip("redis")


def test_metrics_authorization_rejects_malformed_and_wrong_credentials(
    monkeypatch,
) -> None:
    from app.core import metrics

    # Patch the dependency where the module under test looks it up.  A separate
    # config reload test may legitimately replace ``app.core.config.settings``
    # during the same process, while ``metrics.settings`` remains its imported
    # singleton.  Patching the lookup site keeps this authorization contract
    # independent from module reload order.
    monkeypatch.setattr(
        metrics,
        "settings",
        SimpleNamespace(
            metrics_basic_auth_username="metrics-user",
            metrics_basic_auth_password="metrics-pass",  # pragma: allowlist secret
        ),
    )

    assert metrics._is_authorized(_request()) is False
    assert (
        metrics._is_authorized(_request(headers={"Authorization": "Basic !!!"}))
        is False
    )
    no_separator = base64.b64encode(b"metrics-user").decode()
    assert (
        metrics._is_authorized(
            _request(headers={"Authorization": f"Basic {no_separator}"})
        )
        is False
    )
    wrong = base64.b64encode(b"metrics-user:wrong").decode()
    assert (
        metrics._is_authorized(_request(headers={"Authorization": f"Basic {wrong}"}))
        is False
    )
    valid = base64.b64encode(b"metrics-user:metrics-pass").decode()
    assert (
        metrics._is_authorized(_request(headers={"Authorization": f"Basic {valid}"}))
        is True
    )


def test_metrics_authorization_allows_only_loopback_without_credentials(
    monkeypatch,
) -> None:
    from app.core import metrics
    from app.core.config import settings

    monkeypatch.setattr(settings, "metrics_basic_auth_username", "")
    monkeypatch.setattr(settings, "metrics_basic_auth_password", "")
    monkeypatch.setattr(settings, "metrics_allowlist", "127.0.0.1,localhost")
    assert metrics._is_authorized(_request()) is True

    monkeypatch.setattr(settings, "metrics_allowlist", "10.0.0.0/8")
    assert metrics._is_authorized(_request()) is False

    monkeypatch.setattr(settings, "metrics_basic_auth_username", "metrics-user")
    monkeypatch.setattr(settings, "metrics_basic_auth_password", "")
    assert metrics._is_authorized(_request()) is False


def test_metrics_allowlist_handles_empty_invalid_and_hostname_values(
    monkeypatch,
) -> None:
    from app.core import metrics
    from app.core.config import settings

    monkeypatch.setattr(settings, "metrics_allowlist", " , 127.0.0.1, ")
    assert list(metrics._iter_allowlist()) == ["127.0.0.1"]
    assert metrics._is_loopback_value("not-an-address") is False

    monkeypatch.setattr(settings, "metrics_allowlist", "")
    assert metrics._is_allowed(_request()) is True

    monkeypatch.setattr(settings, "metrics_allowlist", "example.com")
    assert metrics._is_allowed(_request(client=("example.com", 80))) is True
    assert metrics._is_allowed(_request(client=("other.example", 80))) is False
    assert metrics._is_allowed(_request(client=None)) is False
    assert metrics._is_allowed(_request(client=("", 80))) is False

    monkeypatch.setattr(settings, "metrics_allowlist", "10.0.0.0/8")
    assert metrics._is_allowed(_request(client=("10.1.2.3", 80))) is True
    assert metrics._is_allowed(_request(client=("not-an-ip", 80))) is False


def test_metrics_auth_configuration_covers_disabled_and_loopback_modes(
    monkeypatch,
) -> None:
    from app.core import metrics
    from app.core.config import settings

    monkeypatch.setattr(settings, "enable_metrics_endpoint", False)
    assert metrics._metrics_auth_config_is_invalid() is False

    monkeypatch.setattr(settings, "enable_metrics_endpoint", True)
    monkeypatch.setattr(settings, "metrics_basic_auth_username", "")
    monkeypatch.setattr(settings, "metrics_basic_auth_password", "")
    monkeypatch.setattr(settings, "metrics_allowlist", "127.0.0.1")
    assert metrics._metrics_auth_config_is_invalid() is False


@pytest.mark.asyncio
async def test_request_metrics_middleware_records_success_error_and_noop() -> None:
    from app.core import metrics

    request = _request()
    response = Response(status_code=200)
    call_next = AsyncMock(return_value=response)
    counter = MagicMock()
    duration = MagicMock()
    router_duration = MagicMock()
    router_errors = MagicMock()

    with (
        patch.object(metrics, "_REQUEST_COUNT", counter),
        patch.object(metrics, "_REQUEST_DURATION", duration),
        patch.object(metrics, "_ROUTER_DURATION", router_duration),
        patch.object(metrics, "_ROUTER_ERRORS", router_errors),
        patch.object(metrics.time, "perf_counter", side_effect=[1.0, 1.2]),
    ):
        result = await metrics.PrometheusRequestMetricsMiddleware(MagicMock()).dispatch(
            request, call_next
        )

    assert result is response
    counter.labels.assert_called_once()
    duration.labels.assert_called_once()
    router_duration.labels.assert_called_once()
    router_errors.labels.assert_not_called()

    async def raise_error(_request):
        raise RuntimeError("handler failed")

    with (
        patch.object(metrics, "_REQUEST_COUNT", counter),
        patch.object(metrics, "_REQUEST_DURATION", duration),
        patch.object(metrics, "_ROUTER_DURATION", router_duration),
        patch.object(metrics, "_ROUTER_ERRORS", router_errors),
        patch.object(metrics.time, "perf_counter", side_effect=[2.0, 2.1]),
    ):
        with pytest.raises(RuntimeError, match="handler failed"):
            await metrics.PrometheusRequestMetricsMiddleware(MagicMock()).dispatch(
                request, raise_error
            )

    router_errors.labels.assert_called()

    no_count = AsyncMock(return_value=response)
    with (
        patch.object(metrics, "_REQUEST_COUNT", None),
        patch.object(metrics, "_REQUEST_DURATION", None),
    ):
        assert (
            await metrics.PrometheusRequestMetricsMiddleware(MagicMock()).dispatch(
                request, no_count
            )
        ) is response

    with (
        patch.object(metrics, "_REQUEST_COUNT", counter),
        patch.object(metrics, "_REQUEST_DURATION", duration),
        patch.object(metrics, "_ROUTER_DURATION", None),
        patch.object(metrics, "_ROUTER_ERRORS", router_errors),
        patch.object(metrics.time, "perf_counter", side_effect=[3.0, 3.1]),
    ):
        await metrics.PrometheusRequestMetricsMiddleware(MagicMock()).dispatch(
            request, call_next
        )


def test_metrics_route_and_router_fallbacks() -> None:
    from app.core import metrics

    request = _request(path="/raw")
    request.scope["route"] = SimpleNamespace(path="", owner=None)
    assert metrics._resolve_path_template(request) == "/raw"
    request.scope["route"] = SimpleNamespace(
        path=None, owner=SimpleNamespace(prefix="/owner")
    )
    assert metrics._resolve_router_label(request) == "/owner"
    request.scope["route"] = SimpleNamespace(path=None, owner=None)
    assert metrics._resolve_router_label(request) == "root"


def test_metric_recorders_swallow_backend_errors() -> None:
    from app.core import metrics

    failing = MagicMock()
    failing.labels.side_effect = RuntimeError("metric backend unavailable")
    with (
        patch.object(metrics, "_HEALTH_CHECK_DURATION", failing),
        patch.object(metrics, "_HEALTH_CHECK_STATUS", failing),
        patch.object(metrics, "_REDIS_COMMAND_DURATION", failing),
        patch.object(metrics, "_REDIS_COMMAND_ERRORS", failing),
        patch.object(metrics, "_DB_OPERATION_DURATION", failing),
        patch.object(metrics, "_DB_OPERATION_ERRORS", failing),
    ):
        metrics.record_health_probe("db", "error", -1.0)
        metrics.record_redis_command("GET", -1.0, success=False)
        metrics.record_db_operation("select", -1.0, success=False)


@pytest.mark.asyncio
async def test_record_cache_metrics_covers_nonredis_success_and_failure() -> None:
    from app.core import metrics
    from app.deps import cache as cache_module

    entries = MagicMock()
    memory = MagicMock()
    health = MagicMock()
    with (
        patch.object(metrics, "_CACHE_ENTRIES", entries),
        patch.object(metrics, "_CACHE_MEMORY_BYTES", memory),
        patch.object(metrics, "_REDIS_HEALTH", health),
        patch.object(cache_module, "get_cache", return_value=object()),
    ):
        await metrics._record_cache_metrics()
    entries.set.assert_called_with(0)
    memory.set.assert_called_with(0)
    health.set.assert_called_with(0)

    redis_type = type("RedisCache", (), {})
    backend = redis_type()
    client = AsyncMock()
    client.ping.return_value = True
    client.info.return_value = {"used_memory": 12}
    client.dbsize.return_value = 4
    backend._get_client = AsyncMock(return_value=client)
    with (
        patch.object(cache_module, "RedisCache", redis_type),
        patch.object(cache_module, "get_cache", return_value=backend),
        patch.object(metrics, "_CACHE_ENTRIES", entries),
        patch.object(metrics, "_CACHE_MEMORY_BYTES", memory),
        patch.object(metrics, "_REDIS_HEALTH", health),
    ):
        await metrics._record_cache_metrics()

    with (
        patch.object(cache_module, "RedisCache", redis_type),
        patch.object(cache_module, "get_cache", return_value=backend),
        patch.object(metrics, "_CACHE_ENTRIES", MagicMock()),
        patch.object(metrics, "_CACHE_MEMORY_BYTES", None),
        patch.object(metrics, "_REDIS_HEALTH", None),
    ):
        await metrics._record_cache_metrics()
    entries.set.assert_called_with(4.0)
    memory.set.assert_called_with(12.0)
    health.set.assert_called_with(1)

    client.ping.side_effect = RuntimeError("redis down")
    with (
        patch.object(cache_module, "RedisCache", redis_type),
        patch.object(cache_module, "get_cache", return_value=backend),
        patch.object(metrics, "_CACHE_ENTRIES", entries),
        patch.object(metrics, "_CACHE_MEMORY_BYTES", memory),
        patch.object(metrics, "_REDIS_HEALTH", health),
        patch.object(metrics, "record_redis_command") as record_command,
    ):
        await metrics._record_cache_metrics()
    health.set.assert_called_with(0)
    record_command.assert_called_once_with("ping", 0.0, success=False)


@pytest.mark.asyncio
async def test_record_cache_metrics_returns_when_all_metrics_disabled() -> None:
    from app.core import metrics

    with (
        patch.object(metrics, "_CACHE_ENTRIES", None),
        patch.object(metrics, "_CACHE_MEMORY_BYTES", None),
        patch.object(metrics, "_REDIS_HEALTH", None),
    ):
        await metrics._record_cache_metrics()


def test_record_pool_metrics_handles_complete_partial_and_broken_pools() -> None:
    from app.core import metrics

    pool = SimpleNamespace(
        size=lambda: 5,
        checkedout=lambda: 2,
        overflow=lambda: 1,
        checkedin=lambda: 3,
    )
    engine = SimpleNamespace(sync_engine=SimpleNamespace(pool=pool))
    with (
        patch.object(metrics, "engine", engine),
        patch.object(metrics, "_DB_POOL_SIZE", MagicMock()),
        patch.object(metrics, "_DB_POOL_CHECKEDOUT", MagicMock()),
        patch.object(metrics, "_DB_POOL_OVERFLOW", MagicMock()),
        patch.object(metrics, "_DB_POOL_CHECKEDIN", MagicMock()),
    ):
        metrics._record_pool_metrics()

    with patch.object(
        metrics,
        "engine",
        SimpleNamespace(
            sync_engine=SimpleNamespace(pool=SimpleNamespace(size=lambda: 1))
        ),
    ):
        metrics._record_pool_metrics()

    broken_pool = SimpleNamespace(
        size=lambda: (_ for _ in ()).throw(RuntimeError("pool"))
    )
    with patch.object(
        metrics,
        "engine",
        SimpleNamespace(sync_engine=SimpleNamespace(pool=broken_pool)),
    ):
        metrics._record_pool_metrics()


@pytest.mark.asyncio
async def test_record_db_metrics_records_success_and_failure() -> None:
    from app.core import metrics

    class Connection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, _statement):
            return None

    class Engine:
        def connect(self):
            return Connection()

    with (
        patch.object(metrics, "_DB_HEALTH", MagicMock()),
        patch.object(metrics, "_DB_OPERATION_DURATION", MagicMock()),
        patch.object(metrics, "_record_pool_metrics"),
        patch.object(metrics, "engine", Engine()),
        patch.object(metrics, "record_db_operation") as record_operation,
    ):
        await metrics._record_db_metrics()
    record_operation.assert_called_once()
    assert record_operation.call_args.kwargs["success"] is True

    class FailingConnection(Connection):
        async def execute(self, _statement):
            raise RuntimeError("database down")

    class FailingEngine:
        def connect(self):
            return FailingConnection()

    with (
        patch.object(metrics, "_DB_HEALTH", MagicMock()),
        patch.object(metrics, "_DB_OPERATION_DURATION", MagicMock()),
        patch.object(metrics, "_record_pool_metrics"),
        patch.object(metrics, "engine", FailingEngine()),
        patch.object(metrics, "record_db_operation") as record_operation,
    ):
        await metrics._record_db_metrics()
    assert record_operation.call_args.kwargs["success"] is False


def test_load_gputil_handles_missing_loader_and_loaded_module() -> None:
    from app.core import metrics

    with patch.object(metrics.importlib.util, "find_spec", return_value=None):
        assert metrics._load_gputil() is None

    with (
        patch.object(
            metrics.importlib.util,
            "find_spec",
            return_value=SimpleNamespace(name="GPUtil", loader=None),
        ),
        patch.object(
            metrics.importlib.util,
            "module_from_spec",
            return_value=SimpleNamespace(),
        ),
    ):
        assert metrics._load_gputil() is None

    module = SimpleNamespace()
    loader = MagicMock()
    spec = SimpleNamespace(loader=loader)
    with (
        patch.object(metrics.importlib.util, "find_spec", return_value=spec),
        patch.object(metrics.importlib.util, "module_from_spec", return_value=module),
    ):
        assert metrics._load_gputil() is module
    loader.exec_module.assert_called_once_with(module)


def test_record_system_metrics_covers_cpu_gpu_and_missing_gpu() -> None:
    from app.core import metrics

    cpu = MagicMock()
    gpu = MagicMock()
    gpu.getGPUs.return_value = [SimpleNamespace(id=1, name="gpu", load=0.5)]
    with (
        patch.object(metrics, "_CPU_LOAD", cpu),
        patch.object(metrics, "_GPU_LOAD", gpu),
        patch.object(metrics, "psutil") as psutil,
        patch.object(metrics, "_load_gputil", return_value=gpu),
    ):
        psutil.cpu_percent.return_value = 10.0
        metrics._record_system_metrics()
    cpu.set.assert_called_with(10.0)
    gpu.labels.assert_called_once_with(index="1", name="gpu")

    with (
        patch.object(metrics, "_CPU_LOAD", None),
        patch.object(metrics, "_GPU_LOAD", gpu),
        patch.object(metrics, "_load_gputil", return_value=None),
    ):
        metrics._record_system_metrics()
    gpu.clear.assert_called()


@pytest.mark.asyncio
async def test_refresh_runtime_metrics_orchestrates_all_sources() -> None:
    from app.core import metrics

    with (
        patch.object(metrics, "_record_cache_metrics", new_callable=AsyncMock),
        patch.object(metrics, "_record_db_metrics", new_callable=AsyncMock),
        patch.object(metrics, "_record_system_metrics") as record_system,
    ):
        await metrics.refresh_runtime_metrics()
    record_system.assert_called_once()


@pytest.mark.asyncio
async def test_metrics_endpoint_security_and_success_paths(monkeypatch) -> None:
    from app.core import metrics
    from app.core.config import settings

    monkeypatch.setattr(settings, "enable_metrics_endpoint", False)
    response = await metrics.metrics_endpoint(_request())
    assert response.status_code == 404

    monkeypatch.setattr(settings, "enable_metrics_endpoint", True)
    monkeypatch.setattr(settings, "metrics_basic_auth_username", "")
    monkeypatch.setattr(settings, "metrics_basic_auth_password", "")
    monkeypatch.setattr(settings, "metrics_allowlist", "10.0.0.0/8")
    with patch.object(metrics, "_ensure_notification_queue_metrics_registry"):
        response = await metrics.metrics_endpoint(_request())
    assert response.status_code == 503

    monkeypatch.setattr(settings, "metrics_basic_auth_username", "user")
    monkeypatch.setattr(settings, "metrics_basic_auth_password", "pass")
    monkeypatch.setattr(settings, "metrics_allowlist", "")
    with patch.object(metrics, "_ensure_notification_queue_metrics_registry"):
        response = await metrics.metrics_endpoint(_request())
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == 'Basic realm="Metrics"'

    valid = base64.b64encode(b"user:pass").decode()
    monkeypatch.setattr(settings, "metrics_allowlist", "10.0.0.0/8")
    with patch.object(metrics, "_ensure_notification_queue_metrics_registry"):
        response = await metrics.metrics_endpoint(
            _request(headers={"Authorization": f"Basic {valid}"})
        )
    assert response.status_code == 403

    monkeypatch.setattr(settings, "metrics_allowlist", "")
    with (
        patch.object(metrics, "_ensure_notification_queue_metrics_registry"),
        patch.object(metrics, "refresh_runtime_metrics", new_callable=AsyncMock),
        patch.object(metrics, "generate_latest", return_value=b"metrics"),
    ):
        response = await metrics.metrics_endpoint(
            _request(headers={"Authorization": f"Basic {valid}"})
        )
    assert response.status_code == 200
    assert response.body == b"metrics"
    assert response.headers["cache-control"] == "no-store"

    with (
        patch.object(metrics, "_ensure_notification_queue_metrics_registry"),
        patch.object(metrics, "REGISTRY", None),
    ):
        with pytest.raises(RuntimeError, match="prometheus-client"):
            await metrics.metrics_endpoint(
                _request(headers={"Authorization": f"Basic {valid}"})
            )


def test_configure_metrics_short_circuits_invalid_and_identical_credentials(
    monkeypatch,
) -> None:
    from app.core import metrics
    from app.core.config import settings

    app = FastAPI()
    app.state._metrics_configured = True
    metrics.configure_metrics(app)

    app.state._metrics_configured = False
    monkeypatch.setattr(settings, "enable_metrics_endpoint", True)
    monkeypatch.setattr(settings, "metrics_basic_auth_username", "same-strong-value")
    monkeypatch.setattr(settings, "metrics_basic_auth_password", "same-strong-value")
    monkeypatch.setattr(settings, "metrics_allowlist", "")
    metrics.configure_metrics(app)
    assert getattr(app.state, "_metrics_configured", False) is False

    monkeypatch.setattr(settings, "enable_metrics_endpoint", False)
    metrics.configure_metrics(app)
    assert app.state._metrics_configured is True


def test_metrics_branch_matrix_for_optional_guards(monkeypatch) -> None:
    from app.core import metrics
    from app.core.config import settings

    with patch.object(
        type(settings),
        "metrics_allowlist_entries",
        new=property(lambda _: ["", "127.0.0.1"]),
    ):
        assert list(metrics._iter_allowlist()) == ["127.0.0.1"]

    with (
        patch.object(metrics, "ip_network", side_effect=ValueError),
        patch.object(
            metrics, "ip_address", return_value=SimpleNamespace(is_loopback=True)
        ),
    ):
        assert metrics._is_loopback_value("loopback-with-scope") is True

    route = SimpleNamespace(
        router=SimpleNamespace(prefix=None), owner=SimpleNamespace(prefix="/owner")
    )
    request = _request()
    request.scope["route"] = route
    assert metrics._resolve_router_label(request) == "/owner"

    with (
        patch.object(metrics, "_HEALTH_CHECK_DURATION", MagicMock()),
        patch.object(metrics, "_HEALTH_CHECK_STATUS", None),
    ):
        metrics.record_health_probe("db", "ok", 0.1)
    with (
        patch.object(metrics, "_HEALTH_CHECK_DURATION", None),
        patch.object(metrics, "_HEALTH_CHECK_STATUS", MagicMock()),
    ):
        metrics.record_health_probe("db", "ok", 0.1)

    with (
        patch.object(metrics, "_REDIS_COMMAND_DURATION", None),
        patch.object(metrics, "_REDIS_COMMAND_ERRORS", MagicMock()),
    ):
        metrics.record_redis_command("GET", 0.1, success=False)
    with (
        patch.object(metrics, "_DB_OPERATION_DURATION", None),
        patch.object(metrics, "_DB_OPERATION_ERRORS", MagicMock()),
    ):
        metrics.record_db_operation("select", 0.1, success=False)


@pytest.mark.asyncio
async def test_cache_and_pool_optional_metric_combinations() -> None:
    from app.core import metrics
    from app.deps import cache as cache_module

    redis_type = type("RedisCache", (), {})
    backend = redis_type()
    client = AsyncMock()
    client.ping.return_value = True
    client.info.return_value = {"used_memory": "not-a-number"}
    client.dbsize.return_value = 3
    backend._get_client = AsyncMock(return_value=client)
    with (
        patch.object(cache_module, "RedisCache", redis_type),
        patch.object(cache_module, "get_cache", return_value=backend),
        patch.object(metrics, "_CACHE_ENTRIES", None),
        patch.object(metrics, "_CACHE_MEMORY_BYTES", MagicMock()),
        patch.object(metrics, "_REDIS_HEALTH", None),
    ):
        await metrics._record_cache_metrics()

    memory = MagicMock()
    with (
        patch.object(cache_module, "get_cache", return_value=object()),
        patch.object(metrics, "_CACHE_ENTRIES", None),
        patch.object(metrics, "_CACHE_MEMORY_BYTES", memory),
        patch.object(metrics, "_REDIS_HEALTH", None),
    ):
        await metrics._record_cache_metrics()
        memory.set.assert_called_once_with(0)

    health = MagicMock()
    with (
        patch.object(cache_module, "get_cache", return_value=object()),
        patch.object(metrics, "_CACHE_ENTRIES", MagicMock()),
        patch.object(metrics, "_CACHE_MEMORY_BYTES", None),
        patch.object(metrics, "_REDIS_HEALTH", health),
    ):
        await metrics._record_cache_metrics()
    health.set.assert_called_with(0)

    pool = SimpleNamespace(
        size=lambda: 1,
        checkedout=lambda: 2,
        overflow=lambda: 3,
        checkedin=lambda: 4,
    )
    with (
        patch.object(
            metrics,
            "engine",
            SimpleNamespace(sync_engine=SimpleNamespace(pool=pool)),
        ),
        patch.object(metrics, "_DB_POOL_SIZE", None),
        patch.object(metrics, "_DB_POOL_CHECKEDOUT", MagicMock()),
        patch.object(metrics, "_DB_POOL_OVERFLOW", None),
        patch.object(metrics, "_DB_POOL_CHECKEDIN", MagicMock()),
    ):
        metrics._record_pool_metrics()

    with (
        patch.object(
            metrics,
            "engine",
            SimpleNamespace(sync_engine=SimpleNamespace(pool=pool)),
        ),
        patch.object(metrics, "_DB_POOL_SIZE", MagicMock()),
        patch.object(metrics, "_DB_POOL_CHECKEDOUT", None),
        patch.object(metrics, "_DB_POOL_OVERFLOW", MagicMock()),
        patch.object(metrics, "_DB_POOL_CHECKEDIN", None),
    ):
        metrics._record_pool_metrics()


@pytest.mark.asyncio
async def test_db_system_and_registry_guard_branches(monkeypatch) -> None:
    from app.core import metrics, observability
    from app.core.config import settings

    with (
        patch.object(metrics, "_DB_HEALTH", None),
        patch.object(metrics, "_DB_OPERATION_DURATION", None),
        patch.object(metrics, "_record_pool_metrics"),
    ):
        await metrics._record_db_metrics()

    with (
        patch.object(metrics, "_DB_HEALTH", None),
        patch.object(metrics, "_DB_OPERATION_DURATION", MagicMock()),
        patch.object(metrics, "_record_pool_metrics"),
        patch.object(metrics, "record_db_operation") as record_operation,
    ):
        await metrics._record_db_metrics()
    assert record_operation.call_args.kwargs["success"] is True

    with (
        patch.object(metrics, "_CPU_LOAD", MagicMock()),
        patch.object(metrics, "_GPU_LOAD", None),
        patch.object(metrics, "psutil") as psutil,
    ):
        psutil.cpu_percent.return_value = 1.0
        metrics._record_system_metrics()

    with patch.object(metrics, "REGISTRY", None):
        metrics._ensure_notification_queue_metrics_registry()

    with patch.object(
        observability,
        "get_notification_queue_metrics",
        side_effect=RuntimeError("metrics not initialized"),
    ):
        metrics._ensure_notification_queue_metrics_registry()

    fresh = object()
    foreign = object()
    with (
        patch.object(
            observability,
            "get_notification_queue_metrics",
            return_value=SimpleNamespace(registry=foreign),
        ),
        patch.object(
            observability,
            "reinitialize_notification_queue_metrics",
            return_value=fresh,
        ),
        patch.object(metrics, "REGISTRY", metrics.REGISTRY),
    ):
        metrics._ensure_notification_queue_metrics_registry()

    app = FastAPI()
    monkeypatch.setattr(settings, "enable_metrics_endpoint", True)
    monkeypatch.setattr(settings, "metrics_basic_auth_username", "")
    monkeypatch.setattr(settings, "metrics_basic_auth_password", "")
    monkeypatch.setattr(settings, "metrics_allowlist", "10.0.0.0/8")
    with pytest.raises(RuntimeError, match="requires credentials"):
        metrics.configure_metrics(app)


def test_configure_metrics_credential_and_otel_branches(monkeypatch) -> None:
    from opentelemetry.sdk import metrics as otel_sdk_metrics
    from opentelemetry.sdk import resources as otel_resources

    from app.core import metrics, observability
    from app.core.config import settings

    monkeypatch.setattr(settings, "enable_metrics_endpoint", True)
    monkeypatch.setattr(settings, "metrics_allowlist", "")
    monkeypatch.setattr(settings, "metrics_basic_auth_username", "operator")
    monkeypatch.setattr(settings, "metrics_basic_auth_password", "operator")
    app = FastAPI()
    metrics.configure_metrics(app)
    assert getattr(app.state, "_metrics_configured", False) is False

    monkeypatch.setattr(settings, "metrics_basic_auth_password", "password")
    app = FastAPI()
    metrics.configure_metrics(app)
    assert getattr(app.state, "_metrics_configured", False) is False

    monkeypatch.setattr(settings, "metrics_basic_auth_username", "operator")
    monkeypatch.setattr(settings, "metrics_basic_auth_password", "different-secret")
    app = FastAPI()
    metrics.configure_metrics(app)
    assert app.state._metrics_configured is True

    monkeypatch.setattr(settings, "metrics_basic_auth_username", "operator")
    monkeypatch.setattr(settings, "metrics_basic_auth_password", "different-secret")
    app = FastAPI()
    with (
        patch.dict(
            sys.modules,
            {
                "opentelemetry.exporter.prometheus": SimpleNamespace(
                    PrometheusMetricReader=MagicMock(return_value=MagicMock())
                )
            },
        ),
        patch.object(
            otel_sdk_metrics,
            "MeterProvider",
            MagicMock(return_value=MagicMock()),
        ),
        patch.object(otel_resources.Resource, "create", return_value=MagicMock()),
        patch("opentelemetry.metrics.set_meter_provider"),
    ):
        metrics.configure_metrics(app)
    assert app.state._metrics_configured is True

    app = FastAPI()
    with (
        patch.dict(
            sys.modules,
            {
                "opentelemetry.exporter.prometheus": SimpleNamespace(
                    PrometheusMetricReader=MagicMock(return_value=MagicMock())
                )
            },
        ),
        patch.object(
            otel_resources.Resource, "create", side_effect=RuntimeError("otel")
        ),
    ):
        metrics.configure_metrics(app)
    assert app.state._metrics_configured is True

    app = FastAPI()
    with patch.object(observability, "get_notification_queue_metrics", None):
        metrics.configure_metrics(app)
    assert app.state._metrics_configured is True

    app = FastAPI()
    with patch.object(
        observability,
        "get_notification_queue_metrics",
        side_effect=RuntimeError("not ready"),
    ):
        metrics.configure_metrics(app)
    assert app.state._metrics_configured is True
