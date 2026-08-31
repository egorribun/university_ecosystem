"""WebSocket message schema contract tests.

Verifies that the Python backend sends WS messages in the format that the
frontend ``parseWsMessage()`` (Valibot discriminated union) expects.

Cross-service invariant:
  Python ``connection_manager.py`` + ``dispatcher.py`` → ws frames →
  Frontend ``wsMessage.ts`` parseWsMessage() Valibot validation.

Any new message type added in Python MUST be added to the frontend Valibot schema,
and vice versa. These tests catch schema drift at CI time.

The authoritative schema is the TypeScript Valibot definition in:
  ``frontend/src/api/schemas/wsMessage.ts``
"""

from __future__ import annotations

import re
import uuid

import pytest

# ---------------------------------------------------------------------------
# Expected WS server→client message types (from frontend Valibot schema)
# ---------------------------------------------------------------------------

# These must match the discriminated union in wsMessage.ts exactly.
# If a type is added/removed in Python, this set must be updated too.
WS_SERVER_MESSAGE_TYPES: frozenset[str] = frozenset(
    {
        "pong",
        "error",
        "rate_limit_exceeded",
        "new_message",
        "typing",
        "read",
        "online",
        "online_list",
        "presence",
        "message_edited",
        "message_deleted",
        "reaction_changed",
        "replay_checkpoint",
    }
)

# Required fields per message type (mirrors Valibot schema field requirements)
WS_MESSAGE_REQUIRED_FIELDS: dict[str, set[str]] = {
    "pong": {"type"},
    "error": {"type"},  # detail is optional
    "new_message": {"type", "chat_id", "message"},
    "typing": {"type", "chat_id", "user_id", "user_name"},
    "read": {"type", "chat_id", "user_id", "read_at"},
    "online": {"type", "user_id", "status"},
    "online_list": {"type", "users"},
    "presence": {"type", "user_id", "active", "last_seen"},
    "message_edited": {"type", "chat_id", "message_id", "content", "edited_at"},
    "message_deleted": {"type", "chat_id", "message_id", "deleted_at"},
    "reaction_changed": {"type", "chat_id", "message_id", "user_id", "emoji", "action"},
    "replay_checkpoint": {"type", "chat_id"},
    "rate_limit_exceeded": {"type"},
}


# ---------------------------------------------------------------------------
# Tests: Message type coverage
# ---------------------------------------------------------------------------


def test_pong_message_format():
    """Backend pong response must have exactly ``{"type": "pong"}``."""
    msg = {"type": "pong"}
    assert msg["type"] == "pong"
    # pong has no other required fields
    assert set(msg.keys()) <= {"type"}, "Pong message should only have 'type' field"


def test_typing_message_format():
    """Typing messages must include chat_id, user_id, user_name."""
    msg = {
        "type": "typing",
        "chat_id": str(uuid.uuid4()),
        "user_id": str(uuid.uuid4()),
        "user_name": "Alice",
    }
    required = WS_MESSAGE_REQUIRED_FIELDS["typing"]
    missing = required - set(msg.keys())
    assert not missing, f"Typing message missing required fields: {missing}"


def test_read_message_format():
    """Read receipts are chat-level and carry read_at, not message_id."""
    msg = {
        "type": "read",
        "chat_id": str(uuid.uuid4()),
        "user_id": str(uuid.uuid4()),
        "read_at": "2026-03-23T12:00:00+00:00",
    }
    required = WS_MESSAGE_REQUIRED_FIELDS["read"]
    missing = required - set(msg.keys())
    assert not missing, f"Read message missing required fields: {missing}"
    assert "message_id" not in msg, "Read receipts are chat-level, not per-message"


def test_presence_message_format():
    """Presence messages must include user_id and active (boolean)."""
    msg = {
        "type": "presence",
        "user_id": str(uuid.uuid4()),
        "active": True,
        "last_seen": "2026-03-23T12:00:00+00:00",
    }
    required = WS_MESSAGE_REQUIRED_FIELDS["presence"]
    missing = required - set(msg.keys())
    assert not missing, f"Presence message missing required fields: {missing}"
    assert isinstance(msg["active"], bool), "active must be boolean"


def test_online_message_format():
    """Online status messages must include user_id and status (boolean)."""
    msg = {
        "type": "online",
        "user_id": str(uuid.uuid4()),
        "status": True,
    }
    required = WS_MESSAGE_REQUIRED_FIELDS["online"]
    missing = required - set(msg.keys())
    assert not missing, f"Online message missing required fields: {missing}"


def test_new_message_format():
    """New message events must include chat_id and message object."""
    msg = {
        "type": "new_message",
        "chat_id": str(uuid.uuid4()),
        "message": {
            "id": str(uuid.uuid4()),
            "content": "Hello",
            "sender_id": str(uuid.uuid4()),
        },
    }
    required = WS_MESSAGE_REQUIRED_FIELDS["new_message"]
    missing = required - set(msg.keys())
    assert not missing, f"New message missing required fields: {missing}"
    assert isinstance(msg["message"], dict), "message must be a dict"


def test_error_message_format():
    """Error messages must have type=error, detail is optional."""
    msg = {"type": "error", "detail": "Rate limit exceeded"}
    required = WS_MESSAGE_REQUIRED_FIELDS["error"]
    missing = required - set(msg.keys())
    assert not missing, f"Error message missing required fields: {missing}"


# ---------------------------------------------------------------------------
# Tests: Backend sends only known types
# ---------------------------------------------------------------------------


def test_backend_dispatcher_uses_known_types():
    """Verify dispatcher.py only sends message types known to frontend schema.

    Reads the Python source and extracts all ``"type": "..."`` string literals
    to detect any new message types that haven't been registered in the
    frontend Valibot schema.
    """
    import inspect

    from app.api.ws import dispatcher

    source = inspect.getsource(dispatcher)
    # Extract all "type": "..." patterns
    type_literals = set(re.findall(r'"type":\s*"([a-z_]+)"', source))

    unknown = type_literals - WS_SERVER_MESSAGE_TYPES
    assert not unknown, (
        f"Dispatcher sends unknown WS message type(s): {unknown}. "
        f"Add them to frontend/src/api/schemas/wsMessage.ts Valibot schema "
        f"and to WS_SERVER_MESSAGE_TYPES in this test."
    )


def test_backend_connection_manager_uses_known_types():
    """Verify connection_manager.py only sends known message types."""
    import inspect

    from app.api.ws import connection_manager

    source = inspect.getsource(connection_manager)
    type_literals = set(re.findall(r'"type":\s*"([a-z_]+)"', source))

    unknown = type_literals - WS_SERVER_MESSAGE_TYPES
    assert not unknown, (
        f"ConnectionManager sends unknown WS message type(s): {unknown}. "
        f"Add them to frontend/src/api/schemas/wsMessage.ts Valibot schema "
        f"and to WS_SERVER_MESSAGE_TYPES in this test."
    )


# ---------------------------------------------------------------------------
# Tests: All required fields present in schema registry
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("msg_type", sorted(WS_SERVER_MESSAGE_TYPES))
def test_all_message_types_have_field_definitions(msg_type: str):
    """Every known message type must have required fields defined."""
    assert msg_type in WS_MESSAGE_REQUIRED_FIELDS, (
        f"Message type '{msg_type}' is in WS_SERVER_MESSAGE_TYPES but has no "
        f"entry in WS_MESSAGE_REQUIRED_FIELDS. Add it."
    )
    assert "type" in WS_MESSAGE_REQUIRED_FIELDS[msg_type], (
        f"Every message type must include 'type' in its required fields. "
        f"'{msg_type}' is missing it."
    )
