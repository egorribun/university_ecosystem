"""Consumer-Driven Contract Tests for Backend <-> Gateway REST.
Consumer: Gateway
Provider: Backend
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pact_lib = None
if sys.platform != "win32":
    try:
        import pact

        pact_lib = pact
    except ImportError:
        pass

if pact_lib is None:
    pytestmark = pytest.mark.skip(reason="pact-python is not installed")

    class DummyPact:
        pass

    Pact = DummyPact
    match = None
else:
    Pact = pact_lib.Pact
    match = pact_lib.match

PACT_DIR = Path(__file__).parent / "pacts"
CONSUMER_NAME = "gateway"
PROVIDER_NAME = "university-backend"


@pytest.fixture(scope="module")
def pact() -> Pact:
    PACT_DIR.mkdir(parents=True, exist_ok=True)
    p = Pact(CONSUMER_NAME, PROVIDER_NAME)
    yield p.with_specification("V4")
    p.write_file(PACT_DIR, overwrite=True)


def test_gateway_rest_contract(pact: Pact) -> None:
    """Contract: Gateway expects Backend to respond to a basic health/status request."""
    (
        pact.upon_receiving("a request to /health")
        .given("Backend is running")
        .with_request(method="GET", path="/health")
        .will_respond_with(200)
        .with_body({"status": match.like("ok")})
    )


def test_gateway_rest_unauthorized_contract(pact: Pact) -> None:
    """Contract: Gateway expects 401 Unauthorized for unauthenticated calls to protected routes."""
    (
        pact.upon_receiving("a request to a protected endpoint without auth header")
        .given("Backend is running")
        .with_request(method="GET", path="/api/v1/auth/me")
        .will_respond_with(401)
        .with_body({"detail": match.like("Not authenticated")})
    )


def test_gateway_rest_forbidden_contract(pact: Pact) -> None:
    """Contract: Gateway expects 403 Forbidden when a student performs admin actions."""
    (
        pact.upon_receiving("a request to an admin route with student credentials")
        .given("Backend is running")
        .with_request(method="POST", path="/api/v1/admin/users")
        .with_headers({"Authorization": "Bearer student-token"})
        .will_respond_with(403)
        .with_body({"detail": match.like("Operation not permitted")})
    )


def test_gateway_rest_rate_limited_contract(pact: Pact) -> None:
    """Contract: Gateway expects 429 Too Many Requests when rate limit threshold is crossed."""
    (
        pact.upon_receiving("too many requests to news endpoint")
        .given("Backend is running")
        .with_request(method="GET", path="/api/v1/news")
        .will_respond_with(429)
        .with_body({"detail": match.like("Rate limit exceeded")})
    )


def test_gateway_rest_service_unavailable_contract(pact: Pact) -> None:
    """Contract: Gateway expects 503 Service Unavailable when backend is in maintenance."""
    (
        pact.upon_receiving("a request during backend database outage")
        .given("Backend is database-down")
        .with_request(method="GET", path="/api/v1/schedule")
        .will_respond_with(503)
        .with_body({"detail": match.like("Service temporarily unavailable")})
    )
