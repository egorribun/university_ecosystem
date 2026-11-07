"""CI, supply-chain and scanner contracts for AUD-245, 346, 378, 380, 384, 429, 480 and 483.

Each test pins a behaviour of a workflow or scanner policy file that the audit found
unproven. A green result here shows the repository configuration, not a hosted run.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPOSITORY_ROOT / ".github" / "workflows"


def _load_workflow(name: str) -> dict[str, Any]:
    workflow: dict[str, Any] = yaml.safe_load(
        (WORKFLOWS / name).read_text(encoding="utf-8")
    )
    return workflow


def _step(job: dict[str, Any], name: str) -> dict[str, Any]:
    matches: list[dict[str, Any]] = [
        step for step in job["steps"] if step.get("name") == name
    ]
    assert len(matches) == 1, name
    step: dict[str, Any] = matches[0]
    return step


# AUD-380 ---------------------------------------------------------------------


def test_semgrep_policy_describes_the_hosted_blocking_job() -> None:
    text = (REPOSITORY_ROOT / ".semgrep.yml").read_text(encoding="utf-8")

    assert "NO hosted Semgrep CI job" not in text
    assert "scripts/quality/run_semgrep_gate.py" in text
    assert "exact unexpired dispositions" in text
    assert "root .semgrepignore patterns" in text
    assert "rules: []" in text


def test_exactly_one_workflow_job_is_the_blocking_semgrep_job() -> None:
    offenders: list[str] = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job_name in (workflow or {}).get("jobs", {}):
            if "semgrep" in job_name.lower():
                offenders.append(f"{path.name}:{job_name}")

    assert offenders == ["ci.yml:semgrep-sast"]


def test_semgrep_job_is_blocking_pinned_and_uploads_sarif() -> None:
    ci = _load_workflow("ci.yml")
    job = ci["jobs"]["semgrep-sast"]
    run = str(_step(job, "Run Semgrep with the pinned rule set")["run"])
    rules = _step(job, "Check out pinned Semgrep rules")
    upload = _step(job, "Upload Semgrep SARIF to Code Scanning")
    setup_uv = _step(job, "Install uv for the Semgrep gate")

    assert job["needs"] == "pre-commit-check"
    assert job["timeout-minutes"] > 0
    assert job["permissions"] == {"contents": "read", "security-events": "write"}
    assert "continue-on-error" not in job
    assert all("continue-on-error" not in step for step in job["steps"])
    assert "|| true" not in run
    resolver = str(_step(job, "Resolve the pinned Semgrep image")["run"])
    assert ".pre-commit-config.yaml" in resolver
    assert "semgrep-docker" in resolver
    assert "hooks != 1 || entries != 1 || images != 1" in resolver
    assert '"SEMGREP_IMAGE=$image" >> "$GITHUB_ENV"' in resolver
    assert '"$SEMGREP_IMAGE"' in run
    assert '"$RUNNER_TEMP/semgrep"' in run
    assert "uv run --frozen python -I scripts/quality/run_semgrep_gate.py" in run
    assert '"$SEMGREP_IMAGE"' in run
    assert '--output-directory "$RUNNER_TEMP/semgrep"' in run
    assert "--exclude" not in run
    assert "docker run" not in run
    assert "--config auto" not in run
    hook_config = yaml.safe_load(
        (REPOSITORY_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    )
    semgrep_hooks = [
        hook
        for repo in hook_config["repos"]
        for hook in repo["hooks"]
        if hook.get("id") == "semgrep-docker"
    ]
    assert len(semgrep_hooks) == 1
    assert "exclude" not in semgrep_hooks[0]
    assert "python -I scripts/quality/run_semgrep_gate.py" in semgrep_hooks[0]["entry"]
    runner = (REPOSITORY_ROOT / "scripts/quality/run_semgrep_gate.py").read_text(
        encoding="utf-8"
    )
    assert "EXCLUSIONS" not in runner
    assert '"--exclude"' not in runner
    assert '"--no-git-ignore"' in runner
    assert '"-I"' in runner
    assert '"--verbose"' in runner
    assert '"--max-target-bytes=0"' in runner
    assert not any(
        step.get("name")
        in {
            "Select the deterministic security rule subset",
            "Create tracked source snapshot",
            "Enforce exact reviewed Semgrep dispositions",
        }
        for step in job["steps"]
    )
    assert upload["uses"].startswith("github/codeql-action/upload-sarif@")
    assert len(upload["uses"].split("@", 1)[1].split(" ", 1)[0]) == 40
    assert upload["if"] == "${{ always() }}"
    assert upload["with"]["category"] == "semgrep-sast"
    assert upload["with"]["sarif_file"] == ("${{ runner.temp }}/semgrep/semgrep.sarif")
    assert setup_uv["uses"].startswith("astral-sh/setup-uv@")
    assert len(setup_uv["uses"].split("@", 1)[1].split(" ", 1)[0]) == 40
    assert rules["uses"].startswith("actions/checkout@")
    assert len(rules["uses"].split("@", 1)[1].split(" ", 1)[0]) == 40
    assert rules["with"]["repository"] == "semgrep/semgrep-rules"
    assert re.fullmatch(r"[0-9a-f]{40}", str(rules["with"]["ref"]))
    assert rules["with"]["path"] == ".semgrep-rules"
    assert rules["with"]["persist-credentials"] is False
    assert "semgrep-sast" in ci["jobs"]["ci-success"]["needs"]
    aggregate = str(ci["jobs"]["ci-success"]["steps"][0]["run"])
    assert "semgrep-sast|${{ needs.semgrep-sast.result }}" in aggregate


def test_semgrep_catalog_entry_matches_the_blocking_job() -> None:
    catalog = yaml.safe_load(
        (REPOSITORY_ROOT / "quality" / "ci-check-catalog.json").read_text(
            encoding="utf-8"
        )
    )
    ci = next(
        item
        for item in catalog["workflows"]
        if item["path"] == ".github/workflows/ci.yml"
    )
    entry = ci["jobs"]["semgrep-sast"]
    assert entry["profile"] == "required-pr-main"
    assert entry["needs"] == ["pre-commit-check"]
    assert entry["check_name_template"] == "Semgrep SAST"


# AUD-378 ---------------------------------------------------------------------


def test_slsa_attestation_verification_retries_boundedly_and_fails_closed() -> None:
    job = _load_workflow("ci.yml")["jobs"]["provenance-check"]
    step = _step(job, "Verify SLSA provenance attestation of slsa-verifier")
    run = step["run"]

    assert "continue-on-error" not in step
    assert "|| true" not in run
    assert "for attempt in 1 2 3; do" in run
    assert "timeout --kill-after=15s 120s /tmp/slsa-verifier verify-artifact" in run
    assert "--source-tag v2.7.1" in run
    assert 'if [[ "$verified" -ne 1 ]]; then' in run
    assert "exit 1" in run
    # Three bounded attempts (120s plus 15s kill grace each) with 20s and 40s
    # backoff must fit inside the catalogued 10-minute job budget with headroom.
    attempts_and_backoff_seconds = 3 * (120 + 15) + 20 + 40
    assert job["timeout-minutes"] * 60 >= attempts_and_backoff_seconds + 120


# AUD-346 ---------------------------------------------------------------------


def test_nightly_chaos_dry_run_probes_no_target_and_serves_none() -> None:
    job = _load_workflow("nightly-full-gate.yml")["jobs"]["chaos-loadtest-orchestrator"]
    names = [step.get("name") for step in job["steps"]]
    runs = [str(step.get("run", "")) for step in job["steps"]]

    assert not any("health target" in str(name).lower() for name in names)
    assert not any("http.server" in run for run in runs)
    assert not any("8000" in run or "127.0.0.1:8000" in run for run in runs)
    dry_run = _step(job, "Run chaos loadtest dry-runs")
    assert "continue-on-error" not in dry_run
    invocations = [
        line for line in dry_run["run"].splitlines() if "run_chaos_loadtest.py" in line
    ]
    assert invocations and all("--dry-run" in line for line in invocations)
    assert all("--target-url" not in line for line in invocations)


# AUD-384 ---------------------------------------------------------------------


def test_slack_notification_configuration_precedes_output_guard() -> None:
    job = _load_workflow("nightly-full-gate.yml")["jobs"]["notify-failure"]
    names = [step.get("name") for step in job["steps"]]
    detect = _step(job, "Detect optional Slack notification configuration")
    send = _step(job, "Send optional Slack notification")

    assert names.index(
        "Detect optional Slack notification configuration"
    ) < names.index("Send optional Slack notification")
    assert detect["id"] == "slack_config"
    assert detect["env"]["SLACK_WEBHOOK_URL"] == "${{ secrets.SLACK_WEBHOOK_URL }}"
    assert 'if [[ -n "$SLACK_WEBHOOK_URL" ]]; then' in detect["run"]
    assert 'echo "configured=true" >> "$GITHUB_OUTPUT"' in detect["run"]
    assert 'echo "configured=false" >> "$GITHUB_OUTPUT"' in detect["run"]
    assert send["if"] == (
        "${{ !cancelled() && steps.trusted_source.outcome == 'success' "
        "&& steps.slack_config.outputs.configured == 'true' }}"
    )
    assert detect["if"] == (
        "${{ !cancelled() && steps.trusted_source.outcome == 'success' }}"
    )
    assert "continue-on-error" not in detect


def test_slack_notification_retains_trusted_main_and_failure_admission() -> None:
    job = _load_workflow("nightly-full-gate.yml")["jobs"]["notify-failure"]
    verify = _step(job, "Verify trusted main source")
    detect = _step(job, "Detect optional Slack notification configuration")
    assert verify["id"] == "trusted_source"

    assert job["if"] == (
        "${{ github.ref == 'refs/heads/main' && always() "
        "&& contains(needs.*.result, 'failure') }}"
    )
    assert job["steps"].index(verify) < job["steps"].index(detect)
    assert '"$EVENT_SHA" != "$trusted_sha"' in verify["run"]
    assert '"$WORKFLOW_SHA" != "$trusted_sha"' in verify["run"]
    assert "exit 1" in verify["run"]
    assert "continue-on-error" not in verify


def test_configured_slack_delivery_remains_fail_closed() -> None:
    job = _load_workflow("nightly-full-gate.yml")["jobs"]["notify-failure"]
    send = _step(job, "Send optional Slack notification")

    assert send["env"]["SLACK_WEBHOOK_URL"] == "${{ secrets.SLACK_WEBHOOK_URL }}"
    assert "continue-on-error" not in job
    assert "continue-on-error" not in send
    assert (
        "curl --fail-with-body --silent --show-error --connect-timeout 10 "
        "--max-time 30 --output /dev/null --request POST"
    ) in send["run"]
    assert '"$SLACK_WEBHOOK_URL"' in send["run"]
    assert "|| true" not in send["run"]


# AUD-480 ---------------------------------------------------------------------


def test_npm_gate_blocks_moderate_and_low_without_allowlist_or_omission() -> None:
    job = _load_workflow("reusable-security-audit.yml")["jobs"]["npm-audit"]
    gate = _step(job, "Block moderate and low npm advisories")

    assert "continue-on-error" not in gate
    assert gate["run"].strip().splitlines()[-1].strip() == (
        "npm audit --audit-level=info --include=prod --include=dev "
        "--include=optional --include=peer"
    )
    assert "--omit" not in gate["run"]
    assert "allowlist" not in gate["run"]
    assert "audit_dependencies" not in gate["run"]


def test_npm_high_gate_with_allowlist_remains_blocking() -> None:
    job = _load_workflow("reusable-security-audit.yml")["jobs"]["npm-audit"]
    names = [step.get("name") for step in job["steps"]]
    allowlist_gate = _step(job, "Run npm audit with allowlist")

    assert "continue-on-error" not in allowlist_gate
    assert names.index("Run npm audit with allowlist") < names.index(
        "Block moderate and low npm advisories"
    )


# AUD-480 unfixed Trivy filesystem gate --------------------------------------


def test_trivy_filesystem_gate_reports_unfixed_findings_with_exact_dispositions() -> (
    None
):
    job = _load_workflow("reusable-security-audit.yml")["jobs"]["docker-security"]
    scan = _step(job, "Run Trivy vulnerability scanner (filesystem)")

    assert scan["env"] == {"TRIVY_IGNORE_UNFIXED": "false"}
    assert scan["with"]["trivyignores"] == ".trivyignore.yaml"
    assert scan["with"]["severity"] == "CRITICAL,HIGH"
    assert "ignore-unfixed" not in scan["with"]


def test_trivy_vulnerability_dispositions_are_path_and_expiry_bounded() -> None:
    from datetime import date

    ignores = yaml.safe_load(
        (REPOSITORY_ROOT / ".trivyignore.yaml").read_text(encoding="utf-8")
    )
    entries = ignores["vulnerabilities"]

    assert entries, "unfixed findings must be dispositioned exactly, not ignored"
    for entry in entries:
        assert set(entry) == {"id", "paths", "expired_at", "statement"}
        assert entry["paths"] and all("*" not in path for path in entry["paths"])
        assert date.fromisoformat(str(entry["expired_at"])) <= date(2027, 1, 10)


# AUD-429 wiring --------------------------------------------------------------


def test_e2e_run_enables_realtime_specs_against_the_started_backend() -> None:
    workflow = _load_workflow("reusable-e2e-tests.yml")
    job = next(iter(workflow["jobs"].values()))
    step = _step(job, "Run E2E tests")

    assert step["env"]["REALTIME_E2E"] == "true"
    assert step["env"]["VITE_BACKEND_ORIGIN"] == "http://127.0.0.1:8000"
    assert "continue-on-error" not in step


def test_e2e_run_step_follows_the_backend_readiness_gate() -> None:
    workflow = _load_workflow("reusable-e2e-tests.yml")
    job = workflow["jobs"]["e2e"]
    names = [step.get("name") for step in job["steps"]]

    assert names.index("Wait for backend") < names.index("Run E2E tests")


def test_sbom_pr_inventory_remains_read_only_and_validated() -> None:
    job = _load_workflow("sbom.yml")["jobs"]["vuln-gate-pr"]
    validate = _step(job, "Validate OSV scanner result (pull request inventory)")

    assert job["permissions"] == {"contents": "read"}
    assert "::error::OSV scanner exited 0 but reported" in validate["run"]
    assert all("upload" not in str(step.get("uses", "")) for step in job["steps"])


# AUD-245 scoped SPIRE KSV dispositions ----------------------------------------


def test_spire_ksv_dispositions_are_scoped_to_their_manifests() -> None:
    from datetime import date

    entries = {
        entry["id"]: entry
        for entry in yaml.safe_load(
            (REPOSITORY_ROOT / ".trivyignore.yaml").read_text(encoding="utf-8")
        )["misconfigurations"]
    }

    assert entries["KSV-0012"]["paths"] == ["k8s/spire/spire-agent.yaml"]
    assert entries["KSV-0023"]["paths"] == ["k8s/spire/spire-agent.yaml"]
    assert entries["KSV-0047"]["paths"] == ["k8s/spire/spire-rbac.yaml"]
    for rule in ("KSV-0012", "KSV-0023", "KSV-0047"):
        assert date.fromisoformat(str(entries[rule]["expired_at"])) == date(2027, 1, 10)
    assert "KSV-0017" not in entries


def test_plain_trivyignore_no_longer_globally_suppresses_scoped_spire_rules() -> None:
    plain = {
        line.strip()
        for line in (REPOSITORY_ROOT / ".trivyignore")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip().startswith("KSV-")
    }

    assert not plain & {"KSV-0012", "KSV-0023", "KSV-0047", "KSV-0017"}


# AUD-245 every KSV exception is exact-path scoped (ADR-047 addendum 2026-11-04) -


_AUD245_KSV_EXPIRY = "2027-01-10"
_AUD245_GLOB_CHARACTERS = frozenset("*?[]")


def _aud245_ksv_entries() -> list[dict[str, Any]]:
    policy = yaml.safe_load(
        (REPOSITORY_ROOT / ".trivyignore.yaml").read_text(encoding="utf-8")
    )
    entries: list[dict[str, Any]] = policy["misconfigurations"]
    return [entry for entry in entries if str(entry["id"]).startswith("KSV-")]


def _aud245_ignored(rule: str, target: str) -> bool:
    """Model Trivy's exact-path matching for the policy entries (no globs)."""
    return any(
        entry["id"] == rule and target in entry["paths"]
        for entry in _aud245_ksv_entries()
    )


