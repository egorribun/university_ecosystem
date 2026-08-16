from __future__ import annotations

import asyncio
import base64
import hmac
import importlib.util
import time
from ipaddress import ip_address, ip_network
from typing import TYPE_CHECKING, Any, cast

import psutil
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.database import engine
from app.core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Iterable

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        REGISTRY,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )
except Exception:  # pragma: no cover - optional dependency guard  # RZ-22-01-JUSTIFIED: optional dependency — prometheus_client may not be installed (reviewed TD-27-04)
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"
    Counter: Any = None  # type: ignore[no-redef]
    Gauge: Any = None  # type: ignore[no-redef]
    Histogram: Any = None  # type: ignore[no-redef]
    REGISTRY: Any = None  # type: ignore[no-redef]

    def _generate_latest_fallback(registry: Any = None, escaping: str = "") -> bytes:
        raise RuntimeError("prometheus-client is required to expose metrics")

    generate_latest = _generate_latest_fallback


def _get_or_create_metric(
    cls: type, name: str, documentation: str, **kwargs: Any
) -> Any:
    if cls is None:
        return None
    if (
        REGISTRY
        and hasattr(REGISTRY, "_names_to_collectors")
        and name in REGISTRY._names_to_collectors
    ):
        return REGISTRY._names_to_collectors[name]
    try:
        return cls(name, documentation, registry=REGISTRY, **kwargs)
    except ValueError:
        if (
            REGISTRY
            and hasattr(REGISTRY, "_names_to_collectors")
            and name in REGISTRY._names_to_collectors
        ):
            return REGISTRY._names_to_collectors[name]
        raise


_REQUEST_COUNT = _get_or_create_metric(
    Counter,
    "http_requests_total",
    "Total HTTP requests",
    labelnames=("method", "path", "status"),
)

_REQUEST_DURATION = _get_or_create_metric(
    Histogram,
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    labelnames=("method", "path"),
)

_ROUTER_DURATION = _get_or_create_metric(
    Histogram,
    "router_request_duration_seconds",
    "HTTP request duration per router",
    labelnames=("router", "method", "path"),
)

_ROUTER_ERRORS = _get_or_create_metric(
    Counter,
    "router_request_errors_total",
    "HTTP errors per router",
    labelnames=("router", "method", "path", "status"),
)

_HEALTH_CHECK_DURATION = _get_or_create_metric(
    Histogram,
    "healthcheck_duration_seconds",
    "Duration of dependency health probes",
    labelnames=("component",),
)

_HEALTH_CHECK_STATUS = _get_or_create_metric(
    Counter,
    "healthcheck_status_total",
    "Total dependency health check results",
    labelnames=("component", "status"),
)

_REDIS_COMMAND_DURATION = _get_or_create_metric(
    Histogram,
    "redis_command_duration_seconds",
    "Redis command duration in seconds",
    labelnames=("command",),
)

_REDIS_COMMAND_ERRORS = _get_or_create_metric(
    Counter,
    "redis_command_errors_total",
    "Total Redis command failures",
    labelnames=("command",),
)

_DB_OPERATION_DURATION = _get_or_create_metric(
    Histogram,
    "db_operation_duration_seconds",
    "Database operation duration in seconds",
    labelnames=("operation",),
)

_DB_OPERATION_ERRORS = _get_or_create_metric(
    Counter,
    "db_operation_errors_total",
    "Total database operation failures",
    labelnames=("operation",),
)

_CACHE_ENTRIES = _get_or_create_metric(
    Gauge,
    "cache_entries",
    "Number of cached entries",
)

_CACHE_MEMORY_BYTES = _get_or_create_metric(
    Gauge,
    "cache_memory_bytes",
    "Memory consumption of cache backend",
)

_REDIS_HEALTH = _get_or_create_metric(
    Gauge,
    "redis_health",
    "Redis availability",
)

_CACHE_HITS = _get_or_create_metric(
    Counter,
    "cache_hits_total",
    "Total cache hits",
    labelnames=("backend",),
)

_CACHE_MISSES = _get_or_create_metric(
    Counter,
    "cache_misses_total",
    "Total cache misses",
    labelnames=("backend",),
)

_DB_HEALTH = _get_or_create_metric(
    Gauge,
    "db_health",
    "Database availability",
)

# Connection pool metrics
_DB_POOL_SIZE = _get_or_create_metric(
    Gauge,
    "db_pool_size",
    "Database connection pool size",
)

_DB_POOL_CHECKEDOUT = _get_or_create_metric(
    Gauge,
    "db_pool_checkedout",
    "Number of connections currently checked out from the pool",
)

