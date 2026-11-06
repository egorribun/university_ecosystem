"""Fail-closed and privacy contracts for the AUD-178/449 proof wiring."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
TEST_NAME = "test_real_gunicorn_worker_emitted_logs_exclude_reset_and_oauth_targets"
CASE_CLASS = "tests.aud178_449_gunicorn_proof"
CANARY = "PRIVACYDIAGNOSTICPROBE"
RECEIPT_VALIDATOR_PATH = ".github/scripts/ci/verify_aud178_449_gunicorn_receipt.py"
pytest_plugins = ("pytester",)


def _proof_step() -> tuple[dict, dict]:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    job = workflow["jobs"]["caddy-emitted-log-proof"]
    steps = [
        step
        for step in job["steps"]
        if step.get("name") == "Run Gunicorn emitted-log redaction proof"
    ]
    assert len(steps) == 1
    return workflow, steps[0]


def test_gunicorn_proof_runs_in_the_required_caddy_job_without_a_new_check() -> None:
    workflow, step = _proof_step()
    job = workflow["jobs"]["caddy-emitted-log-proof"]
    assert job["name"] == "Caddy emitted-log redaction proof"
    assert job["runs-on"] == "ubuntu-24.04"
    assert job["needs"] == "pre-commit-check"
    assert "caddy-emitted-log-proof" in workflow["jobs"]["ci-success"]["needs"]
    assert "if" not in step and "continue-on-error" not in step
    assert step["shell"] == "bash"
    script = step["run"]
    assert "uv run --frozen --no-sync pytest --noconftest" in script
    assert f"tests/aud178_449_gunicorn_proof.py::{TEST_NAME}" in script
    assert "-n 0 -q --tb=no --show-capture=no -p no:cacheprovider" in script
    assert (
        '--basetemp="$proof_root/pytest" --junitxml="$proof_root/receipt.xml"' in script
    )
    assert "umask 077" in script and "trap 'rm -rf -- \"$proof_root\"' EXIT" in script
    assert ">/dev/null 2>&1; then" in script
    assert "Gunicorn emitted-log proof receipt rejected" in script
    assert (
        f"uv run --frozen --no-sync python -I {RECEIPT_VALIDATOR_PATH} "
        '"$proof_root/receipt.xml"'
    ) in script


@pytest.mark.parametrize(
    "case",
    [
        "valid",
        "missing",
        "skipped",
        "child_skipped",
        "failure",
        "error",
        "wrong_name",
        "wrong_class",
        "duplicate",
        "zero",
        "extra_count",
        "malformed",
        "oversized",
        "extra_suite",
    ],
)
def test_gunicorn_receipt_validation_is_fail_closed(
    tmp_path: Path, pytester: pytest.Pytester, case: str
) -> None:
    _proof_step()
    validator = (ROOT / RECEIPT_VALIDATOR_PATH).read_text(encoding="utf-8")
    receipt = tmp_path / "receipt.xml"
    root = ET.Element("testsuites")
    counts = {"tests": "1", "failures": "0", "errors": "0", "skipped": "0"}
    if case == "skipped":
        counts["skipped"] = "1"
    elif case == "failure":
        counts["failures"] = "1"
    elif case == "error":
        counts["errors"] = "1"
    elif case == "zero":
        counts["tests"] = "0"
    elif case == "extra_count":
        counts["tests"] = "2"
    suite = ET.SubElement(root, "testsuite", counts)
    item = ET.SubElement(
        suite,
        "testcase",
        {
            "classname": "wrong.class" if case == "wrong_class" else CASE_CLASS,
            "name": "wrong_test" if case == "wrong_name" else TEST_NAME,
        },
    )
    if case in {"skipped", "child_skipped"}:
        ET.SubElement(item, "skipped")
    elif case in {"failure", "error"}:
        ET.SubElement(item, case)
    elif case == "duplicate":
        ET.SubElement(suite, "testcase", {"classname": CASE_CLASS, "name": TEST_NAME})
    elif case == "extra_suite":
        ET.SubElement(root, "testsuite", counts)
    if case == "malformed":
        receipt.write_text("<bad", encoding="utf-8")
    elif case == "oversized":
        receipt.write_text("x" * 131_073, encoding="utf-8")
    elif case != "missing":
        ET.ElementTree(root).write(receipt, encoding="utf-8")
    with tempfile.TemporaryFile(mode="w+b") as output:
        process = pytester.popen(
            [sys.executable, "-c", validator, str(receipt)],
            stdout=output,
            stderr=output,
        )
        try:
            status = process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
            raise
    assert (status == 0) is (case == "valid")


@pytest.mark.parametrize(
    "mode",
    [
        "csp_positive",
        "csp_negative",
        "csp_unexpected",
        "csp_malformed",
        "gunicorn_assertion",
        "gunicorn_unexpected",
    ],
)
def test_proof_failures_keep_canary_out_of_pytest_and_junit(
    tmp_path: Path,
    pytester: pytest.Pytester,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    # Start a fresh pytest with real assertion rewriting and --showlocals. The
    # caller inspects output privately even if a regression exposes the canary.
    config = tmp_path / "pytest.ini"
    config.write_text("[pytest]\n", encoding="utf-8")
    child = tmp_path / "test_child.py"
    child.write_text(
        f"ROOT = {str(ROOT)!r}\nMODE = {mode!r}\nCANARY = {CANARY!r}\n"
        + """
