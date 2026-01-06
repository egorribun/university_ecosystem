from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.admin import router as admin_api_router
from app.api.health import (
    _check_queue,
    _lightweight_storage_probe,
    _probe_storage,
    _write_delete_storage_probe,
)
from app.api.health import router as health_router
from app.api.health import (
    reset_health_cache as _reset_health_cache,
)
from app.api.health import (
    reset_storage_probe_cache as _reset_storage_probe_cache,
)
from app.api.internal import router as internal_api_router
from app.api.public import router as public_api_router
from app.api.websocket import router as websocket_router
from app.core.config import settings
from app.core.database import engine, wait_db
from app.core.exceptions import AppException, app_exception_handler
from app.core.lifespan import lifespan
from app.core.metrics import configure_metrics
from app.core.middleware import configure_middleware
from app.core.observability import configure_observability
from app.core.versioning import API_VERSION
from app.deps.cache import get_cache
from app.routers.notifications import legacy_router as legacy_push_router
from app.services.file_scanner import (
    check_file_scanner_health,
)
from app.services.file_scanner import (
    scan_for_malware as _scan_for_malware,
)
from app.utils.files import _get_storage_backend
from app.utils.migrations import (
    migrations_are_current as _migrations_are_current,
)
from app.utils.migrations import (
    reset_migration_cache as _reset_migration_cache,
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
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# Exception handlers
app.add_exception_handler(AppException, app_exception_handler)

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


@app.get("/")
async def root():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    """Readiness probe."""
    await wait_db(max_attempts=1, delay=0.1)
    return {"status": "ready"}


# Routers
app.include_router(health_router)
app.include_router(public_api_router)
app.include_router(admin_api_router, include_in_schema=True)
app.include_router(internal_api_router, include_in_schema=False)
app.include_router(legacy_push_router)
app.include_router(websocket_router)
