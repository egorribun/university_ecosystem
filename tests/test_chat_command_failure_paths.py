"""Failure-path tests for app/services/chat/command_service.py.

AsyncMock repo + fake-UoW harness (mirrors tests/test_chat_command_service.py
style) targeting the previously-uncovered error branches:

- send_message idempotency cache hit with a corrupt / legacy entry
  (occupied slots fail closed rather than duplicating a message);
- L207      send_message total attachment payload size guard;
- L234-239  idempotency "pending" slot pre-reservation (Redis SET NX);
- L278      upload TimeoutError -> errors.files.upload_timeout (except* arm);
- L283/285-290  Phase 1 failure cleanup (partial upload removal + slot release);
- L359-372  Phase 2 (DB write) failure cleanup arm (file cleanup + slot release
            + re-raise);
- L380-381  send_message degraded fallback when the post-commit reload misses;
- L430-436  idempotency completed-slot store (SETEX slim format);
- L502      forward_messages defensive TOCTOU reload-gap 404;
- L581-582  forward_messages degraded reload path (session.refresh + manual
            MessageResponse);
- L968      rename_chat whitespace-only name re-validation;
- L984      clear_history non-participant + non-admin forbidden;
- L1021-1023  clear_history commit-failure rollback + re-raise;
- L1093-1095  delete_chat commit-failure rollback + re-raise.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import fakeredis.aioredis
import pytest
from fastapi import HTTPException

import app.deps.cache as cache_module
import app.services.chat.command_service as cs_module
from app.services.chat.command_service import (
    ChatMaintenanceService,
    ChatMessageDispatcher,
)

# ---------------------------------------------------------------------------
# Helpers (mirroring tests/test_chat_command_service.py)
# ---------------------------------------------------------------------------


def _mock_uow():
    uow = MagicMock()
    uow.chats = MagicMock()
    uow.session = AsyncMock()
    uow.commit = AsyncMock()
    uow.rollback = AsyncMock()
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


def _mock_user(role: str = "student") -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "test@example.com"
    user.role = role
    return user


def _mock_chat(
    owner_id: uuid.UUID,
    *participant_ids: uuid.UUID,
    chat_type: str = "dm",
    created_by: uuid.UUID | None = None,
):
    chat = MagicMock()
    chat.id = uuid.uuid4()
    chat.created_at = datetime.now(UTC)
    chat.updated_at = datetime.now(UTC)
    chat.messages = []
    chat.chat_type = chat_type
    chat.created_by = created_by
    participants = []
    for pid in [owner_id, *participant_ids]:
        p = MagicMock()
        p.id = pid
        participants.append(p)
    chat.participants = participants
    return chat


def _patch_ws(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace the module-level ws_manager (consuming-module patch)."""
    ws = MagicMock()
    ws.is_online = MagicMock(return_value=False)
    ws.broadcast_to_chat = AsyncMock()
    monkeypatch.setattr(cs_module, "ws_manager", ws)
    return ws


async def _patch_cache(monkeypatch: pytest.MonkeyPatch):
    """Use real fakeredis transaction behavior at the cache boundary."""
    cache = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(cache_module, "get_cache_client", AsyncMock(return_value=cache))
    return cache


def _capture_create_message(uow) -> list:
    """create_message stand-in: stamps the flush-time fields on the real Message."""
    created: list = []

    async def _capture(msg):
        msg.id = uuid.uuid4()
        msg.created_at = datetime.now(UTC)
        msg.read_status = False
        msg.sender = None
        msg.attachments = []
        created.append(msg)

    uow.chats.create_message = AsyncMock(side_effect=_capture)
    return created


def _leaves(exc: BaseException) -> list[BaseException]:
    """Flatten (possibly nested) ExceptionGroups into leaf exceptions."""
    if isinstance(exc, BaseExceptionGroup):
        out: list[BaseException] = []
        for sub in exc.exceptions:
            out.extend(_leaves(sub))
        return out
    leaves = [exc]
    if exc.__context__ is not None and exc.__context__ is not exc:
        leaves.extend(_leaves(exc.__context__))
    return leaves


# ---------------------------------------------------------------------------
# send_message — total payload size guard (L207)
# ---------------------------------------------------------------------------


