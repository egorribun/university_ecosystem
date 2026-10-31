"""Trusted tenant metadata and bounded polling-outbox context contracts."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import app.core.tenant as tenant_context
import app.services.notifications.delivery as notifications_delivery
import app.workers.outbox as outbox_module
from app.core.events import (
    EventBus,
    EventEmitterMixin,
    EventMetadata,
    NewsCreated,
    capture_domain_events,
)
from app.models.domain_events import StoredEvent

_TENANT_A = str(uuid.UUID("11111111-1111-4111-8111-111111111111"))
_TENANT_B = str(uuid.UUID("22222222-2222-4222-8222-222222222222"))


@contextmanager
def _context(tenant_id: str, *, bypass: bool = False) -> Iterator[None]:
    tenant_token = tenant_context.tenant_id_ctx.set(tenant_id)
    bypass_token = tenant_context.bypass_rls_ctx.set(bypass)
    try:
        yield
    finally:
        tenant_context.bypass_rls_ctx.reset(bypass_token)
        tenant_context.tenant_id_ctx.reset(tenant_token)


def _scope() -> tuple[str, bool]:
    return (
        tenant_context.tenant_id_ctx.get(),
        tenant_context.bypass_rls_ctx.get(),
    )


def _stored_event(metadata) -> StoredEvent:
    user_id = uuid.uuid4()
    return StoredEvent(
        id=uuid.uuid4(),
        event_type="user.created",
        aggregate_type="User",
        aggregate_id=str(user_id),
        payload={
            "user_id": str(user_id),
            "email": "tenant-contract@example.test",
            "tenant_id": _TENANT_B,
            "metadata": {"tenant_id": _TENANT_B},
        },
        metadata_=metadata,
    )


@pytest.mark.parametrize("recording_scope", ["", _TENANT_A], ids=["legacy", "A"])
@pytest.mark.parametrize("flush_scope", ["", _TENANT_B], ids=["flush-empty", "flush-B"])
def test_recorded_event_captures_trusted_tenant_before_deferred_flush(
    recording_scope, flush_scope
):
    class Emitter(EventEmitterMixin):
        def __init__(self):
            self.id = uuid.uuid4()

    emitter = Emitter()
    metadata = EventMetadata(
        correlation_id="synthetic-correlation",
        causation_id="synthetic-cause",
        source="contract-source",
        retry_count=2,
        max_retries=7,
    )
    vars(metadata)["tenant_id"] = _TENANT_B
    event = NewsCreated(news_id=emitter.id, metadata=metadata)
    vars(event)["tenant_id"] = _TENANT_B
    with _context(recording_scope, bypass=True):
        emitter.record_event(event)
    assert emitter._pending_domain_events[0] is event
    metadata_values = (
        event.metadata.correlation_id,
        event.metadata.causation_id,
        event.metadata.user_id,
        event.metadata.source,
        event.metadata.retry_count,
        event.metadata.max_retries,
    )
    expected_values = (
        "synthetic-correlation",
        "synthetic-cause",
        None,
        "contract-source",
        2,
        7,
    )
    assert metadata_values == expected_values

    session = SimpleNamespace(new={emitter}, dirty=set(), deleted=set(), info={})
    with _context(flush_scope):
        capture_domain_events(session, None)

    (stored,) = session.info["_pending_stored_events"]
    expected = {
        "event_id": event.event_id,
        "occurred_at": event.occurred_at.isoformat(),
        "correlation_id": "synthetic-correlation",
        "user_id": None,
    }
    if recording_scope:
        expected["tenant_id"] = recording_scope
    assert stored.metadata_ == expected
    assert stored.payload["tenant_id"] == _TENANT_B
    assert emitter._pending_domain_events == []


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["", _TENANT_A], ids=["legacy-null", "A"])
async def test_notification_request_captures_only_trusted_tenant(scope, monkeypatch):
    user_id = uuid.uuid4()
    database = SimpleNamespace(
        execute=AsyncMock(),
        flush=AsyncMock(),
        add=Mock(),
    )
    monkeypatch.setattr(
        notifications_delivery,
        "filter_user_ids_by_topic",
        AsyncMock(return_value=[user_id]),
    )
    monkeypatch.setattr(notifications_delivery, "_is_push_configured", lambda: False)

    with _context(scope, bypass=True):
        async with asyncio.timeout(2):
            count = await notifications_delivery.create_notifications_for_users(
                database,
                title="Synthetic tenant request",
                user_ids=[user_id],
                payload_data={"tenant_id": _TENANT_B},
                push_via_outbox_only=True,
            )

    assert count == 1
    database.add.assert_called_once()
    stored = database.add.call_args.args[0]
    assert stored.event_type == "notification.delivery_requested"
    expected = {"tenant_id": scope} if scope else None
    assert stored.metadata_ == expected
    assert stored.payload["payload_data"] == {"tenant_id": _TENANT_B}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "metadata",
    [
        pytest.param(None, id="null-metadata"),
        pytest.param({}, id="empty-metadata"),
        pytest.param(
            {"event_id": "legacy-event", "correlation_id": "legacy-correlation"},
            id="legacy-keys",
        ),
    ],
)
async def test_legacy_dispatch_ignores_payload_tenant_and_clears_ambient_scope(
    metadata, monkeypatch
):
    bus = EventBus()
    observed = []
    metadata_types = []

    async def handle(event):
        observed.append(_scope())
        metadata_types.append(isinstance(event.metadata, EventMetadata))

    bus.subscribe("user.created", handle)
    monkeypatch.setattr(outbox_module, "event_bus", bus)
    with _context(_TENANT_B, bypass=True):
        try:
            async with asyncio.timeout(2):
                await outbox_module.OutboxWorker()._dispatch_event(
                    _stored_event(metadata)
                )
        finally:
            assert _scope() == (_TENANT_B, True)
    assert observed == [("", False)]
    assert metadata_types == [True]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bypass", [False, True], ids=["ordinary-caller", "bypass-caller"]
)
@pytest.mark.parametrize("outcome", ["success", "error", "cancel"])
async def test_dispatch_restores_caller_scope_after_every_outcome(
    outcome, bypass, monkeypatch
):
    bus = EventBus()
    entered = asyncio.Event()
    release = asyncio.Event()
    observed = []
    handler_finally = []
    caller_finally = []

    async def handle(_event):
        observed.append(_scope())
        entered.set()
        try:
            if outcome == "error":
                raise RuntimeError("synthetic tenant handler failure")
            if outcome == "cancel":
                await release.wait()
        finally:
            handler_finally.append(_scope())

    bus.subscribe("user.created", handle)
    monkeypatch.setattr(outbox_module, "event_bus", bus)
    stored = _stored_event({"tenant_id": _TENANT_A, "bypass_rls": True})

    async def dispatch_in_caller():
        try:
            await outbox_module.OutboxWorker()._dispatch_event(stored)
        finally:
            # Observe restoration inside the cancelled task, not only its parent.
            caller_finally.append(_scope())

    with _context(_TENANT_B, bypass=bypass):
        task = None
        try:
            async with asyncio.timeout(2):
                if outcome == "cancel":
                    task = asyncio.create_task(dispatch_in_caller())
                    await entered.wait()
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await task
                elif outcome == "error":
                    with pytest.raises(
                        RuntimeError, match="Durable event handler failed"
                    ):
                        await dispatch_in_caller()
                else:
                    await dispatch_in_caller()
        finally:
            release.set()
            if task is not None:
                if not task.done():
                    task.cancel()
                async with asyncio.timeout(2):
                    await asyncio.gather(task, return_exceptions=True)
            assert _scope() == (_TENANT_B, bypass)

    assert observed == [(_TENANT_A, False)]
    assert handler_finally == [(_TENANT_A, False)]
    assert caller_finally == [(_TENANT_B, bypass)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "malformed",
    [
        pytest.param(None, id="present-null"),
        pytest.param("", id="present-empty"),
        pytest.param("not-a-uuid", id="invalid-uuid"),
        pytest.param("   ", id="whitespace"),
        pytest.param(True, id="boolean"),
        pytest.param(1, id="integer"),
        pytest.param([], id="array"),
        pytest.param({}, id="object"),
    ],
)
async def test_malformed_persisted_tenant_fails_before_publish(malformed, monkeypatch):
    bus = EventBus()
    observed = []

    async def handle(_event):
        observed.append(_scope())

    bus.subscribe("user.created", handle)
    monkeypatch.setattr(outbox_module, "event_bus", bus)
    stored = _stored_event({"tenant_id": malformed})
    with _context(_TENANT_B, bypass=True):
        try:
            async with asyncio.timeout(2):
                with pytest.raises(outbox_module.PermanentOutboxError):
                    await outbox_module.OutboxWorker()._dispatch_event(stored)
        finally:
            assert _scope() == (_TENANT_B, True)
    assert observed == []
