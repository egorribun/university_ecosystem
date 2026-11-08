"""Require the five AUD-322 resilience tests to execute successfully."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from xml.etree.ElementTree import Element

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

_MODULE = "tests.chaos.test_resilience"
# The S3 job proves these two cases separately (validate_chaos_s3_junit.py).
_S3_MODULE = "tests.chaos.test_minio_chaos"
_CASES = frozenset(
    {
        "test_nats_outage_outbox_durability",
        "test_valkey_outage_idempotency_fail_open",
        "test_valkey_redis_down_resilience",
        "test_ws_hub_down_gateway_proxy_fallback",
        "test_nats_down_outbox_queue_resilience",
    }
)


def _in_module(case: Element, module: str) -> bool:
    classname = case.get("classname") or ""
    return classname == module or classname.startswith(module + ".")


def validate_report(path: Path) -> None:
    """Reject missing, duplicate, unexpected, unsuccessful or skipped chaos cases.

    Every case in the report must execute.  The only permitted skips belong to
    the S3 module, which the S3 job validates separately.
    """
    try:
        root = ElementTree.parse(path).getroot()
    except (DefusedXmlException, ElementTree.ParseError, OSError) as error:
        raise ValueError("cannot read the chaos JUnit report") from error
    if root.tag not in {"testsuite", "testsuites"}:
        raise ValueError("the chaos JUnit report has an unexpected root")

    cases = [
        case
        for case in root.iter("testcase")
        if case.get("classname") == _MODULE
        or (case.get("classname") or "").startswith(_MODULE + ".")
    ]
    actual = Counter((case.get("classname"), case.get("name")) for case in cases)
    expected = Counter({(_MODULE, name): 1 for name in _CASES})
    if actual != expected:
        raise ValueError(
            "the report does not contain exactly the five resilience cases"
        )
    if any(
        case.find(outcome) is not None
        for case in cases
        for outcome in ("skipped", "failure", "error")
    ):
        raise ValueError("a resilience case did not pass")
    if any(
        case.find("skipped") is not None
        for case in root.iter("testcase")
        if not _in_module(case, _S3_MODULE)
    ):
        raise ValueError("a chaos case in the report was skipped")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    try:
        validate_report(args.report)
    except ValueError as error:
        parser.exit(1, f"AUD-322 proof failed: {error}\n")
    print("AUD-322: all five named resilience cases passed; no chaos case was skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
