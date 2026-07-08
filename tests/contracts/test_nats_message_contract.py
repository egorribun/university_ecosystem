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


def _nats_chat_message_sent_handler(
    msg: str | bytes | None, context: dict[str, Any]
) -> dict[str, Any]:
    assert msg is not None
    payload = json.loads(msg)
    assert "chat_id" in payload
    assert "message_id" in payload
    assert "content_preview" in payload
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


def _nats_router_handler(
    msg: str | bytes | None, context: dict[str, Any]
) -> dict[str, Any]:
    assert msg is not None
    payload = json.loads(msg)
    if "participant_id" in payload:
        return _nats_chat_deleted_handler(msg, context)
    elif "email" in payload:
        return _nats_user_created_handler(msg, context)
    elif "notification_type" in payload:
        return _nats_notification_sent_handler(msg, context)
    elif "args" in payload:
        # Both files.process and tasks.* have args/kwargs
        if "name" in payload and payload["name"] == "process_uploaded_file":
            return _nats_files_process_handler(msg, context)
        return _nats_task_envelope_handler(msg, context)
    elif "chat_id" in payload:
        if "content_preview" in payload:
            return _nats_chat_message_sent_handler(msg, context)
        return _nats_chat_message_handler(msg, context)
    else:
        raise ValueError(f"Unknown payload format: {payload}")


# ---------------------------------------------------------------------------
# Contract interaction tests
# ---------------------------------------------------------------------------


def test_nats_message_contracts(pact: Pact) -> None:
    """Contract: ws-hub and university-backend NATS messages schemas."""
    # 1. chat.direct
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

    # 2. chat.message_sent
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

    # 3. chat.deleted
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

    # 4. user.created
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

    # 5. notification.sent
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

    # 6. files.process
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

    # 7. tasks.*
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

    # Verify all of them against our routing handler
    pact.verify(_nats_router_handler, "Async")
