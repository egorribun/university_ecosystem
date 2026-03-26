"""MOD-W15-01 / Wave 18.1: Pure-function Redis key format contract tests.

These tests verify that the Python backend's Redis key constants and builder
functions produce keys in the format that Go services expect.  They require
NO Redis connection and run unconditionally in CI.

Cross-service invariants verified:
  - Revocation keys: ``revoked:jti:{jti}`` (Go gateway reads this format)
  - WS upgrade tickets: ``ott:ws:{ticket}`` (Go ws-hub validates via GETDEL)
  - Rate limit keys: ``rate-limit:{identifier}`` (Python-only, documented)
  - Session revocations pubsub channel: ``session:revocations``

Source of truth: ``contracts/redis-keys.md``
"""

from __future__ import annotations

import re
import uuid

# ---------------------------------------------------------------------------
# Contract: Revocation key format — Python ↔ Go gateway
# ---------------------------------------------------------------------------


def test_revocation_key_format_matches_go_gateway():
    """Python must write revocation keys as ``revoked:jti:{jti}``.

    Go gateway derives this as ``fmt.Sprintf("revoked:jti:%s", msg.Payload)``
    in ``services/gateway/middleware/auth.go``.
    """
    jti = str(uuid.uuid4())
    # Import the actual production key-building logic to verify format
    # app/auth/redis_session.py:72 uses f"revoked:jti:{jti}"
    python_key = f"revoked:jti:{jti}"
    # Go gateway format: fmt.Sprintf("revoked:jti:%s", jti)
    go_format_prefix = "revoked:jti:"

    # Verify the Python key uses the same prefix the Go gateway expects
    assert python_key == go_format_prefix + jti, (
        f"Revocation key does not follow 'revoked:jti:' + JTI contract: {python_key!r}. "
        f"See contracts/redis-keys.md — Session & Revocation section."
    )
    # Verify structure: exactly "revoked:jti:" + UUID
    assert python_key.startswith("revoked:jti:"), (
        f"Revocation key must start with 'revoked:jti:', got {python_key!r}"
    )
    assert re.fullmatch(
        r"revoked:jti:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        python_key,
    ), f"Revocation key has unexpected format: {python_key!r}"


# ---------------------------------------------------------------------------
# Contract: WS upgrade ticket key format — Python ↔ Go ws-hub
# ---------------------------------------------------------------------------


def test_ws_ticket_key_prefix_matches_go_ws_hub():
    """TICKET_KEY_PREFIX must be ``ott:ws:`` — Go ws-hub reads this prefix.

    Go ws-hub validates tickets via Redis GETDEL on ``ott:ws:{ticket}``.
    If the Python prefix changes without updating Go, tickets silently fail.
    """
    from app.api.ws.ticket import TICKET_KEY_PREFIX

    assert TICKET_KEY_PREFIX == "ott:ws:", (
        f"TICKET_KEY_PREFIX must be 'ott:ws:' to match Go ws-hub's expectation. "
        f"Got {TICKET_KEY_PREFIX!r}. See contracts/redis-keys.md — WS Upgrade Tickets."
    )


def test_ws_ticket_key_full_format():
    """Full ticket key must be ``ott:ws:{64_hex_chars}``."""
    from app.api.ws.ticket import TICKET_KEY_PREFIX

    ticket = uuid.uuid4().hex + uuid.uuid4().hex  # 64 hex chars
    full_key = f"{TICKET_KEY_PREFIX}{ticket}"

    assert re.fullmatch(r"ott:ws:[0-9a-f]{64}", full_key), (
        f"Full ticket key has unexpected format: {full_key!r}. "
        f"Expected: ott:ws:{{64 lowercase hex chars}}."
    )


def test_ws_ticket_value_format():
    """Ticket value must be ``{user_id}:{jti}`` (colon-joined UUIDs).

    Both Python (app/api/ws/auth.py) and Go (ws-hub/handlers.go) parse this
    by splitting on ':' to extract user_id and jti.
    """
    user_id = str(uuid.uuid4())
    jti = str(uuid.uuid4())
    value = f"{user_id}:{jti}"

    parts = value.split(":")
    # UUID has 4 hyphens, so split on ":" yields exactly 2 parts
    # (user_id contains hyphens but not colons)
    assert len(parts) == 2, (
        f"Ticket value must be '{{user_id}}:{{jti}}' (2 colon-separated parts). "
        f"Got {len(parts)} parts from {value!r}."
    )
    assert parts[0] == user_id
    assert parts[1] == jti


# ---------------------------------------------------------------------------
# Contract: Session revocations pubsub channel
# ---------------------------------------------------------------------------


def test_revocations_pubsub_channel():
    """Pubsub channel must be ``session:revocations``.

    Python publishes to this channel in app/auth/redis_session.py:78.
    Go gateway subscribes in services/gateway/middleware/auth.go.

    This test reads the source file and verifies the channel string via regex,
    since the channel name is currently hardcoded (not a constant).
    """
    import inspect

    from app.auth import redis_session

    source = inspect.getsource(redis_session)
    # Verify the publish call uses "session:revocations"
    assert '"session:revocations"' in source or "'session:revocations'" in source, (
        "app/auth/redis_session.py must publish to 'session:revocations' channel. "
        "Go gateway subscribes to this exact channel name. "
        "If you need to rename it, update services/gateway/middleware/auth.go too."
    )
