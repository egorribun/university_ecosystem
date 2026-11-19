"""Membership lookups must consult both tenant-protected parent tables."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.repositories.chat_repository import ChatRepository


@pytest.mark.asyncio
@pytest.mark.parametrize("visible", [False, True])
async def test_membership_query_joins_rls_protected_chat_and_user(visible):
    db = AsyncMock()
    result = MagicMock()
    result.scalar.return_value = visible
    db.execute.return_value = result
    chat_id, user_id = uuid4(), uuid4()

    assert await ChatRepository(db).check_participant(chat_id, user_id) is visible

    statement = db.execute.await_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "EXISTS" in sql
    assert "JOIN chats ON chats.id = chat_participants.chat_id" in sql
    assert "JOIN users ON users.id = chat_participants.user_id" in sql
    assert chat_id in compiled.params.values()
    assert user_id in compiled.params.values()
