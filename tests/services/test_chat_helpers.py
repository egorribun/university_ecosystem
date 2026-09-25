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

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from sqlalchemy import select

from app.api.ws.serializers import serialize_message
from app.models import Notification
from app.services.chat.attachment_service import ChatAttachmentService
from app.services.chat.notification_service import ChatNotificationService
from app.services.storage import S3Storage, StaticFSStorage

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


@pytest.mark.asyncio
async def test_durable_cleanup_retries_partial_s3_delete_without_acknowledging_it(
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A swallowed S3 delete failure must keep the outbox event retryable."""
    remaining = {"chat/a", "chat/b", "chat/c"}
    attempts: list[str] = []
    client = AsyncMock()

    async def delete_object(*, Bucket: str, Key: str) -> None:
        assert Bucket == "attachments"
        attempts.append(Key)
        if Key == "chat/b" and attempts.count(Key) == 1:
            raise ConnectionError("private-user@example.edu")
        remaining.discard(Key)

    async def head_object(*, Bucket: str, Key: str) -> dict[str, str]:
        assert Bucket == "attachments"
        if Key not in remaining:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {}

    client.delete_object.side_effect = delete_object
    client.head_object.side_effect = head_object
    backend = S3Storage(
        bucket="attachments", client=client, base_url="https://objects.example.test"
    )
    urls = [f"https://objects.example.test/{key}" for key in sorted(remaining)]
    service = ChatAttachmentService()

    with (
        patch("app.utils.files._get_storage_backend", return_value=backend),
        patch("app.services.storage.logger.warning") as warning,
    ):
        with pytest.raises(RuntimeError) as exc_info:
            await service.cleanup_files(urls, durable=True)
        assert "private-user@example.edu" not in str(exc_info.value)
        assert remaining == {"chat/b"}
        assert set(attempts) == {"chat/a", "chat/b", "chat/c"}

        await service.cleanup_files(urls, durable=True)

    assert not remaining
    assert attempts.count("chat/b") == 2
    assert "private-user@example.edu" not in caplog.text
    output = capsys.readouterr()
    assert "private-user@example.edu" not in output.out + output.err
    assert warning.call_count == 1
    assert all(
        "chat/b" not in str(call) and "private-user@example.edu" not in str(call)
        for call in warning.call_args_list
    )


@pytest.mark.asyncio
async def test_durable_cleanup_rejects_unmanaged_s3_url() -> None:
    """An old/foreign endpoint cannot be silently mistaken for deleted data."""
    client = AsyncMock()
    backend = S3Storage(
        bucket="attachments", client=client, base_url="https://objects.example.test"
    )
    with patch(
        "app.utils.files._get_storage_backend",
        return_value=backend,
    ):
        with pytest.raises(RuntimeError, match="Attachment cleanup failed"):
            await ChatAttachmentService().cleanup_files(
                ["https://old-private.example.test/chat/a"], durable=True
            )
    client.delete_object.assert_not_awaited()


@pytest.mark.asyncio
async def test_durable_cleanup_rejects_noncanonical_static_url(tmp_path: Path) -> None:
    backend = StaticFSStorage(tmp_path, base_url="/static")
    await backend.save_file("wrong/path.txt", b"keep")
    with patch("app.utils.files._get_storage_backend", return_value=backend):
        with pytest.raises(RuntimeError, match="Attachment cleanup failed"):
            await ChatAttachmentService().cleanup_files(
                ["/wrong/path.txt"], durable=True
            )
    assert await backend.exists("/static/wrong/path.txt")


@pytest.mark.asyncio
async def test_durable_cleanup_rejects_static_base_without_file(tmp_path: Path) -> None:
    backend = StaticFSStorage(tmp_path, base_url="/static")
    with patch("app.utils.files._get_storage_backend", return_value=backend):
        with pytest.raises(RuntimeError, match="Attachment cleanup failed"):
            await ChatAttachmentService().cleanup_files(["/static"], durable=True)


@pytest.mark.asyncio
async def test_durable_cleanup_accepts_canonical_static_url_without_base_prefix(
    tmp_path: Path,
) -> None:
    backend = StaticFSStorage(tmp_path, base_url="")
    url = await backend.save_file("chat/a.txt", b"delete me")
    assert url == "/chat/a.txt"
    with patch("app.utils.files._get_storage_backend", return_value=backend):
        await ChatAttachmentService().cleanup_files([url], durable=True)
    assert not await backend.exists(url)


@pytest.mark.asyncio
async def test_durable_static_delete_failure_does_not_log_private_path(
    tmp_path: Path,
) -> None:
    backend = StaticFSStorage(tmp_path, base_url="/static")
    await backend.save_file("chat/private-user@example.edu.txt", b"keep")
    with (
        patch("app.utils.files._get_storage_backend", return_value=backend),
        patch.object(Path, "unlink", side_effect=PermissionError("private-token")),
        patch("app.services.storage.logger.warning") as warning,
    ):
        with pytest.raises(RuntimeError, match="Attachment cleanup failed"):
            await ChatAttachmentService().cleanup_files(
                ["/static/chat/private-user@example.edu.txt"], durable=True
            )
    assert warning.call_count == 1
    assert "private-user@example.edu" not in str(warning.call_args)
    assert "private-token" not in str(warning.call_args)


@pytest.mark.asyncio
async def test_durable_cleanup_sanitizes_verification_failure() -> None:
    backend = SimpleNamespace(
        delete_file=AsyncMock(),
        exists=AsyncMock(side_effect=OSError("private-user@example.edu")),
    )
    with patch("app.utils.files._get_storage_backend", return_value=backend):
        with pytest.raises(RuntimeError, match="Attachment cleanup failed") as exc_info:
            await ChatAttachmentService().cleanup_files(
                ["/static/chat/a"], durable=True
            )
    assert "private-user@example.edu" not in str(exc_info.value)
    assert exc_info.value.__cause__ is None


@pytest.mark.asyncio
async def test_durable_cleanup_preserves_cancellation() -> None:
    backend = SimpleNamespace(
        delete_file=AsyncMock(side_effect=asyncio.CancelledError()),
        exists=AsyncMock(),
    )
    with patch("app.utils.files._get_storage_backend", return_value=backend):
        with pytest.raises(asyncio.CancelledError):
            await ChatAttachmentService().cleanup_files(
                ["/static/chat/a"], durable=True
            )
    backend.exists.assert_not_awaited()


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


def _notification_session() -> MagicMock:
    """Model an empty persisted notification set for isolated fan-out tests."""
    session = MagicMock()
    session.get_bind.return_value.dialect.name = "sqlite"
    session.execute = AsyncMock(return_value=MagicMock())
    session.execute.return_value.all.return_value = []
    return session


@pytest.mark.asyncio
async def test_notify_new_message_broadcasts_via_ws_excluding_sender() -> None:
    sender = _user(uuid.uuid4(), full_name="Alice")
    other = _user(uuid.uuid4())
    chat_id = uuid.uuid4()
    message = _msg(chat_id=chat_id, sender_id=sender.id, content="hi")

    session = _notification_session()
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

    session = _notification_session()
    svc = ChatNotificationService(session)

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
    assert kwargs["topic"] == "chat.message.created"
    assert kwargs["dedupe_key"] == f"chat-message:{message.id}"
    assert kwargs["push_via_outbox_only"] is True
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
async def test_replayed_message_creates_one_persistent_notification_per_recipient(
    db_session, user_factory
) -> None:
    """Outbox redelivery must reuse the message identity, not insert another bell row."""
    sender = await user_factory()
    recipient = await user_factory()
    chat_id = uuid.uuid4()
    message = _msg(chat_id=chat_id, sender_id=sender.id, content="hello")
    service = ChatNotificationService(db_session)

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
    ):
        await service.notify_new_message(message, [sender, recipient], sender)
        await db_session.commit()
        await service.notify_new_message(message, [sender, recipient], sender)
        await db_session.commit()

    rows = (
        (
            await db_session.execute(
                select(Notification).where(Notification.user_id == recipient.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].dedupe_key == f"chat-message:{message.id}"


@pytest.mark.asyncio
async def test_replayed_message_only_notifies_a_new_recipient(
    db_session, user_factory
) -> None:
    sender = await user_factory()
    first = await user_factory()
    later = await user_factory()
    message = _msg(chat_id=uuid.uuid4(), sender_id=sender.id, content="hello")
    service = ChatNotificationService(db_session)

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
    ):
        await service.notify_new_message(message, [sender, first], sender)
        await db_session.commit()
        await service.notify_new_message(message, [sender, first, later, first], sender)
        await db_session.commit()

    rows = (await db_session.execute(select(Notification))).scalars().all()
    assert {(row.user_id, row.dedupe_key) for row in rows} == {
        (first.id, f"chat-message:{message.id}"),
        (later.id, f"chat-message:{message.id}"),
    }
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_replayed_reply_preserves_one_notification_of_each_kind(
    db_session, user_factory
) -> None:
    sender = await user_factory()
    quoted = await user_factory()
    third = await user_factory()
    message = _msg(chat_id=uuid.uuid4(), sender_id=sender.id, content="reply")
    replied = _replied(message_id=uuid.uuid4(), sender_id=quoted.id)
    service = ChatNotificationService(db_session)

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
    ):
        for _ in range(2):
            await service.notify_new_message(
                message, [sender, quoted, third], sender, replied=replied
            )
            await db_session.commit()

    rows = (await db_session.execute(select(Notification))).scalars().all()
    assert {(row.user_id, row.type, row.dedupe_key) for row in rows} == {
        (quoted.id, "chat.reply", f"chat-reply:{message.id}"),
        (third.id, "chat.message", f"chat-message:{message.id}"),
    }


@pytest.mark.asyncio
async def test_reply_to_departed_member_never_leaks_current_chat_to_them(
    db_session, user_factory
) -> None:
    sender = await user_factory()
    current_member = await user_factory()
    departed_member = await user_factory()
    message = _msg(chat_id=uuid.uuid4(), sender_id=sender.id, content="private update")
    replied = _replied(message_id=uuid.uuid4(), sender_id=departed_member.id)
    service = ChatNotificationService(db_session)

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
    ):
        await service.notify_new_message(
            message, [sender, current_member], sender, replied=replied
        )
        await db_session.commit()

    rows = (await db_session.execute(select(Notification))).scalars().all()
    assert [(row.user_id, row.type) for row in rows] == [
        (current_member.id, "chat.message")
    ]


@pytest.mark.asyncio
async def test_replay_fills_only_missing_reply_notification(
    db_session, user_factory
) -> None:
    sender = await user_factory()
    quoted = await user_factory()
    third = await user_factory()
    message = _msg(chat_id=uuid.uuid4(), sender_id=sender.id, content="reply")
    replied = _replied(message_id=uuid.uuid4(), sender_id=quoted.id)
    service = ChatNotificationService(db_session)

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
    ):
        await service.notify_new_message(message, [sender, third], sender)
        await db_session.commit()
        await service.notify_new_message(
            message, [sender, quoted, third], sender, replied=replied
        )
        await db_session.commit()

    rows = (await db_session.execute(select(Notification))).scalars().all()
    assert {(row.user_id, row.type, row.dedupe_key) for row in rows} == {
        (quoted.id, "chat.reply", f"chat-reply:{message.id}"),
        (third.id, "chat.message", f"chat-message:{message.id}"),
    }


@pytest.mark.asyncio
async def test_notify_new_message_truncates_long_body() -> None:
    """Bodies over 100 chars are clipped + '...' appended."""
    sender = _user(uuid.uuid4(), full_name="Alice")
    chat_id = uuid.uuid4()
    long_body = "x" * 250
    message = _msg(chat_id=chat_id, sender_id=sender.id, content=long_body)

    svc = ChatNotificationService(_notification_session())

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

    svc = ChatNotificationService(_notification_session())

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

    svc = ChatNotificationService(_notification_session())

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
        # Wave 205 SW4 — serialize_message now reads edited_at/deleted_at; the
        # stand-in must carry them (None) or .isoformat()-access AttributeErrors.
        edited_at=None,
        deleted_at=None,
        # Wave 211 — serialize_message reads forwarded_from_name (a plain scalar).
        forwarded_from_name=None,
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


# ── 5. handle_message_sent fetches the sender explicitly (Wave 205) ───────────


@pytest.mark.asyncio
async def test_handle_message_sent_fetches_sender_by_id_not_noload_relationship() -> (
    None
):
    """Wave 205 regression: the outbox handler must load the sender via
    db.get(User, sender_id), NOT pass message.sender (which is lazy="noload"
    -> None after db.get(Message)). Passing message.sender crashed on sender.id
    the first time this handler ran end-to-end — dormant for waves because the
    outbox produced ZERO events until the SW-A capture-on-commit fix.
    """
    import app.services.event_handlers as eh
    from app import models as app_models
    from app.core.events import MessageSent

    message_id = uuid.uuid4()
    chat_id = uuid.uuid4()
    sender_id = uuid.uuid4()

    # db.get(Message) returns a message whose .sender is None (noload).
    message = SimpleNamespace(
        id=message_id,
        chat_id=chat_id,
        sender_id=sender_id,
        sender=None,
        content="hi",
        reply_to_message_id=None,  # Wave 207 — handle_message_sent reads this attr
    )
    fetched_sender = SimpleNamespace(id=sender_id, profile=None)

    async def fake_get(model: object, _ident: object) -> object | None:
        if model is app_models.Message:
            return message
        if model is app_models.User:
            return fetched_sender
        return None

    db = MagicMock()
    db.get = AsyncMock(side_effect=fake_get)
    db.commit = AsyncMock()

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=db)
    session_cm.__aexit__ = AsyncMock(return_value=False)

    repo = MagicMock()
    # Wave 210 G3 — the handler now reads chat.chat_type/name (a ChatDTO) to
    # thread the group identity into notify_new_message; the stand-in must carry
    # them or attribute access AttributeErrors.
    repo.get_by_id = AsyncMock(
        return_value=SimpleNamespace(
            participants=[fetched_sender], chat_type="dm", name=None
        )
    )

    service = MagicMock()
    service.notify_new_message = AsyncMock()

    event = MessageSent(message_id=message_id, chat_id=chat_id, sender_id=sender_id)

    with (
        patch("app.services.event_handlers.async_session", return_value=session_cm),
        patch("app.repositories.chat_repository.ChatRepository", return_value=repo),
        patch(
            "app.services.chat.notification_service.ChatNotificationService",
            return_value=service,
        ),
    ):
        await eh.handle_message_sent(event)

    service.notify_new_message.assert_awaited_once()
    kwargs = service.notify_new_message.await_args.kwargs
    # The fetched User — never the noload None relationship.
    assert kwargs["sender"] is fetched_sender
    assert kwargs["sender"] is not None
    assert kwargs["message"] is message
    # Wave 210 G3 — a DM chat threads chat_type="dm" + chat_name=None.
    assert kwargs["chat_type"] == "dm"
    assert kwargs["chat_name"] is None


# ── 6. Reply-notification SUPERSEDE (Wave 208) ───────────────────────────────


def _replied(*, message_id: uuid.UUID, sender_id: uuid.UUID) -> SimpleNamespace:
    """A replied-to MessageDTO stand-in.

    notify_new_message reads ONLY ``.id`` + ``.sender_id`` off ``replied`` for the
    supersede push path (serialize_message is patched in these tests, so its other
    fields are irrelevant). The real object is a ``MessageDTO`` which carries both
    (app/schemas/dtos/chat.py).
    """
    return SimpleNamespace(id=message_id, sender_id=sender_id)


@pytest.mark.asyncio
async def test_notify_reply_supersedes_quoted_author_off_generic() -> None:
    """X replies to Y in a 3-person chat → Y is dropped from the generic
    chat.message (only Z keeps it) and Y gets a specific chat.reply entry."""
    sender = _user(uuid.uuid4(), full_name="Alice")  # X — replier
    quoted = _user(uuid.uuid4())  # Y — author of the replied-to message
    third = _user(uuid.uuid4())  # Z — unrelated participant
    chat_id = uuid.uuid4()
    message = _msg(chat_id=chat_id, sender_id=sender.id, content="re: hi")
    replied = _replied(message_id=uuid.uuid4(), sender_id=quoted.id)

    session = _notification_session()
    svc = ChatNotificationService(session)

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
        await svc.notify_new_message(
            message, [sender, quoted, third], sender, replied=replied
        )

    assert create.await_count == 2
    by_type = {call.kwargs["type"]: call.kwargs for call in create.await_args_list}
    assert set(by_type) == {"chat.message", "chat.reply"}

    # Generic chat.message excludes the quoted author (supersede).
    generic = by_type["chat.message"]
    assert set(generic["user_ids"]) == {third.id}
    assert quoted.id not in generic["user_ids"]

    # Specific chat.reply goes ONLY to the quoted author.
    reply = by_type["chat.reply"]
    assert reply["user_ids"] == [quoted.id]
    assert reply["title"] == "Alice"
    assert reply["body"] == "re: hi"
    assert reply["url"] == f"/messenger/{chat_id}"
    assert reply["tag"] == f"chat-reply:{replied.id}"
    assert reply["dedupe_key"] == f"chat-reply:{message.id}"
    assert reply["push_via_outbox_only"] is True
    assert reply["topic"] == "chat.message.created"
    payload = reply["payload_data"]
    assert payload["chatId"] == str(chat_id)
    assert payload["repliedToMessageId"] == str(replied.id)
    assert payload["replyingMessageId"] == str(message.id)
    assert payload["senderId"] == str(sender.id)
    # All payload UUIDs stringified for JSON safety.
    assert all(isinstance(v, str) for v in payload.values())
    assert all(call.args and call.args[0] is session for call in create.await_args_list)


@pytest.mark.asyncio
async def test_notify_reply_in_dm_sends_only_chat_reply() -> None:
    """In a 1-on-1 DM the quoted author is the ONLY other participant, so after
    supersede the generic list is empty → exactly one chat.reply, no chat.message."""
    sender = _user(uuid.uuid4(), full_name="Alice")
    quoted = _user(uuid.uuid4())
    chat_id = uuid.uuid4()
    message = _msg(chat_id=chat_id, sender_id=sender.id, content="re: hi")
    replied = _replied(message_id=uuid.uuid4(), sender_id=quoted.id)

    svc = ChatNotificationService(_notification_session())

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
        await svc.notify_new_message(message, [sender, quoted], sender, replied=replied)

    create.assert_awaited_once()
    kwargs = create.await_args.kwargs
    assert kwargs["type"] == "chat.reply"
    assert kwargs["user_ids"] == [quoted.id]
    assert kwargs["dedupe_key"] == f"chat-reply:{message.id}"


@pytest.mark.asyncio
async def test_notify_self_reply_keeps_generic_no_chat_reply() -> None:
    """Replying to your OWN message is NOT a reply-to-other → no supersede, no
    chat.reply; the generic chat.message is sent unchanged."""
    sender = _user(uuid.uuid4(), full_name="Alice")
    other = _user(uuid.uuid4())
    chat_id = uuid.uuid4()
    message = _msg(chat_id=chat_id, sender_id=sender.id, content="re: my own")
    replied = _replied(message_id=uuid.uuid4(), sender_id=sender.id)  # self-reply

    svc = ChatNotificationService(_notification_session())

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
        await svc.notify_new_message(message, [sender, other], sender, replied=replied)

    create.assert_awaited_once()
    kwargs = create.await_args.kwargs
    assert kwargs["type"] == "chat.message"
    assert set(kwargs["user_ids"]) == {other.id}


@pytest.mark.asyncio
async def test_handle_message_sent_loads_replied_for_reply() -> None:
    """Wave 208: when the stored message is a reply, the outbox handler loads the
    replied-to message via repo.get_message_by_id and threads it into
    notify_new_message as ``replied`` (which then drives the supersede)."""
    import app.services.event_handlers as eh
    from app import models as app_models
    from app.core.events import MessageSent

    message_id = uuid.uuid4()
    chat_id = uuid.uuid4()
    sender_id = uuid.uuid4()
    reply_target_id = uuid.uuid4()
    quoted_sender_id = uuid.uuid4()

    message = SimpleNamespace(
        id=message_id,
        chat_id=chat_id,
        sender_id=sender_id,
        sender=None,
        content="re: hi",
        reply_to_message_id=reply_target_id,  # this message IS a reply
    )
    fetched_sender = SimpleNamespace(id=sender_id, profile=None)
    replied_dto = SimpleNamespace(id=reply_target_id, sender_id=quoted_sender_id)

    async def fake_get(model: object, _ident: object) -> object | None:
        if model is app_models.Message:
            return message
        if model is app_models.User:
            return fetched_sender
        return None

    db = MagicMock()
    db.get = AsyncMock(side_effect=fake_get)
    db.commit = AsyncMock()

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=db)
    session_cm.__aexit__ = AsyncMock(return_value=False)

    repo = MagicMock()
    repo.get_by_id = AsyncMock(
        return_value=SimpleNamespace(
            participants=[
                fetched_sender,
                SimpleNamespace(id=quoted_sender_id, profile=None),
            ],
            chat_type="dm",
            name=None,
        )
    )
    repo.get_message_by_id = AsyncMock(return_value=replied_dto)

    service = MagicMock()
    service.notify_new_message = AsyncMock()

    event = MessageSent(message_id=message_id, chat_id=chat_id, sender_id=sender_id)

    with (
        patch("app.services.event_handlers.async_session", return_value=session_cm),
        patch("app.repositories.chat_repository.ChatRepository", return_value=repo),
        patch(
            "app.services.chat.notification_service.ChatNotificationService",
            return_value=service,
        ),
    ):
        await eh.handle_message_sent(event)

    # The handler resolved the replied-to message and passed it through.
    repo.get_message_by_id.assert_awaited_once_with(reply_target_id)
    service.notify_new_message.assert_awaited_once()
    assert service.notify_new_message.await_args.kwargs["replied"] is replied_dto


# ── 7. Group notification re-tiering (Wave 210 G3) ───────────────────────────


@pytest.mark.asyncio
async def test_notify_group_message_titles_by_group_name_and_fans_out() -> None:
    """A GROUP push titles by the group name + prefixes the body with the sender,
    and fans the generic chat.message out to ALL non-sender members."""
    sender = _user(uuid.uuid4(), full_name="Alice")
    b = _user(uuid.uuid4())
    c = _user(uuid.uuid4())
    d = _user(uuid.uuid4())
    chat_id = uuid.uuid4()
    message = _msg(chat_id=chat_id, sender_id=sender.id, content="hello")

    svc = ChatNotificationService(_notification_session())

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
        await svc.notify_new_message(
            message,
            [sender, b, c, d],
            sender,
            chat_type="group",
            chat_name="Team",
        )

    create.assert_awaited_once()
    kwargs = create.await_args.kwargs
    assert kwargs["type"] == "chat.message"
    # Group identity: title is the group name, body is sender-prefixed.
    assert kwargs["title"] == "Team"
    assert kwargs["body"] == "Alice: hello"
    # Fans out to every non-sender member.
    assert set(kwargs["user_ids"]) == {b.id, c.id, d.id}


@pytest.mark.asyncio
async def test_notify_group_reply_supersede_carries_group_name() -> None:
    """Reply-supersede still works inside a group AND both the generic + reply
    entries carry the group's identity (title=name, sender-prefixed body)."""
    sender = _user(uuid.uuid4(), full_name="Alice")  # replier
    quoted = _user(uuid.uuid4())  # author of the replied-to message
    third = _user(uuid.uuid4())  # unrelated member
    chat_id = uuid.uuid4()
    message = _msg(chat_id=chat_id, sender_id=sender.id, content="re: hi")
    replied = _replied(message_id=uuid.uuid4(), sender_id=quoted.id)

    svc = ChatNotificationService(_notification_session())

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
        await svc.notify_new_message(
            message,
            [sender, quoted, third],
            sender,
            replied=replied,
            chat_type="group",
            chat_name="Team",
        )

    assert create.await_count == 2
    by_type = {call.kwargs["type"]: call.kwargs for call in create.await_args_list}
    assert set(by_type) == {"chat.message", "chat.reply"}

    # Supersede preserved: generic excludes the quoted author.
    assert set(by_type["chat.message"]["user_ids"]) == {third.id}
    # Both entries carry the group identity.
    for kwargs in by_type.values():
        assert kwargs["title"] == "Team"
        assert kwargs["body"] == "Alice: re: hi"
    # The reply entry still goes only to the quoted author.
    assert by_type["chat.reply"]["user_ids"] == [quoted.id]


@pytest.mark.asyncio
async def test_handle_message_sent_threads_group_identity() -> None:
    """Wave 210 G3 — the outbox handler threads chat_type/chat_name from the chat
    DTO into notify_new_message so a group push is re-tiered."""
    import app.services.event_handlers as eh
    from app import models as app_models
    from app.core.events import MessageSent

    message_id = uuid.uuid4()
    chat_id = uuid.uuid4()
    sender_id = uuid.uuid4()

    message = SimpleNamespace(
        id=message_id,
        chat_id=chat_id,
        sender_id=sender_id,
        sender=None,
        content="hi",
        reply_to_message_id=None,
    )
    fetched_sender = SimpleNamespace(id=sender_id, profile=None)

    async def fake_get(model: object, _ident: object) -> object | None:
        if model is app_models.Message:
            return message
        if model is app_models.User:
            return fetched_sender
        return None

    db = MagicMock()
    db.get = AsyncMock(side_effect=fake_get)
    db.commit = AsyncMock()

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=db)
    session_cm.__aexit__ = AsyncMock(return_value=False)

    repo = MagicMock()
    repo.get_by_id = AsyncMock(
        return_value=SimpleNamespace(
            participants=[fetched_sender], chat_type="group", name="Team"
        )
    )

    service = MagicMock()
    service.notify_new_message = AsyncMock()

    event = MessageSent(message_id=message_id, chat_id=chat_id, sender_id=sender_id)

    with (
        patch("app.services.event_handlers.async_session", return_value=session_cm),
        patch("app.repositories.chat_repository.ChatRepository", return_value=repo),
        patch(
            "app.services.chat.notification_service.ChatNotificationService",
            return_value=service,
        ),
    ):
        await eh.handle_message_sent(event)

    service.notify_new_message.assert_awaited_once()
    kwargs = service.notify_new_message.await_args.kwargs
    assert kwargs["chat_type"] == "group"
    assert kwargs["chat_name"] == "Team"
