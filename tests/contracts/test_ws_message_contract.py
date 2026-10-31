"""Check backend frame production and the frontend's declared type catalog.

The captured JSON frames can be replayed by a frontend parser test. This Python
suite reads the frontend schema source but does not execute its Valibot parser.
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


@pytest.mark.asyncio
async def test_backend_emitters_capture_real_ws_frames(
    monkeypatch: pytest.MonkeyPatch, pact_output_dir: Path
) -> None:
    """Capture actual backend emitters; DB and socket delivery are test seams.

    The output is JSON-ready for a frontend parser contract. This test alone
    does not execute the TypeScript consumer or a live WebSocket transport.
    """
    import json
    from contextlib import asynccontextmanager
    from datetime import UTC, datetime
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from fastapi.encoders import jsonable_encoder

    import app.api.ws.dispatcher as dispatcher_module
    import app.api.ws.presence as presence_module
    import app.services.chat.command_service as command_module
    import app.services.chat.notification_service as notification_module
    from app.api.ws.connection_manager import ConnectionManager

    user = SimpleNamespace(
        id=uuid.uuid4(),
        profile=SimpleNamespace(full_name="Alice"),
        email="alice@example.org",
    )
    chat_id = uuid.uuid4()
    timestamp = datetime(2030, 1, 2, tzinfo=UTC)
    socket = SimpleNamespace(send_json=AsyncMock())
    manager = SimpleNamespace(
        broadcast_presence=AsyncMock(), broadcast_to_chat=AsyncMock()
    )
    dispatcher = dispatcher_module.MessageDispatcher(manager)

    await dispatcher.dispatch(socket, user, None, {"type": "ping"})
    await dispatcher.dispatch(
        socket, user, None, {"type": "heartbeat_ping", "nonce": "a" * 32}
    )
    await dispatcher.dispatch(
        socket, user, None, {"type": "heartbeat_ping", "nonce": "invalid"}
    )
    pong, heartbeat_pong, error = [
        call.args[0] for call in socket.send_json.await_args_list
    ]
    assert pong == {"type": "pong"}
    assert heartbeat_pong == {"type": "heartbeat_pong", "nonce": "a" * 32}
    assert error["type"] == "error" and error["message"] == "Invalid heartbeat nonce"

    repo = SimpleNamespace(
        check_participant=AsyncMock(return_value=True),
        get_chat_type=AsyncMock(return_value="dm"),
        mark_messages_read=AsyncMock(return_value=(timestamp, 1)),
    )
    session = SimpleNamespace(commit=AsyncMock())

    @asynccontextmanager
    async def db_session():
        yield session

    monkeypatch.setattr(dispatcher_module, "async_session", db_session)
    monkeypatch.setattr(dispatcher_module, "ChatRepository", lambda _: repo)
    await dispatcher.dispatch(
        socket, user, None, {"type": "read", "chat_id": str(chat_id)}
    )
    read_frame = manager.broadcast_to_chat.await_args.args[1]
    assert read_frame["chat_id"] == str(chat_id)
    assert read_frame["user_id"] == str(user.id)
    assert read_frame["read_at"] == timestamp.isoformat()
    assert "message_id" not in read_frame

    typing_manager = SimpleNamespace(broadcast_to_chat=AsyncMock())
    monkeypatch.setattr(command_module, "ws_manager", typing_manager)
    maintenance = command_module.ChatMaintenanceService(
        SimpleNamespace(chats=repo, session=session), None
    )
    await maintenance.broadcast_typing(chat_id, user, "en")
    typing_call = typing_manager.broadcast_to_chat.await_args
    assert typing_call.kwargs["db_session"] is session
    assert typing_call.kwargs["exclude_user_id"] == user.id
    typing_frame = typing_call.args[1]
    assert typing_frame["chat_id"] == str(chat_id)
    assert typing_frame["user_id"] == str(user.id)
    assert typing_frame["user_name"] == "Alice"

    connection_manager = ConnectionManager()
    connection_manager.send_to_user = AsyncMock(return_value=1)
    audience_user = uuid.uuid4()
    monkeypatch.setattr(
        presence_module,
        "_get_presence_audience",
        AsyncMock(return_value=[audience_user]),
    )
    assert (
        await connection_manager.broadcast_presence(
            user.id, True, timestamp, source="ping", publish=False
        )
        == 1
    )
    presence_frame = jsonable_encoder(
        connection_manager.send_to_user.await_args.args[1]
    )
    assert presence_frame["user_id"] == str(user.id)
    assert presence_frame["active"] is True
    assert presence_frame["last_seen"] == timestamp.isoformat()

    message = SimpleNamespace(
        id=uuid.uuid4(),
        chat_id=chat_id,
        sender_id=user.id,
        content="Hello",
        created_at=timestamp,
        read_status=False,
        read_at=None,
        edited_at=None,
        deleted_at=None,
        sender=None,
        attachments=[],
        forwarded_from_name=None,
    )
    notification_manager = SimpleNamespace(broadcast_to_chat=AsyncMock())
    monkeypatch.setattr(notification_module, "ws_manager", notification_manager)
    monkeypatch.setattr(
        notification_module, "build_presence_map", AsyncMock(return_value={})
    )
    notifications = notification_module.ChatNotificationService(object())
    await notifications.notify_new_message(message, [user], user)
    new_message = jsonable_encoder(
        notification_manager.broadcast_to_chat.await_args.args[1]
    )
    assert new_message["chat_id"] == str(chat_id)
    assert new_message["message"]["id"] == str(message.id)
    assert new_message["message"]["sender_id"] == str(user.id)
    assert new_message["message"]["content"] == "Hello"

    frames = [
        pong,
        heartbeat_pong,
        error,
        read_frame,
        typing_frame,
        presence_frame,
        new_message,
    ]
    assert [frame["type"] for frame in frames] == [
        "pong",
        "heartbeat_pong",
        "error",
        "read",
        "typing",
        "presence",
        "new_message",
    ]
    assert {frame["type"] for frame in frames} <= WS_SERVER_MESSAGE_TYPES
    (pact_output_dir / "ws-backend-frames.json").write_text(
        json.dumps(frames, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


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
    """Literal backend frame types must appear in the frontend catalog."""
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
