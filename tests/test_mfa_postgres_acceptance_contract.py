from __future__ import annotations

import inspect
import os
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import psycopg
import pytest
import yaml
from sqlalchemy.engine import make_url

from tests.integration import test_mfa_email_otp_postgres as acceptance

SOURCE = (
    "postgresql+asyncpg://test:test@localhost:5432/test"  # pragma: allowlist secret
)
# Non-test database names that the provisioning guard must refuse.
PRODUCTION_NAMED_DSN = (
    "postgresql://test:test@localhost/production"  # pragma: allowlist secret
)
LATEST_NAMED_DSN = "postgresql://test:test@localhost/latest"  # pragma: allowlist secret
IDENTITY = UUID("00000000-0000-4000-8000-000000000001")
OWNED = f"test_mfa_{IDENTITY.hex}"
ROOT = Path(__file__).resolve().parents[1]


def test_existing_workflow_provides_isolated_acceptance_authority():
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/reusable-backend-tests.yml").read_text(
            encoding="utf-8"
        )
    )
    environment = workflow["jobs"]["integration-tests"]["env"]
    assert environment["RUN_INTEGRATION_TESTS"] == "1"
    assert environment["ENVIRONMENT"] == "testing"
    assert environment["UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET"] == "1"
    assert make_url(environment["DATABASE_URL"]).get_backend_name() == "postgresql"
    assert make_url(environment["DATABASE_URL"]).database == "test"


def test_existing_integration_lane_requests_acceptance(monkeypatch):
    monkeypatch.delenv("MFA_TEST_POSTGRES_DSN", raising=False)
    monkeypatch.setenv("RUN_INTEGRATION_TESTS", "1")
    requested = getattr(acceptance, "_acceptance_requested", None)
    assert callable(requested), "existing integration opt-in must enable MFA acceptance"
    assert requested()
    skip = next(mark for mark in acceptance.pytestmark if mark.name == "skipif")
    assert skip.args == ("not _acceptance_requested()",)
    assert (
        "mfa_postgres_urls"
        in inspect.signature(
            acceptance.test_postgres_migration_and_two_connection_security_races
        ).parameters
    )


@pytest.mark.parametrize(
    "manual,integration,expected",
    [("", "", False), (SOURCE, "", True), ("", "1", True)],
)
def test_acceptance_opt_in(manual, integration, expected, monkeypatch):
    monkeypatch.setenv("MFA_TEST_POSTGRES_DSN", manual)
    monkeypatch.setenv("RUN_INTEGRATION_TESTS", integration)
    assert acceptance._acceptance_requested() is expected


@pytest.fixture
def provisioning(monkeypatch):
    monkeypatch.delenv("MFA_TEST_POSTGRES_DSN", raising=False)
    monkeypatch.setenv("RUN_INTEGRATION_TESTS", "1")
    monkeypatch.setenv("ENVIRONMENT", "testing")
    monkeypatch.setenv("UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET", "1")
    monkeypatch.setenv("DATABASE_URL", SOURCE)
    monkeypatch.setattr(acceptance, "uuid4", lambda: IDENTITY)
    admin = Mock()
    admin.__enter__ = Mock(return_value=admin)
    admin.__exit__ = Mock(return_value=False)
    connect = Mock(return_value=admin)
    monkeypatch.setattr(acceptance.psycopg, "connect", connect)
    return connect, admin


def _statements(admin):
    return [call.args[0].as_string() for call in admin.execute.call_args_list]


