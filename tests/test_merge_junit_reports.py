"""Contracts for the fail-closed weekly JUnit report merger."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

import pytest
from defusedxml import ElementTree as DefusedElementTree

from scripts.quality.merge_junit_reports import JUnitMergeError, merge_junit_reports


def _write_report(
    input_directory: Path,
    shard_id: int,
    *,
    file_name: str,
    test_name: str,
    root_tag: str = "testsuites",
    suffix: str = "attempt-1",
) -> Path:
    report_directory = (
        input_directory / f"weekly-test-duration-shard-{shard_id}-{suffix}"
    )
    report_directory.mkdir(parents=True)
    if root_tag == "testsuite":
        root = ElementTree.Element("testsuite", name=f"shard-{shard_id}")
    else:
        root = ElementTree.Element("testsuites")
        ElementTree.SubElement(root, "testsuite", name=f"shard-{shard_id}")
    suite = root if root.tag == "testsuite" else root[0]
    ElementTree.SubElement(
        suite,
        "testcase",
        file=file_name,
        classname=file_name.removesuffix(".py"),
        name=test_name,
        time="0.25",
    )
    report_path = report_directory / "pytest-report.xml"
    ElementTree.ElementTree(root).write(
        report_path, encoding="utf-8", xml_declaration=True
    )
    return report_path


def test_merge_junit_reports_requires_each_expected_shard_and_preserves_cases(
    tmp_path: Path,
) -> None:
    input_directory = tmp_path / "reports"
    _write_report(
        input_directory,
        0,
        file_name="tests/test_alpha.py",
        test_name="test_alpha",
        root_tag="testsuite",
    )
    _write_report(
        input_directory,
        1,
        file_name="tests/test_beta.py",
        test_name="test_beta",
    )
    output = tmp_path / "pytest-report.xml"

    merge_junit_reports(input_directory, output, expected_shards=2)

    root = DefusedElementTree.parse(output).getroot()
    assert root.tag == "testsuites"
    assert root.get("name") == "weekly-test-duration-refresh"
    assert [testcase.get("file") for testcase in root.iter("testcase")] == [
        "tests/test_alpha.py",
        "tests/test_beta.py",
    ]


@pytest.mark.parametrize(
    ("directory_names", "message"),
    (
        (("weekly-test-duration-shard-0-attempt-1",), "expected exactly 2"),
        (
            (
                "weekly-test-duration-shard-0-attempt-1",
                "weekly-test-duration-shard-0-attempt-2",
            ),
            "duplicate JUnit report for shard 0",
        ),
        (
            (
                "weekly-test-duration-shard-0-attempt-1",
                "weekly-test-duration-shard-2-attempt-1",
            ),
            "outside the expected range",
        ),
    ),
)
def test_merge_junit_reports_rejects_incomplete_or_ambiguous_shards(
    tmp_path: Path,
    directory_names: tuple[str, ...],
    message: str,
) -> None:
    input_directory = tmp_path / "reports"
    for index, directory_name in enumerate(directory_names):
        report_directory = input_directory / directory_name
        report_directory.mkdir(parents=True)
        root = ElementTree.Element("testsuite", name=f"shard-{index}")
        ElementTree.SubElement(
            root,
            "testcase",
            file=f"tests/test_{index}.py",
            name=f"test_{index}",
            time="0.1",
        )
        ElementTree.ElementTree(root).write(
            report_directory / "pytest-report.xml", encoding="utf-8"
        )

    with pytest.raises(JUnitMergeError, match=message):
        merge_junit_reports(input_directory, tmp_path / "merged.xml", expected_shards=2)


def test_merge_junit_reports_rejects_malformed_and_duplicate_testcases(
    tmp_path: Path,
) -> None:
    input_directory = tmp_path / "reports"
    first = _write_report(
        input_directory,
        0,
        file_name="tests/test_duplicate.py",
        test_name="test_same",
    )
    second = _write_report(
        input_directory,
        1,
        file_name="tests/test_duplicate.py",
        test_name="test_same",
    )
    with pytest.raises(JUnitMergeError, match="duplicate JUnit testcase"):
        merge_junit_reports(input_directory, tmp_path / "merged.xml", expected_shards=2)

    second.write_text("<testsuites>", encoding="utf-8")
    with pytest.raises(JUnitMergeError, match="unable to parse JUnit report"):
        merge_junit_reports(input_directory, tmp_path / "merged.xml", expected_shards=2)

    first.unlink()
    second.unlink()


def test_merge_junit_reports_rejects_empty_reports(tmp_path: Path) -> None:
    input_directory = tmp_path / "reports"
    for shard_id in (0, 1):
        report_directory = input_directory / f"shard-{shard_id}"
        report_directory.mkdir(parents=True)
        ElementTree.ElementTree(ElementTree.Element("testsuite")).write(
            report_directory / "pytest-report.xml", encoding="utf-8"
        )

    with pytest.raises(JUnitMergeError, match="no testcase elements"):
        merge_junit_reports(input_directory, tmp_path / "merged.xml", expected_shards=2)
