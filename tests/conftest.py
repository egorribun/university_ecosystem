import os
import sys
from pathlib import Path
from typing import Any, cast

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Pre-register magic as unavailable to prevent libmagic.dll hang on Windows.
# python-magic is installed but libmagic.dll may be missing; without this guard
# `import magic` blocks indefinitely (instead of raising ImportError).
if "magic" not in sys.modules:
    sys.modules["magic"] = None  # type: ignore[assignment]

import pytest
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

# Core settings for tests
os.environ["ENVIRONMENT"] = "testing"
worker_id = os.environ.get("PYTEST_XDIST_WORKER")
if worker_id:
    # Use unique database per worker for parallel testing
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///./test_{worker_id}.db"
else:
    os.environ["DATABASE_URL"] = os.environ.get(
        "DATABASE_URL", "sqlite+aiosqlite:///./test.db"
    )
os.environ["SECRET_KEY"] = "test-secret-key-32-characters-long-entropy"
os.environ["ALGORITHM"] = "HS256"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "30"
os.environ["STATIC_DIR"] = "app/test-static"
os.environ["SPOTIFY_TOKEN_SECRET"] = "aN-c6G_Gi7q0E8VnXW0fvkYlCYwH14r2raXI5Qun7Ss="
os.environ["SPOTIFY_OAUTH_STATE_SECRET"] = (
    "aN-c6G_Gi7q0E8VnXW0fvkYlCYwH14r2raXI5Qun7Ss="
)
os.environ["CACHE_ENABLED"] = "false"
os.environ["ENABLE_OTEL"] = "false"
os.environ["SESSION_STORAGE_BACKEND"] = "redis"
os.environ["RATE_LIMIT_STORAGE_BACKEND"] = "memory"
os.environ["RATE_LIMIT_STORAGE_URI"] = "redis://localhost"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["RATE_LIMIT_NEWS"] = "5/minute"
os.environ["RATE_LIMIT_AUTH_REGISTER"] = "4/minute"
os.environ["RATE_LIMIT_AUTH_PASSWORD_RESET"] = "4/minute"
os.environ["IMGPROXY_KEY"] = ""
os.environ["IMGPROXY_SALT"] = ""

Path(os.environ.get("STATIC_DIR", "app/test-static")).mkdir(parents=True, exist_ok=True)

# Load modular fixtures
pytest_plugins = [
    "tests.fixtures.database.database",
    "tests.fixtures.infrastructure.infrastructure",
    "tests.fixtures.auth.auth_fixtures",
    "tests.fixtures.auth.mfa_fixtures",
    "tests.fixtures.services.service_fixtures",
    "tests.fixtures.services.notification_fixtures",
    "tests.fixtures.services.websocket_fixtures",
]


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_element, _compiler, **_kwargs):
    return "TEXT"


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session", autouse=True)
def initialize_database_for_tests():
    """
    Initialize the database engine for the test session.
    Must run after environment variables are set.
    """
    from app.core.database import init_database

    init_database()


@pytest.fixture(scope="session", autouse=True)
def mock_global_redis(monkeypatch_session):
    """
    Global session-scoped fixture to redirect all Redis connections to fakeredis.
    This prevents 'Error 22' connection errors during test startup.
    """
    import fakeredis.aioredis
    from redis.asyncio import Redis as AsyncRedis

    # Create a shared fake client for the session
    fake_client = fakeredis.aioredis.FakeRedis(decode_responses=True)

    # Stable lock implementation to avoid AsyncMock/deepcopy RuntimeWarnings
    class SimpleAsyncLock:
        async def acquire(self, *args, **kwargs):
            return True

        async def release(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args, **kwargs):
            pass

    from unittest.mock import MagicMock

    import redis.asyncio.client

    fake_lock = SimpleAsyncLock()

    # Monkeypatch the Redis constructor to return our fake client
    monkeypatch_session.setattr(
        AsyncRedis, "from_url", lambda *args, **kwargs: fake_client
    )
    # Also patch the class itself if used as a constructor
    monkeypatch_session.setattr(
        redis.asyncio.client, "Redis", lambda *args, **kwargs: fake_client
    )

    fake_client.lock = MagicMock(return_value=fake_lock)

    return fake_client


@pytest.fixture(scope="session", autouse=True)
def monkeypatch_session():
    """Helper fixture to provide monkeypatch at session scope."""
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


@pytest.fixture(autouse=True)
def mock_cache_backend(monkeypatch, mock_global_redis):
    """Ensure the global cache backend uses the fake redis client."""
    from tests.fixtures.services.service_fixtures import _TestingRedisCache

    # Create a wrapper that uses our shared fake client
    mock_cache = _TestingRedisCache(url="redis://localhost", default_ttl=60)
    mock_cache._client = mock_global_redis

    monkeypatch.setattr("app.deps.cache._cache_backend", mock_cache)
    return mock_cache


