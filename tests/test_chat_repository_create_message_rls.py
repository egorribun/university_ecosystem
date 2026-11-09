"""create_message binds the sender's RLS identity before the INSERT.

The messages_participant_isolation policy also checks INSERT on PostgreSQL, so a
plain send (no Idempotency-Key) must bind app.current_user_id in the same
transaction before the flush. The real-role proof lives in
tests/integration/test_chat_send_nosuperuser_rls_postgres.py.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import app.repositories.chat_repository as chat_module
from app.models.chat import Message
from app.repositories.chat_repository import ChatRepository

CHAT_ID = uuid.UUID("019c1468-f495-7980-9ad0-d8f31705df79")
SENDER_ID = uuid.UUID("019c1468-f495-7980-9ad0-d8f31705df7a")


class _FakeMessageDTO:
    @classmethod
    def model_validate(cls, value: object) -> tuple[str, object]:
        return ("message-dto", value)


def _repo(dialect: str) -> tuple[ChatRepository, MagicMock, list[str]]:
    """Return a repository whose session records the order of database calls."""
    order: list[str] = []
    db = MagicMock()

    async def execute(statement: object, parameters: object = None) -> MagicMock:
        order.append("execute")
        return MagicMock()

    async def flush() -> None:
        order.append("flush")

    db.execute = AsyncMock(side_effect=execute)
    db.flush = AsyncMock(side_effect=flush)
    db.add = MagicMock(side_effect=lambda _instance: order.append("add"))
    db.in_transaction.return_value = True
    db.get_bind.return_value.dialect.name = dialect
    return ChatRepository(db), db, order


async def test_create_message_binds_sender_before_insert_on_postgresql() -> None:
    repo, db, order = _repo("postgresql")
    message = Message(chat_id=CHAT_ID, sender_id=SENDER_ID, content="hello")

    with patch.object(chat_module, "MessageDTO", _FakeMessageDTO):
        await repo.create_message(message)

    assert order == ["execute", "add", "flush"]
    db.add.assert_called_once_with(message)
    statement, parameters = db.execute.await_args.args
    assert "set_config('app.current_user_id'" in str(statement)
    assert parameters == {"uid": str(SENDER_ID)}


async def test_create_message_skips_identity_binding_off_postgresql() -> None:
    repo, db, order = _repo("sqlite")
    message = Message(chat_id=CHAT_ID, sender_id=SENDER_ID, content="hello")

    with patch.object(chat_module, "MessageDTO", _FakeMessageDTO):
        await repo.create_message(message)

    db.execute.assert_not_awaited()
    assert order == ["add", "flush"]
