"""Consumer-Driven Contract Tests for the files.process NATS message boundary.

Consumer: file-processor
Provider: university-backend (or ws-hub)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

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
CONSUMER_NAME = "file-processor"
PROVIDER_NAME = "university-backend"

@pytest.fixture(scope="module")
def pact() -> Pact:
    PACT_DIR.mkdir(parents=True, exist_ok=True)
    p = Pact(CONSUMER_NAME, PROVIDER_NAME)
    yield p.with_specification("V4")
    p.write_file(PACT_DIR, overwrite=True)

def _files_process_handler(msg: str | bytes | None, context: dict[str, Any]) -> dict[str, Any]:
    """Simulate the file-processor NATS subscriber for files.process."""
    assert msg is not None, "Message body must not be None"
    payload: dict[str, Any] = json.loads(msg)
    assert isinstance(payload, dict), "Payload must be a JSON object"

    assert "id" in payload, "Missing required field: 'id'"
    assert "type" in payload, "Missing required field: 'type'"
    assert "source_key" in payload, "Missing required field: 'source_key'"
    assert "dest_key" in payload, "Missing required field: 'dest_key'"

    return payload

def test_files_process_event_contract(pact: Pact) -> None:
    """Contract: file-processor expects ProcessJob schema."""
    (
        pact.upon_receiving("a file process event", "Async")
        .with_body(
            {
                "id": match.like("uuid"),
                "type": match.like("resize"),
                "source_key": match.like("uploads/raw/img.jpg"),
                "dest_key": match.like("uploads/processed/img.jpg"),
                "options": match.like({"width": 800}),
                "callback_url": match.like("http://backend/callback"),
            },
            "application/json",
        )
        .with_metadata({"nats_subject": "files.process"})
    )
    pact.verify(_files_process_handler, "Async")
