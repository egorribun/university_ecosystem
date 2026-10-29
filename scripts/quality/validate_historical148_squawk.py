"""Recognize one inactive historical Squawk diagnostic inventory.

A match is not scanner success, migration permission, greenfield admission or
deployment acceptance. The function performs no file, process, database or CI
operation. Compiled fingerprints bind the reviewed policy and historical report;
a caller cannot authorize a different policy by supplying matching new findings.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import NoReturn

# Reproducible from the committed historical148 policy and 36f70a0f capture.
# Compact ASCII JSON, sorted object keys, no final LF. Only each raw warning
# array is sorted by complete canonical rows; duplicates and all fields remain.
_POLICY_SHA256 = "d22de4503b8ecc752cbc2c188e91876dd56dee739db3fc88613be7bee4d3e93c"
_CAPTURE_SHA256 = "ead6a5f5d0c9a8f16711804b2f465f0681c98f004948992fa4fb37398dad786c"
_NOT_BEFORE = datetime(2026, 10, 28, tzinfo=UTC)
_EXPIRES_AT = datetime(2026, 11, 13, tzinfo=UTC)
_MAX_DEPTH = 8


def _reject_number(_value: str) -> NoReturn:
    raise ValueError("non-integer inventory metadata")


def _unsigned_integer(value: str) -> int:
    if value.startswith("-") or len(value) > 10:
        raise ValueError("invalid inventory integer")
    result = int(value)
    if result > 1_000_000_000:
        raise ValueError("oversized inventory integer")
    return result


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate inventory key")
        key.encode("utf-8")
        result[key] = value
    return result


def _bounded_nesting(text: str) -> None:
    depth = 0
    quoted = False
    escaped = False
    for character in text:
        if quoted:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quoted = False
        elif character == '"':
            quoted = True
        elif character in "[{":
            depth += 1
            if depth > _MAX_DEPTH:
                raise ValueError("inventory nesting limit")
        elif character in "]}":
            depth -= 1
            if depth < 0:
                raise ValueError("invalid inventory nesting")
    if depth or quoted:
        raise ValueError("incomplete inventory JSON")


def _scalar_types(value: object) -> None:
    if type(value) is bool:
        raise ValueError("boolean inventory metadata")
    if isinstance(value, str):
        value.encode("utf-8")
    elif isinstance(value, list):
        for item in value:
            _scalar_types(item)
    elif isinstance(value, dict):
        for item in value.values():
            _scalar_types(item)


def _decode(data: bytes, limit: int) -> object:
    if type(data) is not bytes or not data or len(data) > limit:
        raise ValueError("invalid inventory bytes")
    text = data.decode("utf-8")
    _bounded_nesting(text)
    value = json.loads(
        text,
        object_pairs_hook=_unique_object,
        parse_int=_unsigned_integer,
        parse_float=_reject_number,
        parse_constant=_reject_number,
    )
    _scalar_types(value)
    return value


def _canonical(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _fingerprint(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("ascii")).hexdigest()


def _normalize_warnings(capture: object) -> None:
    if not isinstance(capture, dict):
        raise ValueError("invalid capture root")
    report = capture.get("report")
    if not isinstance(report, dict):
        raise ValueError("invalid capture report")
    captures = report.get("captures")
    if not isinstance(captures, list) or len(captures) != 2:
        raise ValueError("invalid capture scenarios")
    for count, scenario in zip((13, 24), captures, strict=True):
        if not isinstance(scenario, dict):
            raise ValueError("invalid raw scanner report")
        stdout = scenario.get("stdout")
        if not isinstance(stdout, str):
            raise ValueError("invalid raw scanner report")
        rows = _decode(stdout.encode("utf-8"), 16384)
        if (
            not isinstance(rows, list)
            or len(rows) != count
            or not all(isinstance(row, dict) for row in rows)
        ):
            raise ValueError("invalid warning population")
        # Only this JSON representation changes inside the privately parsed tree.
        # Never drop unknown fields or convert the multiset to a deduplicating set.
        scenario["stdout"] = _canonical(sorted(rows, key=_canonical))


def match_inventory(policy_bytes: bytes, capture_bytes: bytes) -> str | None:
    """Return a historical diagnostic match, never execution authorization."""
    try:
        policy = _decode(policy_bytes, 32768)
        if not isinstance(policy, dict) or _fingerprint(policy) != _POLICY_SHA256:
            return None
        capture = _decode(capture_bytes, 131072)
        _normalize_warnings(capture)
        if _fingerprint(capture) != _CAPTURE_SHA256:
            return None
        # Use the real UTC clock at the final boundary, not caller data or env.
        now = datetime.now(UTC)
        if _NOT_BEFORE <= now < _EXPIRES_AT:
            return "matched-diagnostic-inventory"
    except (RecursionError, TypeError, ValueError):
        return None
    return None
