"""Wave 209 G1 — ChatCreationService.create_group (mocked repo/uow/cache).

Validation + happy-path orchestration. The repository's create_group is mocked
here (it is real-DB-tested in test_chat_repository_groups); presence hydration +
cache invalidation are patched. The real `settings` supply the 3..100 bound.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.chat.creation_service import ChatCreationService


def _mock_user(uid: uuid.UUID | None = None):
    user = MagicMock()
    user.id = uid or uuid.uuid4()
    return user


def _mock_uow():
    uow = MagicMock()
    uow.chats = MagicMock()
    uow.commit = AsyncMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=False)
    return uow


def _mock_group_dto(creator_id: uuid.UUID, member_ids, name="Team"):
    dto = MagicMock()
    dto.id = uuid.uuid4()
    dto.chat_type = "group"
    dto.name = name
    dto.created_by = creator_id
    dto.created_at = datetime.now(UTC)
    dto.updated_at = datetime.now(UTC)
    parts = []
    for pid in (creator_id, *member_ids):
        p = MagicMock()
        p.id = pid
        p.email = f"user-{pid.hex[:6]}@example.com"
        p.full_name = "User"
        p.avatar_url = None
        p.is_active = True
        parts.append(p)
    dto.participants = parts
    return dto


def _svc(uow):
    # ChatCreationService(uow, session, cache) — cache unused by create_group.
    return ChatCreationService(uow, AsyncMock(), MagicMock())


@pytest.mark.asyncio
async def test_create_group_rejects_too_few_members():
    creator = _mock_user()
    uow = _mock_uow()
    svc = _svc(uow)

    # One other member → total 2 < min 3 → rejected before the repo is touched.
    with pytest.raises(Exception):  # noqa: B017
        await svc.create_group(creator, "Team", [uuid.uuid4()], "en")

    uow.chats.create_group.assert_not_called()


@pytest.mark.asyncio
async def test_create_group_rejects_blank_name():
    creator = _mock_user()
    uow = _mock_uow()
    svc = _svc(uow)

    with pytest.raises(Exception):  # noqa: B017
        await svc.create_group(creator, "   ", [uuid.uuid4(), uuid.uuid4()], "en")

    uow.chats.create_group.assert_not_called()


@pytest.mark.asyncio
async def test_create_group_happy_path():
    creator = _mock_user()
    m1, m2 = uuid.uuid4(), uuid.uuid4()
    uow = _mock_uow()
    uow.chats.get_user = AsyncMock(side_effect=lambda pid: _mock_user(pid))
    dto = _mock_group_dto(creator.id, [m1, m2], name="Team Chat")
    uow.chats.create_group = AsyncMock(return_value=dto)
    svc = _svc(uow)

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
        result = await svc.create_group(creator, "Team Chat", [m1, m2], "en")

    assert result.chat_type == "group"
    assert result.name == "Team Chat"
    assert result.created_by == creator.id
    assert len(result.participants) == 3
    uow.chats.create_group.assert_awaited_once()
    uow.commit.assert_awaited_once()
