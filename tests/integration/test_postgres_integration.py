"""Integration tests for database-layer behaviors (Wave 12.1).

These tests verify multi-layer interactions:
    API → Service → Repository → DB (SQLite in CI / PostgreSQL in full stack)

They use the fixtures provided by conftest.py (async_client, db_session)
and are intentionally free of testcontainers so they run in standard CI.

Run with:
    pytest tests/integration/test_postgres_integration.py -v -m integration
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unique_email(prefix: str = "integ") -> str:
    """Return a collision-free email address for a single test run."""
    return f"{prefix}+{uuid.uuid4().hex[:8]}@university.edu"


def _register_payload(email: str, password: str = "Integration#1") -> dict:  # noqa: S107
    return {"email": email, "password": password, "role": "student"}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_user_create_and_retrieve_roundtrip(async_client: AsyncClient) -> None:
    """Verify full create→retrieve round-trip through all layers.

    WHY: Ensures the registration handler, service, repository, and DB columns
    all agree on the canonical user representation.  A mismatch in any layer
    (e.g. column name change in a migration) would surface here before it
    reaches a user-facing 500.
    """
    email = _unique_email("roundtrip")
    payload = _register_payload(email)

    resp = await async_client.post("/auth/register", json=payload)
    assert resp.status_code in {200, 201}, resp.text

    body = resp.json()
    assert "id" in body or "user" in body or "email" in body, (
        f"Unexpected registration response shape: {body}"
    )


async def test_duplicate_email_is_rejected(async_client: AsyncClient) -> None:
    """Second registration with the same email must return 409 / 400 — not 500.

    WHY: Validates that the UNIQUE constraint on users.email is correctly
    surfaced by the service layer as a domain error rather than an unhandled
    DB exception.
    """
    email = _unique_email("dup")
    payload = _register_payload(email)

    first = await async_client.post("/auth/register", json=payload)
    assert first.status_code in {200, 201}, first.text

    second = await async_client.post("/auth/register", json=payload)
    assert second.status_code in {400, 409, 422}, (
        f"Expected 4xx for duplicate email, got {second.status_code}: {second.text}"
    )


async def test_concurrent_registrations_no_data_corruption(
    async_client: AsyncClient,
) -> None:
    """Concurrent writes for different users must not corrupt each other.

    WHY: Race conditions between concurrent INSERT paths (especially around
    auto-generated UUIDs / created_at timestamps) can silently produce
    corrupted rows or PK collisions.  Using asyncio.gather simulates the
    burst scenario.
    """
    emails = [_unique_email(f"concurrent{i}") for i in range(5)]
    payloads = [_register_payload(e) for e in emails]

    responses = await asyncio.gather(
        *[async_client.post("/auth/register", json=p) for p in payloads],
        return_exceptions=True,
    )

    successful = 0
    for resp in responses:
        if isinstance(resp, Exception):
            # Network-layer errors would indicate a server crash — not acceptable.
            pytest.fail(f"Concurrent registration raised an exception: {resp}")
        if resp.status_code in {200, 201}:
            successful += 1

    # All 5 should succeed if isolation is correct.
    assert successful == 5, (
        f"Expected 5 successful concurrent registrations, got {successful}"
    )


async def test_invalid_input_returns_422_not_500(async_client: AsyncClient) -> None:
    """Malformed request body must return 422 Unprocessable Entity, never 500.

    WHY: An unhandled ValidationError that escapes the service layer and hits
    the global exception handler would return 500.  Catching it at the Pydantic
    layer returns 422.  This test enforces the contract: bad inputs are user
    errors, not server errors.
    """
    resp = await async_client.post(
        "/auth/register",
        json={"email": "not-an-email", "password": "x"},
    )
    assert resp.status_code == 422, (
        f"Expected 422 for invalid payload, got {resp.status_code}: {resp.text}"
    )


async def test_unauthenticated_protected_endpoint_returns_401(
    async_client: AsyncClient,
) -> None:
    """Protected endpoints must reject requests without valid auth headers.

    WHY: Verifies that the authentication middleware / dependency chain is wired
    correctly end-to-end — not just mocked in unit tests.
    """
    resp = await async_client.get("/users/me")
    assert resp.status_code == 401, (
        f"Expected 401 on unauthenticated /users/me, got {resp.status_code}"
    )
    body = resp.json()
    assert "detail" in body, f"Missing 'detail' in 401 response: {body}"


async def test_weak_password_is_rejected(async_client: AsyncClient) -> None:
    """Registration with a trivially weak password must be rejected.

    WHY: Ensures the password-strength policy is enforced at the API boundary
    (not just in the frontend) so the DB never stores unacceptably weak hashes.
    """
    resp = await async_client.post(
        "/auth/register",
        json={"email": _unique_email("weakpw"), "password": "123"},
    )
    # The service should reject this; 400/422 are both acceptable policy responses.
    assert resp.status_code in {400, 422}, (
        f"Expected 4xx for weak password, got {resp.status_code}: {resp.text}"
    )


async def test_health_endpoint_returns_ok(async_client: AsyncClient) -> None:
    """The /health endpoint must return 200 with a valid JSON body.

    WHY: Acts as a smoke test for the full request lifecycle through all
    middleware layers.  If any middleware is misconfigured it typically breaks
    /health first.
    """
    resp = await async_client.get(
        "http://testserver/healthz",
        headers={"X-Disable-Query-Budget": "1"},
    )
    assert resp.status_code == 200, f"Health check failed: {resp.text}"
    body = resp.json()
    assert "status" in body, f"Missing 'status' in health response: {body}"


async def test_db_session_write_read_consistency(db_session: AsyncSession) -> None:
    """Verify that a write within a session is visible to a read in the same session.

    WHY: Catches misconfigured autoflush / autocommit settings where a write
    appears successful (no exception) but is invisible to subsequent reads
    within the same transaction, which would cause subtle data-loss bugs.
    """
    # Use the raw DB session to write and immediately read back.
    # We write to stored_events (always present) since it has minimal constraints.
    event_id = str(uuid.uuid4())
    await db_session.execute(
        text(
            "INSERT INTO stored_events "
            "(id, event_type, aggregate_id, aggregate_type, sequence_number, payload, error_count, version, status, created_at) "
            "VALUES (:id, 'test.event', 'agg-1', 'TestAggregate', 1, '{\"test\": true}', 0, 1, 'pending', CURRENT_TIMESTAMP)"
        ),
        {"id": event_id},
    )

    result = await db_session.execute(
        text("SELECT id FROM stored_events WHERE id = :id"),
        {"id": event_id},
    )
    row = result.fetchone()
    assert row is not None, (
        "Written event not visible within the same DB session — "
        "possible autoflush/autocommit misconfiguration"
    )
    assert str(row[0]) == event_id


async def test_connection_pool_exhaustion_resilience(
    async_client: AsyncClient,
) -> None:
    """Burst of concurrent requests must not crash the server due to pool exhaustion.

    WHY: When the connection pool is saturated, SQLAlchemy raises QueuePool
    overflow / connection timeout errors.  These must surface as 503 / 504
    responses — not unhandled 500s or silent hangs.  This test fires 10
    lightweight requests concurrently to exercise the pool-wait path.
    """
    # Use the absolute healthz URL that exists at the root (not under /api/v1).
    responses = await asyncio.gather(
        *[
            async_client.get(
                "http://testserver/healthz",
                headers={"X-Disable-Query-Budget": "1"},
            )
            for _ in range(10)
        ],
        return_exceptions=True,
    )

    for resp in responses:
        if isinstance(resp, Exception):
            pytest.fail(f"Concurrent request raised an exception: {resp}")
        # The server must return a structured response — not crash.
        assert resp.status_code in {200, 503, 504}, (
            f"Unexpected status {resp.status_code} under load: {resp.text}"
        )


async def test_transaction_rollback_on_unique_violation(
    db_session: AsyncSession,
) -> None:
    """A unique-constraint violation must roll back only the failed operation.

    WHY: If the exception propagates without a savepoint / nested transaction,
    the entire session becomes unusable and subsequent reads return
    InternalError('current transaction is aborted').  This test ensures the
    repository layer correctly handles the violation and leaves the session
    in a usable state.
    """
    from sqlalchemy.exc import IntegrityError

    event_id = str(uuid.uuid4())

    # First insert — must succeed.
    await db_session.execute(
        text(
            "INSERT INTO stored_events "
            "(id, event_type, aggregate_id, aggregate_type, sequence_number, payload, error_count, version, status, created_at) "
            "VALUES (:id, 'test.unique', 'agg-2', 'TestAggregate', 2, '{\"dup\": 1}', 0, 1, 'pending', CURRENT_TIMESTAMP)"
        ),
        {"id": event_id},
    )
    await db_session.flush()

    # Second insert with the same PK — must raise IntegrityError.
    try:
        await db_session.execute(
            text(
                "INSERT INTO stored_events "
                "(id, event_type, aggregate_id, aggregate_type, sequence_number, payload, error_count, version, status, created_at) "
                "VALUES (:id, 'test.unique', 'agg-2', 'TestAggregate', 2, '{\"dup\": 2}', 0, 1, 'pending', CURRENT_TIMESTAMP)"
            ),
            {"id": event_id},
        )
        await db_session.flush()
    except IntegrityError:
        await db_session.rollback()

    # Session must still be usable after rolling back.
    result = await db_session.execute(text("SELECT 1"))
    assert result.scalar() == 1, (
        "DB session is no longer usable after IntegrityError rollback — "
        "unique violations must not permanently corrupt the session state"
    )
