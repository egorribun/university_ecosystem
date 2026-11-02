"""Contracts for the current owned-baseline MFA harness, without Docker or SQL.

ADR-051 retired migration replay and operator-URL provisioning. Admission is now
an active owned lease, not a URL name/reset flag. These tests exercise the live
lifecycle coroutine and structured races; the owned helper's own tests retain
CREATE receipt/OID/container identity and destructive-cleanup failure coverage.
"""

from __future__ import annotations

import asyncio
import inspect
import runpy
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import UUID

import pytest
import yaml
from sqlalchemy.engine import make_url

from tests.fixtures import owned_baseline_postgres as owned
from tests.integration import test_mfa_email_otp_postgres as acceptance

initialize_database_for_tests = owned.initialize_database_for_tests
prepare_database = owned.prepare_database
clean_database = owned.clean_database
default_database_guard = owned.default_database_guard

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = UUID("00000000-0000-4000-8000-000000000001")


def test_existing_workflow_enables_owned_acceptance_and_watchdog():
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/reusable-backend-tests.yml").read_text()
    )
    lane = workflow["jobs"]["integration-tests"]
    assert lane["env"]["RUN_INTEGRATION_TESTS"] == "1"
    assert any(
        "--timeout-disable-debugger-detection" in step.get("run", "")
        for step in lane["steps"]
    )
    for name in (
        "initialize_database_for_tests",
        "prepare_database",
        "clean_database",
        "default_database_guard",
        "owned_baseline_server",
    ):
        assert getattr(acceptance, name) is getattr(owned, name)
    watchdog = next(mark for mark in acceptance.pytestmark if mark.name == "timeout")
    assert watchdog.args == (300,)
    assert watchdog.kwargs == {"method": "signal", "func_only": False}
    assert set(
        inspect.signature(
            acceptance.test_postgres_baseline_two_connection_security_races
        ).parameters
    ) == {"request"}


@pytest.mark.parametrize(
    "integration,manual,skip",
    [
        ("", "", True),
        ("", "operator", True),
        ("1", "", False),
        ("1", "operator", False),
    ],
)
def test_only_integration_opt_in_enables_acceptance(
    integration, manual, skip, monkeypatch
):
    monkeypatch.setenv("RUN_INTEGRATION_TESTS", integration)
    monkeypatch.setenv("MFA_TEST_POSTGRES_DSN", manual)
    namespace = runpy.run_path(acceptance.__file__)
    marker = next(mark for mark in namespace["pytestmark"] if mark.name == "skipif")
    assert marker.args == (skip,)


@pytest.mark.parametrize("enabled", [False, True])
def test_watchdog_requires_unsuppressible_timeout(enabled):
    request = Mock()
    request.config.getoption.return_value = enabled
    if enabled:
        acceptance.mfa_watchdog.__wrapped__(request)
    else:
        with pytest.raises(AssertionError, match="timeout-disable-debugger-detection"):
            acceptance.mfa_watchdog.__wrapped__(request)
    request.config.getoption.assert_called_once_with(
        "timeout_disable_debugger_detection", False
    )


@pytest.mark.parametrize(
    "unowned",
    [
        None,
        object(),
        "postgresql://localhost/test",
        "postgresql://localhost/production",
    ],
)
def test_real_baseline_rejects_unowned_objects_before_database_or_cleanup(
    unowned, monkeypatch
):
    scratch = Mock(side_effect=AssertionError("must not acquire or drop"))
    monkeypatch.setattr(owned, "_owned_scratch_database", scratch)
    with pytest.raises(owned.OwnedPostgresError, match="lease is required"):
        with owned.committed_baseline(unowned):
            pytest.fail("unowned baseline yielded")
    scratch.assert_not_called()


def test_real_baseline_failed_lease_verification_has_no_database_cleanup(monkeypatch):
    lease = Mock()
    lease.verify.side_effect = owned.OwnedPostgresError("lease is not active")
    server = owned.OwnedPostgres(
        make_url("postgresql://localhost/postgres"), "container", "nonce", lease
    )
    scratch = Mock(side_effect=AssertionError("must not acquire or drop"))
    monkeypatch.setattr(owned, "_owned_scratch_database", scratch)
    with pytest.raises(owned.OwnedPostgresError, match="lease is not active"):
        with owned.committed_baseline(server):
            pytest.fail("inactive lease yielded")
    lease.verify.assert_called_once_with(server)
    scratch.assert_not_called()


