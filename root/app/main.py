from __future__ import annotations

import time
import uuid
from functools import lru_cache
from pathlib import Path

from brotli_asgi import BrotliMiddleware
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from alembic.config import Config
from alembic.script import ScriptDirectory
from app.api.internal import INTERNAL_ROUTE_PREFIXES
from app.api.internal import router as internal_api_router
from app.api.public import router as public_api_router
from app.api.websocket import router as websocket_router
from app.core.config import settings
from app.core.database import async_session, engine, wait_db
from app.core.exceptions import AppException
from app.core.internal_access import InternalAccessMiddleware
from app.core.lifespan import lifespan
from app.core.metrics import configure_metrics, record_health_probe
from app.core.observability import configure_observability
from app.core.rate_limit import RateLimitMiddleware, parse_rate_limit
from app.core.security_headers import SecurityHeadersMiddleware
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

try:
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
except Exception:
    ProxyHeadersMiddleware = None


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


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.message,
            "code": exc.code,
            "payload": exc.payload,
        },
    )


configure_observability(app, engine=engine)
configure_metrics(app)

# Re-export the malware scanning helper so health checks can be monkeypatched in tests
# without importing the heavy scanning module directly.
scan_for_malware = _scan_for_malware

_RESPONSE_COMPRESSION_MINIMUM_SIZE = 512

if settings.response_compression_enabled:
    app.add_middleware(
        BrotliMiddleware,
        minimum_size=_RESPONSE_COMPRESSION_MINIMUM_SIZE,
        gzip_fallback=True,
        quality=5,
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins_list,
    allow_credentials=settings.cors_allow_credentials_effective,
    allow_methods=settings.cors_allow_methods_list,
    allow_headers=settings.cors_allow_headers_list,
    expose_headers=settings.cors_expose_headers_list,
)

app.add_middleware(SecurityHeadersMiddleware, settings=settings)

app.add_middleware(
    InternalAccessMiddleware,
    allowed_ips=settings.internal_allowed_ips_list,
    header_name=settings.internal_auth_header,
    header_token=settings.internal_auth_token,
    internal_prefixes=INTERNAL_ROUTE_PREFIXES,
)


def _ensure_vary_header(response, header_name: str) -> None:
    existing = response.headers.get("Vary")
    if not existing:
        response.headers["Vary"] = header_name
        return
    values = [value.strip() for value in existing.split(",") if value.strip()]
    if header_name not in values:
        values.append(header_name)
        response.headers["Vary"] = ", ".join(values)


@app.middleware("http")
async def _http_response_hardening(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/") and response.status_code == 200:
        # Encourage browsers to keep avatars locally without marking them immutable.
        response.headers.setdefault("Cache-Control", "public, max-age=86400")
    acao = response.headers.get("access-control-allow-origin")
    if acao and acao != "*":
        _ensure_vary_header(response, "Origin")
        if request.method.upper() == "OPTIONS":
            _ensure_vary_header(response, "Access-Control-Request-Method")
            if request.headers.get("access-control-request-headers"):
                _ensure_vary_header(response, "Access-Control-Request-Headers")
    return response


rate_limit_url = settings.rate_limit_storage_uri.strip()
rate_limit_backend = settings.rate_limit_storage_backend.strip().lower()
rate_limit_defaults = settings.rate_limit_default_list
default_limit, default_window = parse_rate_limit(
    rate_limit_defaults[0] if rate_limit_defaults else None,
    fallback=(60, 60),
)

if settings.rate_limit_enabled:
    normalized_url = rate_limit_url.lower()
    if rate_limit_backend == "redis" and normalized_url.startswith(
        ("redis://", "rediss://")
    ):
        app.add_middleware(
            RateLimitMiddleware,
            redis_url=rate_limit_url,
            limit=default_limit,
            window_seconds=default_window,
            headers_enabled=settings.rate_limit_headers_enabled,
            storage_backend="redis",
        )
    elif rate_limit_backend == "memory" or normalized_url.startswith("memory://"):
        app.add_middleware(
            RateLimitMiddleware,
            redis_url=None,
            limit=default_limit,
            window_seconds=default_window,
            headers_enabled=settings.rate_limit_headers_enabled,
            storage_backend="memory",
        )

if ProxyHeadersMiddleware:
    trusted_hosts = settings.trusted_hosts_list
    if trusted_hosts:
        app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=trusted_hosts)

