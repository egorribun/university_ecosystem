"""Integration tests for NATS JetStream message delivery (Wave 12.2).

Uses AsyncMock to simulate the NATS broker so these tests can run in CI
without a live NATS server.  The tests verify:

  - outbox message retry logic (error_count increments on dispatch failure)
  - DLQ promotion when max retries are exhausted
  - JetStream message schema validation (the _NatsTaskPayload model)
  - publish_core skips when the broker is not connected

Run with:
    pytest tests/integration/test_nats_jetstream.py -v -m integration
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from nats.js.api import RetentionPolicy, StorageType

from app.core.nats_broker import NatsTaskBroker, _NatsTaskPayload

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_broker_with_mocked_js() -> tuple[NatsTaskBroker, AsyncMock]:
    """Return a broker whose JetStream client is an AsyncMock.

    WHY: We want to verify publish() behaviour (trace injection, serialisation)
    without a live NATS server.  The mock captures every publish call so we can
    assert on subject + payload.
    """
    broker = NatsTaskBroker()
    mock_js = AsyncMock()
    broker._js = mock_js
    return broker, mock_js


def _make_task_payload(name: str = "test.task") -> dict:
    return {
        "id": str(uuid.uuid4()),
        "name": name,
        "args": [],
        "kwargs": {},
        "trace_context": {},
    }


# ---------------------------------------------------------------------------
# _NatsTaskPayload schema tests
# ---------------------------------------------------------------------------


def test_nats_task_payload_valid_schema() -> None:
    """Valid task payloads must deserialize without error.

    WHY: The _NatsTaskPayload model is the first line of defense against
    malformed NATS messages crashing the worker loop.
    """
    raw = _make_task_payload("email.send")
    payload = _NatsTaskPayload.model_validate(raw)
    assert payload.name == "email.send"
    assert isinstance(payload.args, list)
    assert isinstance(payload.kwargs, dict)


def test_nats_task_payload_rejects_empty_name() -> None:
    """A task payload with an empty/whitespace name must be rejected.

    WHY: An empty task name would cause handler lookup to silently fall
    through (no handler found) and the message to be nak'd indefinitely.
    """
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _NatsTaskPayload.model_validate({**_make_task_payload(), "name": ""})


def test_nats_task_payload_rejects_missing_name() -> None:
    """A task payload without the 'name' field must be rejected."""
    from pydantic import ValidationError

    raw = _make_task_payload()
    del raw["name"]
    with pytest.raises(ValidationError):
        _NatsTaskPayload.model_validate(raw)


def test_nats_task_payload_rejects_whitespace_only_name() -> None:
    """A whitespace-only task name is semantically empty and must fail."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _NatsTaskPayload.model_validate({**_make_task_payload(), "name": "   "})


# ---------------------------------------------------------------------------
# publish() — JetStream path
# ---------------------------------------------------------------------------


async def test_publish_jetstream_encodes_json_payload() -> None:
    """publish() must serialize the payload as JSON and call js.publish.

    WHY: If orjson / json encoding is broken the ws-hub and file-processor
    will receive garbled frames.
    """
    broker, mock_js = _build_broker_with_mocked_js()
    subject = "tasks.test"
    data = {"user_id": str(uuid.uuid4()), "action": "send_email"}

    await broker.publish(subject, data)

    mock_js.publish.assert_called_once()
    call_subject, call_body = mock_js.publish.call_args[0]
    assert call_subject == subject
    decoded = json.loads(call_body.decode())
    assert decoded["user_id"] == data["user_id"]
    assert decoded["action"] == data["action"]


async def test_publish_jetstream_propagates_subject_correctly() -> None:
    """publish() must forward the caller's subject verbatim.

    WHY: Subject routing drives consumer subscriptions; a mangled subject
    silently drops messages to the wrong stream.
    """
    broker, mock_js = _build_broker_with_mocked_js()

    await broker.publish("files.process", {"file_id": "abc"})

    call_subject = mock_js.publish.call_args[0][0]
    assert call_subject == "files.process"


