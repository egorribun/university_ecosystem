from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.ws import connection_manager, presence
from app.core import nats_broker
from app.deps.cache import MemoryCache, versioned_key
from app.services.chat.command_service import ChatMaintenanceService


@pytest.mark.asyncio
async def test_removed_member_is_not_in_next_cached_chat_broadcast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_id = uuid.uuid4()
    removed_id = uuid.uuid4()
    remaining_id = uuid.uuid4()
    chat_id = uuid.uuid4()
    old_participants = [owner_id, removed_id, remaining_id]
    current_participants = list(old_participants)
    cache = MemoryCache(default_ttl=120)
    cache_key = versioned_key(f"chat:{chat_id}:participants")
    await cache.set(cache_key, [str(user_id) for user_id in old_participants], ttl=3600)
    monkeypatch.setattr(presence, "get_cache", lambda: cache)
    monkeypatch.setattr(connection_manager, "get_cache", lambda: cache)
    monkeypatch.setattr(nats_broker.broker, "publish_core", AsyncMock())
    monkeypatch.setattr(
        "app.services.ws_hub_client.invalidate_ws_hub_cache", AsyncMock()
    )

    class ParticipantRepository:
        def __init__(self, _session: object) -> None:
            pass

        async def get_participants(
            self, requested_chat_id: uuid.UUID
        ) -> list[uuid.UUID]:
            if requested_chat_id != chat_id:
                raise AssertionError("chat_participant_reload_identity_contract")
            return list(current_participants)

    @asynccontextmanager
    async def open_session() -> AsyncIterator[object]:
        yield object()

    monkeypatch.setattr(connection_manager, "ChatRepository", ParticipantRepository)
    manager = connection_manager.ConnectionManager(session_factory=open_session)
    monkeypatch.setattr(manager, "send_to_user", AsyncMock(return_value=1))
    await manager.broadcast_to_chat(chat_id, {"type": "test"})
    warmed_targets = {item.args[0] for item in manager.send_to_user.await_args_list}
    if warmed_targets != set(old_participants):
        raise AssertionError("pre_removal_participant_cache_contract")

    owner = MagicMock()
    owner.id = owner_id
    chat = MagicMock()
    chat.id = chat_id
    chat.created_by = owner_id
    chat.chat_type = "group"
    chat.participants = [
        MagicMock(id=owner_id),
        MagicMock(id=removed_id),
        MagicMock(id=remaining_id),
    ]
    uow = MagicMock()
    uow.chats = MagicMock()
    uow.chats.get_by_id = AsyncMock(return_value=chat)

    async def remove_member(
        _requested_chat_id: uuid.UUID, requested_user_id: uuid.UUID
    ) -> int:
        if requested_user_id != removed_id:
            raise AssertionError("removed_participant_identity_contract")
        current_participants.remove(removed_id)
        return 1

    uow.chats.remove_participant = AsyncMock(side_effect=remove_member)
    uow.chats.add = MagicMock()
    uow.commit = AsyncMock()
    uow.rollback = AsyncMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=False)

    service = ChatMaintenanceService(uow, MagicMock())
    await service.remove_participant(chat_id, owner, removed_id, "en")

    manager.send_to_user.reset_mock()
    await manager.broadcast_to_chat(chat_id, {"type": "after-removal"})
    delivered_targets = {item.args[0] for item in manager.send_to_user.await_args_list}
    if delivered_targets != {owner_id, remaining_id}:
        raise AssertionError("removed_member_received_stale_chat_broadcast")
    if removed_id in delivered_targets:
        raise AssertionError("removed_member_received_stale_chat_broadcast")
