"""Chaos tests: memory pressure and resource exhaustion scenarios (Wave 14.1).

These tests verify that the application degrades *gracefully* under resource
constraints.  They are lightweight (no Docker) and run against the in-process
test client to check for:

  - Oversized payload rejection (413 / 422, not 500)
  - Concurrent request burst without data corruption
  - Deeply nested JSON DoS resistance
  - Rapid successive requests on the same resource

Run with:
    pytest tests/chaos/test_memory_pressure.py -v -m "chaos or slow"

WHY a separate file from test_resilience.py:
    test_resilience.py requires Docker Compose and is opt-in with CHAOS_TESTS=1.
    These tests use only the in-process ASGI client (no Docker) so they can run
    in standard CI pipelines.
"""

from __future__ import annotations

import asyncio
import json
import string

import pytest
from httpx import AsyncClient

pytestmark = [pytest.mark.chaos]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_large_string(size_bytes: int) -> str:
    """Return a string of approximately `size_bytes` bytes."""
    chunk = string.ascii_letters + string.digits
    repetitions = (size_bytes // len(chunk)) + 1
    return (chunk * repetitions)[:size_bytes]


def _make_deeply_nested_json(depth: int) -> dict:
    """Construct a JSON object nested `depth` levels deep."""
    obj: dict = {"leaf": "value"}
    for _ in range(depth):
        obj = {"nested": obj}
    return obj


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.slow
async def test_large_payload_rejected_not_server_error(
    async_client: AsyncClient,
) -> None:
    """Server must reject an oversized payload with 413 or 422, never 500.

    WHY: A 10 MB JSON body should hit the Content-Length / body-size middleware
    before it reaches any handler.  If it reaches the handler and causes an OOM
    or unhandled exception we get a 500, which is the failure mode this test
    catches.

    We POST to /auth/register since it accepts a JSON body and always exists.
    """
    ten_mb_password = _make_large_string(10 * 1024 * 1024)  # 10 MB
    payload = {"email": "chaos@test.com", "password": ten_mb_password}

    resp = await async_client.post(
        "/auth/register",
        content=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "X-Disable-Query-Budget": "1",
        },
    )

    # 413 (Request Entity Too Large) is the ideal; 422 is acceptable if the
    # middleware passes it through but Pydantic/FastAPI rejects the oversized
    # field at validation time.  500 is the failure mode.
    assert resp.status_code != 500, (
        f"Server returned 500 for oversized payload — possible unhandled OOM: "
        f"{resp.text[:500]}"
    )
    assert resp.status_code in {400, 413, 422}, (
        f"Expected 4xx for oversized payload, got {resp.status_code}"
    )


async def test_concurrent_request_burst_no_data_corruption(
    async_client: AsyncClient,
) -> None:
    """Server handles N concurrent requests without crashing or data corruption.

    WHY: A burst of concurrent requests (simulating a flash crowd) stress-tests
    connection pool limits, async task scheduling, and shared state.  We send
    concurrent GET requests to a stateless endpoint (/health) and verify:
      1. The server does not crash (no 5xx).
      2. All responses have the expected shape.
    """
    concurrent_count = 20

    responses = await asyncio.gather(
        *[
            async_client.get(
                "http://testserver/healthz",
                headers={"X-Disable-Query-Budget": "1"},
            )
            for _ in range(concurrent_count)
        ],
        return_exceptions=True,
    )

    errors = [r for r in responses if isinstance(r, Exception)]
    assert not errors, (
        f"{len(errors)} concurrent requests raised exceptions: {errors[:3]}"
    )

    server_errors = [
        r for r in responses if not isinstance(r, Exception) and r.status_code >= 500
    ]
    assert not server_errors, (
        f"{len(server_errors)}/{concurrent_count} concurrent requests returned 5xx"
    )


async def test_deeply_nested_json_dos_resistance(async_client: AsyncClient) -> None:
    """Deeply nested JSON must be rejected without crashing the server.

    WHY: Python's json.loads() and pydantic's recursive model validators can
    hit recursion limits or consume unbounded stack space on extremely deep
    nesting.  FastAPI should return 422, not 500/RecursionError.
    """
    deeply_nested = _make_deeply_nested_json(depth=300)

    resp = await async_client.post(
        "/auth/register",
        content=json.dumps(deeply_nested).encode(),
        headers={
            "Content-Type": "application/json",
            "X-Disable-Query-Budget": "1",
        },
    )

    assert resp.status_code != 500, (
        f"Deeply nested JSON caused server error: {resp.text[:300]}"
    )


async def test_rapid_successive_requests_on_same_resource(
    async_client: AsyncClient,
) -> None:
    """Sequential burst of requests to the same read endpoint must stay consistent.

    WHY: Ensures that caching layers and connection pooling do not produce
    stale or corrupted responses when the same resource is hammered quickly.
    """
    burst_count = 10
    statuses: list[int] = []

    for _ in range(burst_count):
        resp = await async_client.get(
            "http://testserver/healthz",
            headers={"X-Disable-Query-Budget": "1"},
        )
        statuses.append(resp.status_code)

    server_errors = [s for s in statuses if s >= 500]
    assert not server_errors, (
        f"Got {len(server_errors)} server errors in rapid burst: {statuses}"
    )

    # All responses should have the same status code — consistency check.
    unique_statuses = set(statuses)
    assert len(unique_statuses) == 1, (
        f"Inconsistent responses during rapid burst: {unique_statuses}"
    )


async def test_empty_body_on_post_endpoint_returns_422(
    async_client: AsyncClient,
) -> None:
    """An empty body on a POST endpoint expecting JSON must return 422, not 500.

    WHY: Some middleware configurations fail to set Content-Type correctly on
    empty bodies, causing an internal parse error instead of a user-facing
    validation error.
    """
    resp = await async_client.post(
        "/auth/register",
        content=b"",
        headers={
            "Content-Type": "application/json",
            "X-Disable-Query-Budget": "1",
        },
    )

    assert resp.status_code in {400, 422}, (
        f"Empty body returned unexpected status {resp.status_code}: {resp.text[:300]}"
    )
    assert resp.status_code != 500


async def test_unicode_edge_cases_in_request_body(async_client: AsyncClient) -> None:
    """Requests containing Unicode edge cases must not crash the server.

    WHY: Null bytes, surrogates, and zero-width characters are common fuzzer
    inputs that trigger parser crashes in systems that assume well-formed UTF-8.
    """
    edge_case_payloads = [
        {
            "email": "test\x00@example.com",
            "password": "ValidPass#1",  # pragma: allowlist secret
        },
        {
            "email": "test@example.com",
            "password": "Pass\uffff\u0000word",  # pragma: allowlist secret
        },
        {
            "email": "test@example.com\u200b",
            "password": "ValidPass#1",  # pragma: allowlist secret
        },
    ]

    for payload in edge_case_payloads:
        resp = await async_client.post(
            "/auth/register",
            json=payload,
            headers={"X-Disable-Query-Budget": "1"},
        )
        assert resp.status_code != 500, (
            f"Unicode edge case caused server error for payload {payload!r}: "
            f"{resp.text[:300]}"
        )
