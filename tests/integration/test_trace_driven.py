"""Integration test: End-to-end OpenTelemetry Trace Propagation.

This test validates that a custom traceparent header passed to the Go gateway
propagates through to the Python backend and is pushed to ws-hub via NATS,
maintaining the same Trace ID across all three services.

It verifies propagation by:
1. Creating a temporary test user and chat room directly in the DB.
2. Authenticating as the test user to obtain a JWT token.
3. Sending a POST /chats/{chat_id}/typing request through the Go Gateway with a
   custom W3C traceparent header containing a newly generated Trace ID.
4. Waiting for NATS propagation to ws-hub.
5. Querying the local Tempo REST API (with retries and backoff) to assert that
   spans from all three services ('gateway', 'university-ecosystem', and 'ws-hub')
   exist and share the same Trace ID.
"""

from __future__ import annotations

import asyncio
import os
import random
import uuid
from contextlib import suppress

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8080")
TEMPO_URL = os.getenv("TEMPO_URL", "http://localhost:3200")
DATABASE_URL = os.getenv(
    "INTEGRATION_DATABASE_URL",
    os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://test:test@localhost:5432/test",  # pragma: allowlist secret
    ),
)

_RUN = bool(os.getenv("RUN_INTEGRATION_TESTS"))

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _RUN, reason="Set RUN_INTEGRATION_TESTS=1 to run"),
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_engine():
    """Create async SQLAlchemy engine pointing to the integration test database."""
    engine = create_async_engine(DATABASE_URL, echo=False, future=True)
    yield engine
    # Cleanup connection pool on exit synchronously to avoid event loop issues
    engine.sync_engine.dispose()


