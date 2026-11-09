"""Chaos & Resilience Tests — Phase 3 QA Initiative.

These tests verify transactional outbox durability and idempotency behaviours
during real infrastructure failures.  They require a fully running Docker
Compose environment and are opt-in to avoid accidentally stopping containers
during regular CI runs.

Activate with:
    CHAOS_TESTS=1 pytest tests/chaos/test_resilience.py -v

WHY: Unit tests with mocked NATS/Redis prove happy-path logic.  These chaos
tests prove that the *system* survives real failures — that the outbox actually
persists pending events to the DB when NATS is down, and that the app actually
degrades gracefully (fail-open) when Valkey is unavailable.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import time
import uuid

import httpx
import pytest

# ── Guard ────────────────────────────────────────────────────────────────────
# Chaos tests only run when CHAOS_TESTS=1 is set so that a regular `pytest`
# invocation never accidentally stops containers on a developer machine.
pytestmark = [
    pytest.mark.chaos,
    pytest.mark.skipif(
        os.getenv("CHAOS_TESTS") != "1",
        reason="Set CHAOS_TESTS=1 environment variable to run chaos resilience tests",
    ),
]

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8080")

# How long to wait for the outbox worker to pick up and process pending events
# after NATS is restored.  In CI this is generous to account for cold starts.
_OUTBOX_DRAIN_TIMEOUT_SECONDS: int = int(os.getenv("OUTBOX_DRAIN_TIMEOUT", "30"))
_OUTBOX_POLL_INTERVAL_SECONDS: float = 1.0


# ── Helpers ──────────────────────────────────────────────────────────────────


def _run_docker_compose(cmd: str) -> str:
    """Execute a docker compose sub-command and return stdout.

    Raises CalledProcessError on non-zero exit so the test fails loudly
    instead of silently swallowing infrastructure setup errors.

    WHY shlex.split: avoids shell=True (ruff S602) while correctly handling
    quoted arguments.  The `cmd` parameter is always a test-internal literal
    (e.g. "stop nats"), never user-supplied input, so S603/S607 are safe here.
    """
    import shlex

    try:
        result = subprocess.run(  # noqa: S603
            ["docker", "compose", *shlex.split(cmd)],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError as exc:
        print(f"[docker compose] {exc.stderr}")
        raise


def _require_gateway() -> None:
    """Fail explicitly when the gateway required by CHAOS_TESTS=1 is not healthy.

    AUD-322: a missing gateway is a broken precondition of the opt-in chaos run,
    not a reason to skip the resilience check.  The module-level pytestmark is
    the only runtime gate; once CHAOS_TESTS=1 is set every chaos test must run
    or fail with the precondition named in the message.
    """
    try:
        with httpx.Client(base_url=GATEWAY_URL, timeout=3.0) as client:
            status = client.get("/health").status_code
    except (httpx.HTTPError, OSError) as exc:
        pytest.fail(
            f"GATEWAY_URL {GATEWAY_URL} is unreachable under CHAOS_TESTS=1 "
            f"(docker-compose.go.yml must be part of the chaos stack): {exc}"
        )
    if status != 200:
        pytest.fail(
            f"GATEWAY_URL {GATEWAY_URL}/health returned {status} under CHAOS_TESTS=1"
        )


def _first_chaos_chat_id(client: httpx.Client) -> str:
    """Return a chat visible to the chaos user, or fail naming the seed precondition.

    AUD-322: the chat lookup is a precondition, so a missing chat fails the test
    explicitly (before any container is stopped) instead of skipping it.
    """
    response = client.get("/api/v1/chats/?limit=1")
    items = response.json().get("items") if response.status_code == 200 else None
    if not items:
        pytest.fail(
            "No chat is visible to CHAOS_TEST_USER under CHAOS_TESTS=1; the chaos "
            f"stack must seed at least one chat for it (GET returned "
            f"{response.status_code})."
        )
    return str(items[0]["id"])


def _csrf_headers(client: httpx.Client) -> dict[str, str]:
    """Use the current CSRF cookie, including any rotation after login."""
    token = client.cookies.get("csrf_token")
    if not token:
        pytest.fail("The chaos API session did not provide a CSRF cookie")
    return {"X-CSRF-Token": token}


def _post_chaos_message(
    client: httpx.Client,
    chat_id: str,
    content: str,
    *,
    idempotency_key: str | None = None,
) -> httpx.Response:
    headers = _csrf_headers(client)
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return client.post(
        f"/api/v1/chats/{chat_id}/messages",
        files={"content": (None, content)},
        headers=headers,
    )


def _outbox_engine(db_url: str):
    """Use the installed synchronous PostgreSQL driver for plain PG URLs."""
    import sqlalchemy

    url = sqlalchemy.engine.make_url(db_url)
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    return sqlalchemy.create_engine(url, future=True)


def _assert_chat_send_db_state(
    db_url: str, chat_id: str, client_key: str, content: str, message_id: str
) -> None:
    """Check the exact chat message, private receipt, and outbox event on the primary."""
    from sqlalchemy import text

    engine = _outbox_engine(db_url)
    try:
        with engine.connect() as conn:
            messages = conn.execute(
                text(
                    "SELECT CAST(id AS TEXT), CAST(sender_id AS TEXT) FROM messages "
                    "WHERE CAST(chat_id AS TEXT) = :chat_id AND content = :content"
                ),
                {"chat_id": chat_id, "content": content},
            ).fetchall()
            assert len(messages) == 1, (
                f"Expected one message for the unique chaos payload; found {len(messages)}."
            )
            stored_message_id, user_id = messages[0]
            assert stored_message_id == message_id, (
                "Outage response ID differs from the stored message"
            )
            digest = hashlib.sha256(
                b"university-ecosystem:chat-send-receipt:v1\0"
                + uuid.UUID(chat_id).bytes
                + uuid.UUID(user_id).bytes
                + client_key.encode("utf-8")
            ).hexdigest()
            receipts = conn.execute(
                text(
                    "SELECT CAST(message_id AS TEXT) FROM chat_send_receipts "
                    "WHERE CAST(chat_id AS TEXT) = :chat_id "
                    "AND CAST(user_id AS TEXT) = :user_id AND key_digest = :digest "
                    "AND expires_at > CURRENT_TIMESTAMP"
                ),
                {"chat_id": chat_id, "user_id": user_id, "digest": digest},
            ).fetchall()
            assert len(receipts) == 1 and receipts[0][0] == message_id, (
                "Expected one active scoped receipt for the outage message."
            )
            event_count = conn.execute(
                text(
                    "SELECT COUNT(*) FROM stored_events "
                    "WHERE event_type = 'chat.message_sent' AND aggregate_type = 'Message' "
                    "AND aggregate_id = :message_id"
                ),
                {"message_id": message_id},
            ).scalar_one()
            assert event_count == 1, (
                f"Expected one outbox event for the outage message; found {event_count}."
            )
    finally:
        engine.dispose()


def _pending_message_event_id(db_url: str, message_id: str) -> str:
    """Find the unprocessed outbox event for the message just sent."""
    from sqlalchemy import text

    engine = _outbox_engine(db_url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT id, processed_at FROM stored_events "
                    "WHERE event_type = 'chat.message_sent' "
                    "AND aggregate_id = :message_id"
                ),
                {"message_id": message_id},
            ).fetchall()
        assert len(rows) == 1, (
            "Expected exactly one outbox event for the message sent during the "
            f"NATS outage; found {len(rows)}."
        )
        assert rows[0][1] is None, (
            "The message outbox event was already processed during the NATS outage."
        )
        return str(rows[0][0])
    finally:
        engine.dispose()


def _wait_for_outbox_event_processed(
    db_url: str,
    event_id: str,
    timeout: float = _OUTBOX_DRAIN_TIMEOUT_SECONDS,
) -> bool:
    """Poll the outbox table until the specific event is fully processed.

    Returns True when processed_at is set within *timeout* seconds and the
    event was not dead-lettered.
    Returns False on timeout (caller should then fail the test).

    WHY polling: the outbox worker runs on its own asyncio loop and we cannot
    hook into it from a synchronous test.  Polling with a generous timeout is
    the simplest, correct approach.
    """
    from sqlalchemy import text

    engine = _outbox_engine(db_url)
    deadline = time.monotonic() + timeout
    try:
        with engine.connect() as conn:
            while time.monotonic() < deadline:
                row = conn.execute(
                    text(
                        "SELECT event.processed_at, EXISTS ("
                        "SELECT 1 FROM failed_outbox_events AS failed "
                        "WHERE failed.original_event_id = event.id) "
                        "FROM stored_events AS event "
                        "WHERE CAST(event.id AS TEXT) = :event_id"
                    ),
                    {"event_id": event_id},
                ).fetchone()
                if row is not None and row[0] is not None:
                    assert not row[1], "The message outbox event was dead-lettered"
                    return True
                time.sleep(_OUTBOX_POLL_INTERVAL_SECONDS)
        return False
    finally:
        engine.dispose()


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def setup_chaos_env():
    """Ensure docker compose environment is up before the module runs."""
    if os.getenv("GITHUB_ACTIONS") != "true":
        _run_docker_compose("up -d --no-build --no-recreate")
        time.sleep(3)  # Wait for services to initialise
    yield
    # Restore any services that a test may have stopped
    _run_docker_compose("start valkey nats ws-hub gateway")
    time.sleep(2)


@pytest.fixture
def authenticated_client(setup_chaos_env) -> httpx.Client:
    """Return a synchronous httpx client pre-authenticated against the live API.

    The credentials must belong to a user with a seeded chat on the owned stand.
    """
    credentials = {
        "username": os.getenv("CHAOS_TEST_USER", "chaos@test.local"),
        "password": os.getenv("CHAOS_TEST_PASSWORD", "chaos-test-password"),
    }
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        response = client.get("/api/v1/auth/csrf-cookie")
        if response.status_code != 200:
            pytest.fail(
                f"Could not initialize the chaos CSRF cookie: HTTP {response.status_code}"
            )
        initial_csrf = _csrf_headers(client)["X-CSRF-Token"]
        response = client.post(
            "/api/v1/auth/login",
            data=credentials,
            headers={"X-CSRF-Token": initial_csrf},
        )
        if response.status_code != 200:
            pytest.fail(
                "Could not authenticate CHAOS_TEST_USER under CHAOS_TESTS=1; the "
                f"chaos stack must provision it: HTTP {response.status_code}"
            )
        if not client.cookies.get("access_token_v2"):
            pytest.fail("Chaos login did not provide an authenticated session cookie")
        if _csrf_headers(client)["X-CSRF-Token"] == initial_csrf:
            pytest.fail("Chaos login did not rotate the CSRF cookie")
        yield client


# ── Tests ────────────────────────────────────────────────────────────────────


def test_nats_outage_outbox_durability(setup_chaos_env, authenticated_client):
    """Verify that messages sent while NATS is down are persisted to the outbox.

    Scenario:
        1. Stop NATS → simulate a broker outage.
        2. Send a chat message via REST API.
        3. Assert HTTP 200 — the write path must NOT be blocked by NATS.
        4. Assert the message's StoredEvent has no processed_at timestamp.
        5. Restore NATS.
        6. Wait for the outbox worker to drain the event.
        7. Assert processed_at is now set for that same StoredEvent.
    """
    # Identify a chat to send a message to (use the first available).  Resolved
    # before NATS is stopped so a missing precondition fails without side effects.
    chat_id = _first_chaos_chat_id(authenticated_client)

    # 1. Stop NATS
    print("\n[Chaos] Stopping NATS broker...")
    _run_docker_compose("stop nats")
    time.sleep(2)

    try:
        # 2. Send message while NATS is down
        response = _post_chaos_message(
            authenticated_client, chat_id, "Chaos test message — NATS down"
        )

        # 3. HTTP must succeed — NATS failure must not block the write path
        assert response.status_code == 200, (
            f"Expected 200 but got {response.status_code}: {response.text}"
        )

        # 4. Verify pending event is persisted in the outbox DB
        db_url = os.getenv(
            "DATABASE_URL_SYNC",
            "postgresql://postgres:postgres@localhost:5432/university",  # pragma: allowlist secret
        )
        message_id = response.json().get("id")
        assert isinstance(message_id, str) and message_id, "Message response has no ID"
        event_id = _pending_message_event_id(db_url, message_id)

    finally:
        # 5. Restore NATS unconditionally
        print("[Chaos] Restoring NATS broker...")
        _run_docker_compose("start nats")
        time.sleep(3)

    # 6 & 7. Wait for worker to drain
    processed = _wait_for_outbox_event_processed(db_url, event_id)
    assert processed, (
        f"Outbox event was not processed within {_OUTBOX_DRAIN_TIMEOUT_SECONDS}s "
        "after NATS was restored.  Check that the outbox worker is running and "
        "the NATS consumer group subscription is healthy."
    )


def test_valkey_outage_idempotency_fail_open(setup_chaos_env, authenticated_client):
    """A keyed outage send commits one receipt and replays after Valkey recovers."""
    db_url = os.getenv("DATABASE_URL_SYNC")
    if not db_url:
        pytest.fail("DATABASE_URL_SYNC is required to inspect the owned chaos database")
    chat_id = _first_chaos_chat_id(authenticated_client)
    idempotency_key = f"chaos-test-{uuid.uuid4()}"
    content = f"Idempotency chaos test — {idempotency_key}"

    # 1. Stop Valkey
    print("\n[Chaos] Stopping Valkey (Redis)...")
    _run_docker_compose("stop valkey")
    time.sleep(2)

    try:
        # 2 & 3. Request must succeed despite Valkey being down (fail-open)
        response = _post_chaos_message(
            authenticated_client,
            chat_id,
            content,
            idempotency_key=idempotency_key,
        )
        assert response.status_code in (201, 200), (
            f"Expected 2xx (fail-open) but got {response.status_code}: {response.text}"
        )
        outage_id = response.json().get("id")
        assert isinstance(outage_id, str) and outage_id.strip(), (
            "Outage response has no message ID"
        )
        _assert_chat_send_db_state(db_url, chat_id, idempotency_key, content, outage_id)

    finally:
        # 4. Restore Valkey
        print("[Chaos] Restoring Valkey...")
        _run_docker_compose("start valkey")
        time.sleep(3)

    # 5 & 6. The first request after recovery must replay the outage message.
    response_after_restore = _post_chaos_message(
        authenticated_client,
        chat_id,
        content,
        idempotency_key=idempotency_key,
    )
    assert response_after_restore.status_code in (201, 200), (
        f"Expected 2xx after Valkey restore but got "
        f"{response_after_restore.status_code}: {response_after_restore.text}"
    )

    # 7 & 8. Second request with the same key — must be deduplicated
    response_dedup = _post_chaos_message(
        authenticated_client,
        chat_id,
        content,
        idempotency_key=idempotency_key,
    )
    assert response_dedup.status_code in (201, 200), (
        f"Expected 2xx (idempotent repeat) but got "
        f"{response_dedup.status_code}: {response_dedup.text}"
    )
    for retry in (response_after_restore, response_dedup):
        retry_id = retry.json().get("id")
        assert isinstance(retry_id, str) and retry_id.strip(), (
            "Retry response has no message ID"
        )
        assert retry_id == outage_id, (
            "Retry did not replay the message sent during the outage"
        )
    _assert_chat_send_db_state(db_url, chat_id, idempotency_key, content, outage_id)


def test_valkey_redis_down_resilience(setup_chaos_env):
    """Verify that backend degrades gracefully when Redis/Valkey goes down.

    According to RZ-27-03, rate limiter must fail closed on double failure
    (Redis + memory), returning 503/429 rather than exposing backend.
    """
    _require_gateway()
    # 1. Verify health when Redis is UP
    with httpx.Client(base_url=GATEWAY_URL) as client:
        res = client.get("/health")
        assert res.status_code == 200

    # 2. Kill Valkey (Redis) container
    print("\n[Chaos] Stopping Valkey (Redis)...")
    _run_docker_compose("stop valkey")
    time.sleep(2)

    try:
        # 3. Request health or rate-limited endpoints.
        # The API must fail closed gracefully (503 or 429) rather than 500.
        with httpx.Client(base_url=GATEWAY_URL) as client:
            try:
                res = client.get("/api/v1/auth/csrf-cookie", timeout=3.0)
                assert res.status_code in (200, 429, 503)
            except httpx.TimeoutException:
                # Gateway timeouts are also acceptable degradation signatures
                pass
    finally:
        # 4. Recover Valkey
        print("[Chaos] Starting Valkey (Redis)...")
        _run_docker_compose("start valkey")
        time.sleep(3)


def test_ws_hub_down_gateway_proxy_fallback(setup_chaos_env):
    """Verify that when ws-hub is down, gateway handles the failure gracefully.

    The gateway reverse proxies websocket connections to ws-hub:8081.
    If ws-hub dies, gateway should return 502 Bad Gateway to new connection
    attempts instead of crashing.
    """
    _require_gateway()
    # 1. Stop ws-hub
    print("\n[Chaos] Stopping ws-hub...")
    _run_docker_compose("stop ws-hub")
    time.sleep(2)

    try:
        # 2. Try to connect to WS or proxy endpoint and assert it returns 502 Bad Gateway
        with httpx.Client(base_url=GATEWAY_URL) as client:
            res = client.get("/ws/chat", timeout=3.0)
            assert res.status_code == 502, (
                f"Expected 502 while ws-hub is stopped, got {res.status_code}"
            )
    finally:
        # 3. Recover ws-hub
        print("[Chaos] Starting ws-hub...")
        _run_docker_compose("start ws-hub")
        time.sleep(3)


def test_nats_down_outbox_queue_resilience(setup_chaos_env):
    """Verify system health when NATS goes down.

    Messages should be stored in the SQL DB outbox table and processed
    later when NATS is back online (Transactional Outbox Pattern).
    """
    # 1. Stop NATS container
    print("\n[Chaos] Stopping NATS...")
    _run_docker_compose("stop nats")
    time.sleep(2)

    try:
        # 2. Verify that FastAPI healthz shows NATS is degraded but HTTP API still works
        with httpx.Client(base_url=BASE_URL) as client:
            res = client.get("/healthz", timeout=3.0)
            # The backend has degraded health state but continues answering
            assert res.status_code in (200, 503)
    finally:
        # 3. Start NATS container
        print("[Chaos] Starting NATS...")
        _run_docker_compose("start nats")
        time.sleep(3)
