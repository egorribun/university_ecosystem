import os
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Workaround for passlib/bcrypt 4.1+ incompatibility
import bcrypt
import pytest
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

if not hasattr(bcrypt, "__about__"):
    try:
        bcrypt.__about__ = type("about", (object,), {"__version__": bcrypt.__version__})
    except AttributeError:
        # Fallback if __version__ is also missing or other issues
        bcrypt.__about__ = type("about", (object,), {"__version__": "4.0.0"})

# Core settings for tests
os.environ["ENVIRONMENT"] = "testing"
os.environ["DATABASE_URL"] = os.environ.get(
    "DATABASE_URL", "sqlite+aiosqlite:///./test.db"
)
os.environ["SECRET_KEY"] = "test-secret-key-32-characters-long-entropy"
os.environ["ALGORITHM"] = "HS256"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "30"
os.environ["STATIC_DIR"] = "app/test-static"
os.environ["SPOTIFY_TOKEN_SECRET"] = "aN-c6G_Gi7q0E8VnXW0fvkYlCYwH14r2raXI5Qun7Ss="
os.environ["TASKIQ_BROKER_URL"] = "memory://"
os.environ["CACHE_ENABLED"] = "false"
os.environ["ENABLE_OTEL"] = "false"
os.environ["SESSION_STORAGE_BACKEND"] = "redis"
os.environ["RATE_LIMIT_STORAGE_BACKEND"] = "redis"
os.environ["RATE_LIMIT_STORAGE_URI"] = "redis://localhost"
os.environ["RATE_LIMIT_ENABLED"] = "true"
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
    "tests.fixtures.services.service_fixtures",
]


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_element, _compiler, **_kwargs):
    return "TEXT"


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


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
    from _pytest.monkeypatch import MonkeyPatch

    mp = MonkeyPatch()
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
    from app.core.rate_limit import clear_all_rate_limit_memory

    await clear_all_rate_limit_memory()
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
def clear_dependency_overrides():
    """
    Aggressively clear any leftover dependency overrides after each test.
    This prevents AsyncMocks and other test-specific objects from leaking
    into subsequent tests, avoiding RuntimeWarnings during deepcopy.
    """
    from app.main import app

    yield
    app.dependency_overrides.clear()
