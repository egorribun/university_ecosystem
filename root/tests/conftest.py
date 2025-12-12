import asyncio
import datetime as dt
import os
import sys
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parent
for candidate in (REPO_ROOT, PROJECT_ROOT):
    path_str = str(candidate)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

import inspect
import logging

import fakeredis.aioredis
import httpx
import pytest
from asgi_lifespan import LifespanManager
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

pytest_plugins = ("pytest_asyncio", "pytest_cov")

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
os.environ.setdefault(
    "SPOTIFY_TOKEN_SECRET", "aN-c6G_Gi7q0E8VnXW0fvkYlCYwH14r2raXI5Qun7Ss="
)
os.environ.setdefault("RATE_LIMIT_ENABLED", "true")
os.environ.setdefault("RATE_LIMIT_DEFAULT", "5/minute,10/hour")
os.environ.setdefault("RATE_LIMIT_SENSITIVE", "4/minute")
os.environ.setdefault("RATE_LIMIT_STORAGE_BACKEND", "redis")
os.environ.setdefault("RATE_LIMIT_STORAGE_URI", "redis://test")
os.environ.setdefault("ATTENDANCE_TOKEN_SECRET", "attendance-test-secret")
os.environ.setdefault("INTERNAL_AUTH_TOKEN", "test-internal-token")
os.environ.setdefault("INTERNAL_ALLOWED_IPS", "127.0.0.1,::1,testserver")
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
from app.core.config import settings

settings.auto_create_schema = False
from app.core.database import Base, async_session, engine
from app.core.rate_limit import set_rate_limit_client_factory
from app.deps import cache as cache_module
from app.models import models
from app.models.user_loaders import ensure_mfa_relationships_loaded
from app.services import notification_queue
from app.utils import ratelimit as ratelimit_module

_ASYNCIO_PLUGIN_ACTIVE = False


def pytest_configure(config: pytest.Config) -> None:
    global _ASYNCIO_PLUGIN_ACTIVE
    _ASYNCIO_PLUGIN_ACTIVE = config.pluginmanager.hasplugin("asyncio")
    if _ASYNCIO_PLUGIN_ACTIVE:
        current_mode = getattr(config.option, "asyncio_mode", None)
        if not current_mode or current_mode.lower() == "strict":
            config.option.asyncio_mode = "auto"
    if not _ASYNCIO_PLUGIN_ACTIVE:
        config.addinivalue_line(
            "markers",
            "asyncio: mark test to execute as a coroutine using the event loop fixture",
        )


def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
    if _ASYNCIO_PLUGIN_ACTIVE:
        return None
    if not inspect.iscoroutinefunction(pyfuncitem.obj):
        return None
    if not pyfuncitem.get_closest_marker("asyncio"):
        return None
    loop: asyncio.AbstractEventLoop | None = pyfuncitem.funcargs.get("event_loop")
    if loop is None:
        loop = asyncio.get_event_loop()
    argnames = pyfuncitem._fixtureinfo.argnames  # pylint: disable=protected-access
    kwargs = {name: pyfuncitem.funcargs[name] for name in argnames}
    loop.run_until_complete(pyfuncitem.obj(**kwargs))
    return True


