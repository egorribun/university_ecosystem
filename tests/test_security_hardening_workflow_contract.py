"""Supply-chain hardening contracts for scanner bootstrap steps."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
CI = WORKFLOWS / "ci.yml"
SECURITY_AUDIT = WORKFLOWS / "reusable-security-audit.yml"
DETECT_SECRETS_REQUIREMENTS = ROOT / "security" / "detect-secrets-requirements.txt"

ACTIONLINT_SHA256 = "8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8"  # pragma: allowlist secret -- release checksum
HADOLINT_SHA256 = "56de6d5e5ec427e17b74fa48d51271c7fc0d61244bf5c90e828aab8362d55010"  # pragma: allowlist secret -- release checksum
SHELLCHECK_SHA256 = "6c881ab0698e4e6ea235245f22832860544f17ba386442fe7e9d629f8cbedf87"  # pragma: allowlist secret -- release checksum
CARGO_BINSTALL_SCRIPT_COMMIT = "5aafaaca52423a22d83a812fa3ca77492e2895db"  # pragma: allowlist secret -- immutable installer commit
CARGO_BINSTALL_SCRIPT_SHA256 = "d3a93702160e0ec03e2a4e996855db1f01adee801fb84a43add24e0877ef8eae"  # pragma: allowlist secret -- release checksum
SLSA_VERIFIER_SHA256 = "499befb675efcca9001afe6e5156891b91e71f9c07ab120a8943979f85cc82e6"  # pragma: allowlist secret -- release checksum
KUBECONFORM_SHA256 = "95f14e87aa28c09d5941f11bd024c1d02fdc0303ccaa23f61cef67bc92619d73"  # pragma: allowlist secret -- release checksum
K6_SHA256 = "c7f03434854f837b6790ee81572e4b0f955241974c79a43cbb9f8d0fef069589"  # pragma: allowlist secret -- release checksum
CRD_CATALOG_COMMIT = "866b2653a5334db9aed20ad74701e20fd464471b"  # pragma: allowlist secret -- immutable schema revision


def _workflow(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _step(job: dict[str, Any], name: str) -> dict[str, Any]:
    return next(step for step in job["steps"] if step.get("name") == name)


def test_ci_scanner_bootstraps_are_version_pinned_and_checksum_verified() -> None:
    """Every downloaded scanner is verified before it can execute."""

    jobs = _workflow(CI)["jobs"]

    actionlint_run = _step(jobs["actionlint"], "Install and Run actionlint")["run"]
    assert "raw.githubusercontent.com" not in actionlint_run
    assert "bash <(" not in actionlint_run
    assert 'actionlint_version="1.7.12"' in actionlint_run
    assert ACTIONLINT_SHA256 in actionlint_run
    assert "sha256sum --check --strict" in actionlint_run
    assert "curl --fail" in actionlint_run
    assert "--proto '=https'" in actionlint_run
    assert "--tlsv1.2" in actionlint_run

    hadolint_run = _step(jobs["dockerfile-lint"], "Run Hadolint")["run"]
    assert 'hadolint_version="2.12.0"' in hadolint_run
    assert HADOLINT_SHA256 in hadolint_run
    assert "sha256sum --check --strict" in hadolint_run
    assert "curl --fail" in hadolint_run
    assert "sudo curl" not in hadolint_run
    hadolint_lines = [line.strip() for line in hadolint_run.splitlines()]
    assert next(
        index
        for index, line in enumerate(hadolint_lines)
        if "sha256sum --check --strict" in line
    ) < next(index for index, line in enumerate(hadolint_lines) if "chmod +x" in line)

    shellcheck_install = _step(jobs["shellcheck"], "Install shellcheck")["run"]
    assert "wget -qO-" not in shellcheck_install
    assert "| tar" not in shellcheck_install
    assert 'shellcheck_version="0.10.0"' in shellcheck_install
    assert SHELLCHECK_SHA256 in shellcheck_install
    assert "sha256sum --check --strict" in shellcheck_install
    assert "curl --fail" in shellcheck_install
    shellcheck_run = _step(jobs["shellcheck"], "Run ShellCheck")["run"]
    assert "shellcheck-v0.10.0/shellcheck" in shellcheck_run


def test_security_audit_checkouts_disable_credentials_and_detect_secrets_is_locked() -> (
    None
):
    """Security jobs cannot persist a checkout token or install mutable tooling."""

    workflow = _workflow(SECURITY_AUDIT)
    for job_name, job in workflow["jobs"].items():
        for step in job.get("steps", []):
            if "actions/checkout@" not in step.get("uses", ""):
                continue
            assert step.get("with", {}).get("persist-credentials") is False, job_name

    install = _step(
        workflow["jobs"]["detect-secrets-baseline"], "Install detect-secrets"
    )["run"]
    assert "python -m pip install" in install
    assert "--require-hashes" in install
    assert "--only-binary=:all:" in install
    assert "security/detect-secrets-requirements.txt" in install
    assert "pip install detect-secrets==" not in install

    requirements = DETECT_SECRETS_REQUIREMENTS.read_text(encoding="utf-8")
    assert "--only-binary=:all:" in requirements
    expected = {
        "detect-secrets==1.5.0": "e24e7b9b5a35048c313e983f76c4bd09dad89f045ff059e354f9943bf45aa060",  # pragma: allowlist secret -- wheel checksum
        "PyYAML==6.0.3": "c458b6d084f9b935061bc36216e8a69a7e293a2f1e68bf956dcd9e6cbcd143f5",  # pragma: allowlist secret -- wheel checksum
        "requests==2.33.1": "4e6d1ef462f3626a1f0a0a9c42dd93c63bad33f9f1c1937509b8c5c8718ab56a",  # pragma: allowlist secret -- wheel checksum
        "certifi==2026.4.22": "3cb2210c8f88ba2318d29b0388d1023c8492ff72ecdde4ebdaddbb13a31b1c4a",  # pragma: allowlist secret -- wheel checksum
        "charset-normalizer==3.4.7": "bd6c2a1c7573c64738d716488d2cdd3c00e340e4835707d8fdb8dc1a66ef164e",  # pragma: allowlist secret -- wheel checksum
        "idna==3.18": "7f952cbe720b688055e3f87de14f5c3e5fdaa8bc3928985c4077ca689de849a2",  # pragma: allowlist secret -- wheel checksum
        "urllib3==2.7.0": "9fb4c81ebbb1ce9531cce37674bbc6f1360472bc18ca9a553ede278ef7276897",  # pragma: allowlist secret -- wheel checksum
    }
    for requirement, digest in expected.items():
        assert re.search(
            rf"(?m)^{re.escape(requirement)}\s+--hash=sha256:{digest}\s*$",
            requirements,
        )


def test_cargo_udeps_bootstrap_is_immutable_and_checksum_verified() -> None:
    """Rust lint tooling must not execute mutable remote installer content."""

    jobs = _workflow(CI)["jobs"]
    install = _step(jobs["rust-lint"], "Install cargo-udeps")["run"]
    assert "set -euo pipefail" in install
    assert f'binstall_script_commit="{CARGO_BINSTALL_SCRIPT_COMMIT}"' in install
    assert f'binstall_script_sha256="{CARGO_BINSTALL_SCRIPT_SHA256}"' in install
    assert (
        'binstall_script_url="https://raw.githubusercontent.com/cargo-bins/cargo-binstall/${binstall_script_commit}/install-from-binstall-release.sh"'
        in install
    )
    assert "sha256sum --check --strict" in install
    assert "cargo binstall -y cargo-udeps@0.1.61" in install
    assert "cargo-binstall/main/" not in install


def test_ci_provenance_and_kubernetes_tooling_are_immutable_and_verified() -> None:
    """Downloaded CI tooling and remote schemas cannot drift silently."""

    jobs = _workflow(CI)["jobs"]
    provenance = _step(jobs["provenance-check"], "Install slsa-verifier")["run"]
    assert 'slsa_verifier_version="2.7.0"' in provenance
    assert SLSA_VERIFIER_SHA256 in provenance
    assert "curl --fail" in provenance
    assert "--proto '=https'" in provenance
    assert "--tlsv1.2" in provenance
    assert "sha256sum --check --strict" in provenance
    assert "curl -sSLo" not in provenance

    k8s = jobs["helm-validate"]
    kubeconform = _step(k8s, "Install kubeconform")["run"]
    assert 'kubeconform_version="0.6.7"' in kubeconform
    assert KUBECONFORM_SHA256 in kubeconform
    assert "curl --fail" in kubeconform
    assert "--proto '=https'" in kubeconform
    assert "--tlsv1.2" in kubeconform
    assert "sha256sum --check --strict" in kubeconform
    assert "curl -sSLo" not in kubeconform

    for step_name in (
        "Validate manifests with kubeconform",
        "Validate static K8s manifests with kubeconform",
    ):
        schema_validation = _step(k8s, step_name)["run"]
        assert CRD_CATALOG_COMMIT in schema_validation
        assert "/CRDs-catalog/main/" not in schema_validation

    stress = jobs["ws-stress-test"]
    k6 = _step(stress, "Install k6")["run"]
    assert 'k6_version="0.54.0"' in k6
    assert K6_SHA256 in k6
    assert "curl --fail" in k6
    assert "--proto '=https'" in k6
    assert "--tlsv1.2" in k6
    assert "sha256sum --check --strict" in k6
    assert "| tar" not in k6
    assert '"/tmp/k6-v${k6_version}-linux-amd64/k6"' in k6


def test_detect_secrets_verification_is_finding_level_and_base_bound() -> None:
    """PR checks compare against an immutable target-branch baseline."""

    job = _workflow(SECURITY_AUDIT)["jobs"]["detect-secrets-baseline"]
    fetch = _step(job, "Fetch trusted base baseline (pull requests)")
    assert fetch["if"] == "${{ github.event_name == 'pull_request' }}"
    assert fetch["env"] == {"BASE_SHA": "${{ github.event.pull_request.base.sha }}"}
    fetch_run = fetch["run"]
    assert "^[0-9a-f]{40}$" in fetch_run
    assert 'git fetch --no-tags --depth=1 origin "$BASE_SHA"' in fetch_run
    assert 'git show "$BASE_SHA:.secrets.baseline"' in fetch_run
    assert '"$RUNNER_TEMP/trusted-base-baseline.json"' in fetch_run

    scan = _step(job, "Scan repo (no baseline)")["run"]
    assert "--exclude-files" in scan
    assert "^\\.secrets\\.baseline$" in scan

    verify = _step(job, "Verify baseline has not regressed")
    assert verify["env"] == {
        "EVENT_NAME": "${{ github.event_name }}",
        "TRUSTED_BASELINE_PATH": "${{ runner.temp }}/trusted-base-baseline.json",
    }
    verify_run = verify["run"]
    assert '--trusted-base-baseline "$TRUSTED_BASELINE_PATH"' in verify_run
    assert "current_scan.json" in verify_run

    scan = _step(job, "Scan repo (no baseline)")["run"]
    assert "detect-secrets scan --exclude-files '^\\.secrets\\.baseline$'" in scan


def test_semgrep_ce_scan_always_covers_the_suppression_ledger() -> None:
    """The CE fallback must scan all sources on every event.

    A diff-aware baseline can hide an unchanged in-source suppression. The
    blocking validator intentionally requires every reviewed ledger entry to
    be observed, so the unauthenticated CE path must use a complete scan.
    """

    job = _workflow(SECURITY_AUDIT)["jobs"]["semgrep"]
    run = _step(job, "Run Semgrep SAST")["run"]
    full_scan = (
        "semgrep scan --config auto \\\n"
        "    --error --sarif --sarif-output=semgrep.sarif"
    )
    assert full_scan in run
    assert "--baseline-commit" not in run
