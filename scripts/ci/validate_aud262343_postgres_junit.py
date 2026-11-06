"""Require the thirteen AUD-262/343 PostgreSQL cases to pass without skips."""

from __future__ import annotations

import argparse
from pathlib import Path

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

_COMPLETION = (
    "tests/test_aud262_postcommit_redis_failure.py::"
    "test_postcommit_completion_failure_keeps_database_result"
)
_EXPECTED = frozenset(
    {
        *(
            f"{_COMPLETION}[{case}]"
            for case in (
                "os-error",
                "redis-error",
                "redis-timeout",
                "redis-response-error-propagates",
                "cancellation-propagates",
                "unexpected-error-propagates",
            )
        ),
        "tests/test_aud262_postcommit_redis_failure.py::"
        "test_message_without_idempotency_key_skips_cache_completion",
        "tests/test_chat_idempotency_ownership.py::"
        "test_simultaneous_dispatchers_persist_one_real_message",
        "tests/integration/test_aud343_notification_fallback_postgres.py::"
        "test_complete_schema_reads_without_fallback_on_postgres",
        "tests/integration/test_aud343_notification_fallback_postgres.py::"
        "test_unexpected_postgres_error_propagates_without_losing_outer_work",
        *(
            "tests/integration/test_aud343_notification_fallback_postgres.py::"
            f"test_missing_column_fallback_preserves_postgres_transaction[{column}]"
            for column in ("title_en", "body_en", "read_at")
        ),
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

    if len(cases) != 13 or len(_EXPECTED) != 13 or actual != _EXPECTED or unsuccessful:
        raise ValueError("Required PostgreSQL cohort did not pass all 13 cases")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    try:
        validate_report(args.report)
    except ValueError as error:
        parser.exit(1, f"AUD-262/343 report rejected: {error}\n")
    print("PostgreSQL AUD-262/343 cohort: 13 expected passes, zero skips")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
