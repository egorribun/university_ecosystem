from __future__ import annotations

# Configure uvloop before any other asyncio usage for optimal async performance
from app.core.uvloop_setup import configure_uvloop

configure_uvloop()

import logging

from fastapi import FastAPI, HTTPException

try:
    from fastapi.responses import JSONResponse, ORJSONResponse
except ImportError:
    from fastapi.responses import JSONResponse

    ORJSONResponse = JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.admin import router as admin_api_router
from app.api.health import router as health_router
from app.api.internal import router as internal_api_router
from app.api.public import router as public_api_router
from app.api.websocket import router as websocket_router
from app.core.config import settings
from app.core.database import engine
from app.core.exceptions import AppException, app_exception_handler
from app.core.exceptions.domain import DomainException
from app.core.exceptions.handlers import (
    domain_exception_handler,
    http_exception_handler,
)
from app.core.lifespan import lifespan
from app.core.metrics import configure_metrics
from app.core.middleware import (
    _ensure_vary_header,  # noqa: F401 - re-exported for API modules
    configure_middleware,
)
from app.core.observability import configure_observability
from app.core.versioning import API_VERSION
from app.graphql.schema import graphql_router
from app.services.file_scanner import (
    scan_for_malware as _scan_for_malware,
)

# Re-exports for test compatibility and internal use
scan_for_malware = _scan_for_malware


app = FastAPI(
    title="University Ecosystem API",
    description=(
        "REST API for university life management platform - "
        "schedules, news, events, notifications, and more."
    ),
    version=API_VERSION,
    default_response_class=ORJSONResponse,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# Exception handlers
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(DomainException, domain_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)

# Observability & Metrics
configure_observability(app, engine=engine)
configure_metrics(app)

# Middlewares
configure_middleware(app, settings=settings)

# Static files
static_dir = settings.static_dir_path
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

_logger = logging.getLogger(__name__)


@app.get("/", response_class=JSONResponse, summary="Root")
async def get_root():
    return JSONResponse(status_code=200, content={"status": "ok"})


# Routers
app.include_router(health_router)
app.include_router(public_api_router)
app.include_router(admin_api_router, include_in_schema=True)
app.include_router(internal_api_router, include_in_schema=False)
app.include_router(websocket_router)
app.include_router(graphql_router, prefix="/graphql", include_in_schema=False)
