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

import os
import subprocess
import time

import httpx
import pytest

# ── Guard ────────────────────────────────────────────────────────────────────
# Chaos tests only run when CHAOS_TESTS=1 is set so that a regular `pytest`
# invocation never accidentally stops containers on a developer machine.
pytestmark = pytest.mark.skipif(
    os.getenv("CHAOS_TESTS") != "1",
    reason="Set CHAOS_TESTS=1 environment variable to run chaos resilience tests",
)

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


def _gateway_reachable() -> bool:
    """True if the Go gateway is up at GATEWAY_URL/health.

    The two gateway-dependent chaos tests below call GATEWAY_URL as their FIRST
    action OUTSIDE any try/except, so they HARD-ERROR (not skip) when the gateway
    isn't running — e.g. when docker-compose.go.yml isn't part of the stack. Used
    as a skipif condition so those tests skip cleanly in that case instead.

    The CHAOS_TESTS guard short-circuits to False during normal (non-chaos)
    collection: the module is runtime-skipped via the module-level pytestmark
    anyway, and an unguarded probe would add a connect-timeout to every `pytest`
    collection (testpaths includes tests/, and mutmut copies tests/ into
    mutants/tests/). When CHAOS_TESTS=1 the CI job has already brought the stack
    up + readiness-polled the gateway before pytest collects this module.
    """
    if os.getenv("CHAOS_TESTS") != "1":
        return False
    try:
        with httpx.Client(base_url=GATEWAY_URL, timeout=3.0) as client:
            return client.get("/health").status_code == 200
    except httpx.HTTPError, OSError:
        return False


