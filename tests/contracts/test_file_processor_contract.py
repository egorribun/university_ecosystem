"""Wave 2 / Contract 2.1 — Consumer-Driven Contract Tests for the
file-processor Temporal workflow → Python backend callback boundary.

Consumer: university-backend  (Python FastAPI — receives the callback)
Provider: file-processor       (Go Temporal worker — sends the callback)

Flow
----
1. After the ResizeImageActivity completes, the Go worker POSTs a
   ``ProcessResult`` JSON body to ``job.callback_url`` (workflow.go).
2. The Python backend validates the payload and marks the upload record as
   processed/failed.

Schema (from services/file-processor/internal/workflow/workflow.go)
---------------------------------------------------------------------
.. code-block:: json

    {
      "job_id":     "<UUID or opaque string>",
      "success":    <boolean>,
      "dest_key":   "<MinIO object key, omitempty>",
      "error":      "<error message, omitempty>",
      "duration_ms": <non-negative integer>
    }

Why this matters
----------------
The Go struct uses ``json:\"omitempty\"`` on ``dest_key`` and ``error``.
If someone renames ``job_id`` → ``jobId`` or ``duration_ms`` → ``durationMs``
to match Go idiomatic JSON, every Python upload flow silently breaks.
This contract catches that drift at CI time.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Pact availability guard (same pattern as test_ws_hub_contract.py)
# ---------------------------------------------------------------------------

pact_lib = None
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

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PACT_DIR = Path(__file__).parent / "pacts"

CONSUMER_NAME = "university-backend"
PROVIDER_NAME = "file-processor"

# Representative sample values aligned with Go's ProcessResult struct
_SAMPLE_JOB_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
_SAMPLE_DEST_KEY = "uploads/processed/resized_image.jpg"
_SAMPLE_DURATION_MS = 423


# ---------------------------------------------------------------------------
# Python consumer verifier
# ---------------------------------------------------------------------------


def _backend_callback_handler(
    msg: str | bytes | None, context: dict[str, Any]
) -> dict[str, Any]:
    """Simulate the Python backend's file-processor callback receiver.

    Mirrors the validation a Python endpoint must perform on a
    ``ProcessResult`` JSON body:
    - ``job_id``      must be a non-empty string
    - ``success``     must be a boolean
    - ``duration_ms`` must be a non-negative integer
    - ``dest_key``    is optional (omitempty for success=True results)
    - ``error``       is optional (omitempty for success=True results)

    We deliberately do NOT enforce ``dest_key`` presence here —
    on failure, Go omits it (omitempty).  The contract verifies both
    the success and failure message shapes through separate interactions.
    """
    assert msg is not None, "Callback body must not be None"

    payload: dict[str, Any] = json.loads(msg)
    assert isinstance(payload, dict), "Payload must be a JSON object"

    # Required fields
    assert "job_id" in payload, "Missing required field: 'job_id'"
    assert isinstance(payload["job_id"], str) and payload["job_id"], (
        "job_id must be a non-empty string"
    )

    assert "success" in payload, "Missing required field: 'success'"
    assert isinstance(payload["success"], bool), "success must be a boolean"

    assert "duration_ms" in payload, "Missing required field: 'duration_ms'"
    assert isinstance(payload["duration_ms"], int) and payload["duration_ms"] >= 0, (
        f"duration_ms must be a non-negative integer, got {payload['duration_ms']!r}"
    )

    # Optional fields type-check (only validate if present)
    if "dest_key" in payload:
        assert isinstance(payload["dest_key"], str), (
            "dest_key must be a string when present"
        )

    if "error" in payload:
        assert isinstance(payload["error"], str), "error must be a string when present"

    return payload


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pact() -> Pact:
    """Session-scoped Pact instance. Writes the contract file on teardown."""
    PACT_DIR.mkdir(parents=True, exist_ok=True)
    p = Pact(CONSUMER_NAME, PROVIDER_NAME)
    yield p.with_specification("V4")
    p.write_file(PACT_DIR, overwrite=True)


# ---------------------------------------------------------------------------
# Contract interaction tests
# ---------------------------------------------------------------------------


def test_file_processing_success_callback_contract(pact: Pact) -> None:
    """Contract: Python backend expects this schema for a successful ProcessResult.

    Schema (success path):
    ~~~~~~~~~~~~~~~~~~~~~~
    .. code-block:: json

        {
          "job_id":     "<non-empty string>",
          "success":    true,
          "dest_key":   "<MinIO object key string>",
          "duration_ms": <non-negative integer>
        }

    Note: ``error`` is omitted when success=True (Go ``omitempty``).
    """
    (
        pact.upon_receiving("a successful file processing result", "Async")
        .with_body(
            {
                "job_id": match.like(_SAMPLE_JOB_ID),
                "success": match.like(True),
                "dest_key": match.like(_SAMPLE_DEST_KEY),
                "duration_ms": match.like(_SAMPLE_DURATION_MS),
            },
            "application/json",
        )
        .with_metadata({"nats_subject": "file.processed"})
    )
    pact.verify(_backend_callback_handler, "Async")


def test_file_processing_failure_callback_contract(pact: Pact) -> None:
    """Contract: Python backend expects this schema for a failed ProcessResult.

    Schema (failure path):
    ~~~~~~~~~~~~~~~~~~~~~~
    .. code-block:: json

        {
          "job_id":     "<non-empty string>",
          "success":    false,
          "error":      "<error message string>",
          "duration_ms": <non-negative integer>
        }

    Note: ``dest_key`` is omitted when success=False (Go ``omitempty``).
    The error field MUST be present and non-empty on failure.
    """
    (
        pact.upon_receiving("a failed file processing result", "Async")
        .with_body(
            {
                "job_id": match.like(_SAMPLE_JOB_ID),
                "success": match.like(False),
                "error": match.like("image decode failed: unexpected EOF"),
                "duration_ms": match.like(_SAMPLE_DURATION_MS),
            },
            "application/json",
        )
        .with_metadata({"nats_subject": "file.processed"})
    )
    pact.verify(_backend_callback_handler, "Async")
