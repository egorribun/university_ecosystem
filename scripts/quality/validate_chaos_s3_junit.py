"""Require the two nightly S3 chaos tests to pass without skips."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

_MODULE = "tests.chaos.test_minio_chaos"
_CASES = frozenset(
    {
        "test_s3_no_such_bucket_error_is_propagated",
        "test_s3_outage_blocks_avatar_upload_and_preserves_state",
    }
)


def validate_report(path: Path) -> None:
    """Reject missing, duplicate, unexpected or unsuccessful S3 cases."""
    try:
        root = ElementTree.parse(path).getroot()
    except (DefusedXmlException, ElementTree.ParseError, OSError) as error:
        raise ValueError("cannot read the S3 chaos JUnit report") from error
    if root.tag not in {"testsuite", "testsuites"}:
        raise ValueError("the S3 chaos JUnit report has an unexpected root")

    cases = [
        case
        for case in root.iter("testcase")
        if case.get("classname") == _MODULE
        or (case.get("classname") or "").startswith(_MODULE + ".")
    ]
    actual = Counter((case.get("classname"), case.get("name")) for case in cases)
    expected = Counter({(_MODULE, name): 1 for name in _CASES})
    if actual != expected:
        raise ValueError("the report does not contain exactly the two S3 cases")
    if any(
        case.find(outcome) is not None
        for case in cases
        for outcome in ("skipped", "failure", "error")
    ):
        raise ValueError("an S3 chaos case did not pass")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    try:
        validate_report(args.report)
    except ValueError as error:
        parser.exit(1, f"AUD-347 proof failed: {error}\n")
    print("AUD-347: both named S3 chaos cases passed without skips")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