_DB_POOL_OVERFLOW = _get_or_create_metric(
    Gauge,
    "db_pool_overflow",
    "Number of overflow connections beyond pool size",
)

_DB_POOL_CHECKEDIN = _get_or_create_metric(
    Gauge,
    "db_pool_checkedin",
    "Number of connections currently available in the pool",
)

_CPU_LOAD = _get_or_create_metric(
    Gauge,
    "cpu_load_percent",
    "CPU load percentage",
)

# NATS JetStream & CDC Observability Metrics


CDC_WAL_REPLICATION_LAG_BYTES = _get_or_create_metric(
    Gauge,
    "cdc_wal_replication_lag_bytes",
    "PostgreSQL CDC WAL replication lag in bytes",
    labelnames=["slot_name"],
)

PG_CDC_REPLICATION_LAG_BYTES = _get_or_create_metric(
    Gauge,
    "pg_cdc_replication_lag_bytes",
    "PostgreSQL CDC replication LSN lag in bytes",
    labelnames=["slot_name"],
)

PG_CDC_REPLICATION_LAG_SECONDS = _get_or_create_metric(
    Gauge,
    "pg_cdc_replication_lag_seconds",
    "PostgreSQL CDC replication lag in seconds",
    labelnames=["slot_name"],
)

OUTBOX_CDC_DISPATCH_DURATION = _get_or_create_metric(
    Histogram,
    "outbox_cdc_dispatch_duration_seconds",
    "End-to-end CDC dispatch latency from WAL parse to NATS PubAck",
    labelnames=["event_type"],
    buckets=(0.001, 0.002, 0.005, 0.010, 0.025, 0.050, 0.100, 0.500, 1.0),
)

OUTBOX_CDC_EVENTS_DISPATCHED = _get_or_create_metric(
    Counter,
    "outbox_cdc_events_dispatched_total",
    "Total CDC outbox events dispatched to NATS JetStream",
    labelnames=["event_type", "status"],
)

NATS_JETSTREAM_CONSUMER_LAG = _get_or_create_metric(
    Gauge,
    "nats_jetstream_consumer_lag",
    "NATS JetStream consumer unacknowledged message lag",
    labelnames=["stream", "consumer"],
)

JETSTREAM_CONSUMER_LAG = _get_or_create_metric(
    Gauge,
    "jetstream_consumer_lag_messages",
    "NATS JetStream consumer lag in messages",
    labelnames=["stream", "consumer"],
)

NATS_JETSTREAM_ACKS_TOTAL = _get_or_create_metric(
    Counter,
    "nats_jetstream_acks_total",
    "Total NATS JetStream message ACKs",
    labelnames=["stream", "consumer"],
)

JETSTREAM_MESSAGES_ACKED = _get_or_create_metric(
    Counter,
    "jetstream_messages_acked_total",
    "Total NATS JetStream messages ACKed",
    labelnames=["stream", "consumer"],
)

NATS_JETSTREAM_NAKS_TOTAL = _get_or_create_metric(
    Counter,
    "nats_jetstream_naks_total",
    "Total NATS JetStream message NAKs",
    labelnames=["stream", "consumer"],
)

JETSTREAM_MESSAGES_NACKED = _get_or_create_metric(
    Counter,
    "jetstream_messages_nacked_total",
    "Total NATS JetStream messages NACKed",
    labelnames=["stream", "consumer"],
)

_GPU_LOAD = _get_or_create_metric(
    Gauge,
    "gpu_load_percent",
    "GPU load percentage",
    labelnames=("index", "name"),
)

# Business metrics for product analytics
_LOGIN_SUCCESS = _get_or_create_metric(
    Counter,
    "auth_login_success_total",
    "Total successful login attempts",
    labelnames=("method",),
)

_LOGIN_FAILURE = _get_or_create_metric(
    Counter,
    "auth_login_failure_total",
    "Total failed login attempts",
    labelnames=("reason",),
)

_NOTIFICATIONS_DELIVERED = _get_or_create_metric(
    Counter,
    "notifications_delivered_total",
    "Total notifications successfully delivered",
    labelnames=("type",),
)

_NOTIFICATIONS_FAILED = _get_or_create_metric(
    Counter,
    "notifications_failed_total",
    "Total notifications that failed to deliver",
    labelnames=("type", "reason"),
)

_EVENT_REGISTRATIONS = _get_or_create_metric(
    Counter,
    "event_registrations_total",
    "Total event registrations",
)

_ACTIVE_USERS = _get_or_create_metric(
    Gauge,
    "active_users_count",
    "Number of currently active users",
    labelnames=("period",),
)

_MFA_ADOPTION = _get_or_create_metric(
    Gauge,
    "mfa_enabled_users_total",
    "Number of users with MFA enabled",
)

