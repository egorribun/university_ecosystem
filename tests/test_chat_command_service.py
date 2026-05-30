"""Comprehensive tests for app/services/chat/command_service.py.

Covers: ChatMessageDispatcher (send_message — idempotency, validation,
Phase 1/2, error recovery), ChatMaintenanceService (mark_read,
clear_history, delete_chat), and _make_idempotency_key.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.chat.command_service import (
    ChatMaintenanceService,
    ChatMessageDispatcher,
    _make_idempotency_key,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_uow():
    uow = MagicMock()
    uow.chats = MagicMock()
    uow.session = AsyncMock()
    uow.commit = AsyncMock()
    uow.rollback = AsyncMock()
    # context manager support
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=False)
    return uow


def _mock_attachment_service():
    svc = MagicMock()
    svc.process_upload = AsyncMock(
        return_value={
            "url": "https://s3.example.com/file.pdf",
            "file_type": "application/pdf",
            "filename": "file.pdf",
            "size": 1024,
        }
    )
    svc.cleanup_files = AsyncMock()
    svc.collect_urls = AsyncMock(return_value=[])
    return svc


def _mock_notification_service():
    svc = MagicMock()
    svc.notify_new_message = AsyncMock()
    return svc


def _mock_user(role: str = "student") -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "test@example.com"
    user.role = role
    return user


def _mock_chat(owner_id: uuid.UUID, *participant_ids: uuid.UUID):
    chat = MagicMock()
    chat.id = uuid.uuid4()
    chat.created_at = datetime.now(UTC)
    chat.updated_at = datetime.now(UTC)
    chat.messages = []
    participants = []
    for pid in [owner_id, *participant_ids]:
        p = MagicMock()
        p.id = pid
        participants.append(p)
    chat.participants = participants
    return chat


# ---------------------------------------------------------------------------
# _make_idempotency_key
# ---------------------------------------------------------------------------


class TestMakeIdempotencyKey:
    def test_basic(self):
        key = _make_idempotency_key(uuid.uuid4(), uuid.uuid4(), "client-key-1")
        assert key.startswith("idm:msg:")
        assert len(key) > 10

    def test_deterministic(self):
        cid = uuid.uuid4()
        uid = uuid.uuid4()
        k1 = _make_idempotency_key(cid, uid, "same-key")
        k2 = _make_idempotency_key(cid, uid, "same-key")
        assert k1 == k2

    def test_different_keys(self):
        cid = uuid.uuid4()
        uid = uuid.uuid4()
        k1 = _make_idempotency_key(cid, uid, "key-a")
        k2 = _make_idempotency_key(cid, uid, "key-b")
        assert k1 != k2

    def test_with_hmac_secret(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "idempotency_hmac_secret", "test-secret-key")

        key = _make_idempotency_key(uuid.uuid4(), uuid.uuid4(), "test")
        assert key.startswith("idm:msg:")

    def test_without_hmac_secret(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "idempotency_hmac_secret", "")

        key = _make_idempotency_key(uuid.uuid4(), uuid.uuid4(), "test")
        assert key.startswith("idm:msg:")


# ---------------------------------------------------------------------------
# ChatMessageDispatcher.send_message — validation
# ---------------------------------------------------------------------------


class TestSendMessageValidation:
    @pytest.mark.asyncio
    async def test_chat_not_found(self):
        uow = _mock_uow()
        uow.chats.get_by_id = AsyncMock(return_value=None)

        dispatcher = ChatMessageDispatcher(
            uow, _mock_attachment_service(), _mock_notification_service()
        )
        user = _mock_user()

        with pytest.raises(Exception):  # noqa: B017  # noqa: B017
            await dispatcher.send_message(uuid.uuid4(), user, "Hello", [], "en")

    @pytest.mark.asyncio
    async def test_not_participant(self):
        uow = _mock_uow()
        chat = _mock_chat(uuid.uuid4())
        uow.chats.get_by_id = AsyncMock(return_value=chat)
        uow.chats.check_participant = AsyncMock(return_value=False)

        dispatcher = ChatMessageDispatcher(
            uow, _mock_attachment_service(), _mock_notification_service()
        )
        user = _mock_user()

        with pytest.raises(Exception):  # noqa: B017  # noqa: B017
            await dispatcher.send_message(chat.id, user, "Hello", [], "en")

    @pytest.mark.asyncio
    async def test_empty_message_no_files(self):
        uow = _mock_uow()
        user = _mock_user()
        chat = _mock_chat(user.id)
        uow.chats.get_by_id = AsyncMock(return_value=chat)
        uow.chats.check_participant = AsyncMock(return_value=True)

        dispatcher = ChatMessageDispatcher(
            uow, _mock_attachment_service(), _mock_notification_service()
        )

        with pytest.raises(Exception):  # noqa: B017  # noqa: B017
            await dispatcher.send_message(chat.id, user, "   ", [], "en")

    @pytest.mark.asyncio
    async def test_message_too_long(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "chat_max_message_length", 100)

        uow = _mock_uow()
        user = _mock_user()
        chat = _mock_chat(user.id)
        uow.chats.get_by_id = AsyncMock(return_value=chat)
        uow.chats.check_participant = AsyncMock(return_value=True)

        dispatcher = ChatMessageDispatcher(
            uow, _mock_attachment_service(), _mock_notification_service()
        )

        with pytest.raises(Exception):  # noqa: B017  # noqa: B017
            await dispatcher.send_message(chat.id, user, "A" * 200, [], "en")

    @pytest.mark.asyncio
    async def test_too_many_attachments(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "chat_attachment_max_files", 2)

        uow = _mock_uow()
        user = _mock_user()
        chat = _mock_chat(user.id)
        uow.chats.get_by_id = AsyncMock(return_value=chat)
        uow.chats.check_participant = AsyncMock(return_value=True)

        dispatcher = ChatMessageDispatcher(
            uow, _mock_attachment_service(), _mock_notification_service()
        )

        files = [MagicMock() for _ in range(5)]

        with pytest.raises(Exception):  # noqa: B017  # noqa: B017
            await dispatcher.send_message(chat.id, user, "With files", files, "en")


# ---------------------------------------------------------------------------
# ChatMessageDispatcher.send_message — success paths
# ---------------------------------------------------------------------------


class TestSendMessageSuccess:
    @pytest.mark.asyncio
    async def test_simple_text_message(self):
        uow = _mock_uow()
        user = _mock_user()
        chat = _mock_chat(user.id)
        uow.chats.get_by_id = AsyncMock(return_value=chat)
        uow.chats.check_participant = AsyncMock(return_value=True)
        uow.chats.update_timestamp_by_id = AsyncMock()
        uow.chats.add = MagicMock()

        # create_message captures the Message object so we can get its id
        created_msgs = []

        async def _capture_message(msg):
            msg.id = uuid.uuid4()
            msg.created_at = datetime.now(UTC)
            msg.read_status = False
            msg.sender = None
            msg.attachments = []
            created_msgs.append(msg)

        uow.chats.create_message = AsyncMock(side_effect=_capture_message)

        # get_last_messages returns by message id — we need to match dynamically
        async def _get_last(ids):
            if not created_msgs:
                return {}
            m = created_msgs[0]
            mock_resp = MagicMock()
            mock_resp.model_dump.return_value = {
                "id": m.id,
                "chat_id": m.chat_id,
                "sender_id": m.sender_id,
                "content": m.content,
                "created_at": m.created_at,
                "read_status": False,
                "sender": None,
                "attachments": [],
            }
            return {m.id: mock_resp}

        uow.chats.get_last_messages = AsyncMock(side_effect=_get_last)

        dispatcher = ChatMessageDispatcher(
            uow, _mock_attachment_service(), _mock_notification_service()
        )

        with patch("app.services.chat.command_service.ws_manager") as mock_ws:
            mock_ws.is_online = MagicMock(return_value=True)

            # Patch Message to capture record_event
            with patch("app.services.chat.command_service.cast") as mock_cast:
                mock_emitter = MagicMock()
                mock_cast.return_value = mock_emitter

                result = await dispatcher.send_message(chat.id, user, "Hello", [], "en")

        assert result is not None
        uow.chats.create_message.assert_called_once()
        uow.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_idempotency_cache_hit(self):
        """Idempotent send returns cached response."""
        import json as _json

        uow = _mock_uow()
        user = _mock_user()
        msg_id = uuid.uuid4()
        chat_id = uuid.uuid4()

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(
            return_value=_json.dumps({"status": "completed", "message_id": str(msg_id)})
        )

        cached_msg = MagicMock()
        cached_msg.model_dump.return_value = {
            "id": msg_id,
            "chat_id": chat_id,
            "sender_id": user.id,
            "content": "Cached",
            "created_at": datetime.now(UTC),
            "read_status": False,
            "sender": None,
            "attachments": [],
        }
        cached_msg.sender_id = user.id
        uow.chats.get_message_by_id = AsyncMock(return_value=cached_msg)

        dispatcher = ChatMessageDispatcher(
            uow, _mock_attachment_service(), _mock_notification_service()
        )

        with (
            patch(
                "app.deps.cache.get_cache_client",
                new_callable=AsyncMock,
                return_value=mock_redis,
            ),
            patch("app.services.chat.command_service.ws_manager") as mock_ws,
        ):
            mock_ws.is_online = MagicMock(return_value=False)
            result = await dispatcher.send_message(
                chat_id, user, "Hello", [], "en", idempotency_key="idem-123"
            )

        assert result is not None
        uow.chats.create_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_with_file_upload(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "chat_attachment_max_files", 5)
        monkeypatch.setattr(settings, "chat_max_message_length", 10000)

        uow = _mock_uow()
        user = _mock_user()
        chat = _mock_chat(user.id)
        uow.chats.get_by_id = AsyncMock(return_value=chat)
        uow.chats.check_participant = AsyncMock(return_value=True)
        uow.chats.update_timestamp_by_id = AsyncMock()
        uow.chats.add = MagicMock()

        created_msgs = []

        async def _capture(msg):
            msg.id = uuid.uuid4()
            msg.created_at = datetime.now(UTC)
            msg.read_status = False
            msg.sender = None
            msg.attachments = []
            created_msgs.append(msg)

        uow.chats.create_message = AsyncMock(side_effect=_capture)

        async def _get_last(ids):
            if not created_msgs:
                return {}
            m = created_msgs[0]
            mr = MagicMock()
            mr.model_dump.return_value = {
                "id": m.id,
                "chat_id": m.chat_id,
                "sender_id": m.sender_id,
                "content": m.content,
                "created_at": m.created_at,
                "read_status": False,
                "sender": None,
                "attachments": [],
            }
            return {m.id: mr}

        uow.chats.get_last_messages = AsyncMock(side_effect=_get_last)

        mock_file = MagicMock()
        mock_file.size = 1024
        attachment_svc = _mock_attachment_service()

        dispatcher = ChatMessageDispatcher(
            uow, attachment_svc, _mock_notification_service()
        )

        with patch("app.services.chat.command_service.ws_manager") as mock_ws:
            mock_ws.is_online = MagicMock(return_value=True)
            with patch("app.services.chat.command_service.cast") as mc:
                mc.return_value = MagicMock()
                result = await dispatcher.send_message(
                    chat.id, user, "With file", [mock_file], "en"
                )

        assert result is not None
        attachment_svc.process_upload.assert_called_once()


# ---------------------------------------------------------------------------
# ChatMaintenanceService.mark_read
# ---------------------------------------------------------------------------


class TestMarkRead:
    @pytest.mark.asyncio
    async def test_mark_read_success(self):
        # Wave 203 SW4 — mark_messages_read returns (read_at, affected); when
        # affected > 0 a chat-level read receipt is broadcast to the other
        # participant after commit.
        uow = _mock_uow()
        user = _mock_user()
        chat = _mock_chat(user.id)
        read_at = datetime.now(UTC)
        uow.chats.get_by_id = AsyncMock(return_value=chat)
        uow.chats.mark_messages_read = AsyncMock(return_value=(read_at, 2))

        svc = ChatMaintenanceService(uow, _mock_attachment_service())
        with patch(
            "app.services.chat.command_service.ws_manager.broadcast_to_chat",
            new=AsyncMock(),
        ) as broadcast:
            await svc.mark_read(chat.id, user, "en")

        uow.chats.mark_messages_read.assert_called_once_with(chat.id, user.id)
        uow.commit.assert_called_once()
        broadcast.assert_awaited_once()
        call = broadcast.await_args
        assert call.args[0] == chat.id
        frame = call.args[1]
        assert frame["type"] == "read"
        assert frame["chat_id"] == str(chat.id)
        assert frame["user_id"] == str(user.id)
        assert frame["read_at"] == read_at.isoformat()
        assert call.kwargs["exclude_user_id"] == user.id

    @pytest.mark.asyncio
    async def test_mark_read_no_unread_skips_broadcast(self):
        # affected == 0 (nothing new to mark) → no broadcast, no "Seen" churn.
        uow = _mock_uow()
        user = _mock_user()
        chat = _mock_chat(user.id)
        uow.chats.get_by_id = AsyncMock(return_value=chat)
        uow.chats.mark_messages_read = AsyncMock(return_value=(datetime.now(UTC), 0))

        svc = ChatMaintenanceService(uow, _mock_attachment_service())
        with patch(
            "app.services.chat.command_service.ws_manager.broadcast_to_chat",
            new=AsyncMock(),
        ) as broadcast:
            await svc.mark_read(chat.id, user, "en")

        uow.chats.mark_messages_read.assert_called_once_with(chat.id, user.id)
        uow.commit.assert_called_once()
        broadcast.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_mark_read_not_participant(self):
        uow = _mock_uow()
        user = _mock_user()
        other = _mock_user()
        chat = _mock_chat(other.id)  # user is NOT a participant
        uow.chats.get_by_id = AsyncMock(return_value=chat)

        svc = ChatMaintenanceService(uow, _mock_attachment_service())

        with pytest.raises(Exception):  # noqa: B017  # noqa: B017
            await svc.mark_read(chat.id, user, "en")

    @pytest.mark.asyncio
    async def test_mark_read_chat_not_found(self):
        uow = _mock_uow()
        uow.chats.get_by_id = AsyncMock(return_value=None)
        user = _mock_user()

        svc = ChatMaintenanceService(uow, _mock_attachment_service())

        with pytest.raises(Exception):  # noqa: B017  # ensure_exists
            await svc.mark_read(uuid.uuid4(), user, "en")


# ---------------------------------------------------------------------------
# ChatMaintenanceService.clear_history
# ---------------------------------------------------------------------------


class TestClearHistory:
    @pytest.mark.asyncio
    async def test_admin_clears_history(self):
        uow = _mock_uow()
        admin = _mock_user(role="admin")
        chat = _mock_chat(admin.id)
        chat.messages = [MagicMock(id=uuid.uuid4()), MagicMock(id=uuid.uuid4())]

        uow.chats.get_by_id = AsyncMock(return_value=chat)
        uow.chats.delete_messages = AsyncMock()
        uow.chats.update_timestamp_by_id = AsyncMock()
        uow.chats.add = MagicMock()

        attachment_svc = _mock_attachment_service()
        attachment_svc.collect_urls.return_value = []

        svc = ChatMaintenanceService(uow, attachment_svc)
        result = await svc.clear_history(chat.id, admin, "en")

        assert result.status == "cleared"
        assert result.deleted_messages == 2
        uow.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_admin_forbidden(self):
        uow = _mock_uow()
        user = _mock_user(role="student")
        chat = _mock_chat(user.id)
        uow.chats.get_by_id = AsyncMock(return_value=chat)

        svc = ChatMaintenanceService(uow, _mock_attachment_service())

        with pytest.raises(Exception):  # noqa: B017  # noqa: B017 (RACE-02)
            await svc.clear_history(chat.id, user, "en")

    @pytest.mark.asyncio
    async def test_clear_with_attachments(self):
        uow = _mock_uow()
        admin = _mock_user(role="admin")
        chat = _mock_chat(admin.id)
        chat.messages = [MagicMock(id=uuid.uuid4())]

        uow.chats.get_by_id = AsyncMock(return_value=chat)
        uow.chats.delete_messages = AsyncMock()
        uow.chats.update_timestamp_by_id = AsyncMock()
        uow.chats.add = MagicMock()

        attachment_svc = _mock_attachment_service()
        attachment_svc.collect_urls.return_value = ["https://s3.example.com/file1.pdf"]

        svc = ChatMaintenanceService(uow, attachment_svc)
        result = await svc.clear_history(chat.id, admin, "en")

        assert result.deleted_attachments == 1
        # StoredEvent should be added for attachment cleanup
        uow.chats.add.assert_called()


# ---------------------------------------------------------------------------
# ChatMaintenanceService.delete_chat
# ---------------------------------------------------------------------------


class TestDeleteChat:
    @pytest.mark.asyncio
    async def test_admin_deletes_chat(self):
        uow = _mock_uow()
        admin = _mock_user(role="admin")
        other = _mock_user()
        chat = _mock_chat(admin.id, other.id)
        chat.messages = []

        uow.chats.get_by_id = AsyncMock(return_value=chat)
        uow.chats.delete_chat = AsyncMock()
        uow.chats.add = MagicMock()

        attachment_svc = _mock_attachment_service()
        attachment_svc.collect_urls.return_value = []

        svc = ChatMaintenanceService(uow, attachment_svc)

        with (
            patch(
                "app.services.chat.command_service.invalidate_chat_participants_cache",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.chat.command_service.invalidate_presence_audience_cache",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.ws_hub_client.invalidate_ws_hub_cache",
                new_callable=AsyncMock,
            ),
        ):
            result = await svc.delete_chat(chat.id, admin, "en")

        assert result.status == "deleted"
        uow.chats.delete_chat.assert_called_once_with(chat.id)
        uow.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_admin_forbidden(self):
        uow = _mock_uow()
        user = _mock_user(role="student")
        chat = _mock_chat(user.id)
        uow.chats.get_by_id = AsyncMock(return_value=chat)

        svc = ChatMaintenanceService(uow, _mock_attachment_service())

        with pytest.raises(Exception):  # noqa: B017
            await svc.delete_chat(chat.id, user, "en")

    @pytest.mark.asyncio
    async def test_delete_with_attachments(self):
        uow = _mock_uow()
        admin = _mock_user(role="admin")
        chat = _mock_chat(admin.id)
        chat.messages = [MagicMock(id=uuid.uuid4())]

        uow.chats.get_by_id = AsyncMock(return_value=chat)
        uow.chats.delete_chat = AsyncMock()
        uow.chats.add = MagicMock()

        attachment_svc = _mock_attachment_service()
        attachment_svc.collect_urls.return_value = [
            "https://s3.example.com/a.pdf",
            "https://s3.example.com/b.png",
        ]

        svc = ChatMaintenanceService(uow, attachment_svc)

        with (
            patch(
                "app.services.chat.command_service.invalidate_chat_participants_cache",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.chat.command_service.invalidate_presence_audience_cache",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.ws_hub_client.invalidate_ws_hub_cache",
                new_callable=AsyncMock,
            ),
        ):
            result = await svc.delete_chat(chat.id, admin, "en")

        assert result.deleted_attachments == 2
        # Both ChatDeleted + AttachmentCleanupRequested StoredEvents
        assert uow.chats.add.call_count >= 2

    @pytest.mark.asyncio
    async def test_delete_chat_not_found(self):
        uow = _mock_uow()
        uow.chats.get_by_id = AsyncMock(return_value=None)
        admin = _mock_user(role="admin")

        svc = ChatMaintenanceService(uow, _mock_attachment_service())

        with pytest.raises(Exception):  # noqa: B017
            await svc.delete_chat(uuid.uuid4(), admin, "en")

    @pytest.mark.asyncio
    async def test_non_participant_non_admin(self):
        uow = _mock_uow()
        user = _mock_user(role="student")
        other = _mock_user()
        chat = _mock_chat(other.id)  # user is NOT a participant
        uow.chats.get_by_id = AsyncMock(return_value=chat)

        svc = ChatMaintenanceService(uow, _mock_attachment_service())

        with pytest.raises(Exception):  # noqa: B017
            await svc.delete_chat(chat.id, user, "en")
