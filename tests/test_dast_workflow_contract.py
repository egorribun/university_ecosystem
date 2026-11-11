from __future__ import annotations

import copy
import json
import os
import re
import shlex
import shutil
import sys
from pathlib import Path

import pytest
import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DAST_WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "dast.yml"
TARGET_EXPRESSION = "${{ inputs.target_url || secrets.DAST_TARGET_URL }}"
TRUSTED_REF_ERROR = "DAST scans must run from the protected main ref."
pytest_plugins = ("pytester",)


def _workflow_triggers(workflow: dict[str, object]) -> dict[str, object]:
    """PyYAML parses the YAML 1.1 key ``on`` as boolean True."""

    triggers = workflow.get("on", workflow.get(True))
    assert isinstance(triggers, dict)
    return triggers


def _assert_fail_closed_target_preflight(preflight_script: str) -> None:
    """Nuclei rejects missing targets before a scan can receive one."""
    shell_lines = [
        line.strip()
        for line in preflight_script.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert shell_lines == [
        "set -euo pipefail",
        "python3 -m scripts.quality.dast_privacy prepare-target \\",
        '--output "$RUNNER_TEMP/nuclei-target.txt"',
    ]


def test_dast_active_scans_reject_pr_controlled_workflow_sources() -> None:
    """Changing a PR label must never expose the configured scan target."""

    workflow = yaml.safe_load(DAST_WORKFLOW_PATH.read_text(encoding="utf-8"))
    triggers = _workflow_triggers(workflow)

    assert set(triggers) == {"schedule", "workflow_dispatch"}
    assert "pull_request" not in triggers
    assert "pull_request_target" not in triggers

    trusted_ref = workflow["jobs"]["verify-trusted-ref"]
    assert trusted_ref["permissions"] == {"contents": "read"}
    validation_step = trusted_ref["steps"][0]
    assert validation_step["env"] == {"WORKFLOW_REF": "${{ github.ref }}"}
    assert 'if [ "$WORKFLOW_REF" != "refs/heads/main" ]; then' in validation_step["run"]
    assert f'echo "::error::{TRUSTED_REF_ERROR}"' in validation_step["run"]
    assert "exit 1" in validation_step["run"]

    for job_name in ("nuclei", "zap"):
        job = workflow["jobs"][job_name]
        assert job["needs"] == "verify-trusted-ref"
        assert job["if"] == "${{ needs.verify-trusted-ref.result == 'success' }}"
        checkout = next(
            step
            for step in job["steps"]
            if step.get("uses", "").startswith("actions/checkout@")
        )
        assert checkout["with"]["ref"] == "${{ github.sha }}"
        expected_sparse_paths = (
            {".github", "scripts/quality"}
            if job_name == "nuclei"
            else {".github/workflows/dast.yml", ".zap", "scripts/quality"}
        )
        assert set(checkout["with"]["sparse-checkout"].split()) == expected_sparse_paths
        assert checkout["with"]["persist-credentials"] is False
        assert checkout["with"]["sparse-checkout-cone-mode"] is False
        if job_name == "zap":
            assert ".zap" in checkout["with"]["sparse-checkout"].split()


def test_nuclei_target_preflight_remains_fail_closed() -> None:
    workflow = yaml.safe_load(DAST_WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["nuclei"]["steps"]
    names = [step["name"] for step in steps]
    preflight = steps[names.index("Validate Nuclei target URL")]
    assert names.index("Validate Nuclei target URL") < names.index("Run Nuclei scan")
    assert preflight["env"] == {"DAST_SECRET_TARGET": "${{ secrets.DAST_TARGET_URL }}"}
    assert preflight.get("continue-on-error", False) is False
    _assert_fail_closed_target_preflight(preflight["run"])


def test_nuclei_dispatch_target_never_appears_in_a_step_preamble() -> None:
    workflow = yaml.safe_load(DAST_WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["nuclei"]["steps"]
    preflight = next(
        step for step in steps if step.get("name") == "Validate Nuclei target URL"
    )

    assert preflight["env"] == {"DAST_SECRET_TARGET": "${{ secrets.DAST_TARGET_URL }}"}
    assert "prepare-target" in preflight["run"]
    for step in steps:
        preamble = json.dumps({"env": step.get("env"), "with": step.get("with")})
        assert "inputs.target_url" not in preamble
        assert "inputs.target_url" not in step.get("run", "")


@pytest.mark.parametrize(
    ("event_name", "inputs", "secret", "expected_target"),
    [
        (
            "workflow_dispatch",
            {"target_url": "https://manual.example.test/private"},
            "https://secret.example.test",
            "https://manual.example.test/private",
        ),
        (
            "workflow_dispatch",
            {"target_url": ""},
            "https://secret.example.test",
            "https://secret.example.test",
        ),
        (
            "schedule",
            None,
            "https://secret.example.test",
            "https://secret.example.test",
        ),
        (
            "workflow_dispatch",
            {"target_url": "https://private.example.test/path?token=hidden"},
            "https://secret.example.test",
            None,
        ),
        ("workflow_dispatch", {"target_url": ""}, "", None),
    ],
)
def test_nuclei_target_preflight_executes_private_selection(
    tmp_path: Path,
    pytester,
    monkeypatch: pytest.MonkeyPatch,
    event_name: str,
    inputs: object,
    secret: str,
    expected_target: str | None,
) -> None:
    workflow = yaml.safe_load(DAST_WORKFLOW_PATH.read_text(encoding="utf-8"))
    step = next(
        item
        for item in workflow["jobs"]["nuclei"]["steps"]
        if item.get("name") == "Validate Nuclei target URL"
    )
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"inputs": inputs}), encoding="utf-8")
    monkeypatch.chdir(REPOSITORY_ROOT)
    monkeypatch.delenv("BASH_ENV", raising=False)
    monkeypatch.delenv("TARGET_URL", raising=False)
    for name, value in {
        "GITHUB_EVENT_NAME": event_name,
        "GITHUB_EVENT_PATH": event.as_posix(),
        "DAST_SECRET_TARGET": secret,
        "RUNNER_TEMP": tmp_path.as_posix(),
        "TEST_GATE_PYTHON": Path(sys.executable).as_posix(),
    }.items():
        monkeypatch.setenv(name, value)
    script = tmp_path / "target-preflight.sh"
    script.write_text(
        'python3() { "$TEST_GATE_PYTHON" "$@"; }\n' + step["run"],
        encoding="utf-8",
        newline="\n",
    )
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    bash = (
        str(git_bash) if os.name == "nt" and git_bash.exists() else shutil.which("bash")
    )
    assert bash
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
    handoff = tmp_path / "nuclei-target.txt"
    assert result.ret == (0 if expected_target is not None else 1)
    assert handoff.exists() is (expected_target is not None)
    if expected_target is not None:
        assert handoff.read_text(encoding="utf-8") == expected_target
    else:
        assert "private.example.test" not in result.stdout.str() + result.stderr.str()