_PRESENCE_EVENTS = _get_or_create_metric(
    Counter,
    "websocket_presence_events_total",
    "Total presence events broadcast over websockets",
    labelnames=("state", "source"),
)

_PRESENCE_THROTTLED = _get_or_create_metric(
    Counter,
    "websocket_presence_throttled_total",
    "Total presence events throttled before broadcast",
    labelnames=("state", "source"),
)

_CSP_REPORTS = _get_or_create_metric(
    Counter,
    "csp_reports_total",
    "Total CSP violation reports received",
    labelnames=("outcome",),
)

_CHAT_MESSAGES_TOTAL = _get_or_create_metric(
    Counter,
    "chat_messages_total",
    "Total chat messages processed",
    labelnames=("channel",),
)

_WS_CONNECTIONS_ACTIVE = _get_or_create_metric(
    Gauge,
    "websocket_connections_active",
    "Number of currently active websocket connections",
    labelnames=("path",),
)

# Circuit breaker metrics
_CIRCUIT_BREAKER_STATE = _get_or_create_metric(
    Gauge,
    "circuit_breaker_state",
    "Current circuit breaker state (0=closed, 1=open, 2=half_open)",
    labelnames=("service",),
)

_CIRCUIT_BREAKER_TRIPS = _get_or_create_metric(
    Counter,
    "circuit_breaker_trips_total",
    "Total circuit breaker trips (transitions to open state)",
    labelnames=("service",),
)

# MOD-W10-08: Counter for background task failures.
# Alert when rate(background_task_errors_total[5m]) > 0.
_BACKGROUND_TASK_ERRORS = _get_or_create_metric(
    Counter,
    "background_task_errors_total",
    "Total background task failures by task class name",
    labelnames=("task_name",),
)

# ── Revocation & ABAC Metrics ──────────────────────────────────────────────
_SPICEDB_WATCH_EVENTS = _get_or_create_metric(
    Counter,
    "spicedb_watch_events_total",
    "Total SpiceDB Watch stream relationship events received",
    labelnames=("event_type",),
)

_WS_HUB_SESSIONS_REVOKED = _get_or_create_metric(
    Counter,
    "ws_hub_sessions_revoked_total",
    "Total WebSocket hub user sessions revoked due to permission updates",
    labelnames=("reason",),
)

_ABAC_ACCESS_DENIED = _get_or_create_metric(
    Counter,
    "abac_access_denied_total",
    "Total ABAC access denials by policy rule",
    labelnames=("rule",),
)


def record_background_task_error(task_name: str) -> None:
    """Increment the background task error counter.

    MOD-W10-08: Call this in every background task's bare-except handler so
    failures are visible in Grafana / alerting even when the task swallows the
    exception silently.  Alert rule: rate(background_task_errors_total[5m]) > 0.
    """
    if _BACKGROUND_TASK_ERRORS is not None:
        _BACKGROUND_TASK_ERRORS.labels(task_name=task_name).inc()


def record_login_success(method: str = "password") -> None:
    """Record a successful login."""
    if _LOGIN_SUCCESS is not None:
        _LOGIN_SUCCESS.labels(method=method).inc()


def record_login_failure(reason: str = "invalid_credentials") -> None:
    """Record a failed login attempt."""
    if _LOGIN_FAILURE is not None:
        _LOGIN_FAILURE.labels(reason=reason).inc()


def record_notification_delivered(notification_type: str) -> None:
    """Record a successfully delivered notification."""
    if _NOTIFICATIONS_DELIVERED is not None:
        _NOTIFICATIONS_DELIVERED.labels(type=notification_type).inc()


def record_notification_failed(notification_type: str, reason: str) -> None:
    """Record a failed notification delivery."""
    if _NOTIFICATIONS_FAILED is not None:
        _NOTIFICATIONS_FAILED.labels(type=notification_type, reason=reason).inc()


def record_event_registration() -> None:
    """Record an event registration."""
    if _EVENT_REGISTRATIONS is not None:
        _EVENT_REGISTRATIONS.inc()


def set_active_users(count: int, period: str = "daily") -> None:
    """Set the active users count for a period."""
    if _ACTIVE_USERS is not None:
        _ACTIVE_USERS.labels(period=period).set(float(count))


def set_mfa_adoption(count: int) -> None:
    """Set the MFA adoption count."""
    if _MFA_ADOPTION is not None:
        _MFA_ADOPTION.set(float(count))


def record_presence_event(state: str, source: str) -> None:
    """Record a presence broadcast event."""
    if _PRESENCE_EVENTS is not None:
        _PRESENCE_EVENTS.labels(state=state, source=source).inc()


