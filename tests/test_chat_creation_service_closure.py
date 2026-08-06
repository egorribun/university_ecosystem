from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.core.exceptions import BusinessRuleViolation
from app.schemas.chat import PresenceStatus
from app.services.chat.creation_service import ChatCreationService


def _user(user_id: uuid.UUID | None = None) -> SimpleNamespace:
    return SimpleNamespace(id=user_id or uuid.uuid4())


def _participant(user_id: uuid.UUID) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        email=f"user-{user_id.hex[:8]}@example.com",
        full_name="User",
        avatar_url=None,
        is_active=True,
    )


def _chat(participants: list[SimpleNamespace], *, chat_type="dm") -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid.uuid4(),
        chat_type=chat_type,
        name=None,
        created_by=None,
        participants=participants,
        created_at=now,
        updated_at=now,
    )


def _uow() -> MagicMock:
    uow = MagicMock()
    uow.chats = MagicMock()
    uow.commit = AsyncMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=False)
    return uow


def _cache(*, lock: AsyncMock, wrapped: bool = False) -> SimpleNamespace:
    client = MagicMock()
    lock_object = SimpleNamespace(
        acquire=lock,
        release=AsyncMock(),
    )
    client.lock.return_value = lock_object
    backend = SimpleNamespace(
        _get_client=AsyncMock(return_value=client), _test_lock=lock_object
    )
    if wrapped:
        return SimpleNamespace(l2=backend)
    return backend


@pytest.mark.asyncio
async def test_create_chat_rejects_missing_self_and_missing_participant():
    uow = _uow()
    service = ChatCreationService(uow, AsyncMock(), MagicMock())
    user = _user()

    with pytest.raises(HTTPException) as missing:
        await service.create_chat(user, None, "en")
    assert missing.value.status_code == 400

    with pytest.raises(HTTPException) as self_chat:
        await service.create_chat(user, user.id, "en")
    assert self_chat.value.status_code == 400

    uow.chats.get_user = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as not_found:
        await service.create_chat(user, uuid.uuid4(), "en")
    assert not_found.value.status_code == 404


@pytest.mark.asyncio
async def test_create_chat_requires_redis_backend_and_valid_ids():
    user = _user()
    participant_id = uuid.uuid4()
    uow = _uow()
    uow.chats.get_user = AsyncMock(return_value=_participant(participant_id))

    no_backend = ChatCreationService(uow, AsyncMock(), SimpleNamespace())
    with pytest.raises(RuntimeError, match="Redis-backed"):
        await no_backend.create_chat(user, participant_id, "en")

    invalid_user = SimpleNamespace(id=None)
    lock = AsyncMock(return_value=True)
    service = ChatCreationService(uow, AsyncMock(), _cache(lock=lock))
    with pytest.raises(BusinessRuleViolation, match="invalid_participants"):
        await service.create_chat(invalid_user, participant_id, "en")


@pytest.mark.asyncio
async def test_create_chat_lock_timeout_and_release_failure():
    user = _user()
    participant_id = uuid.uuid4()
    uow = _uow()
    uow.chats.get_user = AsyncMock(return_value=_participant(participant_id))

    lock = AsyncMock(return_value=False)
    service = ChatCreationService(uow, AsyncMock(), _cache(lock=lock))
    with pytest.raises(HTTPException) as not_acquired:
        await service.create_chat(user, participant_id, "en")
    assert not_acquired.value.status_code == 400

    timeout_lock = AsyncMock(side_effect=TimeoutError)
    timeout_service = ChatCreationService(
        uow, AsyncMock(), _cache(lock=timeout_lock, wrapped=True)
    )
    with pytest.raises(HTTPException) as timed_out:
        await timeout_service.create_chat(user, participant_id, "en")
    assert timed_out.value.status_code == 400


