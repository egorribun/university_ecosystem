from __future__ import annotations

import uuid
from collections import deque
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import fakeredis.aioredis
import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

import app.deps.cache as cache_module
import app.services.chat.command_service as command_service
from app.models import Message
from app.repositories.chat_repository import SendReceiptState
from app.schemas.dtos.chat import MessageDTO
from app.services.chat.command_service import ChatMessageDispatcher

_NOW = datetime(2026, 10, 26, 12, tzinfo=UTC)


def _dispatcher(
    user_id: uuid.UUID, chat_id: uuid.UUID
) -> tuple[ChatMessageDispatcher, MagicMock, list[Message], SimpleNamespace]:
    uow = MagicMock()
    uow.session = MagicMock()
    uow.session.get_bind.return_value = SimpleNamespace(
        dialect=SimpleNamespace(default_schema_name="public")
    )
    uow.session.execute = AsyncMock()
    uow.commit = AsyncMock()
    uow.rollback = AsyncMock()

    repository = uow.chats
    chat = SimpleNamespace(id=chat_id)
    repository.get_by_id = AsyncMock(return_value=chat)
    repository.check_participant = AsyncMock(return_value=True)
    repository.get_send_receipt = AsyncMock(return_value=None)
    repository.create_send_receipt = AsyncMock(return_value=_NOW + timedelta(hours=24))
    repository.prune_expired_send_receipts = AsyncMock(return_value=0)
    repository.send_receipt_remaining_seconds = AsyncMock(return_value=86400)
    repository.set_message_rls_user = AsyncMock()
    repository.update_timestamp_by_id = AsyncMock()
    repository.get_last_messages = AsyncMock(return_value={})
    repository.get_message_by_id = AsyncMock()
    repository.add = MagicMock()

    created: list[Message] = []

    async def create_message(message: Message) -> None:
        message.id = uuid.uuid4()
        message.created_at = _NOW
        message.read_status = False
        message.sender = None
        message.attachments = []
        created.append(message)

    repository.create_message = AsyncMock(side_effect=create_message)
    attachment_service = SimpleNamespace(
        process_upload=AsyncMock(), cleanup_files=AsyncMock()
    )
    sender = ChatMessageDispatcher(uow, attachment_service, MagicMock())
    return sender, uow, created, chat


def _receipt_conflict() -> IntegrityError:
    driver_error = RuntimeError("exact chat-send-receipt uniqueness conflict")
    for name, value in (
        ("sqlstate", "23505"),
        ("constraint_name", "uq_chat_send_receipts_chat_user_key"),
        ("table_name", "chat_send_receipts"),
        ("schema_name", "public"),
    ):
        setattr(driver_error, name, value)
    return IntegrityError("INSERT", {}, driver_error)


@pytest.fixture
async def redis(monkeypatch: pytest.MonkeyPatch):
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(
        cache_module, "get_cache_client", AsyncMock(return_value=client)
    )
    monkeypatch.setattr(command_service.ws_manager, "is_online", lambda _user_id: False)
    yield client
    await client.aclose()


async def test_live_public_receipt_without_message_id_returns_retryable_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id, chat_id = uuid.uuid4(), uuid.uuid4()
    sender, uow, _, _ = _dispatcher(user_id, chat_id)
    sender.repository.get_send_receipt = AsyncMock(
        return_value=SendReceiptState(
            message_id=None,
            expires_at=_NOW + timedelta(hours=24),
            observed_at=_NOW,
        )
    )
    cache_client = AsyncMock(
        side_effect=AssertionError("a live receipt is resolved before Redis access")
    )
    monkeypatch.setattr(cache_module, "get_cache_client", cache_client)

    with pytest.raises(HTTPException) as caught:
        await sender.send_message(
            chat_id,
            SimpleNamespace(id=user_id),
            "retry",
            [],
            "en",
            idempotency_key="incomplete-receipt",
        )

    assert caught.value.status_code == 409
    assert caught.value.detail["error"] == "idempotency_in_progress"
    assert caught.value.headers["Retry-After"] == "1"
    sender.repository.get_send_receipt.assert_awaited_once_with(
        chat_id,
        user_id,
        command_service._make_send_receipt_digest(
            chat_id, user_id, "incomplete-receipt"
        ),
    )
    sender.repository.get_message_by_id.assert_not_awaited()
    sender.repository.create_message.assert_not_awaited()
    uow.commit.assert_not_awaited()
    uow.rollback.assert_not_awaited()
    cache_client.assert_not_awaited()


