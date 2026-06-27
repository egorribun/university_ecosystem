from unittest.mock import MagicMock, patch

import pytest
from prometheus_client import REGISTRY

import app.core.metrics as m
import app.core.observability as obs


def test_record_background_task_error():
    m.record_background_task_error("my_test_task")
    val = REGISTRY.get_sample_value(
        "background_task_errors_total", {"task_name": "my_test_task"}
    )
    assert val is not None
    assert val >= 1.0


def test_record_login_success():
    m.record_login_success("password")
    val = REGISTRY.get_sample_value("auth_login_success_total", {"method": "password"})
    assert val is not None
    assert val >= 1.0


def test_record_login_failure():
    m.record_login_failure("invalid_credentials")
    val = REGISTRY.get_sample_value(
        "auth_login_failure_total", {"reason": "invalid_credentials"}
    )
    assert val is not None
    assert val >= 1.0


def test_record_notification_delivered():
    m.record_notification_delivered("email")
    val = REGISTRY.get_sample_value("notifications_delivered_total", {"type": "email"})
    assert val is not None
    assert val >= 1.0


def test_record_notification_failed():
    m.record_notification_failed("sms", "timeout")
    val = REGISTRY.get_sample_value(
        "notifications_failed_total", {"type": "sms", "reason": "timeout"}
    )
    assert val is not None
    assert val >= 1.0


def test_record_event_registration():
    before = REGISTRY.get_sample_value("event_registrations_total") or 0.0
    m.record_event_registration()
    after = REGISTRY.get_sample_value("event_registrations_total") or 0.0
    assert after == before + 1.0


def test_set_active_users():
    m.set_active_users(42, "daily")
    val = REGISTRY.get_sample_value("active_users_count", {"period": "daily"})
    assert val == 42.0


def test_set_mfa_adoption():
    m.set_mfa_adoption(100)
    val = REGISTRY.get_sample_value("mfa_enabled_users_total")
    assert val == 100.0


def test_record_presence_event():
    m.record_presence_event("online", "web")
    val = REGISTRY.get_sample_value(
        "websocket_presence_events_total", {"state": "online", "source": "web"}
    )
    assert val is not None
    assert val >= 1.0


def test_record_presence_throttled():
    m.record_presence_throttled("away", "mobile")
    val = REGISTRY.get_sample_value(
        "websocket_presence_throttled_total", {"state": "away", "source": "mobile"}
    )
    assert val is not None
    assert val >= 1.0


def test_record_csp_report():
    m.record_csp_report("enforced")
    val = REGISTRY.get_sample_value("csp_reports_total", {"outcome": "enforced"})
    assert val is not None
    assert val >= 1.0


def test_record_chat_message():
    m.record_chat_message("direct")
    val = REGISTRY.get_sample_value("chat_messages_total", {"channel": "direct"})
    assert val is not None
    assert val >= 1.0


def test_websocket_connections():
    m.set_ws_connections_active("/ws/chat", 5)
    assert (
        REGISTRY.get_sample_value("websocket_connections_active", {"path": "/ws/chat"})
        == 5.0
    )
    m.inc_ws_connections("/ws/chat")
    assert (
        REGISTRY.get_sample_value("websocket_connections_active", {"path": "/ws/chat"})
        == 6.0
    )
    m.dec_ws_connections("/ws/chat")
    assert (
        REGISTRY.get_sample_value("websocket_connections_active", {"path": "/ws/chat"})
        == 5.0
    )


def test_record_cache_hits_misses():
    m.record_cache_hit("redis")
    assert REGISTRY.get_sample_value("cache_hits_total", {"backend": "redis"}) >= 1.0
    m.record_cache_miss("redis")
    assert REGISTRY.get_sample_value("cache_misses_total", {"backend": "redis"}) >= 1.0


def test_record_circuit_breaker():
    m.record_circuit_breaker_state("clamav", "open")
    assert (
        REGISTRY.get_sample_value("circuit_breaker_state", {"service": "clamav"})
        is not None
    )
    m.record_circuit_breaker_trip("clamav")
    assert (
        REGISTRY.get_sample_value("circuit_breaker_trips_total", {"service": "clamav"})
        >= 1.0
    )


def test_record_health_probe():
    m.record_health_probe("db", "ok", 0.05)
    assert (
        REGISTRY.get_sample_value(
            "healthcheck_status_total", {"component": "db", "status": "ok"}
        )
        >= 1.0
    )


