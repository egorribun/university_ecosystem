from unittest.mock import MagicMock

import pytest
import pytest_asyncio

from app import main
from app.core.config import settings
from app.utils import ratelimit as ratelimit_module
from asgi_lifespan import LifespanManager


@pytest_asyncio.fixture(scope="session")
async def _rate_limit_redis_client(mock_global_redis):
    yield mock_global_redis


@pytest_asyncio.fixture(scope="session", autouse=True)
async def configure_rate_limit(_rate_limit_redis_client):
    ratelimit_module._redis_client = _rate_limit_redis_client
    # Make sure it's enabled for tests that need it
    settings.rate_limit_enabled = True
    yield
    ratelimit_module._redis_client = None


@pytest_asyncio.fixture(autouse=True)
async def reset_sensitive_rate_limiter(_rate_limit_redis_client):
    await _rate_limit_redis_client.flushall()
    yield


@pytest.fixture
def mock_background_tasks(monkeypatch):
    """Mock out background tasks and migrations."""

    def _noop(*args, **kwargs):
        mock = MagicMock()
        mock.stop = lambda: None
        return mock

    monkeypatch.setattr("app.services.notification_queue.start_worker", _noop)
    # Add other mocks from conftest.py...
    yield


@pytest_asyncio.fixture
async def app():
    async with LifespanManager(main.app) as manager:
        yield manager


@pytest_asyncio.fixture
async def async_client(app, prepare_database):
    """Client for testing API endpoints (with /api/v1 prefix)."""
    import httpx

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver/api/v1",
        follow_redirects=True,
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def root_client(app, prepare_database):
    """Client for testing root-level endpoints (no /api/v1 prefix)."""
    import httpx

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        follow_redirects=True,
    ) as ac:
        yield ac
