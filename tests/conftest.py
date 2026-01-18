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

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.compiler import compiles

import fakeredis.aioredis
from asgi_lifespan import LifespanManager

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
os.environ.setdefault("SECRET_KEY", "test-secret-key-32-characters-long-entropy")
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
os.environ.setdefault("CACHE_ENABLED", "false")
os.environ.setdefault("ENABLE_OTEL", "false")
os.environ.setdefault("SESSION_STORAGE_BACKEND", "db")
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


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_element, _compiler, **_kwargs):  # type: ignore[unused-argument]
    return "JSON"


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


@pytest_asyncio.fixture(autouse=True)
async def notification_queue_shutdown() -> AsyncIterator[None]:
    await notification_queue.shutdown_notification_queue()
    try:
        yield
    finally:
        await notification_queue.shutdown_notification_queue()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def prepare_database() -> AsyncIterator[None]:
    database_url = os.environ.get("DATABASE_URL", "")
    is_postgresql = database_url.startswith("postgresql")

    if is_postgresql:
        # For PostgreSQL, tables are created via Alembic migrations in CI
        yield
        return

    # SQLite-specific cleanup and setup
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

    # Tables with composite PKs that are incompatible with SQLite autoincrement
    # We exclude them from create_all and create them separately without composite PK
    partitioned_tables = {
        models.DataAccessLog.__table__.name,
        models.Notification.__table__.name,
        models.NotificationDelivery.__table__.name,
    }

    # Create all tables except partitioned ones
    async with engine.begin() as conn:
        await conn.exec_driver_sql("PRAGMA busy_timeout=5000")
        await conn.exec_driver_sql("PRAGMA journal_mode=WAL")

        # Create non-partitioned tables
        def _create_non_partitioned(connection):
            for table in Base.metadata.sorted_tables:
                if table.name not in partitioned_tables:
                    table.create(connection, checkfirst=True)

        await conn.run_sync(_create_non_partitioned)

        # Create partitioned tables with modified schema (single PK) for SQLite
        # DataAccessLog
        await conn.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS data_access_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                subject_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                resource_type VARCHAR(64) NOT NULL,
                resource_id VARCHAR(128),
                action VARCHAR(64) NOT NULL,
                context JSON,
                ip_address VARCHAR(64),
                user_agent VARCHAR(512),
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                signature VARCHAR(512)
            )
        """
        )

        # Notification
        await conn.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title VARCHAR NOT NULL,
                title_en VARCHAR,
                body TEXT,
                body_en TEXT,
                type VARCHAR,
                url VARCHAR,
                dedupe_key VARCHAR(255),
                read BOOLEAN DEFAULT 0,
                read_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        await conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_notifications_user_created "
            "ON notifications(user_id, created_at)"
        )
        await conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_notifications_dupe_check "
            "ON notifications(user_id, title, url, created_at)"
        )
        await conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_notifications_user_dedupe "
            "ON notifications(user_id, dedupe_key)"
        )

        # NotificationDelivery
        await conn.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS notification_deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                notification_id INTEGER NOT NULL,
                notification_created_at TIMESTAMP NOT NULL,
                channel VARCHAR NOT NULL DEFAULT 'inapp',
                status VARCHAR NOT NULL DEFAULT 'delivered',
                attempted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                delivered_at DATETIME,
                status_code INTEGER,
                detail TEXT,
                FOREIGN KEY (notification_id)
                REFERENCES notifications(id) ON DELETE CASCADE
            )
        """
        )
        await conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_notification_deliveries_notif_channel "
            "ON notification_deliveries(notification_id, channel)"
        )

    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(autouse=True)
async def clean_database(prepare_database: None) -> AsyncIterator[None]:
    yield

    database_url = os.environ.get("DATABASE_URL", "")
    is_postgresql = database_url.startswith("postgresql")

    attempts = 5
    delay = 0.1
    for attempt in range(1, attempts + 1):
        try:
            async with engine.begin() as conn:
                if is_postgresql:
                    # PostgreSQL: use TRUNCATE with CASCADE
                    for table in reversed(Base.metadata.sorted_tables):
                        try:
                            await conn.exec_driver_sql(
                                f'TRUNCATE TABLE "{table.name}" CASCADE'
                            )
                        except Exception:
                            pass
                else:
                    # SQLite: use PRAGMA and DELETE
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
                (
                    "SQLite database locked during test cleanup, retrying in "
                    "%.1fs (attempt %d/%d)"
                ),
                delay,
                attempt,
                attempts,
            )
            await asyncio.sleep(delay)
            delay *= 2
        except RuntimeError as exc:
            # Event loop closed before teardown finalizer completed
            # This happens with uvloop + asyncpg when the transport closes early
            error_message = str(exc).lower()
            if (
                "event loop is closed" in error_message
                or "handler is closed" in error_message
            ):
                logging.debug("Skipping database cleanup: event loop already closed")
                break
            raise


@pytest.fixture(scope="session")
def _rate_limit_redis_client() -> AsyncIterator[fakeredis.aioredis.FakeRedis]:
    fake = fakeredis.aioredis.FakeRedis(encoding="utf-8", decode_responses=False)
    set_rate_limit_client_factory(lambda url: fake)
    try:
        yield fake
    finally:
        set_rate_limit_client_factory(None)


@pytest_asyncio.fixture(autouse=True)
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
def mock_background_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock out all background schedulers and migration checks."""

    async def _noop(*args, **kwargs) -> Callable[[], Awaitable[None]]:
        async def _stop() -> None:
            return None

        return _stop

    # Obsolete patches - functions moved or removed
    # monkeypatch.setattr(
    #     "app.core.lifespan.start_notifications_scheduler",
    #     _noop,
    # )
    # monkeypatch.setattr(
    #     "app.core.lifespan.start_notifications_retention_scheduler",
    #     _noop,
    # )
    # monkeypatch.setattr(
    #     "app.core.lifespan.start_session_cleanup_scheduler",
    #     _noop,
    # )
    # monkeypatch.setattr(
    #     "app.core.lifespan.start_story_cleanup_scheduler",
    #     _noop,
    # )
    # monkeypatch.setattr(
    #     "app.core.lifespan.start_password_reset_cleanup_scheduler",
    #     _noop,
    # )

    async def _mock_migrations_current(conn=None) -> tuple[bool, set[str], set[str]]:
        return True, set(), set()

    monkeypatch.setattr(
        "app.api.health.migrations_are_current", _mock_migrations_current
    )
    monkeypatch.setattr(
        "app.utils.migrations.migrations_are_current", _mock_migrations_current
    )


@pytest_asyncio.fixture
async def async_client(
    mock_background_tasks: None,
    prepare_database: None,
) -> AsyncIterator[httpx.AsyncClient]:
    """Client for testing API endpoints (with /api/v1 prefix)."""
    transport = httpx.ASGITransport(app=main.app)
    async with LifespanManager(main.app):
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver/api/v1",
            follow_redirects=True,
        ) as client:
            yield client


@pytest_asyncio.fixture
async def root_client(
    mock_background_tasks: None,
    prepare_database: None,
) -> AsyncIterator[httpx.AsyncClient]:
    """Client for testing root-level endpoints (no /api/v1 prefix)."""
    transport = httpx.ASGITransport(app=main.app)
    async with LifespanManager(main.app):
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            follow_redirects=True,
        ) as client:
            yield client


@pytest_asyncio.fixture
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


@pytest_asyncio.fixture
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


@pytest_asyncio.fixture
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


@pytest_asyncio.fixture
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