@pytest.fixture
async def setup_integration_data(db_engine):
    """Insert a temporary test user and a group chat they participate in.

    Yields a tuple of (user_email, password, chat_id). Cleaned up after test.
    """
    user_id = uuid.uuid4()
    email = f"trace_test_{uuid.uuid4().hex[:8]}@example.com"
    password = "TraceSecretPassword123!"  # pragma: allowlist secret
    chat_id = uuid.uuid4()

    from app.auth.security import get_password_hash

    hashed_password = await get_password_hash(password)

    async with db_engine.connect() as conn:
        async with conn.begin():
            # 1. Insert user
            await conn.execute(
                text(
                    "INSERT INTO users (id, email, hashed_password, role, is_active, mfa_required) "
                    "VALUES (:id, :email, :password_hash, 'student', true, false)"
                ),
                {"id": user_id, "email": email, "password_hash": hashed_password},
            )
            # 2. Insert profile (needed for username resolution in typing indicator)
            await conn.execute(
                text(
                    "INSERT INTO user_profiles (user_id, full_name) "
                    "VALUES (:uid, 'Trace Integration Tester')"
                ),
                {"uid": user_id},
            )
            # 3. Insert chat
            await conn.execute(
                text(
                    "INSERT INTO chats (id, created_at, updated_at, chat_type) "
                    "VALUES (:id, NOW(), NOW(), 'group')"
                ),
                {"id": chat_id},
            )
            # 4. Add user as participant
            await conn.execute(
                text(
                    "INSERT INTO chat_participants (chat_id, user_id) "
                    "VALUES (:chat_id, :user_id)"
                ),
                {"chat_id": chat_id, "user_id": user_id},
            )

    try:
        yield email, password, chat_id
    finally:
        # Cleanup all test data in reverse order
        async with db_engine.connect() as conn:
            async with conn.begin():
                await conn.execute(
                    text("DELETE FROM chat_participants WHERE chat_id = :chat_id"),
                    {"chat_id": chat_id},
                )
                await conn.execute(
                    text("DELETE FROM chats WHERE id = :chat_id"),
                    {"chat_id": chat_id},
                )
                await conn.execute(
                    text("DELETE FROM user_profiles WHERE user_id = :user_id"),
                    {"user_id": user_id},
                )
                await conn.execute(
                    text("DELETE FROM users WHERE id = :user_id"),
                    {"user_id": user_id},
                )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_service_names(data: any) -> set[str]:
    """Recursively parses Tempo's trace JSON looking for service.name attributes."""
    names = set()
    if isinstance(data, dict):
        for k, v in data.items():
            if k == "service.name":
                if isinstance(v, str):
                    names.add(v)
                elif isinstance(v, dict) and "value" in v:
                    val = v["value"]
                    if isinstance(val, str):
                        names.add(val)
                    elif isinstance(val, dict) and "stringValue" in val:
                        names.add(val["stringValue"])
            elif k == "key" and v == "service.name" and "value" in data:
                val = data["value"]
                if isinstance(val, str):
                    names.add(val)
                elif isinstance(val, dict) and "stringValue" in val:
                    names.add(val["stringValue"])
                elif isinstance(val, dict) and "value" in val:
                    names.add(str(val["value"]))
            else:
                names.update(_extract_service_names(v))
    elif isinstance(data, list):
        for item in data:
            names.update(_extract_service_names(item))
    return names


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trace_propagation_across_services(setup_integration_data) -> None:
    """Send a request via the Go Gateway with traceparent and assert propagation in Tempo."""
    email, password, chat_id = setup_integration_data

    # Generate custom Trace ID (128-bit hex = 32 chars)
    trace_id = uuid.uuid4().hex
    parent_span_id = f"{random.getrandbits(64):016x}"
    traceparent = f"00-{trace_id}-{parent_span_id}-01"

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Fetch CSRF token first
        await client.get(f"{BACKEND_URL}/health/ready")
        csrf_token = client.cookies.get("csrf_token", "")

        # 1. Login via backend to get the access token and cookies
        login_resp = await client.post(
            f"{BACKEND_URL}/api/v1/auth/login/json",
            json={"email": email, "password": password},
            headers={"x-csrf-token": csrf_token},
        )
        assert login_resp.status_code == 200, (
            f"Login failed: {login_resp.status_code} {login_resp.text}"
        )
        login_data = login_resp.json()
        token = login_data.get("access_token") or login_resp.cookies.get(
            "access_token_v2", ""
        )
        cookies = dict(login_resp.cookies)

        # 2. Issue a POST /chats/{chat_id}/typing request via the Go Gateway carrying traceparent
        headers = {
            "Authorization": f"Bearer {token}",
            "traceparent": traceparent,
            "Content-Type": "application/json",
        }
        client.cookies.update(cookies)
        typing_resp = await client.post(
            f"{GATEWAY_URL}/api/v1/chats/{chat_id}/typing",
            headers=headers,
        )
        assert typing_resp.status_code == 200, (
            f"Gateway typing request failed: {typing_resp.status_code} {typing_resp.text}"
        )

    # 3. Query Tempo's REST API at /api/traces/{trace_id} with backoff
    tempo_client = httpx.AsyncClient(timeout=10.0)

    # Trace ingestion can be delayed. We try up to 10 times with exponential backoff.
    max_attempts = 10
    backoff = 0.5
    trace_data = None

    for attempt in range(1, max_attempts + 1):
        with suppress(Exception):
            resp = await tempo_client.get(f"{TEMPO_URL}/api/traces/{trace_id}")
            if resp.status_code == 200:
                trace_data = resp.json()
                # Verify we got non-empty trace data
                if trace_data and (
                    "batches" in trace_data
                    or "scopeSpans" in trace_data
                    or len(trace_data) > 0
                ):
                    break

        await asyncio.sleep(backoff)
        backoff = min(5.0, backoff * 1.5)
    else:
        await tempo_client.aclose()
        pytest.fail(
            f"Trace {trace_id} was not found in Tempo after {max_attempts} attempts."
        )

    await tempo_client.aclose()

    # 4. Extract and assert service names present in the Trace ID spans
    service_names = _extract_service_names(trace_data)

    # Expected services:
    # - gateway (Go Gateway)
    # - university-ecosystem (Python Backend - see app/core/config/observability.py)
    # - ws-hub (WebSocket Hub receiving the typing frame via NATS)

    # Print services found for debugging purposes in case of failure
    print(f"Services found in Tempo trace: {service_names}")

    # Robust verification: try to match key services in parsed service names.
    # Fallback to checking raw JSON string if service name schema varies.
    raw_trace_str = str(trace_data).lower()

    has_gateway = "gateway" in service_names or "gateway" in raw_trace_str
    has_backend = (
        "university-ecosystem" in service_names
        or "backend" in service_names
        or "university-ecosystem" in raw_trace_str
        or "backend" in raw_trace_str
    )
    has_wshub = "ws-hub" in service_names or "ws-hub" in raw_trace_str

    assert has_gateway, (
        f"Go Gateway span not found under trace {trace_id}. Found services: {service_names}"
    )
    assert has_backend, (
        f"Python Backend span not found under trace {trace_id}. Found services: {service_names}"
    )
    assert has_wshub, (
        f"WebSocket Hub span not found under trace {trace_id}. Found services: {service_names}"
    )
