"""Merge disjoint pytest JUnit reports with strict shard validation.

The weekly duration refresh runs the measurable pytest population in separate
file-granularity shards.  This helper combines those reports before the
historical-duration updater consumes them.  It deliberately fails closed when
an artifact is missing, duplicated, malformed, or does not identify exactly
one expected shard: a partial report must never be presented as a complete
duration refresh.
"""

from __future__ import annotations

import argparse
import copy
import os
import re
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn
from xml.etree import ElementTree

from defusedxml import ElementTree as DefusedElementTree
from defusedxml.common import DefusedXmlException

_REPORT_NAME = "pytest-report.xml"
_SHARD_COMPONENT = re.compile(r"(?:^|-)shard-(?P<id>[0-9]+)(?:-|$)")


class JUnitMergeError(ValueError):
    """Raised when JUnit shard evidence cannot be trusted."""


def _fail(message: str) -> NoReturn:
    raise JUnitMergeError(message)


def _discover_reports(input_directory: Path, expected_shards: int) -> dict[int, Path]:
    if expected_shards < 1:
        _fail("expected shard count must be a positive integer")
    if not input_directory.is_dir():
        _fail(f"JUnit input directory does not exist: {input_directory}")

    try:
        reports = sorted(input_directory.rglob(_REPORT_NAME))
    except OSError as error:
        raise JUnitMergeError(
            f"unable to enumerate JUnit input directory {input_directory}"
        ) from error
    reports = [path for path in reports if path.is_file()]
    if len(reports) != expected_shards:
        _fail(
            f"expected exactly {expected_shards} JUnit shard reports, "
            f"found {len(reports)}"
        )

    by_shard: dict[int, Path] = {}
    for report in reports:
        relative_parts = report.relative_to(input_directory).parts[:-1]
        matches = [
            int(match.group("id"))
            for component in relative_parts
            if (match := _SHARD_COMPONENT.search(component)) is not None
        ]
        if len(matches) != 1:
            _fail(f"JUnit report must identify exactly one shard in its path: {report}")
        shard_id = matches[0]
        if shard_id in by_shard:
            _fail(
                f"duplicate JUnit report for shard {shard_id}: "
                f"{by_shard[shard_id]} and {report}"
            )
        if shard_id >= expected_shards:
            _fail(
                f"JUnit report shard {shard_id} is outside the expected range "
                f"0..{expected_shards - 1}"
            )
        by_shard[shard_id] = report

    expected_ids = set(range(expected_shards))
    missing = sorted(expected_ids - by_shard.keys())
    if missing:
        _fail(f"missing JUnit shard reports: {missing}")
    return by_shard


def _read_suites(report_path: Path) -> list[ElementTree.Element]:
    try:
        root = DefusedElementTree.parse(report_path).getroot()
    except (
        DefusedXmlException,
        DefusedElementTree.ParseError,
        OSError,
        UnicodeError,
    ) as error:
        raise JUnitMergeError(f"unable to parse JUnit report {report_path}") from error

    if root.tag == "testsuite":
        suites = [root]
    elif root.tag == "testsuites":
        suites = list(root.findall("testsuite"))
    else:
        _fail(f"JUnit report {report_path} has unsupported root element {root.tag!r}")
    if not suites:
        _fail(f"JUnit report {report_path} contains no testsuite element")
    return suites


def _testcase_key(testcase: ElementTree.Element) -> tuple[str, str, str] | None:
    file_name = testcase.get("file", "")
    classname = testcase.get("classname", "")
    name = testcase.get("name", "")
    if not any((file_name, classname, name)):
        return None
    # Pytest may assign a different suite name to each CI shard.  The
    # testcase identity must therefore be independent of that container name;
    # otherwise duplicate execution could be silently merged when only the
    # shard-generated suite differs.
    return file_name, classname, name


def merge_junit_reports(
    input_directory: Path,
    output: Path,
    *,
    expected_shards: int,
) -> None:
    """Merge one complete, disjoint JUnit report per expected shard."""

    reports = _discover_reports(input_directory, expected_shards)
    resolved_output = output.resolve()
    if any(report.resolve() == resolved_output for report in reports.values()):
        _fail("output path must differ from every input report")

    merged_root = ElementTree.Element(
        "testsuites", {"name": "weekly-test-duration-refresh"}
    )
    seen_testcases: set[tuple[str, str, str]] = set()
    testcase_count = 0

    for shard_id in sorted(reports):
        report_path = reports[shard_id]
        for suite in _read_suites(report_path):
            for testcase in suite.iter("testcase"):
                testcase_count += 1
                key = _testcase_key(testcase)
                if key is not None:
                    if key in seen_testcases:
                        _fail(
                            "duplicate JUnit testcase across shard reports: "
                            f"file={key[0]!r}, classname={key[1]!r}, "
                            f"name={key[2]!r}"
                        )
                    seen_testcases.add(key)
            merged_root.append(copy.deepcopy(suite))

    if testcase_count == 0:
        _fail("merged JUnit reports contain no testcase elements")

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{output.name}.",
            suffix=".tmp",
            dir=output.parent,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            ElementTree.ElementTree(merged_root).write(
                temporary,
                encoding="utf-8",
                xml_declaration=True,
            )
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.replace(output)
    except (OSError, TypeError, ValueError) as error:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise JUnitMergeError(
            f"unable to write merged JUnit report {output}"
        ) from error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, dest="input_directory")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-shards", required=True, type=int)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        merge_junit_reports(
            args.input_directory,
            args.output,
            expected_shards=args.expected_shards,
        )
    except JUnitMergeError as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