async def test_send_message_total_size_exceeded(monkeypatch):
    monkeypatch.setattr(cs_module.settings, "chat_attachment_max_files", 10)
    monkeypatch.setattr(cs_module.settings, "chat_attachment_max_total_bytes", 100)

    uow = _mock_uow()
    user = _mock_user()
    chat = _mock_chat(user.id)
    uow.chats.get_by_id = AsyncMock(return_value=chat)
    uow.chats.check_participant = AsyncMock(return_value=True)

    dispatcher = ChatMessageDispatcher(uow, _mock_attachment_service(), MagicMock())

    f1, f2 = MagicMock(size=80), MagicMock(size=80)
    with pytest.raises(HTTPException) as excinfo:
        await dispatcher.send_message(chat.id, user, "big", [f1, f2], "en")
    assert excinfo.value.status_code == 400
    uow.chats.create_message.assert_not_called()


# ---------------------------------------------------------------------------
# send_message — corrupt and pending entries cannot bypass slot ownership
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cached",
    [
        "not-json",  # ValueError from json.loads
        '{"status": "pending"}',  # KeyError: no message_id
        '{"message_id": "zzz"}',  # ValueError from uuid.UUID
    ],
)
async def test_send_message_existing_idempotency_entry_is_not_overwritten(
    monkeypatch, cached
):
    """A pending or malformed entry cannot grant ownership of an occupied key."""
    cache = await _patch_cache(monkeypatch)
    uow = _mock_uow()
    user = _mock_user()
    chat = _mock_chat(user.id)
    uow.chats.get_by_id = AsyncMock(return_value=chat)
    uow.chats.check_participant = AsyncMock(return_value=True)
    key = cs_module._make_idempotency_key(chat.id, user.id, "idem-corrupt")
    await cache.set(key, cached)
    dispatcher = ChatMessageDispatcher(uow, _mock_attachment_service(), MagicMock())
    try:
        with pytest.raises(HTTPException) as exc:
            await dispatcher.send_message(
                chat.id, user, "Hello", [], "en", idempotency_key="idem-corrupt"
            )
        assert exc.value.status_code == 409
        assert await cache.get(key) == cached
        uow.chats.create_message.assert_not_called()
    finally:
        await cache.aclose()


# ---------------------------------------------------------------------------
# send_message — upload TimeoutError maps to errors.files.upload_timeout
# ---------------------------------------------------------------------------


async def test_send_message_upload_timeout_maps_to_400(monkeypatch):
    monkeypatch.setattr(cs_module.settings, "chat_attachment_max_files", 5)
    _patch_ws(monkeypatch)

    uow = _mock_uow()
    user = _mock_user()
    chat = _mock_chat(user.id)
    uow.chats.get_by_id = AsyncMock(return_value=chat)
    uow.chats.check_participant = AsyncMock(return_value=True)

    attachment_svc = _mock_attachment_service()
    attachment_svc.process_upload = AsyncMock(side_effect=TimeoutError())

    dispatcher = ChatMessageDispatcher(uow, attachment_svc, MagicMock())

    with pytest.raises(HTTPException) as excinfo:
        await dispatcher.send_message(
            chat.id, user, "with file", [MagicMock(size=10)], "en"
        )

    assert excinfo.value.status_code == 400
    uow.chats.create_message.assert_not_called()


async def test_send_message_uses_first_original_http_failure_from_upload_group(
    monkeypatch,
):
    monkeypatch.setattr(cs_module.settings, "chat_attachment_max_files", 5)
    _patch_ws(monkeypatch)

    uow = _mock_uow()
    user = _mock_user()
    chat = _mock_chat(user.id)
    uow.chats.get_by_id = AsyncMock(return_value=chat)
    uow.chats.check_participant = AsyncMock(return_value=True)

    first_file, second_file = MagicMock(size=10), MagicMock(size=10)
    first_error = HTTPException(status_code=413, detail="first upload rejected")
    second_error = HTTPException(status_code=415, detail="second upload rejected")
    second_started = asyncio.Event()

    async def process_upload(upload, *_args, **_kwargs):
        if upload is first_file:
            await second_started.wait()
            raise first_error
        second_started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            raise second_error from None

    attachment_svc = _mock_attachment_service()
    attachment_svc.process_upload = AsyncMock(side_effect=process_upload)
    dispatcher = ChatMessageDispatcher(uow, attachment_svc, MagicMock())

    with pytest.raises(HTTPException) as excinfo:
        await dispatcher.send_message(
            chat.id, user, "with files", [first_file, second_file], "en"
        )

    assert excinfo.value is first_error
    assert excinfo.value.status_code == 413
    uow.chats.create_message.assert_not_called()


