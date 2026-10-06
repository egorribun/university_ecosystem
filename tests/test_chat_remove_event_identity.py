from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock, call

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import ChatParticipantRemoved
from app.models.domain_events import StoredEvent
from app.models.users import User
from app.repositories.chat_repository import ChatRepository
from app.repositories.unit_of_work import uow_from_session
from app.services.chat.attachment_service import ChatAttachmentService
from app.services.chat.command_service import ChatMaintenanceService
from app.services.event_handlers import handle_chat_participant_removed


@pytest.mark.asyncio
async def test_remove_group_member_reuses_persisted_outbox_event_id(
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await user_factory()
    member = await user_factory()
    repository = ChatRepository(db_session)
    chat = await repository.create_group(owner, "event-identity", [member])
    await db_session.commit()

    invalidate_ws_hub = AsyncMock(side_effect=ConnectionError("test transport failure"))
    monkeypatch.setattr(
        "app.services.chat.command_service.invalidate_chat_participants_cache",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.services.chat.command_service.invalidate_presence_audience_cache",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.services.ws_hub_client.invalidate_ws_hub_cache", invalidate_ws_hub
    )
    service = ChatMaintenanceService(
        uow_from_session(db_session), ChatAttachmentService()
    )

    await service.remove_participant(chat.id, owner, member.id, "en")

    result = await db_session.execute(
        select(StoredEvent).where(
            StoredEvent.event_type == ChatParticipantRemoved.EVENT_TYPE,
            StoredEvent.aggregate_type == "Chat",
            StoredEvent.aggregate_id == str(chat.id),
        )
    )
    events = list(result.scalars().all())
    assert len(events) == 1
    stored_event = events[0]
    assert isinstance(stored_event.id, uuid.UUID)
    assert stored_event.payload == {
        "chat_id": str(chat.id),
        "user_id": str(member.id),
    }
    assert await repository.check_participant(chat.id, member.id) is False

    eviction_args = (str(member.id), str(chat.id))
    persisted_event_id = str(stored_event.id)
    assert invalidate_ws_hub.await_args_list == [
        call(*eviction_args, evict_room=True, event_id=persisted_event_id)
    ]

    # The durable outbox retry must use the same identity as the immediate eviction.
    invalidate_ws_hub.side_effect = None
    await handle_chat_participant_removed(
        ChatParticipantRemoved(
            chat_id=chat.id,
            user_id=member.id,
            event_id=persisted_event_id,
        )
    )
    assert invalidate_ws_hub.await_args_list == [
        call(*eviction_args, evict_room=True, event_id=persisted_event_id),
        call(
            *eviction_args,
            evict_room=True,
            event_id=persisted_event_id,
            raise_on_failure=True,
        ),
    ]
