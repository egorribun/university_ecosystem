from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from psycopg.conninfo import conninfo_to_dict
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError
from typer.testing import CliRunner

from app.cli import migrate_passwords
from app.cli.migrate_passwords import _is_bcrypt, app
from tests.integration.test_cli_migrate_passwords_postgres import _sync_conninfo

runner = CliRunner()


def test_is_bcrypt():
    assert _is_bcrypt("$2b$12$somehash...") is True
    assert _is_bcrypt("$2a$10$somehash...") is True
    assert _is_bcrypt("$2y$10$somehash...") is True
    assert _is_bcrypt("argon2id...") is False


@pytest.fixture
def mock_db_session():
    mock_session = AsyncMock()
    mock_session.get_bind = MagicMock()
    mock_session.get_bind.return_value.dialect.name = "sqlite"
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None
    return mock_session


def test_report_no_users(mock_db_session):
    with patch("app.cli.migrate_passwords.async_session", return_value=mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0
        mock_db_session.execute.return_value = mock_result

        result = runner.invoke(app, ["report"])

    assert result.exit_code == 0
    assert "Legacy bcrypt accounts remaining: 0" in result.stdout
    assert "No active legacy bcrypt accounts are currently reported" in result.stdout
    assert "Migration complete" not in result.stdout


def test_report_with_users_is_count_only_by_default(mock_db_session):
    with patch("app.cli.migrate_passwords.async_session", return_value=mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 1
        mock_db_session.execute.return_value = mock_result

        result = runner.invoke(app, ["report"])

    assert result.exit_code == 0
    assert "Legacy bcrypt accounts remaining: 1" in result.stdout
    assert "test@example.com" not in result.stdout
    assert "No records were changed" in result.stdout


def test_report_can_show_only_opaque_ids(mock_db_session):
    with patch("app.cli.migrate_passwords.async_session", return_value=mock_db_session):
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        sample_result = MagicMock()
        sample_result.scalars.return_value.all.return_value = [
            "00000000-0000-0000-0000-000000000001"
        ]
        mock_db_session.execute.side_effect = [count_result, sample_result]

        result = runner.invoke(app, ["report", "--show-ids", "--limit", "1"])

    assert result.exit_code == 0
    assert "00000000-0000-0000-0000-000000000001" in result.stdout
    assert "@" not in result.stdout


def test_report_rejects_negative_limit():
    result = runner.invoke(app, ["report", "--limit", "-1"])
    assert result.exit_code != 0
    assert "zero or positive" in result.output


def test_assert_none_returns_success_when_empty(mock_db_session):
    with patch("app.cli.migrate_passwords.async_session", return_value=mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0
        mock_db_session.execute.return_value = mock_result

        result = runner.invoke(app, ["assert-none"])

    assert result.exit_code == 0
    assert "No active legacy bcrypt accounts" in result.stdout


def test_assert_none_fails_closed_when_rows_remain(mock_db_session):
    with patch("app.cli.migrate_passwords.async_session", return_value=mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 1
        mock_db_session.execute.return_value = mock_result

        result = runner.invoke(app, ["assert-none"])

    assert result.exit_code == 1
    assert "Legacy bcrypt accounts remain: 1" in result.stdout
    mock_db_session.commit.assert_not_called()


_DENIED_OUTPUT = "Legacy inventory authority could not be verified."


def _postgres_session(monkeypatch, session, decisions, *, count=0):
    session.get_bind = MagicMock()
    session.get_bind.return_value.dialect.name = "postgresql"
    remaining = iter(decisions)
    statements = []

    async def execute(statement):
        query = str(
            statement.compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        statements.append(query)
        decision = next(remaining)
        result = MagicMock()
        if "pg_has_role" in query:
            if isinstance(decision, Exception):
                raise decision
            result.scalar_one.return_value = decision
            result.one.return_value = (decision, count)
            result.all.return_value = [(decision, "opaque-user-id" if count else None)]
        else:
            # A separate later inventory statement sees the next authority
            # state, reproducing the check-then-use false-clean gap.
            visible_count = count if decision is True else 0
            result.scalar_one.return_value = visible_count
            result.scalars.return_value.all.return_value = (
                ["opaque-user-id"] if visible_count else []
            )
        return result

    session.execute.side_effect = execute
    monkeypatch.setattr(migrate_passwords, "async_session", lambda: session)
    return statements


@pytest.mark.parametrize("command", ["report", "assert-none"])
@pytest.mark.parametrize("decision", [False, None, 0, 1, "true", "True"])
def test_global_inventory_denies_unverified_postgres_authority(
    monkeypatch, mock_db_session, command, decision
):
    statements = _postgres_session(monkeypatch, mock_db_session, [decision])

    result = runner.invoke(app, [command])

    assert result.exit_code == 2
    assert result.stdout.strip() == _DENIED_OUTPUT
    assert result.stderr == ""
    assert len(statements) == 1
    assert "pg_has_role" in statements[0]
    assert "pg_catalog.to_regrole('ue_rls_bypass')" in statements[0]
    assert "'MEMBER'" in statements[0]
    assert "count(*)" in statements[0]
    mock_db_session.commit.assert_not_called()
    assert migrate_passwords.bypass_rls_ctx.get() is False


@pytest.mark.parametrize("command", ["report", "assert-none"])
@pytest.mark.parametrize("error_type", [SQLAlchemyError, OSError])
def test_global_inventory_redacts_authority_query_failures(
    monkeypatch, mock_db_session, command, error_type
):
    diagnostic = "untrusted database diagnostic"
    statements = _postgres_session(
        monkeypatch, mock_db_session, [error_type(diagnostic)]
    )

    result = runner.invoke(app, [command])

    assert result.exit_code == 2
    assert result.stdout.strip() == _DENIED_OUTPUT
    assert diagnostic not in result.output
    assert len(statements) == 1
    assert migrate_passwords.bypass_rls_ctx.get() is False


@pytest.mark.parametrize("command", ["report", "assert-none"])
@pytest.mark.parametrize("count", [0, 1])
def test_global_inventory_combines_authority_and_count_in_one_statement(
    monkeypatch, mock_db_session, command, count
):
    statements = _postgres_session(
        monkeypatch, mock_db_session, [True, False], count=count
    )

    result = runner.invoke(app, [command])

    assert result.exit_code == (1 if command == "assert-none" and count else 0)
    expected = (
        f"Legacy bcrypt accounts remaining: {count}"
        if command == "report"
        else (
            "Legacy bcrypt accounts remain: 1"
            if count
            else "No active legacy bcrypt accounts found."
        )
    )
    assert expected in result.stdout
    assert len(statements) == 1
    assert "pg_has_role" in statements[0]
    assert "count(*)" in statements[0]
    assert "users.hashed_password" in statements[0]
    mock_db_session.commit.assert_not_called()
    assert migrate_passwords.bypass_rls_ctx.get() is False


def test_global_inventory_rechecks_authority_in_opt_in_sample_statement(
    monkeypatch, mock_db_session
):
    statements = _postgres_session(monkeypatch, mock_db_session, [True, False], count=1)

    result = runner.invoke(app, ["report", "--show-ids", "--limit", "1"])

    assert result.exit_code == 2
    assert result.stdout.strip().endswith(_DENIED_OUTPUT)
    assert "opaque-user-id" not in result.stdout
    assert "Opaque ID sample" not in result.stdout
    assert len(statements) == 2
    assert all("pg_has_role" in statement for statement in statements)
    assert "count(*)" in statements[0]
    assert "LEFT OUTER JOIN" in statements[1]
    assert "users.id" in statements[1]
    assert mock_db_session.__aenter__.await_count == 2
    assert migrate_passwords.bypass_rls_ctx.get() is False


def test_global_inventory_authorized_sample_preserves_projection_and_bound(
    monkeypatch, mock_db_session
):
    statements = _postgres_session(monkeypatch, mock_db_session, [True, True], count=1)

    result = runner.invoke(app, ["report", "--show-ids", "--limit", "1"])

    assert result.exit_code == 0
    assert "opaque-user-id" in result.stdout
    assert len(statements) == 2
    assert "pg_has_role" in statements[1]
    assert "LEFT OUTER JOIN" in statements[1]
    assert "LIMIT 1" in statements[1]
    assert "ORDER BY users.id" in statements[1]
    assert "users.email" not in statements[1]
    assert migrate_passwords.bypass_rls_ctx.get() is False


@pytest.mark.parametrize("command", ["report", "assert-none"])
@pytest.mark.parametrize("error_type", [SQLAlchemyError, OSError])
def test_global_inventory_denies_unavailable_database_binding(
    monkeypatch, mock_db_session, command, error_type
):
    _postgres_session(monkeypatch, mock_db_session, [True])
    diagnostic = "untrusted bind diagnostic"
    mock_db_session.get_bind.side_effect = error_type(diagnostic)

    result = runner.invoke(app, [command])

    assert result.exit_code == 2
    assert result.stdout.strip() == _DENIED_OUTPUT
    assert diagnostic not in result.output
    mock_db_session.execute.assert_not_awaited()
    assert migrate_passwords.bypass_rls_ctx.get() is False


@pytest.mark.parametrize(
    ("rows", "expected_exit"),
    [
        ([], 2),
        ([(True, None)], 0),
        ([(1, None)], 2),
        ([(None, None)], 2),
        ([(True, "opaque-user-id"), (False, None)], 2),
    ],
)
def test_global_inventory_empty_sample_retains_an_authority_result(
    monkeypatch, mock_db_session, rows, expected_exit
):
    statements = _postgres_session(monkeypatch, mock_db_session, [True, True], count=1)
    execute = mock_db_session.execute.side_effect

    async def execute_with_sample(statement):
        result = await execute(statement)
        if "count(*)" not in str(statement):
            result.all.return_value = rows
        return result

    mock_db_session.execute.side_effect = execute_with_sample

    result = runner.invoke(app, ["report", "--show-ids", "--limit", "2"])

    assert result.exit_code == expected_exit
    assert len(statements) == 2
    assert "opaque-user-id" not in result.stdout
    if expected_exit:
        assert result.stdout.strip().endswith(_DENIED_OUTPUT)
        assert "Opaque ID sample" not in result.stdout
    else:
        assert "Opaque ID sample (first 2):" in result.stdout
    assert migrate_passwords.bypass_rls_ctx.get() is False


@pytest.mark.parametrize("error_type", [SQLAlchemyError, OSError])
def test_global_inventory_redacts_sample_query_failures(
    monkeypatch, mock_db_session, error_type
):
    diagnostic = "untrusted sample diagnostic"
    statements = _postgres_session(
        monkeypatch, mock_db_session, [True, error_type(diagnostic)], count=1
    )

    result = runner.invoke(app, ["report", "--show-ids", "--limit", "1"])

    assert result.exit_code == 2
    assert result.stdout.strip().endswith(_DENIED_OUTPUT)
    assert diagnostic not in result.output
    assert "Opaque ID sample" not in result.stdout
    assert len(statements) == 2
    assert migrate_passwords.bypass_rls_ctx.get() is False


@pytest.mark.parametrize("rendered", [False, True], ids=["url-object", "rendered-url"])
def test_preflight_conninfo_preserves_decoded_connection_fields(rendered):
    generated_value = uuid4().hex + "+ space/@:%'\\"
    options = (
        "-c lock_timeout=10s -c statement_timeout=60s "
        "-c idle_in_transaction_session_timeout=60s"
    )
    source = URL.create(
        "postgresql+psycopg",
        username="owned+reader",
        password=generated_value,
        host="127.0.0.1",
        port=5432,
        database="owned+preflight",
        query={
            "options": options,
            "application_name": "owned preflight+probe",
            "connect_timeout": "5",
        },
    )
    actual = conninfo_to_dict(
        _sync_conninfo(
            source.render_as_string(hide_password=False) if rendered else source
        )
    )
    expected = {
        "user": source.username,
        "password": generated_value,
        "host": source.host,
        "port": str(source.port),
        "dbname": source.database,
        **source.query,
    }
    # Keep generated authentication material out of assertion diagnostics.
    fields_match = set(actual) == set(expected) and all(
        actual[key] == value for key, value in expected.items()
    )
    assert fields_match, "Decoded preflight connection fields changed"


def test_preflight_conninfo_rejects_repeated_query_values():
    source = URL.create(
        "postgresql+psycopg",
        host="127.0.0.1",
        database="owned_preflight",
        query={"options": ("-c lock_timeout=10s", "-c statement_timeout=60s")},
    )
    with pytest.raises(ValueError, match="connection query values must be singular"):
        _sync_conninfo(source)