async def test_nats_jetstream_five_file_backed_streams_with_seven_day_retention() -> (
    None
):
    """NatsTaskBroker.connect() provisions 5 file-backed streams with 7-day retention."""
    broker = NatsTaskBroker()

    mock_js = AsyncMock()
    mock_nc = AsyncMock()
    mock_nc.jetstream = MagicMock(return_value=mock_js)
    mock_nc.is_connected = True

    with patch(
        "app.core.nats_broker.nats.connect", new=AsyncMock(return_value=mock_nc)
    ):
        await broker.connect()

    assert mock_js.add_stream.await_count == 5
    expected_streams = {
        "TASK_QUEUE": ["tasks.>"],
        "FILES_PROCESS": ["files.process"],
        "CHAT_EVENTS": ["chat.*"],
        "NOTIFICATIONS_EVENTS": ["notifications.*"],
        "OUTBOX_EVENTS": ["outbox.*"],
    }

    for call in mock_js.add_stream.call_args_list:
        cfg = call.kwargs["config"]
        assert cfg.name in expected_streams
        assert cfg.subjects == expected_streams[cfg.name]
        assert cfg.storage == StorageType.FILE
        assert cfg.retention == RetentionPolicy.LIMITS
        assert cfg.max_age == 604_800


async def test_publish_injects_nats_msg_id_header() -> None:
    """publish(), enqueue(), and publish_core() must inject Nats-Msg-Id headers."""
    broker, mock_js = _build_broker_with_mocked_js()

    # 1. publish with explicit msg_id
    explicit_id = str(uuid.uuid4())
    await broker.publish("chat.event", {"event_id": "evt-123"}, msg_id=explicit_id)
    headers = mock_js.publish.call_args.kwargs["headers"]
    assert headers["Nats-Msg-Id"] == explicit_id

    # 2. publish with payload event_id fallback
    mock_js.publish.reset_mock()
    await broker.publish("chat.event", {"event_id": "evt-456"})
    headers = mock_js.publish.call_args.kwargs["headers"]
    assert headers["Nats-Msg-Id"] == "evt-456"

    # 3. enqueue generates task_id and uses it as Nats-Msg-Id
    mock_js.publish.reset_mock()
    task_id = await broker.enqueue("test.task")
    headers = mock_js.publish.call_args.kwargs["headers"]
    assert headers["Nats-Msg-Id"] == task_id

    # 4. publish_core injects Nats-Msg-Id
    mock_nc = AsyncMock()
    mock_nc.is_connected = True
    broker._nc = mock_nc
    await broker.publish_core("chat.live", {"id": "msg-789"})
    headers = mock_nc.publish.call_args.kwargs["headers"]
    assert headers["Nats-Msg-Id"] == "msg-789"


# ---------------------------------------------------------------------------
# publish_core() — Core NATS (ephemeral, fire-and-forget)
# ---------------------------------------------------------------------------


async def test_publish_core_skips_when_not_connected() -> None:
    """publish_core() must not raise when the broker is disconnected.

    WHY: The chat broadcast path calls publish_core() in a hot loop.  If NATS
    is unavailable and publish_core() raises, the in-process fan-out (which
    already delivered the message) is interrupted unnecessarily.
    """
    broker = NatsTaskBroker()
    # Deliberately leave _nc = None (disconnected state)
    # Should be a no-op, not an exception.
    await broker.publish_core("chat.direct", {"msg": "hello"})  # must not raise


async def test_publish_core_publishes_when_connected() -> None:
    """publish_core() must call nc.publish when the broker is connected."""
    broker = NatsTaskBroker()
    mock_nc = AsyncMock()
    mock_nc.is_connected = True
    broker._nc = mock_nc

    await broker.publish_core("chat.direct", {"chat_id": "c-123", "text": "hi"})

    mock_nc.publish.assert_called_once()
    call_subject = mock_nc.publish.call_args[0][0]
    assert call_subject == "chat.direct"


# ---------------------------------------------------------------------------
# enqueue() — task routing
# ---------------------------------------------------------------------------


async def test_enqueue_writes_to_correct_subject() -> None:
    """enqueue() must publish to 'tasks.<task_name>' on JetStream.

    WHY: The durable consumer subscribes to 'tasks.>' — if the subject prefix
    changes the consumer never receives the message.
    """
    broker, mock_js = _build_broker_with_mocked_js()

    task_id = await broker.enqueue("email.send_welcome", "user@test.com")

    mock_js.publish.assert_called_once()
    call_subject = mock_js.publish.call_args[0][0]
    assert call_subject == "tasks.email.send_welcome"
    assert isinstance(task_id, str)


