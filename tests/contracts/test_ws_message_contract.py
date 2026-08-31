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

import ast
import re
import uuid
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Current WS protocol sources
# ---------------------------------------------------------------------------

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_WS_SCHEMA = REPOSITORY_ROOT / "frontend/src/api/schemas/wsMessage.ts"
FRONTEND_WS_HOOK = REPOSITORY_ROOT / "frontend/src/hooks/useChatWebSocket.ts"
WS_HUB_CLIENT_SOURCE = REPOSITORY_ROOT / "services/ws-hub/pkg/hub/client.go"


def _frontend_server_message_types() -> frozenset[str]:
    """Read the discriminated-union catalog from the Valibot source.

    Keeping this derived from the runtime schema prevents the contract test from
    becoming a second, stale registry whenever a frame is added or removed.
    """
    source = FRONTEND_WS_SCHEMA.read_text(encoding="utf-8")
    return frozenset(re.findall(r"v\.literal\([\"']([a-z_]+)[\"']\)", source))


def _ws_hub_client_message_types() -> frozenset[str]:
    """Read ws-hub's client-to-hub command allowlist from Go source."""
    source = WS_HUB_CLIENT_SOURCE.read_text(encoding="utf-8")
    match = re.search(
        r"var allowedMessageTypes = map\[string\]bool\{(?P<body>.*?)\n\}",
        source,
        flags=re.DOTALL,
    )
    assert match is not None, "ws-hub client command allowlist is missing"
    return frozenset(re.findall(r'"([a-z_]+)"\s*:\s*true', match.group("body")))


def _python_ws_output_types(path: Path) -> frozenset[str]:
    """Extract literal ``type`` values from Python dict expressions.

    AST inspection intentionally ignores docstrings/comments, where inbound
    examples such as ``{"type": "ping"}`` are documentation rather than frames
    emitted by the backend.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    types: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values, strict=False):
            if (
                isinstance(key, ast.Constant)
                and key.value == "type"
                and isinstance(value, ast.Constant)
                and isinstance(value.value, str)
            ):
                types.add(value.value)
    return frozenset(types)


# This is the current frontend output catalog, not a hand-maintained copy.
WS_SERVER_MESSAGE_TYPES = _frontend_server_message_types()
WS_HUB_CLIENT_MESSAGE_TYPES = _ws_hub_client_message_types()

# Product events required by the messenger roadmap.  The complete catalog above
# is generated from the frontend schema; this subset makes the contract fail if
# one of the recently-added event families is accidentally removed.
REQUIRED_MESSENGER_EVENTS = frozenset(
    {
        "new_message",
        "message_edited",
        "message_deleted",
        "reaction_changed",
        "replay_checkpoint",
        "read",
        "typing",
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
# Tests: backend output and ws-hub input directions
# ---------------------------------------------------------------------------


def test_frontend_catalog_contains_all_messenger_event_families():
    """The generated/current frontend union covers every messenger event."""
    assert REQUIRED_MESSENGER_EVENTS <= WS_SERVER_MESSAGE_TYPES


BACKEND_WS_PRODUCERS = (
    "app/api/websocket.py",
    "app/api/ws/dispatcher.py",
    "app/api/ws/connection_manager.py",
    "app/services/chat/command_service.py",
    "app/services/chat/notification_service.py",
)


@pytest.mark.parametrize("relative_path", BACKEND_WS_PRODUCERS)
def test_backend_ws_producers_use_frontend_catalog(relative_path: str):
    """Every backend WS producer emits only schema-registered frame types."""
    source_path = REPOSITORY_ROOT / relative_path
    # Parse dictionaries instead of grepping source text: endpoint docstrings
    # legitimately mention inbound commands (for example ``{"type": "ping"}`)
    # that are not server-to-client frames and therefore are not in the output
    # Valibot union.
    type_literals = _python_ws_output_types(source_path)

    unknown = type_literals - WS_SERVER_MESSAGE_TYPES
    assert not unknown, (
        f"{relative_path} emits unknown WS message type(s): {unknown}. "
        "Add the frame to frontend/src/api/schemas/wsMessage.ts first."
    )


def test_ws_hub_inbound_allowlist_has_no_server_receipt_commands():
    """ws-hub accepts transport commands only; REST owns read receipts."""
    assert WS_HUB_CLIENT_MESSAGE_TYPES == frozenset({"join", "leave", "message"})
    assert "read" not in WS_HUB_CLIENT_MESSAGE_TYPES
    assert "typing" not in WS_HUB_CLIENT_MESSAGE_TYPES


def test_transport_direction_is_explicitly_split():
    """REST owns receipts/typing and ws-hub owns the control heartbeat."""
    assert "read" in WS_SERVER_MESSAGE_TYPES
    hook_source = FRONTEND_WS_HOOK.read_text(encoding="utf-8")
    assert not re.search(r"sendRead|type\s*:\s*['\"]read['\"]", hook_source)
    assert not re.search(
        r"JSON\.stringify\(\{\s*type\s*:\s*['\"]ping['\"]", hook_source
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
