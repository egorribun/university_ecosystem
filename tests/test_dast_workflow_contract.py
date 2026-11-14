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
TRUSTED_REF_ERROR = "DAST scans must run from the protected main ref."
pytest_plugins = ("pytester",)


def _workflow_triggers(workflow: dict[str, object]) -> dict[str, object]:
    """PyYAML parses the YAML 1.1 key ``on`` as boolean True."""

    triggers = workflow.get("on", workflow.get(True))
    assert isinstance(triggers, dict)
    return triggers


PREFLIGHT_LINES = [
    "set -euo pipefail",
    "python3 -m scripts.quality.dast_privacy prepare-target \\",
    '--status-in "$RUNNER_TEMP/dast-stand-status.txt" \\',
    '--output "$RUNNER_TEMP/nuclei-target.txt"',
]
CHECKOUT_NAME = "Check out the event commit without persisting credentials"
START_NAME = "Start the owned ephemeral DAST stand"
STATUS_NAME = "Read the owned stand status privately"
TEARDOWN_NAME = "Stop and remove the owned DAST stand"
NUCLEI_PREFLIGHT_NAME = "Prepare the owned stand target for Nuclei"
ZAP_PREPARE_NAME = "Prepare private ZAP scan and sanitized evidence"
TELEMETRY_START_NAME = "Start DAST runner memory telemetry"
TELEMETRY_STOP_NAME = "Stop DAST runner memory telemetry and summarize"
TELEMETRY_UPLOAD_NAME = "Upload DAST runner memory telemetry"
ZAP_RESOURCES_NAME = "Record ZAP container resources if it still exists"


def _steps(workflow: dict[str, object], job_name: str) -> list[dict[str, object]]:
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    job = jobs[job_name]
    assert isinstance(job, dict)
    steps = job["steps"]
    assert isinstance(steps, list)
    return steps


def _step(steps: list[dict[str, object]], name: str) -> dict[str, object]:
    matches = [step for step in steps if step.get("name") == name]
    assert len(matches) == 1, name
    return matches[0]


