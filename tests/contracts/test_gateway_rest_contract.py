"""Consumer-driven Pact contract for the gateway -> backend HTTP boundary.

The gateway forwards backend HTTP responses to its consumers.  This contract
intentionally uses the backend's dependency-free liveness endpoint so provider
replay can run against the real FastAPI application without seeded users,
rate-limit windows, or a database fixture.
"""

from __future__ import annotations

import json
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

CONSUMER_NAME = "gateway"
PROVIDER_NAME = "university-backend"


@pytest.fixture(scope="module")
def pact(pact_output_dir: Path) -> Pact:
    p = Pact(CONSUMER_NAME, PROVIDER_NAME)
    yield p.with_specification("V4")
    p.write_file(pact_output_dir, overwrite=False)


def test_gateway_backend_liveness_contract(pact: Pact, tmp_path: Path) -> None:
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

    # Read the contract emitted by Pact's supported writer and verify the
    # actual HTTP interaction, rather than merely constructing its DSL chain.
    inspection_dir = tmp_path / "pact-inspection"
    pact.write_file(inspection_dir, overwrite=False)
    [pact_path] = list(inspection_dir.glob("*.json"))
    contract = json.loads(pact_path.read_text(encoding="utf-8"))

    assert contract["consumer"]["name"] == CONSUMER_NAME
    assert contract["provider"]["name"] == PROVIDER_NAME
    [interaction] = contract["interactions"]
    assert interaction["description"] == "a backend liveness request"
    assert interaction["type"] == "Synchronous/HTTP"
    assert interaction["providerStates"] == [{"name": "Backend process is alive"}]
    assert interaction["request"]["method"] == "GET"
    assert interaction["request"]["path"] == "/health/live"

    response = interaction["response"]
    assert response["status"] == 200
    assert response["body"]["content"] == {"status": "alive"}
    assert response["body"]["contentType"] == "application/json"
    assert any(
        name.casefold() == "content-type" and values == ["application/json"]
        for name, values in response["headers"].items()
    )
    assert response["matchingRules"]["body"]["$.status"]["matchers"] == [
        {"match": "type"}
    ]
    assert response["matchingRules"]["header"]["content-type"]["matchers"] == [
        {"match": "regex", "regex": r"^application/json(?:;.*)?$"}
    ]
