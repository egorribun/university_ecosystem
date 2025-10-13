from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.events import router as events_router
from app.api.news import router as news_router
from app.api.notifications import router as notifications_router
from app.api.schedule import router as schedule_api_router
from app.api.spotify import router as spotify_router
from app.api.users import router as users_router
from app.auth.auth import router as auth_router
from app.core.config import settings
from app.core.database import Base, engine, wait_db
from app.core.observability import configure_observability, shutdown_observability
from app.core.rate_limit import RateLimitMiddleware, parse_rate_limit
from app.core.security_headers import SecurityHeadersMiddleware
from app.deps.cache import shutdown_cache
from app.routers.notifications import legacy_router as legacy_push_router
from app.routers.notifications import router as push_router
from app.routers.schedule import router as schedule_router
from app.services.notifications import start_notifications_scheduler

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
    stop_scheduler = None
    if settings.is_development and settings.notifications_scheduler_inline_enabled:
        stop_scheduler = await start_notifications_scheduler(
            poll_seconds=settings.notifications_scheduler_poll_seconds,
            window_minutes=settings.notifications_scheduler_window_minutes,
            max_backoff_seconds=settings.notifications_scheduler_max_backoff_seconds,
        )
    try:
        yield
    finally:
        if stop_scheduler is not None:
            await stop_scheduler()
        await shutdown_cache()
        shutdown_observability()


app = FastAPI(lifespan=lifespan)

configure_observability(app, engine=engine)

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
rate_limit_defaults = settings.rate_limit_default_list
default_limit, default_window = parse_rate_limit(
    rate_limit_defaults[0] if rate_limit_defaults else None,
    fallback=(60, 60),
)

if settings.rate_limit_enabled and rate_limit_url.lower().startswith(
    ("redis://", "rediss://")
):
    app.add_middleware(
        RateLimitMiddleware,
        redis_url=rate_limit_url,
        limit=default_limit,
        window_seconds=default_window,
        headers_enabled=settings.rate_limit_headers_enabled,
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


@app.get("/healthz")
async def healthz():
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    await wait_db(max_attempts=1, delay=0.1)
    return {"status": "ready"}


app.include_router(auth_router)
app.include_router(spotify_router)
app.include_router(notifications_router)
app.include_router(push_router)
app.include_router(legacy_push_router)
app.include_router(schedule_router)
app.include_router(users_router)
app.include_router(events_router)
app.include_router(news_router)
app.include_router(schedule_api_router)