def record_presence_throttled(state: str, source: str) -> None:
    """Record a throttled presence event."""
    if _PRESENCE_THROTTLED is not None:
        _PRESENCE_THROTTLED.labels(state=state, source=source).inc()


def record_csp_report(outcome: str) -> None:
    """Record a CSP report processing outcome."""
    if _CSP_REPORTS is not None:
        _CSP_REPORTS.labels(outcome=outcome).inc()


def record_chat_message(channel: str) -> None:
    """Record a chat message event."""
    if _CHAT_MESSAGES_TOTAL is not None:
        _CHAT_MESSAGES_TOTAL.labels(channel=channel).inc()


def set_ws_connections_active(path: str, count: int) -> None:
    """Set the active websocket connections count for a path."""
    if _WS_CONNECTIONS_ACTIVE is not None:
        _WS_CONNECTIONS_ACTIVE.labels(path=path).set(float(count))


def inc_ws_connections(path: str) -> None:
    """Increment the active websocket connections count for a path."""
    if _WS_CONNECTIONS_ACTIVE is not None:
        _WS_CONNECTIONS_ACTIVE.labels(path=path).inc()


def dec_ws_connections(path: str) -> None:
    """Decrement the active websocket connections count for a path."""
    if _WS_CONNECTIONS_ACTIVE is not None:
        _WS_CONNECTIONS_ACTIVE.labels(path=path).dec()


def record_cache_hit(backend: str = "redis") -> None:
    """Record a cache hit."""
    if _CACHE_HITS is not None:
        _CACHE_HITS.labels(backend=backend).inc()


def record_cache_miss(backend: str = "redis") -> None:
    """Record a cache miss."""
    if _CACHE_MISSES is not None:
        _CACHE_MISSES.labels(backend=backend).inc()


def record_circuit_breaker_state(service: str, state: str) -> None:
    """Record circuit breaker state change.

    Args:
        service: Name of the protected service.
        state: Current state (closed, open, half_open).
    """
    if _CIRCUIT_BREAKER_STATE is not None:
        state_value = {"closed": 0, "open": 1, "half_open": 2}.get(state, -1)
        _CIRCUIT_BREAKER_STATE.labels(service=service).set(float(state_value))


def record_circuit_breaker_trip(service: str) -> None:
    """Record a circuit breaker trip (transition to open state)."""
    if _CIRCUIT_BREAKER_TRIPS is not None:
        _CIRCUIT_BREAKER_TRIPS.labels(service=service).inc()


def record_spicedb_watch_event(event_type: str = "update") -> None:
    """Record a SpiceDB watch stream event."""
    if _SPICEDB_WATCH_EVENTS is not None:
        try:
            _SPICEDB_WATCH_EVENTS.labels(event_type=event_type).inc()
        except Exception:  # RZ-22-01-JUSTIFIED: metrics guard
            logger.debug("Failed to record SpiceDB watch event", exc_info=True)


def record_ws_hub_session_revoked(reason: str = "access_revoked") -> None:
    """Record a WebSocket hub session revocation event."""
    if _WS_HUB_SESSIONS_REVOKED is not None:
        try:
            _WS_HUB_SESSIONS_REVOKED.labels(reason=reason).inc()
        except Exception:  # RZ-22-01-JUSTIFIED: metrics guard
            logger.debug("Failed to record ws_hub session revoked", exc_info=True)


def record_abac_access_denied(rule: str = "unknown") -> None:
    """Record an ABAC access denial event by rule (e.g. 'subnet', 'schedule')."""
    if _ABAC_ACCESS_DENIED is not None:
        try:
            _ABAC_ACCESS_DENIED.labels(rule=rule).inc()
        except Exception:  # RZ-22-01-JUSTIFIED: metrics guard
            logger.debug("Failed to record ABAC access denied", exc_info=True)


_CONFIGURED_ATTR = "_metrics_configured"
# CFG-1 (audit 2026-03): Expanded placeholder password set.  The previous
# set only contained "changeme".  Common weak/placeholder values are now
# rejected at startup so operators can't accidentally expose metrics with
# trivially-guessable credentials.
_PLACEHOLDER_PASSWORDS: frozenset[str] = frozenset(
    {
        "changeme",
        "change_me",
        "change-me",
        "password",
        "password123",
        "admin",
        "admin123",
        "metrics",
        "prometheus",
        "secret",
        "test",
        "1234",
        "12345",
        "123456",
        "qwerty",
        "letmein",
        "welcome",
        "placeholder",
        "example",
        "default",
        "",
    }
)
_LOOPBACK_HOSTNAMES = {"localhost"}
logger = get_logger(__name__)

