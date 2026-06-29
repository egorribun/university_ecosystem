"""Consumer-Driven Contract Tests for Backend <-> File-Processor gRPC.
Consumer: Backend
Provider: File-Processor
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
CONSUMER_NAME = "university-backend"
PROVIDER_NAME = "file-processor"

@pytest.fixture(scope="module")
def pact() -> Pact:
    PACT_DIR.mkdir(parents=True, exist_ok=True)
    p = Pact(CONSUMER_NAME, PROVIDER_NAME)
    # Use V4 for gRPC / Synchronous Messages
    yield p.with_specification("V4")
    p.write_file(PACT_DIR, overwrite=True)

def test_process_file_grpc_contract(pact: Pact) -> None:
    """Contract: Backend expects ProcessFile to return ProcessFileResponse."""
    (
        pact.upon_receiving("a gRPC request for ProcessFile", "Synchronous/Messages")
        .with_request(
            {
                "id": match.like("uuid"),
                "type": match.like("resize"),
                "source_key": match.like("uploads/raw/img.jpg"),
                "dest_key": match.like("uploads/processed/img.jpg"),
                "options": {"width": "800"},
                "callback_url": match.like("http://backend/callback"),
            },
            "application/grpc"
        )
        .with_body(
            {
                "job_id": match.like("uuid"),
                "success": match.like(True),
                "dest_key": match.like("uploads/processed/img.jpg"),
                "duration_ms": match.like(100)
            },
            "application/grpc"
        )
    )
