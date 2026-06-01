"""Wave 206 — message reactions (ChatMaintenanceService + query aggregation).

Mirrors the W205 edit/delete tests (tests/test_wave205_edit_delete.py): mock the
uow + repo, patch ws_manager.broadcast_to_chat, assert the synchronous-broadcast
contract. Reactions ride the same rail with three differences from edit/delete:
  - NOT author-gated (any participant); a missing message is a clean 404 via an
    explicit message_exists_in_chat check (add only), not affected == 0.
  - DELTA frame {type:reaction_changed, user_id, emoji, action} carrying the actor,
    broadcast with exclude_user_id (the FE self-echo guard handles the NATS mirror).
  - Idempotent: a duplicate add (is_new == False) / a remove of a non-existent
    reaction (affected == 0) commits but does NOT broadcast (no state change).

The repo-level ON CONFLICT DO NOTHING idempotency is DB-enforced by the
(user_id, message_id, emoji) unique constraint — verified at SW1 (migration) and
live at SW7. Here the SERVICE handling of is_new / affected is what's asserted.
The pure _aggregate_reactions helper (the REST reacted_by_me computation) is
unit-tested directly.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.schemas.dtos.chat import MessageReactionDTO
from app.services.chat.command_service import ChatMaintenanceService
from app.services.chat.query_service import _aggregate_reactions

BROADCAST = "app.services.chat.command_service.ws_manager.broadcast_to_chat"


def _mock_uow() -> MagicMock:
    uow = MagicMock()
    uow.chats = MagicMock()
    uow.session = AsyncMock()
    uow.commit = AsyncMock()
    uow.rollback = AsyncMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=False)
    return uow


def _mock_user() -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "test@example.com"
    user.role = "student"
    return user


def _mock_chat(*participant_ids: uuid.UUID) -> MagicMock:
    chat = MagicMock()
    chat.id = uuid.uuid4()
    parts = []
    for pid in participant_ids:
        p = MagicMock()
        p.id = pid
        parts.append(p)
    chat.participants = parts
    return chat


def _svc(uow: MagicMock) -> ChatMaintenanceService:
    return ChatMaintenanceService(uow, MagicMock())


# ---------------------------------------------------------------------------
# add_reaction
# ---------------------------------------------------------------------------


class TestAddReaction:
    @pytest.mark.asyncio
    async def test_success_broadcasts_reaction_added(self) -> None:
        uow = _mock_uow()
        user = _mock_user()
        chat = _mock_chat(user.id)
        message_id = uuid.uuid4()
        uow.chats.get_by_id = AsyncMock(return_value=chat)
        uow.chats.message_exists_in_chat = AsyncMock(return_value=True)
        uow.chats.add_reaction = AsyncMock(return_value=True)  # is_new

        with patch(BROADCAST, new=AsyncMock()) as broadcast:
            await _svc(uow).add_reaction(chat.id, message_id, user, "👍", "en")

        uow.chats.message_exists_in_chat.assert_awaited_once_with(message_id, chat.id)
        uow.chats.add_reaction.assert_awaited_once_with(message_id, user.id, "👍")
        uow.commit.assert_awaited_once()
        broadcast.assert_awaited_once()
        call = broadcast.await_args
        assert call.args[0] == chat.id
        frame = call.args[1]
        assert frame["type"] == "reaction_changed"
        assert frame["chat_id"] == str(chat.id)
        assert frame["message_id"] == str(message_id)
        assert frame["user_id"] == str(user.id)
        assert frame["emoji"] == "👍"
        assert frame["action"] == "added"
        # Delta frame excludes the actor in-process; the FE self-echo guard
        # handles the NATS mirror (the actor already patched optimistically).
        assert call.kwargs.get("exclude_user_id") == user.id

    @pytest.mark.asyncio
    async def test_duplicate_commits_but_no_broadcast(self) -> None:
        uow = _mock_uow()
        user = _mock_user()
        chat = _mock_chat(user.id)
        uow.chats.get_by_id = AsyncMock(return_value=chat)
        uow.chats.message_exists_in_chat = AsyncMock(return_value=True)
        uow.chats.add_reaction = AsyncMock(return_value=False)  # already reacted

        with patch(BROADCAST, new=AsyncMock()) as broadcast:
            await _svc(uow).add_reaction(chat.id, uuid.uuid4(), user, "👍", "en")

        uow.commit.assert_awaited_once()
        broadcast.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_message_raises_404_before_commit(self) -> None:
        uow = _mock_uow()
        user = _mock_user()
        chat = _mock_chat(user.id)
        uow.chats.get_by_id = AsyncMock(return_value=chat)
        uow.chats.message_exists_in_chat = AsyncMock(return_value=False)
        uow.chats.add_reaction = AsyncMock()

        with patch(BROADCAST, new=AsyncMock()) as broadcast:
            with pytest.raises(HTTPException) as exc:
                await _svc(uow).add_reaction(chat.id, uuid.uuid4(), user, "👍", "en")

        assert exc.value.status_code == 404
        uow.chats.add_reaction.assert_not_awaited()
        uow.commit.assert_not_awaited()
        broadcast.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_not_participant_raises_403_without_repo_call(self) -> None:
        uow = _mock_uow()
        user = _mock_user()
        other = _mock_user()
        chat = _mock_chat(other.id)  # user NOT a participant
        uow.chats.get_by_id = AsyncMock(return_value=chat)
        uow.chats.message_exists_in_chat = AsyncMock()
        uow.chats.add_reaction = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await _svc(uow).add_reaction(chat.id, uuid.uuid4(), user, "👍", "en")

        assert exc.value.status_code == 403
        uow.chats.message_exists_in_chat.assert_not_awaited()
        uow.chats.add_reaction.assert_not_awaited()


# ---------------------------------------------------------------------------
# remove_reaction
# ---------------------------------------------------------------------------


class TestRemoveReaction:
    @pytest.mark.asyncio
    async def test_success_broadcasts_reaction_removed(self) -> None:
        uow = _mock_uow()
        user = _mock_user()
        chat = _mock_chat(user.id)
        message_id = uuid.uuid4()
        uow.chats.get_by_id = AsyncMock(return_value=chat)
        uow.chats.remove_reaction = AsyncMock(return_value=1)  # affected

        with patch(BROADCAST, new=AsyncMock()) as broadcast:
            await _svc(uow).remove_reaction(chat.id, message_id, user, "👍", "en")

        uow.chats.remove_reaction.assert_awaited_once_with(message_id, user.id, "👍")
        uow.commit.assert_awaited_once()
        broadcast.assert_awaited_once()
        call = broadcast.await_args
        assert call.args[0] == chat.id
        frame = call.args[1]
        assert frame["type"] == "reaction_changed"
        assert frame["message_id"] == str(message_id)
        assert frame["user_id"] == str(user.id)
        assert frame["emoji"] == "👍"
        assert frame["action"] == "removed"
        assert call.kwargs.get("exclude_user_id") == user.id

    @pytest.mark.asyncio
    async def test_nonexistent_commits_but_no_broadcast(self) -> None:
        uow = _mock_uow()
        user = _mock_user()
        chat = _mock_chat(user.id)
        uow.chats.get_by_id = AsyncMock(return_value=chat)
        uow.chats.remove_reaction = AsyncMock(return_value=0)  # nothing to remove

        with patch(BROADCAST, new=AsyncMock()) as broadcast:
            await _svc(uow).remove_reaction(chat.id, uuid.uuid4(), user, "👍", "en")

        uow.commit.assert_awaited_once()
        broadcast.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_not_participant_raises_403_without_repo_call(self) -> None:
        uow = _mock_uow()
        user = _mock_user()
        other = _mock_user()
        chat = _mock_chat(other.id)
        uow.chats.get_by_id = AsyncMock(return_value=chat)
        uow.chats.remove_reaction = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await _svc(uow).remove_reaction(chat.id, uuid.uuid4(), user, "👍", "en")

        assert exc.value.status_code == 403
        uow.chats.remove_reaction.assert_not_awaited()


# ---------------------------------------------------------------------------
# _aggregate_reactions — the REST reacted_by_me computation (pure)
# ---------------------------------------------------------------------------


class TestAggregateReactions:
    def test_groups_by_emoji_with_counts_and_reacted_by_me(self) -> None:
        me = uuid.uuid4()
        other1 = uuid.uuid4()
        other2 = uuid.uuid4()
        rows = [
            MessageReactionDTO(user_id=other1, emoji="👍"),
            MessageReactionDTO(user_id=other2, emoji="👍"),
            MessageReactionDTO(user_id=me, emoji="❤️"),
        ]
        aggs = _aggregate_reactions(rows, me)
        by_emoji = {a.emoji: a for a in aggs}
        assert by_emoji["👍"].count == 2
        assert by_emoji["👍"].reacted_by_me is False  # me didn't react with 👍
        assert by_emoji["❤️"].count == 1
        assert by_emoji["❤️"].reacted_by_me is True

    def test_empty_rows_returns_empty(self) -> None:
        assert _aggregate_reactions([], uuid.uuid4()) == []

    def test_preserves_first_seen_emoji_order(self) -> None:
        me = uuid.uuid4()
        rows = [
            MessageReactionDTO(user_id=uuid.uuid4(), emoji="😂"),
            MessageReactionDTO(user_id=uuid.uuid4(), emoji="👍"),
            MessageReactionDTO(user_id=me, emoji="😂"),
        ]
        aggs = _aggregate_reactions(rows, me)
        assert [a.emoji for a in aggs] == ["😂", "👍"]
        assert aggs[0].count == 2
        assert aggs[0].reacted_by_me is True
