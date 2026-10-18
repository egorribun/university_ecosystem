from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.events import AttachmentCleanupRequested
from app.models.enums import UserRole
from app.services.chat.command_service import ChatMaintenanceService


def _message(*urls: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        attachments=[SimpleNamespace(url=url) for url in urls],
    )


def _service(participant_ids: list[uuid.UUID]):
    chat_id = uuid.uuid4()
    admin = SimpleNamespace(id=participant_ids[0], role=UserRole.ADMIN)
    chat = SimpleNamespace(
        id=chat_id,
        participants=[
            SimpleNamespace(id=participant_id) for participant_id in participant_ids
        ],
    )
    uow = MagicMock()
    uow.chats = MagicMock()
    uow.chats.get_by_id = AsyncMock(return_value=chat)
    uow.chats.get_orm_for_update = AsyncMock(return_value=object())
    uow.chats.lock_participant_ids_for_maintenance = AsyncMock(
        return_value=participant_ids
    )
    uow.chats.get_messages = AsyncMock()
    uow.chats.delete_messages = AsyncMock()
    uow.chats.delete_chat = AsyncMock()
    uow.chats.update_timestamp_by_id = AsyncMock()
    uow.chats.add = MagicMock()
    uow.flush = AsyncMock()
    uow.commit = AsyncMock()
    uow.rollback = AsyncMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=False)
    return ChatMaintenanceService(uow, MagicMock()), uow, chat, admin


@pytest.mark.asyncio
async def test_clear_history_pages_with_deleted_cursor_and_chunks_cleanup_urls():
    participant_id = uuid.uuid4()
    service, uow, chat, admin = _service([participant_id])
    urls = [f"https://objects.example.test/{index}" for index in range(130)]
    first_page = [_message(*urls)]
    second_page = [_message("https://objects.example.test/final")]
    uow.chats.get_messages.side_effect = [
        (first_page, True, "cursor-encodes-first-page-tail"),
        (second_page, False, None),
    ]
    uow.chats.delete_messages.side_effect = [1, 1]

    result = await service.clear_history(chat.id, admin, "en")

    assert result.deleted_messages == 2
    assert result.deleted_attachments == 131
    assert result.status == "cleared"
    assert [call.args[1] for call in uow.chats.get_messages.await_args_list] == [
        None,
        "cursor-encodes-first-page-tail",
    ]
    assert all(
        call.kwargs["for_update"] is True
        and call.args[2] == ChatMaintenanceService._MESSAGE_PAGE_SIZE
        for call in uow.chats.get_messages.await_args_list
    )
    assert [call.args[0] for call in uow.chats.delete_messages.await_args_list] == [
        [message.id for message in first_page],
        [message.id for message in second_page],
    ]
    cleanup_events = [
        call.args[0]
        for call in uow.chats.add.call_args_list
        if call.args[0].event_type == AttachmentCleanupRequested.EVENT_TYPE
    ]
    assert [len(event.payload["attachment_urls"]) for event in cleanup_events] == [
        128,
        2,
        1,
    ]
    assert [
        url for event in cleanup_events for url in event.payload["attachment_urls"]
    ] == [*urls, "https://objects.example.test/final"]
    assert uow.flush.await_count == 2
    uow.commit.assert_awaited_once()
    uow.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_clear_history_cancellation_after_page_flush_rolls_back():
    participant_id = uuid.uuid4()
    service, uow, chat, admin = _service([participant_id])
    page = [_message("https://objects.example.test/already-uploaded")]
    uow.chats.get_messages.side_effect = [
        (page, True, "cursor-on-deleted-page"),
        asyncio.CancelledError(),
    ]

    with pytest.raises(asyncio.CancelledError):
        await service.clear_history(chat.id, admin, "en")

    uow.chats.delete_messages.assert_awaited_once_with(
        [page[0].id], chat_id=chat.id, user_id=participant_id
    )
    uow.flush.assert_awaited_once()
    uow.rollback.assert_awaited_once()
    uow.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_clear_history_rolls_back_if_page_cannot_continue():
    participant_id = uuid.uuid4()
    service, uow, chat, admin = _service([participant_id])
    page = [_message()]
    uow.chats.get_messages.return_value = (page, True, None)
    uow.chats.delete_messages.return_value = 1

    with pytest.raises(RuntimeError, match="omitted its next cursor"):
        await service.clear_history(chat.id, admin, "en")

    uow.chats.delete_messages.assert_awaited_once()
    uow.rollback.assert_awaited_once()
    uow.commit.assert_not_awaited()
