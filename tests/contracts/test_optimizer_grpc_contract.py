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

    def parse_body(contents: str | bytes | None) -> object:
        assert isinstance(contents, (str, bytes))
        return json.loads(contents)

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

    # Pact owns each native message until the iterator is exhausted.
    interaction_snapshots = [
        (
            str(interaction.description),
            parse_body(interaction.request_contents.contents),
            [
                parse_body(response.contents)
                for response in interaction.response_contents
            ],
        )
        for interaction in pact.interactions(kind="Sync")
    ]
    assert len(interaction_snapshots) == 1
    [(description, request, responses)] = interaction_snapshots
    assert description == "a gRPC request for DetectConflicts"

    def expected_type_matcher(value: object) -> dict[str, object]:
        return {
            "pact:matcher:type": "type",
            "value": value,
            "min": None,
            "max": None,
        }

    expected_event = {
        "weekday": expected_type_matcher("Monday"),
        "start_time": {
            "seconds": expected_type_matcher(1710000000),
            "nanos": 0,
        },
        "end_time": {
            "seconds": expected_type_matcher(1710003600),
            "nanos": 0,
        },
        "parity": expected_type_matcher("both"),
        "room": expected_type_matcher("404"),
        "teacher": expected_type_matcher("Dr. Smith"),
    }
    expected_request = {
        "target": expected_event,
        "existing": [expected_event],
    }
    expected_response = {"conflicts": [expected_event]}

    assert request == expected_request
    assert len(responses) == 1
    assert responses[0] == expected_response