import importlib
import sys
import pytest

pytest_plugins = ("pytester",)
sys.path.insert(0, ROOT)
name = "tests.aud178_449_gunicorn_proof" if MODE.startswith("gunicorn") else "tests.test_aud178_449_emitted_logs"
pytest.register_assert_rewrite(name)
subject = importlib.import_module(name)

def test_probe(monkeypatch, tmp_path, pytester):
    if MODE.startswith("gunicorn"):
        def explode(*args, **kwargs):
            if MODE == "gunicorn_assertion":
                raise AssertionError(CANARY)
            raise RuntimeError(CANARY)
        monkeypatch.setattr(subject, "_assert_real_gunicorn_worker_emitted_logs_exclude_reset_and_oauth_targets", explode)
        subject.test_real_gunicorn_worker_emitted_logs_exclude_reset_and_oauth_targets(tmp_path, pytester, monkeypatch)
        return
    monkeypatch.setattr(subject.secrets, "token_hex", lambda _: CANARY)
    def probe(reports, _pytester, *, unsafe):
        if MODE == "csp_positive":
            return CANARY
        if MODE == "csp_unexpected":
            raise RuntimeError(CANARY)
        if unsafe or MODE == "csp_negative":
            return str(reports)
        return '{"csp_violation":' + CANARY
    monkeypatch.setattr(subject, "_run_csp_report_probe", probe)
    subject.test_csp_report_emitted_logs_remove_legacy_tokens_from_all_uri_fields(pytester)
""",
        encoding="utf-8",
    )
    receipt = tmp_path / "privacy.xml"
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    monkeypatch.setenv("PYTHONPATH", str(ROOT))
    monkeypatch.delenv("PYTEST_ADDOPTS", raising=False)
    with tempfile.TemporaryFile(mode="w+b") as captured:
        process = pytester.popen(
            [
                sys.executable,
                "-m",
                "pytest",
                str(child),
                "-c",
                str(config),
                "--noconftest",
                "--basetemp=" + str(tmp_path / "child-temp"),
                "--junitxml=" + str(receipt),
                "-p",
                "no:cacheprovider",
                "-q",
                "-l",
            ],
            cwd=ROOT,
            stdout=captured,
            stderr=captured,
        )
        try:
            status = process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
            raise
        captured.seek(0)
        output = captured.read().decode("utf-8", errors="replace")
    if receipt.is_file():
        output += receipt.read_text(encoding="utf-8")
    expected = (
        "the Gunicorn emitted-log proof failed"
        if mode.startswith("gunicorn")
        else "the CSP emitted-log proof failed"
    )
    if status != 1 or CANARY in output or expected not in output:
        pytest.fail(
            "proof failure diagnostics were not private and generic", pytrace=False
        )
