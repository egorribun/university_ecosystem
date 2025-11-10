from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError
from starlette.middleware.gzip import GZipMiddleware

from app.api.events import router as events_router
from app.api.news import router as news_router
from app.api.notifications import router as notifications_router
from app.api.schedule import router as schedule_api_router
from app.api.sessions import router as sessions_router
from app.api.spotify import router as spotify_router
from app.api.stats import router as stats_router
from app.api.stories import router as stories_router
from app.api.users import router as users_router
from app.auth.auth import router as auth_router
from app.core.config import settings
from app.core.database import Base, async_session, engine, wait_db
from app.core.metrics import configure_metrics
from app.core.observability import configure_observability, shutdown_observability
from app.core.rate_limit import RateLimitMiddleware, parse_rate_limit
from app.core.schema_upgrade import ensure_webauthn_attestation_columns
from app.core.security_headers import SecurityHeadersMiddleware
from app.deps.cache import get_cache, shutdown_cache
from app.models.models import NotificationQueueJob
from app.routers.notifications import legacy_router as legacy_push_router
from app.routers.notifications import router as push_router
from app.routers.schedule import router as schedule_router
from app.services import notification_queue, webpush
from app.services.email_change_cleanup import (
    EmailChangeCleanupConfig,
    cleanup_stale_email_change_tokens,
    start_email_change_cleanup_scheduler,
)
from app.services.file_scanner import (
    check_file_scanner_health,
    scan_for_malware as _scan_for_malware,
)
from app.services.notification_queue import (
    DeadLetterCleanupConfig,
    start_dead_letter_cleanup_scheduler,
)
from app.services.notifications import (
    cleanup_stale_notifications,
    start_notifications_scheduler,
)
from app.services.notifications_retention import (
    NotificationsRetentionConfig,
    start_notifications_retention_scheduler,
)
from app.services.password_reset_cleanup import (
    PasswordResetCleanupConfig,
    cleanup_stale_password_reset_tokens,
    start_password_reset_cleanup_scheduler,
)
from app.services.session_cleanup import (
    SessionCleanupConfig,
    cleanup_expired_sessions,
    start_session_cleanup_scheduler,
)
from app.services.story_cleanup import (
    StoryCleanupConfig,
    cleanup_expired_stories,
    start_story_cleanup_scheduler,
)
from app.utils.files import _get_storage_backend

