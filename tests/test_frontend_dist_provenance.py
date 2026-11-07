"""Policy parser tests; fixtures are synthetic and are not cryptographic proof."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

HELPER_DIR = Path(__file__).resolve().parents[1] / "scripts" / "quality"
sys.path.insert(0, str(HELPER_DIR))

import verify_frontend_dist_provenance as provenance

FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "synthetic-gh-attestation-verification.json"
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


def test_accepts_one_complete_synthetic_verified_cli_result() -> None:
    # This validates our policy parser only. gh performs the live signature,
    # transparency-log, subject-file and trusted-root verification in CI.
    provenance.validate_verified_output(_fixture(), _binding())


@pytest.mark.parametrize("version", ["2.102.0", "2.102.1", "3.0.0"])
def test_accepts_patched_github_cli_version(
    monkeypatch: pytest.MonkeyPatch, version: str
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert command == ["gh", "--version"]
        assert kwargs["timeout"] == provenance.GH_VERSION_TIMEOUT_SECONDS
        return subprocess.CompletedProcess(
            command, 0, stdout=f"gh version {version} (test)\n", stderr=""
        )

    monkeypatch.setattr(provenance.subprocess, "run", fake_run)

    assert provenance.check_gh_version({"PATH": "unused"}) == version


@pytest.mark.parametrize("version", ["2.98.0", "2.101.99", "2.102.0-rc.1"])
def test_rejects_unpatched_or_prerelease_github_cli(
    monkeypatch: pytest.MonkeyPatch, version: str
) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(
            command, 0, stdout=f"gh version {version} (test)\n", stderr=""
        )

    monkeypatch.setattr(provenance.subprocess, "run", fake_run)

    with pytest.raises(provenance.ProvenanceError, match="GitHub CLI"):
        provenance.verify_with_gh(Path("unused.zip"), _binding(), {"PATH": "unused"})

    assert calls == [["gh", "--version"]]


def test_rejects_github_cli_version_check_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(provenance.subprocess, "run", fake_run)

    with pytest.raises(provenance.ProvenanceError, match="version check timed out"):
        provenance.check_gh_version({"PATH": "unused"})


def test_bounds_and_rejects_attestation_verifier_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], float]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs["timeout"]))
        if command == ["gh", "--version"]:
            return subprocess.CompletedProcess(
                command, 0, stdout="gh version 2.102.0 (test)\n", stderr=""
            )
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(provenance.subprocess, "run", fake_run)

    with pytest.raises(
        provenance.ProvenanceError, match="attestation verify timed out"
    ):
        provenance.verify_with_gh(Path("unused.zip"), _binding(), {"PATH": "unused"})

    assert calls[0] == (["gh", "--version"], provenance.GH_VERSION_TIMEOUT_SECONDS)
    assert calls[1][0][0:3] == ["gh", "attestation", "verify"]
    assert calls[1][1] == provenance.GH_VERIFY_TIMEOUT_SECONDS


def test_rejects_wrong_subject_digest() -> None:
    result = _fixture()
    result[0]["verificationResult"]["statement"]["subject"][0]["digest"]["sha256"] = (
        "e" * 64
    )

    with pytest.raises(provenance.ProvenanceError, match="subject digest mismatch"):
        provenance.validate_verified_output(result, _binding())


def test_rejects_wrong_source_commit() -> None:
    result = _fixture()
    result[0]["verificationResult"]["signature"]["certificate"][
        "sourceRepositoryDigest"
    ] = "b" * 40

    with pytest.raises(
        provenance.ProvenanceError, match="sourceRepositoryDigest mismatch"
    ):
        provenance.validate_verified_output(result, _binding())


def test_rejects_wrong_workflow_identity() -> None:
    result = _fixture()
    result[0]["verificationResult"]["signature"]["certificate"][
        "subjectAlternativeName"
    ] = "https://github.com/egorribun/university_ecosystem/.github/workflows/other.yml@refs/heads/main"

    with pytest.raises(
        provenance.ProvenanceError, match="subjectAlternativeName mismatch"
    ):
        provenance.validate_verified_output(result, _binding())


def test_rejects_missing_attestation() -> None:
    with pytest.raises(provenance.ProvenanceError, match="non-empty list"):
        provenance.validate_verified_output([], _binding())


def test_rejects_artifact_api_identity_drift() -> None:
    binding = _binding()
    artifact, run = _api_fixture(binding)
    mismatched = copy.deepcopy(artifact)
    mismatched["workflow_run"]["head_sha"] = "c" * 40

    with pytest.raises(
        provenance.ProvenanceError, match="artifact source SHA mismatch"
    ):
        provenance.validate_artifact_and_run(mismatched, run, binding)


def _api_fixture(binding: provenance.Binding) -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        {
            "id": int(binding.artifact_id),
            "name": "frontend-dist",
            "digest": f"sha256:{binding.artifact_digest}",
            "expired": False,
            "size_in_bytes": 4096,
            "workflow_run": {
                "id": int(binding.run_id),
                "repository_id": int(binding.repository_id),
                "head_repository_id": int(binding.repository_id),
                "head_sha": binding.source_sha,
                "head_branch": "main",
            },
        },
        {
            "id": int(binding.run_id),
            "run_attempt": int(binding.run_attempt),
            "event": binding.event,
            "head_sha": binding.source_sha,
            "head_branch": "main",
            "path": ".github/workflows/ci.yml",
            "repository": {"id": int(binding.repository_id)},
        },
    )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda cert: cert.update(sourceRepositoryRef="refs/heads/MAIN"),
            "sourceRepositoryRef mismatch",
        ),
        (
            lambda cert: cert.update(buildTrigger="pull_request"),
            "buildTrigger mismatch",
        ),
        (
            lambda cert: cert.update(runInvocationURI="https://github.com/other/run"),
            "certificate run invocation URI is invalid",
        ),
    ],
)
def test_rejects_wrong_source_event_or_attempt_claim(mutate: Any, message: str) -> None:
    result = _fixture()
    mutate(result[0]["verificationResult"]["signature"]["certificate"])

    with pytest.raises(provenance.ProvenanceError, match=message):
        provenance.validate_verified_output(result, _binding())


def test_workflow_postimage_exports_exact_bundle_receipt_and_scopes_attester() -> None:
    postimage = Path(__file__).resolve().parents[1]
    ci = yaml.safe_load(
        (postimage / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    reusable = yaml.safe_load(
        (postimage / ".github" / "workflows" / "reusable-frontend-tests.yml").read_text(
            encoding="utf-8"
        )
    )

    attester = ci["jobs"]["frontend-dist-attestation"]
    assert attester["if"] == "${{ github.event_name == 'push' }}"
    assert attester["permissions"] == {
        "contents": "read",
        "id-token": "write",
        "attestations": "write",
    }
    assert all("checkout" not in step.get("uses", "") for step in attester["steps"])
    assert ci["jobs"]["frontend-tests"]["permissions"] == {
        "contents": "read",
        "actions": "read",
    }
    attest_step = next(
        step
        for step in attester["steps"]
        if step.get("name") == "Attest exact frontend-dist archive digest"
    )
    assert attest_step["uses"].startswith("actions/attest-build-provenance@")
    assert attest_step["with"]["subject-name"] == "frontend-dist"

    verifier = ci["jobs"]["provenance-check"]
    assert verifier["name"] == "SLSA Provenance Dry-Run"
    assert set(verifier["needs"]) == {
        "pre-commit-check",
        "frontend-tests",
        "frontend-dist-attestation",
    }
    assert verifier["permissions"] == {
        "contents": "read",
        "actions": "read",
        "attestations": "read",
    }
    app_verifier = next(
        step
        for step in verifier["steps"]
        if step.get("name") == "Verify frontend-dist application artifact attestation"
    )
    assert app_verifier["if"] == "${{ github.event_name == 'push' }}"
    assert "provenance-check" in ci["jobs"]["ci-success"]["needs"]

    on_section = next(
        value
        for key, value in reusable.items()
        if key is True or str(key).lower() == "on"
    )
    outputs = on_section["workflow_call"]["outputs"]
    assert (
        outputs["bundle-artifact-id"]["value"]
        == "${{ jobs.build.outputs.bundle-artifact-id }}"
    )
    assert (
        outputs["bundle-artifact-digest"]["value"]
        == "${{ jobs.build.outputs.bundle-artifact-digest }}"
    )
    assert (
        reusable["jobs"]["build"]["outputs"]["bundle-artifact-digest"]
        == "${{ steps.upload-production-bundle.outputs.artifact-digest }}"
    )
