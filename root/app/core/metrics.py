from __future__ import annotations

import base64
import hmac
import logging
import time
from collections.abc import Iterable
from ipaddress import ip_address, ip_network

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings

try:  # pragma: no cover - optional dependency guard
    from prometheus_client import (  # type: ignore
        CONTENT_TYPE_LATEST,
        REGISTRY,
        Counter,
        Histogram,
        generate_latest,
    )
except Exception:  # pragma: no cover - optional dependency guard
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"
    Counter = None  # type: ignore[assignment]
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

_CONFIGURED_ATTR = "_metrics_configured"
_PLACEHOLDER_PASSWORDS = {"changeme"}
logger = logging.getLogger(__name__)


class PrometheusRequestMetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        if _REQUEST_COUNT is None or _REQUEST_DURATION is None:
            return await call_next(request)

        start = time.perf_counter()
        status_code = "500"
        try:
            response = await call_next(request)
            status_code = str(response.status_code)
            return response
        except Exception:
            raise
        finally:
            path_template = _resolve_path_template(request)
            method = request.method.upper()
            _REQUEST_COUNT.labels(
                method=method, path=path_template, status=status_code
            ).inc()
            elapsed = max(time.perf_counter() - start, 0.0)
            _REQUEST_DURATION.labels(method=method, path=path_template).observe(elapsed)


def _resolve_path_template(request: Request) -> str:
    route = request.scope.get("route")
    if route is not None:
        path = getattr(route, "path", None)
        if path:
            return str(path)
    raw_path = request.scope.get("path") or request.url.path
    return str(raw_path) if raw_path else "unknown"


def _authorization_header(request: Request) -> str:
    return request.headers.get("Authorization", "")


def _is_authorized(request: Request) -> bool:
    username = settings.metrics_basic_auth_username.strip()
    password = settings.metrics_basic_auth_password
    if not username and not password:
        return True

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


async def metrics_endpoint(request: Request) -> Response:
    if not settings.enable_metrics_endpoint:
        return PlainTextResponse("Not Found", status_code=404)

    _ensure_notification_queue_metrics_registry()

    if not _is_authorized(request):
        response = PlainTextResponse("Unauthorized", status_code=401)
        response.headers["WWW-Authenticate"] = 'Basic realm="Metrics"'
        return response

    if not _is_allowed(request):
        return PlainTextResponse("Forbidden", status_code=403)

    if REGISTRY is None:
        raise RuntimeError("prometheus-client is required to expose metrics")

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
