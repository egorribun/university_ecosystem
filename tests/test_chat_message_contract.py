"""Focused contract tests for the messenger message-size boundary.

These tests intentionally exercise the same limit at each backend boundary before
the implementation is changed.  A failure here is the RED proof for
MSG-CONTRACT-01; the generated OpenAPI check is run after the production change.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

import app.core.config.storage as storage_config
from app.api.websocket import _is_websocket_payload_within_limits
from app.core.config.storage import StorageSettings
from app.models.chat import Message
from app.schemas.chat import MessageCreate, MessageResponse

EXPECTED_LIMIT = 32_768


def _response(content: str) -> MessageResponse:
    now = datetime.now(UTC)
    return MessageResponse(
        id=uuid4(),
        chat_id=uuid4(),
        sender_id=uuid4(),
        content=content,
        created_at=now,
        read_status=False,
    )


def test_message_limit_is_one_canonical_backend_value() -> None:
    settings = StorageSettings(_allow_missing=True)

    assert getattr(storage_config, "CHAT_MAX_MESSAGE_LENGTH", None) == EXPECTED_LIMIT
    assert settings.chat_max_message_length == EXPECTED_LIMIT
    assert Message.__table__.c.content.type.length == EXPECTED_LIMIT


@pytest.mark.parametrize("size", [EXPECTED_LIMIT - 1, EXPECTED_LIMIT])
def test_message_create_accepts_limit_minus_one_and_limit(size: int) -> None:
    assert len(MessageCreate(content="x" * size).content) == size


def test_message_create_rejects_limit_plus_one_without_truncation() -> None:
    with pytest.raises(ValidationError):
        MessageCreate(content="x" * (EXPECTED_LIMIT + 1))


def test_message_create_uses_unicode_code_points_for_the_limit() -> None:
    content = "😀" * EXPECTED_LIMIT

    assert len(content) == EXPECTED_LIMIT
    assert MessageCreate(content=content).content == content

    with pytest.raises(ValidationError):
        MessageCreate(content=content + "😀")


def test_message_response_accepts_legacy_rows_through_current_limit() -> None:
    # Rows written under the old 2,000-character DTO must remain readable after
    # the contract is widened; response validation must not reject them.
    legacy = _response("l" * 2_001)
    current = _response("c" * EXPECTED_LIMIT)

    assert len(legacy.content) == 2_001
    assert len(current.content) == EXPECTED_LIMIT


def test_message_response_rejects_only_above_canonical_limit() -> None:
    with pytest.raises(ValidationError):
        _response("x" * (EXPECTED_LIMIT + 1))


def test_frontend_message_limit_is_generated_from_backend_contract() -> None:
    """The browser schema must consume the backend-owned generated value."""
    generated = (
        Path(__file__).parents[1]
        / "frontend"
        / "src"
        / "api"
        / "schemas"
        / "messageLimits.ts"
    )
    assert generated.exists(), "run scripts/generate_message_contract.py"
    source = generated.read_text(encoding="utf-8")
    assert f"CHAT_MESSAGE_MAX_LENGTH = {EXPECTED_LIMIT}" in source


def test_openapi_message_content_limits_cover_send_edit_and_response() -> None:
    """All public message surfaces expose the same inclusive content limit."""
    from app.main import app

    spec = app.openapi()
    components = spec["components"]["schemas"]

    send_ref = spec["paths"]["/api/v1/chats/{chat_id}/messages"]["post"]["requestBody"][
        "content"
    ]["multipart/form-data"]["schema"]["$ref"]
    edit_ref = spec["paths"]["/api/v1/chats/{chat_id}/messages/{message_id}"]["patch"][
        "requestBody"
    ]["content"]["application/x-www-form-urlencoded"]["schema"]["$ref"]

    send_schema = components[send_ref.rsplit("/", 1)[-1]]
    edit_schema = components[edit_ref.rsplit("/", 1)[-1]]
    response_schema = components["MessageResponse"]

    send_content = send_schema["properties"]["content"]
    edit_content = edit_schema["properties"]["content"]
    response_content = response_schema["properties"]["content"]

    assert (
        send_content["type"]
        == edit_content["type"]
        == response_content["type"]
        == "string"
    )
    assert send_content["maxLength"] == EXPECTED_LIMIT
    assert edit_content["maxLength"] == EXPECTED_LIMIT
    assert edit_content["minLength"] == 1
    assert response_content["maxLength"] == EXPECTED_LIMIT


@pytest.mark.parametrize(
    ("character", "size", "expected"),
    [
        ("x", EXPECTED_LIMIT - 1, True),
        ("x", EXPECTED_LIMIT, True),
        ("x", EXPECTED_LIMIT + 1, False),
        ("я", EXPECTED_LIMIT, False),
    ],
)
def test_websocket_content_limit_is_independent_from_json_framing(
    character: str, size: int, expected: bool
) -> None:
    """Validate message content by code points, not the enclosing JSON length."""
    import json

    content = character * size
    frame = json.dumps(
        {"type": "message", "payload": {"content": content}},
        ensure_ascii=False,
        separators=(",", ":"),
    )

    assert _is_websocket_payload_within_limits(frame, json.loads(frame)) is expected
    if len(content) == EXPECTED_LIMIT:
        assert (
            len(frame) > EXPECTED_LIMIT
        )  # JSON framing must not consume content slots


def test_websocket_frame_limit_counts_utf8_bytes_for_non_message_commands() -> None:
    """Transport framing follows ws-hub's 60 KiB raw-byte guard."""
    import json

    base = json.dumps({"type": "ping", "padding": ""}, separators=(",", ":"))
    available = 60 * 1024 - len(base.encode("utf-8"))
    at_limit = json.dumps(
        {"type": "ping", "padding": "x" * available}, separators=(",", ":")
    )
    over_limit = json.dumps(
        {"type": "ping", "padding": "x" * (available + 1)}, separators=(",", ":")
    )

    assert len(at_limit.encode("utf-8")) == 60 * 1024
    assert _is_websocket_payload_within_limits(at_limit, json.loads(at_limit)) is True
    assert (
        _is_websocket_payload_within_limits(over_limit, json.loads(over_limit)) is False
    )