def test_record_redis_command():
    m.record_redis_command("GET", 0.002, success=True)
    assert (
        REGISTRY.get_sample_value(
            "redis_command_duration_seconds_count", {"command": "GET"}
        )
        >= 1.0
    )
    m.record_redis_command("SET", 0.005, success=False)
    assert (
        REGISTRY.get_sample_value("redis_command_errors_total", {"command": "SET"})
        >= 1.0
    )


def test_record_db_operation():
    m.record_db_operation("select", 0.01, success=True)
    assert (
        REGISTRY.get_sample_value(
            "db_operation_duration_seconds_count", {"operation": "select"}
        )
        >= 1.0
    )
    m.record_db_operation("insert", 0.02, success=False)
    assert (
        REGISTRY.get_sample_value("db_operation_errors_total", {"operation": "insert"})
        >= 1.0
    )


class MockRequest:
    def __init__(self, path, route_path=None, root_path="root"):
        self.scope = {}
        if route_path:
            mock_route = MagicMock()
            mock_route.path = route_path
            self.scope["route"] = mock_route
        self.scope["path"] = path
        self.scope["root_path"] = root_path
        self.url = MagicMock()
        self.url.path = path
        self.headers = {}
        self.client = MagicMock()
        self.client.host = ""


def test_resolve_path_template():
    req1 = MockRequest(
        path="/api/v1/users/123/profile", route_path="/api/v1/users/{id}/profile"
    )
    assert m._resolve_path_template(req1) == "/api/v1/users/{id}/profile"

    req2 = MockRequest(path="/healthz")
    assert m._resolve_path_template(req2) == "/healthz"


def test_resolve_router_label():
    # 1. With router prefix
    mock_router = MagicMock()
    mock_router.prefix = "users"
    mock_route = MagicMock()
    mock_route.router = mock_router
    req1 = MockRequest(path="/api/v1/users/123")
    req1.scope["route"] = mock_route
    assert m._resolve_router_label(req1) == "users"

    # 2. Without route, root_path defined
    req2 = MockRequest(path="/unknown", root_path="custom_root")
    assert m._resolve_router_label(req2) == "custom_root"


def test_authorization_header():
    req = MockRequest(path="/metrics")
    req.headers["Authorization"] = "Basic dXNlcjpwYXNz"
    assert m._authorization_header(req) == "Basic dXNlcjpwYXNz"


def test_is_authorized():
    with patch("app.core.metrics.settings") as mock_settings:
        mock_settings.metrics_basic_auth_username = "user"
        mock_settings.metrics_basic_auth_password = "pass"  # pragma: allowlist secret

        # Authorized
        req = MockRequest(path="/metrics")
        req.headers["Authorization"] = "Basic dXNlcjpwYXNz"  # base64(user:pass)
        assert m._is_authorized(req) is True

        # Unauthorized
        req2 = MockRequest(path="/metrics")
        req2.headers["Authorization"] = "Basic invalid"
        assert m._is_authorized(req2) is False


def test_is_loopback_value():
    assert m._is_loopback_value("127.0.0.1") is True
    assert m._is_loopback_value("::1") is True
    assert m._is_loopback_value("localhost") is True
    assert m._is_loopback_value("10.0.0.1") is False


def test_allowlist_is_loopback_only():
    with patch("app.core.metrics.settings") as mock_settings:
        mock_settings.metrics_allowlist_entries = ["127.0.0.1", "::1", "localhost"]
        assert m._allowlist_is_loopback_only() is True

        mock_settings.metrics_allowlist_entries = ["127.0.0.1", "10.0.0.1"]
        assert m._allowlist_is_loopback_only() is False


def test_is_allowed():
    with patch("app.core.metrics.settings") as mock_settings:
        # 1. Empty allowlist -> allowed
        mock_settings.metrics_allowlist_entries = []
        req = MockRequest(path="/metrics")
        req.client.host = "10.0.0.5"
        assert m._is_allowed(req) is True

        # 2. Host matching allowlist
        mock_settings.metrics_allowlist_entries = ["127.0.0.1", "10.0.0.0/24"]

        req_local = MockRequest(path="/metrics")
        req_local.client.host = "127.0.0.1"
        assert m._is_allowed(req_local) is True

        req_cidr = MockRequest(path="/metrics")
        req_cidr.client.host = "10.0.0.5"
        assert m._is_allowed(req_cidr) is True

        req_blocked = MockRequest(path="/metrics")
        req_blocked.client.host = "10.0.1.5"
        assert m._is_allowed(req_blocked) is False


