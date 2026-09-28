"""Exact durable-dispatch contracts of the event bus and attachment cleanup."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.core import events
from app.core.events import AttachmentCleanupRequested, EventBus, UserCreated
from app.services import event_handlers

# ---------------------------------------------------------------------------
# EventBus durable dispatch
# ---------------------------------------------------------------------------


def test_deferral_carries_a_fixed_message() -> None:
    assert str(events.DurableEventDeferred()) == "Durable event deferred"


@pytest.mark.asyncio
async def test_durable_publish_without_a_handler_is_rejected_exactly() -> None:
    with pytest.raises(RuntimeError) as error:
        await EventBus().publish(UserCreated(email="a@example.test"), durable=True)

    assert str(error.value) == "No durable event handler registered"


@pytest.mark.asyncio
async def test_a_later_failure_wins_over_an_earlier_deferral() -> None:
    event = UserCreated(email="a@example.test")
    bus = EventBus()

    async def defer(_event: object) -> None:
        raise events.DurableEventDeferred()

    async def fail(_event: object) -> None:
        raise ValueError("otp 123456 for a@example.test")

    bus.subscribe(event.event_type, defer)
    bus.subscribe(event.event_type, fail)

    with pytest.raises(RuntimeError) as error:
        await bus.publish(event, durable=True)

    assert str(error.value) == "Durable event handler failed"
    assert error.value.__cause__ is None


@pytest.mark.asyncio
async def test_all_handlers_succeeding_is_not_a_deferral() -> None:
    event = UserCreated(email="a@example.test")
    bus = EventBus()
    seen: list[str] = []

    async def ok(evt: UserCreated) -> None:
        seen.append(evt.event_id)

    bus.subscribe(event.event_type, ok)

    await bus.publish(event, durable=True)
    assert seen == [event.event_id]


def _stall_dispatch_timer(started: asyncio.Event, release: asyncio.Event | None = None):
    async def pending_wait(tasks, *, timeout):
        del timeout
        await started.wait()
        if release is not None:
            release.set()
        return set(), tasks

    return pending_wait


@pytest.mark.asyncio
async def test_slow_external_delivery_is_awaited_and_logged_with_its_identity() -> None:
    event = AttachmentCleanupRequested(chat_id=uuid4(), attachment_urls=["/static/x"])
    bus = EventBus()
    started = asyncio.Event()
    finished = asyncio.Event()

    async def cleanup(_event: object) -> None:
        started.set()
        await asyncio.sleep(0)
        finished.set()

    bus.subscribe(event.event_type, cleanup)
    with (
        patch.object(
            events.asyncio, "wait", side_effect=_stall_dispatch_timer(started)
        ),
        patch.object(events, "logger") as logger,
    ):
        await bus.publish(event, durable=True)

    assert finished.is_set()
    logger.warning.assert_called_once_with(
        "Durable external delivery exceeded event dispatch timer",
        extra={"event_type": event.event_type, "event_id": event.event_id},
    )


@pytest.mark.asyncio
async def test_other_durable_timeouts_fail_with_a_fixed_message() -> None:
    event = UserCreated(email="a@example.test")
    bus = EventBus()
    started = asyncio.Event()
    release = asyncio.Event()

    async def late_handler(_event: object) -> None:
        started.set()
        await release.wait()

    bus.subscribe(event.event_type, late_handler)
    with (
        patch.object(
            events.asyncio, "wait", side_effect=_stall_dispatch_timer(started, release)
        ),
        pytest.raises(TimeoutError) as error,
    ):
        await bus.publish(event, durable=True)

    assert str(error.value) == "Durable event dispatch timed out"


# ---------------------------------------------------------------------------
# Attachment cleanup handler
# ---------------------------------------------------------------------------


def _session(db: AsyncMock) -> MagicMock:
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=db)
    context.__aexit__ = AsyncMock(return_value=False)
    return context


@pytest.mark.asyncio
async def test_cleanup_queries_references_per_batch_and_reports_totals() -> None:
    urls = [f"/static/chat/{index}" for index in range(130)]
    referenced = {urls[0], urls[129]}
    statements: list[object] = []

    async def execute(statement):
        statements.append(statement)
        rows = MagicMock()
        rows.scalars.return_value.all.return_value = sorted(referenced)
        return rows

    db = AsyncMock()
    db.execute.side_effect = execute
    service = MagicMock()
    service.cleanup_files = AsyncMock()
    event = AttachmentCleanupRequested(chat_id=uuid4(), attachment_urls=urls)

    with (
        patch.object(event_handlers, "async_session", lambda: _session(db)),
        patch(
            "app.services.chat.attachment_service.ChatAttachmentService",
            return_value=service,
        ),
        patch.object(event_handlers, "logger") as logger,
    ):
        await event_handlers.handle_attachment_cleanup_requested(event)

    assert len(statements) == 2
    sql = str(
        statements[0].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert sql.startswith("SELECT DISTINCT attachments.url")
    assert "WHERE attachments.url IN ('/static/chat/0', '/static/chat/1'" in sql
    assert "'/static/chat/128'" not in sql
    assert [call.args[0] for call in service.cleanup_files.await_args_list] == [
        urls[1:128],
        [urls[128]],
    ]
    logger.info.assert_called_once_with(
        "attachment_cleanup_requested: deleted %d file(s), retained %d referenced file(s) for chat=%s",
        128,
        2,
        event.chat_id,
    )
