"""Produce real signed cache-invalidation wire messages for the Go hub test.

The shared artifact contains the bytes passed to JetStream by the backend's
actual WsHubClient and NatsTaskBroker. The Go contract job feeds those bytes to
its production cache-invalidation handler, including a tampered-message control.
The transport itself is captured in memory; this is not a live NATS test.
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
from pathlib import Path
from typing import Any

USER_ID = "11111111-1111-1111-1111-111111111111"
ROOM_ID = "22222222-2222-2222-2222-222222222222"
FIXTURE_NAME = "ws-hub-cache-invalidation.json"


class CapturedJetStream:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def publish(
        self, subject: str, data: bytes, *, headers: dict[str, str]
    ) -> None:
        self.events.append(
            {"subject": subject, "wire": data.decode("utf-8"), "headers": headers}
        )


def test_cache_invalidation_producer_writes_wire_fixture(pact_output_dir: Path) -> None:
    """Capture the production publisher and broker, not a hand-built message."""
    from app.core.nats_broker import NatsTaskBroker
    from app.services.ws_hub_client import WsHubClient

    # Per-run test-only key; it is shared only with this generated fixture and
    # never used by a running service or printed in test output.
    test_hmac_key = secrets.token_urlsafe(32)

    async def produce() -> list[dict[str, Any]]:
        jetstream = CapturedJetStream()
        broker = NatsTaskBroker()
        broker._js = jetstream
        client = WsHubClient.__new__(WsHubClient)
        client._broker = broker
        client._secret = test_hmac_key
        await client.invalidate_cache(USER_ID, ROOM_ID, event_id="contract-room")
        await client.invalidate_cache(USER_ID, "", event_id="contract-user-wide")
        await client.invalidate_cache(
            USER_ID, ROOM_ID, evict_room=True, event_id="contract-eviction"
        )
        return jetstream.events

    events = asyncio.run(produce())
    assert len(events) == 3
    # Room revocations (evict_room) travel on their own subject; the ws-hub
    # consumer for cache.invalidate never sees them.
    assert [event["subject"] for event in events] == [
        "cache.invalidate",
        "cache.invalidate",
        "cache.revoke",
    ]
    assert [event["headers"]["Nats-Msg-Id"] for event in events] == [
        "contract-room",
        "contract-user-wide",
        "contract-eviction",
    ]
    destination = pact_output_dir / FIXTURE_NAME
    fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        json.dump({"test_hmac_key": test_hmac_key, "events": events}, output, indent=2)
        output.write("\n")
    if os.name == "posix":
        assert destination.stat().st_mode & 0o077 == 0
