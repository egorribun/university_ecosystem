import asyncio
import os
import sys
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import httpx
import pytest
from asgi_lifespan import LifespanManager
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from opentelemetry.sdk import _logs as otel_logs
except Exception:
    otel_logs = None
else:
    if not hasattr(otel_logs, "set_logger_provider"):

        def _set_logger_provider(provider):
            return None

        otel_logs.set_logger_provider = _set_logger_provider

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("STATIC_DIR", "app/test-static")
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("RATE_LIMIT_SENSITIVE", "")
Path(os.environ.get("STATIC_DIR", "app/test-static")).mkdir(parents=True, exist_ok=True)

try:
    from slowapi import middleware as slowapi_middleware
except Exception:
    slowapi_middleware = None
else:

    class _NoopSlowAPIMiddleware:
        def __init__(self, app, *args, **kwargs):
            self.app = app

        async def __call__(self, scope, receive, send):
            await self.app(scope, receive, send)

    slowapi_middleware.SlowAPIMiddleware = _NoopSlowAPIMiddleware

from app.core import security_headers as security_headers_module


class _NoopSecurityHeadersMiddleware:
    def __init__(self, app, *args, **kwargs):
        self.app = app

    async def __call__(self, scope, receive, send):
        await self.app(scope, receive, send)


security_headers_module.SecurityHeadersMiddleware = _NoopSecurityHeadersMiddleware

from app import main
from app.core.database import Base, async_session, engine
from app.models import models


@pytest.fixture(scope="session")
def event_loop() -> AsyncIterator[asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()
    try:
        yield loop
    finally:
        loop.close()


@pytest.fixture(scope="session", autouse=True)
async def prepare_database() -> AsyncIterator[None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(autouse=True)
async def clean_database(prepare_database: None) -> AsyncIterator[None]:
    yield
    async with engine.begin() as conn:
        await conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
        await conn.exec_driver_sql("PRAGMA foreign_keys=ON")


@pytest.fixture
def app():
    return main.app


@pytest.fixture
async def async_client(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[httpx.AsyncClient]:
    async def _start_notifications_scheduler(
        *args, **kwargs
    ) -> Callable[[], Awaitable[None]]:
        async def _stop() -> None:
            return None

        return _stop

    monkeypatch.setattr(
        main, "start_notifications_scheduler", _start_notifications_scheduler
    )
    transport = httpx.ASGITransport(app=main.app)
    async with LifespanManager(main.app):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", follow_redirects=True
        ) as client:
            yield client


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    async with async_session() as session:
        yield session


@pytest.fixture
async def user_factory(db_session) -> Callable[..., Awaitable[models.User]]:
    async def _factory(**kwargs) -> models.User:
        defaults = {
            "email": f"user-{uuid.uuid4().hex[:8]}@example.com",
            "hashed_password": "hashed-password",
            "role": "student",
            "is_active": True,
        }
        defaults.update(kwargs)
        user = models.User(**defaults)
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    return _factory


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
