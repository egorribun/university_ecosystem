from typing import List
import os
import inspect
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import engine
from app.models.models import Base
from app.api.routes import router as main_router
from app.auth.auth import router as auth_router
from app.api.spotify import router as spotify_router
from app.api.notifications import router as notifications_router
from app.api.push import router as push_router
from app.services.notifications import start_notifications_scheduler

try:
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
except Exception:
    ProxyHeadersMiddleware = None


def collect_origins() -> List[str]:
    values: List[str] = []
    candidates = (
        getattr(settings, "frontend_origins", None),
        getattr(settings, "frontend_origin", None),
        getattr(settings, "app_base_url", None),
        os.getenv("FRONTEND_ORIGINS", None),
    )
    for v in candidates:
        if not v:
            continue
        if isinstance(v, (list, tuple, set)):
            values.extend([str(x) for x in v if x])
        elif isinstance(v, str):
            values.extend([p.strip() for p in v.split(",") if p.strip()])
    values.extend(["http://localhost:5173", "http://127.0.0.1:5173"])
    seen = set()
    out: List[str] = []
    for o in values:
        o = o.rstrip("/")
        if o and o not in seen:
            seen.add(o)
            out.append(o)
    return out


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    stop_handle = start_notifications_scheduler()
    if inspect.isawaitable(stop_handle):
        stop_handle = await stop_handle
    try:
        yield
    finally:
        if callable(stop_handle):
            res = stop_handle()
            if inspect.isawaitable(res):
                await res


app = FastAPI(lifespan=lifespan)

origins = collect_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

if ProxyHeadersMiddleware:
    trusted_hosts = settings.trusted_hosts_list
    if trusted_hosts:
        app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=trusted_hosts)

if not os.path.isdir(settings.static_dir):
    os.makedirs(settings.static_dir, exist_ok=True)

app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")


@app.get("/")
async def root():
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(spotify_router)
app.include_router(notifications_router)
app.include_router(push_router)
app.include_router(main_router)