@pytest.fixture(scope="session")
def event_loop() -> AsyncIterator[asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        yield loop
    finally:
        asyncio.set_event_loop(None)
        loop.close()


@pytest.fixture(autouse=True)
async def notification_queue_shutdown() -> AsyncIterator[None]:
    await notification_queue.shutdown_notification_queue()
    try:
        yield
    finally:
        await notification_queue.shutdown_notification_queue()


@pytest.fixture(scope="session", autouse=True)
async def prepare_database() -> AsyncIterator[None]:
    if os.path.exists("test.db"):
        try:
            os.remove("test.db")
        except OSError:
            pass
    if os.path.exists("test.db-journal"):
        try:
            os.remove("test.db-journal")
        except OSError:
            pass

    async with engine.begin() as conn:
        await conn.exec_driver_sql("PRAGMA busy_timeout=5000")
        await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(
            models.NotificationDelivery.__table__.create, checkfirst=True
        )
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(autouse=True)
async def clean_database(prepare_database: None) -> AsyncIterator[None]:
    yield

    attempts = 5
    delay = 0.1
    for attempt in range(1, attempts + 1):
        try:
            async with engine.begin() as conn:
                await conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
                for table in reversed(Base.metadata.sorted_tables):
                    try:
                        await conn.execute(table.delete())
                    except Exception:
                        pass
                await conn.exec_driver_sql("PRAGMA foreign_keys=ON")
            break
        except OperationalError as exc:
            if "database is locked" not in str(exc).lower() or attempt == attempts:
                raise

            logging.warning(
                "SQLite database locked during test cleanup, retrying in %.1fs (attempt %d/%d)",
                delay,
                attempt,
                attempts,
            )
            await asyncio.sleep(delay)
            delay *= 2


@pytest.fixture(scope="session")
def _rate_limit_redis_client() -> AsyncIterator[fakeredis.aioredis.FakeRedis]:
    fake = fakeredis.aioredis.FakeRedis(encoding="utf-8", decode_responses=False)
    set_rate_limit_client_factory(lambda url: fake)
    try:
        yield fake
    finally:
        set_rate_limit_client_factory(None)


@pytest.fixture(autouse=True)
async def configure_rate_limit(
    _rate_limit_redis_client: fakeredis.aioredis.FakeRedis,
) -> AsyncIterator[None]:
    await _rate_limit_redis_client.flushall()
    try:
        yield
    finally:
        await _rate_limit_redis_client.flushall()


@pytest.fixture(autouse=True)
def reset_sensitive_rate_limiter() -> Iterator[None]:
    ratelimit_module.limiter.reset()
    try:
        yield
    finally:
        ratelimit_module.limiter.reset()


@pytest.fixture
def app():
    return main.app


@pytest.fixture
async def async_client(
    monkeypatch: pytest.MonkeyPatch,
    prepare_database: None,
) -> AsyncIterator[httpx.AsyncClient]:
    async def _start_notifications_scheduler(
        *args, **kwargs
    ) -> Callable[[], Awaitable[None]]:
        async def _stop() -> None:
            return None

        return _stop

    monkeypatch.setattr(
        "app.core.lifespan.start_notifications_scheduler",
        _start_notifications_scheduler,
    )

    async def _start_notifications_retention_scheduler(
        *args, **kwargs
    ) -> Callable[[], Awaitable[None]]:
        async def _stop() -> None:
            return None

        return _stop

    monkeypatch.setattr(
        "app.core.lifespan.start_notifications_retention_scheduler",
        _start_notifications_retention_scheduler,
    )

    async def _start_session_cleanup_scheduler(
        *args, **kwargs
    ) -> Callable[[], Awaitable[None]]:
        async def _stop() -> None:
            return None

        return _stop

    monkeypatch.setattr(
        "app.core.lifespan.start_session_cleanup_scheduler",
        _start_session_cleanup_scheduler,
    )

    async def _start_story_cleanup_scheduler(
        *args, **kwargs
    ) -> Callable[[], Awaitable[None]]:
        async def _stop() -> None:
            return None

        return _stop

    monkeypatch.setattr(
        "app.core.lifespan.start_story_cleanup_scheduler",
        _start_story_cleanup_scheduler,
    )

    async def _start_password_reset_cleanup_scheduler(
        *args, **kwargs
    ) -> Callable[[], Awaitable[None]]:
        async def _stop() -> None:
            return None

        return _stop

    monkeypatch.setattr(
        "app.core.lifespan.start_password_reset_cleanup_scheduler",
        _start_password_reset_cleanup_scheduler,
    )

    async def _mock_migrations_current() -> bool:
        return True

    monkeypatch.setattr(main, "_migrations_are_current", _mock_migrations_current)

    transport = httpx.ASGITransport(app=main.app)
    async with LifespanManager(main.app):
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver/api/v1",
            follow_redirects=True,
        ) as client:
            yield client


