from __future__ import annotations

import secrets
from unittest.mock import MagicMock

import pytest
import pytest_asyncio

import app.core.ratelimit as ratelimit_module
from app import main
from asgi_lifespan import LifespanManager

# Static CSRF token for test clients — used by both the cookie and the header.
# Using a fixed value keeps debugging simple and removes non-determinism.
_TEST_CSRF_TOKEN: str = secrets.token_urlsafe(32)


@pytest_asyncio.fixture(scope="session")
async def _rate_limit_redis_client(mock_global_redis):
    yield mock_global_redis


@pytest_asyncio.fixture(scope="session", autouse=True)
async def configure_rate_limit(_rate_limit_redis_client):
    ratelimit_module.set_rate_limit_client_factory(lambda _: _rate_limit_redis_client)
    # Rate limiting is disabled by default (RATE_LIMIT_ENABLED=false in conftest).
    # Tests that need rate limiting should enable it per-test via monkeypatch.
    yield
    ratelimit_module.set_rate_limit_client_factory(None)


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
    """Client for testing API endpoints (with /api/v1 prefix).

    Pre-configures a CSRF token cookie and the matching X-CSRF-Token header
    so that mutation requests (POST/PUT/PATCH/DELETE) are accepted by the
    CSRFMiddleware without a separate setup step in each test.

    Note: tests that POST to /auth/login via form data (not Bearer) rely on
    this pre-configuration because the login endpoint IS a mutation and CSRF
    protection applies.  Token-based callers (Authorization: Bearer …) bypass
    CSRF automatically; this pre-set is for browser-flow integration tests.
    """
    import httpx

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver/api/v1",
        follow_redirects=True,
        headers={"X-CSRF-Token": _TEST_CSRF_TOKEN},
    ) as ac:
        ac.cookies.set("csrf_token", _TEST_CSRF_TOKEN, domain="testserver.local")

        # Intercept responses to automatically apply rotated CSRF tokens to future requests
        original_send = ac.send

        async def _intercepted_send(*args, **kwargs):
            response = await original_send(*args, **kwargs)
            for header in response.headers.get_list("set-cookie"):
                if header.lower().startswith("csrf_token="):
                    new_token = header.split(";")[0].split("=")[1]
                    ac.headers["X-CSRF-Token"] = new_token
            return response

        ac.send = _intercepted_send

        yield ac


@pytest_asyncio.fixture
async def root_client(app, prepare_database):
    """Client for testing root-level endpoints (no /api/v1 prefix).

    Also pre-configures CSRF token for mutation request compatibility.
    """
    import httpx

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        follow_redirects=True,
        headers={"X-CSRF-Token": _TEST_CSRF_TOKEN},
    ) as ac:
        ac.cookies.set("csrf_token", _TEST_CSRF_TOKEN, domain="testserver.local")

        # Intercept responses to automatically apply rotated CSRF tokens to future requests
        original_send = ac.send

        async def _intercepted_send(*args, **kwargs):
            response = await original_send(*args, **kwargs)
            for header in response.headers.get_list("set-cookie"):
                if header.lower().startswith("csrf_token="):
                    new_token = header.split(";")[0].split("=")[1]
                    ac.headers["X-CSRF-Token"] = new_token
            return response

        ac.send = _intercepted_send

        yield ac