@pytest.fixture
def lifecycle(monkeypatch):
    """Fake only external boundaries; execute the actual harness lifecycle."""
    calls = []
    server = object()
    state = SimpleNamespace(
        calls=calls, server=server, enter_error=None, exit_error=None, hook=None
    )
    url = make_url("postgresql+psycopg://localhost/owned_contract").set(
        query={"options": "-c statement_timeout=60s"}
    )

    @contextmanager
    def baseline(candidate):
        assert candidate is server
        if state.enter_error is not None:
            raise state.enter_error
        calls.append("baseline-enter")
        try:
            yield SimpleNamespace(url=url)
        finally:
            calls.append("baseline-exit")
            if state.exit_error is not None:
                raise state.exit_error

    monkeypatch.setattr(owned, "committed_baseline", baseline)
    request = Mock()
    request.getfixturevalue.side_effect = (
        lambda name: server if name == "owned_baseline_server" else []
    )
    connection = Mock()
    admin = Mock()
    admin.begin.return_value = MagicMock(
        __enter__=Mock(return_value=connection), __exit__=Mock(return_value=False)
    )
    admin.dispose.side_effect = lambda: calls.append("admin-dispose")
    admin_factory = Mock(return_value=admin)
    monkeypatch.setattr(acceptance, "create_engine", admin_factory)
    inspector = Mock()
    inspector.get_columns.return_value = [{"name": "token_digest"}]
    inspector.get_table_names.return_value = ["users", "mfa_challenges"]
    monkeypatch.setattr(acceptance, "inspect", Mock(return_value=inspector))

    def listens_for(target, name):
        assert issubclass(target, acceptance.Session)
        assert target is not acceptance.Session
        assert name == "after_begin"

        def register(function):
            state.hook = function
            return function

        return register

    monkeypatch.setattr(acceptance, "event", SimpleNamespace(listens_for=listens_for))
    engine = Mock(dispose=AsyncMock(side_effect=lambda: calls.append("async-dispose")))
    engine_factory = Mock(return_value=engine)
    monkeypatch.setattr(acceptance, "create_async_engine", engine_factory)
    sessions = object()
    session_factory = Mock(return_value=sessions)
    monkeypatch.setattr(acceptance, "async_sessionmaker", session_factory)
    state.request, state.admin, state.connection = request, admin, connection
    state.admin_factory, state.engine_factory = admin_factory, engine_factory
    state.engine, state.sessions, state.session_factory = (
        engine,
        sessions,
        session_factory,
    )
    state.inspector, state.url = inspector, url
    return state


def _database(state):
    return acceptance._mfa_database(
        state.request, user_id=IDENTITY, email="contract@example.invalid", verified=True
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ambient", ["", "sqlite:///operator.db", "postgresql://localhost/production"]
)
async def test_lifecycle_ignores_ambient_urls_and_restores_context(
    lifecycle, monkeypatch, ambient
):
    state = lifecycle
    for variable in (
        "DATABASE_URL",
        "MFA_TEST_POSTGRES_DSN",
        "MIGRATION_ROUNDTRIP_DATABASE_URL",
    ):
        monkeypatch.setenv(variable, ambient)
    tenant_token = acceptance.tenant_id_ctx.set("previous-tenant")
    bypass_token = acceptance.bypass_rls_ctx.set(True)
    try:
        async with _database(state) as (engine, sessions):
            assert (engine, sessions) == (state.engine, state.sessions)
            assert acceptance.tenant_id_ctx.get() != "previous-tenant"
            assert UUID(acceptance.tenant_id_ctx.get())
            assert acceptance.bypass_rls_ctx.get() is False
            assert state.calls == ["baseline-enter", "admin-dispose"]
        assert acceptance.tenant_id_ctx.get() == "previous-tenant"
        assert acceptance.bypass_rls_ctx.get() is True
    finally:
        acceptance.bypass_rls_ctx.reset(bypass_token)
        acceptance.tenant_id_ctx.reset(tenant_token)
    assert state.calls == [
        "baseline-enter",
        "admin-dispose",
        "async-dispose",
        "baseline-exit",
    ]
    state.admin_factory.assert_called_once_with(
        state.url, poolclass=acceptance.NullPool, connect_args={"connect_timeout": 5}
    )
    args, kwargs = state.engine_factory.call_args
    assert args == (state.url.set(drivername="postgresql+asyncpg", query={}),)
    assert kwargs == {
        "poolclass": acceptance.NullPool,
        "hide_parameters": True,
        "connect_args": {
            "timeout": 5,
            "command_timeout": 65,
            "server_settings": {
                "lock_timeout": "10s",
                "statement_timeout": "60s",
                "idle_in_transaction_session_timeout": "60s",
            },
        },
    }
    state.engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", [owned.OwnedPostgresError("unacknowledged CREATE"), OSError("unreachable")]
)
async def test_failed_baseline_acquisition_is_not_skipped_or_cleaned(lifecycle, error):
    lifecycle.enter_error = error
    with pytest.raises(type(error), match=str(error)):
        async with _database(lifecycle):
            pytest.fail("failed acquisition yielded")
    assert lifecycle.calls == []
    lifecycle.admin_factory.assert_not_called()
    lifecycle.engine_factory.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stage", ["begin", "execute", "inspect", "dispose", "async-create"]
)
async def test_setup_failures_dispose_only_acquired_engines(lifecycle, stage):
    state = lifecycle
    failure = ValueError("setup failed")
    target = {
        "begin": state.admin.begin,
        "execute": state.connection.execute,
        "inspect": state.inspector.get_columns,
        "dispose": state.admin.dispose,
        "async-create": state.engine_factory,
    }[stage]
    target.side_effect = failure
    with pytest.raises(ValueError, match="setup failed"):
        async with _database(state):
            pytest.fail("failed setup yielded")
    state.admin.dispose.assert_called_once()
    state.engine.dispose.assert_not_awaited()
    assert state.calls[-1] == "baseline-exit"
    if stage != "async-create":
        state.engine_factory.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", [AssertionError("race failed"), asyncio.CancelledError()]
)
async def test_body_failure_and_cancellation_dispose_before_owned_cleanup(
    lifecycle, failure
):
    previous = (acceptance.tenant_id_ctx.get(), acceptance.bypass_rls_ctx.get())
    with pytest.raises(type(failure)):
        async with _database(lifecycle):
            raise failure
    assert lifecycle.calls == [
        "baseline-enter",
        "admin-dispose",
        "async-dispose",
        "baseline-exit",
    ]
    assert (acceptance.tenant_id_ctx.get(), acceptance.bypass_rls_ctx.get()) == previous


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["async-dispose", "baseline-exit"])
async def test_cleanup_failure_is_visible_preserves_body_and_restores_context(
    lifecycle, stage
):
    state = lifecycle
    if stage == "async-dispose":
        state.engine.dispose.side_effect = OSError("cleanup failed")
    else:
        state.exit_error = OSError("cleanup failed")
    previous = (acceptance.tenant_id_ctx.get(), acceptance.bypass_rls_ctx.get())
    with pytest.raises(OSError, match="cleanup failed") as caught:
        async with _database(state):
            raise AssertionError("security race failed")
    assert isinstance(caught.value.__context__, AssertionError)
    assert str(caught.value.__context__) == "security race failed"
    state.engine.dispose.assert_awaited_once()
    assert state.calls[-1] == "baseline-exit"
    assert (acceptance.tenant_id_ctx.get(), acceptance.bypass_rls_ctx.get()) == previous


