"""Workflow contracts for the CI gate hardening of AUD-244, AUD-381, AUD-384 and AUD-483."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
pytest_plugins = ("pytester",)

PERSIST_CREDENTIAL_FILES = (
    "auto-merge-patches.yml",
    "chromatic.yml",
    "contract-validation.yml",
    "dast.yml",
    "go-lint.yml",
    "lhci-linux.yml",
    "quality-promotion-check.yml",
    "reusable-full-backend-mutation.yml",
    "reusable-helm-dependencies.yml",
    "sbom.yml",
    "sonar.yml",
    "trufflehog.yml",
)


def _load(name: str) -> dict[str, Any]:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def _step(job: dict[str, Any], name: str) -> dict[str, Any]:
    matches = [step for step in job["steps"] if step.get("name") == name]
    assert len(matches) == 1, name
    return matches[0]


def _names(job: dict[str, Any]) -> list[str]:
    return [step.get("name", "") for step in job["steps"]]


def test_zizmor_configuration_disables_no_audit() -> None:
    config = yaml.safe_load((ROOT / "zizmor.yml").read_text(encoding="utf-8"))

    assert config == {"rules": {}}


def test_dependabot_auto_merge_gates_on_immutable_pr_author_id() -> None:
    job = _load("auto-merge-patches.yml")["jobs"]["auto-merge"]

    assert job["if"] == "github.event.pull_request.user.id == 49699333"


def test_deploy_and_lhci_default_to_read_only_repository_contents() -> None:
    deploy = _load("deploy.yml")
    lhci = _load("lhci-linux.yml")

    assert deploy["permissions"] == {"contents": "read"}
    assert deploy["jobs"]["validate"]["permissions"] == {
        "contents": "read",
        "actions": "read",
    }
    assert lhci["permissions"] == {"contents": "read"}


def test_nightly_slack_notification_reads_a_step_output_in_its_condition() -> None:
    job = _load("nightly-full-gate.yml")["jobs"]["notify-failure"]
    detect = next(step for step in job["steps"] if step.get("id") == "slack_config")
    send = _step(job, "Send optional Slack notification")

    assert set(detect["env"]) == {"SLACK_WEBHOOK_URL"}
    assert send["if"] == (
        "${{ !cancelled() && steps.trusted_source.outcome == 'success' "
        "&& steps.slack_config.outputs.configured == 'true' }}"
    )
    assert "env." not in send["if"]
    assert "secrets." not in send["if"]


def test_dast_nuclei_fails_on_high_or_critical_only_after_publication() -> None:
    job = _load("dast.yml")["jobs"]["nuclei"]
    names = _names(job)
    gate = _step(job, "Fail on high or critical Nuclei findings")
    run = gate["run"]

    assert names.index("Upload raw JSON findings") < names.index(gate["name"])
    assert '.info.severity == "high" or .info.severity == "critical"' in run
    assert "exit 1" in run
    assert "[[ ! -f nuclei-results.json ]]" in run  # missing export fails closed


def _nuclei_export(severity: str) -> str:
    """Representative native JSON export, not JSONL or scanner emulation."""
    return json.dumps(
        [
            {
                "template-id": "workflow-contract-fixture",
                "info": {
                    "name": "Synthetic workflow contract finding",
                    "author": ["workflow-contract"],
                    "tags": ["workflow-contract"],
                    "severity": severity,
                },
                "type": "http",
                "host": "https://example.invalid",
                "matched-at": "https://example.invalid/",
                "timestamp": "2026-10-31T00:00:00Z",
                "matcher-status": True,
            }
        ]
    )


@pytest.fixture
def nuclei_gate(pytester, monkeypatch: pytest.MonkeyPatch):
    job = _load("dast.yml")["jobs"]["nuclei"]
    scan = _step(job, "Run Nuclei scan")["run"]
    gate = _step(job, "Fail on high or critical Nuclei findings")
    script = gate["run"]

    # A producer switch to JSONL requires an explicit fixture-contract review.
    assert "-json-export nuclei-results.json" in scan
    assert gate["shell"] == "bash"
    assert "${{" not in script, "Actions expressions require runner substitution"

    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    bash = (
        str(git_bash) if os.name == "nt" and git_bash.exists() else shutil.which("bash")
    )
    assert bash, "Real Bash is required to execute the Nuclei gate"
    monkeypatch.chdir(pytester.path)
    monkeypatch.delenv("BASH_ENV", raising=False)

    # Missing jq is a fixture/environment failure, never product RED evidence.
    probe = pytester.run(
        bash,
        "--noprofile",
        "--norc",
        "-e",
        "-o",
        "pipefail",
        "-c",
        "jq --version",
        timeout=20,
    )
    assert probe.ret == 0, (
        "Real jq must be available inside Bash before testing the Nuclei gate:\n"
        + probe.stdout.str()
        + "\n"
        + probe.stderr.str()
    )
    assert probe.stdout.str().strip().startswith("jq-")

    script_path = pytester.path / "actual-nuclei-gate.sh"
    script_path.write_text(script, encoding="utf-8", newline="\n")
    export_path = pytester.path / "nuclei-results.json"

    def run(export: str | None):
        export_path.unlink(missing_ok=True)
        if export is not None:
            export_path.write_text(export, encoding="utf-8", newline="\n")
        return pytester.run(
            bash,
            "--noprofile",
            "--norc",
            "-e",
            "-o",
            "pipefail",
            script_path.as_posix(),
            timeout=20,
        )

    return run


@pytest.mark.parametrize(
    ("export", "expected_success", "blocking_count"),
    [
        pytest.param("[]", True, None, id="native-empty-array"),
        pytest.param(_nuclei_export("medium"), True, None, id="native-medium"),
        pytest.param(_nuclei_export("high"), False, 1, id="native-high"),
        pytest.param(_nuclei_export("critical"), False, 1, id="native-critical"),
        pytest.param(None, False, None, id="missing-export"),
        pytest.param("", False, None, id="zero-byte-export"),
        pytest.param("[", False, None, id="malformed-json"),
        pytest.param(
            '{"info":{"severity":"medium"}}',
            False,
            None,
            id="wrong-top-level-object",
        ),
    ],
)
def test_dast_nuclei_gate_consumes_native_json_export(
    nuclei_gate,
    export: str | None,
    expected_success: bool,
    blocking_count: int | None,
) -> None:
    result = nuclei_gate(export)
    stdout = result.stdout.str()
    stderr = result.stderr.str()
    diagnostic = f"exit={result.ret}\nstdout:\n{stdout}\nstderr:\n{stderr}"

    assert (result.ret == 0) is expected_success, diagnostic

    clean_message = "Nuclei reported no high or critical findings."
    if expected_success:
        assert clean_message in stdout, diagnostic
    else:
        assert clean_message not in stdout + stderr, diagnostic

    if blocking_count is not None:
        # A jq type error must not satisfy the high/critical negative control.
        assert result.ret == 1, diagnostic
        assert f"Nuclei reported {blocking_count} high or critical" in stderr, (
            diagnostic
        )


@pytest.mark.parametrize(
    ("export", "blocking_count"),
    [
        pytest.param(_nuclei_export("info"), 0, id="canonical-info"),
        pytest.param(_nuclei_export("low"), 0, id="canonical-low"),
        pytest.param(_nuclei_export("unknown"), 0, id="canonical-unknown"),
        pytest.param(
            json.dumps(
                [
                    json.loads(_nuclei_export(severity))[0]
                    for severity in ("medium", "high", "critical")
                ],
                indent=2,
            ),
            2,
            id="pretty-mixed-findings",
        ),
        pytest.param(
            json.dumps(
                [
                    json.loads(_nuclei_export(severity))[0]
                    for severity in ("medium", "high", "critical")
                ],
                separators=(",", ":"),
            ),
            2,
            id="minified-mixed-findings",
        ),
        pytest.param(
            _nuclei_export("high").replace('"high"', '"\\u0068igh"'),
            1,
            id="json-escaped-high",
        ),
    ],
)
def test_dast_nuclei_gate_preserves_native_severity_and_json_equivalence(
    nuclei_gate,
    export: str,
    blocking_count: int,
) -> None:
    result = nuclei_gate(export)
    stdout = result.stdout.str()
    stderr = result.stderr.str()
    diagnostic = f"exit={result.ret}\nstdout:\n{stdout}\nstderr:\n{stderr}"
    clean_message = "Nuclei reported no high or critical findings."

    if blocking_count:
        assert result.ret == 1, diagnostic
        assert f"Nuclei reported {blocking_count} high or critical" in stderr, (
            diagnostic
        )
        assert clean_message not in stdout + stderr, diagnostic
    else:
        assert result.ret == 0, diagnostic
        assert clean_message in stdout, diagnostic


@pytest.mark.parametrize(
    "export",
    [
        pytest.param(" \n\t", id="whitespace-only"),
        pytest.param("[]\n[]", id="two-array-documents"),
        pytest.param("{}\n{}", id="jsonl-object-documents"),
        pytest.param(_nuclei_export("medium") + "\n[]", id="extra-empty-document"),
        pytest.param("null", id="null-root"),
        pytest.param("true", id="boolean-root"),
        pytest.param("1", id="number-root"),
        pytest.param('"finding"', id="string-root"),
        pytest.param("[null]", id="null-member"),
        pytest.param("[[]]", id="array-member"),
        pytest.param("[true]", id="boolean-member"),
        pytest.param("[1]", id="number-member"),
        pytest.param('["finding"]', id="string-member"),
        pytest.param("[{}]", id="missing-info"),
        pytest.param('[{"info":null}]', id="null-info"),
        pytest.param('[{"info":[]}]', id="array-info"),
        pytest.param('[{"info":{}}]', id="missing-severity"),
        pytest.param('[{"info":{"severity":null}}]', id="null-severity"),
        pytest.param('[{"info":{"severity":1}}]', id="numeric-severity"),
        pytest.param('[{"info":{"severity":true}}]', id="boolean-severity"),
        pytest.param('[{"info":{"severity":[]}}]', id="array-severity"),
        pytest.param('[{"info":{"severity":{}}}]', id="object-severity"),
        pytest.param(_nuclei_export(""), id="undefined-severity"),
        pytest.param(_nuclei_export("HIGH"), id="noncanonical-severity"),
        pytest.param(_nuclei_export(" high "), id="padded-severity"),
        pytest.param(_nuclei_export("unrecognized"), id="unsupported-severity"),
        pytest.param(
            json.dumps([json.loads(_nuclei_export("medium"))[0], None]),
            id="valid-medium-then-malformed-member",
        ),
        pytest.param(
            json.dumps([json.loads(_nuclei_export("high"))[0], {}]),
            id="validate-whole-array-before-blocking-count",
        ),
    ],
)
def test_dast_nuclei_gate_rejects_invalid_evidence_before_counting(
    nuclei_gate,
    export: str,
) -> None:
    result = nuclei_gate(export)
    stdout = result.stdout.str()
    stderr = result.stderr.str()
    diagnostic = f"exit={result.ret}\nstdout:\n{stdout}\nstderr:\n{stderr}"

    assert result.ret == 1, diagnostic
    assert "Could not validate Nuclei JSON export" in stderr, diagnostic
    assert "the scan result is unknown" in stderr, diagnostic
    assert "Nuclei reported no high or critical findings." not in stdout + stderr
    assert "high or critical finding(s)." not in stdout + stderr


def test_scorecard_fails_on_high_severity_after_sarif_upload() -> None:
    job = _load("scorecard.yml")["jobs"]["analysis"]
    names = _names(job)
    gate = _step(job, "Fail on high-severity Scorecard findings")

    assert names.index("Upload SARIF results to GitHub Security tab") < names.index(
        gate["name"]
    )
    assert "security-severity" in gate["run"]
    assert ">= 7.0" in gate["run"]
    assert "sys.exit(1)" in gate["run"]


def test_sqlmap_writes_result_logs_and_fails_on_confirmed_injection() -> None:
    job = _load("sqlmap.yml")["jobs"]["sqlmap"]
    scan = _step(job, "Run SQLMap Scan on API")["run"]
    gate = _step(job, "Fail on confirmed SQL injection")
    upload = _step(job, "Upload SQLMap result logs")

    assert "--output-dir=sqlmap-output" in scan
    assert gate["if"] == "${{ always() }}"
    assert "identified the following injection point" in gate["run"]
    assert "exit 1" in gate["run"]
    assert upload["if"] == "${{ always() }}"
    assert upload["with"]["path"] == "sqlmap-output/"


def test_pull_request_vulnerability_gate_runs_read_only_osv_inventory() -> None:
    job = _load("sbom.yml")["jobs"]["vuln-gate-pr"]
    names = _names(job)
    scan = _step(job, "Scan Go modules for vulnerabilities (pull request inventory)")
    validate = _step(job, "Validate OSV scanner result (pull request inventory)")

    assert "Install osv-scanner (pull request inventory)" in names
    assert job["permissions"] == {"contents": "read"}
    assert "scan source --recursive --format sarif" in scan["run"]
    assert "::error::OSV scanner exited 0 but reported" in validate["run"]
    assert not any("upload" in str(step.get("uses", "")) for step in job["steps"])


def test_hardened_workflows_do_not_persist_checkout_credentials() -> None:
    for workflow_name in PERSIST_CREDENTIAL_FILES:
        workflow = _load(workflow_name)
        for job_name, job in workflow["jobs"].items():
            for step in job.get("steps", []):
                if not str(step.get("uses", "")).startswith("actions/checkout@"):
                    continue
                persist = step.get("with", {}).get("persist-credentials")
                assert persist is False, f"{workflow_name}:{job_name}"


def test_coverage_consumer_has_only_job_scoped_artifact_read_permission() -> None:
    workflow = _load("ci.yml")
    job = workflow["jobs"]["coverage-policy-gate"]
    selector = _step(job, "Select retry-safe same-run coverage producer artifacts")

    assert workflow["permissions"] == {"contents": "read"}
    assert job.get("permissions") == {"contents": "read", "actions": "read"}
    assert selector["env"] == {"GH_TOKEN": "${{ github.token }}"}
    assert "scripts.quality.select_coverage_producer_artifacts" in selector["run"]


def test_inline_trivy_builds_do_not_use_shared_github_actions_cache() -> None:
    workflow = _load("ci.yml")
    job = workflow["jobs"]["docker-security-scan-additional"]
    build = _step(job, "Build local runtime image for scanning")["with"]
    scan = _step(job, "Run Trivy vulnerability scanner")["with"]

    assert workflow["cache-mode"] == "none"
    assert "cache-from" not in build
    assert "cache-to" not in build
    assert build["push"] is False
    assert build["load"] is True
    assert {row["image_name"] for row in job["strategy"]["matrix"]["include"]} == {
        "frontend",
        "gateway",
        "ws-hub",
        "file-processor",
        "caddy",
    }
    assert scan["severity"] == "CRITICAL,HIGH"
    assert scan["exit-code"] == "1"


def test_weekly_duration_writer_keeps_trust_and_credential_boundaries() -> None:
    workflow = _load("weekly-test-durations.yml")
    events = workflow.get("on", workflow.get(True))
    assert set(events) == {"schedule", "repository_dispatch"}
    assert events["repository_dispatch"] == {"types": ["run-weekly-test-durations"]}
    assert workflow["permissions"] == {"actions": "read", "contents": "read"}
    shard = workflow["jobs"]["refresh-shard"]
    writer = workflow["jobs"]["refresh"]
    assert shard["permissions"] == {"contents": "read"}
    assert shard["if"] == "${{ github.ref == 'refs/heads/main' }}"
    assert writer["permissions"] == {
        "actions": "read",
        "contents": "write",
        "pull-requests": "write",
    }
    assert writer["needs"] == "refresh-shard"
    assert writer["if"] == "${{ always() && github.ref == 'refs/heads/main' }}"
    assert _step(writer, "Fail if a duration shard failed")["if"] == (
        "${{ needs.refresh-shard.result != 'success' }}"
    )
    assert _names(writer).index("Verify trusted main source") < _names(writer).index(
        "Open update pull request"
    )
    assert _step(writer, "Checkout")["with"]["ref"] == "main"
    assert _step(writer, "Open update pull request")["env"] == {
        "GH_TOKEN": "${{ github.token }}"
    }
    for job in (shard, writer):
        assert _step(job, "Checkout")["with"]["persist-credentials"] is False


@pytest.fixture
def weekly_duration_writer(pytester, monkeypatch: pytest.MonkeyPatch):
    import secrets

    writer = _load("weekly-test-durations.yml")["jobs"]["refresh"]
    verify = _step(writer, "Verify trusted main source")["run"]
    publish = _step(writer, "Open update pull request")["run"]
    assert "${{" not in verify + publish, "Runner expressions need substitution"

    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    bash = (
        str(git_bash) if os.name == "nt" and git_bash.exists() else shutil.which("bash")
    )
    assert bash, "Real Bash is required for the duration writer contract"
    monkeypatch.chdir(pytester.path)
    for name in tuple(os.environ):
        if name in {"BASH_ENV", "ENV", "SHELLOPTS", "BASHOPTS", "GITHUB_TOKEN"} or (
            name.startswith(("GIT_", "GH_", "BASH_FUNC_"))
        ):
            monkeypatch.delenv(name, raising=False)
    empty_bin = pytester.path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", empty_bin.as_posix())
    marker = secrets.token_urlsafe(32)
    sha = "a" * 40
    for name, value in {
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_RUN_ID": "12345",
        "EVENT_SHA": sha,
        "WORKFLOW_SHA": sha,
        "TEST_TRUSTED_SHA": sha,
        "TEST_CHECKOUT_SHA": sha,
        "TEST_EXPECTED_TOKEN": marker,
    }.items():
        monkeypatch.setenv(name, value)

    journal = pytester.path / "writer-events.txt"
    monkeypatch.setenv("TEST_WRITER_JOURNAL", journal.as_posix())
    # Only remote Git/PR effects are doubled. The checked-in Bash, its failure
    # propagation and the selected command-local credential helper execute.
    transport = r"""
