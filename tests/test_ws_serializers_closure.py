"""Branch closure tests for websocket serializer reply handling."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from app.api.ws.serializers import serialize_message
from app.schemas.chat import ReplyPreview


def test_serialize_message_omits_reply_when_preview_builder_returns_none(monkeypatch):
    message = SimpleNamespace(
        id=uuid4(),
        chat_id=uuid4(),
        sender_id=uuid4(),
        content="body",
        created_at=datetime.now(UTC),
        read_status=False,
        read_at=None,
        edited_at=None,
        deleted_at=None,
        forwarded_from_name=None,
        sender=None,
        attachments=[],
    )
    monkeypatch.setattr(ReplyPreview, "from_message", lambda _message: None)

    result = serialize_message(message, replied=object())

    assert result["reply_to"] is None
