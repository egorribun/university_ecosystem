"""Legacy forwarded attachments can share one stored object URL."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.events import AttachmentCleanupRequested
from app.services import event_handlers
from app.services.chat.attachment_service import (
    AttachmentCleanupError,
    ChatAttachmentService,
)


def _session(db: AsyncMock) -> MagicMock:
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=db)
    context.__aexit__ = AsyncMock(return_value=False)
    return context


@pytest.mark.asyncio
async def test_cleanup_skips_legacy_url_still_referenced_by_another_attachment() -> (
    None
):
    shared = "https://objects.example.test/chat/shared"
    orphan = "https://objects.example.test/chat/orphan"
    db = AsyncMock()
    db.execute.return_value = MagicMock()
    db.execute.return_value.scalars.return_value.all.return_value = [shared]
    service = MagicMock()
    service.cleanup_files = AsyncMock()
    event = AttachmentCleanupRequested(
        chat_id=uuid4(), attachment_urls=[shared, orphan, shared]
    )

    with (
        patch.object(event_handlers, "async_session", lambda: _session(db)),
        patch(
            "app.services.chat.attachment_service.ChatAttachmentService",
            return_value=service,
        ),
    ):
        await event_handlers.handle_attachment_cleanup_requested(event)

    db.execute.assert_awaited_once()
    service.cleanup_files.assert_awaited_once_with([orphan], durable=True)


@pytest.mark.asyncio
async def test_cleanup_database_error_never_deletes_an_unverified_blob() -> None:
    db = AsyncMock()
    db.execute.side_effect = OSError("database unavailable")
    service = MagicMock()
    service.cleanup_files = AsyncMock()
    event = AttachmentCleanupRequested(
        chat_id=uuid4(), attachment_urls=["https://objects.example.test/chat/a"]
    )
    with (
        patch.object(event_handlers, "async_session", lambda: _session(db)),
        patch(
            "app.services.chat.attachment_service.ChatAttachmentService",
            return_value=service,
        ),
        pytest.raises(OSError, match="database unavailable"),
    ):
        await event_handlers.handle_attachment_cleanup_requested(event)
    service.cleanup_files.assert_not_awaited()


@pytest.mark.asyncio
async def test_cleanup_queries_and_deletes_large_legacy_payload_in_bounded_chunks() -> (
    None
):
    db = AsyncMock()
    db.execute.return_value = MagicMock()
    db.execute.return_value.scalars.return_value.all.return_value = []
    service = MagicMock()
    service.cleanup_files = AsyncMock()
    urls = [f"https://objects.example.test/chat/{index}" for index in range(129)]
    event = AttachmentCleanupRequested(chat_id=uuid4(), attachment_urls=urls)
    with (
        patch.object(event_handlers, "async_session", lambda: _session(db)),
        patch(
            "app.services.chat.attachment_service.ChatAttachmentService",
            return_value=service,
        ),
    ):
        await event_handlers.handle_attachment_cleanup_requested(event)
    assert db.execute.await_count == 2
    assert service.cleanup_files.await_count == 2
    assert service.cleanup_files.await_args_list[0].args == (urls[:128],)
    assert service.cleanup_files.await_args_list[1].args == (urls[128:],)
    assert all(
        call.kwargs == {"durable": True}
        for call in service.cleanup_files.await_args_list
    )


@pytest.mark.asyncio
async def test_durable_cleanup_limits_in_flight_storage_deletes() -> None:
    started = 0
    active = 0
    peak = 0
    first_batch_started = asyncio.Event()
    release = asyncio.Event()

    async def delete_file(_url: str) -> None:
        nonlocal started, active, peak
        started += 1
        active += 1
        peak = max(peak, active)
        if started >= 8:
            first_batch_started.set()
        try:
            await release.wait()
        finally:
            active -= 1

    backend = SimpleNamespace(
        delete_file=delete_file, exists=AsyncMock(return_value=False)
    )
    urls = [f"/static/chat/{index}" for index in range(24)]
    with patch("app.utils.files._get_storage_backend", return_value=backend):
        task = asyncio.create_task(
            ChatAttachmentService().cleanup_files(urls, durable=True)
        )
        try:
            await asyncio.wait_for(first_batch_started.wait(), timeout=2)
            assert peak <= 8
        finally:
            release.set()
            await task
    assert started == len(urls)


@pytest.mark.asyncio
async def test_durable_cleanup_attempts_later_batch_then_retries_failed_first_batch() -> (
    None
):
    calls: list[str] = []
    failed_url = "/static/chat/0"
    backend = SimpleNamespace()

    async def delete_file(url: str) -> None:
        calls.append(url)
        if url == failed_url and calls.count(url) == 1:
            raise OSError("retry this object")

    backend.delete_file = delete_file
    backend.exists = AsyncMock(
        side_effect=lambda url: url == failed_url and calls.count(url) == 1
    )
    urls = [f"/static/chat/{index}" for index in range(9)]
    with patch("app.utils.files._get_storage_backend", return_value=backend):
        with pytest.raises(RuntimeError, match="Attachment cleanup failed"):
            await ChatAttachmentService().cleanup_files(urls, durable=True)
        assert calls[-1] == urls[-1]
        await ChatAttachmentService().cleanup_files(urls, durable=True)
    assert calls.count(failed_url) == 2


@pytest.mark.asyncio
async def test_durable_cleanup_accepts_ambiguous_delete_only_after_absence_probe() -> (
    None
):
    backend = SimpleNamespace()
    backend.delete_file = AsyncMock(side_effect=OSError("ambiguous delete"))
    backend.exists = AsyncMock(return_value=False)
    with patch("app.utils.files._get_storage_backend", return_value=backend):
        await ChatAttachmentService().cleanup_files(["/static/chat/gone"], durable=True)
    backend.exists.assert_awaited_once_with("/static/chat/gone")


@pytest.mark.asyncio
async def test_durable_cleanup_naks_when_ambiguous_delete_cannot_be_verified() -> None:
    backend = SimpleNamespace()
    backend.delete_file = AsyncMock(side_effect=OSError("recipient@example.test"))
    backend.exists = AsyncMock(side_effect=OSError("provider secret 123456"))
    with patch("app.utils.files._get_storage_backend", return_value=backend):
        with pytest.raises(AttachmentCleanupError) as error:
            await ChatAttachmentService().cleanup_files(
                ["/static/chat/unknown"], durable=True
            )
    assert "recipient@example.test" not in str(error.value)
    assert "123456" not in str(error.value)