async def test_enqueue_payload_contains_required_fields() -> None:
    """Enqueued task payload must carry id, name, args, kwargs, trace_context."""
    broker, mock_js = _build_broker_with_mocked_js()

    await broker.enqueue("notifications.send", "user_id_abc", channel="push")

    call_body = mock_js.publish.call_args[0][1]
    payload = json.loads(call_body.decode())

    assert payload.get("id")
    assert payload["name"] == "notifications.send"
    assert "user_id_abc" in payload["args"]
    assert payload["kwargs"].get("channel") == "push"
    assert "trace_context" in payload


# ---------------------------------------------------------------------------
# Outbox retry simulation (no DB, just logic)
# ---------------------------------------------------------------------------


async def test_outbox_worker_process_batch_increments_error_count_on_failure() -> None:
    """process_batch() must increment stored_event.error_count on dispatch failure.

    WHY: If error_count is not incremented the event is retried forever,
    filling the outbox table and preventing newer events from being dispatched.

    This test mocks the DB session factory and the event bus to isolate the
    OutboxWorker retry logic from infrastructure dependencies.
    """
    import uuid as _uuid
    from unittest.mock import MagicMock

    from app.workers.outbox import OutboxWorker

    # Build a synthetic StoredEvent mock with a realistic initial state.
    mock_event = MagicMock()
    mock_event.id = _uuid.uuid4()
    mock_event.event_type = "test.retry"
    mock_event.error_count = 0
    mock_event.processed_at = None

    # Mock db session that returns our synthetic event from the query.
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_event]

    mock_count_result = MagicMock()
    mock_count_result.scalar_one.return_value = 1

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[mock_result, mock_count_result])
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=None)

    mock_session_factory = MagicMock(return_value=mock_db)

    worker = OutboxWorker(poll_interval=0.0, batch_size=1, max_retries=3)

    with patch("app.workers.outbox.async_session", mock_session_factory):
        with patch("app.workers.outbox.event_bus") as mock_bus:
            mock_bus.emit = AsyncMock(side_effect=RuntimeError("broker down"))
            await worker.process_batch()

    # The worker must increment error_count on dispatch failure.
    assert mock_event.error_count == 1, (
        f"expected error_count=1 after failed dispatch, got {mock_event.error_count}"
    )


# ---------------------------------------------------------------------------
# Reconnect resilience — transient JetStream error does not kill the broker
# ---------------------------------------------------------------------------


async def test_publish_retries_on_transient_js_error() -> None:
    """publish() must propagate the error on the first call but leave the broker intact.

    WHY: A transient JetStream error (e.g. stream not ready) must not put the
    broker into a permanently broken state.  After the first failure the broker
    must be callable again without re-connecting.  This simulates the outbox
    worker's retry loop calling publish() again after a brief back-off.
    """
    broker, mock_js = _build_broker_with_mocked_js()

    # First call: JetStream is transiently unavailable.
    mock_js.publish.side_effect = RuntimeError("nats: timeout")
    with pytest.raises(RuntimeError, match="nats: timeout"):
        await broker.publish("tasks.test", {"attempt": 1})

    # Broker must still be usable: second call succeeds.
    mock_js.publish.side_effect = None
    await broker.publish("tasks.test", {"attempt": 2})
    assert mock_js.publish.call_count == 2, (
        "broker must remain functional after a single transient publish error"
    )


# ---------------------------------------------------------------------------
# Pipeline (batched) publish — multiple messages forwarded in order
# ---------------------------------------------------------------------------


async def test_publish_pipeline_preserves_message_order() -> None:
    """Sequential publish() calls must deliver messages in FIFO order.

    WHY: JetStream guarantees at-least-once delivery in publish order for a
    given producer.  If the broker or mock reorders calls the consumer may
    process tasks out of sequence, corrupting dependent state (e.g. a
    'user_updated' event arriving before 'user_created').
    """
    broker, mock_js = _build_broker_with_mocked_js()

    messages = [
        ("tasks.step1", {"step": 1}),
        ("tasks.step2", {"step": 2}),
        ("tasks.step3", {"step": 3}),
    ]
    for subject, payload in messages:
        await broker.publish(subject, payload)

    assert mock_js.publish.call_count == len(messages), (
        f"Expected {len(messages)} publish calls, got {mock_js.publish.call_count}"
    )
    for i, call in enumerate(mock_js.publish.call_args_list):
        actual_subject = call[0][0]
        assert actual_subject == messages[i][0], (
            f"Message {i} subject mismatch: expected '{messages[i][0]}', "
            f"got '{actual_subject}' — publish order must be preserved"
        )


