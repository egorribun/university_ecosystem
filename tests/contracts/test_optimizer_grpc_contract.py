"""Consumer-Driven Contract Tests for Backend <-> Optimizer gRPC.
Consumer: Backend
Provider: Optimizer
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
PROVIDER_NAME = "optimizer-service"


@pytest.fixture(scope="module")
def pact() -> Pact:
    PACT_DIR.mkdir(parents=True, exist_ok=True)
    p = Pact(CONSUMER_NAME, PROVIDER_NAME)
    yield p.with_specification("V4")
    p.write_file(PACT_DIR, overwrite=True)


def test_detect_conflicts_grpc_contract(pact: Pact) -> None:
    """Contract: Backend expects DetectConflicts to return conflicts list."""
    (
        pact.upon_receiving("a gRPC request for DetectConflicts", "Sync")
        .with_body(
            {
                "target": {
                    "weekday": match.like("Monday"),
                    "start_time": {"seconds": match.like(1710000000), "nanos": 0},
                    "end_time": {"seconds": match.like(1710003600), "nanos": 0},
                    "parity": match.like("both"),
                    "room": match.like("404"),
                    "teacher": match.like("Dr. Smith"),
                },
                "existing": [
                    {
                        "weekday": match.like("Monday"),
                        "start_time": {"seconds": match.like(1710000000), "nanos": 0},
                        "end_time": {"seconds": match.like(1710003600), "nanos": 0},
                        "parity": match.like("both"),
                        "room": match.like("404"),
                        "teacher": match.like("Dr. Smith"),
                    }
                ],
            },
            "application/grpc",
        )
        .will_respond_with()
        .with_body(
            {
                "conflicts": [
                    {
                        "weekday": match.like("Monday"),
                        "start_time": {"seconds": match.like(1710000000), "nanos": 0},
                        "end_time": {"seconds": match.like(1710003600), "nanos": 0},
                        "parity": match.like("both"),
                        "room": match.like("404"),
                        "teacher": match.like("Dr. Smith"),
                    }
                ]
            },
            "application/grpc",
        )
    )
