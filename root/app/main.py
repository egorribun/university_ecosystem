from __future__ import annotations

import asyncio
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
from app.services.storage import S3Storage, StaticFSStorage
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

print(f"DEBUG: CORS Origins: {settings.cors_allow_origins_list}")


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins_list,
    allow_credentials=settings.cors_allow_credentials_effective,
    allow_methods=settings.cors_allow_methods_list,
    allow_headers=settings.cors_allow_headers_list,
    expose_headers=settings.cors_expose_headers_list,
)


@app.get("/")
async def root():
    return {"status": "ok"}


@lru_cache
def _get_alembic_script() -> ScriptDirectory:
    project_root = Path(__file__).resolve().parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))
    return ScriptDirectory.from_config(config)


async def _migrations_are_current() -> tuple[bool, set[str], set[str]]:
    script = _get_alembic_script()
    expected_heads = set(script.get_heads())
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT version_num FROM alembic_version"))
        current_versions = {row[0] for row in result}
    return current_versions == expected_heads, current_versions, expected_heads


_storage_probe_cache: dict[str, float | str] = {
    "expires_at": 0.0,
    "status": "unknown",
    "latency": 0.0,
}


def _reset_storage_probe_cache() -> None:
    _storage_probe_cache.update(
        {"expires_at": 0.0, "status": "unknown", "latency": 0.0}
    )


async def _lightweight_storage_probe(backend) -> str | None:
    if isinstance(backend, StaticFSStorage):
        exists = await asyncio.to_thread(backend.base_dir.exists)
        return "ok" if exists else "error"
    if isinstance(backend, S3Storage):
        await asyncio.to_thread(
            backend.client.list_objects_v2, Bucket=backend.bucket, MaxKeys=0
        )
        return "ok"
    return None


async def _write_delete_storage_probe(backend) -> str:
    probe_name = f"healthz/{uuid.uuid4().hex}.txt"
    try:
        probe_url = await backend.save_file(probe_name, b"", content_type="text/plain")
    except Exception:
        return "error"
    try:
        await backend.delete_file(probe_url)
    except Exception:
        return "error"
    return "ok"


async def _probe_storage() -> tuple[str, float]:
    now = time.monotonic()
    cached_expires_at = float(_storage_probe_cache.get("expires_at", 0.0) or 0.0)
    if cached_expires_at > now:
        status = str(_storage_probe_cache.get("status", "unknown"))
        latency_seconds = float(_storage_probe_cache.get("latency", 0.0) or 0.0)
        return status, latency_seconds

    start = time.perf_counter()
    status: str | None = None
    try:
        backend = _get_storage_backend()
        if settings.health_storage_probe_enabled:
            status = await _write_delete_storage_probe(backend)
        if status is None:
            lightweight_status = await _lightweight_storage_probe(backend)
            if lightweight_status is not None:
                status = lightweight_status
            else:
                status = "disabled"
        elif status == "error":
            lightweight_status = await _lightweight_storage_probe(backend)
            if lightweight_status is not None:
                status = lightweight_status
    except Exception:
        status = "error"
    elapsed = time.perf_counter() - start
    latency_seconds = max(elapsed, 0.0)
    _storage_probe_cache.update(
        {
            "expires_at": now
            + max(settings.health_storage_probe_min_interval_seconds, 0.0),
            "status": status,
            "latency": latency_seconds,
        }
    )
    return status, latency_seconds


@app.get("/healthz")
async def healthz():
    statuses: dict[str, str] = {}

    latencies: dict[str, float] = {}

    db_status = "ok"
    db_start = time.perf_counter()
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"
    else:
        try:
            (
                migrations_current,
                current_versions,
                expected_versions,
            ) = await _migrations_are_current()
            if not migrations_current:
                db_status = "error"
                statuses["db_migrations"] = "error"
                statuses["db_migrations_current"] = sorted(current_versions)
                statuses["db_migrations_expected"] = sorted(expected_versions)
        except Exception:
            db_status = "error"
    statuses["db"] = db_status
    if db_status == "error":
        statuses.setdefault("db_migrations", "error")
    db_elapsed = time.perf_counter() - db_start
    latencies["db_latency_ms"] = max(db_elapsed * 1000, 0.0)
    record_health_probe("db", db_status, db_elapsed)

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
    cache_elapsed = time.perf_counter() - cache_start
    statuses["cache"] = cache_status
    latencies["cache_latency_ms"] = max(cache_elapsed * 1000, 0.0)
    record_health_probe("cache", cache_status, cache_elapsed)

    storage_status, storage_elapsed = await _probe_storage()
    statuses["storage"] = storage_status
    latencies["storage_latency_ms"] = max(storage_elapsed * 1000, 0.0)
    record_health_probe("storage", storage_status, storage_elapsed)

    queue_status = "ok"
    queue_start = time.perf_counter()
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
    queue_elapsed = time.perf_counter() - queue_start
    statuses["notification_queue"] = queue_status
    latencies["notification_queue_latency_ms"] = max(queue_elapsed * 1000, 0.0)
    record_health_probe("notification_queue", queue_status, queue_elapsed)

    scanner_start = time.perf_counter()
    if getattr(settings, "event_file_scanner_enabled", False):
        scanner_status = "ok"
        try:
            await check_file_scanner_health()
        except Exception:
            scanner_status = "error"
    else:
        scanner_status = "disabled"
    scanner_elapsed = time.perf_counter() - scanner_start
    statuses["file_scanner"] = scanner_status
    latencies["file_scanner_latency_ms"] = max(scanner_elapsed * 1000, 0.0)
    record_health_probe("file_scanner", scanner_status, scanner_elapsed)

    overall_ok = all(value != "error" for value in statuses.values())
    http_status = (
        status.HTTP_200_OK if overall_ok else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    payload = {"status": "ok" if overall_ok else "error", **statuses, **latencies}
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