def _assert_owned_stand_target_preflight(preflight_script: str) -> None:
    """The scanner receives only the loopback base URL from private stand status."""
    shell_lines = [
        line.strip()
        for line in preflight_script.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert shell_lines == PREFLIGHT_LINES


def test_dast_active_scans_reject_pr_controlled_workflow_sources() -> None:
    """Changing a PR label must never authorize a scan of anything but the owned stand."""

    workflow = yaml.safe_load(DAST_WORKFLOW_PATH.read_text(encoding="utf-8"))
    triggers = _workflow_triggers(workflow)

    assert set(triggers) == {"schedule", "workflow_dispatch"}
    assert triggers["workflow_dispatch"] is None
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
        checkout = _step(_steps(workflow, job_name), CHECKOUT_NAME)
        # The owned stand is built from the checkout, so the full event commit is required.
        assert checkout["uses"] == (
            "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
        )
        assert checkout["with"] == {
            "fetch-depth": 0,
            "persist-credentials": False,
            "ref": "${{ github.sha }}",
        }


@pytest.mark.parametrize("job_name", ["nuclei", "zap"])
def test_each_scanner_job_starts_and_tears_down_its_own_owned_stand(
    job_name: str,
) -> None:
    workflow = yaml.safe_load(DAST_WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = _steps(workflow, job_name)
    names = [step.get("name") for step in steps]

    start = _step(steps, START_NAME)
    assert start["id"] == "start-stand"
    assert "STAND_REF" in start["env"]
    for fragment in (
        "scripts.live_stand up",
        "--in-place",
        '--state-dir "$LIVE_STATE_DIR"',
        '--ref "$STAND_REF"',
        "--stack core",
    ):
        assert fragment in start["run"]

    status = _step(steps, STATUS_NAME)
    assert "scripts.live_stand status" in status["run"]
    assert '--state-dir "$LIVE_STATE_DIR"' in status["run"]
    assert '>"$RUNNER_TEMP/dast-stand-status.txt"' in status["run"]

    teardown = _step(steps, TEARDOWN_NAME)
    assert teardown["id"] == "stop-stand"
    assert teardown["if"] == "${{ always() && steps.start-stand.outcome != 'skipped' }}"
    assert "scripts.live_stand teardown" in teardown["run"]
    assert '--state-dir "$LIVE_STATE_DIR"' in teardown["run"]

    scan_name = "Run Nuclei scan" if job_name == "nuclei" else ZAP_PREPARE_NAME
    assert (
        names.index(START_NAME)
        < names.index(STATUS_NAME)
        < names.index(scan_name)
        < names.index(TEARDOWN_NAME)
    )
    for step in steps:
        assert "DAST_TARGET_URL" not in json.dumps(step)
        assert "DAST_SECRET_TARGET" not in json.dumps(step)


def test_nuclei_stand_target_preflight_is_fail_closed_and_status_bound() -> None:
    workflow = yaml.safe_load(DAST_WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = _steps(workflow, "nuclei")
    names = [step["name"] for step in steps]
    preflight = _step(steps, NUCLEI_PREFLIGHT_NAME)
    assert names.index(START_NAME) < names.index(STATUS_NAME)
    assert names.index(STATUS_NAME) < names.index(NUCLEI_PREFLIGHT_NAME)
    assert names.index(NUCLEI_PREFLIGHT_NAME) < names.index("Run Nuclei scan")
    assert "env" not in preflight
    assert preflight.get("continue-on-error", False) is False
    _assert_owned_stand_target_preflight(preflight["run"])


def test_no_external_dast_target_source_remains() -> None:
    """Scans reach only the owned stand; no secret or dispatch input can redirect them."""

    text = DAST_WORKFLOW_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "DAST_TARGET_URL",
        "DAST_SECRET_TARGET",
        "inputs.target_url",
        "target_url",
    ):
        assert forbidden not in text
    workflow = yaml.safe_load(text)
    assert _workflow_triggers(workflow)["workflow_dispatch"] is None


@pytest.mark.parametrize(
    ("status_text", "expected_target"),
    [
        ("LIVE_BASE_URL=http://localhost:20000\n", "http://localhost:20000"),
        (
            "+ docker compose ps\n"
            "LIVE_BASE_URL=http://localhost:45000\n"
            "LIVE_MAILPIT_URL=http://127.0.0.1:18025\n",
            "http://localhost:45000",
        ),
        ("LIVE_BASE_URL=https://secret.example.test\n", None),
        (
            "LIVE_BASE_URL=http://localhost:20000\nLIVE_BASE_URL=http://localhost:20001\n",
            None,
        ),
        ("", None),
    ],
)
def test_nuclei_stand_target_preflight_executes_on_private_status(
    tmp_path: Path,
    pytester,
    monkeypatch: pytest.MonkeyPatch,
    status_text: str,
    expected_target: str | None,
) -> None:
    workflow = yaml.safe_load(DAST_WORKFLOW_PATH.read_text(encoding="utf-8"))
    step = _step(_steps(workflow, "nuclei"), NUCLEI_PREFLIGHT_NAME)
    (tmp_path / "dast-stand-status.txt").write_text(status_text, encoding="utf-8")
    monkeypatch.chdir(REPOSITORY_ROOT)
    monkeypatch.delenv("BASH_ENV", raising=False)
    monkeypatch.delenv("TARGET_URL", raising=False)
    for name, value in {
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
        assert "secret.example.test" not in result.stdout.str() + result.stderr.str()


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
ZAP_STEP_ORDER = (
    CHECKOUT_NAME,
    "Set up Python",
    "Install uv",
    "Install locked Python runtime dependencies",
    "Select unique owned DAST state directory",
    START_NAME,
    STATUS_NAME,
    TELEMETRY_START_NAME,
    ZAP_PREPARE_NAME,
    ZAP_RESOURCES_NAME,
    TEARDOWN_NAME,
    TELEMETRY_STOP_NAME,
    "Verify ZAP public evidence and provenance",
    "Upload ZAP SARIF to GitHub Security",
    "Upload verified ZAP public evidence",
    TELEMETRY_UPLOAD_NAME,
    "Fail on medium or high ZAP findings",
)
ZAP_GATE_NAME = "Fail on medium or high ZAP findings"
ZAP_VERIFY_NAME = "Verify ZAP public evidence and provenance"
ZAP_SARIF_NAME = "Upload ZAP SARIF to GitHub Security"
ZAP_ARTIFACT_NAME = "Upload verified ZAP public evidence"


def _assert_zap_pipeline(workflow: dict) -> None:
    """Publication must have one narrow, independently verified producer."""
    job = workflow["jobs"]["zap"]
    assert job["permissions"] == {"contents": "read", "security-events": "write"}
    assert job["needs"] == "verify-trusted-ref"
    assert job["if"] == "${{ needs.verify-trusted-ref.result == 'success' }}"
    assert job["timeout-minutes"] == 150
    assert "env" not in job and "env" not in workflow
    steps = job["steps"]
    assert [step.get("name") for step in steps] == list(ZAP_STEP_ORDER)
    by_name = {step["name"]: step for step in steps}
    start = by_name[START_NAME]
    assert start["id"] == "start-stand"
    assert "--stack core" in start["run"]
    prepare = by_name[ZAP_PREPARE_NAME]
    verify = by_name[ZAP_VERIFY_NAME]
    gate = by_name[ZAP_GATE_NAME]
    teardown = by_name[TEARDOWN_NAME]
    assert prepare["id"] == "zap_prepare"
    assert verify["id"] == "zap_verify"
    assert verify["if"] == "${{ always() && steps.zap_prepare.outcome == 'success' }}"
    assert teardown["if"] == "${{ always() && steps.start-stand.outcome != 'skipped' }}"
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
        if command == "prepare":
            expected += ["--status-in", "$RUNNER_TEMP/dast-stand-status.txt"]
        if command != "verify":
            expected += ["--summary-file", "$GITHUB_STEP_SUMMARY"]
        assert shlex.split(step["run"].replace("\\\n", " ")) == expected
    for step in steps:
        preamble = json.dumps({"env": step.get("env"), "with": step.get("with")})
        assert "inputs.target_url" not in preamble
        assert "DAST_TARGET_URL" not in json.dumps(step)
        assert "DAST_SECRET_TARGET" not in json.dumps(step)
        assert "inputs.target_url" not in step.get("run", "")
        assert step.get("continue-on-error", False) is False
        assert "${{" not in step.get("run", "")
        if step is not start:
            assert "env" not in step
    sarif = by_name[ZAP_SARIF_NAME]
    artifact = by_name[ZAP_ARTIFACT_NAME]
    assert (
        sarif["uses"]
        == "github/codeql-action/upload-sarif@33d7b85da1a04171e211befe2c739303b9a4c066"
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


def test_dast_sarif_categories_and_retention_remain_pinned() -> None:
    workflow = yaml.safe_load(DAST_WORKFLOW_PATH.read_text(encoding="utf-8"))
    categories: set[str] = set()
    for job_name in ("nuclei", "zap"):
        for step in _steps(workflow, job_name):
            uses = str(step.get("uses", ""))
            if uses.startswith("github/codeql-action/upload-sarif@"):
                categories.add(step["with"]["category"])
            if uses.startswith("actions/upload-artifact@"):
                # Runner telemetry is diagnostic only and keeps short retention.
                expected_retention = (
                    7 if step.get("name") == TELEMETRY_UPLOAD_NAME else 90
                )
                assert step["with"]["retention-days"] == expected_retention
    assert categories == {"nuclei-dast", "zap-dast"}


@pytest.mark.parametrize(
    "mutation",
    [
        "raw_upload",
        "directory_upload",
        "skip_verify",
        "ignore_failure",
        "target_in_verify",
        "external_target_secret",
        "target_in_shell",
        "target_in_action_input",
        "public_work",
        "gate_before_upload",
        "teardown_before_scan",
        "skip_teardown",
        "issue_permission",
        "unpin_action",
        "extra_publisher",
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
    by_name = {step["name"]: step for step in steps}
    artifact = by_name[ZAP_ARTIFACT_NAME]
    if mutation == "raw_upload":
        artifact["with"]["path"] += "$RUNNER_TEMP/zap-private/report_json.json\n"
    elif mutation == "directory_upload":
        artifact["with"]["path"] = "zap-public/"
    elif mutation == "skip_verify":
        by_name[ZAP_VERIFY_NAME]["if"] = "${{ always() }}"
    elif mutation == "ignore_failure":
        by_name[ZAP_PREPARE_NAME]["continue-on-error"] = True
    elif mutation == "target_in_verify":
        by_name[ZAP_VERIFY_NAME]["env"] = {
            "TARGET_URL": "${{ secrets.DAST_TARGET_URL }}"
        }
    elif mutation == "external_target_secret":
        by_name[ZAP_PREPARE_NAME]["env"] = {
            "DAST_SECRET_TARGET": "${{ secrets.DAST_TARGET_URL }}"
        }
    elif mutation == "target_in_shell":
        by_name[ZAP_PREPARE_NAME]["run"] += "echo ${{ secrets.DAST_TARGET_URL }}\n"
    elif mutation == "target_in_action_input":
        by_name[ZAP_SARIF_NAME]["with"]["target"] = "${{ inputs.target_url }}"
    elif mutation == "public_work":
        by_name[ZAP_PREPARE_NAME]["run"] = by_name[ZAP_PREPARE_NAME]["run"].replace(
            "$RUNNER_TEMP/zap-private", "$GITHUB_WORKSPACE"
        )
    elif mutation == "gate_before_upload":
        gate_index = steps.index(by_name[ZAP_GATE_NAME])
        sarif_index = steps.index(by_name[ZAP_SARIF_NAME])
        steps[gate_index], steps[sarif_index] = steps[sarif_index], steps[gate_index]
    elif mutation == "teardown_before_scan":
        teardown_index = steps.index(by_name[TEARDOWN_NAME])
        scan_index = steps.index(by_name[ZAP_PREPARE_NAME])
        steps.insert(scan_index, steps.pop(teardown_index))
    elif mutation == "skip_teardown":
        by_name[TEARDOWN_NAME]["if"] = "${{ success() }}"
    elif mutation == "issue_permission":
        job["permissions"]["issues"] = "write"
    elif mutation == "unpin_action":
        artifact["uses"] = "actions/upload-artifact@main"
    else:
        steps.append(copy.deepcopy(artifact))
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
    step_name = {
        "prepare": ZAP_PREPARE_NAME,
        "verify": ZAP_VERIFY_NAME,
        "gate": ZAP_GATE_NAME,
    }[command]
    step = _step(_steps(workflow, "zap"), step_name)
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
    if command == "prepare":
        expected += ["--status-in", str(private / "dast-stand-status.txt")]
    if command != "verify":
        expected += ["--summary-file", str(summary)]
    assert json.loads(log.read_text(encoding="utf-8")) == expected


def test_zap_runner_telemetry_observes_without_changing_scan_outcome() -> None:
    """AUD-381 telemetry records runner memory but cannot alter pass/fail."""

    workflow = yaml.safe_load(DAST_WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = _steps(workflow, "zap")
    by_name = {step["name"]: step for step in steps}
    start = by_name[TELEMETRY_START_NAME]
    stop = by_name[TELEMETRY_STOP_NAME]
    upload = by_name[TELEMETRY_UPLOAD_NAME]
    resources = by_name[ZAP_RESOURCES_NAME]

    assert start["shell"] == "bash"
    assert "scripts/quality/dast_memory_sampler.py sample" in start["run"]
    assert "--stop-file" in start["run"]
    assert start["run"].rstrip().endswith('"$!" >"$RUNNER_TEMP/dast-memory.pid"')
    assert stop["if"] == upload["if"] == resources["if"] == "${{ always() }}"
    assert "dast_memory_sampler.py summarize" in stop["run"]
    assert "$GITHUB_STEP_SUMMARY" in stop["run"]
    assert upload["uses"] == (
        "actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9"
    )
    assert upload["with"]["if-no-files-found"] == "warn"
    assert "runner.temp" in upload["with"]["path"]
    assert workflow["jobs"]["zap"]["permissions"] == {
        "contents": "read",
        "security-events": "write",
    }
    for step in (start, stop, upload, resources):
        assert step.get("continue-on-error", False) is False
        assert "env" not in step
    assert by_name[ZAP_PREPARE_NAME]["id"] == "zap_prepare"