def test_nuclei_nonzero_exit_remains_terminal_after_artifact_uploads() -> None:
    """Network/configuration failures must not be converted into a green DAST run."""

    workflow = yaml.safe_load(DAST_WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["nuclei"]["steps"]
    scan_index, scan = next(
        (index, step)
        for index, step in enumerate(steps)
        if step.get("name") == "Run Nuclei scan"
    )
    assert scan.get("continue-on-error", False) is False
    assert "|| true" not in scan["run"]
    assert "nuclei \\" in scan["run"]

    uploads = {
        step["name"]: (index, step)
        for index, step in enumerate(steps)
        if step.get("name")
        in {
            "Upload results to GitHub Security",
            "Upload sanitized JSON findings",
            "Upload sanitized SARIF report",
        }
    }
    assert len(uploads) == 3
    assert all(scan_index < index for index, _ in uploads.values())
    assert uploads["Upload sanitized JSON findings"][1]["if"] == "always()"
    assert uploads["Upload sanitized SARIF report"][1]["if"] == (
        "${{ always() && hashFiles('nuclei-results.sarif') != '' }}"
    )
    assert uploads["Upload results to GitHub Security"][1]["if"] == (
        "${{ success() && hashFiles('nuclei-results.sarif') != '' }}"
    )


def test_nuclei_requires_sarif_for_any_findings_before_publication() -> None:
    """A clean native export can omit SARIF; findings must have a report."""

    workflow = yaml.safe_load(DAST_WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["nuclei"]["steps"]
    indices = {step["name"]: index for index, step in enumerate(steps)}
    validation = steps[indices["Validate Nuclei report evidence"]]

    assert indices["Run Nuclei scan"] < indices["Validate Nuclei report evidence"]
    assert (
        indices["Validate Nuclei report evidence"]
        < indices["Upload results to GitHub Security"]
    )
    assert validation.get("continue-on-error", False) is False
    assert '"$RUNNER_TEMP/nuclei-results.json"' in validation["run"]
    assert '--check-sarif "$RUNNER_TEMP/nuclei-results.sarif"' in validation["run"]


def test_nuclei_publishes_only_sanitized_reports() -> None:
    workflow = yaml.safe_load(DAST_WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["nuclei"]["steps"]
    indices = {step["name"]: index for index, step in enumerate(steps)}
    scan = steps[indices["Run Nuclei scan"]]
    sanitize = steps[indices["Sanitize Nuclei reports"]]

    assert '-json-export "$RUNNER_TEMP/nuclei-results.json"' in scan["run"]
    assert '-sarif-export "$RUNNER_TEMP/nuclei-results.sarif"' in scan["run"]
    assert '-trace-log "$RUNNER_TEMP/nuclei-trace.jsonl"' in scan["run"]
    assert "-no-color" in scan["run"]
    assert '>"$RUNNER_TEMP/nuclei-stdout.log"' in scan["run"]
    assert '2>"$RUNNER_TEMP/nuclei-stderr.log"' in scan["run"]
    assert "-omit-raw" in scan["run"]
    assert sanitize["if"] == "${{ always() }}"
    assert "env" not in sanitize
    assert 'DAST_TARGET_FILE="$RUNNER_TEMP/nuclei-target.txt"' in sanitize["run"]
    assert "python3 -m scripts.quality.dast_privacy sanitize" in sanitize["run"]
    assert '--json-in "$RUNNER_TEMP/nuclei-results.json"' in sanitize["run"]
    assert '--sarif-in "$RUNNER_TEMP/nuclei-results.sarif"' in sanitize["run"]
    assert "--json-out nuclei-results.json" in sanitize["run"]
    assert "--sarif-out nuclei-results.sarif" in sanitize["run"]
    assert indices["Run Nuclei scan"] < indices["Sanitize Nuclei reports"]
    assert (
        indices["Sanitize Nuclei reports"]
        < indices["Upload results to GitHub Security"]
    )


def test_nuclei_completion_is_bound_to_the_event_checkout_before_publication() -> None:
    workflow = yaml.safe_load(DAST_WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["nuclei"]["steps"]
    indices = {step["name"]: index for index, step in enumerate(steps)}
    scan = steps[indices["Run Nuclei scan"]]
    check = steps[indices["Validate Nuclei scan completion"]]

    assert scan["id"] == "nuclei_scan"
    assert check["if"] == "${{ always() }}"
    assert check["env"] == {
        "SCAN_OUTCOME": "${{ steps.nuclei_scan.outcome }}",
    }
    assert '"$(git rev-parse HEAD)" != "$GITHUB_SHA"' in check["run"]
    assert "python3 -m scripts.quality.dast_privacy verify-scan" in check["run"]
    assert 'DAST_TARGET_FILE="$RUNNER_TEMP/nuclei-target.txt"' in check["run"]
    assert '--trace-in "$RUNNER_TEMP/nuclei-trace.jsonl"' in check["run"]
    assert '--log-in "$RUNNER_TEMP/nuclei-stderr.log"' in check["run"]
    assert '--summary-file "$GITHUB_STEP_SUMMARY"' in check["run"]
    assert check.get("continue-on-error", False) is False
    assert indices["Run Nuclei scan"] < indices["Validate Nuclei scan completion"]
    assert (
        indices["Validate Nuclei scan completion"]
        < indices["Validate Nuclei report evidence"]
        < indices["Upload results to GitHub Security"]
    )
    uploads = [
        step["with"]["path"]
        for step in steps
        if step.get("uses", "").startswith("actions/upload-artifact@")
    ]
    assert set(uploads) == {"nuclei-results.json", "nuclei-results.sarif"}


@pytest.mark.parametrize(
    ("outcome", "request_error", "matching_source", "expected"),
    [
        ("success", "none", True, 0),
        ("success", "connection refused", True, 1),
        ("success", "none", False, 1),
        ("failure", "none", True, 1),
    ],
)
def test_nuclei_completion_workflow_executes_the_validator(
    tmp_path: Path,
    pytester,
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
    request_error: str,
    matching_source: bool,
    expected: int,
) -> None:
    workflow = yaml.safe_load(DAST_WORKFLOW_PATH.read_text(encoding="utf-8"))
    check = next(
        step
        for step in workflow["jobs"]["nuclei"]["steps"]
        if step.get("name") == "Validate Nuclei scan completion"
    )
    target = "https://stage.example.test/private-area"
    (tmp_path / "nuclei-target.txt").write_text(target, encoding="utf-8")
    (tmp_path / "nuclei-trace.jsonl").write_text(
        json.dumps(
            {
                "template": "example.yaml",
                "type": "http",
                "input": f"{target}/proof",
                "address": "stage.example.test:443",
                "error": request_error,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "nuclei-stderr.log").write_text(
        "[INF] Scan completed in 1s. No results found.\n", encoding="utf-8"
    )
    source_result = pytester.run("git", "-C", str(REPOSITORY_ROOT), "rev-parse", "HEAD")
    assert source_result.ret == 0
    source_sha = source_result.stdout.str().strip()
    assert re.fullmatch(r"[0-9a-f]{40}", source_sha)
    if not matching_source:
        source_sha = "0" * 40 if source_sha != "0" * 40 else "1" * 40
    monkeypatch.chdir(REPOSITORY_ROOT)
    monkeypatch.delenv("BASH_ENV", raising=False)
    for name, value in {
        "SCAN_OUTCOME": outcome,
        "GITHUB_SHA": source_sha,
        "RUNNER_TEMP": tmp_path.as_posix(),
        "GITHUB_STEP_SUMMARY": (tmp_path / "summary.md").as_posix(),
        "TEST_GATE_PYTHON": Path(sys.executable).as_posix(),
    }.items():
        monkeypatch.setenv(name, value)
    script = tmp_path / "actual-completion-check.sh"
    script.write_text(
        'python3() { "$TEST_GATE_PYTHON" "$@"; }\n' + check["run"],
        encoding="utf-8",
        newline="\n",
    )
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    bash = (
        str(git_bash) if os.name == "nt" and git_bash.exists() else shutil.which("bash")
    )
    assert bash, "Real Bash is required to execute the Nuclei completion gate"
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
    assert result.ret == expected
    assert target not in result.stdout.str() + result.stderr.str()
    assert (tmp_path / "summary.md").exists() is (expected == 0)


def _nuclei_scan_contract_options(command: str) -> tuple[list[str], set[str]]:
    """Normalize supported flag aliases and attached values from a Nuclei command."""

    continued = " ".join(
        line.rstrip().removesuffix("\\") for line in command.splitlines()
    )
    tokens = shlex.split(continued)
    template_roots: list[str] = []
    forbidden_options: set[str] = set()
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            break
        option, separator, inline_value = token.partition("=")
        dash_count = len(option) - len(option.lstrip("-"))
        if dash_count in (1, 2):
            name = option[dash_count:]
            if name in {"t", "templates"}:
                if separator:
                    template_root = inline_value
                else:
                    index += 1
                    assert index < len(tokens), f"{token} requires a template root"
                    template_root = tokens[index]
                    assert not template_root.startswith("-"), (
                        f"{token} requires a template root"
                    )
                assert template_root, f"{token} requires a non-empty template root"
                template_roots.append(template_root)
            elif name in {"code", "dast", "fuzz"}:
                forbidden_options.add(name)
        index += 1
    return template_roots, forbidden_options


def test_nuclei_option_parser_normalizes_supported_aliases_and_inline_values() -> None:
    """All documented flag spellings participate in the DAST contract."""

    template_roots, forbidden_options = _nuclei_scan_contract_options(
        "nuclei -t cves/ --t=exposures/ -templates misconfiguration/ "
        "--templates=vulnerabilities/ -t=network/ -code --code=false "
        "-dast=true --dast -fuzz=true --fuzz"
    )

    assert template_roots == [
        "cves/",
        "exposures/",
        "misconfiguration/",
        "vulnerabilities/",
        "network/",
    ]
    assert forbidden_options == {"code", "dast", "fuzz"}


def test_nuclei_pins_signed_official_template_compatible_release() -> None:
    """Keep Nuclei on a release that accepts signed official JS templates."""

    workflow = yaml.safe_load(DAST_WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["nuclei"]["steps"]
    setup = next(step for step in steps if step.get("name") == "Set up Nuclei")
    scan = next(step for step in steps if step.get("name") == "Run Nuclei scan")

    assert set(setup["with"]) == {"version", "install-only"}
    assert re.fullmatch(r"v?\d+\.\d+\.\d+", str(setup["with"]["version"]))
    assert setup["with"]["install-only"] is True

    template_roots, forbidden_options = _nuclei_scan_contract_options(scan["run"])
    assert template_roots == [
        "cves/",
        "exposures/",
        "misconfiguration/",
        "vulnerabilities/",
        "network/",
    ]
    assert forbidden_options == set()


PUBLIC_FILES = [
    "zap-public/zap-results.sarif",
    "zap-public/zap-evidence.txt",
    "zap-public/zap-sarif-provenance.json",
]
VERIFIED_UPLOAD = (
    "${{ always() && steps.zap_prepare.outcome == 'success' "
    "&& steps.zap_verify.outcome == 'success' }}"
)


def _assert_zap_pipeline(workflow: dict) -> None:
    """Publication must have one narrow, independently verified producer."""
    job = workflow["jobs"]["zap"]
    assert job["permissions"] == {"contents": "read", "security-events": "write"}
    assert job["needs"] == "verify-trusted-ref"
    assert job["if"] == "${{ needs.verify-trusted-ref.result == 'success' }}"
    assert job["timeout-minutes"] == 60
    assert "env" not in job and "env" not in workflow
    steps = job["steps"]
    assert len(steps) == 6
    checkout, prepare, verify, sarif, artifact, gate = steps
    assert (
        checkout["uses"] == "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
    )
    assert prepare["id"] == "zap_prepare"
    assert prepare["env"] == {"DAST_SECRET_TARGET": "${{ secrets.DAST_TARGET_URL }}"}
    assert "if" not in prepare
    assert verify["id"] == "zap_verify"
    assert verify["if"] == "${{ always() && steps.zap_prepare.outcome == 'success' }}"
    assert gate["name"] == "Fail on medium or high ZAP findings"
    assert gate["if"] == "${{ always() }}"
    for step, command in ((prepare, "prepare"), (verify, "verify"), (gate, "gate")):
        assert step["shell"] == "bash"
        expected = [
            "set",
            "-euo",
            "pipefail",
            "python3",
            "-m",
            "scripts.quality.zap_workflow",
            command,
            "--repo-root",
            "$GITHUB_WORKSPACE",
            "--work",
            "$RUNNER_TEMP/zap-private",
            "--public",
            "$GITHUB_WORKSPACE/zap-public",
        ]
        if command != "verify":
            expected += ["--summary-file", "$GITHUB_STEP_SUMMARY"]
        assert shlex.split(step["run"].replace("\\\n", " ")) == expected
    for step in steps:
        preamble = json.dumps({"env": step.get("env"), "with": step.get("with")})
        assert "inputs.target_url" not in preamble
        assert "inputs.target_url" not in step.get("run", "")
        assert step.get("continue-on-error", False) is False
        if step is not prepare:
            assert "env" not in step
        assert "${{" not in step.get("run", "")
    assert (
        sarif["uses"]
        == "github/codeql-action/upload-sarif@9b3254085494b55a0f7c4c2b3d2d52cc712ce370"
    )
    assert (
        artifact["uses"]
        == "actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9"
    )
    assert sarif["if"] == artifact["if"] == VERIFIED_UPLOAD
    assert sarif["with"] == {"sarif_file": PUBLIC_FILES[0], "category": "zap-dast"}
    assert artifact["with"] == {
        "name": "zap-results-${{ github.run_id }}-attempt-${{ github.run_attempt }}",
        "path": "\n".join(PUBLIC_FILES) + "\n",
        "retention-days": 90,
        "if-no-files-found": "error",
    }


def test_zap_private_prepare_verify_publish_threshold_pipeline() -> None:
    _assert_zap_pipeline(yaml.safe_load(DAST_WORKFLOW_PATH.read_text(encoding="utf-8")))


@pytest.mark.parametrize(
    "mutation",
    [
        "raw_upload",
        "directory_upload",
        "skip_verify",
        "ignore_failure",
        "target_in_verify",
        "public_work",
        "gate_before_upload",
        "issue_permission",
        "unpin_action",
        "extra_publisher",
        "target_in_shell",
        "target_in_prepare_env",
        "target_in_action_input",
    ],
)
def test_zap_pipeline_contract_rejects_privacy_and_ordering_regressions(
    mutation: str,
) -> None:
    workflow = copy.deepcopy(
        yaml.safe_load(DAST_WORKFLOW_PATH.read_text(encoding="utf-8"))
    )
    job = workflow["jobs"]["zap"]
    steps = job["steps"]
    if mutation == "raw_upload":
        steps[4]["with"]["path"] += "$RUNNER_TEMP/zap-private/report_json.json\n"
    elif mutation == "directory_upload":
        steps[4]["with"]["path"] = "zap-public/"
    elif mutation == "skip_verify":
        steps[3]["if"] = "${{ always() }}"
    elif mutation == "ignore_failure":
        steps[1]["continue-on-error"] = True
    elif mutation == "target_in_verify":
        steps[2]["env"] = {"TARGET_URL": TARGET_EXPRESSION}
    elif mutation == "public_work":
        steps[1]["run"] = steps[1]["run"].replace(
            "$RUNNER_TEMP/zap-private", "$GITHUB_WORKSPACE"
        )
    elif mutation == "gate_before_upload":
        steps[3], steps[5] = steps[5], steps[3]
    elif mutation == "issue_permission":
        job["permissions"]["issues"] = "write"
    elif mutation == "unpin_action":
        steps[4]["uses"] = "actions/upload-artifact@main"
    elif mutation == "target_in_prepare_env":
        steps[1]["env"] = {"TARGET_URL": TARGET_EXPRESSION}
    elif mutation == "target_in_action_input":
        steps[3]["with"]["target"] = TARGET_EXPRESSION
    elif mutation == "extra_publisher":
        steps.append(copy.deepcopy(steps[4]))
    else:
        steps[1]["run"] += "echo " + TARGET_EXPRESSION
    with pytest.raises(AssertionError):
        _assert_zap_pipeline(workflow)


@pytest.mark.parametrize("command", ["prepare", "verify", "gate"])
@pytest.mark.parametrize("exit_code", [0, 1, 2, 7])
def test_zap_real_shell_preserves_cli_arguments_and_failure(
    tmp_path: Path,
    pytester,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    exit_code: int,
) -> None:
    """Execute actual workflow shell without running Docker or contacting a target."""
    workflow = yaml.safe_load(DAST_WORKFLOW_PATH.read_text(encoding="utf-8"))
    step = workflow["jobs"]["zap"]["steps"][
        {"prepare": 1, "verify": 2, "gate": 5}[command]
    ]
    workspace = tmp_path / "workspace with spaces"
    private = tmp_path / "private with spaces"
    summary = tmp_path / "summary with spaces.md"
    log = tmp_path / "argv.json"
    monkeypatch.delenv("BASH_ENV", raising=False)
    for key, value in {
        "GITHUB_WORKSPACE": str(workspace),
        "RUNNER_TEMP": str(private),
        "GITHUB_STEP_SUMMARY": str(summary),
        "SPY_LOG": str(log),
        "SPY_EXIT": str(exit_code),
        "TEST_GATE_PYTHON": sys.executable,
    }.items():
        monkeypatch.setenv(key, value)
    spy = tmp_path / "spy.py"
    spy.write_text(
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "Path(os.environ['SPY_LOG']).write_text(json.dumps(sys.argv[1:]))\n"
        "raise SystemExit(int(os.environ['SPY_EXIT']))\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SPY_SCRIPT", str(spy))
    script = tmp_path / "workflow.sh"
    script.write_text(
        'python3() { "$TEST_GATE_PYTHON" "$SPY_SCRIPT" "$@"; }\n' + step["run"],
        encoding="utf-8",
    )
    bash = shutil.which("bash")
    assert bash
    result = pytester.run(bash, "--noprofile", "--norc", str(script), timeout=20)
    assert result.ret == exit_code
    expected = [
        "-m",
        "scripts.quality.zap_workflow",
        command,
        "--repo-root",
        str(workspace),
        "--work",
        str(private / "zap-private"),
        "--public",
        str(workspace / "zap-public"),
    ]
    if command != "verify":
        expected += ["--summary-file", str(summary)]
    assert json.loads(log.read_text(encoding="utf-8")) == expected