static_dir = settings.static_dir_path
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def root():
    return {"status": "ok"}


@lru_cache
def _get_alembic_script() -> ScriptDirectory:
    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))
    return ScriptDirectory.from_config(config)


async def _migrations_are_current() -> bool:
    script = _get_alembic_script()
    expected_heads = set(script.get_heads())
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT version_num FROM alembic_version"))
        current_versions = {row[0] for row in result}
    return current_versions == expected_heads


@app.get("/healthz")
async def healthz():
    statuses: dict[str, str] = {}

    db_status = "ok"
    db_start = time.perf_counter()
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"
    else:
        try:
            migrations_current = await _migrations_are_current()
            if not migrations_current:
                db_status = "error"
        except Exception:
            db_status = "error"
    statuses["db"] = db_status
    if db_status == "error":
        statuses["db_migrations"] = "error"
    record_health_probe("db", db_status, time.perf_counter() - db_start)

    cache_status = "disabled"
    cache_start = time.perf_counter()
    try:
        cache_backend = get_cache()
        if getattr(cache_backend, "enabled", False):
            probe_key = f"healthz:{uuid.uuid4().hex}"
            try:
                await cache_backend.set(probe_key, {"status": "ok"}, ttl=5)
                cache_status = "ok"
            except Exception:
                cache_status = "error"
            finally:
                try:
                    await cache_backend.invalidate(probe_key)
                except Exception:
                    cache_status = "error"
        else:
            cache_status = "disabled"
    except Exception:
        cache_status = "error"
    statuses["cache"] = cache_status
    record_health_probe("cache", cache_status, time.perf_counter() - cache_start)

    storage_status = "ok"
    try:
        backend = _get_storage_backend()
        probe_name = f"healthz/{uuid.uuid4().hex}.txt"
        try:
            probe_url = await backend.save_file(
                probe_name, b"", content_type="text/plain"
            )
        except Exception:
            storage_status = "error"
        else:
            try:
                await backend.delete_file(probe_url)
            except Exception:
                storage_status = "error"
    except Exception:
        storage_status = "error"
    statuses["storage"] = storage_status

    queue_status = "ok"
    if getattr(settings, "notifications_queue_in_memory_only", False):
        queue_status = "ok"
    else:
        try:
            async with async_session() as session:
                await session.execute(text("SELECT 1 FROM notification_queue_jobs"))
        except OperationalError:
            queue_status = "error"
        except Exception:
            queue_status = "error"
    statuses["notification_queue"] = queue_status

    if getattr(settings, "event_file_scanner_enabled", False):
        scanner_status = "ok"
        try:
            await check_file_scanner_health()
        except Exception:
            scanner_status = "error"
        statuses["file_scanner"] = scanner_status
    else:
        statuses["file_scanner"] = "disabled"

    overall_ok = all(value != "error" for value in statuses.values())
    http_status = (
        status.HTTP_200_OK if overall_ok else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    payload = {"status": "ok" if overall_ok else "error", **statuses}
    return JSONResponse(status_code=http_status, content=payload)


@app.get("/ready")
async def ready():
    await wait_db(max_attempts=1, delay=0.1)
    return {"status": "ready"}


# Public and internal API routers
app.include_router(public_api_router)
app.include_router(internal_api_router, include_in_schema=False)

# Legacy push router for backward compatibility (deprecated)
app.include_router(legacy_push_router)

# WebSocket router (mounted at root level - /ws/*)
app.include_router(websocket_router)
