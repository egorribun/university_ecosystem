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
        .will_respond_with(status=200, body={"status": match.like("ok")})
    )
