"""Integration test: Python-backend session revocation is honoured by Go gateway.

P0-W5-03 regression guard.

Background
----------
Both the Python backend and the Go gateway use ``revoked:jti:{jti}`` as the
Redis key for session revocations.  On logout the backend writes this key;
the gateway reads it to refuse subsequent requests.

History: an earlier version of this guard (P0-W5-03) documented the key as
``revoked:{session_id}``, which was the format at that point in time.  The
implementation was later unified on ``revoked:jti:{jti}`` across both services
(see app/auth/redis_session.py and services/gateway/middleware/auth.go).
The test behaviour remains unchanged — it validates end-to-end revocation —
but the key-format comments have been updated to reflect current code.

Running
-------
These tests require **both** the Python backend and the Go gateway to be
reachable.  Configure them via environment variables:

    BACKEND_URL   e.g. http://localhost:8000   (default)
    GATEWAY_URL   e.g. http://localhost:8080   (default)
    TEST_USER_EMAIL     valid seeded user email
    TEST_USER_PASSWORD  corresponding password

The tests are marked ``integration`` and are skipped unless
``pytest -m integration`` is passed explicitly, or the env-var
``RUN_INTEGRATION_TESTS=1`` is set.
"""

from __future__ import annotations

import os

import httpx
import pytest
import pytest_asyncio  # noqa: F401  – required for asyncio mode

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8080")
TEST_EMAIL = os.getenv("TEST_USER_EMAIL", "integration@example.com")
TEST_PASSWORD = os.getenv("TEST_USER_PASSWORD", "IntegrationSecret1!")

_RUN = bool(os.getenv("RUN_INTEGRATION_TESTS"))

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _RUN, reason="Set RUN_INTEGRATION_TESTS=1 to run"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _login(client: httpx.AsyncClient) -> tuple[str, dict[str, str]]:
    """Login via the Python backend and return (access_token, cookies)."""
    resp = await client.post(
        f"{BACKEND_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
    data = resp.json()
    token: str = data["access_token"]
    # Collect Set-Cookie headers so we can replay them to the gateway
    cookies: dict[str, str] = dict(resp.cookies)
    return token, cookies


async def _logout(
    client: httpx.AsyncClient, token: str, cookies: dict[str, str]
) -> None:
    """Logout via the Python backend (stores revocation in Redis)."""
    resp = await client.post(
        f"{BACKEND_URL}/api/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
        cookies=cookies,
    )
    assert resp.status_code in (200, 204), (
        f"Logout failed: {resp.status_code} {resp.text}"
    )


async def _gateway_request(
    client: httpx.AsyncClient,
    token: str,
    cookies: dict[str, str],
) -> int:
    """Send an authenticated request through the Go gateway and return HTTP status."""
    resp = await client.get(
        f"{GATEWAY_URL}/api/me",
        headers={"Authorization": f"Bearer {token}"},
        cookies=cookies,
    )
    return resp.status_code


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gateway_accepts_valid_session() -> None:
    """Before logout, the gateway must accept the token (sanity check)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        token, cookies = await _login(client)
        status = await _gateway_request(client, token, cookies)
    assert status == 200, f"Gateway rejected a valid session (status {status})"


@pytest.mark.asyncio
async def test_gateway_rejects_revoked_session() -> None:
    """After Python-backend logout, the gateway must return 401.

    This validates P0-W5-03: the Go gateway reads ``revoked:jti:{jti}``
    which matches the key written by the Python backend on logout.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        token, cookies = await _login(client)
        # Verify the session is initially valid
        pre_status = await _gateway_request(client, token, cookies)
        assert pre_status == 200, (
            f"Pre-logout gateway check failed (status {pre_status})"
        )

        await _logout(client, token, cookies)

        # The gateway caches tokens for up to 30 s (L1 TTL).  We allow a short
        # grace window: if the gateway has a warm cache, the test may need to
        # retry.  In CI the gateway is freshly started so L1 is cold.
        post_status = await _gateway_request(client, token, cookies)

    assert post_status == 401, (
        f"Gateway accepted a revoked session (status {post_status}). "
        "Verify that both services use the same Redis key format: "
        "revoked:jti:{{jti}} (see app/auth/redis_session.py and "
        "services/gateway/middleware/auth.go)."
    )


@pytest.mark.asyncio
async def test_gateway_rejects_revoked_session_with_different_client() -> None:
    """Revocation applies even when the token is replayed from a new HTTP client.

    This simulates an attacker who captures the token (e.g., from network
    traffic) and attempts to use it after the legitimate user has logged out.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        token, cookies = await _login(client)
        await _logout(client, token, cookies)

    # New client instance — simulates a different machine / attacker
    async with httpx.AsyncClient(timeout=10.0) as attacker:
        # No cookies — Bearer token only (attacker may not have the session cookie)
        resp = await attacker.get(
            f"{GATEWAY_URL}/api/me",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 401, (
        f"Gateway accepted a revoked token replayed by a different client "
        f"(status {resp.status_code})."
    )
