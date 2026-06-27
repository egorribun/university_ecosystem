from __future__ import annotations

import secrets
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event

import app.core.ratelimit as ratelimit_module
from app import main
from asgi_lifespan import LifespanManager

# Static CSRF token for test clients — used by both the cookie and the header.
# Using a fixed value keeps debugging simple and removes non-determinism.
_TEST_CSRF_TOKEN: str = secrets.token_urlsafe(32)

_DEFAULT_QUERY_BUDGET: int = 5


class _QueryBudgetListener:
    """Counts SQL statements executed within a single HTTP request boundary.

    WHY: N+1 query regressions are silent in unit tests but catastrophic in
    production.  By counting queries per GET request we create a trip-wire that
    fails the test long before the regression hits staging.

    Usage headers (test clients only):
      X-Query-Budget: <int>  — override the per-request limit for one call
      X-Disable-Query-Budget — disable the check entirely for one call
    """

    def __init__(self, engines: list) -> None:
        # engines is a list of SQLAlchemy SyncEngine instances to instrument.
        self._engines = engines
        self._count: int = 0

    # ── Listener ────────────────────────────────────────────────────────────

    def _on_before_cursor_execute(
        self, conn, cursor, statement, parameters, context, executemany
    ) -> None:
        self._count += 1

    # ── Context manager protocol ─────────────────────────────────────────────

    def __enter__(self) -> _QueryBudgetListener:
        for engine in self._engines:
            sa_event.listen(
                engine, "before_cursor_execute", self._on_before_cursor_execute
            )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        for engine in self._engines:
            if sa_event.contains(
                engine, "before_cursor_execute", self._on_before_cursor_execute
            ):
                sa_event.remove(
                    engine, "before_cursor_execute", self._on_before_cursor_execute
                )

    # ── Assertion helper ─────────────────────────────────────────────────────

    def assert_within_budget(self, budget: int) -> None:
        """Fail the currently-running test if the budget was exceeded."""
        if self._count > budget:
            pytest.fail(
                f"SQL Query Budget exceeded: {self._count} queries executed "
                f"(budget={budget}). Possible N+1 regression. "
                "Use X-Query-Budget header to raise the limit for this test, "
                "or X-Disable-Query-Budget to skip the check."
            )


def _collect_sync_engines() -> list:
    """Return all active SQLAlchemy sync engines for budget instrumentation.

    We import lazily to avoid import-time side effects before the app is
    configured by the test session fixtures.
    """
    try:
        from unittest.mock import Mock

        from app.core.database import engine, read_replica_engine

        engines = []
        # _LazyProxy instances are never None, but their underlying targets
        # will be None if they are not configured/initialized.
        if engine is not None and engine._get_target() is not None:
            sync_eng = engine.sync_engine
            if not isinstance(sync_eng, Mock):
                engines.append(sync_eng)
        if (
            read_replica_engine is not None
            and read_replica_engine._get_target() is not None
        ):
            sync_eng = read_replica_engine.sync_engine
            if not isinstance(sync_eng, Mock):
                engines.append(sync_eng)
        return engines
    except Exception:
        return []


def _build_budget_send(original_send):
    """Wrap an httpx AsyncClient.send method with the query budget gate.

    Only GET requests are checked — mutation requests (POST/PUT/PATCH/DELETE)
    legitimately issue many queries inside a transaction and should not be
    gated the same way.
    """

    async def _budget_guarded_send(request, *args, **kwargs):
        is_read_request = request.method.upper() == "GET"
        budget_disabled = "x-disable-query-budget" in {
            k.lower() for k in request.headers
        }

        if not is_read_request or budget_disabled:
            return await original_send(request, *args, **kwargs)

        # Parse custom budget from header (falls back to default).
        budget_header = request.headers.get("x-query-budget") or request.headers.get(
            "X-Query-Budget"
        )
        budget = (
            int(budget_header) if budget_header is not None else _DEFAULT_QUERY_BUDGET
        )

        engines = _collect_sync_engines()
        listener = _QueryBudgetListener(engines)
        with listener:
            response = await original_send(request, *args, **kwargs)

        # Rotate CSRF token regardless (existing behaviour) then gate queries.
        listener.assert_within_budget(budget)
        return response

    return _budget_guarded_send


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
    manager = LifespanManager(main.app)
    await manager.__aenter__()
    yield main.app  # yield the ASGI app, not the manager
    try:
        await manager.__aexit__(None, None, None)
    except (RuntimeError, ValueError) as exc:
        # Suppress "unable to perform operation on <TCPTransport closed=True>"
        # from httpx/httpcore teardown — known uvloop/asyncio race condition.
        # Also suppress "The future belongs to a different loop than the one
        # specified": surfaces ONLY under mutmut, which calls pytest.main()
        # multiple times in one process (stats -> clean-test -> per-mutant), so
        # session-loop-bound module globals raise at the second run's teardown.
        # NOTE: "different loop" is raised as a *ValueError* (asyncio tasks.py
        # ensure_future), NOT a RuntimeError — so this except MUST include
        # ValueError or it escapes (the message guard below still re-raises every
        # other ValueError). Defense-in-depth: the periodic_scheduler daemon (the
        # primary leaker) is gated out of "testing" in app/core/lifespan.py, so
        # this swallow is dormant for it; it remains a safety net for any future
        # changed-module that pulls a different loop-bound global into the
        # clean-test set. Mirrors the clean_database swallow in
        # tests/fixtures/database/database.py.
        message = str(exc).lower()
        if (
            "tcptransport" not in message
            and "closed" not in message
            and "different loop" not in message
        ):
            raise


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

        # Layer 1: CSRF token rotation — must run on every response.
        original_send = ac.send

        async def _csrf_rotating_send(*args, **kwargs):
            response = await original_send(*args, **kwargs)
            for header in response.headers.get_list("set-cookie"):
                if header.lower().startswith("csrf_token="):
                    new_token = header.split(";")[0].split("=")[1]
                    ac.headers["X-CSRF-Token"] = new_token
            return response

        # Layer 2: SQL Query Budget Gate — wraps the CSRF-rotating send so
        # that each GET request is counted and the test fails fast on N+1s.
        ac.send = _build_budget_send(_csrf_rotating_send)

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

        # Layer 1: CSRF token rotation — must run on every response.
        original_send = ac.send

        async def _csrf_rotating_send(*args, **kwargs):
            response = await original_send(*args, **kwargs)
            for header in response.headers.get_list("set-cookie"):
                if header.lower().startswith("csrf_token="):
                    new_token = header.split(";")[0].split("=")[1]
                    ac.headers["X-CSRF-Token"] = new_token
            return response

        # Layer 2: SQL Query Budget Gate — mirrors the async_client gate.
        ac.send = _build_budget_send(_csrf_rotating_send)

        yield ac
