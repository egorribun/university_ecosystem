"""Require the five AUD-322 resilience tests to execute successfully."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

_MODULE = "tests.chaos.test_resilience"
_CASES = frozenset(
    {
        "test_nats_outage_outbox_durability",
        "test_valkey_outage_idempotency_fail_open",
        "test_valkey_redis_down_resilience",
        "test_ws_hub_down_gateway_proxy_fallback",
        "test_nats_down_outbox_queue_resilience",
    }
)


def validate_report(path: Path) -> None:
    """Reject missing, duplicate, unexpected or unsuccessful resilience cases."""
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    try:
        validate_report(args.report)
    except ValueError as error:
        parser.exit(1, f"AUD-322 proof failed: {error}\n")
    print("AUD-322: all five named resilience cases passed without skips")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
