"""Wave 209 G1 — ChatCreationService.create_group (mocked repo/uow/cache).

Validation + happy-path orchestration. The repository's create_group is mocked
here (it is real-DB-tested in test_chat_repository_groups); presence hydration +
cache invalidation are patched. The real `settings` supply the 3..100 bound.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.core.localization import translate
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


def _patched_side_effects():
    return (
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
    )


async def _create_group_with_total(total: int):
    """Create a group whose total size (creator included) is ``total``.

    ``create_group`` counts the creator plus the distinct other participant ids
    (the creator's own id and duplicates are dropped first), so ``total - 1``
    other ids are passed in.
    """
    creator = _mock_user()
    other_ids = [uuid.uuid4() for _ in range(total - 1)]
    uow = _mock_uow()
    uow.chats.get_user = AsyncMock(side_effect=lambda pid: _mock_user(pid))
    dto = _mock_group_dto(creator.id, other_ids, name="Team")
    uow.chats.create_group = AsyncMock(return_value=dto)
    svc = _svc(uow)

    first, second, third = _patched_side_effects()
    with first, second, third:
        result = await svc.create_group(creator, "Team", other_ids, "en")
    return uow, result


@pytest.mark.asyncio
async def test_create_group_total_counts_creator_and_rejects_two_total_below_minimum():
    """Creator + 1 other = 2 total, below the minimum of 3: HTTP 400."""
    assert settings.chat_group_min_members == 3
    creator = _mock_user()
    uow = _mock_uow()
    svc = _svc(uow)

    # One other member → total 2 < min 3 → rejected before the repo is touched.
    with pytest.raises(HTTPException) as exc:
        await svc.create_group(creator, "Team", [uuid.uuid4()], "en")

    assert exc.value.status_code == 400
    assert exc.value.detail == translate(
        "errors.chat.group_too_few_members", locale="en"
    )
    uow.chats.create_group.assert_not_called()


@pytest.mark.asyncio
async def test_create_group_total_counts_creator_and_accepts_exactly_three_total():
    """Creator + 2 others = 3 total, exactly the minimum: accepted."""
    uow, result = await _create_group_with_total(3)

    assert len(result.participants) == 3
    create_call = uow.chats.create_group.await_args
    assert create_call is not None
    assert len(create_call.args[2]) == 2  # other members, creator excluded
    uow.chats.create_group.assert_awaited_once()
    uow.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_group_total_counts_creator_and_accepts_exactly_100_total():
    """Creator + 99 others = 100 total, exactly the maximum: accepted."""
    assert settings.chat_group_max_members == 100
    uow, result = await _create_group_with_total(100)

    assert len(result.participants) == 100
    create_call = uow.chats.create_group.await_args
    assert create_call is not None
    assert len(create_call.args[2]) == 99  # other members, creator excluded
    uow.chats.create_group.assert_awaited_once()
    uow.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_group_total_counts_creator_and_rejects_101_total_above_maximum():
    """Creator + 100 others = 101 total, above the maximum of 100: HTTP 400."""
    creator = _mock_user()
    uow = _mock_uow()
    svc = _svc(uow)

    with pytest.raises(HTTPException) as exc:
        await svc.create_group(
            creator, "Team", [uuid.uuid4() for _ in range(100)], "en"
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == translate(
        "errors.chat.group_too_many_members", locale="en"
    )
    uow.chats.create_group.assert_not_called()


@pytest.mark.asyncio
async def test_create_group_rejects_blank_name():
    creator = _mock_user()
    uow = _mock_uow()
    svc = _svc(uow)

    with pytest.raises(HTTPException) as exc:
        await svc.create_group(creator, "   ", [uuid.uuid4(), uuid.uuid4()], "en")

    assert exc.value.status_code == 400
    assert exc.value.detail == translate("errors.chat.group_name_required", locale="en")
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

    first, second, third = _patched_side_effects()
    with first, second, third:
        result = await svc.create_group(creator, "Team Chat", [m1, m2], "en")

    assert result.chat_type == "group"
    assert result.name == "Team Chat"
    assert result.created_by == creator.id
    assert len(result.participants) == 3
    uow.chats.create_group.assert_awaited_once()
    uow.commit.assert_awaited_once()