# RZ-33-28: Prime psutil CPU measurement so the first real call to
# cpu_percent(interval=None) returns a non-zero value (needs a prior baseline).
psutil.cpu_percent(interval=None)


class PrometheusRequestMetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Any) -> Response:
        if _REQUEST_COUNT is None or _REQUEST_DURATION is None:
            return cast(Response, await call_next(request))

        start = time.perf_counter()
        status_code = "500"
        router_label = _resolve_router_label(request)
        path_template = _resolve_path_template(request)
        method = request.method.upper()
        try:
            response = await call_next(request)
            status_code = str(response.status_code)
            return cast(Response, response)
        except Exception:  # RZ-22-01-JUSTIFIED: re-raise-after-cleanup — ensures metrics are recorded in finally block (reviewed TD-27-04)
            raise
        finally:
            _REQUEST_COUNT.labels(
                method=method, path=path_template, status=status_code
            ).inc()
            elapsed = max(time.perf_counter() - start, 0.0)
            _REQUEST_DURATION.labels(method=method, path=path_template).observe(elapsed)
            if _ROUTER_DURATION is not None:
                _ROUTER_DURATION.labels(
                    router=router_label, method=method, path=path_template
                ).observe(elapsed)
            if _ROUTER_ERRORS is not None and status_code.startswith("5"):
                _ROUTER_ERRORS.labels(
                    router=router_label,
                    method=method,
                    path=path_template,
                    status=status_code,
                ).inc()


def _resolve_path_template(request: Request) -> str:
    route = request.scope.get("route")
    if route is not None:
        path = getattr(route, "path", None)
        if path:
            return str(path)
    raw_path = request.scope.get("path") or request.url.path
    return str(raw_path) if raw_path else "unknown"


def _resolve_router_label(request: Request) -> str:
    route = request.scope.get("route")
    if route is not None:
        for attr in ("router", "owner"):
            router = getattr(route, attr, None)
            if router is not None:
                prefix = getattr(router, "prefix", None)
                if prefix:
                    return str(prefix)
    return request.scope.get("root_path") or "root"


def _authorization_header(request: Request) -> str:
    return request.headers.get("Authorization", "")


def _is_authorized(request: Request) -> bool:
    username = settings.metrics_basic_auth_username.strip()
    password = settings.metrics_basic_auth_password.strip()
    if not username and not password:
        # LOW-W19: Intentional behaviour — when no credentials are configured,
        # access is granted only when the entire allowlist consists of loopback
        # addresses (127.0.0.1, ::1, localhost). This is safe for internal
        # scraping scenarios (e.g. prometheus running on the same host) but is
        # correctly rejected by _metrics_auth_config_is_invalid() for any
        # non-loopback allowlist entry, so no further credential check is needed.
        return _allowlist_is_loopback_only()

    if not username or not password:
        return False

    header = _authorization_header(request)
    if not header.startswith("Basic "):
        return False

    encoded = header[6:].strip()
    try:
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
    except Exception:  # RZ-22-01-JUSTIFIED: fail-closed auth — invalid base64 returns False (reviewed TD-27-04)
        return False
    provided_username, _, provided_password = decoded.partition(":")
    if not _:
        return False
    return hmac.compare_digest(provided_username, username) and hmac.compare_digest(
        provided_password, password
    )


def _iter_allowlist() -> Iterable[str]:
    for raw in settings.metrics_allowlist_entries:
        value = raw.strip()
        if value:
            yield value


def _is_loopback_value(value: str) -> bool:
    try:
        network = ip_network(value, strict=False)
    except ValueError:
        try:
            address = ip_address(value)
        except ValueError:
            return value.lower() in _LOOPBACK_HOSTNAMES
        return address.is_loopback
    return network.is_loopback


def _allowlist_is_loopback_only() -> bool:
    values = list(_iter_allowlist())
    if not values:
        return False
    return all(_is_loopback_value(value) for value in values)


def _is_allowed(request: Request) -> bool:
    allowlist = list(_iter_allowlist())
    if not allowlist:
        return True
    client = request.client
    if client is None or not client.host:
        return False
    host = client.host
    try:
        ip = ip_address(host)
    except ValueError:
        ip = None
    for value in allowlist:
        try:
            network = ip_network(value, strict=False)
        except ValueError:
            if host.lower() == value.lower():
                return True
        else:
            if ip is not None and ip in network:
                return True
    return False


def _metrics_auth_config_is_invalid() -> bool:
    if not settings.enable_metrics_endpoint:
        return False

    username = settings.metrics_basic_auth_username.strip()
    password = settings.metrics_basic_auth_password.strip()
    if username and password:
        return False

    return not _allowlist_is_loopback_only()