@pytest.mark.asyncio
async def test_private_listener_uses_current_context_not_captured_tenant(lifecycle):
    state = lifecycle
    async with _database(state):
        connection = Mock()
        connection.dialect.name = "postgresql"
        role_sql = str(state.connection.execute.call_args_list[0].args[0])
        role = role_sql.split('"')[1]
        connection.execute.return_value.one.return_value = (role, False, False, False)
        token = acceptance.tenant_id_ctx.set("")
        try:
            state.hook(None, None, connection)
        finally:
            acceptance.tenant_id_ctx.reset(token)
        statements = [str(call.args[0]) for call in connection.execute.call_args_list]
        assert statements[0] == f'SET LOCAL ROLE "{role}"'
        assert "set_config('app.current_tenant', '', true)" in statements[1]
        assert "pg_has_role(current_user, 'ue_rls_bypass', 'MEMBER')" in statements[-1]
        connection.execute.return_value.one.return_value = (role, False, True, False)
        with pytest.raises(AssertionError):
            state.hook(None, None, connection)


@pytest.mark.asyncio
async def test_actual_race_failure_cancels_and_drains_sibling_before_return():
    started = asyncio.Event()
    drained = []

    async def sibling():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)
            drained.append(True)

    async def fail():
        await started.wait()
        raise ValueError("race child failed")

    with pytest.raises(ExceptionGroup) as caught:
        await asyncio.wait_for(acceptance._race(sibling(), fail()), timeout=2)
    assert len(caught.value.exceptions) == 1
    assert isinstance(caught.value.exceptions[0], ValueError)
    assert drained == [True]


@pytest.mark.asyncio
async def test_actual_race_parent_cancellation_drains_every_child():
    started = asyncio.Barrier(3)
    drained = []

    async def child(index):
        try:
            await started.wait()
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)
            drained.append(index)

    task = asyncio.create_task(acceptance._race(child(1), child(2)))
    try:
        await asyncio.wait_for(started.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=2)
        assert sorted(drained) == [1, 2]
    finally:
        if not task.done():
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=2)


@pytest.mark.asyncio
async def test_race_preserves_ordered_results_and_finite_deadline(monkeypatch):
    actual_timeout = asyncio.timeout
    deadlines = []

    def timeout(seconds):
        deadlines.append(seconds)
        return actual_timeout(seconds)

    monkeypatch.setattr(
        acceptance,
        "asyncio",
        SimpleNamespace(timeout=timeout, TaskGroup=asyncio.TaskGroup),
    )

    async def result(value):
        await asyncio.sleep(0)
        return value

    assert await acceptance._race(result(True), result(False)) == [True, False]
    assert deadlines == [75]


@pytest.mark.asyncio
async def test_race_deadline_cancels_and_drains_children(monkeypatch):
    actual_timeout = asyncio.timeout
    deadlines = []
    drained = []

    def timeout(seconds):
        deadlines.append(seconds)
        return actual_timeout(0.01)

    monkeypatch.setattr(
        acceptance,
        "asyncio",
        SimpleNamespace(timeout=timeout, TaskGroup=asyncio.TaskGroup),
    )

    async def child(index):
        try:
            await asyncio.Event().wait()
        finally:
            drained.append(index)

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(acceptance._race(child(1), child(2)), timeout=2)
    assert deadlines == [75]
    assert sorted(drained) == [1, 2]
