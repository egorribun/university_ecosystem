from __future__ import annotations

# Configure uvloop before any other asyncio usage for optimal async performance
from app.core.uvloop_setup import configure_uvloop

configure_uvloop()


from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.admin import router as admin_api_router
from app.api.health import router as health_router
from app.api.internal import router as internal_api_router
from app.api.public import router as public_api_router
from app.api.websocket import router as websocket_router
from app.api.well_known import router as well_known_router
from app.api.ws.ticket import router as ws_ticket_router
from app.core.config import settings
from app.core.database import engine
from app.core.exceptions import AppException, app_exception_handler
from app.core.exceptions.domain import DomainException
from app.core.exceptions.handlers import (
    domain_exception_handler,
    http_exception_handler,
)
from app.core.lifespan import lifespan
from app.core.logging import get_logger
from app.core.metrics import configure_metrics
from app.core.middleware import (
    _ensure_vary_header,
    configure_middleware,
)
from app.core.observability import configure_observability
from app.core.ratelimit.exceptions import (
    RateLimitExceeded,
    RateLimitStorageUnavailable,
)
from app.core.versioning import API_VERSION
from app.graphql.schema import graphql_router
from app.openapi import install_custom_openapi
from app.services.file_scanner import (
    scan_for_malware as _scan_for_malware,
)

# Re-exports for test compatibility and internal use
scan_for_malware = _scan_for_malware

# Initialize Profiler (TD-003: audit 2026-03-10)
from app.core.profiling import get_profiler

get_profiler().configure()

# Disable interactive API documentation in non-development environments to
# reduce attack surface (schema enumeration, PoC generation by attackers).
_is_dev = settings.environment in {"development", "testing", "local"}
app = FastAPI(
    title="University Ecosystem API",
    description=(
        "REST API for university life management platform - "
        "schedules, news, events, notifications, and more."
    ),
    version=API_VERSION,
    docs_url="/api/docs" if _is_dev else None,
    redoc_url="/api/redoc" if _is_dev else None,
    openapi_url="/api/openapi.json" if _is_dev else None,
    lifespan=lifespan,
)

# Exception handlers
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(DomainException, domain_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)


async def _rate_limit_storage_unavailable_handler(
    request: object, exc: Exception
) -> JSONResponse:
    """RZ-14-01: Fail-closed rate limit storage → HTTP 503 (not silent in-memory fallback)."""
    return JSONResponse(
        status_code=503,
        content={"detail": "Rate limit service temporarily unavailable"},
        headers={"Retry-After": "5"},
    )


app.add_exception_handler(
    RateLimitStorageUnavailable, _rate_limit_storage_unavailable_handler
)


async def _rate_limit_exceeded_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """RZ-14-02: Global handler for RateLimitExceeded → HTTP 429."""
    if not isinstance(exc, RateLimitExceeded):
        return await http_exception_handler(request, exc)  # Fallback

    from app.core.localization import resolve_locale, translate

    locale = resolve_locale(request=request)
    detail = translate("errors.rate_limit.generic", locale=locale)

    retry_after = max(0, exc.info.retry_after)
    headers = {"Retry-After": str(retry_after)} if retry_after else None

    return JSONResponse(
        status_code=429,
        content={"detail": detail},
        headers=headers,
    )


app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Observability & Metrics
configure_observability(app, engine=engine)
configure_metrics(app)


# Routers and Middlewares setup


# Middlewares
configure_middleware(app, settings=settings)

from app.core.security.spiffe import SPIFFEAuthMiddleware

app.add_middleware(
    SPIFFEAuthMiddleware,
    allowed_spiffe_ids=settings.security.spiffe_allowed_clients,
    protected_prefixes=("/api/internal", "/api/v1/chat/check-participant"),
    enabled=settings.security.spiffe_enabled,
)

from dishka.integrations.fastapi import setup_dishka

from app.core.di_provider import create_dishka_container

setup_dishka(create_dishka_container(), app)


# Static files
static_dir = settings.static_dir_path
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

_logger = get_logger(__name__)


@app.get("/", response_class=JSONResponse, summary="Root")
async def get_root() -> JSONResponse:
    return JSONResponse(status_code=200, content={"status": "ok"})


# Routers
app.include_router(health_router)
app.include_router(well_known_router, prefix="/.well-known", include_in_schema=False)
app.include_router(public_api_router)
app.include_router(admin_api_router, include_in_schema=True)
app.include_router(internal_api_router, include_in_schema=False)
app.include_router(websocket_router)
app.include_router(ws_ticket_router)  # RZ-W14-01: POST /ws/ticket
app.include_router(graphql_router, prefix="/graphql", include_in_schema=False)
install_custom_openapi(app)

__all__ = ["_ensure_vary_header", "app", "scan_for_malware"]
