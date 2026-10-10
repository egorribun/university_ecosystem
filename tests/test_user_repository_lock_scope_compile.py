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


async def _get_statement(*, with_for_update: bool) -> str:
    session = _RecordingSession()
    repository = UserRepository(cast(AsyncDatabaseSession, session))

    if await repository.get(uuid.uuid4(), with_for_update=with_for_update) is not None:
        raise AssertionError("user_get_missing_row_contract")
    if len(session.statements) != 1:
        raise AssertionError("user_get_statement_count_contract")
    return _compiled_sql(session.statements[0])


def _require_nullable_join_context(sql: str) -> None:
    for table_name in (
        "USER_PREFERENCES",
        "SPOTIFY_INTEGRATIONS",
        "USER_PROFILES",
        "USER_EDUCATION_PATHS",
    ):
        if f"LEFT OUTER JOIN {table_name}" not in sql:
            raise AssertionError("user_get_nullable_join_context_contract")


async def test_get_with_for_update_locks_only_users_row() -> None:
    sql = await _get_statement(with_for_update=True)

    _require_nullable_join_context(sql)
    if "FOR UPDATE OF USERS" not in sql:
        raise AssertionError("user_get_for_update_users_scope_contract")


async def test_get_without_for_update_emits_no_lock_clause() -> None:
    sql = await _get_statement(with_for_update=False)

    _require_nullable_join_context(sql)
    if "FOR UPDATE" in sql:
        raise AssertionError("user_get_without_for_update_contract")
