"""Unit tests for the smaller chat-service modules.

The full chat services (``query_service``, ``command_service``,
``creation_service``) are heavy orchestrators that pull in repositories,
WebSocket managers, push delivery, file scanners, etc. We focus here on
the deterministic helpers + the notification fan-out:

* ``ChatAttachmentService.cleanup_files`` — best-effort batch delete via
  ``asyncio.gather(..., return_exceptions=True)`` (one failure does not
  block the rest);
* ``ChatAttachmentService.collect_urls`` — collects every non-empty
  attachment URL across the chat's messages;
* ``ChatNotificationService.notify_new_message`` — broadcasts via the
  WS manager (excluding the sender), creates push notifications for
  the *other* participants, truncates body preview at 100 chars,
  composes the right URL/tag/payload_data with stringified UUIDs.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.ws.serializers import serialize_message
from app.services.chat.attachment_service import ChatAttachmentService
from app.services.chat.notification_service import ChatNotificationService

# ── 1. ChatAttachmentService.cleanup_files ───────────────────────────────────


@pytest.mark.asyncio
async def test_cleanup_files_skips_empty_input() -> None:
    """An empty list of URLs is a no-op."""
    svc = ChatAttachmentService()
    with patch("app.services.chat.attachment_service.delete_static_file") as deleter:
        await svc.cleanup_files([])
    deleter.assert_not_called()


@pytest.mark.asyncio
async def test_cleanup_files_skips_falsy_urls() -> None:
    """Empty strings and None values are filtered out before deletion."""
    svc = ChatAttachmentService()
    with patch(
        "app.services.chat.attachment_service.delete_static_file",
        new=AsyncMock(),
    ) as deleter:
        await svc.cleanup_files(["", "/static/a", "/static/b", ""])
    # Two real URLs, two filtered out.
    assert deleter.call_count == 2
    deleter.assert_any_call("/static/a")
    deleter.assert_any_call("/static/b")


@pytest.mark.asyncio
async def test_cleanup_files_continues_after_individual_failure() -> None:
    """One delete raising must not abort the rest (return_exceptions=True)."""
    calls: list[str] = []

    async def fake_delete(url: str) -> None:
        calls.append(url)
        if url == "/static/bad":
            raise OSError("permission denied")

    svc = ChatAttachmentService()
    with patch(
        "app.services.chat.attachment_service.delete_static_file",
        new=fake_delete,
    ):
        # Should not raise — failures are swallowed by gather(return_exceptions).
        await svc.cleanup_files(["/static/good", "/static/bad", "/static/also-good"])

    assert calls == ["/static/good", "/static/bad", "/static/also-good"]


# ── 2. ChatAttachmentService.collect_urls ────────────────────────────────────


def _attachment(url: str | None) -> SimpleNamespace:
    return SimpleNamespace(url=url)


def _message(*urls: str | None) -> SimpleNamespace:
    return SimpleNamespace(attachments=[_attachment(u) for u in urls])


def _chat(*messages: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(messages=list(messages))


@pytest.mark.asyncio
async def test_collect_urls_empty_chat_returns_empty() -> None:
    svc = ChatAttachmentService()
    chat = _chat()
    assert await svc.collect_urls(chat) == []


@pytest.mark.asyncio
async def test_collect_urls_aggregates_across_messages() -> None:
    """URLs from every message + attachment combine in iteration order."""
    svc = ChatAttachmentService()
    chat = _chat(
        _message("/a.png", "/b.png"),
        _message("/c.mp4"),
        _message(),  # message with no attachments
        _message("/d.pdf"),
    )
    assert await svc.collect_urls(chat) == ["/a.png", "/b.png", "/c.mp4", "/d.pdf"]


@pytest.mark.asyncio
async def test_collect_urls_skips_empty_url() -> None:
    """Attachments without a URL are silently skipped (cleanup-pre-emption)."""
    svc = ChatAttachmentService()
    chat = _chat(_message("/a.png", None, ""))
    assert await svc.collect_urls(chat) == ["/a.png"]


# ── 3. ChatNotificationService.notify_new_message ────────────────────────────


def _user(user_id: uuid.UUID, *, full_name: str | None = None) -> SimpleNamespace:
    profile = SimpleNamespace(full_name=full_name) if full_name is not None else None
    return SimpleNamespace(id=user_id, profile=profile)


def _msg(*, chat_id: uuid.UUID, sender_id: uuid.UUID, content: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        chat_id=chat_id,
        sender_id=sender_id,
        content=content,
        attachments=[],
    )


@pytest.mark.asyncio
async def test_notify_new_message_broadcasts_via_ws_excluding_sender() -> None:
    sender = _user(uuid.uuid4(), full_name="Alice")
    other = _user(uuid.uuid4())
    chat_id = uuid.uuid4()
    message = _msg(chat_id=chat_id, sender_id=sender.id, content="hi")

    session = MagicMock()
    svc = ChatNotificationService(session)

    with (
        patch(
            "app.services.chat.notification_service.build_presence_map",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "app.services.chat.notification_service.serialize_message",
            return_value={"id": str(message.id), "content": "hi"},
        ),
        patch(
            "app.services.chat.notification_service.ws_manager.broadcast_to_chat",
            new=AsyncMock(),
        ) as ws_broadcast,
        patch(
            "app.services.chat.notification_service.create_notifications_for_users",
            new=AsyncMock(),
        ),
    ):
        await svc.notify_new_message(message, [sender, other], sender)

    ws_broadcast.assert_awaited_once()
    call_args = ws_broadcast.await_args
    assert call_args.args[0] == chat_id
    payload = call_args.args[1]
    assert payload["type"] == "new_message"
    assert payload["chat_id"] == str(chat_id)
    # Sender is excluded from the WS broadcast.
    assert call_args.kwargs["exclude_user_id"] == sender.id


@pytest.mark.asyncio
async def test_notify_new_message_creates_push_for_other_participants() -> None:
    """``create_notifications_for_users`` is called with the non-sender list."""
    sender = _user(uuid.uuid4(), full_name="Alice")
    other_a = _user(uuid.uuid4())
    other_b = _user(uuid.uuid4())
    chat_id = uuid.uuid4()
    message = _msg(chat_id=chat_id, sender_id=sender.id, content="hello")

    svc = ChatNotificationService(MagicMock())

    with (
        patch(
            "app.services.chat.notification_service.build_presence_map",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "app.services.chat.notification_service.serialize_message",
            return_value={},
        ),
        patch(
            "app.services.chat.notification_service.ws_manager.broadcast_to_chat",
            new=AsyncMock(),
        ),
        patch(
            "app.services.chat.notification_service.create_notifications_for_users",
            new=AsyncMock(),
        ) as create,
    ):
        await svc.notify_new_message(message, [sender, other_a, other_b], sender)

    create.assert_awaited_once()
    kwargs = create.await_args.kwargs
    assert kwargs["title"] == "Alice"
    assert kwargs["body"] == "hello"
    assert kwargs["type"] == "chat.message"
    assert kwargs["url"] == f"/messenger/{chat_id}"
    assert kwargs["tag"] == f"chat:{chat_id}"
    assert set(kwargs["user_ids"]) == {other_a.id, other_b.id}
    # All UUIDs in payload_data are stringified for JSON safety.
    payload = kwargs["payload_data"]
    assert payload["chatId"] == str(chat_id)
    assert payload["senderId"] == str(sender.id)
    assert payload["messageId"] == str(message.id)
    assert isinstance(payload["chatId"], str)


@pytest.mark.asyncio
async def test_notify_new_message_truncates_long_body() -> None:
    """Bodies over 100 chars are clipped + '...' appended."""
    sender = _user(uuid.uuid4(), full_name="Alice")
    chat_id = uuid.uuid4()
    long_body = "x" * 250
    message = _msg(chat_id=chat_id, sender_id=sender.id, content=long_body)

    svc = ChatNotificationService(MagicMock())

    with (
        patch(
            "app.services.chat.notification_service.build_presence_map",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "app.services.chat.notification_service.serialize_message",
            return_value={},
        ),
        patch(
            "app.services.chat.notification_service.ws_manager.broadcast_to_chat",
            new=AsyncMock(),
        ),
        patch(
            "app.services.chat.notification_service.create_notifications_for_users",
            new=AsyncMock(),
        ) as create,
    ):
        await svc.notify_new_message(message, [sender, _user(uuid.uuid4())], sender)

    body = create.await_args.kwargs["body"]
    # First 100 chars + '...'
    assert body == "x" * 100 + "..."
    assert len(body) == 103


@pytest.mark.asyncio
async def test_notify_new_message_skips_push_when_only_sender() -> None:
    """If the sender is the only participant, no push is created."""
    sender = _user(uuid.uuid4(), full_name="Alice")
    chat_id = uuid.uuid4()
    message = _msg(chat_id=chat_id, sender_id=sender.id, content="hi")

    svc = ChatNotificationService(MagicMock())

    with (
        patch(
            "app.services.chat.notification_service.build_presence_map",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "app.services.chat.notification_service.serialize_message",
            return_value={},
        ),
        patch(
            "app.services.chat.notification_service.ws_manager.broadcast_to_chat",
            new=AsyncMock(),
        ),
        patch(
            "app.services.chat.notification_service.create_notifications_for_users",
            new=AsyncMock(),
        ) as create,
    ):
        await svc.notify_new_message(message, [sender], sender)

    create.assert_not_called()


@pytest.mark.asyncio
async def test_notify_new_message_falls_back_to_user_when_no_profile() -> None:
    """If sender has no profile, the push title falls back to 'User'."""
    sender = _user(uuid.uuid4(), full_name=None)  # profile is None
    other = _user(uuid.uuid4())
    chat_id = uuid.uuid4()
    message = _msg(chat_id=chat_id, sender_id=sender.id, content="hi")

    svc = ChatNotificationService(MagicMock())

    with (
        patch(
            "app.services.chat.notification_service.build_presence_map",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "app.services.chat.notification_service.serialize_message",
            return_value={},
        ),
        patch(
            "app.services.chat.notification_service.ws_manager.broadcast_to_chat",
            new=AsyncMock(),
        ),
        patch(
            "app.services.chat.notification_service.create_notifications_for_users",
            new=AsyncMock(),
        ) as create,
    ):
        await svc.notify_new_message(message, [sender, other], sender)

    assert create.await_args.kwargs["title"] == "User"


# ── 4. serialize_message read_at (Wave 203 SW3) ──────────────────────────────


def _serializable_message(read_at: datetime | None) -> SimpleNamespace:
    """A minimal Message ORM stand-in (sender=None so model_validate is skipped)."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        chat_id=uuid.uuid4(),
        sender_id=uuid.uuid4(),
        content="hi",
        created_at=datetime(2026, 5, 30, 14, 32, tzinfo=UTC),
        read_status=read_at is not None,
        read_at=read_at,
        sender=None,
        attachments=[],
    )


def test_serialize_message_includes_read_at_iso() -> None:
    """A read message serializes read_at as an ISO 8601 string."""
    ts = datetime(2026, 5, 30, 14, 32, tzinfo=UTC)
    result = serialize_message(_serializable_message(ts))
    assert result["read_at"] == ts.isoformat()


def test_serialize_message_read_at_none_when_unread() -> None:
    """An unread message serializes read_at as None (key present)."""
    result = serialize_message(_serializable_message(None))
    assert "read_at" in result
    assert result["read_at"] is None
