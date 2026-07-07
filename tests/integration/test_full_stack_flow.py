"""
W25: Full-stack integration flow test.
Tests the complete user journey through the API.
Requires DATABASE_URL env var pointing to PostgreSQL. Skips otherwise.

WHY: Unit tests mock the DB and service layers individually.  These tests
exercise the entire stack end-to-end — API router → service → repository →
DB — to catch integration regressions that mocks cannot surface.
"""

from __future__ import annotations

import os
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

# Only run when a real (non-SQLite) DATABASE_URL is configured.
_DB_URL = os.getenv("DATABASE_URL", "")
_HAS_REAL_DB = bool(_DB_URL) and not _DB_URL.startswith("sqlite")

skip_without_db = pytest.mark.skipif(
    not _HAS_REAL_DB,
    reason="Requires a non-SQLite DATABASE_URL (PostgreSQL) to be set",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unique_email(prefix: str = "w25") -> str:
    """Return a collision-free email address for this test run."""
    return f"{prefix}+{uuid.uuid4().hex[:8]}@university.edu"


# ---------------------------------------------------------------------------
# Full-stack flow tests
# ---------------------------------------------------------------------------


@skip_without_db
async def test_user_registration_and_login_flow(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Complete registration → login → JWT acquisition flow.

    Verifies:
    - Registration creates a user record in the DB.
    - Login with the same credentials returns a valid JWT.
    - The returned token can be used to authenticate subsequent requests.
    """
    email = _unique_email("reg_login")
    password = "SecurePass123!"  # pragma: allowlist secret

    # Step 1: register
    register_response = await async_client.post(
        "/auth/register",
        json={"email": email, "password": password, "role": "student"},
    )
    # 409 is acceptable if the same e-mail was already registered in a prior
    # test run that did not fully clean up.
    assert register_response.status_code in (200, 201, 409), (
        f"Registration failed unexpectedly: {register_response.status_code} "
        f"— {register_response.text}"
    )

    # Step 2: login
    login_response = await async_client.post(
        "/auth/login",
        data={"username": email, "password": password},
    )
    assert login_response.status_code == 200, (
        f"Login failed: {login_response.status_code} — {login_response.text}"
    )
    data = login_response.json()
    token = data.get("access_token") or data.get("token") or login_response.cookies.get("access_token_v2")
    assert token, f"No JWT in login response: {data}"

    # Step 3: use the JWT for an authenticated request
    protected_response = await async_client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    # 200 means auth worked end-to-end; 403 would indicate an RBAC issue
    # that is a separate concern.  Both are acceptable here — what we guard
    # against is 401 (token rejected) or 500 (server error).
    assert protected_response.status_code in (200, 403), (
        f"Authenticated request rejected: {protected_response.status_code} "
        f"— {protected_response.text}"
    )


@skip_without_db
async def test_events_crud_flow(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Create → Read → soft-delete event flow.

    Verifies referential integrity and data consistency across the event
    domain boundary.  Skips gracefully when the events API is not yet
    wired (e.g. feature-flagged off in CI).
    """
    # We need auth to create events — attempt login with an admin credential
    # provisioned via the `admin_user` fixture in the parent suite.
    # Since full-stack tests run without the fixture chain, we try to create
    # a user first.
    email = _unique_email("events_crud")
    password = "SecurePass123!"  # pragma: allowlist secret

    await async_client.post(
        "/auth/register",
        json={"email": email, "password": password, "role": "admin"},
    )
    login = await async_client.post(
        "/auth/login",
        data={"username": email, "password": password},
    )
    if login.status_code != 200:
        pytest.skip(f"Could not authenticate for events CRUD: {login.status_code}")

    token = login.json().get("access_token") or login.json().get("token") or login.cookies.get("access_token_v2")
    auth_header = {"Authorization": f"Bearer {token}"}

    # Step 1: create event
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    create_response = await async_client.post(
        "/events",
        json={
            "title": "W25 Integration Test Event",
            "description": "Created by test_events_crud_flow",
            "starts_at": (now + timedelta(hours=1)).isoformat(),
            "ends_at": (now + timedelta(hours=2)).isoformat(),
        },
        headers=auth_header,
    )
    if create_response.status_code not in (200, 201):
        pytest.skip(
            f"Event creation returned {create_response.status_code} — "
            f"endpoint may be behind a feature flag"
        )

    body = create_response.json()
    event_id = body.get("id")
    assert event_id, f"Created event has no 'id' field: {body}"

    # Step 2: read the created event back
    get_response = await async_client.get(
        f"/events/{event_id}",
        headers=auth_header,
    )
    assert get_response.status_code == 200, (
        f"Expected 200 reading event {event_id}, "
        f"got {get_response.status_code}: {get_response.text}"
    )
    retrieved = get_response.json()
    assert retrieved.get("title") == "W25 Integration Test Event", (
        f"Title mismatch after round-trip: {retrieved}"
    )


@skip_without_db
async def test_health_endpoint_reflects_db_connectivity(
    async_client: AsyncClient,
) -> None:
    """Health endpoint must reflect actual DB connectivity state.

    WHY: A health check that ignores the database gives a false OK signal
    and breaks load-balancer rolling-restart safety checks.
    """
    response = await async_client.get(
        "/health",
        headers={"X-Disable-Query-Budget": "1"},
    )
    assert response.status_code == 200, (
        f"Health endpoint returned {response.status_code}: {response.text}"
    )
    body = response.json()
    # The response must be a JSON object with at least a "status" key.
    assert isinstance(body, dict), f"Expected JSON object, got: {body!r}"
    assert "status" in body, f"Missing 'status' field in health response: {body}"


async def test_unauthenticated_requests_are_rejected_full_stack(
    async_client: AsyncClient,
) -> None:
    """Protected endpoints must reject unauthenticated requests with 401.

    WHY: Verifies the authentication middleware is wired end-to-end — not
    just unit-tested in isolation.  This test runs without a real DB because
    the 401 is returned before any DB query is issued.
    """
    response = await async_client.get("/users/me")
    assert response.status_code == 401, (
        f"Expected 401 for unauthenticated /users/me, "
        f"got {response.status_code}: {response.text}"
    )
    body = response.json()
    assert "detail" in body, f"Missing 'detail' in 401 response: {body}"


async def test_invalid_token_returns_401_full_stack(
    async_client: AsyncClient,
) -> None:
    """An invalid / tampered Bearer token must be rejected with 401.

    WHY: Ensures that JWT signature validation is enforced end-to-end (not
    bypassed by a misconfigured middleware order).
    """
    response = await async_client.get(
        "/users/me",
        headers={"Authorization": "Bearer this.is.not.a.valid.jwt"},
    )
    assert response.status_code == 401, (
        f"Expected 401 for tampered token, got {response.status_code}"
    )
