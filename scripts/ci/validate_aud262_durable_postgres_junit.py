"""Require the five AUD-262 durable replay cases to pass without skips."""

from __future__ import annotations

import argparse
from pathlib import Path

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

_PREFIX = "tests/test_aud262_durable_replay_postgres.py::"
_EXPECTED = frozenset(
    {
        _PREFIX + "test_committed_send_replays_after_pending_state_loss[deleted]",
        _PREFIX + "test_committed_send_replays_after_pending_state_loss[expired]",
        _PREFIX + "test_overlapping_sends_survive_redis_lease_loss",
        _PREFIX + "test_live_pending_lease_rejects_overlapping_send",
        _PREFIX + "test_rolled_back_send_succeeds_after_pending_lease_expiry",
    }
)


def validate_report(path: Path) -> None:
    """Reject a malformed report or any missing, duplicate, or failed case."""
    try:
        root = ElementTree.parse(
            path,
            forbid_dtd=True,
            forbid_entities=True,
            forbid_external=True,
        ).getroot()
        cases = list(root.iter("testcase"))
        actual = {
            case.attrib["classname"].replace(".", "/") + ".py::" + case.attrib["name"]
            for case in cases
        }
        unsuccessful = any(
            case.find(status) is not None
            for case in cases
            for status in ("failure", "error", "skipped")
        )
    except (DefusedXmlException, ElementTree.ParseError, KeyError, OSError):
        raise ValueError("JUnit report could not be read safely") from None

    if len(cases) != 5 or actual != _EXPECTED or unsuccessful:
        raise ValueError("Required durable PostgreSQL cohort did not pass all 5 cases")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    try:
        validate_report(args.report)
    except ValueError as error:
        parser.exit(1, f"AUD-262 durable report rejected: {error}\n")
    print("PostgreSQL AUD-262 durable cohort: 5 expected passes, zero skips")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
