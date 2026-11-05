"""Fail closed on the nightly S3 chaos JUnit receipt."""

from __future__ import annotations

import io
import json
import runpy
import shlex
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree

import pytest
import yaml

pytest_plugins = ("pytester",)

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts/quality/validate_chaos_s3_junit.py"
WORKFLOW = ROOT / ".github/workflows/nightly-full-gate.yml"
CLASSNAME = "tests.chaos.test_minio_chaos"
CASES = {
    "test_s3_no_such_bucket_error_is_propagated",
    "test_s3_outage_blocks_avatar_upload_and_preserves_state",
}


def _report() -> ElementTree.Element:
    root = ElementTree.Element("testsuites")
    suite = ElementTree.SubElement(root, "testsuite")
    for name in sorted(CASES):
        ElementTree.SubElement(suite, "testcase", classname=CLASSNAME, name=name)
    return root


def _write(path: Path, root: ElementTree.Element) -> None:
    ElementTree.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def _validate(report: Path) -> subprocess.CompletedProcess[str]:
    argv = [str(VALIDATOR), str(report)]
    stdout, stderr = io.StringIO(), io.StringIO()
    with (
        patch.object(sys, "argv", argv),
        redirect_stdout(stdout),
        redirect_stderr(stderr),
    ):
        try:
            runpy.run_path(str(VALIDATOR), run_name="__main__")
        except SystemExit as exc:
            assert isinstance(exc.code, int)
            return subprocess.CompletedProcess(
                argv, exc.code, stdout.getvalue(), stderr.getvalue()
            )
    raise AssertionError("validator did not exit")


def test_workflow_validates_and_uploads_the_report_from_the_s3_job() -> None:
    jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    job = jobs["chaos-tests"]
    assert job["env"]["DATABASE_URL"] == "sqlite+aiosqlite:///./test_chaos.db"
    step = next(s for s in job["steps"] if s.get("name") == "Run chaos tests")
    lines = step["run"].splitlines()
    assert lines[:2] == [
        'export MINIO_ACCESS_KEY="$STORAGE_S3_ACCESS_KEY_ID"',
        'export MINIO_SECRET_KEY="$STORAGE_S3_SECRET_ACCESS_KEY"',
    ]
    assert shlex.split(lines[2]) == [
        "uv",
        "run",
        "pytest",
        "tests/chaos/",
        "-v",
        "-m",
        "chaos",
        "--tb=short",
        "--junitxml=$RUNNER_TEMP/chaos-s3.xml",
    ]
    assert shlex.split(lines[3]) == [
        "uv",
        "run",
        "python",
        "scripts/quality/validate_chaos_s3_junit.py",
        "$RUNNER_TEMP/chaos-s3.xml",
    ]
    assert len(lines) == 4
    upload = next(s for s in job["steps"] if s.get("name") == "Upload S3 chaos receipt")
    assert job["steps"].index(upload) > job["steps"].index(step)
    assert upload["if"] == "${{ success() }}"
    assert (
        upload["uses"]
        == "actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9"
    )
    assert (
        upload["with"]["name"]
        == "nightly-s3-chaos-${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}"
    )
    assert upload["with"]["path"] == "${{ runner.temp }}/chaos-s3.xml"
    assert upload["with"]["if-no-files-found"] == "error"


def test_validator_can_be_imported_without_running_the_cli() -> None:
    module = runpy.run_path(str(VALIDATOR), run_name="s3_receipt_library")
    assert callable(module["validate_report"])


def test_catalog_inventory_records_the_receipt() -> None:
    catalog = json.loads(
        (ROOT / "quality/ci-check-catalog.json").read_text(encoding="utf-8")
    )
    workflow = next(
        entry
        for entry in catalog["workflows"]
        if entry["path"] == ".github/workflows/nightly-full-gate.yml"
    )
    assert workflow["jobs"]["chaos-tests"]["artifacts"] == [
        {
            "name_pattern": "nightly-s3-chaos-${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}",
            "path_pattern": "${{ runner.temp }}/chaos-s3.xml",
            "required": False,
            "provenance": "sha",
        }
    ]


def test_validator_accepts_both_passed_and_ignores_unrelated_cases(
    tmp_path: Path,
) -> None:
    root = _report()
    suite = root.find("testsuite")
    assert suite is not None
    other = ElementTree.SubElement(
        suite, "testcase", classname="tests.chaos.other", name="skipped"
    )
    ElementTree.SubElement(other, "skipped")
    report = tmp_path / "junit.xml"
    _write(report, root)
    result = _validate(report)
    assert result.returncode == 0, result.stderr


def test_validator_accepts_a_single_junit_testsuite(tmp_path: Path) -> None:
    suite = _report().find("testsuite")
    assert suite is not None
    report = tmp_path / "junit.xml"
    _write(report, suite)
    result = _validate(report)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "defect", ["missing", "duplicate", "extra", "nested", "skipped", "failure", "error"]
)
def test_validator_rejects_incomplete_or_unexecuted_cases(
    tmp_path: Path, defect: str
) -> None:
    root = _report()
    suite = root.find("testsuite")
    assert suite is not None
    cases = suite.findall("testcase")
    if defect == "missing":
        suite.remove(cases[0])
    elif defect == "duplicate":
        suite.append(deepcopy(cases[0]))
    elif defect == "extra":
        ElementTree.SubElement(suite, "testcase", classname=CLASSNAME, name="extra")
    elif defect == "nested":
        ElementTree.SubElement(
            suite, "testcase", classname=f"{CLASSNAME}.TestExtra", name="extra"
        )
    else:
        ElementTree.SubElement(cases[0], defect)
    report = tmp_path / "junit.xml"
    _write(report, root)
    assert _validate(report).returncode != 0


@pytest.mark.parametrize(
    "contents",
    [
        None,
        "<testsuites>",
        "<not-junit />",
        '<!DOCTYPE testsuite [<!ENTITY bad "bad">]><testsuite>&bad;</testsuite>',
    ],
)
def test_validator_rejects_bad_report(tmp_path: Path, contents: str | None) -> None:
    report = tmp_path / "junit.xml"
    if contents is not None:
        report.write_text(contents, encoding="utf-8")
    assert _validate(report).returncode != 0


@pytest.mark.parametrize(("skip", "expected"), [(False, 0), (True, 1)])
def test_validator_handles_junit_generated_by_controlled_pytest(
    pytester: pytest.Pytester,
    monkeypatch: pytest.MonkeyPatch,
    skip: bool,
    expected: int,
) -> None:
    test_file = pytester.path / "tests/chaos/test_minio_chaos.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text(
        "import os\nimport pytest\n"
        "def test_s3_no_such_bucket_error_is_propagated():\n    assert True\n"
        "@pytest.mark.skipif(os.getenv('AUD347_SKIP') == '1', reason='controlled skip')\n"
        "def test_s3_outage_blocks_avatar_upload_and_preserves_state():\n    assert True\n",
        encoding="utf-8",
    )
    config = pytester.makeini("[pytest]\n")
    report = pytester.path / "junit.xml"
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    monkeypatch.setenv("PYTEST_ADDOPTS", "")
    monkeypatch.setenv("AUD347_SKIP", "1" if skip else "0")
    result = pytester.runpytest_subprocess(
        "-c",
        str(config),
        "--noconftest",
        "-q",
        "-p",
        "no:cacheprovider",
        f"--junitxml={report}",
        str(test_file),
        timeout=60,
    )
    assert result.ret == 0, str(result.stdout) + str(result.stderr)
    validated = _validate(report)
    assert validated.returncode == expected, validated.stdout + validated.stderr
