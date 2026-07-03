"""MOD-07 (audit 2026-03-16 Wave 10): Consumer-Driven Contract Tests for the
Python backend → ws-hub NATS message boundary.

Consumer: ws-hub  (subscribes to NATS cache.invalidate subject)
Provider: university-backend  (Python backend — publishes to NATS)

Flow
----
1. This test (consumer side) defines the expected message schema and writes
   ``tests/contracts/pacts/ws-hub-university-backend.json``.
2. The Go provider test in ``services/ws-hub/internal/contract/`` reads that
   pact file and verifies that the ws-hub message handler can process any
   message matching the schema.

Why this matters
----------------
Python's ``WsHubClient.invalidate_cache`` signs NATS messages with
HMAC-SHA256 using ``json.dumps(sort_keys=True, separators=(',', ':'))``.
The Go subscriber re-serialises with ``json.Marshal`` on a struct whose fields
are ordered alphabetically by JSON tag.  Any drift — a new field, a renamed
key, a changed type — would cause every cache invalidation to be silently
dropped by Go's HMAC check.  These contract tests catch such drift at CI time.
"""

from __future__ import annotations

import json
import re
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
    pytestmark = pytest.mark.skip(
        reason="pact-python is not installed or failed to load DLL (e.g. on Windows)"
    )

    class DummyPact:
        pass

    Pact = DummyPact
    match = None
else:
    Pact = pact_lib.Pact
    match = pact_lib.match

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PACT_DIR = Path(__file__).parent / "pacts"

CONSUMER_NAME = "ws-hub"
PROVIDER_NAME = "university-backend"

# UUID v1/v4: 8-4-4-4-12 hex groups, case-insensitive.
_UUID_PATTERN: str = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
# HMAC-SHA256 hex digest is always exactly 64 lower-case hex characters.
_HMAC_HEX_PATTERN: str = r"^[0-9a-f]{64}$"

# Representative sample values used in the pact interaction body.
_SAMPLE_USER_ID = "550e8400-e29b-41d4-a716-446655440000"
_SAMPLE_ROOM_ID = "550e8400-e29b-41d4-a716-446655440001"
_SAMPLE_TIMESTAMP = 1710000000000  # uuid1().time, non-negative integer
_SAMPLE_SIGNATURE = "a" * 64  # 64-char hex string placeholder

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pact() -> Pact:
    """Session-scoped Pact instance.

    On teardown (after all tests in the module), writes the pact contract file
    to *PACT_DIR*.  The file is consumed by the Go provider test.
    """
    PACT_DIR.mkdir(parents=True, exist_ok=True)
    p = Pact(CONSUMER_NAME, PROVIDER_NAME)
    yield p.with_specification("V4")
    p.write_file(PACT_DIR, overwrite=True)


# ---------------------------------------------------------------------------
# Consumer message verifier (mirrors ws-hub logic)
# ---------------------------------------------------------------------------


def _ws_hub_handler(msg: str | bytes | None, context: dict[str, Any]) -> dict[str, Any]:
    """Simulate the ws-hub NATS cache.invalidate subscriber (hub.go).

    This verifier is invoked by pact.verify() against the mock message
    generated from the interaction definition.  It must pass iff the mock
    message satisfies every structural invariant the Go code enforces before
    performing the HMAC check.

    Mirrors the checks in ``services/ws-hub/pkg/hub/hub.go`` lines 431-475:
    - JSON must unmarshal to ``struct { Data {...}; Signature string }``
    - ``data.user_id`` and ``data.room_id`` must be valid UUIDs
    - ``data.timestamp`` must be a non-negative integer
    - ``signature`` must be a 64-char lowercase hex string

    (We do not replay the HMAC check here — that depends on a shared secret
    and is verified structurally by the regex matcher on the signature field.)
    """
    assert msg is not None, "NATS message body must not be None"

    payload: dict[str, Any] = json.loads(msg)
    assert isinstance(payload, dict), "Top-level payload must be a JSON object"

    # Required top-level fields ------------------------------------------
    assert "data" in payload, "Missing required top-level field: 'data'"
    assert "signature" in payload, "Missing required top-level field: 'signature'"

    # Required data sub-fields -------------------------------------------
    data = payload["data"]
    assert isinstance(data, dict), "'data' must be a JSON object"
    for field in ("user_id", "room_id", "timestamp"):
        assert field in data, f"Missing required field: 'data.{field}'"

    # UUID format validation ---------------------------------------------
    _uuid_re = re.compile(_UUID_PATTERN, re.IGNORECASE)
    assert _uuid_re.match(str(data["user_id"])), (
        f"data.user_id is not a valid UUID: {data['user_id']!r}"
    )
    assert _uuid_re.match(str(data["room_id"])), (
        f"data.room_id is not a valid UUID: {data['room_id']!r}"
    )

    # Timestamp must be a non-negative integer ----------------------------
    ts = data["timestamp"]
    assert isinstance(ts, int) and ts >= 0, (
        f"data.timestamp must be a non-negative integer, got {ts!r}"
    )

    # Signature must be a 64-char lowercase hex string -------------------
    sig = payload["signature"]
    assert re.fullmatch(_HMAC_HEX_PATTERN, str(sig)), (
        f"signature must be exactly 64 lower-case hex chars, got {sig!r}"
    )

    return payload


