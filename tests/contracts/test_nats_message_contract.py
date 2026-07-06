"""Contract tests for NATS messages exchanged between backend and ws-hub (Wave 13).

Existing coverage: chat.direct message schema (Wave 5/6).

Wave 13 additions:
  - chat.message_sent event (OutboxWorker → ws-hub)
  - chat.deleted event
  - user.created domain event
  - notification.sent event
  - files.process task envelope
  - task envelope schema validation (id, name, args, kwargs, trace_context)

WHY pact-python on non-Windows only: pact requires a native Pact binary that
is not available as a prebuilt wheel for Windows.  All tests in this file are
skipped on Windows CI runners to avoid false negatives.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

pact_lib = None
if sys.platform != "win32":
    try:
        import pact

        pact_lib = pact
    except ImportError:
        pass

if pact_lib is None:
    pytestmark = pytest.mark.skip(reason="pact-python is not installed")

    class DummyPact:
        pass

    Pact = DummyPact
    match = None
else:
    Pact = pact_lib.Pact
    match = pact_lib.match

PACT_DIR = Path(__file__).parent / "pacts"
CONSUMER_NAME = "ws-hub"
PROVIDER_NAME = "university-backend"


@pytest.fixture(scope="module")
def pact() -> Pact:
    PACT_DIR.mkdir(parents=True, exist_ok=True)
    p = Pact(CONSUMER_NAME, PROVIDER_NAME)
    yield p.with_specification("V4")
    p.write_file(PACT_DIR, overwrite=True)


# ---------------------------------------------------------------------------
# Handler helpers — validate incoming message shape
# ---------------------------------------------------------------------------


def _nats_chat_message_handler(
    msg: str | bytes | None, context: dict[str, Any]
) -> dict[str, Any]:
    assert msg is not None
    payload = json.loads(msg)
    assert "chat_id" in payload
    assert "message_id" in payload
    assert "content" in payload
    assert "sender_id" in payload
    return payload


def _nats_chat_deleted_handler(
    msg: str | bytes | None, context: dict[str, Any]
) -> dict[str, Any]:
    assert msg is not None
    payload = json.loads(msg)
    assert "chat_id" in payload
    assert "participant_id" in payload
    return payload


def _nats_user_created_handler(
    msg: str | bytes | None, context: dict[str, Any]
) -> dict[str, Any]:
    assert msg is not None
    payload = json.loads(msg)
    assert "user_id" in payload
    assert "email" in payload
    return payload


def _nats_notification_sent_handler(
    msg: str | bytes | None, context: dict[str, Any]
) -> dict[str, Any]:
    assert msg is not None
    payload = json.loads(msg)
    assert "notification_id" in payload
    assert "user_id" in payload
    assert "notification_type" in payload
    return payload


def _nats_files_process_handler(
    msg: str | bytes | None, context: dict[str, Any]
) -> dict[str, Any]:
    assert msg is not None
    payload = json.loads(msg)
    # Task envelope: must carry id, name; file-processor reads name to route.
    assert "id" in payload
    assert "name" in payload
    return payload


def _nats_task_envelope_handler(
    msg: str | bytes | None, context: dict[str, Any]
) -> dict[str, Any]:
    assert msg is not None
    payload = json.loads(msg)
    assert payload.get("id")
    assert payload.get("name")
    assert isinstance(payload.get("args", []), list)
    assert isinstance(payload.get("kwargs", {}), dict)
    assert isinstance(payload.get("trace_context", {}), dict)
    return payload


# ---------------------------------------------------------------------------
# Existing test (Wave 5/6 — preserved)
# ---------------------------------------------------------------------------


def test_nats_direct_message_contract(pact: Pact) -> None:
    """Contract: ws-hub expects direct message events in this schema."""
    (
        pact.upon_receiving("a direct chat message event", "Async")
        .with_body(
            {
                "chat_id": match.like("chat-uuid-123"),
                "message_id": match.like("msg-uuid-456"),
                "content": match.like("Hello there!"),
                "sender_id": match.like("user-uuid-789"),
            },
            "application/json",
        )
        .with_metadata({"nats_subject": "chat.direct"})
    )
    pact.verify(_nats_chat_message_handler, "Async")


# ---------------------------------------------------------------------------
# Wave 13: Additional NATS subject contracts
# ---------------------------------------------------------------------------


def test_nats_chat_message_sent_contract(pact: Pact) -> None:
    """Contract: ws-hub expects chat.message_sent domain events from the OutboxWorker.

    WHY: The OutboxWorker publishes MessageSent domain events that ws-hub
    subscribes to for live push notifications.  This schema is the authoritative
    cross-service contract.
    """
    (
        pact.upon_receiving("a chat message_sent domain event", "Async")
        .with_body(
            {
                "chat_id": match.like("chat-uuid-001"),
                "message_id": match.like("msg-uuid-001"),
                "sender_id": match.like("user-uuid-001"),
                "content_preview": match.like("Hello world"),
            },
            "application/json",
        )
        .with_metadata({"nats_subject": "chat.message_sent"})
    )
    pact.verify(_nats_chat_message_handler, "Async")


def test_nats_chat_deleted_contract(pact: Pact) -> None:
    """Contract: ws-hub expects chat.deleted events to invalidate its cache.

    WHY: RED-04 (audit 2026-03-14) — ws-hub must close any open WebSocket
    connections for participants of a deleted chat and drop its cache entry
    within one NATS delivery cycle.
    """
    (
        pact.upon_receiving("a chat deleted event", "Async")
        .with_body(
            {
                "chat_id": match.like("chat-uuid-del"),
                "participant_id": match.like("user-uuid-del"),
            },
            "application/json",
        )
        .with_metadata({"nats_subject": "chat.deleted"})
    )
    pact.verify(_nats_chat_deleted_handler, "Async")


def test_nats_user_created_contract(pact: Pact) -> None:
    """Contract: downstream consumers expect user.created events in this schema.

    WHY: ws-hub and notification services subscribe to user.created to provision
    per-user data structures (presence slots, notification preferences).  A schema
    break here silently prevents new user onboarding.
    """
    (
        pact.upon_receiving("a user.created domain event", "Async")
        .with_body(
            {
                "user_id": match.like("user-uuid-new"),
                "email": match.like("newuser@university.test"),
            },
            "application/json",
        )
        .with_metadata({"nats_subject": "user.created"})
    )
    pact.verify(_nats_user_created_handler, "Async")


def test_nats_notification_sent_contract(pact: Pact) -> None:
    """Contract: notification consumers expect notification.sent events.

    WHY: The notification worker subscribes to notification.sent to persist
    delivery receipts.  A missing field here silently loses delivery data.
    """
    (
        pact.upon_receiving("a notification.sent event", "Async")
        .with_body(
            {
                "notification_id": match.like("notif-uuid-001"),
                "user_id": match.like("user-uuid-001"),
                "notification_type": match.like("push"),
            },
            "application/json",
        )
        .with_metadata({"nats_subject": "notification.sent"})
    )
    pact.verify(_nats_notification_sent_handler, "Async")


def test_nats_files_process_task_contract(pact: Pact) -> None:
    """Contract: file-processor expects files.process task envelope on JetStream.

    WHY: W140 SW1 — file-processor subscribes to the FILES_PROCESS stream.
    The task envelope must carry 'id' and 'name' for correct routing.
    """
    (
        pact.upon_receiving("a files.process task envelope", "Async")
        .with_body(
            {
                "id": match.like("task-uuid-001"),
                "name": match.like("process_uploaded_file"),
                "args": match.like([]),
                "kwargs": match.like({"file_id": "file-uuid-001"}),
                "trace_context": match.like({}),
            },
            "application/json",
        )
        .with_metadata({"nats_subject": "files.process"})
    )
    pact.verify(_nats_files_process_handler, "Async")


def test_nats_generic_task_envelope_contract(pact: Pact) -> None:
    """Contract: all NATS task messages must conform to the _NatsTaskPayload schema.

    WHY: The worker uses _NatsTaskPayload to deserialize ALL task messages.
    This contract ensures that any producer (service, CLI, test) that publishes
    to 'tasks.*' uses the same envelope structure.
    """
    (
        pact.upon_receiving("a generic NATS task envelope", "Async")
        .with_body(
            {
                "id": match.like("task-uuid-999"),
                "name": match.like("email.send_welcome"),
                "args": match.like(["user@university.test"]),
                "kwargs": match.like({}),
                "trace_context": match.like({}),
            },
            "application/json",
        )
        .with_metadata({"nats_subject": "tasks.email.send_welcome"})
    )
    pact.verify(_nats_task_envelope_handler, "Async")
