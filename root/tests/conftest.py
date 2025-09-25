import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


try:
    from opentelemetry.sdk import _logs as otel_logs
except Exception:  # pragma: no cover - optional dependency
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


try:
    from slowapi import middleware as slowapi_middleware
except Exception:  # pragma: no cover - optional dependency
    slowapi_middleware = None
else:
    class _PatchedSlowAPIMiddleware(slowapi_middleware.SlowAPIMiddleware):
        def __init__(self, app, *args, **kwargs):
            super().__init__(app)

    slowapi_middleware.SlowAPIMiddleware = _PatchedSlowAPIMiddleware


from app.core import security_headers as security_headers_module


class _PatchedSecurityHeadersMiddleware(security_headers_module.SecurityHeadersMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        return response


security_headers_module.SecurityHeadersMiddleware = _PatchedSecurityHeadersMiddleware

from app import main
from app.core.database import Base, async_session, engine
from app.models import models


@pytest.fixture(scope="session")
def event_loop() -> AsyncIterator[asyncio.AbstractEventLoop]:
    "Provide a dedicated event loop for the test session."
    loop = asyncio.new_event_loop()
    try:
        yield loop
    finally:
        loop.close()


@pytest.fixture(scope="session", autouse=True)
async def prepare_database() -> AsyncIterator[None]:
    "Ensure that the database schema exists for the duration of the test run."
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(autouse=True)
async def clean_database(prepare_database: None) -> AsyncIterator[None]:
    "Clean all tables between tests to guarantee isolation."
    yield
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


@pytest.fixture
def app():
    "Return the FastAPI application instance."
    return main.app


@pytest.fixture
async def async_client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    "Yield an HTTPX asynchronous client configured for the FastAPI app."

    async def _start_notifications_scheduler(*args, **kwargs) -> Callable[[], Awaitable[None]]:
        async def _stop() -> None:
            return None

        return _stop

    monkeypatch.setattr(main, "start_notifications_scheduler", _start_notifications_scheduler)
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    "Yield a database session bound to the test engine."
    async with async_session() as session:
        yield session


@pytest.fixture
async def user_factory(db_session) -> Callable[..., Awaitable[models.User]]:
    "Return a factory that persists user instances for tests."

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
