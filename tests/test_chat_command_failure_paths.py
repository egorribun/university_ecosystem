"""Failure-path tests for app/services/chat/command_service.py.

AsyncMock repository fixtures plus real borrowed-UoW failure tests targeting
previously-uncovered error branches:

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
- clear_history commit failure remains visible when real-UOW rollback also fails;
- delete_chat commit failure remains visible when real-UOW rollback also fails.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import fakeredis.aioredis
import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import Headers

import app.deps.cache as cache_module
import app.services.chat.attachment_service as attachment_module
import app.services.chat.command_service as cs_module
import app.utils.files as files_module
from app.repositories.unit_of_work import uow_from_session
from app.services.chat.command_service import (
    ChatMaintenanceService,
    ChatMessageDispatcher,
)
from app.services.storage import StaticFSStorage

# ---------------------------------------------------------------------------
# Helpers (mirroring tests/test_chat_command_service.py)
# ---------------------------------------------------------------------------


def _attachment_reference_result(urls: list[str]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = urls
    return result


def _mock_uow():
    uow = MagicMock()
    uow.chats = MagicMock()
    uow.chats.get_send_receipt = AsyncMock(return_value=None)
    uow.chats.create_send_receipt = AsyncMock(
        return_value=datetime.now(UTC) + timedelta(hours=24)
    )
    uow.chats.prune_expired_send_receipts = AsyncMock(return_value=0)
    uow.chats.send_receipt_remaining_seconds = AsyncMock(return_value=86400)
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


@pytest.mark.parametrize("replacement", [None, "replacement-owner"])
async def test_cancelled_reservation_drains_before_real_set_and_cas(
    monkeypatch, replacement
):
    cache = await _patch_cache(monkeypatch)
    uow = _mock_uow()
    user = _mock_user()
    chat = _mock_chat(user.id)
    uow.chats.get_by_id = AsyncMock(return_value=chat)
    uow.chats.check_participant = AsyncMock(return_value=True)
    attachment_service = _mock_attachment_service()
    dispatcher = ChatMessageDispatcher(uow, attachment_service, MagicMock())
    key = cs_module._make_idempotency_key(chat.id, user.id, "cancel-set-ack")
    stored_values = []
    set_started = asyncio.Event()
    acknowledge_set = asyncio.Event()
    real_set = cache.set
    change_calls = []
    real_change = cs_module._change_idempotency_slot

    async def tracked_change(*args, **kwargs):
        change_calls.append((args, kwargs))
        return await real_change(*args, **kwargs)

    async def withhold_before_real_set(name, value, *args, **kwargs):
        if name == key and kwargs.get("nx") is True:
            stored_values.append(value)
            set_started.set()
            await acknowledge_set.wait()
        return await real_set(name, value, *args, **kwargs)

    monkeypatch.setattr(cache, "set", withhold_before_real_set)
    monkeypatch.setattr(cs_module, "_change_idempotency_slot", tracked_change)
    upload = MagicMock(size=10)
    send_task = asyncio.create_task(
        dispatcher.send_message(
            chat.id,
            user,
            "with file",
            [upload],
            "en",
            idempotency_key="cancel-set-ack",
        )
    )
    try:
        await asyncio.wait_for(set_started.wait(), timeout=2)
        assert len(stored_values) == 1
        owned_value = stored_values[0]
        assert isinstance(owned_value, str)
        assert await cache.get(key) is None

        send_task.cancel("first reservation cancellation")
        await asyncio.sleep(0)
        assert not send_task.done()
        if replacement is not None:
            await real_set(key, replacement, ex=300)
        send_task.cancel("second reservation cancellation")
        await asyncio.sleep(0)
        assert not send_task.done()
        send_task.cancel("third reservation cancellation")
        await asyncio.sleep(0)
        assert not send_task.done()
        assert change_calls == []
        assert await cache.get(key) == replacement

        acknowledge_set.set()
        with pytest.raises(asyncio.CancelledError) as raised:
            await asyncio.wait_for(send_task, timeout=2)

        assert raised.value.args == ("first reservation cancellation",)
        assert await cache.get(key) == replacement
        assert len(change_calls) == 1
        assert change_calls[0][0][:2] == (key, owned_value)
        attachment_service.process_upload.assert_not_awaited()
        attachment_service.cleanup_files.assert_not_awaited()
        uow.chats.create_message.assert_not_called()
        uow.commit.assert_not_awaited()
    finally:
        acknowledge_set.set()
        if not send_task.done():
            send_task.cancel("test cleanup")
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(send_task, timeout=2)
        await cache.aclose()


async def test_cancelled_reservation_timeout_skips_cas_before_late_set(
    monkeypatch,
):
    monkeypatch.setattr(cs_module, "_CANCELLED_UPLOAD_CLEANUP_TIMEOUT_SECONDS", 0.02)
    cache = await _patch_cache(monkeypatch)
    uow = _mock_uow()
    user = _mock_user()
    chat = _mock_chat(user.id)
    uow.chats.get_by_id = AsyncMock(return_value=chat)
    uow.chats.check_participant = AsyncMock(return_value=True)
    attachment_service = _mock_attachment_service()
    dispatcher = ChatMessageDispatcher(uow, attachment_service, MagicMock())
    key = cs_module._make_idempotency_key(chat.id, user.id, "late-set-ack")
    stored_values = []
    set_started = asyncio.Event()
    allow_late_set = asyncio.Event()
    cancellation_suppressed = asyncio.Event()
    reservation_tasks = []
    server_set_tasks = []
    real_set = cache.set
    change_calls = []

    async def tracked_change(*args, **kwargs):
        change_calls.append((args, kwargs))
        return False

    async def withhold_server_set(name, value, *args, **kwargs):
        if name != key or kwargs.get("nx") is not True:
            return await real_set(name, value, *args, **kwargs)
        stored_values.append(value)
        reservation_tasks.append(asyncio.current_task())
        set_started.set()

        async def perform_late_set():
            await allow_late_set.wait()
            return await real_set(name, value, *args, **kwargs)

        server_task = asyncio.create_task(perform_late_set())
        server_set_tasks.append(server_task)
        try:
            return await asyncio.shield(server_task)
        except asyncio.CancelledError:
            cancellation_suppressed.set()
            return await asyncio.shield(server_task)

    monkeypatch.setattr(cache, "set", withhold_server_set)
    monkeypatch.setattr(cs_module, "_change_idempotency_slot", tracked_change)
    upload = MagicMock(size=10)
    send_task = asyncio.create_task(
        dispatcher.send_message(
            chat.id,
            user,
            "with file",
            [upload],
            "en",
            idempotency_key="late-set-ack",
        )
    )
    try:
        await asyncio.wait_for(set_started.wait(), timeout=2)
        send_task.cancel("cancel during late reservation")
        with pytest.raises(asyncio.CancelledError) as raised:
            await asyncio.wait_for(send_task, timeout=1)
        assert raised.value.args == ("cancel during late reservation",)
        await asyncio.wait_for(cancellation_suppressed.wait(), timeout=1)
        assert len(reservation_tasks) == 1
        assert len(server_set_tasks) == 1
        assert not reservation_tasks[0].done()
        assert not server_set_tasks[0].done()
        assert change_calls == []
        assert await cache.get(key) is None
        attachment_service.process_upload.assert_not_awaited()
        attachment_service.cleanup_files.assert_not_awaited()
        uow.chats.create_message.assert_not_called()
        uow.commit.assert_not_awaited()

        allow_late_set.set()
        assert (
            await asyncio.wait_for(asyncio.shield(server_set_tasks[0]), timeout=1)
            is True
        )
        assert (
            await asyncio.wait_for(asyncio.shield(reservation_tasks[0]), timeout=1)
            is True
        )
        assert change_calls == []
        assert await cache.get(key) == stored_values[0]
        assert 0 < await cache.ttl(key) <= 300
    finally:
        allow_late_set.set()
        if not send_task.done():
            send_task.cancel("test cleanup")
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(send_task, timeout=1)
        for task in server_set_tasks:
            if not task.done():
                await asyncio.wait_for(asyncio.shield(task), timeout=1)
        for task in reservation_tasks:
            if not task.done():
                await asyncio.wait_for(asyncio.shield(task), timeout=1)
        await cache.aclose()


@pytest.mark.parametrize("idempotency_key", [None, "cancelled-upload"])
@pytest.mark.parametrize("completed_upload", [False, True])
async def test_send_message_phase1_cancellation_cleans_partial_uploads_and_slot(
    monkeypatch, tmp_path, idempotency_key, completed_upload
):
    """Cancelling the parent send cannot strand uploaded bytes or its own lease."""
    monkeypatch.setattr(cs_module.settings, "chat_attachment_max_files", 5)
    cache = await _patch_cache(monkeypatch)
    uow = _mock_uow()
    user = _mock_user()
    chat = _mock_chat(user.id)
    uow.chats.get_by_id = AsyncMock(return_value=chat)
    uow.chats.check_participant = AsyncMock(return_value=True)

    good_file, slow_file = MagicMock(size=10), MagicMock(size=10)
    saved_file = tmp_path / "completed-upload.bin"
    slow_started = asyncio.Event()
    slow_cancelled = asyncio.Event()

    async def process_upload(upload, _chat_id, *, locale):
        if upload is good_file:
            if not completed_upload:
                await asyncio.Future()
            saved_file.write_bytes(b"uploaded")
            return {
                "url": "/static/chat_uploads/completed-upload.bin",
                "file_type": "file",
                "filename": saved_file.name,
                "size": 8,
            }
        slow_started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            slow_cancelled.set()
            raise

    async def cleanup_files(urls):
        assert urls == ["/static/chat_uploads/completed-upload.bin"]
        saved_file.unlink()

    attachment_service = _mock_attachment_service()
    attachment_service.process_upload = AsyncMock(side_effect=process_upload)
    attachment_service.cleanup_files = AsyncMock(side_effect=cleanup_files)
    dispatcher = ChatMessageDispatcher(uow, attachment_service, MagicMock())
    send_task = asyncio.create_task(
        dispatcher.send_message(
            chat.id,
            user,
            "with files",
            [good_file, slow_file],
            "en",
            idempotency_key=idempotency_key,
        )
    )
    try:
        await asyncio.wait_for(slow_started.wait(), timeout=2)
        assert saved_file.exists() is completed_upload
        if idempotency_key:
            assert len(await cache.keys("idm:msg:*")) == 1
        send_task.cancel("cancelled during upload")
        with pytest.raises(asyncio.CancelledError) as raised:
            await send_task

        assert raised.value.args == ("cancelled during upload",)
        assert slow_cancelled.is_set()
        assert not saved_file.exists()
        assert not await cache.keys("idm:msg:*")
        uow.chats.create_message.assert_not_called()
        uow.commit.assert_not_awaited()
    finally:
        if not send_task.done():
            send_task.cancel()
            try:
                await send_task
            except asyncio.CancelledError:
                pass
        await cache.aclose()


@pytest.mark.parametrize(
    "failure",
    [
        "none",
        "repeated_cancel",
        "replacement_owner",
        "replacement_invalid_bytes",
        "redis_unavailable",
        "redis_unexpected",
        "cleanup_unexpected",
        "cleanup_cancelled",
        "storage_failure",
        "storage_timeout",
        "release_timeout",
    ],
)
async def test_cancelled_upload_cleanup_finishes_before_propagating_cancellation(
    monkeypatch, tmp_path, caplog, failure
):
    import app.services.chat.attachment_service as attachment_module

    cache = await _patch_cache(monkeypatch)
    uow = _mock_uow()
    user = _mock_user()
    chat = _mock_chat(user.id)
    uow.chats.get_by_id = AsyncMock(return_value=chat)
    uow.chats.check_participant = AsyncMock(return_value=True)
    good_file, slow_file = MagicMock(size=10), MagicMock(size=10)
    saved_file = tmp_path / "completed-upload.bin"
    upload_started = asyncio.Event()
    deletion_started = asyncio.Event()
    resume_deletion = asyncio.Event()
    resume_release = asyncio.Event()
    deletion_finished = asyncio.Event()
    release_finished = asyncio.Event()
    cleanup_tasks = set()
    deletion_tasks = set()
    release_tasks = set()
    private_error = "private-cleanup-error-must-not-be-logged"
    key = cs_module._make_idempotency_key(chat.id, user.id, "cancel-boundaries")
    if failure in {"storage_timeout", "release_timeout"}:
        monkeypatch.setattr(
            cs_module, "_CANCELLED_UPLOAD_CLEANUP_TIMEOUT_SECONDS", 0.02
        )

    async def process_upload(upload, _chat_id, *, locale):
        if upload is good_file:
            saved_file.write_bytes(b"uploaded")
            return {
                "url": "/static/chat_uploads/completed-upload.bin",
                "file_type": "file",
                "filename": saved_file.name,
                "size": 8,
            }
        upload_started.set()
        await asyncio.Future()

    async def delete_file(url):
        assert url == "/static/chat_uploads/completed-upload.bin"
        deletion_tasks.add(asyncio.current_task())
        deletion_started.set()
        try:
            if failure == "repeated_cancel":
                await resume_deletion.wait()
            if failure == "storage_timeout":
                try:
                    await resume_deletion.wait()
                finally:
                    # Cancellation must drain this real gather child before the
                    # request returns or any lease release can start.
                    await asyncio.sleep(0)
                    assert await cache.get(key) is not None
            if failure == "storage_failure":
                raise OSError(private_error)
            saved_file.unlink()
        finally:
            deletion_finished.set()

    monkeypatch.setattr(attachment_module, "delete_static_file", delete_file)
    attachment_service = attachment_module.ChatAttachmentService()
    attachment_service.process_upload = AsyncMock(side_effect=process_upload)
    real_cleanup = attachment_service.cleanup_files

    async def cleanup_files(urls):
        cleanup_tasks.add(asyncio.current_task())
        if failure == "cleanup_unexpected":
            raise RuntimeError(private_error)
        if failure == "cleanup_cancelled":
            raise asyncio.CancelledError("cleanup cancellation")
        await real_cleanup(urls)

    monkeypatch.setattr(attachment_service, "cleanup_files", cleanup_files)
    real_change_slot = cs_module._change_idempotency_slot

    async def release_slot(*args, **kwargs):
        release_tasks.add(asyncio.current_task())
        try:
            if failure not in {"cleanup_unexpected", "cleanup_cancelled"}:
                assert deletion_finished.is_set()
            if failure == "redis_unavailable":
                raise OSError(private_error)
            if failure == "redis_unexpected":
                raise RuntimeError(private_error)
            if failure == "release_timeout":
                await resume_release.wait()
            return await real_change_slot(*args, **kwargs)
        finally:
            release_finished.set()

    monkeypatch.setattr(cs_module, "_change_idempotency_slot", release_slot)
    dispatcher = ChatMessageDispatcher(uow, attachment_service, MagicMock())
    send_task = asyncio.create_task(
        dispatcher.send_message(
            chat.id,
            user,
            "with files",
            [good_file, slow_file],
            "en",
            idempotency_key="cancel-boundaries",
        )
    )
    try:
        await asyncio.wait_for(upload_started.wait(), timeout=2)
        assert saved_file.exists()
        assert await cache.get(key) is not None
        if failure == "replacement_owner":
            await cache.set(key, "replacement-owner", ex=300)
        elif failure == "replacement_invalid_bytes":
            await cache.set(key, b"\xff", ex=300)
        stored_lease = await cache.dump(key)

        send_task.cancel("original cancellation")
        if failure == "repeated_cancel":
            await asyncio.wait_for(deletion_started.wait(), timeout=2)
            send_task.cancel("second cancellation")
            await asyncio.sleep(0)
            send_task.cancel("third cancellation")
            await asyncio.sleep(0)
            assert not send_task.done()
            assert not release_finished.is_set()
            assert await cache.dump(key) == stored_lease
            resume_deletion.set()
        done, _ = await asyncio.wait({send_task}, timeout=2)
        assert send_task in done, "cleanup exceeded its cooperative deadline"
        with pytest.raises(asyncio.CancelledError) as raised:
            await send_task

        assert raised.value.args == ("original cancellation",)
        assert send_task.cancelled()
        assert len(cleanup_tasks) == 1
        if failure not in {"cleanup_unexpected", "cleanup_cancelled"}:
            assert len(deletion_tasks) == 1
            assert deletion_started.is_set()
            assert deletion_finished.is_set()
        assert all(task is not None and task.done() for task in cleanup_tasks)
        assert all(task is not None and task.done() for task in deletion_tasks)
        assert all(task is not None and task.done() for task in release_tasks)
        assert saved_file.exists() is (
            failure
            in {
                "cleanup_unexpected",
                "cleanup_cancelled",
                "storage_failure",
                "storage_timeout",
            }
        )
        retained_lease = failure in {
            "replacement_owner",
            "replacement_invalid_bytes",
            "redis_unavailable",
            "redis_unexpected",
            "storage_timeout",
            "release_timeout",
        }
        assert (await cache.dump(key) is not None) is retained_lease
        if retained_lease:
            assert await cache.dump(key) == stored_lease
            assert 0 < await cache.ttl(key) <= 300
        if failure == "storage_timeout":
            assert not release_finished.is_set()
        else:
            assert release_finished.is_set()
        assert private_error not in caplog.text
        uow.chats.create_message.assert_not_called()
        uow.commit.assert_not_awaited()
    finally:
        resume_deletion.set()
        resume_release.set()
        if not send_task.done():
            send_task.cancel()
            try:
                await send_task
            except asyncio.CancelledError:
                pass
        await cache.aclose()


# ---------------------------------------------------------------------------
# send_message — Phase 2 (DB write) failure cleanup (L359-372)
# ---------------------------------------------------------------------------


async def test_send_message_phase2_failure_cleans_only_unreferenced_files_and_keeps_pending_lease(
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
    uow.chats.update_timestamp_by_id = AsyncMock()
    uow.chats.add = MagicMock()
    _capture_create_message(uow)
    uow.commit = AsyncMock(side_effect=ConnectionError("commit outcome unknown"))
    shared_url = "https://s3.example.com/shared.bin"
    orphan_url = "https://s3.example.com/orphan.bin"
    first_file = MagicMock(size=10)
    second_file = MagicMock(size=10)

    async def process_upload(upload, _chat_id, *, locale):
        if upload is first_file:
            return {
                "url": shared_url,
                "file_type": "application/octet-stream",
                "filename": "shared.bin",
                "size": 10,
            }
        return {
            "url": orphan_url,
            "file_type": "application/octet-stream",
            "filename": "orphan.bin",
            "size": 10,
        }

    attachment_svc = _mock_attachment_service()
    attachment_svc.process_upload = AsyncMock(side_effect=process_upload)
    order = []

    async def rollback():
        order.append("rollback")

    async def lookup(_statement):
        order.append("reference_lookup")
        return _attachment_reference_result([shared_url])

    uow.rollback.side_effect = rollback
    uow.session.execute = AsyncMock(side_effect=lookup)
    dispatcher = ChatMessageDispatcher(uow, attachment_svc, MagicMock())

    with pytest.raises(ConnectionError, match="commit outcome unknown"):
        await dispatcher.send_message(
            chat.id,
            user,
            "with files",
            [first_file, second_file],
            "en",
            idempotency_key="idem-phase2",
        )

    assert order == ["rollback", "reference_lookup"]
    attachment_svc.cleanup_files.assert_awaited_once_with([orphan_url])
    idempotency_keys = await cache.keys("idm:msg:*")
    assert len(idempotency_keys) == 1
    pending = json.loads(await cache.get(idempotency_keys[0]))
    assert pending["status"] == "pending"
    assert 0 < await cache.ttl(idempotency_keys[0]) <= 300
    await cache.aclose()


async def test_send_message_ambiguous_commit_keeps_pending_lease_with_real_uow(
    monkeypatch,
):
    cache = await _patch_cache(monkeypatch)
    _patch_ws(monkeypatch)
    session = AsyncMock(spec=AsyncSession)
    uow = uow_from_session(session)
    uow.chats.get_send_receipt = AsyncMock(return_value=None)
    uow.chats.create_send_receipt = AsyncMock(
        return_value=datetime.now(UTC) + timedelta(hours=24)
    )
    uow.chats.prune_expired_send_receipts = AsyncMock(return_value=0)
    uow.chats.send_receipt_remaining_seconds = AsyncMock(return_value=86400)
    user = _mock_user()
    chat = _mock_chat(user.id)
    uow.chats.get_by_id = AsyncMock(return_value=chat)
    uow.chats.check_participant = AsyncMock(return_value=True)
    uow.chats.update_timestamp_by_id = AsyncMock()
    uow.chats.add = MagicMock()
    created = _capture_create_message(uow)
    commit_applied = False

    async def commit_with_lost_acknowledgement():
        nonlocal commit_applied
        commit_applied = True
        raise ConnectionError("commit outcome unknown")

    rollback_count = 0

    async def fail_first_rollback():
        nonlocal rollback_count
        rollback_count += 1
        if rollback_count == 1:
            raise OSError("rollback connection lost")

    session.commit.side_effect = commit_with_lost_acknowledgement
    session.rollback.side_effect = fail_first_rollback
    dispatcher = ChatMessageDispatcher(uow, _mock_attachment_service(), MagicMock())

    try:
        with pytest.raises(ConnectionError, match="commit outcome unknown"):
            await dispatcher.send_message(
                chat.id,
                user,
                "Hello",
                [],
                "en",
                idempotency_key="idem-ambiguous-commit",
            )

        assert commit_applied is True
        assert rollback_count == 1
        assert session.commit.await_count == 1
        assert len(created) == 1
        key = cs_module._make_idempotency_key(chat.id, user.id, "idem-ambiguous-commit")
        pending = json.loads(await cache.get(key))
        assert pending["status"] == "pending"
        assert 0 < await cache.ttl(key) <= 300

        with pytest.raises(HTTPException) as retry_error:
            await dispatcher.send_message(
                chat.id,
                user,
                "Hello",
                [],
                "en",
                idempotency_key="idem-ambiguous-commit",
            )
        assert retry_error.value.status_code == 409
        assert retry_error.value.detail["error"] == "idempotency_in_progress"
        assert session.commit.await_count == 1
        assert len(created) == 1
    finally:
        await cache.aclose()


async def test_send_message_precommit_repository_failure_releases_owned_pending_lease(
    monkeypatch,
):
    cache = await _patch_cache(monkeypatch)
    _patch_ws(monkeypatch)
    real_change = cs_module._change_idempotency_slot
    change_calls = []

    async def track_change(key, expected, replacement=None, *, ttl=300):
        result = await real_change(key, expected, replacement, ttl=ttl)
        change_calls.append((key, expected, replacement, result))
        return result

    monkeypatch.setattr(cs_module, "_change_idempotency_slot", track_change)
    uow = _mock_uow()
    user = _mock_user()
    chat = _mock_chat(user.id)
    uow.chats.get_by_id = AsyncMock(return_value=chat)
    uow.chats.check_participant = AsyncMock(return_value=True)
    repository_error = RuntimeError("repository write failed before commit")
    uow.chats.create_message = AsyncMock(side_effect=repository_error)
    dispatcher = ChatMessageDispatcher(uow, _mock_attachment_service(), MagicMock())
    client_key = "idem-precommit-repository-failure"

    try:
        with pytest.raises(RuntimeError) as excinfo:
            await dispatcher.send_message(
                chat.id, user, "Hello", [], "en", idempotency_key=client_key
            )

        assert excinfo.value is repository_error
        uow.chats.create_message.assert_awaited_once()
        uow.rollback.assert_awaited_once()
        uow.commit.assert_not_awaited()
        key = cs_module._make_idempotency_key(chat.id, user.id, client_key)
        assert len(change_calls) == 2
        acquired_key, acquired_owner, acquired_replacement, acquired = change_calls[0]
        released_key, released_owner, released_replacement, released = change_calls[1]
        assert acquired_key == released_key == key
        assert acquired_owner == released_owner
        assert acquired_replacement == acquired_owner
        assert acquired is True
        assert released_replacement is None
        assert released is True
        assert await cache.get(key) is None
    finally:
        await cache.aclose()


async def test_send_message_cache_renewal_failure_preserves_commit_error(
    monkeypatch,
):
    cache = await _patch_cache(monkeypatch)
    _patch_ws(monkeypatch)
    real_change = cs_module._change_idempotency_slot
    change_calls = []

    async def fail_best_effort_renewal(key, expected, replacement=None, *, ttl=300):
        if not change_calls:
            result = await real_change(key, expected, replacement, ttl=ttl)
            change_calls.append((key, expected, replacement, result))
            return result
        change_calls.append((key, expected, replacement, None))
        raise OSError("Redis unavailable during pending lease renewal")

    monkeypatch.setattr(cs_module, "_change_idempotency_slot", fail_best_effort_renewal)
    uow = _mock_uow()
    user = _mock_user()
    chat = _mock_chat(user.id)
    uow.chats.get_by_id = AsyncMock(return_value=chat)
    uow.chats.check_participant = AsyncMock(return_value=True)
    uow.chats.update_timestamp_by_id = AsyncMock()
    uow.chats.add = MagicMock()
    _capture_create_message(uow)
    commit_error = ConnectionError("commit outcome unknown")
    uow.commit = AsyncMock(side_effect=commit_error)
    dispatcher = ChatMessageDispatcher(uow, _mock_attachment_service(), MagicMock())
    client_key = "idem-renewal-failure"

    try:
        with pytest.raises(ConnectionError) as excinfo:
            await dispatcher.send_message(
                chat.id, user, "Hello", [], "en", idempotency_key=client_key
            )

        assert excinfo.value is commit_error
        assert uow.commit.await_count == 1
        uow.rollback.assert_awaited_once()
        assert len(change_calls) == 2
        key, owner, replacement, initial_renewal = change_calls[0]
        cleanup_key, cleanup_owner, cleanup_replacement, cleanup_result = change_calls[
            1
        ]
        assert (
            key
            == cleanup_key
            == cs_module._make_idempotency_key(chat.id, user.id, client_key)
        )
        assert replacement == owner == cleanup_owner
        assert initial_renewal is True
        assert cleanup_replacement == owner
        assert cleanup_result is None
        pending = json.loads(await cache.get(key))
        assert pending["status"] == "pending"
        assert 0 < await cache.ttl(key) <= 300
    finally:
        await cache.aclose()


async def test_send_message_cleanup_failure_preserves_commit_error_and_lease(
    monkeypatch,
):
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
    uow.commit = AsyncMock(side_effect=ConnectionError("commit outcome unknown"))
    uow.session.execute = AsyncMock(return_value=_attachment_reference_result([]))
    attachment_service = _mock_attachment_service()
    attachment_service.cleanup_files = AsyncMock(
        side_effect=RuntimeError("object-store cleanup failed")
    )
    dispatcher = ChatMessageDispatcher(uow, attachment_service, MagicMock())

    try:
        with pytest.raises(ConnectionError, match="commit outcome unknown"):
            await dispatcher.send_message(
                chat.id,
                user,
                "with file",
                [MagicMock(size=10)],
                "en",
                idempotency_key="idem-cleanup-failure",
            )

        attachment_service.cleanup_files.assert_awaited_once_with(
            ["https://s3.example.com/file.pdf"]
        )
        pending = await cache.get(
            cs_module._make_idempotency_key(chat.id, user.id, "idem-cleanup-failure")
        )
        assert json.loads(pending)["status"] == "pending"
    finally:
        await cache.aclose()


async def test_send_message_reference_lookup_failure_retains_saved_file(monkeypatch):
    _patch_ws(monkeypatch)
    uow = _mock_uow()
    user = _mock_user()
    chat = _mock_chat(user.id)
    uow.chats.get_by_id = AsyncMock(return_value=chat)
    uow.chats.check_participant = AsyncMock(return_value=True)
    uow.chats.update_timestamp_by_id = AsyncMock()
    uow.chats.add = MagicMock()
    _capture_create_message(uow)
    uow.commit = AsyncMock(side_effect=ConnectionError("commit outcome unknown"))
    order = []

    async def rollback():
        order.append("rollback")

    async def lookup(_statement):
        order.append("reference_lookup")
        raise OSError("reference query unavailable")

    uow.rollback.side_effect = rollback
    uow.session.execute = AsyncMock(side_effect=lookup)
    attachment_svc = _mock_attachment_service()
    dispatcher = ChatMessageDispatcher(uow, attachment_svc, MagicMock())

    with pytest.raises(ConnectionError, match="commit outcome unknown"):
        await dispatcher.send_message(
            chat.id, user, "with file", [MagicMock(size=10)], "en"
        )

    assert order == ["rollback", "reference_lookup"]
    attachment_svc.cleanup_files.assert_not_awaited()


@pytest.mark.parametrize("urls", [[], ["", ""]], ids=("empty", "blank"))
@pytest.mark.asyncio
async def test_cleanup_unreferenced_uploads_skips_database_and_storage_for_empty_urls(
    urls: list[str],
) -> None:
    uow = _mock_uow()
    attachment_service = _mock_attachment_service()
    dispatcher = ChatMessageDispatcher(uow, attachment_service, MagicMock())

    await dispatcher._cleanup_unreferenced_uploaded_files(urls)

    uow.session.execute.assert_not_awaited()
    attachment_service.cleanup_files.assert_not_awaited()


@pytest.mark.asyncio
async def test_cleanup_unreferenced_uploads_retains_all_referenced_urls() -> None:
    referenced_urls = [
        "https://s3.example.com/shared-a.bin",
        "https://s3.example.com/shared-b.bin",
    ]
    uow = _mock_uow()
    uow.session.execute = AsyncMock(
        return_value=_attachment_reference_result(referenced_urls)
    )
    attachment_service = _mock_attachment_service()
    dispatcher = ChatMessageDispatcher(uow, attachment_service, MagicMock())

    await dispatcher._cleanup_unreferenced_uploaded_files(
        [referenced_urls[0], referenced_urls[1], referenced_urls[0]]
    )

    uow.session.execute.assert_awaited_once()
    attachment_service.cleanup_files.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_message_real_uow_rollback_failure_retains_uploaded_file():
    session = AsyncMock(spec=AsyncSession)
    uow = uow_from_session(session)
    user = _mock_user()
    chat = _mock_chat(user.id)
    uow.chats.get_by_id = AsyncMock(return_value=chat)
    uow.chats.check_participant = AsyncMock(return_value=True)
    uow.chats.update_timestamp_by_id = AsyncMock()
    uow.chats.add = MagicMock()
    _capture_create_message(uow)
    session.commit.side_effect = ConnectionError("commit acknowledgement lost")
    session.rollback.side_effect = OSError("rollback connection lost")
    attachment_service = _mock_attachment_service()
    dispatcher = ChatMessageDispatcher(uow, attachment_service, MagicMock())
    upload = MagicMock(size=10)

    with pytest.raises(ConnectionError, match="commit acknowledgement lost"):
        await dispatcher.send_message(
            chat.id, user, "with uploaded file", [upload], "en"
        )

    session.commit.assert_awaited_once()
    session.rollback.assert_awaited_once()
    # Both repository lookups were stubbed, so any SQL here would be the
    # post-rollback Attachment ownership probe that must be skipped on failure.
    session.execute.assert_not_awaited()
    attachment_service.process_upload.assert_awaited_once_with(
        upload, chat.id, locale="en"
    )
    attachment_service.cleanup_files.assert_not_awaited()


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
# clear_history — real UOW preserves the commit error if rollback also fails
# ---------------------------------------------------------------------------


async def test_clear_history_commit_failure_rolls_back():
    admin = _mock_user(role="admin")
    chat = _mock_chat(admin.id)
    message = MagicMock()
    message.id = uuid.uuid4()
    message.attachments = []
    session = AsyncMock(spec=AsyncSession)
    uow = uow_from_session(session)
    uow.chats = MagicMock()
    uow.chats.get_by_id = AsyncMock(return_value=chat)
    uow.chats.get_orm_for_update = AsyncMock(return_value=object())
    uow.chats.lock_participant_ids_for_maintenance = AsyncMock(return_value=[admin.id])
    uow.chats.get_messages = AsyncMock(return_value=([message], False, None))
    uow.chats.delete_messages = AsyncMock()
    uow.chats.update_timestamp_by_id = AsyncMock()
    uow.chats.add = MagicMock()
    commit_error = ConnectionError("commit acknowledgement lost")
    session.commit.side_effect = commit_error
    session.rollback.side_effect = OSError("rollback connection lost")

    svc = ChatMaintenanceService(uow, _mock_attachment_service())

    with pytest.raises(ConnectionError, match="commit acknowledgement lost") as error:
        await svc.clear_history(chat.id, admin, "en")

    assert error.value is commit_error
    session.commit.assert_awaited_once()
    session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# delete_chat — real UOW preserves the commit error if rollback also fails
# ---------------------------------------------------------------------------


async def test_delete_chat_commit_failure_rolls_back():
    admin = _mock_user(role="admin")
    other = _mock_user()
    chat = _mock_chat(admin.id, other.id)
    message = MagicMock()
    message.id = uuid.uuid4()
    message.attachments = []
    session = AsyncMock(spec=AsyncSession)
    uow = uow_from_session(session)
    uow.chats = MagicMock()
    uow.chats.get_by_id = AsyncMock(return_value=chat)
    uow.chats.get_orm_for_update = AsyncMock(return_value=object())
    uow.chats.lock_participant_ids_for_maintenance = AsyncMock(
        return_value=[admin.id, other.id]
    )
    uow.chats.get_messages = AsyncMock(return_value=([message], False, None))
    uow.chats.delete_chat = AsyncMock()
    uow.chats.add = MagicMock()
    commit_error = ConnectionError("commit acknowledgement lost")
    session.commit.side_effect = commit_error
    session.rollback.side_effect = OSError("rollback connection lost")

    svc = ChatMaintenanceService(uow, _mock_attachment_service())

    with pytest.raises(ConnectionError, match="commit acknowledgement lost") as error:
        await svc.delete_chat(chat.id, admin, "en")

    assert error.value is commit_error
    session.commit.assert_awaited_once()
    session.rollback.assert_awaited_once()
    # ChatDeleted StoredEvents were staged for both participants before failure.
    assert uow.chats.add.call_count == 2


# ---------------------------------------------------------------------------
# Real static upload cancellation: writer ownership and readiness handoff
# ---------------------------------------------------------------------------

_CANCELLABLE_STATIC_PAYLOAD = b"%PDF-1.7\nprivate cancellation probe\n"


async def _no_static_scan(*_args, **_kwargs):
    return None


def _install_cancellable_static_storage(monkeypatch, storage_root: Path):
    storage_root.mkdir(parents=True, exist_ok=True)
    backend = StaticFSStorage(storage_root)
    monkeypatch.setattr(files_module, "_get_storage_backend", lambda: backend)
    monkeypatch.setattr(files_module, "_magic_mime_detector", None)
    monkeypatch.setattr(files_module, "scan_for_malware", _no_static_scan)
    monkeypatch.setattr(attachment_module, "scan_for_malware", _no_static_scan)
    return backend


def _cancellable_static_upload() -> UploadFile:
    return UploadFile(
        file=BytesIO(_CANCELLABLE_STATIC_PAYLOAD),
        size=len(_CANCELLABLE_STATIC_PAYLOAD),
        filename="cancel-probe.pdf",
        headers=Headers({"content-type": "application/pdf"}),
    )


def _cancellable_static_dispatcher(attachment_service):
    user = MagicMock()
    user.id = uuid.uuid4()
    chat = MagicMock()
    chat.id = uuid.uuid4()
    uow = MagicMock()
    uow.chats = MagicMock()
    uow.chats.get_by_id = AsyncMock(return_value=chat)
    uow.chats.check_participant = AsyncMock(return_value=True)
    uow.chats.create_message = AsyncMock()
    uow.session = AsyncMock()
    uow.commit = AsyncMock()
    uow.rollback = AsyncMock()
    return ChatMessageDispatcher(uow, attachment_service, MagicMock()), uow, chat, user


async def _wait_for_static_writer_event(event: threading.Event) -> None:
    deadline = asyncio.get_running_loop().time() + 4
    while not event.is_set():
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("bounded wait for static writer event expired")
        await asyncio.sleep(0.01)


class _GatedStaticWriter:
    def __init__(
        self, stream, *, phase: str, entered, released, write_finished
    ) -> None:
        self.stream = stream
        self.phase = phase
        self.entered = entered
        self.released = released
        self.write_finished = write_finished

    def __enter__(self):
        self.stream.__enter__()
        return self

    def __exit__(self, exc_type, exc, traceback):
        if self.phase == "after":
            self.entered.set()
            if not self.released.wait(timeout=8):
                raise TimeoutError("test did not release the completed writer")
        return self.stream.__exit__(exc_type, exc, traceback)

    def write(self, data: bytes) -> int:
        if self.phase == "before":
            self.entered.set()
            if not self.released.wait(timeout=8):
                raise TimeoutError("test did not release the active writer")
            written = self.stream.write(data)
            self.stream.flush()
            self.write_finished.set()
            return written

        written = self.stream.write(data)
        self.stream.flush()
        self.write_finished.set()
        return written


@pytest.mark.parametrize(
    ("phase", "fail_cleanup"),
    [("before", False), ("after", False), ("after", True)],
)
async def test_real_chat_upload_cancel_cleans_owned_write_before_url_delivery(
    monkeypatch, tmp_path, caplog, phase, fail_cleanup
):
    storage_root = tmp_path / "static"
    backend = _install_cancellable_static_storage(monkeypatch, storage_root)
    loop = asyncio.get_running_loop()
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="chat-static-test")
    original_run_in_executor = loop.run_in_executor

    def use_private_executor(executor_arg, function, *args):
        if executor_arg is None:
            executor_arg = executor
        return original_run_in_executor(executor_arg, function, *args)

    monkeypatch.setattr(loop, "run_in_executor", use_private_executor)
    release_write = threading.Event()
    writer_entered = threading.Event()
    writer_finished = threading.Event()
    targets: list[Path] = []
    worker_threads: list[threading.Thread] = []
    original_open = Path.open

    def gated_open(path: Path, mode: str = "r", *args, **kwargs):
        stream = original_open(path, mode, *args, **kwargs)
        if path.resolve().is_relative_to(storage_root.resolve()) and mode == "xb":
            targets.append(path)
            worker_threads.append(threading.current_thread())
            return _GatedStaticWriter(
                stream,
                phase=phase,
                entered=writer_entered,
                released=release_write,
                write_finished=writer_finished,
            )
        return stream

    monkeypatch.setattr(Path, "open", gated_open)
    if fail_cleanup:

        def fail_remove(_path: Path) -> None:
            raise RuntimeError("private cleanup failure")

        monkeypatch.setattr(backend, "_unlink_ignore_missing", fail_remove)

    attachment_service = attachment_module.ChatAttachmentService()
    cleanup_calls: list[list[str]] = []
    real_cleanup = attachment_service.cleanup_files

    async def observe_cleanup(urls, **kwargs):
        cleanup_calls.append(list(urls))
        await real_cleanup(urls, **kwargs)

    monkeypatch.setattr(attachment_service, "cleanup_files", observe_cleanup)
    dispatcher, uow, chat, user = _cancellable_static_dispatcher(attachment_service)
    upload = _cancellable_static_upload()
    send_task = asyncio.create_task(
        dispatcher.send_message(chat.id, user, "upload", [upload], "en")
    )
    write_future = None

    try:
        await _wait_for_static_writer_event(writer_entered)
        assert len(targets) == 1
        target = targets[0]
        assert backend._pending_cancellable_writes
        write_future = next(iter(backend._pending_cancellable_writes))
        assert not write_future.done()
        if phase == "after":
            assert writer_finished.is_set()
            assert target.read_bytes() == _CANCELLABLE_STATIC_PAYLOAD

        send_task.cancel("original upload cancellation")
        with pytest.raises(asyncio.CancelledError) as raised:
            await asyncio.wait_for(send_task, timeout=3)
        assert raised.value.args == ("original upload cancellation",)
        assert send_task.cancelled()
        assert not release_write.is_set()

        if phase == "before":
            assert not writer_finished.is_set()
            assert target.read_bytes() == b""
        else:
            assert target.read_bytes() == _CANCELLABLE_STATIC_PAYLOAD

        release_write.set()
        await asyncio.wait_for(asyncio.shield(write_future), timeout=4)
        assert writer_finished.is_set()
        assert target.exists() is fail_cleanup
        if fail_cleanup:
            assert target.read_bytes() == _CANCELLABLE_STATIC_PAYLOAD
            assert "private cleanup failure" not in caplog.text
        await asyncio.sleep(0)
        assert not backend._pending_cancellable_writes
        assert cleanup_calls == [], "the upload never returned a URL to the dispatcher"
        uow.chats.create_message.assert_not_called()
        uow.commit.assert_not_awaited()
    finally:
        release_write.set()
        if not send_task.done():
            send_task.cancel("test cleanup")
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(send_task, timeout=3)
        if write_future is not None and not write_future.done():
            await asyncio.wait_for(asyncio.shield(write_future), timeout=4)
        await upload.close()
        for target in targets:
            if target.exists():
                target.unlink()
        upload_dir = storage_root / "chat_uploads"
        if upload_dir.is_dir() and not any(upload_dir.iterdir()):
            upload_dir.rmdir()
        if storage_root.is_dir() and not any(storage_root.iterdir()):
            storage_root.rmdir()
        executor.shutdown(wait=True, cancel_futures=True)
    assert worker_threads and all(not worker.is_alive() for worker in worker_threads)


async def _reservation_cancellation_case(monkeypatch, suffix: str):
    cache = await _patch_cache(monkeypatch)
    uow = _mock_uow()
    user = _mock_user()
    chat = _mock_chat(user.id)
    uow.chats.get_by_id = AsyncMock(return_value=chat)
    uow.chats.check_participant = AsyncMock(return_value=True)
    attachment_service = _mock_attachment_service()
    dispatcher = ChatMessageDispatcher(uow, attachment_service, MagicMock())
    key = cs_module._make_idempotency_key(chat.id, user.id, suffix)
    upload = MagicMock(size=10)

    async def send():
        return await dispatcher.send_message(
            chat.id,
            user,
            "with file",
            [upload],
            "en",
            idempotency_key=suffix,
        )

    return cache, uow, attachment_service, key, upload, send


def _assert_reservation_cancel_stopped_before_phase2(attachment_service, uow) -> None:
    attachment_service.process_upload.assert_not_awaited()
    attachment_service.cleanup_files.assert_not_awaited()
    uow.chats.create_message.assert_not_called()
    uow.commit.assert_not_awaited()


async def test_cancelled_reservation_task_skips_cas_and_consumes_cancelled_result(
    monkeypatch,
):
    (
        cache,
        uow,
        attachment_service,
        key,
        _upload,
        send,
    ) = await _reservation_cancellation_case(monkeypatch, "cancelled-set-task")
    set_started = asyncio.Event()
    cancel_reservation = asyncio.Event()
    change_calls = []
    real_set = cache.set

    async def cancelled_set(name, value, *args, **kwargs):
        if name == key and kwargs.get("nx") is True:
            set_started.set()
            await cancel_reservation.wait()
            raise asyncio.CancelledError("fake Redis reservation cancellation")
        return await real_set(name, value, *args, **kwargs)

    monkeypatch.setattr(cache, "set", cancelled_set)
    monkeypatch.setattr(
        cs_module,
        "_change_idempotency_slot",
        AsyncMock(
            side_effect=lambda *args, **kwargs: change_calls.append((args, kwargs))
        ),
    )
    send_task = asyncio.create_task(send())
    try:
        await asyncio.wait_for(set_started.wait(), timeout=2)
        send_task.cancel("caller cancellation before SET result")
        await asyncio.sleep(0)
        assert not send_task.done()
        cancel_reservation.set()
        with pytest.raises(asyncio.CancelledError) as raised:
            await asyncio.wait_for(send_task, timeout=2)
        assert raised.value.args == ("caller cancellation before SET result",)
        await asyncio.sleep(0)
        assert change_calls == []
        assert await cache.get(key) is None
        _assert_reservation_cancel_stopped_before_phase2(attachment_service, uow)
    finally:
        cancel_reservation.set()
        if not send_task.done():
            send_task.cancel("test cleanup")
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(send_task, timeout=2)
        await cache.aclose()


async def test_cancelled_reservation_set_error_cas_cleans_possible_owner(
    monkeypatch, caplog
):
    caplog.set_level(logging.WARNING, logger=cs_module.__name__)
    (
        cache,
        uow,
        attachment_service,
        key,
        _upload,
        send,
    ) = await _reservation_cancellation_case(monkeypatch, "cancelled-set-error")
    set_started = asyncio.Event()
    acknowledge_set = asyncio.Event()
    stored_values = []
    change_calls = []
    real_set = cache.set
    real_change = cs_module._change_idempotency_slot

    async def set_then_lose_ack(name, value, *args, **kwargs):
        if name != key or kwargs.get("nx") is not True:
            return await real_set(name, value, *args, **kwargs)
        stored_values.append(value)
        assert await real_set(name, value, *args, **kwargs) is True
        set_started.set()
        await acknowledge_set.wait()
        raise RuntimeError("simulated lost SET acknowledgement")

    async def tracked_change(*args, **kwargs):
        change_calls.append((args, kwargs))
        return await real_change(*args, **kwargs)

    monkeypatch.setattr(cache, "set", set_then_lose_ack)
    monkeypatch.setattr(cs_module, "_change_idempotency_slot", tracked_change)
    send_task = asyncio.create_task(send())
    try:
        await asyncio.wait_for(set_started.wait(), timeout=2)
        send_task.cancel("cancel before failed SET acknowledgement")
        await asyncio.sleep(0)
        assert not send_task.done()
        acknowledge_set.set()
        with pytest.raises(asyncio.CancelledError) as raised:
            await asyncio.wait_for(send_task, timeout=2)
        assert raised.value.args == ("cancel before failed SET acknowledgement",)
        assert len(stored_values) == 1
        assert len(change_calls) == 1
        assert change_calls[0][0][:2] == (key, stored_values[0])
        assert await cache.get(key) is None
        assert any(
            record.name == cs_module.__name__
            and "chat_message_idempotency_reservation_ack_failed" in record.getMessage()
            for record in caplog.records
        )
        _assert_reservation_cancel_stopped_before_phase2(attachment_service, uow)
    finally:
        acknowledge_set.set()
        if not send_task.done():
            send_task.cancel("test cleanup")
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(send_task, timeout=2)
        await cache.aclose()


async def test_cancelled_reservation_cas_error_preserves_caller_cancellation(
    monkeypatch, caplog
):
    caplog.set_level(logging.WARNING, logger=cs_module.__name__)
    (
        cache,
        uow,
        attachment_service,
        key,
        _upload,
        send,
    ) = await _reservation_cancellation_case(monkeypatch, "failed-owner-cas")
    set_started = asyncio.Event()
    acknowledge_set = asyncio.Event()
    stored_values = []
    change_calls = []
    real_set = cache.set

    async def gated_set(name, value, *args, **kwargs):
        if name != key or kwargs.get("nx") is not True:
            return await real_set(name, value, *args, **kwargs)
        stored_values.append(value)
        result = await real_set(name, value, *args, **kwargs)
        set_started.set()
        await acknowledge_set.wait()
        return result

    async def fail_owner_cas(*args, **kwargs):
        change_calls.append((args, kwargs))
        raise RuntimeError("simulated compare-delete failure")

    monkeypatch.setattr(cache, "set", gated_set)
    monkeypatch.setattr(cs_module, "_change_idempotency_slot", fail_owner_cas)
    send_task = asyncio.create_task(send())
    try:
        await asyncio.wait_for(set_started.wait(), timeout=2)
        send_task.cancel("cancel before CAS failure")
        await asyncio.sleep(0)
        assert not send_task.done()
        acknowledge_set.set()
        with pytest.raises(asyncio.CancelledError) as raised:
            await asyncio.wait_for(send_task, timeout=2)
        assert raised.value.args == ("cancel before CAS failure",)
        assert len(stored_values) == 1
        assert len(change_calls) == 1
        assert change_calls[0][0][:2] == (key, stored_values[0])
        assert await cache.get(key) == stored_values[0]
        assert any(
            record.name == cs_module.__name__
            and "chat_message_idempotency_cleanup_failed" in record.getMessage()
            for record in caplog.records
        )
        _assert_reservation_cancel_stopped_before_phase2(attachment_service, uow)
    finally:
        acknowledge_set.set()
        if not send_task.done():
            send_task.cancel("test cleanup")
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(send_task, timeout=2)
        await cache.aclose()


async def test_cancelled_request_recancel_after_cleanup_done_preserves_first_reason(
    monkeypatch,
):
    (
        cache,
        uow,
        attachment_service,
        key,
        _upload,
        send,
    ) = await _reservation_cancellation_case(monkeypatch, "cleanup-already-done")
    set_started = asyncio.Event()
    acknowledge_set = asyncio.Event()
    cleanup_waiting_after_done = asyncio.Event()
    allow_request_resume = asyncio.Event()
    stored_values = []
    change_calls = []
    cleanup_tasks = []
    real_set = cache.set
    real_change = cs_module._change_idempotency_slot
    real_shield = asyncio.shield

    async def gated_set(name, value, *args, **kwargs):
        if name != key or kwargs.get("nx") is not True:
            return await real_set(name, value, *args, **kwargs)
        stored_values.append(value)
        set_started.set()
        await acknowledge_set.wait()
        return await real_set(name, value, *args, **kwargs)

    async def tracked_change(*args, **kwargs):
        change_calls.append((args, kwargs))
        return await real_change(*args, **kwargs)

    def hold_request_after_cleanup_done(future):
        coroutine = getattr(future, "get_coro", lambda: None)()
        if getattr(coroutine, "__name__", None) == "_cleanup_cancelled_reservation":
            cleanup_tasks.append(future)

            async def await_cleanup_then_hold_request():
                result = await real_shield(future)
                assert future.done()
                cleanup_waiting_after_done.set()
                await allow_request_resume.wait()
                return result

            return await_cleanup_then_hold_request()
        return real_shield(future)

    monkeypatch.setattr(cache, "set", gated_set)
    monkeypatch.setattr(cs_module, "_change_idempotency_slot", tracked_change)
    monkeypatch.setattr(asyncio, "shield", hold_request_after_cleanup_done)
    send_task = asyncio.create_task(send())
    try:
        await asyncio.wait_for(set_started.wait(), timeout=2)
        send_task.cancel("first request cancellation")
        await asyncio.sleep(0)
        assert not send_task.done()
        acknowledge_set.set()
        await asyncio.wait_for(cleanup_waiting_after_done.wait(), timeout=2)
        assert len(cleanup_tasks) == 1 and cleanup_tasks[0].done()
        send_task.cancel("late cancellation after cleanup finished")
        with pytest.raises(asyncio.CancelledError) as raised:
            await asyncio.wait_for(send_task, timeout=2)
        assert raised.value.args == ("first request cancellation",)
        assert len(change_calls) == 1
        assert change_calls[0][0][:2] == (key, stored_values[0])
        assert await cache.get(key) is None
        _assert_reservation_cancel_stopped_before_phase2(attachment_service, uow)
    finally:
        acknowledge_set.set()
        allow_request_resume.set()
        if not send_task.done():
            send_task.cancel("test cleanup")
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(send_task, timeout=2)
        for task in cleanup_tasks:
            if not task.done():
                await asyncio.wait_for(real_shield(task), timeout=2)
        await cache.aclose()


@pytest.mark.asyncio
async def test_chat_queued_static_executor_failure_cleans_completed_upload(
    monkeypatch,
):
    storage_root = Path(__file__).resolve().parent / "executor-shutdown-chat"
    backend = _install_cancellable_static_storage(monkeypatch, storage_root)
    loop = asyncio.get_running_loop()
    executor = ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="chat-shutdown-test"
    )
    original_run_in_executor = loop.run_in_executor
    use_private_executor = True

    def route_executor(executor_arg, function, *args):
        if executor_arg is None and use_private_executor:
            executor_arg = executor
        return original_run_in_executor(executor_arg, function, *args)

    monkeypatch.setattr(loop, "run_in_executor", route_executor)
    blocker_started = threading.Event()
    release_blocker = threading.Event()
    opened_targets: list[Path] = []
    worker_threads: list[threading.Thread] = []
    original_open = Path.open

    def observe_open(path: Path, mode: str = "r", *args, **kwargs):
        stream = original_open(path, mode, *args, **kwargs)
        if path.resolve().is_relative_to(storage_root.resolve()) and mode == "xb":
            opened_targets.append(path)
            worker_threads.append(threading.current_thread())
        return stream

    monkeypatch.setattr(Path, "open", observe_open)
    real_prepare = files_module._prepare_local_storage
    second_prepared = asyncio.Event()
    allow_second_save = asyncio.Event()
    prepare_count = 0

    async def gate_second_prepare(storage_backend, subdir):
        nonlocal prepare_count
        await real_prepare(storage_backend, subdir)
        prepare_count += 1
        if prepare_count == 2:
            second_prepared.set()
            await allow_second_save.wait()

    monkeypatch.setattr(files_module, "_prepare_local_storage", gate_second_prepare)

    attachment_service = attachment_module.ChatAttachmentService()
    first_upload = _cancellable_static_upload()
    second_upload = _cancellable_static_upload()
    first_saved = asyncio.Event()
    first_url: str | None = None
    real_process_upload = attachment_service.process_upload

    async def ordered_process_upload(upload, chat_id, *, locale):
        nonlocal first_url
        if upload is second_upload:
            await first_saved.wait()
        result = await real_process_upload(upload, chat_id, locale=locale)
        if upload is first_upload:
            first_url = str(result["url"])
            first_saved.set()
        return result

    monkeypatch.setattr(attachment_service, "process_upload", ordered_process_upload)
    cleanup_calls: list[list[str]] = []
    real_cleanup = attachment_service.cleanup_files

    async def observe_cleanup(urls, **kwargs):
        cleanup_calls.append(list(urls))
        await real_cleanup(urls, **kwargs)

    monkeypatch.setattr(attachment_service, "cleanup_files", observe_cleanup)
    dispatcher, uow, chat, user = _cancellable_static_dispatcher(attachment_service)
    send_task = asyncio.create_task(
        dispatcher.send_message(
            chat.id, user, "two uploads", [first_upload, second_upload], "en"
        )
    )
    blocker_future = None
    write_future = None

    def occupy_worker() -> None:
        blocker_started.set()
        if not release_blocker.wait(timeout=8):
            raise TimeoutError("test did not release the executor blocker")

    try:
        await asyncio.wait_for(second_prepared.wait(), timeout=5)
        assert first_saved.is_set()
        assert first_url is not None
        deadline = loop.time() + 3
        while backend._pending_cancellable_writes and loop.time() < deadline:
            await asyncio.sleep(0.005)
        assert not backend._pending_cancellable_writes
        assert len(opened_targets) == 1
        first_target = opened_targets[0]
        assert first_target.read_bytes() == _CANCELLABLE_STATIC_PAYLOAD

        blocker_future = loop.run_in_executor(executor, occupy_worker)
        deadline = loop.time() + 3
        while not blocker_started.is_set() and loop.time() < deadline:
            await asyncio.sleep(0.005)
        assert blocker_started.is_set()
        allow_second_save.set()

        deadline = loop.time() + 3
        while not backend._pending_cancellable_writes and loop.time() < deadline:
            await asyncio.sleep(0.005)
        assert backend._pending_cancellable_writes
        write_future = next(iter(backend._pending_cancellable_writes))

        use_private_executor = False
        executor.shutdown(wait=False, cancel_futures=True)
        deadline = loop.time() + 3
        while not write_future.done() and loop.time() < deadline:
            await asyncio.sleep(0.005)
        assert write_future.cancelled()
        release_blocker.set()
        await asyncio.wait_for(blocker_future, timeout=3)

        with pytest.raises(ExceptionGroup) as raised:
            await asyncio.wait_for(send_task, timeout=4)
        assert any(
            isinstance(error, RuntimeError) and "executor stopped" in str(error)
            for error in _leaves(raised.value)
        )
        assert cleanup_calls == [[first_url]]
        assert not first_target.exists(), "completed sibling upload must be compensated"
        assert len(opened_targets) == 1, (
            "the cancelled queued upload must not create a file"
        )
        await asyncio.sleep(0)
        assert not backend._pending_cancellable_writes
        uow.chats.create_message.assert_not_called()
        uow.commit.assert_not_awaited()
    finally:
        release_blocker.set()
        allow_second_save.set()
        use_private_executor = False
        if not send_task.done():
            send_task.cancel("test cleanup")
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(send_task, timeout=4)
        if blocker_future is not None and not blocker_future.done():
            await asyncio.wait_for(blocker_future, timeout=3)
        if write_future is not None and not write_future.done():
            try:
                await asyncio.wait_for(asyncio.shield(write_future), timeout=3)
            except asyncio.CancelledError:
                pass
        executor.shutdown(wait=True, cancel_futures=True)
        await first_upload.close()
        await second_upload.close()
        for target in opened_targets:
            if target.exists():
                target.unlink()
        upload_dir = storage_root / "chat_uploads"
        if upload_dir.is_dir() and not any(upload_dir.iterdir()):
            upload_dir.rmdir()
        if storage_root.is_dir() and not any(storage_root.iterdir()):
            storage_root.rmdir()
    assert worker_threads and all(not worker.is_alive() for worker in worker_threads)


@pytest.mark.asyncio
async def test_real_chat_upload_cancel_after_ready_is_queued_drains_worker(
    monkeypatch, tmp_path
):
    storage_root = tmp_path / "static-ready-race"
    backend = _install_cancellable_static_storage(monkeypatch, storage_root)
    loop = asyncio.get_running_loop()
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="chat-static-test")
    original_run_in_executor = loop.run_in_executor

    def use_private_executor(executor_arg, function, *args):
        if executor_arg is None:
            executor_arg = executor
        return original_run_in_executor(executor_arg, function, *args)

    monkeypatch.setattr(loop, "run_in_executor", use_private_executor)
    original_call_soon_threadsafe = loop.call_soon_threadsafe
    ready_callback_queued = threading.Event()
    queued_callbacks = []

    def hold_ready_callback(callback, *args, **kwargs):
        if getattr(callback, "__name__", "") == "publish_ready":
            queued_callbacks.append((callback, args, kwargs))
            ready_callback_queued.set()
            return None
        return original_call_soon_threadsafe(callback, *args, **kwargs)

    monkeypatch.setattr(loop, "call_soon_threadsafe", hold_ready_callback)
    targets: list[Path] = []
    worker_threads: list[threading.Thread] = []
    original_open = Path.open

    def observe_open(path: Path, mode: str = "r", *args, **kwargs):
        stream = original_open(path, mode, *args, **kwargs)
        if path.resolve().is_relative_to(storage_root.resolve()) and mode == "xb":
            targets.append(path)
            worker_threads.append(threading.current_thread())
        return stream

    monkeypatch.setattr(Path, "open", observe_open)
    attachment_service = attachment_module.ChatAttachmentService()
    dispatcher, uow, chat, user = _cancellable_static_dispatcher(attachment_service)
    upload = _cancellable_static_upload()
    send_task = asyncio.create_task(
        dispatcher.send_message(chat.id, user, "upload", [upload], "en")
    )
    write_future = None

    try:
        await _wait_for_static_writer_event(ready_callback_queued)
        assert len(queued_callbacks) == 1
        assert len(targets) == 1
        target = targets[0]
        assert target.read_bytes() == _CANCELLABLE_STATIC_PAYLOAD
        write_future = next(iter(backend._pending_cancellable_writes))
        assert not write_future.done()

        send_task.cancel("cancel after readiness was queued")
        with pytest.raises(asyncio.CancelledError) as raised:
            await asyncio.wait_for(send_task, timeout=3)
        assert raised.value.args == ("cancel after readiness was queued",)
        assert send_task.cancelled()

        await asyncio.wait_for(asyncio.shield(write_future), timeout=4)
        assert not target.exists(), "worker must abort after cancellation wins delivery"
        await asyncio.sleep(0)
        assert not backend._pending_cancellable_writes

        callback, args, kwargs = queued_callbacks.pop()
        original_call_soon_threadsafe(callback, *args, **kwargs)
        await asyncio.sleep(0)
        uow.chats.create_message.assert_not_called()
        uow.commit.assert_not_awaited()
    finally:
        if not send_task.done():
            send_task.cancel("test cleanup")
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(send_task, timeout=3)
        if write_future is not None and not write_future.done():
            await asyncio.wait_for(asyncio.shield(write_future), timeout=4)
        if queued_callbacks:
            callback, args, kwargs = queued_callbacks.pop()
            original_call_soon_threadsafe(callback, *args, **kwargs)
            await asyncio.sleep(0)
        await upload.close()
        for target in targets:
            if target.exists():
                target.unlink()
        upload_dir = storage_root / "chat_uploads"
        if upload_dir.is_dir() and not any(upload_dir.iterdir()):
            upload_dir.rmdir()
        if storage_root.is_dir() and not any(storage_root.iterdir()):
            storage_root.rmdir()
        executor.shutdown(wait=True, cancel_futures=True)
    assert worker_threads and all(not worker.is_alive() for worker in worker_threads)
