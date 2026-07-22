"""Consumer-driven Pact contract for the gateway -> backend HTTP boundary.

The gateway forwards backend HTTP responses to its consumers.  This contract
intentionally uses the backend's dependency-free liveness endpoint so provider
replay can run against the real FastAPI application without seeded users,
rate-limit windows, or a database fixture.
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
    pytestmark = pytest.mark.skip(
        reason="pact-python is not installed or failed to load DLL (e.g. on Windows)"
    )

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


def test_gateway_backend_liveness_contract(pact: Pact) -> None:
    """The gateway requires a stable liveness response from the backend."""
    (
        pact.upon_receiving("a backend liveness request")
        .given("Backend process is alive")
        .with_request(method="GET", path="/health/live")
        .will_respond_with(200)
        .with_headers(
            {
                "content-type": match.regex(
                    "application/json", regex=r"^application/json(?:;.*)?$"
                )
            }
        )
        .with_body({"status": match.like("alive")})
    )