@pytest.mark.asyncio
async def test_create_chat_returns_existing_chat_and_releases_lock():
    user = _user()
    participant_id = uuid.uuid4()
    participant = _participant(participant_id)
    existing = _chat([_participant(user.id), participant])
    uow = _uow()
    uow.chats.get_user = AsyncMock(return_value=participant)
    uow.chats.find_existing_dm = AsyncMock(return_value=existing)
    lock = AsyncMock(return_value=True)
    cache = _cache(lock=lock)
    lock_object = cache._test_lock

    result = await ChatCreationService(uow, AsyncMock(), cache).create_chat(
        user, participant_id, "en"
    )
    assert result.id == existing.id
    lock_object.release.assert_awaited_once()
    uow.chats.create_chat.assert_not_called()


@pytest.mark.asyncio
async def test_create_chat_creates_and_hydrates_presence():
    user = _user()
    participant_id = uuid.uuid4()
    people = [_participant(user.id), _participant(participant_id)]
    created = _chat(people)
    uow = _uow()
    uow.chats.get_user = AsyncMock(return_value=people[1])
    uow.chats.find_existing_dm = AsyncMock(return_value=None)
    uow.chats.create_chat = AsyncMock(return_value=created)
    lock = AsyncMock(return_value=True)
    cache = _cache(lock=lock)

    with (
        patch(
            "app.services.chat.creation_service.invalidate_chat_participants_cache",
            new_callable=AsyncMock,
        ) as invalidate_chat,
        patch(
            "app.services.chat.creation_service.invalidate_presence_audience_cache",
            new_callable=AsyncMock,
        ) as invalidate_audience,
        patch(
            "app.services.chat.creation_service.build_presence_map",
            new_callable=AsyncMock,
            return_value={people[0].id: PresenceStatus(active=True)},
        ),
    ):
        result = await ChatCreationService(uow, "db", cache).create_chat(
            user, participant_id, "en"
        )

    assert result.presence[people[0].id].active is True
    assert result.presence[people[1].id].active is False
    invalidate_chat.assert_awaited_once_with(created.id)
    invalidate_audience.assert_awaited_once_with(user.id, participant_id)
    uow.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_group_rejects_too_many_and_missing_member():
    creator = _user()
    uow = _uow()
    service = ChatCreationService(uow, AsyncMock(), MagicMock())

    with pytest.raises(HTTPException) as too_many:
        await service.create_group(
            creator, "Team", [uuid.uuid4() for _ in range(100)], "en"
        )
    assert too_many.value.status_code == 400

    member_id = uuid.uuid4()
    uow.chats.get_user = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as missing:
        await service.create_group(creator, "Team", [member_id, uuid.uuid4()], "en")
    assert missing.value.status_code == 404


@pytest.mark.asyncio
async def test_create_group_deduplicates_creator_and_members():
    creator = _user()
    first_id, second_id = uuid.uuid4(), uuid.uuid4()
    members = [_participant(first_id), _participant(second_id)]
    created = _chat([_participant(creator.id), *members], chat_type="group")
    created.name = "Clean Team"
    created.created_by = creator.id
    uow = _uow()
    uow.chats.get_user = AsyncMock(side_effect=lambda pid: _participant(pid))
    uow.chats.create_group = AsyncMock(return_value=created)
    service = ChatCreationService(uow, "db", MagicMock())

    with (
        patch(
            "app.services.chat.creation_service.invalidate_chat_participants_cache",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.chat.creation_service.invalidate_presence_audience_cache",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.chat.creation_service.build_presence_map",
            new_callable=AsyncMock,
            return_value={},
        ),
    ):
        result = await service.create_group(
            creator,
            "  Clean Team  ",
            [creator.id, first_id, first_id, second_id],
            "en",
        )

    assert result.name == "Clean Team"
    assert [call.args[0] for call in uow.chats.get_user.await_args_list] == [
        first_id,
        second_id,
    ]
    uow.chats.create_group.assert_awaited_once_with(creator, "Clean Team", members)


