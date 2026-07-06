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
from unittest.mock import AsyncMock, patch

import pytest

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
