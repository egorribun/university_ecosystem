from types import SimpleNamespace

from prometheus_client import REGISTRY, CollectorRegistry
from starlette.requests import Request

import app.core.metrics as m
import app.core.observability as obs


def _make_request(
    path: str = "/",
    *,
    route_path: str | None = None,
    router_prefix: str | None = None,
    root_path: str = "",
    client_host: str = "127.0.0.1",
    headers: dict[str, str] | None = None,
) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "root_path": root_path,
        "headers": [
            (name.lower().encode("latin-1"), value.encode("latin-1"))
            for name, value in (headers or {}).items()
        ],
        "client": (client_host, 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    if route_path is not None:
        router = SimpleNamespace(prefix=router_prefix) if router_prefix else None
        scope["route"] = SimpleNamespace(path=route_path, router=router)
    return Request(scope)


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


def test_resolve_path_template():
    assert (
        m._resolve_path_template(
            _make_request(
                "/api/v1/users/123/profile",
                route_path="/api/v1/users/{id}/profile",
            )
        )
        == "/api/v1/users/{id}/profile"
    )
    assert (
        m._resolve_path_template(
            _make_request("/api/v1/news/456", route_path="/api/v1/news/{id}")
        )
        == "/api/v1/news/{id}"
    )
    assert m._resolve_path_template(_make_request("/healthz")) == "/healthz"


def test_resolve_router_label():
    assert (
        m._resolve_router_label(
            _make_request(
                "/api/v1/users/123", route_path="/users/{id}", router_prefix="/users"
            )
        )
        == "/users"
    )
    assert (
        m._resolve_router_label(_make_request("/api/v1/news", root_path="/api/v1"))
        == "/api/v1"
    )
    assert m._resolve_router_label(_make_request("/unknown")) == "root"


def test_authorization_header():
    request = _make_request(headers={"Authorization": "Basic dXNlcjpwYXNz"})
    assert m._authorization_header(request) == "Basic dXNlcjpwYXNz"
    assert m._authorization_header(_make_request()) == ""


def test_is_loopback_value():
    assert m._is_loopback_value("127.0.0.1") is True
    assert m._is_loopback_value("::1") is True
    assert m._is_loopback_value("localhost") is True
    assert m._is_loopback_value("10.0.0.1") is False


def test_allowlist_is_loopback_only(monkeypatch):
    monkeypatch.setattr(m.settings, "metrics_allowlist", "127.0.0.1,::1,localhost")
    assert m._allowlist_is_loopback_only() is True

    monkeypatch.setattr(m.settings, "metrics_allowlist", "127.0.0.1,10.0.0.1")
    assert m._allowlist_is_loopback_only() is False


def test_is_allowed(monkeypatch):
    monkeypatch.setattr(m.settings, "metrics_allowlist", "127.0.0.1")
    assert m._is_allowed(_make_request(client_host="127.0.0.1")) is True
    assert m._is_allowed(_make_request(client_host="10.0.0.1")) is False

    monkeypatch.setattr(m.settings, "metrics_allowlist", "10.0.0.0/24")
    assert m._is_allowed(_make_request(client_host="10.0.0.5")) is True
    assert m._is_allowed(_make_request(client_host="10.0.1.5")) is False


def test_metrics_auth_config_is_invalid(monkeypatch):
    monkeypatch.setattr(m.settings, "enable_metrics_endpoint", True)
    monkeypatch.setattr(m.settings, "metrics_allowlist", "")
    monkeypatch.setattr(m.settings, "metrics_basic_auth_username", "user")
    monkeypatch.setattr(m.settings, "metrics_basic_auth_password", "")
    assert m._metrics_auth_config_is_invalid() is True

    monkeypatch.setattr(m.settings, "metrics_basic_auth_username", "")
    monkeypatch.setattr(m.settings, "metrics_basic_auth_password", "pass")
    assert m._metrics_auth_config_is_invalid() is True

    monkeypatch.setattr(m.settings, "metrics_basic_auth_username", "user")
    monkeypatch.setattr(m.settings, "metrics_basic_auth_password", "pass")
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
    headers = "Authorization=Bearer token,X-Request-Id=123"
    resolved = obs._resolve_headers(headers)
    assert resolved["Authorization"] == "Bearer token"
    assert resolved["X-Request-Id"] == "123"


def test_periodic_task_metrics():
    registry = CollectorRegistry()
    ptm = obs.get_periodic_task_metrics("test_periodic", registry=registry)
    assert ptm is not None
    ptm.runs_total.inc()
    ptm.duration_seconds.observe(1.5)

    val = registry.get_sample_value("periodic_task_test_periodic_runs_total")
    assert val is not None
    assert val >= 1.0
    assert (
        registry.get_sample_value("periodic_task_test_periodic_duration_seconds_count")
        == 1.0
    )


def test_notification_queue_metrics():
    registry = CollectorRegistry()
    nqm = obs.create_notification_queue_metrics(registry=registry)
    assert nqm is not None
    nqm.dead_lettered_jobs.set(1)
    val = registry.get_sample_value("notification_queue_dead_lettered_jobs")
    assert val is not None
    assert val == 1.0