record() { printf '%s\n' "$1" >> "$TEST_WRITER_JOURNAL"; }
gh() {
  if [[ "$*" == "auth git-credential get" ]]; then
    local protocol host blank
    IFS= read -r protocol
    IFS= read -r host
    IFS= read -r blank
    [[ "$protocol" == protocol=https && "$host" == host=github.com ]]
    [[ -z "$blank" && -n "${GH_TOKEN:-}" ]]
    printf 'protocol=https\nhost=github.com\nusername=x-access-token\npassword=%s\n' "$GH_TOKEN"
  elif [[ "$#" == 10 && "$*" == "pr create --base main --head automation/test-durations-12345 --title chore(quality): refresh pytest duration map --body Automated weekly refresh from pytest JUnit timings." ]]; then
    record pr
    return "$TEST_PR_STATUS"
  else
    return 91
  fi
}
export -f gh record
git() {
  case "$1" in
    fetch)
      [[ "$*" == "fetch origin refs/heads/main:refs/remotes/origin/main --depth=1" ]]
      ;;
    rev-parse)
      case "$2" in
        refs/remotes/origin/main) printf '%s\n' "$TEST_TRUSTED_SHA" ;;
        HEAD) printf '%s\n' "$TEST_CHECKOUT_SHA" ;;
        *) return 92 ;;
      esac
      ;;
    diff)
      [[ "$*" == "diff --quiet -- quality/test-durations.json" ]] || return 93
      return "$TEST_DIFF_STATUS"
      ;;
    switch)
      [[ "$*" == "switch --create automation/test-durations-12345" ]] || return 94
      record switch
      ;;
    config)
      case "$*" in
        "config user.name github-actions[bot]") record config-name ;;
        "config user.email 41898282+github-actions[bot]@users.noreply.github.com") record config-email ;;
        *) record forbidden-config; return 95 ;;
      esac
      ;;
    add)
      [[ "$*" == "add quality/test-durations.json" ]] || return 96
      record add
      ;;
    commit)
      [[ "$#" == 3 && "$*" == "commit -m chore(quality): refresh pytest duration map" ]] || return 97
      record commit
      ;;
    -c)
      [[ "$#" == 8 && "$2" == credential.helper= && "$3" == -c ]] || return 98
      [[ "$4" == 'credential.https://github.com.helper=!gh auth git-credential' ]] || return 98
      [[ "$5 $6 $7 $8" == "push --set-upstream origin automation/test-durations-12345" ]] || return 98
      local helper credentials expected
      helper="${4#credential.https://github.com.helper=!}"
      credentials="$(printf 'protocol=https\nhost=github.com\n\n' |
        "$BASH" --noprofile --norc -e -o pipefail -c "$helper get")" || return 99
      expected="$(printf 'protocol=https\nhost=github.com\nusername=x-access-token\npassword=%s' "$TEST_EXPECTED_TOKEN")"
      [[ "$credentials" == "$expected" ]] || return 99
      record authenticated-push
      return "$TEST_PUSH_STATUS"
      ;;
    push)
      record unauthenticated-push
      return 90
      ;;
    *) return 100 ;;
  esac
}
"""
    script = pytester.path / "actual-weekly-writer.sh"
    script.write_text(
        transport
        + "\n(\nunset GH_TOKEN\n"
        + verify
        + "\n)\nunset EVENT_SHA WORKFLOW_SHA\n"
        + publish,
        encoding="utf-8",
        newline="\n",
    )

    def run(case: str):
        journal.unlink(missing_ok=True)
        monkeypatch.setenv("GH_TOKEN", marker)
        monkeypatch.setenv("TEST_DIFF_STATUS", "0" if case == "unchanged" else "1")
        monkeypatch.setenv("TEST_PUSH_STATUS", "77" if case == "push-failed" else "0")
        monkeypatch.setenv("TEST_PR_STATUS", "78" if case == "pr-failed" else "0")
        if case == "missing-token":
            monkeypatch.delenv("GH_TOKEN")
        elif case == "wrong-ref":
            monkeypatch.setenv("GITHUB_REF", "refs/heads/other")
        elif case == "stale-source":
            monkeypatch.setenv("WORKFLOW_SHA", "b" * 40)
        result = pytester.run(
            bash,
            "--noprofile",
            "--norc",
            "-e",
            "-o",
            "pipefail",
            script.as_posix(),
            timeout=20,
        )
        leaked = marker in result.stdout.str() + result.stderr.str()
        assert not leaked, "The writer exposed its synthetic credential"
        events = (
            journal.read_text(encoding="utf-8").splitlines() if journal.exists() else []
        )
        return result.ret, events

    return run


@pytest.mark.parametrize(
    "case",
    [
        "changed",
        "unchanged",
        "missing-token",
        "push-failed",
        "pr-failed",
        "wrong-ref",
        "stale-source",
    ],
)
def test_weekly_duration_writer_authenticates_only_the_guarded_push(
    weekly_duration_writer, case: str
) -> None:
    status, events = weekly_duration_writer(case)
    mutations = ["switch", "config-name", "config-email", "add", "commit"]
    if case == "changed":
        assert status == 0
        assert events == [*mutations, "authenticated-push", "pr"]
    elif case == "unchanged":
        assert status == 0
        assert events == []
    elif case == "push-failed":
        assert status == 77
        assert events == [*mutations, "authenticated-push"]
    elif case == "pr-failed":
        assert status == 78
        assert events == [*mutations, "authenticated-push", "pr"]
    else:
        assert status != 0
        assert events == []
