"""Focused CLI preflight contracts for legacy password inventory."""

from __future__ import annotations

import inspect
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from typer.testing import CliRunner

from app.cli import migrate_passwords
from app.models.users import User

runner = CliRunner()


def test_sql_predicate_filters_before_limit_and_projects_only_ids():
    statement = (
        select(User.id)
        .where(migrate_passwords._bcrypt_predicate())
        .order_by(User.id)
        .limit(1)
    )
    compiled = str(statement.compile(dialect=postgresql.dialect()))

    assert "users.id" in compiled
    assert "users.email" not in compiled
    assert "users.hashed_password" in compiled
    assert compiled.index("LIKE") < compiled.index("LIMIT")


def test_sql_predicate_requires_active_users_and_all_bcrypt_prefixes():
    """The inventory must never include inactive users or non-bcrypt hashes."""

    statement = select(User.id).where(migrate_passwords._bcrypt_predicate())
    compiled = str(
        statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    ).lower()

    assert "users.is_active is true" in compiled
    for prefix in ("$2a$%", "$2b$%", "$2y$%"):
        assert prefix in compiled


def test_cli_has_no_legacy_mutation_or_completion_claims():
    source = inspect.getsource(migrate_passwords)

    for forbidden in (
        "must_reset_password",
        "force-reset",
        "Done.",
        "Migration complete",
    ):
        assert forbidden not in source


@pytest.mark.asyncio
async def test_count_uses_scalar_count_query_and_resets_rls_context():
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.__aexit__.return_value = None
    result = MagicMock()
    result.scalar_one.return_value = 0
    session.execute.return_value = result

    with patch.object(migrate_passwords, "async_session", return_value=session):
        assert await migrate_passwords._count_bcrypt_users() == 0

    assert migrate_passwords.bypass_rls_ctx.get() is False


@pytest.mark.asyncio
async def test_count_executes_a_count_query_with_the_bcrypt_predicate():
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.__aexit__.return_value = None
    result = MagicMock()
    result.scalar_one.return_value = 4
    session.execute.return_value = result

    with patch.object(migrate_passwords, "async_session", return_value=session):
        assert await migrate_passwords._count_bcrypt_users() == 4

    statement = session.execute.await_args.args[0]
    compiled = str(
        statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    ).lower()
    assert "count(*)" in compiled
    assert "users.is_active is true" in compiled
    assert "$2a$%" in compiled


@pytest.mark.asyncio
async def test_count_enables_scoped_rls_bypass_only_during_query():
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.__aexit__.return_value = None
    result = MagicMock()
    result.scalar_one.return_value = 2

    async def execute(_statement):
        assert migrate_passwords.bypass_rls_ctx.get() is True
        return result

    session.execute.side_effect = execute

    with patch.object(migrate_passwords, "async_session", return_value=session):
        assert await migrate_passwords._count_bcrypt_users() == 2

    assert migrate_passwords.bypass_rls_ctx.get() is False


@pytest.mark.asyncio
async def test_count_resets_rls_bypass_when_query_fails():
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.__aexit__.return_value = None
    session.execute.side_effect = RuntimeError("database unavailable")

    with patch.object(migrate_passwords, "async_session", return_value=session):
        with pytest.raises(RuntimeError, match="database unavailable"):
            await migrate_passwords._count_bcrypt_users()

    assert migrate_passwords.bypass_rls_ctx.get() is False


@pytest.mark.asyncio
async def test_report_bcrypt_users_rejects_negative_limit() -> None:
    with pytest.raises(ValueError) as exc_info:
        await migrate_passwords._report_bcrypt_users(limit=-1, show_ids=True)

    assert str(exc_info.value) == "limit must be zero or positive"


@pytest.mark.asyncio
async def test_report_bcrypt_users_zero_limit_skips_database_query() -> None:
    with patch.object(migrate_passwords, "_privileged_session") as session_factory:
        assert (
            await migrate_passwords._report_bcrypt_users(limit=0, show_ids=True) == []
        )

    session_factory.assert_not_called()


@pytest.mark.asyncio
async def test_report_bcrypt_users_is_count_only_by_default() -> None:
    with patch.object(migrate_passwords, "_privileged_session") as session_factory:
        assert await migrate_passwords._report_bcrypt_users(limit=1) == []

    session_factory.assert_not_called()


@pytest.mark.asyncio
async def test_report_bcrypt_users_default_sample_limit_is_fifty() -> None:
    """The operator-facing default must stay bounded at the documented limit."""

    session = AsyncMock()
    session.__aenter__.return_value = session
    session.__aexit__.return_value = None
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session.execute.return_value = result

    with patch.object(migrate_passwords, "async_session", return_value=session):
        assert await migrate_passwords._report_bcrypt_users(show_ids=True) == []

    statement = session.execute.await_args.args[0]
    compiled = str(
        statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "LIMIT 50" in compiled


@pytest.mark.asyncio
async def test_report_bcrypt_users_projects_ids_and_applies_bcrypt_predicate() -> None:
    sample_id = uuid.uuid4()
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.__aexit__.return_value = None
    result = MagicMock()
    result.scalars.return_value.all.return_value = [sample_id]
    session.execute.return_value = result

    with patch.object(migrate_passwords, "async_session", return_value=session):
        assert await migrate_passwords._report_bcrypt_users(limit=1, show_ids=True) == [
            {"id": str(sample_id)}
        ]

    statement = session.execute.await_args.args[0]
    compiled = str(
        statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    ).lower()
    assert "users.id" in compiled
    assert "users.hashed_password" in compiled
    assert "users.is_active is true" in compiled


def test_report_is_count_only_without_explicit_id_opt_in():
    with (
        patch.object(
            migrate_passwords, "_count_bcrypt_users", new=AsyncMock(return_value=3)
        ),
        patch.object(
            migrate_passwords,
            "_report_bcrypt_users",
            new=AsyncMock(side_effect=AssertionError("sample must not be fetched")),
        ),
    ):
        result = runner.invoke(migrate_passwords.app, ["report", "--limit", "1"])

    assert result.exit_code == 0
    assert "Legacy bcrypt accounts remaining: 3" in result.stdout
    assert "No records were changed" in result.stdout


def test_report_show_ids_is_explicit_and_bounded():
    entries = [{"id": "opaque-user-id"}]
    with (
        patch.object(
            migrate_passwords, "_count_bcrypt_users", new=AsyncMock(return_value=3)
        ),
        patch.object(
            migrate_passwords,
            "_report_bcrypt_users",
            new=AsyncMock(return_value=entries),
        ) as sample,
    ):
        result = runner.invoke(
            migrate_passwords.app, ["report", "--show-ids", "--limit", "1"]
        )

    assert result.exit_code == 0
    assert "opaque-user-id" in result.stdout
    sample.assert_awaited_once_with(limit=1, show_ids=True)


def test_assert_none_produces_nonzero_exit_for_remaining_accounts():
    with patch.object(
        migrate_passwords, "_count_bcrypt_users", new=AsyncMock(return_value=1)
    ):
        result = runner.invoke(migrate_passwords.app, ["assert-none"])

    assert result.exit_code == 1
    assert "Legacy bcrypt accounts remain: 1" in result.stdout