def test_metrics_auth_config_is_invalid():
    with patch("app.core.metrics.settings") as mock_settings:
        mock_settings.enable_metrics_endpoint = True

        # Valid config: username & password set
        mock_settings.metrics_basic_auth_username = "user"
        mock_settings.metrics_basic_auth_password = "pass"  # pragma: allowlist secret
        assert m._metrics_auth_config_is_invalid() is False

        # Invalid config: empty credentials, non-loopback allowlist
        mock_settings.metrics_basic_auth_username = ""
        mock_settings.metrics_basic_auth_password = ""
        mock_settings.metrics_allowlist_entries = ["10.0.0.1"]
        assert m._metrics_auth_config_is_invalid() is True

        # Valid config: empty credentials, loopback only allowlist
        mock_settings.metrics_allowlist_entries = ["127.0.0.1"]
        assert m._metrics_auth_config_is_invalid() is False

        # Endpoint disabled -> always valid (returns False)
        mock_settings.enable_metrics_endpoint = False
        assert m._metrics_auth_config_is_invalid() is False


def test_sanitize_metric_name():
    assert obs._sanitize_metric_name("my-metric.name") == "my_metric_name"
    assert obs._sanitize_metric_name("normal_name") == "normal_name"


def test_coerce_deleted_value():
    assert obs._coerce_deleted_value(None) == 0
    assert obs._coerce_deleted_value("10") == 10
    assert obs._coerce_deleted_value(42) == 42
    assert obs._coerce_deleted_value("abc") == 0


def test_build_otel_resource_attributes():
    attributes = obs._build_otel_resource_attributes()
    assert "service.name" in attributes
    assert attributes["service.name"] == "university-ecosystem"


def test_resolve_headers():
    headers_str = "Authorization=Bearer token,X-Request-Id=123"
    resolved = obs._resolve_headers(headers_str)
    assert resolved["Authorization"] == "Bearer token"
    assert resolved["X-Request-Id"] == "123"

    # Empty string
    assert obs._resolve_headers("") == {}


@pytest.mark.anyio
async def test_periodic_task_metrics():
    ptm = obs.get_periodic_task_metrics("test_periodic")
    assert ptm is not None

    async with ptm.track_execution() as run:
        run.observe_deleted(3)
        run.observe_deleted([1, 2, None])

    val_runs = REGISTRY.get_sample_value("periodic_task_test_periodic_runs_total")
    assert val_runs is not None
    assert val_runs >= 1.0

    val_deleted = REGISTRY.get_sample_value("periodic_task_test_periodic_deleted_total")
    assert val_deleted is not None
    assert val_deleted == 6.0


def test_notification_queue_metrics():
    nqm = obs.reinitialize_notification_queue_metrics(registry=REGISTRY)
    assert nqm is not None
    nqm.reset()
    nqm.dead_lettered_jobs.set(1.0)
    val = REGISTRY.get_sample_value("notification_queue_dead_lettered_jobs")
    assert val is not None
    assert val == 1.0


def test_create_worker_metrics():
    wm = obs.create_worker_metrics("test_worker_cli")
    assert wm is not None
    wm.mark_startup()
    assert wm.status == "ok"
    wm.record_success(notifications_created=5)
    assert wm.status == "ok"
    assert wm.last_success is not None
    assert wm.last_run is not None

    wm.record_failure()
    assert wm.status == "degraded"
    assert wm.last_failure is not None


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
@pytest.mark.anyio
async def test_worker_monitoring_app_and_server():
    from fastapi.testclient import TestClient

    wm = obs.create_worker_metrics("test_worker_server")
    app = obs.create_worker_monitoring_app(worker_name="test_worker_server", metrics=wm)

    client = TestClient(app)
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["worker"] == "test_worker_server"

    resp_metrics = client.get("/metrics")
    assert resp_metrics.status_code == 200
    assert b"test_worker_server_last_run_timestamp_seconds" in resp_metrics.content

    # Port validation
    with pytest.raises(ValueError):
        await obs.start_worker_monitoring_server(app, host="127.0.0.1", port=0)

    # Test start and stop server on ephemeral port
    import socket

    s = socket.socket()
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()

    stop_fn = await obs.start_worker_monitoring_server(app, host="127.0.0.1", port=port)
    assert callable(stop_fn)
    await stop_fn()


def test_configure_worker_observability():
    with patch("app.core.observability.settings") as mock_settings:
        mock_settings.enable_otel = False
        mock_settings.log_level = "info"
        mock_settings.environment = "testing"
        obs.configure_worker_observability(worker_name="test_worker_obs")
