"""Prove the nightly chaos selector reaches the real resilience tests."""

from __future__ import annotations

import runpy
import sys
from copy import deepcopy
from pathlib import Path
from xml.etree import ElementTree

import pytest

pytest_plugins = ("pytester",)

ROOT = Path(__file__).resolve().parents[1]
RESILIENCE = "tests/chaos/test_resilience.py"
VALIDATOR = ROOT / "scripts/quality/validate_chaos_resilience_junit.py"
CLASSNAME = "tests.chaos.test_resilience"
EXPECTED_CASES = {
    "test_nats_outage_outbox_durability",
    "test_valkey_outage_idempotency_fail_open",
    "test_valkey_redis_down_resilience",
    "test_ws_hub_down_gateway_proxy_fallback",
    "test_nats_down_outbox_queue_resilience",
}


def test_nightly_marker_collects_all_five_resilience_cases(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CHAOS_TESTS", "1")
    monkeypatch.delenv("PYTEST_ADDOPTS", raising=False)
    result = pytester.runpytest_subprocess(
        "--collect-only",
        "--no-cov",
        "-o",
        "addopts=",
        "-q",
        "-m",
        "chaos",
        str(ROOT / RESILIENCE),
        "-p",
        "no:cacheprovider",
        timeout=60,
    )
    assert result.ret == 0, str(result.stdout) + str(result.stderr)
    selected = {
        line.partition("::")[2]
        for line in result.stdout.lines
        if line.partition("::")[0].replace("\\", "/").endswith(RESILIENCE)
    }
    assert selected == EXPECTED_CASES


def _run_validator(monkeypatch: pytest.MonkeyPatch, report: Path) -> int:
    monkeypatch.setattr(sys, "argv", [str(VALIDATOR), str(report)])
    with pytest.raises(SystemExit) as exited:
        runpy.run_path(str(VALIDATOR), run_name="__main__")
    assert isinstance(exited.value.code, int)
    return exited.value.code


def _report() -> ElementTree.Element:
    root = ElementTree.Element("testsuites")
    suite = ElementTree.SubElement(root, "testsuite")
    for name in sorted(EXPECTED_CASES):
        ElementTree.SubElement(suite, "testcase", classname=CLASSNAME, name=name)
    return root


def _write_report(path: Path, root: ElementTree.Element) -> None:
    ElementTree.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def test_validator_accepts_the_exact_five_passed_cases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _report()
    suite = root.find("testsuite")
    assert suite is not None
    unrelated = ElementTree.SubElement(
        suite, "testcase", classname="tests.chaos.test_minio_chaos", name="other"
    )
    ElementTree.SubElement(unrelated, "skipped")
    report = tmp_path / "chaos.xml"
    _write_report(report, root)

    assert _run_validator(monkeypatch, report) == 0


def test_validator_accepts_a_single_junit_testsuite(tmp_path: Path) -> None:
    from scripts.quality.validate_chaos_resilience_junit import validate_report

    suite = _report().find("testsuite")
    assert suite is not None
    report = tmp_path / "chaos.xml"
    _write_report(report, suite)

    assert validate_report(report) is None


@pytest.mark.parametrize(
    "defect",
    ["missing", "duplicate", "extra", "nested", "skipped", "failure", "error"],
)
def test_validator_rejects_incomplete_or_unexecuted_resilience_cases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, defect: str
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
    report = tmp_path / "chaos.xml"
    _write_report(report, root)

    assert _run_validator(monkeypatch, report) != 0


@pytest.mark.parametrize(
    "contents",
    [
        None,
        "<testsuites>",
        "<not-junit />",
        '<!DOCTYPE testsuite [<!ENTITY bad "bad">]><testsuite>&bad;</testsuite>',
    ],
)
def test_validator_rejects_missing_malformed_or_unexpected_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, contents: str | None
) -> None:
    report = tmp_path / "chaos.xml"
    if contents is not None:
        report.write_text(contents, encoding="utf-8")

    assert _run_validator(monkeypatch, report) != 0


@pytest.mark.parametrize(
    "module",
    [
        "tests.chaos.test_network_failures",
        "tests.chaos.test_memory_pressure",
        # A lookalike name must not inherit the S3 skip exception.
        "tests.chaos.test_minio_chaos_extra",
    ],
)
def test_validator_rejects_a_skipped_chaos_case_outside_the_s3_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, module: str
) -> None:
    root = _report()
    suite = root.find("testsuite")
    assert suite is not None
    skipped = ElementTree.SubElement(
        suite, "testcase", classname=module, name="test_skipped"
    )
    ElementTree.SubElement(skipped, "skipped")
    report = tmp_path / "chaos.xml"
    _write_report(report, root)

    assert _run_validator(monkeypatch, report) != 0
