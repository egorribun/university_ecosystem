"""Password-reset issuance takes the account row lock before touching tokens."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.auth_repository import AuthRepository


async def test_issuance_locks_the_owning_user_row_first(
    db_session: AsyncSession,
    user_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await user_factory()
    statements: list[Any] = []
    execute = db_session.execute

    async def recording_execute(statement: Any, *args: Any, **kwargs: Any) -> Any:
        statements.append(statement)
        return await execute(statement, *args, **kwargs)

    monkeypatch.setattr(db_session, "execute", recording_execute)

    await AuthRepository(db_session).create_password_reset_token(
        user.id, "hash-lock-order", datetime.now(UTC) + timedelta(hours=1)
    )

    first = statements[0].compile()
    assert str(first) == (
        "SELECT users.id \nFROM users \nWHERE users.id = :id_1 FOR UPDATE"
    )
    assert first.params == {"id_1": user.id}