@pytest.fixture(autouse=True)
async def clear_redis_between_tests(mock_global_redis):
    """
    Clear the shared FakeRedis instance and in-memory rate limiters before each test.
    This prevents rate limits and cache data from leaking between tests.
    """
    await mock_global_redis.flushall()
    from app.core.ratelimit import clear_delay_memory, clear_memory_state

    clear_memory_state()
    clear_delay_memory()
    yield


@pytest.fixture(autouse=True)
def link_read_db_to_write_db():
    """
    Ensure get_read_db uses the same dependency as get_db during tests.
    This allows tests that override get_db to automatically cover get_read_db,
    preventing issues where read-only endpoints use a different (empty) session.
    """
    from app.core.database import get_db, get_read_db
    from app.main import app

    app.dependency_overrides[get_read_db] = get_db
    yield
    # We carefully remove the override only if it matches our redirection
    current = app.dependency_overrides.get(get_read_db)
    if current == get_db:
        del app.dependency_overrides[get_read_db]


@pytest.fixture(autouse=True)
def _reset_settings_cached_properties():
    """Pop settings @cached_property caches before each test (defense-in-depth).

    pydantic v2 does NOT invalidate a @cached_property (e.g.
    ``event_file_allowed_mime_types_set``) when its underlying RAW field
    (``event_file_allowed_mime_types``) is reassigned. In a shared in-process
    session — mutmut's clean-test runs the changed-modules covering subset in ONE
    pytest process; pytest-xdist within a worker; etc. — a stale derived value could
    otherwise leak across tests: a prior PDF-upload test caches {'application/pdf'},
    then a later text/plain test monkeypatches the raw field but save_attachment
    still reads the stale set. Popping the cached_property entries (identified via the
    class MRO, so pydantic FIELDS are never touched) forces every derived value to
    recompute from the current (monkeypatched-or-default) raw field.

    NOTE: the actual upload-415 seen in mutmut's clean-test was a DIFFERENT root cause
    — six event-upload tests overrode the derived sets via an unrestored
    ``type(settings).event_file_allowed_mime_types_set = property(...)`` CLASS
    mutation that leaked into every later test (fixed by switching them to
    ``monkeypatch.setattr`` in test_event_file_upload.py). That leak rebinds the
    attribute to a plain ``property`` object, which this fixture's
    ``isinstance(..., functools.cached_property)`` enumeration intentionally skips —
    so this fixture is retained purely as defense-in-depth against the genuine
    @cached_property-staleness sub-case, not as the upload-415 fix.
    """
    import functools

    from app.core.config import settings

    cached_names = [
        name
        for klass in type(settings).__mro__
        for name, attr in vars(klass).items()
        if isinstance(attr, functools.cached_property)
    ]
    for name in cached_names:
        settings.__dict__.pop(name, None)
    yield


@pytest.fixture(autouse=True)
def mock_nats_broker(monkeypatch):
    """Mock the NATS broker so tests using LifespanManager don't hang on connect()."""
    from app.core.nats_broker import broker

    async def mock_connect(*args, **kwargs):
        pass

    async def mock_close(*args, **kwargs):
        pass

    async def mock_run_worker(*args, **kwargs):
        import asyncio

        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass

    async def mock_enqueue(*args, **kwargs):
        return "mocked_task_id"

    monkeypatch.setattr(broker, "connect", mock_connect)
    monkeypatch.setattr(broker, "close", mock_close)
    monkeypatch.setattr(broker, "run_worker", mock_run_worker)
    monkeypatch.setattr(broker, "enqueue", mock_enqueue)


@pytest.fixture(autouse=True)
def mock_health_checks(monkeypatch):
    """
    Mock health check probes that require external infrastructure (SpiceDB, etc.)
    to prevent 503 Service Unavailable errors in integration tests.
    """

    async def mock_spicedb_health(*args, **kwargs):
        return "ok", 0.0

    monkeypatch.setattr("app.core.health.check_spicedb_health", mock_spicedb_health)

    async def mock_wait_db(*args, **kwargs):
        return None

    monkeypatch.setattr("app.api.health.wait_db", mock_wait_db)
    from app.api.health import reset_shutdown_flag

    reset_shutdown_flag()
    yield