def test_websocket_message_content_shapes_are_fail_closed() -> None:
    """All supported message envelope shapes share the same content contract."""
    import json

    at_limit = "x" * EXPECTED_LIMIT
    over_limit = "x" * (EXPECTED_LIMIT + 1)
    frames = [
        {"type": "message", "content": at_limit},
        {"type": "message", "payload": {"content": at_limit}},
        {"type": "message", "payload": {"message": {"content": at_limit}}},
        {"type": "message", "payload": {"text": at_limit}},
        {"type": "message", "payload": {"message": "legacy-text"}},
        {"type": "message", "payload": {"message": {"text": "legacy-text"}}},
        {"type": "message", "payload": "legacy-text"},
    ]
    for data in frames:
        frame = json.dumps(data, separators=(",", ":"))
        assert _is_websocket_payload_within_limits(frame, data) is True

    invalid_content = {"type": "message", "content": 42}
    invalid_frame = json.dumps(invalid_content, separators=(",", ":"))
    assert _is_websocket_payload_within_limits(invalid_frame, invalid_content) is False

    nested_over = {"type": "message", "payload": {"message": {"content": over_limit}}}
    nested_over_frame = json.dumps(nested_over, separators=(",", ":"))
    assert _is_websocket_payload_within_limits(nested_over_frame, nested_over) is False

    assert _is_websocket_payload_within_limits("[]", []) is False


def test_legacy_read_is_scoped_to_python_fallback_not_ws_hub() -> None:
    """REST owns browser receipts; ``read`` remains only direct-backend compatibility."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    dispatcher = (root / "app/api/ws/dispatcher.py").read_text(encoding="utf-8")
    ws_hub = (root / "services/ws-hub/pkg/hub/client.go").read_text(encoding="utf-8")

    assert re.search(r"msg_type\s*==\s*[\"']read[\"']", dispatcher)
    assert re.search(r"allowedMessageTypes.*?\n\}", ws_hub, flags=re.DOTALL)
    allowlist = re.search(
        r"var allowedMessageTypes = map\[string\]bool\{(?P<body>.*?)\n\}",
        ws_hub,
        flags=re.DOTALL,
    )
    assert allowlist is not None
    assert '"read"' not in allowlist.group("body")
