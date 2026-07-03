"""Contract tests for NATS messages exchanged between backend and ws-hub."""

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
