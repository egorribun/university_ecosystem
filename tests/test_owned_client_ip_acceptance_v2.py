"""Bounded decoder controls for direct-backend spoof observations.

These are offline protocol tests, not proof of an owned deployment.
"""

from __future__ import annotations

import json

import pytest

from scripts.owned_client_ip_acceptance import (
    decode_observations,
    evaluate_observations,
)
from scripts.owned_nats_process import (
    LocalCleanup,
    PrivateProcessResult,
    ProcessOutcome,
)

_SOURCE = "a" * 40
_RUN = "b" * 64


def _frame() -> dict[str, object]:
    cases = []
    for name, count, status in (
        ("login", 60, 422),
        ("register", 5, 422),
        ("mfa", 5, 422),
        ("forgot", 3, 422),
        ("ws_hub", 10, 401),
    ):
        cases.append(
            {
                "case": name,
                "allowed": [status] * count,
                "blocked": 429,
                "other_client": status,
                "spoofed": [429, 429, 429],
                "direct_untrusted": 429,
                "backend_direct_untrusted": None if name == "ws_hub" else 429,
                "elapsed_ms": 1,
            }
        )
    return {
        "schema": "ue-owned-client-ip-v2",
        "source_sha": _SOURCE,
        "run_id": _RUN,
        "closed": True,
        "sources_verified": True,
        "anonymous": True,
        "source_labels": ["public", "frontend_net"],
        "csrf_ready": [True, True],
        "setup_requests": 2,
        "http_requests": 119,
        "elapsed_ms": 20,
        "cases": cases,
    }


def _decode(frame: dict[str, object]):
    raw = (json.dumps(frame, separators=(",", ":")) + "\n").encode()
    return decode_observations(
        PrivateProcessResult(
            ProcessOutcome.EXITED, 0, raw, b"", LocalCleanup.CONFIRMED
        ),
        expected_source_sha=_SOURCE,
        expected_run_id=_RUN,
        now_ms=1000,
        deadline_ms=121000,
    )


def test_v2_requires_all_four_direct_backend_checks_for_backend_subset() -> None:
    observed = _decode(_frame())
    assert observed is not None
    verdict = evaluate_observations(observed)
    assert (verdict.backend, verdict.ws_hub) == (True, True)
    assert (verdict.gateway, verdict.deployment) == ("not_assessed", "not_assessed")


@pytest.mark.parametrize("index", range(4))
def test_direct_backend_spoof_reaching_handler_fails_only_backend(index: int) -> None:
    frame = _frame()
    cases = frame["cases"]
    assert isinstance(cases, list)
    cases[index]["backend_direct_untrusted"] = 422
    observed = _decode(frame)
    assert observed is not None
    verdict = evaluate_observations(observed)
    assert (verdict.backend, verdict.ws_hub) == (False, True)


@pytest.mark.parametrize(
    "defect", ["legacy_schema", "legacy_count", "missing", "ws_status"]
)
def test_incomplete_or_legacy_direct_backend_receipt_is_rejected(defect: str) -> None:
    frame = _frame()
    cases = frame["cases"]
    assert isinstance(cases, list)
    if defect == "legacy_schema":
        frame["schema"] = "ue-owned-client-ip-v1"
    elif defect == "legacy_count":
        frame["http_requests"] = 115
    elif defect == "missing":
        del cases[0]["backend_direct_untrusted"]
    else:
        cases[4]["backend_direct_untrusted"] = 429
    assert _decode(frame) is None
