"""Cardinality parser tests with synthetic gh JSON, not signature proof."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import pytest

HELPER_DIR = Path(__file__).resolve().parents[1] / "scripts" / "quality"
sys.path.insert(0, str(HELPER_DIR))

import verify_frontend_dist_provenance as provenance

FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "synthetic-gh-attestation-verification.json"
)
OTHER_RUN_URI = (
    "https://github.com/egorribun/university_ecosystem/actions/runs/987654321"
    "/attempts/2"
)


def _binding() -> provenance.Binding:
    return provenance.Binding(
        repository="egorribun/university_ecosystem",
        repository_id="1062776154",
        artifact_id="123456789012",
        artifact_digest="d" * 64,
        producer_result="success",
        run_id="12345678901",
        run_attempt="3",
        event="push",
        source_sha="a" * 40,
        source_ref="refs/heads/main",
        caller_workflow_ref=(
            "egorribun/university_ecosystem/.github/workflows/ci.yml@refs/heads/main"
        ),
    )


def _fixture() -> list[dict[str, Any]]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _certificate(result: dict[str, Any]) -> dict[str, Any]:
    return result["verificationResult"]["signature"]["certificate"]


def test_rejects_ambiguous_duplicate_results_for_the_current_invocation() -> None:
    # Two valid results claiming this invocation are ambiguous; the gate must
    # select exactly one current-run attestation.
    result = _fixture()
    result.append(copy.deepcopy(result[0]))

    with pytest.raises(provenance.ProvenanceError, match="exactly one"):
        provenance.validate_verified_output(result, _binding())


def test_accepts_a_prior_run_result_only_alongside_the_current_run() -> None:
    # Reproducible archives can have valid attestations from other runs. They
    # remain constrained to the same repository, source, and artifact claims;
    # one result must still bind the exact current run and attempt.
    binding = _binding()
    result = _fixture()
    prior = copy.deepcopy(result[0])
    _certificate(prior)["runInvocationURI"] = (
        f"https://github.com/{binding.repository}/actions/runs/987654321/attempts/2"
    )
    result.append(prior)

    assert (provenance.validate_verified_output(result, binding)) is None


def test_rejects_prior_run_results_without_the_current_invocation() -> None:
    binding = _binding()
    result = _fixture()
    result.append(copy.deepcopy(result[0]))
    for item in result:
        _certificate(item)["runInvocationURI"] = (
            f"https://github.com/{binding.repository}/actions/runs/{binding.run_id}"
            "/attempts/2"
        )

    with pytest.raises(provenance.ProvenanceError, match="current run"):
        provenance.validate_verified_output(result, binding)


def test_rejects_empty_result_set() -> None:
    with pytest.raises(provenance.ProvenanceError, match="non-empty list"):
        provenance.validate_verified_output([], _binding())


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda item: _certificate(item).update(sourceRepositoryIdentifier="42"),
            "sourceRepositoryIdentifier mismatch",
        ),
        (
            lambda item: _certificate(item).update(sourceRepositoryDigest="b" * 40),
            "sourceRepositoryDigest mismatch",
        ),
        (
            lambda item: _certificate(item).update(issuer="https://invalid.example"),
            "issuer mismatch",
        ),
        (
            lambda item: _certificate(item).update(
                subjectAlternativeName="https://github.com/other/workflow"
            ),
            "subjectAlternativeName mismatch",
        ),
        (
            lambda item: _certificate(item).update(
                sourceRepositoryURI="https://github.com/other/repository"
            ),
            "sourceRepositoryURI mismatch",
        ),
        (
            lambda item: item["verificationResult"]["statement"].update(
                predicateType="https://invalid.example/predicate"
            ),
            "predicate type mismatch",
        ),
        (
            lambda item: _certificate(item).update(
                sourceRepositoryRef="refs/heads/OTHER"
            ),
            "sourceRepositoryRef mismatch",
        ),
        (
            lambda item: _certificate(item).update(buildTrigger="pull_request"),
            "buildTrigger mismatch",
        ),
        (
            lambda item: _certificate(item).update(runnerEnvironment="self-hosted"),
            "runnerEnvironment mismatch",
        ),
        (
            lambda item: item["verificationResult"].update(verifiedTimestamps=[]),
            "no verified timestamp",
        ),
        (
            lambda item: item["verificationResult"]["statement"]["subject"][0].update(
                name="other-artifact"
            ),
            "subject name mismatch",
        ),
        (
            lambda item: item["verificationResult"]["statement"]["subject"][0][
                "digest"
            ].update(sha256="e" * 64),
            "subject digest mismatch",
        ),
    ],
)
def test_rejects_any_extra_result_that_fails_a_binding(
    mutate: Any, message: str
) -> None:
    result = _fixture()
    invalid_extra = copy.deepcopy(result[0])
    mutate(invalid_extra)
    result.append(invalid_extra)

    with pytest.raises(provenance.ProvenanceError, match=message):
        provenance.validate_verified_output(result, _binding())


@pytest.mark.parametrize(
    "uri",
    [
        "https://github.com/attacker/other/actions/runs/987654321/attempts/2",
        "https://[invalid/actions/runs/987654321/attempts/2",
        f" {OTHER_RUN_URI}",
        f"\n{OTHER_RUN_URI}",
        f"\t{OTHER_RUN_URI}",
        f"\x00{OTHER_RUN_URI}",
        f"{OTHER_RUN_URI} ",
        f"{OTHER_RUN_URI}\n",
        f"{OTHER_RUN_URI}\t",
        OTHER_RUN_URI.replace("/actions/runs/", "/actions/\truns/"),
        OTHER_RUN_URI.replace("/actions/runs/", "/actions/\nruns/"),
        OTHER_RUN_URI.replace("/actions/runs/", "/actions/ runs/"),
        OTHER_RUN_URI.replace("/actions/runs/", "/actions/\x01runs/"),
    ],
)
def test_rejects_an_extra_result_with_foreign_or_noncanonical_run_uri(
    uri: str,
) -> None:
    binding = _binding()
    result = _fixture()
    invalid_extra = copy.deepcopy(result[0])
    _certificate(invalid_extra)["runInvocationURI"] = uri
    result.append(invalid_extra)

    with pytest.raises(provenance.ProvenanceError, match="run invocation URI"):
        provenance.validate_verified_output(result, binding)


def test_rejects_non_object_verification_result_entry() -> None:
    result = _fixture()
    result.append({"verificationResult": None})

    with pytest.raises(provenance.ProvenanceError, match="verified result"):
        provenance.validate_verified_output(result, _binding())
