"""Comprehensive tests for app/services/chat/query_service.py.

Covers: get_chats, get_chat_details, get_messages — validation,
presence enrichment, pagination, and edge cases.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.chat import PresenceStatus
from app.services.chat.query_service import ChatQueryService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_user(role: str = "student") -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "test@example.com"
    user.role = role
    return user


def _mock_chat(
    *participant_ids: uuid.UUID,
    chat_type: str = "dm",
    name: str | None = None,
    created_by: uuid.UUID | None = None,
):
    chat = MagicMock()
    chat.id = uuid.uuid4()
    chat.created_at = datetime.now(UTC)
    chat.updated_at = datetime.now(UTC)
    # Wave 209 G1 — explicit so the MagicMock auto-attr isn't fed into the
    # ChatResponse str/UUID fields (the W203-SW8 / W207 replied_to trap → 500).
    chat.chat_type = chat_type
    chat.name = name
    chat.created_by = created_by
    participants = []
    for pid in participant_ids:
        p = MagicMock()
        p.id = pid
        p.email = f"user-{pid.hex[:6]}@example.com"
        p.full_name = f"User {pid.hex[:6]}"
        p.avatar_url = None
        p.is_active = True
        participants.append(p)
    chat.participants = participants
    return chat


def _mock_message(chat_id: uuid.UUID, sender_id: uuid.UUID):
    msg = MagicMock()
    msg.id = uuid.uuid4()
    msg.chat_id = chat_id
    msg.sender_id = sender_id
    msg.content = "Test message"
    msg.created_at = datetime.now(UTC)
    msg.read_status = False
    msg.read_at = (
        None  # Wave 203 — explicit so MagicMock auto-attr doesn't break MessageResponse
    )
    msg.sender = None
    msg.attachments = []
    # Wave 207 — explicit so the auto-MagicMock attr isn't a truthy stand-in that
    # ReplyPreview.from_message would try to build a quote preview from.
    msg.replied_to = None
    return msg


# ---------------------------------------------------------------------------
# get_chats
# ---------------------------------------------------------------------------


class TestGetChats:
    @pytest.mark.asyncio
    async def test_empty_chats(self):
        repo = MagicMock()
        repo.get_chats_for_user = AsyncMock(return_value=([], False, None))
        repo.get_last_messages = AsyncMock(return_value={})

        session = AsyncMock()
        svc = ChatQueryService(session, repo)
        user = _mock_user()

        with patch(
            "app.services.chat.query_service.build_presence_map",
            new_callable=AsyncMock,
            return_value={},
        ):
            result = await svc.get_chats(user, None, 20)

        assert result.items == []
        assert result.has_more is False

    @pytest.mark.asyncio
    async def test_with_chats_and_messages(self):
        from app.schemas.chat import MessageResponse

        user = _mock_user()
        chat = _mock_chat(user.id)
        msg_id = uuid.uuid4()

        row = (chat, 2, msg_id)  # (chat, unread_count, last_message_id)
        repo = MagicMock()
        repo.get_chats_for_user = AsyncMock(return_value=([row], False, None))

        last_msg = MessageResponse(
            id=msg_id,
            chat_id=chat.id,
            sender_id=user.id,
            content="Last",
            created_at=datetime.now(UTC),
            read_status=False,
            sender=None,
            attachments=[],
        )
        repo.get_last_messages = AsyncMock(return_value={msg_id: last_msg})

        session = AsyncMock()
        svc = ChatQueryService(session, repo)

        with patch(
            "app.services.chat.query_service.build_presence_map",
            new_callable=AsyncMock,
            return_value={user.id: PresenceStatus(active=True)},
        ):
            result = await svc.get_chats(user, None, 20)

        assert len(result.items) == 1
        assert result.items[0].unread_count == 2

    @pytest.mark.asyncio
    async def test_with_no_last_message(self):
        user = _mock_user()
        chat = _mock_chat(user.id)
        row = (chat, 0, None)  # no last message

        repo = MagicMock()
        repo.get_chats_for_user = AsyncMock(return_value=([row], False, None))
        repo.get_last_messages = AsyncMock(return_value={})

        session = AsyncMock()
        svc = ChatQueryService(session, repo)

        with patch(
            "app.services.chat.query_service.build_presence_map",
            new_callable=AsyncMock,
            return_value={user.id: PresenceStatus(active=False)},
        ):
            result = await svc.get_chats(user, None, 20)

        assert len(result.items) == 1
        assert result.items[0].last_message is None


# ---------------------------------------------------------------------------
# get_chat_details
# ---------------------------------------------------------------------------


class TestGetChatDetails:
    @pytest.mark.asyncio
    async def test_success(self):
        user = _mock_user()
        chat = _mock_chat(user.id)

        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=chat)
        repo.get_unread_count = AsyncMock(return_value=3)
        repo.get_last_message = AsyncMock(return_value=None)

        session = AsyncMock()
        svc = ChatQueryService(session, repo)

        with patch(
            "app.services.chat.query_service.build_presence_map",
            new_callable=AsyncMock,
            return_value={user.id: PresenceStatus(active=True)},
        ):
            result = await svc.get_chat_details(chat.id, user, "en")

        assert result.id == chat.id
        assert result.unread_count == 3

    @pytest.mark.asyncio
    async def test_returns_group_identity(self):
        # Wave 209 G1 — get_chat_details must surface chat_type/name/created_by
        # (the W203-SW8 5-site fan-out: a missed site silently renders a group as
        # a nameless DM with no error).
        user = _mock_user()
        created_by = uuid.uuid4()
        chat = _mock_chat(
            user.id, chat_type="group", name="Team Chat", created_by=created_by
        )

        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=chat)
        repo.get_unread_count = AsyncMock(return_value=0)
        repo.get_last_message = AsyncMock(return_value=None)
        # Wave 210 G2 — a group detail-fetch queries per-member read receipts.
        repo.get_read_receipts = AsyncMock(return_value=[])

        svc = ChatQueryService(AsyncMock(), repo)

        with patch(
            "app.services.chat.query_service.build_presence_map",
            new_callable=AsyncMock,
            return_value={},
        ):
            result = await svc.get_chat_details(chat.id, user, "en")

        assert result.chat_type == "group"
        assert result.name == "Team Chat"
        assert result.created_by == created_by
        assert result.read_receipts == []

    @pytest.mark.asyncio
    async def test_group_populates_read_receipts(self):
        # Wave 210 G2 — get_chat_details folds the repo's per-member read receipts
        # into ChatResponse.read_receipts (the FE "seen by N" source).
        user = _mock_user()
        reader = uuid.uuid4()
        read_at = datetime.now(UTC)
        chat = _mock_chat(user.id, chat_type="group", name="Team", created_by=user.id)

        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=chat)
        repo.get_unread_count = AsyncMock(return_value=0)
        repo.get_last_message = AsyncMock(return_value=None)
        repo.get_read_receipts = AsyncMock(return_value=[(reader, read_at)])

        svc = ChatQueryService(AsyncMock(), repo)

        with patch(
            "app.services.chat.query_service.build_presence_map",
            new_callable=AsyncMock,
            return_value={},
        ):
            result = await svc.get_chat_details(chat.id, user, "en")

        repo.get_read_receipts.assert_awaited_once_with(chat.id)
        assert len(result.read_receipts) == 1
        assert result.read_receipts[0].user_id == reader
        assert result.read_receipts[0].last_read_at == read_at

    @pytest.mark.asyncio
    async def test_not_found(self):
        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=None)

        svc = ChatQueryService(AsyncMock(), repo)
        user = _mock_user()

        with pytest.raises(Exception):  # noqa: B017
            await svc.get_chat_details(uuid.uuid4(), user, "en")

    @pytest.mark.asyncio
    async def test_not_participant(self):
        user = _mock_user()
        other = _mock_user()
        chat = _mock_chat(other.id)  # user is NOT participant

        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=chat)

        svc = ChatQueryService(AsyncMock(), repo)

        with pytest.raises(Exception):  # noqa: B017
            await svc.get_chat_details(chat.id, user, "en")


# ---------------------------------------------------------------------------
# get_messages
# ---------------------------------------------------------------------------


class TestGetMessages:
    @pytest.mark.asyncio
    async def test_success(self):
        user = _mock_user()
        chat = _mock_chat(user.id)
        msg = _mock_message(chat.id, user.id)

        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=chat)
        repo.get_messages = AsyncMock(return_value=([msg], False, None))

        session = AsyncMock()
        svc = ChatQueryService(session, repo)

        with patch(
            "app.services.chat.query_service.build_presence_map",
            new_callable=AsyncMock,
            return_value={user.id: PresenceStatus(active=True)},
        ):
            result = await svc.get_messages(chat.id, user, None, 20, "en")

        assert len(result.items) == 1
        assert result.has_more is False

    @pytest.mark.asyncio
    async def test_empty_messages(self):
        user = _mock_user()
        chat = _mock_chat(user.id)

        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=chat)
        repo.get_messages = AsyncMock(return_value=([], False, None))

        session = AsyncMock()
        svc = ChatQueryService(session, repo)

        with patch(
            "app.services.chat.query_service.build_presence_map",
            new_callable=AsyncMock,
            return_value={},
        ):
            result = await svc.get_messages(chat.id, user, None, 20, "en")

        assert result.items == []

    @pytest.mark.asyncio
    async def test_not_participant(self):
        user = _mock_user()
        other = _mock_user()
        chat = _mock_chat(other.id)

        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=chat)

        svc = ChatQueryService(AsyncMock(), repo)

        with pytest.raises(Exception):  # noqa: B017
            await svc.get_messages(chat.id, user, None, 20, "en")

    @pytest.mark.asyncio
    async def test_chat_not_found(self):
        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=None)

        svc = ChatQueryService(AsyncMock(), repo)
        user = _mock_user()

        with pytest.raises(Exception):  # noqa: B017
            await svc.get_messages(uuid.uuid4(), user, None, 20, "en")

    @pytest.mark.asyncio
    async def test_with_pagination(self):
        user = _mock_user()
        chat = _mock_chat(user.id)
        msgs = [_mock_message(chat.id, user.id) for _ in range(3)]

        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=chat)
        repo.get_messages = AsyncMock(return_value=(msgs, True, "cursor-abc"))

        session = AsyncMock()
        svc = ChatQueryService(session, repo)

        with patch(
            "app.services.chat.query_service.build_presence_map",
            new_callable=AsyncMock,
            return_value={user.id: PresenceStatus()},
        ):
            result = await svc.get_messages(chat.id, user, None, 3, "en")

        assert len(result.items) == 3
        assert result.has_more is True
        assert result.next_cursor == "cursor-abc"

    @pytest.mark.asyncio
    async def test_get_messages_surfaces_read_at(self):
        # Wave 203 SW8 regression — get_messages constructs MessageResponse
        # field-by-field and originally OMITTED read_at, so it defaulted to None
        # even when the DB row had a timestamp (the seen-marker never showed on
        # refetch). This asserts read_at now flows through.
        user = _mock_user()
        chat = _mock_chat(user.id)
        msg = _mock_message(chat.id, user.id)
        read_at = datetime(2026, 5, 30, 14, 32, tzinfo=UTC)
        msg.read_status = True
        msg.read_at = read_at

        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=chat)
        repo.get_messages = AsyncMock(return_value=([msg], False, None))

        svc = ChatQueryService(AsyncMock(), repo)
        with patch(
            "app.services.chat.query_service.build_presence_map",
            new_callable=AsyncMock,
            return_value={},
        ):
            result = await svc.get_messages(chat.id, user, None, 20, "en")

        assert result.items[0].read_at == read_at