@pytest.fixture(autouse=True)
def mock_spicedb_permissions():
    """
    Global mock for SpiceDB permissions to prevent 503 errors in integration tests.
    Returns True for all permission checks if user.role == 'admin'.
    """
    from unittest.mock import AsyncMock, MagicMock

    from app.auth.rbac import PermissionChecker
    from app.main import app

    mock_checker = MagicMock(spec=PermissionChecker)

    async def mock_check_admin(user_id: str, *, user: Any = None) -> bool:
        if user and hasattr(user, "role"):
            return cast(bool, user.role == "admin")
        return True  # Default fallback for legacy calls

    async def mock_check_permission(
        resource_type, resource_id, permission, user_id
    ) -> bool:
        return True

    mock_checker.check_admin = AsyncMock(side_effect=mock_check_admin)
    mock_checker.check_permission = AsyncMock(side_effect=mock_check_permission)

    from app.api.deps.auth import get_permission_checker

    app.dependency_overrides[get_permission_checker] = lambda: mock_checker
    yield mock_checker


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    """
    Clear ONLY the dependency overrides that were added by the CURRENT test.
    RZ-3: The previous implementation called app.dependency_overrides.clear(),
    which destroyed session-scoped permanent overrides installed by fixtures like
    link_read_db_to_write_db and mock_spicedb_permissions. Those session-scoped
    fixtures register their overrides ONCE for the entire test session, but
    clear() wiped them after every test, making subsequent tests use the real
    (unavailable) read-replica and real SpiceDB, causing non-deterministic failures.
    """
    from app.main import app

    # Snapshot the keys of overrides that are already installed (from session-scoped fixtures).
    _permanent_keys = set(app.dependency_overrides.keys())
    yield
    # Remove only test-specific overrides, leaving permanent session-scoped ones intact.
    for key in list(app.dependency_overrides.keys()):
        if key not in _permanent_keys:
            del app.dependency_overrides[key]


# ---------------------------------------------------------------------------
# PERF-14-03 (audit 2026-03-23): Reusable N+1 query detection fixture.
#
# Usage:
#   async def test_get_chats_query_count(client, auth_headers, assert_max_queries):
#       async with assert_max_queries(3):
#           resp = await client.get("/chats", headers=auth_headers)
#       assert resp.status_code == 200
#
# The fixture attaches a SQLAlchemy before_cursor_execute listener to the
# synchronous engine underlying the test's AsyncSession and fails the test if
# more than max_count queries were issued inside the context block.
#
# Why listen on the sync engine?  SQLAlchemy fires before_cursor_execute on the
# sync dialect layer — which all async sessions delegate to internally.  This is
# the same approach used by the existing _count_queries() helper in
# test_notifications_service.py and test_event_time_constraints.py, promoted
# here as a globally-available fixture so every test file can use it without
# copy-pasting the boilerplate.
# ---------------------------------------------------------------------------
@pytest.fixture
def assert_max_queries(db_session):
    """Return an async context manager that fails if more than N SQL queries are issued.

    Args:
        db_session: Injected by pytest from tests/fixtures/database/database.py.

    Example::

        async def test_list_users_query_count(client, auth_headers, assert_max_queries):
            async with assert_max_queries(2):
                resp = await client.get("/users", headers=auth_headers)
            assert resp.status_code == 200
    """
    from contextlib import asynccontextmanager

    from sqlalchemy import event

    @asynccontextmanager
    async def _check(max_count: int):
        queries: list[str] = []

        engine = getattr(db_session, "bind", None)
        if engine is None:
            # No engine bound (e.g. pure-unit test without DB) — skip counting.
            yield queries
            return

        sync_engine = engine.sync_engine

        def _before_execute(_conn, _cursor, statement, _params, _ctx, _many) -> None:
            queries.append(statement)

        event.listen(sync_engine, "before_cursor_execute", _before_execute)
        try:
            yield queries
        finally:
            event.remove(sync_engine, "before_cursor_execute", _before_execute)
            if len(queries) > max_count:
                query_list = "\n".join(
                    f"  [{i + 1}] {q[:300]}" for i, q in enumerate(queries)
                )
                pytest.fail(
                    f"Expected ≤{max_count} SQL queries, got {len(queries)}:\n{query_list}"
                )

    return _check


# ---------------------------------------------------------------------------
# SQL Query Logger for DB Performance Gate (Task 1)
# ---------------------------------------------------------------------------
from sqlalchemy import Engine, event

_logged_queries: set[str] = set()


@event.listens_for(Engine, "before_cursor_execute")
def _log_query_before_execute(
    conn, cursor, statement, parameters, context, executing_many
):
    stmt_upper = statement.strip().upper()
    if not any(
        stmt_upper.startswith(kw)
        for kw in ("SELECT", "INSERT", "UPDATE", "DELETE", "WITH")
    ):
        return

    normalized_stmt = " ".join(statement.split())
    if normalized_stmt in _logged_queries:
        return
    _logged_queries.add(normalized_stmt)

    worker_id = os.environ.get("PYTEST_XDIST_WORKER")
    log_suffix = f"_{worker_id}" if worker_id else ""
    log_path = Path(PROJECT_ROOT) / f"tests/queries{log_suffix}.log"

    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(normalized_stmt + "\n")
    except Exception:  # noqa: S110
        pass


@pytest.fixture(autouse=True)
async def cleanup_asyncio_tasks():
    """Cancel all running tasks except the current one to prevent hangs/leaks."""
    yield
    import asyncio

    current_task = asyncio.current_task()
    tasks = [t for t in asyncio.all_tasks() if t is not current_task]
    if tasks:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