def test_fixture_creates_and_drops_only_owned_database(provisioning):
    connect, admin = provisioning
    with acceptance._postgres_acceptance_urls() as urls:
        assert tuple(make_url(url).drivername for url in urls) == (
            "postgresql+asyncpg",
            "postgresql+psycopg",
        )
        assert all(make_url(url).database == OWNED for url in urls)
        assert os.environ["DATABASE_URL"] == SOURCE
        assert _statements(admin) == [f'CREATE DATABASE "{OWNED}"']
    assert _statements(admin) == [
        f'CREATE DATABASE "{OWNED}"',
        f'DROP DATABASE "{OWNED}" WITH (FORCE)',
    ]
    assert make_url(connect.call_args.args[0]).database == "postgres"
    assert connect.call_args.kwargs == {
        "autocommit": True,
        "connect_timeout": 10,
        "options": "-c lock_timeout=10000 -c statement_timeout=30000",
    }
    admin.__exit__.assert_called_once()
    assert os.environ["DATABASE_URL"] == SOURCE


def test_fixture_registers_owned_lifecycle(provisioning):
    _, admin = provisioning
    fixture = acceptance.mfa_postgres_urls.__wrapped__()
    assert make_url(next(fixture)[0]).database == OWNED
    fixture.close()
    assert _statements(admin)[-1] == f'DROP DATABASE "{OWNED}" WITH (FORCE)'


def test_separate_invocations_have_distinct_owned_names(provisioning, monkeypatch):
    _, admin = provisioning
    identifiers = iter([IDENTITY, UUID("00000000-0000-4000-8000-000000000002")])
    monkeypatch.setattr(acceptance, "uuid4", lambda: next(identifiers))
    targets = []
    for _ in range(2):
        with acceptance._postgres_acceptance_urls() as urls:
            targets.append(make_url(urls[0]).database)
    assert len(set(targets)) == 2
    assert _statements(admin) == [
        statement
        for target in targets
        for statement in (
            f'CREATE DATABASE "{target}"',
            f'DROP DATABASE "{target}" WITH (FORCE)',
        )
    ]


def test_manual_database_is_never_provisioned_or_deleted(provisioning, monkeypatch):
    connect, _ = provisioning
    monkeypatch.setenv("MFA_TEST_POSTGRES_DSN", SOURCE)
    monkeypatch.delenv("RUN_INTEGRATION_TESTS", raising=False)
    monkeypatch.delenv(
        "UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET", raising=False
    )
    with pytest.raises(ValueError, match="test body"):
        with acceptance._postgres_acceptance_urls() as urls:
            assert make_url(urls[0]).database == "test"
            raise ValueError("test body")
    connect.assert_not_called()


@pytest.mark.parametrize(
    "variable,value",
    [
        ("RUN_INTEGRATION_TESTS", ""),
        ("ENVIRONMENT", "production"),
        ("UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET", ""),
        ("DATABASE_URL", ""),
        ("DATABASE_URL", "sqlite:///test.db"),
        ("DATABASE_URL", PRODUCTION_NAMED_DSN),
        ("DATABASE_URL", LATEST_NAMED_DSN),
        ("DATABASE_URL", "postgresql:///test"),
    ],
)
def test_unsafe_provisioning_authority_fails_before_connect(
    variable, value, provisioning, monkeypatch
):
    connect, _ = provisioning
    monkeypatch.setenv(variable, value)
    with pytest.raises(
        (ValueError, RuntimeError),
        match=r"PostgreSQL|integration|testing|reset|test database",
    ):
        with acceptance._postgres_acceptance_urls():
            pytest.fail("unsafe authority must not yield a target")
    connect.assert_not_called()


@pytest.mark.parametrize(
    "dsn",
    [
        "sqlite:///test.db",
        PRODUCTION_NAMED_DSN,
        "postgresql:///test",
    ],
)
def test_manual_override_requires_explicit_postgres_test_database(
    dsn, provisioning, monkeypatch
):
    connect, _ = provisioning
    monkeypatch.setenv("MFA_TEST_POSTGRES_DSN", dsn)
    with pytest.raises(ValueError, match=r"PostgreSQL|test database"):
        with acceptance._postgres_acceptance_urls():
            pytest.fail("invalid manual target must fail")
    connect.assert_not_called()