@pytest.fixture
async def root_client(
    monkeypatch: pytest.MonkeyPatch,
    prepare_database: None,
) -> AsyncIterator[httpx.AsyncClient]:
    """Client for testing root-level endpoints (no /api/v1 prefix)."""

    async def _start_notifications_scheduler(
        *args, **kwargs
    ) -> Callable[[], Awaitable[None]]:
        async def _stop() -> None:
            return None

        return _stop

    monkeypatch.setattr(
        "app.core.lifespan.start_notifications_scheduler",
        _start_notifications_scheduler,
    )

    async def _start_notifications_retention_scheduler(
        *args, **kwargs
    ) -> Callable[[], Awaitable[None]]:
        async def _stop() -> None:
            return None

        return _stop

    monkeypatch.setattr(
        "app.core.lifespan.start_notifications_retention_scheduler",
        _start_notifications_retention_scheduler,
    )

    async def _start_session_cleanup_scheduler(
        *args, **kwargs
    ) -> Callable[[], Awaitable[None]]:
        async def _stop() -> None:
            return None

        return _stop

    monkeypatch.setattr(
        "app.core.lifespan.start_session_cleanup_scheduler",
        _start_session_cleanup_scheduler,
    )

    async def _start_story_cleanup_scheduler(
        *args, **kwargs
    ) -> Callable[[], Awaitable[None]]:
        async def _stop() -> None:
            return None

        return _stop

    monkeypatch.setattr(
        "app.core.lifespan.start_story_cleanup_scheduler",
        _start_story_cleanup_scheduler,
    )

    async def _start_password_reset_cleanup_scheduler(
        *args, **kwargs
    ) -> Callable[[], Awaitable[None]]:
        async def _stop() -> None:
            return None

        return _stop

    monkeypatch.setattr(
        "app.core.lifespan.start_password_reset_cleanup_scheduler",
        _start_password_reset_cleanup_scheduler,
    )

    async def _mock_migrations_current() -> bool:
        return True

    monkeypatch.setattr(main, "_migrations_are_current", _mock_migrations_current)

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


class _TestingRedisCache(cache_module.RedisCache):
    async def _get_client(self):  # type: ignore[override]
        if self._client is None:
            self._client = fakeredis.aioredis.FakeRedis(
                encoding="utf-8", decode_responses=True
            )
        return self._client

    async def invalidate(self, *keys: str) -> None:
        filtered = [str(key) for key in keys if key]
        if not filtered:
            return

        client = await self._get_client()

        # Separate exact keys and patterns
        exact_keys = []
        patterns = []
        for key in filtered:
            if "*" in key:
                patterns.append(key)
            else:
                exact_keys.append(key)

        # Delete exact keys
        if exact_keys:
            await client.delete(*exact_keys)

        # Process patterns using FakeRedis internals
        if patterns:
            # Note: This relies on FakeRedis implementation details (_strings)
            # because it doesn't support scan/keys commands
            all_keys = list(client._strings.keys())
            to_delete = []
            for pattern in patterns:
                # Simple glob matching
                import fnmatch

                matched = fnmatch.filter(all_keys, pattern)
                to_delete.extend(matched)

            if to_delete:
                await client.delete(*to_delete)


@pytest.fixture
async def fake_cache() -> AsyncIterator[_TestingRedisCache]:
    original_enabled = settings.cache_enabled
    settings.cache_enabled = True
    cache_module.set_cache_backend(None)
    cache = _TestingRedisCache(
        url=settings.cache_redis_url,
        default_ttl=settings.cache_default_ttl_seconds,
    )
    cache_module.set_cache_backend(cache)
    try:
        yield cache
    finally:
        await cache.close()
        cache_module.set_cache_backend(None)
        settings.cache_enabled = original_enabled


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

        # Always create SpotifyIntegration for consistency in tests
        if not user.spotify:
            user.spotify = models.SpotifyIntegration()

        await db_session.commit()
        await db_session.refresh(user)
        await ensure_mfa_relationships_loaded(db_session, user)
        return user

    return _factory


@pytest.fixture
async def story_factory(db_session) -> Callable[..., Awaitable[models.Story]]:
    async def _factory(**kwargs) -> models.Story:
        now = dt.datetime.now(dt.UTC)
        defaults = {
            "title": f"Story {uuid.uuid4().hex[:8]}",
            "short_text": "Story body",
            "expires_at": now + dt.timedelta(hours=24),
            "published_at": now,
            "is_active": True,
        }
        defaults.update(kwargs)
        story = models.Story(**defaults)
        db_session.add(story)
        await db_session.commit()
        await db_session.refresh(story)
        return story

    return _factory


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"
