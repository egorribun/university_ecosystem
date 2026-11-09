from __future__ import annotations

import uuid
from typing import cast

from sqlalchemy import Select
from sqlalchemy.dialects import postgresql

from app.core.protocols import AsyncDatabaseSession
from app.models import User
from app.repositories.user_repository import UserRepository


class _ScalarResult:
    def scalars(self) -> _ScalarResult:
        return self

    def first(self) -> None:
        return None


class _RecordingSession:
    def __init__(self) -> None:
        self.statements: list[Select[tuple[User]]] = []

    async def execute(self, statement: Select[tuple[User]]) -> _ScalarResult:
        self.statements.append(statement)
        return _ScalarResult()


def _compiled_sql(statement: Select[tuple[User]]) -> str:
    compiled = statement.compile(dialect=postgresql.dialect())
    return " ".join(str(compiled).upper().split())


_NULLABLE_JOIN_TABLES = (
    "USER_PREFERENCES",
    "SPOTIFY_INTEGRATIONS",
    "USER_PROFILES",
    "USER_EDUCATION_PATHS",
)


async def _get_statement(*, with_for_update: bool) -> tuple[object, int, str]:
    """Run the repository get and return (result, statement count, compiled SQL)."""
    session = _RecordingSession()
    repository = UserRepository(cast(AsyncDatabaseSession, session))

    found = await repository.get(uuid.uuid4(), with_for_update=with_for_update)
    sql = _compiled_sql(session.statements[-1]) if session.statements else ""
    return found, len(session.statements), sql


def _missing_nullable_joins(sql: str) -> list[str]:
    return [
        table_name
        for table_name in _NULLABLE_JOIN_TABLES
        if f"LEFT OUTER JOIN {table_name}" not in sql
    ]


async def test_get_with_for_update_locks_only_users_row() -> None:
    found, statement_count, sql = await _get_statement(with_for_update=True)

    assert found is None
    assert statement_count == 1
    assert _missing_nullable_joins(sql) == []
    assert "FOR UPDATE OF USERS" in sql


async def test_get_without_for_update_emits_no_lock_clause() -> None:
    found, statement_count, sql = await _get_statement(with_for_update=False)

    assert found is None
    assert statement_count == 1
    assert _missing_nullable_joins(sql) == []
    assert "FOR UPDATE" not in sql
