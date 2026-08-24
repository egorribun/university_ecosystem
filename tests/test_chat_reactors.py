"""Reactor-list ("who reacted") query service tests.

Covers ChatQueryService.get_reactors (SW5):
  - a participant maps the repo's User rows → ReactorOut (User.id → user_id; name +
    avatar carried through; the repo's oldest-first order is preserved);
  - an empty reactor list → [];
  - a non-participant → forbidden (raise_forbidden);
  - a missing chat → ensure_exists raises;
  - a message not in this chat → 404 (raise_not_found) BEFORE the reactor query
    (so a participant of one chat can't enumerate reactors of a message in another).

Mirrors the W206/W207 mock pattern (mock the repo, no DB). The repo's get_reactors
itself (a direct users↔message_reactions JOIN) is exercised cross-user at SW9.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.schemas.chat import ReactorOut
from app.services.chat.query_service import ChatQueryService


def _mock_user(uid: uuid.UUID | None = None) -> MagicMock:
    user = MagicMock()
    user.id = uid or uuid.uuid4()
    return user


def _mock_chat(*participant_ids: uuid.UUID) -> MagicMock:
    chat = MagicMock()
    chat.id = uuid.uuid4()
    participants = []
    for pid in participant_ids:
        p = MagicMock()
        p.id = pid
        participants.append(p)
    chat.participants = participants
    return chat


def _reactor(name: str | None = "Alice", avatar: str | None = None) -> MagicMock:
    """A duck-typed User row (with .profile) as returned by ChatRepository.get_reactors.

    full_name/avatar_url live on User.profile (the repo selectinloads it), so the
    mock carries them on a nested profile object, matching production.
    """
    u = MagicMock()
    u.id = uuid.uuid4()
    profile = MagicMock()
    profile.full_name = name
    profile.avatar_url = avatar
    u.profile = profile
    return u


class TestGetReactors:
    @pytest.mark.asyncio
    async def test_participant_maps_user_rows_to_reactor_out(self) -> None:
        user = _mock_user()
        chat = _mock_chat(user.id)
        message_id = uuid.uuid4()
        r1 = _reactor("Alice", "https://example.com/a.png")
        r2 = _reactor("Bob", None)

        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=chat)
        repo.message_exists_in_chat = AsyncMock(return_value=True)
        repo.get_reactors = AsyncMock(return_value=[r1, r2])

        svc = ChatQueryService(AsyncMock(), repo)
        result = await svc.get_reactors(chat.id, message_id, "👍", user, "en")

        assert all(isinstance(x, ReactorOut) for x in result)
        # User.id → user_id remap + oldest-first order preserved.
        assert [x.user_id for x in result] == [r1.id, r2.id]
        assert result[0].name == "Alice"
        assert result[0].avatar_url == "https://example.com/a.png"
        assert result[1].name == "Bob"
        assert result[1].avatar_url is None
        repo.get_reactors.assert_awaited_once_with(message_id, "👍")

    @pytest.mark.asyncio
    async def test_empty_reactor_list_returns_empty(self) -> None:
        user = _mock_user()
        chat = _mock_chat(user.id)
        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=chat)
        repo.message_exists_in_chat = AsyncMock(return_value=True)
        repo.get_reactors = AsyncMock(return_value=[])

        svc = ChatQueryService(AsyncMock(), repo)
        result = await svc.get_reactors(chat.id, uuid.uuid4(), "😂", user, "en")
        assert result == []

    @pytest.mark.asyncio
    async def test_reactor_without_profile_yields_null_name_avatar(self) -> None:
        # A user with no profile row → name/avatar resolve to None (the
        # `if u.profile else None` guard), not a crash.
        user = _mock_user()
        chat = _mock_chat(user.id)
        bare = MagicMock()
        bare.id = uuid.uuid4()
        bare.profile = None
        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=chat)
        repo.message_exists_in_chat = AsyncMock(return_value=True)
        repo.get_reactors = AsyncMock(return_value=[bare])

        svc = ChatQueryService(AsyncMock(), repo)
        result = await svc.get_reactors(chat.id, uuid.uuid4(), "👍", user, "en")
        assert result[0].user_id == bare.id
        assert result[0].name is None
        assert result[0].avatar_url is None

    @pytest.mark.asyncio
    async def test_non_participant_forbidden(self) -> None:
        user = _mock_user()
        other = _mock_user()
        chat = _mock_chat(other.id)  # user is NOT a participant

        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=chat)
        repo.message_exists_in_chat = AsyncMock()
        repo.get_reactors = AsyncMock()

        svc = ChatQueryService(AsyncMock(), repo)
        with pytest.raises(Exception):  # noqa: B017 — raise_forbidden
            await svc.get_reactors(chat.id, uuid.uuid4(), "👍", user, "en")
        repo.message_exists_in_chat.assert_not_awaited()
        repo.get_reactors.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_chat_not_found_raises(self) -> None:
        user = _mock_user()
        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=None)
        repo.get_reactors = AsyncMock()

        svc = ChatQueryService(AsyncMock(), repo)
        with pytest.raises(Exception):  # noqa: B017 — ensure_exists
            await svc.get_reactors(uuid.uuid4(), uuid.uuid4(), "👍", user, "en")
        repo.get_reactors.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_message_not_in_chat_404_before_query(self) -> None:
        user = _mock_user()
        chat = _mock_chat(user.id)
        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=chat)
        repo.message_exists_in_chat = AsyncMock(return_value=False)
        repo.get_reactors = AsyncMock()

        svc = ChatQueryService(AsyncMock(), repo)
        with pytest.raises(HTTPException) as exc:
            await svc.get_reactors(chat.id, uuid.uuid4(), "👍", user, "en")
        assert exc.value.status_code == 404
        repo.get_reactors.assert_not_awaited()
