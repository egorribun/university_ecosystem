from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.notifications import router as notifications_router
from app.api.push import router as push_router
from app.api.routes import router as main_router
from app.api.spotify import router as spotify_router
from app.auth.auth import router as auth_router
from app.core.config import settings
from app.core.database import Base, engine, wait_db
from app.core.observability import configure_observability, shutdown_observability
from app.core.security_headers import SecurityHeadersMiddleware
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
    stop_scheduler = await start_notifications_scheduler()
    try:
        yield
    finally:
        if stop_scheduler is not None:
            await stop_scheduler()
        shutdown_observability()


app = FastAPI(lifespan=lifespan)

configure_observability(app, engine=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins_list,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods_list,
    allow_headers=settings.cors_allow_headers_list,
    expose_headers=settings.cors_expose_headers_list,
)

app.add_middleware(SecurityHeadersMiddleware, settings=settings)

if ProxyHeadersMiddleware:
    trusted_hosts = settings.trusted_hosts_list
    if trusted_hosts:
        app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=trusted_hosts)

static_dir = settings.static_dir_path
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


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
app.include_router(main_router)