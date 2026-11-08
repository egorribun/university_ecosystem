"""Unit tests for the broadcast-to-chat → ws-hub NATS mirror.

ConnectionManager.broadcast_to_chat() must, after its in-process fan-out,
ALSO publish the frame to NATS `chat.{chat_id}` (wrapped as the ws-hub
`{type, room, payload}` envelope) so browser clients — connected to ws-hub,
NOT the in-process manager — receive it live.

Contracts:
  1. The mirror fires with the correct subject + envelope shape, independent
     of in-process participants (the browser is on ws-hub, not in-process).
  2. A raising publish_core (NATS infra failure) is swallowed — the in-process
     return value is unaffected (best-effort; browser self-heals via refetch).
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import orjson
import pytest

from app.api.ws.connection_manager import ConnectionManager
from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[1]
_HUB_CANONICAL_UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")


@pytest.mark.asyncio
async def test_broadcast_to_chat_mirrors_frame_to_nats() -> None:
    """The frame is mirrored to chat.{id} as a {type, room, payload} envelope."""
    cm = ConnectionManager()
    chat_id = uuid.uuid4()
    frame = {
        "type": "new_message",
        "chat_id": str(chat_id),
        "message": {"id": str(uuid.uuid4()), "content": "hi"},
    }

    with (
        patch.object(cm, "_get_chat_participants", new=AsyncMock(return_value=[])),
        patch("app.core.nats_broker.broker.publish_core", new=AsyncMock()) as mock_pub,
    ):
        sent = await cm.broadcast_to_chat(chat_id, frame)

    assert sent == 0  # no in-process connections — mirror still fires
    mock_pub.assert_awaited_once()
    call = mock_pub.call_args
    assert call.args[0] == f"chat.{chat_id}"
    envelope = call.args[1]
    assert envelope["type"] == "new_message"
    assert envelope["room"] == str(chat_id)
    assert envelope["payload"] is frame  # the flat frame is the payload


@pytest.mark.asyncio
async def test_broadcast_to_chat_publishes_the_roster_as_hub_audience() -> None:
    """ws-hub drops the event body without an exact, canonical audience."""
    cm = ConnectionManager()
    chat_id = uuid.uuid4()
    sender = uuid.uuid4()
    receiver = uuid.uuid4()

    with (
        patch.object(
            cm,
            "_get_chat_participants",
            new=AsyncMock(return_value=[sender, receiver, receiver]),
        ),
        patch.object(cm, "send_to_user", new=AsyncMock(return_value=0)),
        patch("app.core.nats_broker.broker.publish_core", new=AsyncMock()) as mock_pub,
    ):
        await cm.broadcast_to_chat(chat_id, {"type": "read"}, exclude_user_id=sender)

    wire = orjson.loads(orjson.dumps(mock_pub.call_args.args[1], default=str))
    audience = wire["audience"]
    # The excluded sender stays listed so their other sessions receive the frame.
    assert audience == sorted({str(sender), str(receiver)})
    # decodeChatAudience rejects duplicates and anything but lower-case UUIDs.
    assert all(_HUB_CANONICAL_UUID.fullmatch(member) for member in audience)


def test_group_size_bound_fits_the_hub_audience_limit() -> None:
    """A larger roster would be rejected by ws-hub as a malformed audience."""
    source = (ROOT / "services/ws-hub/pkg/hub/audience.go").read_text(encoding="utf-8")
    match = re.search(r"^const maxChatAudienceMembers = (\d+)$", source, re.MULTILINE)
    assert match is not None
    assert Settings.model_fields["chat_group_max_members"].default <= int(match[1])


@pytest.mark.asyncio
async def test_broadcast_to_chat_mirror_failure_does_not_break_return() -> None:
    """A raising publish_core must not propagate — the return value is intact."""
    cm = ConnectionManager()
    chat_id = uuid.uuid4()
    frame = {
        "type": "read",
        "chat_id": str(chat_id),
        "user_id": str(uuid.uuid4()),
        "read_at": None,
    }

    with (
        patch.object(cm, "_get_chat_participants", new=AsyncMock(return_value=[])),
        patch(
            "app.core.nats_broker.broker.publish_core",
            new=AsyncMock(side_effect=ConnectionError("nats down")),
        ),
    ):
        # Must NOT raise — the in-process delivery + refetch fallback depend
        # on the mirror being best-effort.
        sent = await cm.broadcast_to_chat(chat_id, frame)

    assert sent == 0