async def test_send_message_preserves_mixed_nested_upload_group_and_releases_slot(
    monkeypatch,
):
    monkeypatch.setattr(cs_module.settings, "chat_attachment_max_files", 5)
    cache = await _patch_cache(monkeypatch)
    _patch_ws(monkeypatch)

    uow = _mock_uow()
    user = _mock_user()
    chat = _mock_chat(user.id)
    uow.chats.get_by_id = AsyncMock(return_value=chat)
    uow.chats.check_participant = AsyncMock(return_value=True)

    first_file, second_file = MagicMock(size=10), MagicMock(size=10)
    first_error = HTTPException(status_code=413, detail="first upload rejected")
    nested_error = ExceptionGroup(
        "nested upload failure",
        [
            HTTPException(status_code=415, detail="second upload rejected"),
            RuntimeError("scanner failure"),
        ],
    )
    second_started = asyncio.Event()

    async def process_upload(upload, *_args, **_kwargs):
        if upload is first_file:
            await second_started.wait()
            raise first_error
        second_started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            raise nested_error from None

    attachment_svc = _mock_attachment_service()
    attachment_svc.process_upload = AsyncMock(side_effect=process_upload)
    dispatcher = ChatMessageDispatcher(uow, attachment_svc, MagicMock())

    try:
        with pytest.raises(ExceptionGroup) as excinfo:
            await dispatcher.send_message(
                chat.id,
                user,
                "with files",
                [first_file, second_file],
                "en",
                idempotency_key="mixed-upload-failure",
            )

        assert excinfo.value.exceptions == (first_error, nested_error)
        assert nested_error.exceptions[1].args == ("scanner failure",)
        assert not await cache.keys("idm:msg:*")
        uow.chats.create_message.assert_not_called()
    finally:
        await cache.aclose()


# ---------------------------------------------------------------------------
# send_message — Phase 1 failure cleanup (L282-283, L284-290)
# ---------------------------------------------------------------------------


async def test_send_message_phase1_failure_cleans_partial_uploads_and_slot(
    monkeypatch,
):
    """One upload succeeds, the second fails: the saved url must be cleaned up
    and the idempotency pending slot released (cache DELETE)."""
    monkeypatch.setattr(cs_module.settings, "chat_attachment_max_files", 5)
    cache = await _patch_cache(monkeypatch)
    _patch_ws(monkeypatch)

    uow = _mock_uow()
    user = _mock_user()
    chat = _mock_chat(user.id)
    uow.chats.get_by_id = AsyncMock(return_value=chat)
    uow.chats.check_participant = AsyncMock(return_value=True)

    good_file = MagicMock(size=10)
    bad_file = MagicMock(size=10)

    async def _process(upload, chat_id, *, locale):
        if upload is bad_file:
            # Yield once so the good upload (scheduled first) completes.
            await asyncio.sleep(0)
            raise RuntimeError("scan failed")
        return {
            "url": "https://s3.example.com/ok.bin",
            "file_type": "application/octet-stream",
            "filename": "ok.bin",
            "size": 10,
        }

    attachment_svc = _mock_attachment_service()
    attachment_svc.process_upload = AsyncMock(side_effect=_process)

    dispatcher = ChatMessageDispatcher(uow, attachment_svc, MagicMock())

    with pytest.raises(Exception) as excinfo:
        await dispatcher.send_message(
            chat.id,
            user,
            "with files",
            [good_file, bad_file],
            "en",
            idempotency_key="idem-phase1",
        )

    assert any(isinstance(leaf, RuntimeError) for leaf in _leaves(excinfo.value))
    # Partial upload removed (L282-283).
    attachment_svc.cleanup_files.assert_awaited_once_with(
        ["https://s3.example.com/ok.bin"]
    )
    # Pending slot released (L284-290).
    assert not await cache.keys("idm:msg:*")
    await cache.aclose()
    uow.chats.create_message.assert_not_called()


# ---------------------------------------------------------------------------
# send_message — Phase 2 (DB write) failure cleanup (L359-372)
# ---------------------------------------------------------------------------


