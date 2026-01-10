from __future__ import annotations

import asyncio
import base64
import hmac
import importlib.util
import logging
import time
from collections.abc import Iterable
from ipaddress import ip_address, ip_network

import psutil
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.database import engine

try:  # pragma: no cover - optional dependency guard
    from prometheus_client import (  # type: ignore
        CONTENT_TYPE_LATEST,
        REGISTRY,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )
except Exception:  # pragma: no cover - optional dependency guard
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"
    Counter = None  # type: ignore[assignment]
    Gauge = None  # type: ignore[assignment]
    Histogram = None  # type: ignore[assignment]
    REGISTRY = None  # type: ignore[assignment]

    def generate_latest(_: object | None = None) -> bytes:  # type: ignore[misc]
        raise RuntimeError("prometheus-client is required to expose metrics")


_REQUEST_COUNT = (
    Counter(
        "http_requests_total",
        "Total HTTP requests",
        ("method", "path", "status"),
        registry=REGISTRY,
    )
    if Counter is not None
    else None
)

_REQUEST_DURATION = (
    Histogram(
        "http_request_duration_seconds",
        "HTTP request duration in seconds",
        ("method", "path"),
        registry=REGISTRY,
    )
    if Histogram is not None
    else None
)

_ROUTER_DURATION = (
    Histogram(
        "router_request_duration_seconds",
        "HTTP request duration per router",
        ("router", "method", "path"),
        registry=REGISTRY,
    )
    if Histogram is not None
    else None
)

_ROUTER_ERRORS = (
    Counter(
        "router_request_errors_total",
        "HTTP errors per router",
        ("router", "method", "path", "status"),
        registry=REGISTRY,
    )
    if Counter is not None
    else None
)

_HEALTH_CHECK_DURATION = (
    Histogram(
        "healthcheck_duration_seconds",
        "Duration of dependency health probes",
        ("component",),
        registry=REGISTRY,
    )
    if Histogram is not None
    else None
)

_HEALTH_CHECK_STATUS = (
    Counter(
        "healthcheck_status_total",
        "Total dependency health check results",
        ("component", "status"),
        registry=REGISTRY,
    )
    if Counter is not None
    else None
)

_REDIS_COMMAND_DURATION = (
    Histogram(
        "redis_command_duration_seconds",
        "Redis command duration in seconds",
        ("command",),
        registry=REGISTRY,
    )
    if Histogram is not None
    else None
)

_REDIS_COMMAND_ERRORS = (
    Counter(
        "redis_command_errors_total",
        "Total Redis command failures",
        ("command",),
        registry=REGISTRY,
    )
    if Counter is not None
    else None
)

_DB_OPERATION_DURATION = (
    Histogram(
        "db_operation_duration_seconds",
        "Database operation duration in seconds",
        ("operation",),
        registry=REGISTRY,
    )
    if Histogram is not None
    else None
)

_DB_OPERATION_ERRORS = (
    Counter(
        "db_operation_errors_total",
        "Total database operation failures",
        ("operation",),
        registry=REGISTRY,
    )
    if Counter is not None
    else None
)

_CACHE_ENTRIES = (
    Gauge("cache_entries", "Number of cached entries", registry=REGISTRY)
    if Gauge is not None
    else None
)

_CACHE_MEMORY_BYTES = (
    Gauge(
        "cache_memory_bytes",
        "Memory consumption of cache backend",
        registry=REGISTRY,
    )
    if Gauge is not None
    else None
)

_REDIS_HEALTH = (
    Gauge("redis_health", "Redis availability", registry=REGISTRY)
    if Gauge is not None
    else None
)

_DB_HEALTH = (
    Gauge("db_health", "Database availability", registry=REGISTRY)
    if Gauge is not None
    else None
)

# Connection pool metrics
_DB_POOL_SIZE = (
    Gauge("db_pool_size", "Database connection pool size", registry=REGISTRY)
    if Gauge is not None
    else None
)

_DB_POOL_CHECKEDOUT = (
    Gauge(
        "db_pool_checkedout",
        "Number of connections currently checked out from the pool",
        registry=REGISTRY,
    )
    if Gauge is not None
    else None
)

_DB_POOL_OVERFLOW = (
    Gauge(
        "db_pool_overflow",
        "Number of overflow connections beyond pool size",
        registry=REGISTRY,
    )
    if Gauge is not None
    else None
)

