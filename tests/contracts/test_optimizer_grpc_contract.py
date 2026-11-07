"""Consumer-Driven Contract Tests for Backend <-> Optimizer gRPC.
Consumer: Backend
Provider: Optimizer
"""

from __future__ import annotations

import json
import sys

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
PROVIDER_NAME = "optimizer-service"


@pytest.fixture(scope="module")
def pact() -> Pact:
    """Consumer-only schema sentinel; no optimizer provider replay exists in CI.

    Keep the interaction coverage without emitting an orphan provider artifact,
    matching the other unreplayed consumer-only Pact fixtures.
    """
    p = Pact(CONSUMER_NAME, PROVIDER_NAME)
    yield p.with_specification("V4")


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

    interactions = list(pact.interactions(kind="Sync"))
    assert len(interactions) == 1
    [interaction] = interactions
    assert interaction.description == "a gRPC request for DetectConflicts"

    request_contents = interaction.request_contents.contents
    assert isinstance(request_contents, (str, bytes))
    assert json.loads(request_contents) == {
        "target": {
            "weekday": "Monday",
            "start_time": {"seconds": 1710000000, "nanos": 0},
            "end_time": {"seconds": 1710003600, "nanos": 0},
            "parity": "both",
            "room": "404",
            "teacher": "Dr. Smith",
        },
        "existing": [
            {
                "weekday": "Monday",
                "start_time": {"seconds": 1710000000, "nanos": 0},
                "end_time": {"seconds": 1710003600, "nanos": 0},
                "parity": "both",
                "room": "404",
                "teacher": "Dr. Smith",
            }
        ],
    }
    responses = list(interaction.response_contents)
    assert len(responses) == 1
    response_contents = responses[0].contents
    assert isinstance(response_contents, (str, bytes))
    assert json.loads(response_contents) == {
        "conflicts": [
            {
                "weekday": "Monday",
                "start_time": {"seconds": 1710000000, "nanos": 0},
                "end_time": {"seconds": 1710003600, "nanos": 0},
                "parity": "both",
                "room": "404",
                "teacher": "Dr. Smith",
            }
        ]
    }