def record_health_probe(component: str, status: str, elapsed_seconds: float) -> None:
    if _HEALTH_CHECK_DURATION is not None:
        try:
            _HEALTH_CHECK_DURATION.labels(component=component).observe(
                max(elapsed_seconds, 0.0)
            )
        except Exception:  # pragma: no cover - defensive metrics guard  # RZ-22-01-JUSTIFIED: metrics guard  # RZ-22-01-JUSTIFIED: metrics guard (reviewed TD-27-04)
            logger.debug("Failed to record health check duration", exc_info=True)
    if _HEALTH_CHECK_STATUS is not None:
        try:
            _HEALTH_CHECK_STATUS.labels(component=component, status=status).inc()
        except Exception:  # pragma: no cover - defensive metrics guard  # RZ-22-01-JUSTIFIED: metrics guard  # RZ-22-01-JUSTIFIED: metrics guard (reviewed TD-27-04)
            logger.debug("Failed to record health check status", exc_info=True)


def record_redis_command(
    command: str, elapsed_seconds: float, *, success: bool
) -> None:
    if _REDIS_COMMAND_DURATION is not None:
        try:
            _REDIS_COMMAND_DURATION.labels(command=command).observe(
                max(elapsed_seconds, 0.0)
            )
        except Exception:  # pragma: no cover - defensive metrics guard  # RZ-22-01-JUSTIFIED: metrics guard  # RZ-22-01-JUSTIFIED: metrics guard (reviewed TD-27-04)
            logger.debug("Failed to record redis command duration", exc_info=True)
    if not success and _REDIS_COMMAND_ERRORS is not None:
        try:
            _REDIS_COMMAND_ERRORS.labels(command=command).inc()
        except Exception:  # pragma: no cover - defensive metrics guard  # RZ-22-01-JUSTIFIED: metrics guard  # RZ-22-01-JUSTIFIED: metrics guard (reviewed TD-27-04)
            logger.debug("Failed to record redis command error", exc_info=True)


def record_db_operation(
    operation: str, elapsed_seconds: float, *, success: bool
) -> None:
    if _DB_OPERATION_DURATION is not None:
        try:
            _DB_OPERATION_DURATION.labels(operation=operation).observe(
                max(elapsed_seconds, 0.0)
            )
        except Exception:  # pragma: no cover - defensive metrics guard  # RZ-22-01-JUSTIFIED: metrics guard  # RZ-22-01-JUSTIFIED: metrics guard (reviewed TD-27-04)
            logger.debug("Failed to record db operation duration", exc_info=True)
    if not success and _DB_OPERATION_ERRORS is not None:
        try:
            _DB_OPERATION_ERRORS.labels(operation=operation).inc()
        except Exception:  # pragma: no cover - defensive metrics guard  # RZ-22-01-JUSTIFIED: metrics guard  # RZ-22-01-JUSTIFIED: metrics guard (reviewed TD-27-04)
            logger.debug("Failed to record db operation error", exc_info=True)


async def _record_cache_metrics() -> None:
    checks = [
        _CACHE_ENTRIES is None,
        _CACHE_MEMORY_BYTES is None,
        _REDIS_HEALTH is None,
    ]
    if all(checks):
        return
    from app.deps.cache import RedisCache, get_cache

    backend = get_cache()
    if isinstance(backend, RedisCache):
        try:
            client: Any = await backend._get_client()
            start = time.perf_counter()
            pong = await client.ping()
            latency = max(time.perf_counter() - start, 0.0)
            record_redis_command("ping", latency, success=bool(pong))
            info = await client.info(section="memory")
            size = await client.dbsize()
            if _CACHE_ENTRIES is not None:
                _CACHE_ENTRIES.set(float(size))
            if _CACHE_MEMORY_BYTES is not None:
                used_memory = (
                    info.get("used_memory") if isinstance(info, dict) else None
                )
                if isinstance(used_memory, int | float):
                    _CACHE_MEMORY_BYTES.set(float(used_memory))
            if _REDIS_HEALTH is not None:
                _REDIS_HEALTH.set(1)
        except Exception:  # pragma: no cover - defensive metrics guard  # RZ-22-01-JUSTIFIED: metrics guard  # RZ-22-01-JUSTIFIED: metrics guard (reviewed TD-27-04)
            if _REDIS_HEALTH is not None:
                _REDIS_HEALTH.set(0)
            record_redis_command("ping", 0.0, success=False)
    else:
        if _CACHE_ENTRIES is not None:
            _CACHE_ENTRIES.set(0)
        if _CACHE_MEMORY_BYTES is not None:
            _CACHE_MEMORY_BYTES.set(0)
        if _REDIS_HEALTH is not None:
            _REDIS_HEALTH.set(0)


