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
from app.core.rate_limit import (
    RateLimitMiddleware,
    create_rate_limit_client,
    parse_rate_limit,
)
from app.core.security_headers import SecurityHeadersMiddleware
from app.deps.cache import shutdown_cache
from app.routers.notifications import legacy_router as legacy_push_router
from app.routers.notifications import router as push_router
from app.routers.schedule import router as schedule_router
from app.services.notifications import start_notifications_scheduler
from redis.asyncio import Redis
from redis.exceptions import RedisError

try:
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
except Exception:
    ProxyHeadersMiddleware = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    await wait_db(max_attempts=10, delay=0.5)
    await _ensure_required_redis()
    if settings.auto_create_schema:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    stop_scheduler = await start_notifications_scheduler()
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


async def _ensure_required_redis() -> None:
    if not (settings.rate_limit_enabled or settings.cache_enabled):
        return

    redis_urls: set[str] = set()
    rate_limit_urls: set[str] = set()

    if settings.rate_limit_enabled:
        rl_url = settings.rate_limit_storage_uri.strip()
        if rl_url:
            redis_urls.add(rl_url)
            rate_limit_urls.add(rl_url)

    if settings.cache_enabled:
        cache_url = settings.cache_redis_url_effective.strip()
        if cache_url:
            redis_urls.add(cache_url)

    urls_to_check = {url for url in redis_urls if url}
    if not urls_to_check:
        return

    is_dev_env = settings.is_development
    non_redis_urls = {
        url
        for url in urls_to_check
        if not url.lower().startswith(("redis://", "rediss://"))
    }

    if non_redis_urls and not is_dev_env:
        formatted = ", ".join(sorted(non_redis_urls))
        raise RuntimeError(
            "Redis is required for throttling or caching, but non-Redis URIs were "
            f"provided: {formatted}."
        )

    urls_to_check -= non_redis_urls
    if not urls_to_check:
        return

    for url in urls_to_check:
        if url in rate_limit_urls:
            client = create_rate_limit_client(url)
            should_close = not client.__class__.__module__.startswith("fakeredis")
        else:
            client = Redis.from_url(
                url,
                encoding="utf-8",
                decode_responses=True,
                health_check_interval=30,
            )
            should_close = True
        try:
            await client.ping()
        except (RedisError, OSError) as exc:  # pragma: no cover - network dependent
            raise RuntimeError(
                "Redis is required for throttling or caching, but the instance at "
                f"{url} is unreachable."
            ) from exc
        finally:
            if should_close and hasattr(client, "aclose"):
                try:
                    await client.aclose()
                except (RedisError, OSError):
                    pass


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

if settings.rate_limit_enabled:
    if rate_limit_url.lower().startswith(("redis://", "rediss://")):
        app.add_middleware(
            RateLimitMiddleware,
            redis_url=rate_limit_url,
            limit=default_limit,
            window_seconds=default_window,
            headers_enabled=settings.rate_limit_headers_enabled,
        )
    elif not settings.is_development:
        raise RuntimeError(
            "Rate limiting is enabled but RATE_LIMIT_STORAGE_URI is not a Redis URI."
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