try:
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
except Exception:
    ProxyHeadersMiddleware = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    await wait_db(max_attempts=10, delay=0.5)
    if settings.auto_create_schema:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await ensure_webauthn_attestation_columns(engine)
    stop_scheduler = None
    stop_notifications_retention = None
    stop_dead_letter_cleanup = None
    stop_session_cleanup = None
    stop_story_cleanup = None
    stop_password_reset_cleanup = None
    stop_email_change_cleanup = None
    if settings.is_development and settings.notifications_scheduler_inline_enabled:
        stop_scheduler = await start_notifications_scheduler(
            poll_seconds=settings.notifications_scheduler_poll_seconds,
            window_minutes=settings.notifications_scheduler_window_minutes,
            max_backoff_seconds=settings.notifications_scheduler_max_backoff_seconds,
        )
    await cleanup_stale_notifications(
        retention_days=settings.notifications_retention_days
    )
    await notification_queue.cleanup_dead_lettered_jobs(
        retention_days=settings.notification_queue_dead_letter_retention_days
    )
    await cleanup_expired_sessions()
    await cleanup_expired_stories()
    await cleanup_stale_password_reset_tokens(
        retention_minutes=settings.password_reset_cleanup_retention_minutes
    )
    await cleanup_stale_email_change_tokens(
        retention_minutes=settings.email_change_cleanup_retention_minutes
    )
    if (
        settings.notifications_retention_days > 0
        and settings.notifications_retention_cleanup_interval_seconds > 0
    ):
        stop_notifications_retention = await start_notifications_retention_scheduler(
            config=NotificationsRetentionConfig(
                retention_days=settings.notifications_retention_days,
                interval_seconds=settings.notifications_retention_cleanup_interval_seconds,
            )
        )
    if (
        settings.notification_queue_dead_letter_retention_days > 0
        and settings.notification_queue_dead_letter_cleanup_interval_seconds > 0
    ):
        stop_dead_letter_cleanup = await start_dead_letter_cleanup_scheduler(
            config=DeadLetterCleanupConfig(
                retention_days=settings.notification_queue_dead_letter_retention_days,
                interval_seconds=settings.notification_queue_dead_letter_cleanup_interval_seconds,
            )
        )
    if settings.session_cleanup_interval_seconds > 0:
        stop_session_cleanup = await start_session_cleanup_scheduler(
            config=SessionCleanupConfig(
                interval_seconds=settings.session_cleanup_interval_seconds
            )
        )
    if settings.password_reset_cleanup_interval_seconds > 0:
        stop_password_reset_cleanup = await start_password_reset_cleanup_scheduler(
            config=PasswordResetCleanupConfig(
                interval_seconds=settings.password_reset_cleanup_interval_seconds,
                retention_minutes=settings.password_reset_cleanup_retention_minutes,
            )
        )
    if settings.email_change_cleanup_interval_seconds > 0:
        stop_email_change_cleanup = await start_email_change_cleanup_scheduler(
            config=EmailChangeCleanupConfig(
                interval_seconds=settings.email_change_cleanup_interval_seconds,
                retention_minutes=settings.email_change_cleanup_retention_minutes,
            )
        )
    if (
        settings.stories_cleanup_enabled
        and settings.stories_retention_cleanup_interval_seconds > 0
    ):
        stop_story_cleanup = await start_story_cleanup_scheduler(
            config=StoryCleanupConfig(
                interval_seconds=settings.stories_retention_cleanup_interval_seconds
            )
        )
    try:
        yield
    finally:
        if stop_scheduler is not None:
            await stop_scheduler()
        if stop_notifications_retention is not None:
            await stop_notifications_retention()
        if stop_dead_letter_cleanup is not None:
            await stop_dead_letter_cleanup()
        if stop_session_cleanup is not None:
            await stop_session_cleanup()
        if stop_story_cleanup is not None:
            await stop_story_cleanup()
        if stop_password_reset_cleanup is not None:
            await stop_password_reset_cleanup()
        if stop_email_change_cleanup is not None:
            await stop_email_change_cleanup()
        await notification_queue.shutdown_notification_queue()
        webpush.cleanup()
        await shutdown_cache()
        shutdown_observability()


app = FastAPI(lifespan=lifespan)

configure_observability(app, engine=engine)
configure_metrics(app)

# Re-export the malware scanning helper so health checks can be monkeypatched in tests
# without importing the heavy scanning module directly.
scan_for_malware = _scan_for_malware

_RESPONSE_COMPRESSION_MINIMUM_SIZE = 512

if settings.response_compression_enabled:
    app.add_middleware(
        GZipMiddleware,
        minimum_size=_RESPONSE_COMPRESSION_MINIMUM_SIZE,
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


_MISSING_TABLE_SQLSTATES = {
    "42P01",  # PostgreSQL undefined_table
    "42S02",  # MySQL/MariaDB ER_NO_SUCH_TABLE
}


def _is_missing_table_error(exc: OperationalError) -> bool:
    """Return True if the OperationalError represents a missing table."""

    orig = getattr(exc, "orig", None)
    if orig is not None:
        sqlstate = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)
        # Keep this list in sync with supported backends' SQLSTATEs.
        if sqlstate in _MISSING_TABLE_SQLSTATES:
            return True

        message = str(orig).lower()
    else:
        message = str(exc).lower()

    missing_table_fragments = (
        "no such table",
        "does not exist",
        "doesn't exist",
        "unknown table",
    )
    return any(fragment in message for fragment in missing_table_fragments)


@app.get("/healthz")
async def healthz():
    statuses: dict[str, str] = {}

    db_status = "ok"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"
    statuses["db"] = db_status

    cache_status = "disabled"
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
                await session.execute(
                    select(func.count()).select_from(NotificationQueueJob)
                )
        except OperationalError as exc:
            if not _is_missing_table_error(exc):
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


app.include_router(auth_router)
app.include_router(spotify_router)
app.include_router(sessions_router)
app.include_router(notifications_router)
app.include_router(push_router)
app.include_router(legacy_push_router)
app.include_router(schedule_router)
app.include_router(users_router)
app.include_router(events_router)
app.include_router(news_router)
app.include_router(stories_router)
app.include_router(schedule_api_router)
app.include_router(stats_router)