async def test_send_message_phase2_failure_cleans_files_and_slot(monkeypatch):
    monkeypatch.setattr(cs_module.settings, "chat_attachment_max_files", 5)
    cache = await _patch_cache(monkeypatch)
    _patch_ws(monkeypatch)

    uow = _mock_uow()
    user = _mock_user()
    chat = _mock_chat(user.id)
    uow.chats.get_by_id = AsyncMock(return_value=chat)
    uow.chats.check_participant = AsyncMock(return_value=True)
    uow.chats.update_timestamp_by_id = AsyncMock()
    uow.chats.add = MagicMock()
    _capture_create_message(uow)
    uow.commit = AsyncMock(side_effect=RuntimeError("db down"))

    attachment_svc = _mock_attachment_service()
    dispatcher = ChatMessageDispatcher(uow, attachment_svc, MagicMock())

    with pytest.raises(RuntimeError, match="db down"):
        await dispatcher.send_message(
            chat.id,
            user,
            "with file",
            [MagicMock(size=10)],
            "en",
            idempotency_key="idem-phase2",
        )

    # Uploaded file cleaned up (L363-364) + pending slot released (L365-371).
    attachment_svc.cleanup_files.assert_awaited_once_with(
        ["https://s3.example.com/file.pdf"]
    )
    assert not await cache.keys("idm:msg:*")
    await cache.aclose()


# ---------------------------------------------------------------------------
# send_message — degraded fallback when the reload misses (L378-400)
# ---------------------------------------------------------------------------


async def test_send_message_fallback_when_reload_missing(monkeypatch):
    """get_last_messages returning {} forces the session.refresh fallback that
    builds the MessageResponse field-by-field from the ORM row (L380-381)."""
    _patch_ws(monkeypatch)

    uow = _mock_uow()
    user = _mock_user()
    chat = _mock_chat(user.id)
    uow.chats.get_by_id = AsyncMock(return_value=chat)
    uow.chats.check_participant = AsyncMock(return_value=True)
    uow.chats.update_timestamp_by_id = AsyncMock()
    uow.chats.add = MagicMock()
    created = _capture_create_message(uow)
    uow.chats.get_last_messages = AsyncMock(return_value={})

    dispatcher = ChatMessageDispatcher(uow, _mock_attachment_service(), MagicMock())
    result = await dispatcher.send_message(chat.id, user, "Hello fallback", [], "en")

    uow.session.refresh.assert_awaited_once_with(created[0])
    assert result.id == created[0].id
    assert result.content == "Hello fallback"
    assert result.read_status is False
    assert result.reply_to is None
    assert result.attachments == []


# ---------------------------------------------------------------------------
# forward_messages — defensive TOCTOU reload gap (L498-502)
# ---------------------------------------------------------------------------


async def test_forward_messages_reload_gap_raises_404(monkeypatch):
    _patch_ws(monkeypatch)

    uow = _mock_uow()
    user = _mock_user()
    dest_chat = _mock_chat(user.id)
    uow.chats.get_by_id = AsyncMock(return_value=dest_chat)
    uow.chats.check_participant = AsyncMock(return_value=True)
    uow.chats.message_exists_in_chat = AsyncMock(return_value=True)
    # Existence checks passed, but the batched load comes back short.
    uow.chats.get_last_messages = AsyncMock(return_value={})

    dispatcher = ChatMessageDispatcher(uow, _mock_attachment_service(), MagicMock())

    with pytest.raises(HTTPException) as excinfo:
        await dispatcher.forward_messages(
            dest_chat.id, user, uuid.uuid4(), [uuid.uuid4()], "en"
        )
    assert excinfo.value.status_code == 404
    uow.chats.create_message.assert_not_called()


# ---------------------------------------------------------------------------
# forward_messages — degraded reload path (L578-596, incl. L581-582)
# ---------------------------------------------------------------------------