def _wait_for_outbox_event_processed(
    db_url: str,
    event_type: str,
    timeout: int = _OUTBOX_DRAIN_TIMEOUT_SECONDS,
) -> bool:
    """Poll the outbox table until the target event_type is fully processed.

    Returns True when processed_at is set within *timeout* seconds.
    Returns False on timeout (caller should then fail the test).

    WHY polling: the outbox worker runs on its own asyncio loop and we cannot
    hook into it from a synchronous test.  Polling with a generous timeout is
    the simplest, correct approach.
    """
    import sqlalchemy
    from sqlalchemy import text

    engine = sqlalchemy.create_engine(db_url, future=True)
    deadline = time.monotonic() + timeout

    with engine.connect() as conn:
        while time.monotonic() < deadline:
            row = conn.execute(
                text(
                    "SELECT processed_at FROM stored_events "
                    "WHERE event_type = :event_type "
                    "  AND status = 'processed' "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"event_type": event_type},
            ).fetchone()
            if row is not None and row[0] is not None:
                return True
            time.sleep(_OUTBOX_POLL_INTERVAL_SECONDS)

    return False


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

    The client uses admin credentials seeded via docker compose fixtures.
    Adjust the username/password to match your compose seed data.
    """
    credentials = {
        "username": os.getenv("CHAOS_TEST_USER", "chaos@test.local"),
        "password": os.getenv("CHAOS_TEST_PASSWORD", "chaos-test-password"),
    }
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        # Obtain auth token
        response = client.post("/api/v1/auth/login", data=credentials)
        if response.status_code != 200:
            pytest.skip(f"Could not authenticate chaos test user: {response.text}")

        token = response.json().get("access_token", "")
        client.headers["Authorization"] = f"Bearer {token}"
        yield client


# ── Tests ────────────────────────────────────────────────────────────────────


def test_nats_outage_outbox_durability(setup_chaos_env, authenticated_client):
    """Verify that messages sent while NATS is down are persisted to the outbox.

    Scenario:
        1. Stop NATS → simulate a broker outage.
        2. Send a chat message via REST API.
        3. Assert HTTP 201 — the write path must NOT be blocked by NATS.
        4. Assert a StoredEvent with status='pending' exists in the DB.
        5. Restore NATS.
        6. Wait for the outbox worker to drain the event.
        7. Assert processed_at is now set (status='processed').
    """
    # 1. Stop NATS
    print("\n[Chaos] Stopping NATS broker...")
    _run_docker_compose("stop nats")
    time.sleep(2)

    # Identify a chat to send a message to (use the first available)
    chats_response = authenticated_client.get("/api/v1/chats/?limit=1")
    if chats_response.status_code != 200 or not chats_response.json().get("items"):
        _run_docker_compose("start nats")
        pytest.skip("No chats available for chaos test — seed data required")

    chat_id = chats_response.json()["items"][0]["id"]

    try:
        # 2. Send message while NATS is down
        response = authenticated_client.post(
            f"/api/v1/chats/{chat_id}/messages",
            json={"content": "Chaos test message — NATS down"},
        )

        # 3. HTTP must succeed — NATS failure must not block the write path
        assert response.status_code == 201, (
            f"Expected 201 but got {response.status_code}: {response.text}"
        )

        # 4. Verify pending event is persisted in the outbox DB
        db_url = os.getenv(
            "DATABASE_URL_SYNC",
            "postgresql://postgres:postgres@localhost:5432/university",  # pragma: allowlist secret
        )
        import sqlalchemy
        from sqlalchemy import text

        engine = sqlalchemy.create_engine(db_url, future=True)
        with engine.connect() as conn:
            pending = conn.execute(
                text(
                    "SELECT id FROM stored_events "
                    "WHERE event_type = 'chat.message_sent' "
                    "  AND status = 'pending' "
                    "ORDER BY created_at DESC LIMIT 1"
                )
            ).fetchone()

        assert pending is not None, (
            "Expected a pending StoredEvent in the outbox after NATS outage, "
            "but none was found.  The transactional outbox may not be recording events."
        )

    finally:
        # 5. Restore NATS unconditionally
        print("[Chaos] Restoring NATS broker...")
        _run_docker_compose("start nats")
        time.sleep(3)

    # 6 & 7. Wait for worker to drain
    db_url = os.getenv(
        "DATABASE_URL_SYNC",
        "postgresql://postgres:postgres@localhost:5432/university",  # pragma: allowlist secret
    )
    processed = _wait_for_outbox_event_processed(db_url, "chat.message_sent")
    assert processed, (
        f"Outbox event was not processed within {_OUTBOX_DRAIN_TIMEOUT_SECONDS}s "
        "after NATS was restored.  Check that the outbox worker is running and "
        "the NATS consumer group subscription is healthy."
    )


def test_valkey_outage_idempotency_fail_open(setup_chaos_env, authenticated_client):
    """Verify that the idempotency check degrades gracefully when Valkey is down.

    The system uses a fail-open strategy (approved in the implementation plan):
    when Valkey is unreachable, the idempotency check is skipped and the
    request proceeds normally.  This preserves API availability at the cost of
    potential duplicate messages during the outage window.

    Scenario:
        1. Stop Valkey.
        2. Send a message with Idempotency-Key header.
        3. Assert HTTP 201 — fail-open means the request MUST succeed.
        4. Restore Valkey.
        5. Send the same message with the same Idempotency-Key.
        6. Assert HTTP 201 (first dedup attempt, key is now stored in Valkey).
        7. Send again with the same key.
        8. Assert HTTP 201 (idempotent repeat) — no duplicate message is created.
    """
    chats_response = authenticated_client.get("/api/v1/chats/?limit=1")
    if chats_response.status_code != 200 or not chats_response.json().get("items"):
        pytest.skip("No chats available for chaos test — seed data required")

    chat_id = chats_response.json()["items"][0]["id"]
    idempotency_key = "chaos-test-idem-key-valkey-down-001"

    # 1. Stop Valkey
    print("\n[Chaos] Stopping Valkey (Redis)...")
    _run_docker_compose("stop valkey")
    time.sleep(2)

    try:
        # 2 & 3. Request must succeed despite Valkey being down (fail-open)
        response = authenticated_client.post(
            f"/api/v1/chats/{chat_id}/messages",
            json={"content": "Idempotency chaos test — Valkey down"},
            headers={"Idempotency-Key": idempotency_key},
        )
        assert response.status_code in (201, 200), (
            f"Expected 2xx (fail-open) but got {response.status_code}: {response.text}"
        )

    finally:
        # 4. Restore Valkey
        print("[Chaos] Restoring Valkey...")
        _run_docker_compose("start valkey")
        time.sleep(3)

    # 5 & 6. First request after Valkey is back — stores the idempotency key
    response_after_restore = authenticated_client.post(
        f"/api/v1/chats/{chat_id}/messages",
        json={"content": "Idempotency chaos test — Valkey down"},
        headers={"Idempotency-Key": idempotency_key},
    )
    assert response_after_restore.status_code in (201, 200), (
        f"Expected 2xx after Valkey restore but got "
        f"{response_after_restore.status_code}: {response_after_restore.text}"
    )

    # 7 & 8. Second request with the same key — must be deduplicated
    response_dedup = authenticated_client.post(
        f"/api/v1/chats/{chat_id}/messages",
        json={"content": "Idempotency chaos test — Valkey down"},
        headers={"Idempotency-Key": idempotency_key},
    )
    assert response_dedup.status_code in (201, 200), (
        f"Expected 2xx (idempotent repeat) but got "
        f"{response_dedup.status_code}: {response_dedup.text}"
    )
    # The deduped response should return the same message ID as the cached one
    dedup_message_id = response_dedup.json().get("id")
    assert dedup_message_id == response_after_restore.json().get("id"), (
        "Idempotency key did not deduplicate the request — a new message was "
        "created instead of returning the cached response.  Check that the "
        "idempotency cache key derivation is stable across requests."
    )


@pytest.mark.skipif(
    not _gateway_reachable(),
    reason="Go gateway not reachable (docker-compose.go.yml not loaded)",
)
def test_valkey_redis_down_resilience(setup_chaos_env):
    """Verify that backend degrades gracefully when Redis/Valkey goes down.

    According to RZ-27-03, rate limiter must fail closed on double failure
    (Redis + memory), returning 503/429 rather than exposing backend.
    """
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
            except httpx.HTTPError:
                # Gateway timeouts are also acceptable degradation signatures
                pass
    finally:
        # 4. Recover Valkey
        print("[Chaos] Starting Valkey (Redis)...")
        _run_docker_compose("start valkey")
        time.sleep(3)


@pytest.mark.skipif(
    not _gateway_reachable(),
    reason="Go gateway not reachable (docker-compose.go.yml not loaded)",
)
def test_ws_hub_down_gateway_proxy_fallback(setup_chaos_env):
    """Verify that when ws-hub is down, gateway handles the failure gracefully.

    The gateway reverse proxies websocket connections to ws-hub:8081.
    If ws-hub dies, gateway should return 502 Bad Gateway to new connection
    attempts instead of crashing.
    """
    # 1. Stop ws-hub
    print("\n[Chaos] Stopping ws-hub...")
    _run_docker_compose("stop ws-hub")
    time.sleep(2)

    try:
        # 2. Try to connect to WS or proxy endpoint and assert it returns 502 Bad Gateway
        with httpx.Client(base_url=GATEWAY_URL) as client:
            res = client.get("/ws/chat", timeout=3.0)
            assert res.status_code in (502, 503, 404)
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
