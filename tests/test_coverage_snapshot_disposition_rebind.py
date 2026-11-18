"""Exact test-only inverse of the two approved coverage companion identities.

This is not a scanner waiver or a permissive historical-policy loader.
The complete predecessor fingerprint protects every other record and field.
"""

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

_POLICY_PATH = "quality/security-false-positive-dispositions.json"
_LEDGER_PATH = "quality/semgrep-dispositions.json"
_KIND = "Hex High Entropy String"
_PREDECESSOR_SHA256 = bytes.fromhex(
    "80 13 9e cc 82 ad 3c 42 db c4 43 ab 7a 5b ef 8d 48 d7 f4 ee 0b 8b 30 2f ee 1e 2f 35 06 10 65 c9"
)
# (predecessor scanner identity, approved replacement scanner identity).
_REBINDS = (
    (
        bytes.fromhex("8e bb be 37 ce 74 a4 e9 4b 3a dd 69 62 c7 d2 0b 4f 12 0b 5e"),
        bytes.fromhex("43 79 6c f7 8e 7e 94 5e d0 d8 89 af 66 ef 32 31 f5 00 1e 0b"),
    ),
    (
        bytes.fromhex("85 d5 57 e8 2d 0d 2e 14 53 e9 97 0d 09 f5 a9 d8 3b 49 55 c2"),
        bytes.fromhex("50 af 2a 70 ab b8 49 66 53 50 ee 3d 30 5b e5 b1 79 01 cc 56"),
    ),
)


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def coverage_snapshot_historical_policy(policy: dict[str, Any]) -> dict[str, Any]:
    """Restore only the approved pair, rejecting any other policy difference."""
    restored = copy.deepcopy(policy)
    records = restored["records"]
    assert len(records) == 524, "coverage snapshot disposition count changed"
    for previous, current in _REBINDS:
        old_identity = {
            "path": _LEDGER_PATH,
            "type": _KIND,
            "hashed_secret_bytes": list(previous),
        }
        new_identity = {**old_identity, "hashed_secret_bytes": list(current)}
        assert not any(row["identity"] == old_identity for row in records), (
            "coverage snapshot predecessor identity remains"
        )
        matches = [row for row in records if row["identity"] == new_identity]
        assert len(matches) == 1, "coverage snapshot replacement is not unique"
        matches[0]["identity"] = old_identity
    assert hashlib.sha256(_canonical_bytes(restored)).digest() == _PREDECESSOR_SHA256, (
        "coverage snapshot predecessor or metadata changed"
    )
    return restored


def _live_policy() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    return json.loads((root / _POLICY_PATH).read_text(encoding="utf-8"))


def _replacement_row(policy: dict[str, Any], pair: int) -> dict[str, Any]:
    identity = {
        "path": _LEDGER_PATH,
        "type": _KIND,
        "hashed_secret_bytes": list(_REBINDS[pair][1]),
    }
    rows = [row for row in policy["records"] if row["identity"] == identity]
    assert len(rows) == 1
    return rows[0]


def test_coverage_snapshot_inverse_is_exact_bijective_and_nonmutating() -> None:
    policy = _live_policy()
    original = copy.deepcopy(policy)
    historical = coverage_snapshot_historical_policy(policy)
    assert policy == original
    assert len(historical["records"]) == len(policy["records"]) == 524
    changed = []
    for index, (before, after) in enumerate(
        zip(historical["records"], policy["records"], strict=True)
    ):
        if before != after:
            changed.append(index)
            old_identity = before["identity"]
            new_identity = after["identity"]
            assert old_identity["path"] == new_identity["path"] == _LEDGER_PATH
            assert old_identity["type"] == new_identity["type"] == _KIND
            normalized = copy.deepcopy(after)
            normalized["identity"] = copy.deepcopy(old_identity)
            assert normalized == before
            assert before["category"] == "public_integrity_digest"
            assert before["expires_on"] == "2027-01-10"
    assert changed == [373, 505]


@pytest.mark.parametrize("pair", [0, 1])
@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "duplicate",
        "foreign_digest",
        "old_digest",
        "path",
        "type",
        "category",
        "owner",
        "approval_status",
        "reviewed_on",
        "expires_on",
        "evidence",
        "third_record",
        "extra_record",
        "schema_version",
    ],
)
def test_coverage_snapshot_inverse_rejects_scope_drift(
    pair: int, mutation: str
) -> None:
    policy = _live_policy()
    row = _replacement_row(policy, pair)
    if mutation == "missing":
        policy["records"].remove(row)
    elif mutation == "duplicate":
        policy["records"][0] = copy.deepcopy(row)
    elif mutation == "foreign_digest":
        row["identity"]["hashed_secret_bytes"][0] ^= 1
    elif mutation == "old_digest":
        row["identity"]["hashed_secret_bytes"] = list(_REBINDS[pair][0])
    elif mutation in {"path", "type"}:
        row["identity"][mutation] += " changed"
    elif mutation == "third_record":
        policy["records"][0]["identity"]["hashed_secret_bytes"][0] ^= 1
    elif mutation == "extra_record":
        policy["records"].append(copy.deepcopy(row))
    elif mutation == "schema_version":
        policy["schema_version"] += 1
    else:
        row[mutation] += " changed"
    with pytest.raises(AssertionError, match="coverage snapshot"):
        coverage_snapshot_historical_policy(policy)
