"""The baseline proof source rebind is one-to-one and rejects unrelated drift."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from tests import test_verify_secrets_baseline as verifier_tests

ROOT = Path(__file__).resolve().parents[1]
PROOF = "tests/integration/test_mvp_baseline_schema_equivalence.py"
AUDIT = "tests/integration/test_aud433_notifications_baseline_partition.py"


def test_baseline_source_and_policy_rebind_preserve_exact_predecessors() -> None:
    proof = (ROOT / PROOF).read_bytes()
    audit = (ROOT / AUDIT).read_bytes()
    for path, source in ((PROOF, proof), (AUDIT, audit)):
        previous = verifier_tests._baseline_source_predecessor(path, source)
        assert (
            hashlib.sha256(previous).digest()
            == verifier_tests._AUD380_CURRENT_DELTA_SOURCE_SHA256[path]
        )
        assert verifier_tests._baseline_source_predecessor(path, previous) == previous
    assert audit.count(hashlib.sha256(proof).hexdigest().encode("ascii")) == 1

    policy = json.loads(
        (ROOT / "quality/security-false-positive-dispositions.json").read_bytes()
    )
    assert len(policy["records"]) == 524
    assert policy["records"][483]["identity"]["hashed_secret_bytes"] == list(
        hashlib.sha1(
            hashlib.sha256(proof).hexdigest().encode("ascii"), usedforsecurity=False
        ).digest()
    )
    previous_policy = verifier_tests._baseline_policy_predecessor(policy)
    previous_row = copy.deepcopy(verifier_tests._AUD380_PENDING_OWNER_RECORDS[14])
    previous_row["approval_status"] = "approved"
    assert previous_policy["records"][483] == previous_row
    expected = copy.deepcopy(policy)
    expected["records"][483] = previous_row
    assert previous_policy == expected
    assert (
        verifier_tests._baseline_policy_predecessor(previous_policy) == previous_policy
    )


@pytest.mark.parametrize("path", [PROOF, AUDIT])
def test_baseline_source_projection_rejects_unrelated_mutation(path: str) -> None:
    source = (ROOT / path).read_bytes() + b"\n# unrelated mutation\n"
    with pytest.raises(AssertionError, match="conditional disposition source"):
        verifier_tests._baseline_source_predecessor(path, source)


def test_baseline_source_projection_rejects_modified_extractor() -> None:
    source = (ROOT / PROOF).read_bytes()
    assert source.count(b'"--first-parent"') == 1
    changed = source.replace(b'"--first-parent"', b'"--all"', 1)
    with pytest.raises(AssertionError, match="conditional disposition source"):
        verifier_tests._baseline_source_predecessor(PROOF, changed)


@pytest.mark.parametrize("field", ["owner", "evidence", "expires_on"])
def test_baseline_policy_projection_rejects_approval_metadata_changes(
    field: str,
) -> None:
    policy = json.loads(
        (ROOT / "quality/security-false-positive-dispositions.json").read_bytes()
    )
    policy["records"][483][field] += " changed"
    with pytest.raises(AssertionError, match="baseline proof disposition"):
        verifier_tests._baseline_policy_predecessor(policy)


@pytest.mark.parametrize("field", ["path", "type", "hashed_secret_bytes"])
def test_baseline_policy_projection_rejects_identity_changes(field: str) -> None:
    policy = json.loads(
        (ROOT / "quality/security-false-positive-dispositions.json").read_bytes()
    )
    identity = policy["records"][483]["identity"]
    if field == "hashed_secret_bytes":
        identity[field][0] ^= 1
    else:
        identity[field] += " changed"
    with pytest.raises(AssertionError, match="baseline proof disposition"):
        verifier_tests._baseline_policy_predecessor(policy)


def test_baseline_then_visual_policy_projection_preserves_both_predecessors() -> None:
    policy = json.loads(
        (ROOT / "quality/security-false-positive-dispositions.json").read_bytes()
    )
    baseline_previous = verifier_tests._baseline_policy_predecessor(policy)
    assert baseline_previous["records"][471] == policy["records"][471]
    assert baseline_previous["records"][483] != policy["records"][483]
    visual_previous = verifier_tests._visual_readiness_policy_predecessor(
        baseline_previous
    )
    assert visual_previous["records"][471] != baseline_previous["records"][471]
    assert visual_previous["records"][483] == baseline_previous["records"][483]
    changed = [
        index
        for index, (current, previous) in enumerate(
            zip(policy["records"], visual_previous["records"], strict=True)
        )
        if current != previous
    ]
    assert changed == [471, 483]
    canonical = json.dumps(
        visual_previous, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    assert (
        hashlib.sha256(canonical).digest()
        == verifier_tests._VISUAL_READINESS_POLICY_BEFORE_SHA256
    )


@pytest.mark.parametrize("row", [471, 483])
def test_combined_policy_history_rejects_either_identity_mutation(row: int) -> None:
    policy = json.loads(
        (ROOT / "quality/security-false-positive-dispositions.json").read_bytes()
    )
    policy["records"][row]["identity"]["hashed_secret_bytes"][0] ^= 1
    with pytest.raises(AssertionError):
        verifier_tests._aud154_historical_policy(policy)
