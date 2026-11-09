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
        ("ws_hub", 120, 401),
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
        "schema": "ue-owned-client-ip-v3",
        "source_sha": _SOURCE,
        "run_id": _RUN,
        "closed": True,
        "sources_verified": True,
        "anonymous": True,
        "source_labels": ["public", "frontend_net"],
        "csrf_ready": [True, True],
        "setup_requests": 2,
        "http_requests": 229,
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


def test_v3_requires_all_four_direct_backend_checks_for_backend_subset() -> None:
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


@pytest.mark.parametrize("allowed_count", [120, 121, 129, 130])
def test_v3_variable_allowed_count_matches_exact_request_count(allowed_count):
    frame = _frame()
    frame["cases"][4]["allowed"] = [401] * allowed_count
    frame["http_requests"] = 229 + allowed_count - 120
    frame["cases"][4]["elapsed_ms"] = min(4999, (allowed_count - 120) * 500)
    frame["elapsed_ms"] = frame["cases"][4]["elapsed_ms"] + 4
    observed = _decode(frame)
    assert observed is not None
    assert evaluate_observations(observed).ws_hub


@pytest.mark.parametrize("schema", ["ue-owned-client-ip-v1", "ue-owned-client-ip-v2"])
def test_legacy_output_schema_rejected_even_with_new_counts(schema):
    frame = _frame()
    frame["schema"] = schema
    assert _decode(frame) is None


@pytest.mark.parametrize(
    "allowed_count,request_count",
    [
        (10, 119),
        (119, 228),
        (131, 240),
        (120, 230),
        (121, 229),
        (130, 238),
        (130, 240),
        (120, True),
    ],
)
def test_forged_ws_lengths_and_request_counts_fail_closed(allowed_count, request_count):
    frame = _frame()
    frame["cases"][4]["allowed"] = [401] * allowed_count
    frame["http_requests"] = request_count
    assert _decode(frame) is None


@pytest.mark.parametrize("index", range(4))
def test_backend_lengths_remain_fixed_with_refill_protocol(index):
    frame = _frame()
    frame["cases"][index]["allowed"].append(422)
    frame["http_requests"] += 1
    assert _decode(frame) is None


@pytest.mark.parametrize(
    "allowed_count,elapsed_ms", [(121, 0), (121, 498), (122, 998), (130, 4499)]
)
def test_forged_refill_allowance_without_elapsed_time_is_rejected(
    allowed_count, elapsed_ms
):
    frame = _frame()
    frame["cases"][4]["allowed"] = [401] * allowed_count
    frame["cases"][4]["elapsed_ms"] = elapsed_ms
    frame["elapsed_ms"] = elapsed_ms + 4
    frame["http_requests"] = 229 + allowed_count - 120
    assert _decode(frame) is None


@pytest.mark.parametrize("elapsed_ms", [499, 500])
def test_refill_bound_conservatively_accounts_for_truncated_milliseconds(elapsed_ms):
    frame = _frame()
    frame["cases"][4]["allowed"] = [401] * 121
    frame["cases"][4]["elapsed_ms"] = elapsed_ms
    frame["elapsed_ms"] = elapsed_ms + 4
    frame["http_requests"] = 230
    assert _decode(frame) is not None
