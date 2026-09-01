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
