"""Consumer-Driven Contract Tests for Backend <-> File-Processor gRPC.
Consumer: Backend
Provider: File-Processor
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
    pytestmark = pytest.mark.skip(reason="pact-python is not installed")

    class DummyPact:
        pass

    Pact = DummyPact
    match = None
else:
    Pact = pact_lib.Pact
    match = pact_lib.match

CONSUMER_NAME = "university-backend"
PROVIDER_NAME = "file-processor"


@pytest.fixture(scope="module")
def pact(pact_output_dir: Path) -> Pact:
    p = Pact(CONSUMER_NAME, PROVIDER_NAME)
    # Use V4 for gRPC / Synchronous Messages
    yield p.with_specification("V4")
    p.write_file(pact_output_dir, overwrite=False)


def test_process_file_grpc_contract(pact: Pact, tmp_path: Path) -> None:
    """Contract: Backend expects ProcessFile to return ProcessFileResponse."""
    (
        pact.upon_receiving("a gRPC request for ProcessFile", "Sync")
        .with_body(
            {
                "id": match.like("uuid"),
                "type": match.like("image_resize"),
                "source_key": match.like("uploads/raw/img.jpg"),
                "dest_key": match.like("uploads/processed/img.jpg"),
                "options": {"width": "800"},
                "callback_url": match.like("http://backend/callback"),
            },
            # Pact V4 message bodies are JSON-encoded representations of the
            # protobuf payload. `application/grpc` makes the verifier compare
            # matcher JSON as opaque bytes instead of applying the matchers.
            "application/json",
        )
        .will_respond_with()
        .with_body(
            {
                "job_id": match.like("550e8400-e29b-41d4-a716-446655440002"),
                "success": match.like(True),
                # ProcessFile starts the Temporal workflow and returns its run
                # identifier immediately; processing output is delivered by the
                # asynchronous callback contract, not this gRPC response.
                "dest_key": match.like(""),
                "duration_ms": match.like(0),
            },
            "application/json",
        )
    )

    # Inspect the serialized Pact produced by the real Pact API. This is a
    # consumer contract assertion; it does not claim provider replay occurred.
    inspection_dir = tmp_path / "pact-inspection"
    pact.write_file(inspection_dir, overwrite=False)
    [pact_path] = list(inspection_dir.glob("*.json"))
    contract = json.loads(pact_path.read_text(encoding="utf-8"))

    assert contract["consumer"]["name"] == CONSUMER_NAME
    assert contract["provider"]["name"] == PROVIDER_NAME
    [interaction] = contract["interactions"]
    assert interaction["description"] == "a gRPC request for ProcessFile"
    assert interaction["type"] == "Synchronous/Messages"

    request = interaction["request"]
    assert request["contents"]["content"] == {
        "id": "uuid",
        "type": "image_resize",
        "source_key": "uploads/raw/img.jpg",
        "dest_key": "uploads/processed/img.jpg",
        "options": {"width": "800"},
        "callback_url": "http://backend/callback",
    }
    assert request["contents"]["contentType"] == "application/json"
    request_rules = request["matchingRules"]["body"]
    assert set(request_rules) == {
        "$.id",
        "$.type",
        "$.source_key",
        "$.dest_key",
        "$.callback_url",
    }
    assert all(
        rule["matchers"] == [{"match": "type"}] for rule in request_rules.values()
    )

    [response] = interaction["response"]
    assert response["contents"]["content"] == {
        "job_id": "550e8400-e29b-41d4-a716-446655440002",
        "success": True,
        "dest_key": "",
        "duration_ms": 0,
    }
    assert response["contents"]["contentType"] == "application/json"
    response_rules = response["matchingRules"]["body"]
    assert set(response_rules) == {
        "$.job_id",
        "$.success",
        "$.dest_key",
        "$.duration_ms",
    }
    assert all(
        rule["matchers"] == [{"match": "type"}] for rule in response_rules.values()
    )