def test_generated_name_cannot_equal_source_database(provisioning, monkeypatch):
    connect, _ = provisioning
    monkeypatch.setenv("DATABASE_URL", SOURCE.replace("/test", f"/{OWNED}"))
    with pytest.raises(RuntimeError, match="source database"):
        with acceptance._postgres_acceptance_urls():
            pytest.fail("source database must never become an owned target")
    connect.assert_not_called()


@pytest.mark.parametrize(
    "error",
    [
        psycopg.errors.DuplicateDatabase("collision"),
        psycopg.OperationalError("create denied"),
        psycopg.errors.LockNotAvailable("lock timeout"),
        psycopg.errors.QueryCanceled("statement timeout"),
    ],
)
def test_failed_create_never_drops_an_unowned_database(error, provisioning):
    _, admin = provisioning
    admin.execute.side_effect = error
    with pytest.raises(type(error), match=str(error)):
        with acceptance._postgres_acceptance_urls():
            pytest.fail("failed create must not yield")
    assert _statements(admin) == [f'CREATE DATABASE "{OWNED}"']
    admin.__exit__.assert_called_once()


def test_connection_failure_is_not_skipped(provisioning):
    connect, admin = provisioning
    connect.side_effect = psycopg.OperationalError("unreachable")
    with pytest.raises(psycopg.OperationalError, match="unreachable"):
        with acceptance._postgres_acceptance_urls():
            pytest.fail("connection failure must not yield")
    admin.execute.assert_not_called()


def test_body_failure_still_cleans_owned_database(provisioning):
    _, admin = provisioning
    with pytest.raises(ValueError, match="race assertion"):
        with acceptance._postgres_acceptance_urls():
            raise ValueError("race assertion")
    assert _statements(admin)[-1] == f'DROP DATABASE "{OWNED}" WITH (FORCE)'
    admin.__exit__.assert_called_once()


def test_cleanup_failure_is_visible_and_closes_admin_connection(provisioning):
    _, admin = provisioning
    admin.execute.side_effect = [None, psycopg.OperationalError("drop denied")]
    with pytest.raises(psycopg.OperationalError, match="drop denied"):
        with acceptance._postgres_acceptance_urls():
            pass
    admin.__exit__.assert_called_once()


def test_cleanup_failure_keeps_the_original_assertion_in_exception_chain(provisioning):
    _, admin = provisioning
    admin.execute.side_effect = [None, psycopg.OperationalError("drop denied")]
    with pytest.raises(psycopg.OperationalError, match="drop denied") as caught:
        with acceptance._postgres_acceptance_urls():
            raise AssertionError("security race failed")
    assert isinstance(caught.value.__context__, AssertionError)
    assert str(caught.value.__context__) == "security race failed"
    admin.__exit__.assert_called_once()


def test_migration_engine_disposed_on_failure(monkeypatch):
    engine = Mock()
    monkeypatch.setattr(acceptance, "create_engine", lambda _: engine)
    monkeypatch.setattr(
        acceptance,
        "_assert_contract_on_engine",
        Mock(side_effect=ValueError("migration")),
    )
    with pytest.raises(ValueError, match="migration"):
        acceptance._assert_contract_abort_and_lock(SOURCE)
    engine.dispose.assert_called_once()


@pytest.mark.asyncio
async def test_race_engine_disposed_on_failure(monkeypatch):
    engine = Mock(dispose=AsyncMock())
    monkeypatch.setattr(acceptance, "_assert_contract_abort_and_lock", Mock())
    monkeypatch.setattr(acceptance, "create_async_engine", lambda _: engine)
    monkeypatch.setattr(
        acceptance, "_assert_security_races", AsyncMock(side_effect=ValueError("race"))
    )
    with pytest.raises(ValueError, match="race"):
        await acceptance.test_postgres_migration_and_two_connection_security_races(
            (SOURCE, SOURCE)
        )
    engine.dispose.assert_awaited_once()