def test_every_ksv_exception_is_path_scoped_with_reason_and_expiry() -> None:
    entries = _aud245_ksv_entries()
    assert entries, "KSV exceptions must be path-scoped, not removed silently"
    for entry in entries:
        assert set(entry) == {"id", "paths", "expired_at", "statement"}, entry["id"]
        paths = entry["paths"]
        assert isinstance(paths, list) and paths, f"{entry['id']} has no paths"
        for path in paths:
            assert not _AUD245_GLOB_CHARACTERS & set(path), f"{entry['id']}: {path}"
            assert (REPOSITORY_ROOT / path).is_file(), f"{entry['id']}: stale {path}"
        assert str(entry["statement"]).strip(), entry["id"]

        assert str(entry["expired_at"]) == _AUD245_KSV_EXPIRY, entry["id"]


def test_ksv_policy_has_no_global_or_plain_format_entries() -> None:
    plain = {
        line.strip()
        for line in (REPOSITORY_ROOT / ".trivyignore")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip() and not line.strip().startswith("#")
    }

    assert not {line for line in plain if line.startswith("KSV-")}
    assert {str(entry["id"]) for entry in _aud245_ksv_entries()} == {
        "KSV-0012",
        "KSV-0104",
        "KSV-0023",
        "KSV-0001",
        "KSV-0118",
        "KSV-0014",
        "KSV-0047",
        "KSV-0009",
        "KSV-0010",
        "KSV-0008",
        "KSV-0024",
    }


def test_ksv_exceptions_do_not_match_manifests_outside_their_scope() -> None:
    # Probe: a manifest outside the scoped paths that triggers the same rule
    # (the AUD-245 local probe copied the SPIRE agent and a kyverno fixture to
    # paths outside the scope; Trivy reported KSV-0009, KSV-0010, KSV-0014 and
    # KSV-0118 there). Positive controls must still match.
    outside_spire = "k8s/spire-elsewhere/spire-agent-probe.yaml"
    outside_kyverno = "k8s/kyverno/tests/probe-outside/flagd-probe.yaml"

    for rule in ("KSV-0009", "KSV-0010"):
        assert _aud245_ignored(rule, "k8s/spire/spire-agent.yaml")
        assert not _aud245_ignored(rule, outside_spire)
    for rule in ("KSV-0014", "KSV-0118"):
        assert not _aud245_ignored(rule, outside_kyverno)
        assert not _aud245_ignored(rule, outside_spire)
    assert _aud245_ignored(
        "KSV-0014",
        "k8s/kyverno/tests/restrict-image-registries/flagd-pod.yaml",
    )
    assert not _aud245_ignored("KSV-0047", "k8s/spire/spire-agent.yaml")
