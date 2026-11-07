"""AUD-378: the SLSA provenance dry-run verifies an attestation, not file presence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

CI = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
PROVENANCE_SHA256 = "b567f5ed9a08d0cbddffc169c4ad2d4101abc6b29f9a4c81893a801e432df1f4"


def _provenance_job() -> dict[str, Any]:
    workflow = yaml.safe_load(CI.read_text(encoding="utf-8"))
    return workflow["jobs"]["provenance-check"]


def _step_named(job: dict[str, Any], name: str) -> dict[str, Any]:
    return next(step for step in job["steps"] if step.get("name") == name)


def test_provenance_check_no_longer_only_checks_file_existence() -> None:
    job = _provenance_job()
    runs = "\n".join(str(step.get("run", "")) for step in job["steps"])
    assert 'if [ ! -f ".github/workflows/ci.yml" ]' not in runs
    assert "Provenance configuration validated" not in runs


def test_provenance_check_verifies_slsa_attestation_of_pinned_verifier() -> None:
    job = _provenance_job()
    names = [step.get("name") for step in job["steps"]]
    install_index = names.index("Install slsa-verifier")
    verify_index = names.index("Verify SLSA provenance attestation of slsa-verifier")
    assert verify_index > install_index

    run = _step_named(job, "Verify SLSA provenance attestation of slsa-verifier")["run"]
    assert "verify-artifact /tmp/slsa-verifier" in run
    assert "--provenance-path" in run
    assert "--source-uri github.com/slsa-framework/slsa-verifier" in run
    assert "--source-tag v2.7.1" in run
    assert "slsa-verifier-linux-amd64.intoto.jsonl" in run
    assert f'provenance_sha256="{PROVENANCE_SHA256}"' in run
    assert "sha256sum --check --strict" in run
    assert "--proto '=https'" in run
    assert "--tlsv1.2" in run
    assert "${{" not in run
    assert job["permissions"] == {
        "contents": "read",
        "actions": "read",
        "attestations": "read",
    }