async def test_forward_messages_degraded_reload_refreshes_orm(monkeypatch):
    """When the FINAL reload returns nothing, the response is built from the
    refreshed ORM row (session.refresh + field-by-field MessageResponse)."""
    _patch_ws(monkeypatch)

    uow = _mock_uow()
    user = _mock_user()
    dest_chat = _mock_chat(user.id)
    source_chat_id = uuid.uuid4()
    mid = uuid.uuid4()

    src = MagicMock()
    src.id = mid
    src.sender_id = uuid.uuid4()
    src.content = "forwarded text"
    src.attachments = []
    src.deleted_at = None

    uow.chats.get_by_id = AsyncMock(return_value=dest_chat)
    uow.chats.check_participant = AsyncMock(return_value=True)
    uow.chats.message_exists_in_chat = AsyncMock(return_value=True)
    # First call: source batch load; second call: post-commit reload misses.
    uow.chats.get_last_messages = AsyncMock(side_effect=[{mid: src}, {}])
    uow.chats.get_user_display_names = AsyncMock(
        return_value={src.sender_id: "Anna Original"}
    )
    uow.chats.update_timestamp_by_id = AsyncMock()
    uow.chats.add = MagicMock()
    created = _capture_create_message(uow)

    dispatcher = ChatMessageDispatcher(uow, _mock_attachment_service(), MagicMock())
    responses = await dispatcher.forward_messages(
        dest_chat.id, user, source_chat_id, [mid], "en"
    )

    assert len(responses) == 1
    resp = responses[0]
    uow.session.refresh.assert_awaited_once_with(created[0])
    assert resp.id == created[0].id
    assert resp.content == "forwarded text"
    assert resp.sender_id == user.id
    assert resp.forwarded_from_name == "Anna Original"
    assert resp.reply_to is None
    uow.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# rename_chat — whitespace-only name re-validation (L966-968)
# ---------------------------------------------------------------------------


async def test_rename_chat_whitespace_only_name_rejected():
    user = _mock_user()
    chat = _mock_chat(user.id, uuid.uuid4(), chat_type="group", created_by=user.id)
    uow = _mock_uow()
    uow.chats.get_by_id = AsyncMock(return_value=chat)
    uow.chats.rename_chat = AsyncMock()

    svc = ChatMaintenanceService(uow, _mock_attachment_service())

    with pytest.raises(HTTPException) as excinfo:
        await svc.rename_chat(chat.id, user, "   ", "en")
    assert excinfo.value.status_code == 400
    uow.chats.rename_chat.assert_not_called()
    uow.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# clear_history — non-participant + non-admin forbidden (L983-984)
# ---------------------------------------------------------------------------


async def test_clear_history_non_participant_non_admin_forbidden():
    user = _mock_user(role="student")
    chat = _mock_chat(uuid.uuid4())  # user is NOT a participant
    uow = _mock_uow()
    uow.chats.get_by_id = AsyncMock(return_value=chat)

    svc = ChatMaintenanceService(uow, _mock_attachment_service())

    with pytest.raises(HTTPException) as excinfo:
        await svc.clear_history(chat.id, user, "en")
    assert excinfo.value.status_code == 403


# ---------------------------------------------------------------------------
# clear_history — commit failure rolls back + re-raises (L1021-1023)
# ---------------------------------------------------------------------------


async def test_clear_history_commit_failure_rolls_back():
    admin = _mock_user(role="admin")
    chat = _mock_chat(admin.id)
    chat.messages = [MagicMock(id=uuid.uuid4())]
    uow = _mock_uow()
    uow.chats.get_by_id = AsyncMock(return_value=chat)
    uow.chats.delete_messages = AsyncMock()
    uow.chats.update_timestamp_by_id = AsyncMock()
    uow.chats.add = MagicMock()
    uow.commit = AsyncMock(side_effect=RuntimeError("commit failed"))

    svc = ChatMaintenanceService(uow, _mock_attachment_service())

    with pytest.raises(RuntimeError, match="commit failed"):
        await svc.clear_history(chat.id, admin, "en")
    uow.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# delete_chat — commit failure rolls back + re-raises (L1093-1095)
# ---------------------------------------------------------------------------


async def test_delete_chat_commit_failure_rolls_back():
    admin = _mock_user(role="admin")
    other = _mock_user()
    chat = _mock_chat(admin.id, other.id)
    uow = _mock_uow()
    uow.chats.get_by_id = AsyncMock(return_value=chat)
    uow.chats.delete_chat = AsyncMock()
    uow.chats.add = MagicMock()
    uow.commit = AsyncMock(side_effect=RuntimeError("commit failed"))

    svc = ChatMaintenanceService(uow, _mock_attachment_service())

    with pytest.raises(RuntimeError, match="commit failed"):
        await svc.delete_chat(chat.id, admin, "en")
    uow.rollback.assert_awaited_once()
    # ChatDeleted StoredEvents were staged for both participants before failure.
    assert uow.chats.add.call_count == 2