def _record_pool_metrics() -> None:
    """Record connection pool statistics."""
    try:
        # Access the underlying sync pool from the async engine
        sync_engine = engine.sync_engine
        pool = sync_engine.pool

        # Get pool status if available (QueuePool has these methods)
        if hasattr(pool, "size"):
            pool_size = pool.size()
            if _DB_POOL_SIZE is not None:
                _DB_POOL_SIZE.set(float(pool_size))

        if hasattr(pool, "checkedout"):
            checked_out = pool.checkedout()
            if _DB_POOL_CHECKEDOUT is not None:
                _DB_POOL_CHECKEDOUT.set(float(checked_out))

        if hasattr(pool, "overflow"):
            overflow = pool.overflow()
            if _DB_POOL_OVERFLOW is not None:
                _DB_POOL_OVERFLOW.set(float(overflow))

        if hasattr(pool, "checkedin"):
            checked_in = pool.checkedin()
            if _DB_POOL_CHECKEDIN is not None:
                _DB_POOL_CHECKEDIN.set(float(checked_in))

    except Exception:  # pragma: no cover - defensive metrics guard  # RZ-22-01-JUSTIFIED: metrics guard (reviewed TD-27-04)
        logger.debug("Failed to collect pool metrics", exc_info=True)


async def _record_db_metrics() -> None:
    db_checks = [_DB_HEALTH is None, _DB_OPERATION_DURATION is None]
    if all(db_checks):
        return

    # Record pool metrics first
    _record_pool_metrics()

    start = time.perf_counter()
    success = False
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        success = True
    except Exception:  # pragma: no cover - defensive metrics guard  # RZ-22-01-JUSTIFIED: metrics guard (reviewed TD-27-04)
        success = False
    finally:
        elapsed = max(time.perf_counter() - start, 0.0)
        record_db_operation("healthcheck", elapsed, success=success)
        if _DB_HEALTH is not None:
            _DB_HEALTH.set(1 if success else 0)


def _load_gputil() -> Any:
    spec = importlib.util.find_spec("GPUtil")
    if spec is None:
        return None
    module = importlib.util.module_from_spec(spec)
    loader = spec.loader
    if loader is None:
        return None
    loader.exec_module(module)
    return module


def _record_system_metrics() -> None:
    if _CPU_LOAD is not None:
        try:
            # Non-blocking: uses delta from the previous call (primed at
            # module load time so the first scrape already has a baseline).
            _CPU_LOAD.set(float(psutil.cpu_percent(interval=None)))
        except Exception:  # pragma: no cover - defensive metrics guard  # RZ-22-01-JUSTIFIED: metrics guard  # RZ-22-01-JUSTIFIED: metrics guard (reviewed TD-27-04)
            logger.debug("Failed to collect CPU metrics", exc_info=True)
    if _GPU_LOAD is not None:
        try:
            module = _load_gputil()
            if module is None:
                _GPU_LOAD.clear()
                return
            gpus = module.getGPUs()
            _GPU_LOAD.clear()
            for gpu in gpus:
                _GPU_LOAD.labels(index=str(gpu.id), name=str(gpu.name)).set(
                    float(getattr(gpu, "load", 0.0)) * 100.0
                )
        except Exception:  # pragma: no cover - defensive metrics guard  # RZ-22-01-JUSTIFIED: metrics guard  # RZ-22-01-JUSTIFIED: metrics guard (reviewed TD-27-04)
            logger.debug("Failed to collect GPU metrics", exc_info=True)


async def refresh_runtime_metrics() -> None:
    await asyncio.gather(_record_cache_metrics(), _record_db_metrics())
    _record_system_metrics()


async def metrics_endpoint(request: Request) -> Response:
    if not settings.enable_metrics_endpoint:
        return PlainTextResponse("Not Found", status_code=404)

    _ensure_notification_queue_metrics_registry()

    if _metrics_auth_config_is_invalid():
        return PlainTextResponse("Metrics misconfigured", status_code=503)

    if not _is_authorized(request):
        auth_response = PlainTextResponse("Unauthorized", status_code=401)
        auth_response.headers["WWW-Authenticate"] = 'Basic realm="Metrics"'
        return auth_response

    if not _is_allowed(request):
        return PlainTextResponse("Forbidden", status_code=403)

    if REGISTRY is None:
        raise RuntimeError("prometheus-client is required to expose metrics")

    await refresh_runtime_metrics()

    payload = generate_latest(REGISTRY)
    response = Response(content=payload, media_type=CONTENT_TYPE_LATEST)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return response