async def test_receipt_conflict_rechecks_membership_before_reading_winner(redis):
    user_id, chat_id = uuid.uuid4(), uuid.uuid4()
    sender, uow, created, chat = _dispatcher(user_id, chat_id)
    membership = deque((True, False))
    events: list[str] = []

    async def check_participant(*_args) -> bool:
        events.append("membership")
        return membership.popleft()

    async def rollback() -> None:
        events.append("rollback")

    sender.repository.get_by_id = AsyncMock(side_effect=(chat, chat))
    sender.repository.check_participant = AsyncMock(side_effect=check_participant)
    sender.repository.create_send_receipt = AsyncMock(side_effect=_receipt_conflict())
    uow.rollback = AsyncMock(side_effect=rollback)

    with pytest.raises(HTTPException) as caught:
        await sender.send_message(
            chat_id,
            SimpleNamespace(id=user_id),
            "losing attempt",
            [],
            "en",
            idempotency_key="membership-revoked",
        )

    assert caught.value.status_code == 403
    assert events == ["membership", "rollback", "membership"]
    sender.repository.get_by_id.assert_has_awaits([call(chat_id), call(chat_id)])
    sender.repository.check_participant.assert_has_awaits(
        [call(chat_id, user_id), call(chat_id, user_id)]
    )
    sender.repository.get_send_receipt.assert_awaited_once()
    sender.repository.get_message_by_id.assert_not_awaited()
    assert len(created) == 1
    uow.commit.assert_not_awaited()
    uow.rollback.assert_awaited_once()
    cache_key = command_service._make_idempotency_key(
        chat_id, user_id, "membership-revoked"
    )
    assert await (await cache_module.get_cache_client()).get(cache_key) is None


async def test_receipt_conflict_replays_live_winner_after_fresh_membership_check(
    redis,
) -> None:
    user_id, chat_id = uuid.uuid4(), uuid.uuid4()
    sender, uow, created, chat = _dispatcher(user_id, chat_id)
    membership_events: list[str] = []

    async def check_participant(*_args) -> bool:
        membership_events.append("membership")
        return True

    async def rollback() -> None:
        membership_events.append("rollback")

    winning_message_id = uuid.uuid4()
    winner = SendReceiptState(
        message_id=winning_message_id,
        expires_at=_NOW + timedelta(hours=24),
        observed_at=_NOW,
    )
    winner_message = MessageDTO(
        id=winning_message_id,
        chat_id=chat_id,
        sender_id=user_id,
        content="committed winner",
        created_at=_NOW,
    )
    sender.repository.get_by_id = AsyncMock(side_effect=(chat, chat))
    sender.repository.check_participant = AsyncMock(side_effect=check_participant)
    sender.repository.get_send_receipt = AsyncMock(side_effect=(None, winner))
    sender.repository.create_send_receipt = AsyncMock(side_effect=_receipt_conflict())
    sender.repository.get_message_by_id = AsyncMock(return_value=winner_message)
    uow.rollback = AsyncMock(side_effect=rollback)

    response = await sender.send_message(
        chat_id,
        SimpleNamespace(id=user_id),
        "losing attempt",
        [],
        "en",
        idempotency_key="receipt-collision",
    )

    assert response.id == winning_message_id
    assert response.content == "committed winner"
    assert membership_events == ["membership", "rollback", "membership"]
    digest = command_service._make_send_receipt_digest(
        chat_id, user_id, "receipt-collision"
    )
    sender.repository.get_send_receipt.assert_has_awaits(
        [call(chat_id, user_id, digest), call(chat_id, user_id, digest)]
    )
    sender.repository.get_message_by_id.assert_awaited_once_with(
        winning_message_id, user_id=user_id, chat_id=chat_id
    )
    assert len(created) == 1
    uow.commit.assert_not_awaited()
    uow.rollback.assert_awaited_once()
    cache_key = command_service._make_idempotency_key(
        chat_id, user_id, "receipt-collision"
    )
    assert await redis.get(cache_key) is None
