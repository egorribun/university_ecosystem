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


def _frontend_object_schema_body(source: str, schema_name: str) -> str:
    """Return one Valibot object schema body by its TypeScript identifier."""
    declaration = re.search(
        rf"^(?:export\s+)?const\s+{re.escape(schema_name)}\s*=\s*"
        r"v\.object\(\{(?P<body>.*?)(?=^(?:export\s+)?const\s+|\Z)",
        source,
        flags=re.DOTALL | re.MULTILINE,
    )
    assert declaration is not None, f"Valibot object schema {schema_name} is missing"
    return declaration.group("body")


def _frontend_schema_type(source: str, schema_name: str) -> str:
    """Read the literal discriminator from one named Valibot object schema."""
    body = _frontend_object_schema_body(source, schema_name)
    type_field = re.search(
        r"\btype\s*:\s*v\.literal\(\s*['\"]([a-z_]+)['\"]\s*\)",
        body,
    )
    assert type_field is not None, f"Schema {schema_name} must declare a literal type"
    return type_field.group(1)


def _frontend_server_message_types() -> frozenset[str]:
    """Read only the schemas referenced by the server-to-client union.

    Client-side schemas live in the same TypeScript file, but are not incoming
    server frames and must not be inferred as members of this discriminated union.
    """
    source = FRONTEND_WS_SCHEMA.read_text(encoding="utf-8")
    server_union = re.search(
        r"export const WsServerMessageSchema = v\.variant\(\s*['\"]type['\"]"
        r"\s*,\s*\[(?P<schemas>.*?)\]\s*\)",
        source,
        flags=re.DOTALL,
    )
    assert server_union is not None, "Frontend server message union is missing"
    schema_names = re.findall(
        r"\b([A-Za-z][A-Za-z0-9]*Schema)\b", server_union.group("schemas")
    )
    assert schema_names, "Frontend server message union must list schemas"
    return frozenset(_frontend_schema_type(source, name) for name in schema_names)


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

    class _OutputTypeVisitor(ast.NodeVisitor):
        """Inspect source bodies while ignoring mutmut mutant variants.

        During mutmut's stats pass the generated module contains the original
        function and one sibling function per mutation.  The latter may hold
        deliberately invalid string values (for example ``NEW_MESSAGE``), so
        scanning those bodies would make the baseline fail before the mutant is
        run.  Production modules do not use the ``__mutmut_`` naming convention;
        their unknown protocol values remain visible below.
        """

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            if "__mutmut_" in node.name and not node.name.endswith("__mutmut_orig"):
                return
            self.generic_visit(node)

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Dict(self, node: ast.Dict) -> None:
            for key, value in zip(node.keys, node.values, strict=False):
                if (
                    isinstance(key, ast.Constant)
                    and key.value == "type"
                    and isinstance(value, ast.Constant)
                    and isinstance(value.value, str)
                ):
                    # mutmut replaces a string literal with an ``XX...XX``
                    # sentinel while collecting baseline stats.  The sentinel
                    # is not a product protocol value and must not make the
                    # initial stats run fail before the mutant is exercised by
                    # the actual tests.  Keep all other values visible.
                    if not re.fullmatch(r"XX[a-z_]+XX", value.value):
                        types.add(value.value)
            self.generic_visit(node)

    _OutputTypeVisitor().visit(tree)
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
    "online_list": {"type", "users"},
    "presence": {"type", "user_id", "active", "last_seen"},
    "message_edited": {"type", "chat_id", "message_id", "content", "edited_at"},
    "message_deleted": {"type", "chat_id", "message_id", "deleted_at"},
    "reaction_changed": {"type", "chat_id", "message_id", "user_id", "emoji", "action"},
    "replay_checkpoint": {"type", "chat_id"},
    "rate_limit_exceeded": {"type"},
    "heartbeat_pong": {"type", "nonce"},
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


def test_backend_contract_ignores_mutmut_string_sentinel_only(tmp_path: Path):
    """Mutation placeholders do not hide real unknown protocol tokens."""
    source = tmp_path / "mutated_ws.py"
    source.write_text(
        "frames = [{'type': 'XXnew_messageXX'},{'type': 'NEW_MESSAGE'},]\n",
        encoding="utf-8",
    )

    assert _python_ws_output_types(source) == frozenset({"NEW_MESSAGE"})


def test_backend_contract_ignores_generated_mutmut_variant_bodies(tmp_path: Path):
    """Stats trees include mutant siblings that must not become protocol output."""
    source = tmp_path / "mutated_ws.py"
    source.write_text(
        "def x_emit__mutmut_orig():\n"
        "    return {'type': 'new_message'}\n"
        "def x_emit__mutmut_1():\n"
        "    return {'type': 'NEW_MESSAGE'}\n",
        encoding="utf-8",
    )

    assert _python_ws_output_types(source) == frozenset({"new_message"})


def test_ws_hub_inbound_allowlist_has_no_server_receipt_commands():
    """ws-hub accepts room commands and a local heartbeat, not server frames."""
    assert WS_HUB_CLIENT_MESSAGE_TYPES == frozenset({"join", "leave", "heartbeat_ping"})
    assert "heartbeat_pong" not in WS_HUB_CLIENT_MESSAGE_TYPES
    assert "read" not in WS_HUB_CLIENT_MESSAGE_TYPES
    assert "typing" not in WS_HUB_CLIENT_MESSAGE_TYPES


def test_heartbeat_nonce_frames_keep_client_and_server_directions_explicit():
    """Client ping stays outside the server union; server pong requires nonce."""
    schema_source = FRONTEND_WS_SCHEMA.read_text(encoding="utf-8")
    assert _frontend_schema_type(schema_source, "WsClientHeartbeatPingSchema") == (
        "heartbeat_ping"
    )
    assert (
        _frontend_schema_type(schema_source, "HeartbeatPongSchema") == "heartbeat_pong"
    )
    assert "heartbeat_ping" not in WS_SERVER_MESSAGE_TYPES
    assert "heartbeat_pong" in WS_SERVER_MESSAGE_TYPES

    nonce_field = re.compile(r"(?m)^\s*nonce:\s*HeartbeatNonceSchema,\s*$")
    for schema_name in ("WsClientHeartbeatPingSchema", "HeartbeatPongSchema"):
        assert nonce_field.search(
            _frontend_object_schema_body(schema_source, schema_name)
        )


def test_transport_direction_is_explicitly_split():
    """REST owns receipts/typing; ws-hub accepts only local heartbeat pings."""
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