# ---------------------------------------------------------------------------
# DLQ promotion — event moves to dead-letter queue after max_retries
# ---------------------------------------------------------------------------


async def test_outbox_worker_promotes_to_dlq_after_max_retries() -> None:
    """process_batch() must mark an event as failed (DLQ) after max_retries exhausted.

    WHY: Without DLQ promotion a poisoned event stays in the 'pending' queue
    forever, blocking all subsequent events (head-of-line blocking) and
    exhausting retry workers.

    The test sets error_count = max_retries so the *next* failure triggers the
    DLQ path rather than a simple increment.
    """
    from unittest.mock import MagicMock

    from app.workers.outbox import OutboxWorker

    max_retries = 3
    mock_event = MagicMock()
    mock_event.id = uuid.uuid4()
    mock_event.event_type = "test.dlq"
    mock_event.error_count = max_retries  # already at the threshold
    mock_event.processed_at = None
    mock_event.status = "pending"

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_event]

    mock_count_result = MagicMock()
    mock_count_result.scalar_one.return_value = 1

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[mock_result, mock_count_result])
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=None)

    mock_session_factory = MagicMock(return_value=mock_db)

    worker = OutboxWorker(poll_interval=0.0, batch_size=1, max_retries=max_retries)

    with patch("app.workers.outbox.async_session", mock_session_factory):
        with patch("app.workers.outbox.event_bus") as mock_bus:
            mock_bus.emit = AsyncMock(side_effect=RuntimeError("broker down"))
            await worker.process_batch()

    # After exceeding max_retries the event status must change to reflect DLQ
    # promotion (the exact field name depends on the OutboxWorker implementation;
    # we accept either error_count > max_retries OR status changed to 'failed').
    promoted_to_dlq = mock_event.error_count > max_retries or getattr(
        mock_event, "status", "pending"
    ) in ("failed", "dlq")
    assert promoted_to_dlq, (
        f"Event must be promoted to DLQ after {max_retries} retries. "
        f"error_count={mock_event.error_count}, status={getattr(mock_event, 'status', 'n/a')}"
    )


# ---------------------------------------------------------------------------
# CDC Outbox Worker JetStream Integration Tests
# ---------------------------------------------------------------------------


async def test_cdc_outbox_worker_publishes_to_jetstream_with_dedup_header() -> None:
    """CdcOutboxWorker must publish CDC insert events to JetStream stream OUTBOX_EVENTS
    (subject outbox.events.<event_type>) with Nats-Msg-Id: <stored_event.id> header and sub-5ms latency.
    """
    import time

    from app.workers.cdc_outbox import CDCInsertRecord, CdcOutboxWorker

    broker, mock_js = _build_broker_with_mocked_js()
    worker = CdcOutboxWorker(nats_broker=broker)

    event_id = str(uuid.uuid4())
    record = CDCInsertRecord(
        relation_id=1,
        relation_name="stored_events",
        data={
            "id": event_id,
            "event_type": "UserCreated",
            "aggregate_type": "User",
            "aggregate_id": "usr-int-1",
            "payload": {"user_id": "usr-int-1", "email": "cdc_integration@test.com"},
            "metadata_": {"correlation_id": "corr-cdc-int"},
        },
        lsn=99999,
    )

    t0 = time.perf_counter()
    event = await worker.dispatch_insert_record(record)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert elapsed_ms < 5.0, (
        f"CDC dispatch latency was {elapsed_ms:.3f}ms (expected < 5ms)"
    )
    assert event is not None
    mock_js.publish.assert_called_once()

    call_args = mock_js.publish.call_args
    call_subject = call_args[0][0]
    headers = call_args.kwargs.get("headers", {})

    assert call_subject == "outbox.events.UserCreated"
    assert headers.get("Nats-Msg-Id") == event_id