def _ensure_notification_queue_metrics_registry() -> None:
    """Ensure notification queue metrics are registered on the default registry."""

    if REGISTRY is None:
        return

    try:
        from app.core import observability
    except Exception:  # pragma: no cover - defensive guard  # RZ-22-01-JUSTIFIED: metrics guard (reviewed TD-27-04)
        return

    try:
        metrics: Any = observability.get_notification_queue_metrics()
    except RuntimeError:
        return

    if metrics.registry is REGISTRY:
        return

    fresh: Any = observability.reinitialize_notification_queue_metrics(
        registry=REGISTRY
    )

    try:
        from app.services import notification_queue
    except Exception:  # pragma: no cover - defensive guard  # RZ-22-01-JUSTIFIED: metrics guard (reviewed TD-27-04)
        return

    notification_queue._queue_metrics = fresh


def configure_metrics(app: FastAPI) -> None:
    if getattr(app.state, _CONFIGURED_ATTR, False):
        return

    if _metrics_auth_config_is_invalid():
        raise RuntimeError(
            "ENABLE_METRICS_ENDPOINT=true requires credentials unless the allowlist is"
            " restricted to loopback addresses"
        )

    # CFG-1 (audit 2026-03): Check BOTH username and password for placeholder
    # values.  The original code only checked the password.  Also check that
    # credentials aren't identical (admin:admin, metrics:metrics, etc.).
    if settings.enable_metrics_endpoint:
        pw = settings.metrics_basic_auth_password.strip().lower()
        un = settings.metrics_basic_auth_username.strip().lower()
        if pw in _PLACEHOLDER_PASSWORDS or un in _PLACEHOLDER_PASSWORDS:
            # LOW-W19: Log at WARNING (not just silent return) so operators can
            # see in application logs that the /metrics endpoint has been
            # DISABLED due to weak/placeholder credentials.
            logger.warning(
                "Metrics endpoint is DISABLED: METRICS_BASIC_AUTH credentials "
                "use a placeholder value — configure strong credentials via "
                "METRICS_BASIC_AUTH_USERNAME / METRICS_BASIC_AUTH_PASSWORD to "
                "re-enable the /metrics endpoint."
            )
            return
        if un and pw and un == pw:
            # LOW-W19: Same as above — warn explicitly that the endpoint is
            # disabled so operators are not surprised by 404/503 responses.
            logger.warning(
                "Metrics endpoint is DISABLED: METRICS_BASIC_AUTH_USERNAME "
                "equals METRICS_BASIC_AUTH_PASSWORD — configure distinct "
                "credentials to re-enable the /metrics endpoint."
            )
            return

    # MOD-23-05 (audit 2026-03-25 Wave 23): OTEL Metrics bridge.
    # Initializes OpenTelemetry MeterProvider with PrometheusMetricReader so that
    # new metrics written via the OTEL API are automatically exposed on the same
    # /metrics endpoint alongside existing prometheus_client metrics. This enables
    # incremental migration: legacy metrics stay untouched, new code uses OTEL API.
    try:
        from opentelemetry.exporter.prometheus import PrometheusMetricReader
        from opentelemetry.metrics import set_meter_provider
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.resources import Resource

        _otel_resource = Resource.create({"service.name": "university-backend"})
        _otel_reader = PrometheusMetricReader()
        _otel_provider = MeterProvider(
            resource=_otel_resource, metric_readers=[_otel_reader]
        )
        set_meter_provider(_otel_provider)
        logger.info(
            "OTEL Metrics bridge initialized — new metrics use OTEL API, exposed via /metrics"
        )
    except ImportError:
        logger.debug(
            "opentelemetry-exporter-prometheus not installed — OTEL metrics bridge skipped"
        )
    except Exception:  # RZ-22-01-JUSTIFIED: metrics guard — OTEL init must not crash the app (reviewed TD-27-04)
        logger.warning(
            "OTEL Metrics bridge initialization failed — falling back to prometheus_client only",
            exc_info=True,
        )

    app.add_middleware(PrometheusRequestMetricsMiddleware)
    try:
        from app.core.observability import get_notification_queue_metrics
    except Exception:  # pragma: no cover - defensive guard  # RZ-22-01-JUSTIFIED: metrics guard (reviewed TD-27-04)
        get_notification_queue_metrics = None  # type: ignore[assignment]
    if get_notification_queue_metrics is not None:
        try:
            get_notification_queue_metrics()
        except RuntimeError:
            pass
    app.add_api_route(
        "/metrics",
        metrics_endpoint,
        methods=["GET"],
        include_in_schema=False,
        name="metrics",
    )
    setattr(app.state, _CONFIGURED_ATTR, True)
