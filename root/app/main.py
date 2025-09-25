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
from app.services.notifications import start_notifications_scheduler

try:  # pragma: no cover - optional dependency
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
except Exception:  # pragma: no cover - optional dependency
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


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

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


app.include_router(auth_router)
app.include_router(spotify_router)
app.include_router(notifications_router)
app.include_router(push_router)
app.include_router(main_router)