_DB_POOL_CHECKEDIN = (
    Gauge(
        "db_pool_checkedin",
        "Number of connections currently available in the pool",
        registry=REGISTRY,
    )
    if Gauge is not None
    else None
)

_CPU_LOAD = (
    Gauge("cpu_load_percent", "CPU load percentage", registry=REGISTRY)
    if Gauge is not None
    else None
)

_GPU_LOAD = (
    Gauge(
        "gpu_load_percent", "GPU load percentage", ("index", "name"), registry=REGISTRY
    )
    if Gauge is not None
    else None
)

# Business metrics for product analytics
_LOGIN_SUCCESS = (
    Counter(
        "auth_login_success_total",
        "Total successful login attempts",
        registry=REGISTRY,
    )
    if Counter is not None
    else None
)

_LOGIN_FAILURE = (
    Counter(
        "auth_login_failure_total",
        "Total failed login attempts",
        ("reason",),
        registry=REGISTRY,
    )
    if Counter is not None
    else None
)

_NOTIFICATIONS_DELIVERED = (
    Counter(
        "notifications_delivered_total",
        "Total notifications successfully delivered",
        ("type",),
        registry=REGISTRY,
    )
    if Counter is not None
    else None
)

_NOTIFICATIONS_FAILED = (
    Counter(
        "notifications_failed_total",
        "Total notifications that failed to deliver",
        ("type", "reason"),
        registry=REGISTRY,
    )
    if Counter is not None
    else None
)

_EVENT_REGISTRATIONS = (
    Counter(
        "event_registrations_total",
        "Total event registrations",
        registry=REGISTRY,
    )
    if Counter is not None
    else None
)

_ACTIVE_USERS = (
    Gauge(
        "active_users_count",
        "Number of currently active users",
        ("period",),
        registry=REGISTRY,
    )
    if Gauge is not None
    else None
)

_MFA_ADOPTION = (
    Gauge(
        "mfa_enabled_users_total",
        "Number of users with MFA enabled",
        registry=REGISTRY,
    )
    if Gauge is not None
    else None
)

_PRESENCE_EVENTS = (
    Counter(
        "websocket_presence_events_total",
        "Total presence events broadcast over websockets",
        ("state", "source"),
        registry=REGISTRY,
    )
    if Counter is not None
    else None
)

_PRESENCE_THROTTLED = (
    Counter(
        "websocket_presence_throttled_total",
        "Total presence events throttled before broadcast",
        ("state", "source"),
        registry=REGISTRY,
    )
    if Counter is not None
    else None
)


def record_login_success() -> None:
    """Record a successful login."""
    if _LOGIN_SUCCESS is not None:
        _LOGIN_SUCCESS.inc()


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


_CONFIGURED_ATTR = "_metrics_configured"
_PLACEHOLDER_PASSWORDS = {"changeme"}
_LOOPBACK_HOSTNAMES = {"localhost"}
logger = logging.getLogger(__name__)


class PrometheusRequestMetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        if _REQUEST_COUNT is None or _REQUEST_DURATION is None:
            return await call_next(request)

        start = time.perf_counter()
        status_code = "500"
        router_label = _resolve_router_label(request)
        path_template = _resolve_path_template(request)
        method = request.method.upper()
        try:
            response = await call_next(request)
            status_code = str(response.status_code)
            return response
        except Exception:
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
    password = settings.metrics_basic_auth_password
    if not username and not password:
        return _allowlist_is_loopback_only()

    if not username or not password:
        return False

    header = _authorization_header(request)
    if not header.startswith("Basic "):
        return False

    encoded = header[6:].strip()
    try:
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
    except Exception:
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
        except Exception:  # pragma: no cover - defensive metrics guard
            logger.debug("Failed to record health check duration", exc_info=True)
    if _HEALTH_CHECK_STATUS is not None:
        try:
            _HEALTH_CHECK_STATUS.labels(component=component, status=status).inc()
        except Exception:  # pragma: no cover - defensive metrics guard
            logger.debug("Failed to record health check status", exc_info=True)


def record_redis_command(
    command: str, elapsed_seconds: float, *, success: bool
) -> None:
    if _REDIS_COMMAND_DURATION is not None:
        try:
            _REDIS_COMMAND_DURATION.labels(command=command).observe(
                max(elapsed_seconds, 0.0)
            )
        except Exception:  # pragma: no cover - defensive metrics guard
            logger.debug("Failed to record redis command duration", exc_info=True)
    if not success and _REDIS_COMMAND_ERRORS is not None:
        try:
            _REDIS_COMMAND_ERRORS.labels(command=command).inc()
        except Exception:  # pragma: no cover - defensive metrics guard
            logger.debug("Failed to record redis command error", exc_info=True)