@pytest.mark.asyncio
async def test_create_group_uses_async_bulk_member_lookup():
    creator = _user()
    first_id, second_id = uuid.uuid4(), uuid.uuid4()
    members = [_participant(first_id), _participant(second_id)]
    created = _chat([_participant(creator.id), *members], chat_type="group")
    uow = _uow()
    uow.chats.get_users_by_ids = AsyncMock(return_value=members)
    uow.chats.get_user = AsyncMock()
    uow.chats.create_group = AsyncMock(return_value=created)

    with (
        patch(
            "app.services.chat.creation_service.invalidate_chat_participants_cache",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.chat.creation_service.invalidate_presence_audience_cache",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.chat.creation_service.build_presence_map",
            new_callable=AsyncMock,
            return_value={},
        ),
    ):
        await ChatCreationService(uow, "db", MagicMock()).create_group(
            creator, "Bulk Team", [first_id, second_id], "en"
        )

    uow.chats.get_users_by_ids.assert_awaited_once_with([first_id, second_id])
    uow.chats.get_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_group_accepts_sync_bulk_lookup_result():
    creator = _user()
    first_id, second_id = uuid.uuid4(), uuid.uuid4()
    members = [_participant(first_id), _participant(second_id)]
    created = _chat([_participant(creator.id), *members], chat_type="group")
    uow = _uow()
    uow.chats.get_users_by_ids = MagicMock(return_value=members)
    uow.chats.get_user = AsyncMock()
    uow.chats.create_group = AsyncMock(return_value=created)

    with (
        patch(
            "app.services.chat.creation_service.invalidate_chat_participants_cache",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.chat.creation_service.invalidate_presence_audience_cache",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.chat.creation_service.build_presence_map",
            new_callable=AsyncMock,
            return_value={},
        ),
    ):
        await ChatCreationService(uow, "db", MagicMock()).create_group(
            creator, "Sync Team", [first_id, second_id], "en"
        )

    uow.chats.get_users_by_ids.assert_called_once_with([first_id, second_id])
    uow.chats.get_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_group_falls_back_after_bulk_lookup_failure():
    creator = _user()
    first_id, second_id = uuid.uuid4(), uuid.uuid4()
    members = [_participant(first_id), _participant(second_id)]
    created = _chat([_participant(creator.id), *members], chat_type="group")
    uow = _uow()
    uow.chats.get_users_by_ids = AsyncMock(side_effect=RuntimeError("unsupported"))
    uow.chats.get_user = AsyncMock(side_effect=members)
    uow.chats.create_group = AsyncMock(return_value=created)

    with (
        patch(
            "app.services.chat.creation_service.invalidate_chat_participants_cache",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.chat.creation_service.invalidate_presence_audience_cache",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.chat.creation_service.build_presence_map",
            new_callable=AsyncMock,
            return_value={},
        ),
    ):
        await ChatCreationService(uow, "db", MagicMock()).create_group(
            creator, "Fallback Team", [first_id, second_id], "en"
        )

    assert [call.args[0] for call in uow.chats.get_user.await_args_list] == [
        first_id,
        second_id,
    ]


@pytest.mark.asyncio
async def test_create_group_falls_back_when_bulk_lookup_is_unavailable():
    creator = _user()
    first_id, second_id = uuid.uuid4(), uuid.uuid4()
    members = [_participant(first_id), _participant(second_id)]
    created = _chat([_participant(creator.id), *members], chat_type="group")
    uow = _uow()
    uow.chats.get_users_by_ids = None
    uow.chats.get_user = AsyncMock(side_effect=members)
    uow.chats.create_group = AsyncMock(return_value=created)

    with (
        patch(
            "app.services.chat.creation_service.invalidate_chat_participants_cache",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.chat.creation_service.invalidate_presence_audience_cache",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.chat.creation_service.build_presence_map",
            new_callable=AsyncMock,
            return_value={},
        ),
    ):
        await ChatCreationService(uow, "db", MagicMock()).create_group(
            creator, "Fallback Team", [first_id, second_id], "en"
        )

    assert [call.args[0] for call in uow.chats.get_user.await_args_list] == [
        first_id,
        second_id,
    ]