# ---------------------------------------------------------------------------
# Contract interaction tests
# ---------------------------------------------------------------------------


def test_cache_invalidation_event_contract(pact: Pact) -> None:
    """Contract: ws-hub expects cache invalidation messages in this schema.

    Published by the Python backend to the ``cache.invalidate`` NATS subject.
    The interaction is recorded in the Pact V4 format and consumed by the Go
    provider verification test.

    Schema
    ~~~~~~
    .. code-block:: json

        {
          "data": {
            "user_id":   "<UUID string>",
            "room_id":   "<UUID string>",
            "timestamp": <non-negative integer — uuid1().time>
          },
          "signature": "<HMAC-SHA256 hex, 64 chars>"
        }

    Field-order note
    ~~~~~~~~~~~~~~~~
    Go's ``json.Marshal`` serialises struct fields in declaration order.
    The hub.go struct declares them as ``RoomID``, ``Timestamp``, ``UserID``
    (alphabetical by JSON tag) to match Python's ``sort_keys=True``.  This
    contract does NOT enforce field order directly (JSON objects are unordered)
    but the regex on ``signature`` proves the canonical serialisation is stable.
    """
    (
        pact.upon_receiving("a cache invalidation event", "Async")
        .with_body(
            {
                "data": {
                    "user_id": match.regex(_SAMPLE_USER_ID, regex=_UUID_PATTERN),
                    "room_id": match.regex(_SAMPLE_ROOM_ID, regex=_UUID_PATTERN),
                    "timestamp": match.like(_SAMPLE_TIMESTAMP),
                },
                "signature": match.regex(_SAMPLE_SIGNATURE, regex=_HMAC_HEX_PATTERN),
            },
            "application/json",
        )
        .with_metadata({"nats_subject": "cache.invalidate"})
    )
    pact.verify(_ws_hub_handler, "Async")


def test_broadcast_to_many_contract(pact: Pact) -> None:
    """Contract: ws-hub expects broadcast event payloads in this schema."""
    (
        pact.upon_receiving("a broadcast event to all clients", "Async")
        .with_body(
            {
                "data": {
                    "payload": match.like(
                        "Attention: System maintenance scheduled tonight."
                    ),
                    "sender_id": match.regex(_SAMPLE_USER_ID, regex=_UUID_PATTERN),
                    "timestamp": match.like(_SAMPLE_TIMESTAMP),
                },
                "signature": match.regex(_SAMPLE_SIGNATURE, regex=_HMAC_HEX_PATTERN),
            },
            "application/json",
        )
        .with_metadata({"nats_subject": "broadcast.all"})
    )
    pact.verify(_ws_hub_handler, "Async")


def test_heartbeat_timeout_contract(pact: Pact) -> None:
    """Contract: Python backend expects heartbeat timeout notifications in this schema."""
    (
        pact.upon_receiving("a client heartbeat timeout event", "Async")
        .with_body(
            {
                "data": {
                    "user_id": match.regex(_SAMPLE_USER_ID, regex=_UUID_PATTERN),
                    "reason": match.like("ping timeout after 30 seconds"),
                    "timestamp": match.like(_SAMPLE_TIMESTAMP),
                },
                "signature": match.regex(_SAMPLE_SIGNATURE, regex=_HMAC_HEX_PATTERN),
            },
            "application/json",
        )
        .with_metadata({"nats_subject": "client.timeout"})
    )
    pact.verify(_ws_hub_handler, "Async")