def record_db_operation(
    operation: str, elapsed_seconds: float, *, success: bool
) -> None:
    if _DB_OPERATION_DURATION is not None:
        try:
            _DB_OPERATION_DURATION.labels(operation=operation).observe(
                max(elapsed_seconds, 0.0)
            )
        except Exception:  # pragma: no cover - defensive metrics guard
            logger.debug("Failed to record db operation duration", exc_info=True)
    if not success and _DB_OPERATION_ERRORS is not None:
        try:
            _DB_OPERATION_ERRORS.labels(operation=operation).inc()
        except Exception:  # pragma: no cover - defensive metrics guard
            logger.debug("Failed to record db operation error", exc_info=True)


async def _record_cache_metrics() -> None:
    if _CACHE_ENTRIES is None and _CACHE_MEMORY_BYTES is None and _REDIS_HEALTH is None:
        return
    from app.deps.cache import RedisCache, get_cache

    backend = get_cache()
    if isinstance(backend, RedisCache):
        try:
            client = await backend._get_client()  # noqa: SLF001 - metrics probe only
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
        except Exception:  # pragma: no cover - defensive metrics guard
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

    except Exception:  # pragma: no cover - defensive metrics guard
        logger.debug("Failed to collect pool metrics", exc_info=True)


async def _record_db_metrics() -> None:
    if _DB_HEALTH is None and _DB_OPERATION_DURATION is None:
        return

    # Record pool metrics first
    _record_pool_metrics()

    start = time.perf_counter()
    success = False
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        success = True
    except Exception:  # pragma: no cover - defensive metrics guard
        success = False
    finally:
        elapsed = max(time.perf_counter() - start, 0.0)
        record_db_operation("healthcheck", elapsed, success=success)
        if _DB_HEALTH is not None:
            _DB_HEALTH.set(1 if success else 0)


def _load_gputil():
    spec = importlib.util.find_spec("GPUtil")
    if spec is None:
        return None
    module = importlib.util.module_from_spec(spec)
    loader = spec.loader
    if loader is None:
        return None
    loader.exec_module(module)  # type: ignore[arg-type]
    return module


def _record_system_metrics() -> None:
    if _CPU_LOAD is not None:
        try:
            _CPU_LOAD.set(float(psutil.cpu_percent(interval=None)))
        except Exception:  # pragma: no cover - defensive metrics guard
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
        except Exception:  # pragma: no cover - defensive metrics guard
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
        response = PlainTextResponse("Unauthorized", status_code=401)
        response.headers["WWW-Authenticate"] = 'Basic realm="Metrics"'
        return response

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
    except Exception:  # pragma: no cover - defensive guard
        return

    try:
        metrics = observability.get_notification_queue_metrics()
    except RuntimeError:  # pragma: no cover - optional dependency guard
        return

    if metrics.registry is REGISTRY:
        return

    fresh = observability.reinitialize_notification_queue_metrics(registry=REGISTRY)

    try:
        from app.services import notification_queue
    except Exception:  # pragma: no cover - defensive guard
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

    if (
        settings.enable_metrics_endpoint
        and settings.metrics_basic_auth_password.strip().lower()
        in _PLACEHOLDER_PASSWORDS
    ):
        logger.warning(
            "Metrics endpoint is enabled but METRICS_BASIC_AUTH_PASSWORD uses a "
            "placeholder value; refusing to expose /metrics until strong "
            "credentials are configured."
        )
        return

    app.add_middleware(PrometheusRequestMetricsMiddleware)
    try:
        from app.core.observability import get_notification_queue_metrics
    except Exception:  # pragma: no cover - defensive guard
        get_notification_queue_metrics = None  # type: ignore[assignment]
    if get_notification_queue_metrics is not None:
        try:
            get_notification_queue_metrics()
        except RuntimeError:  # pragma: no cover - optional dependency guard
            pass
    app.add_api_route(
        "/metrics",
        metrics_endpoint,
        methods=["GET"],
        include_in_schema=False,
        name="metrics",
    )
    setattr(app.state, _CONFIGURED_ATTR, True)
