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
    "80 13 9e cc 82 ad 3c 42 db c4 43 ab 7a 5b ef 8d "
    "48 d7 f4 ee 0b 8b 30 2f ee 1e 2f 35 06 10 65 c9"
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


_SOURCE_BINDINGS = {
    ".github/actions/node-actions-coverage/action.yml": (
        bytes.fromhex(
            "91 08 0d 17 3f 07 12 d1 e9 b5 2c 12 53 6c c1 04 "
            "04 01 e0 8f 5e 91 d9 e5 9d a8 e2 6f c1 6e 0f 47"
        ),
        bytes.fromhex(
            "b8 42 38 5a fe 99 85 86 8a 8e 7e dc 07 ac 2e 05 "
            "0b 2a ad 1b 7f 33 dc 61 d0 70 72 53 0e e9 f0 19"
        ),
    ),
    "tests/test_quality_workflow_contract.py": (
        bytes.fromhex(
            "0e f8 b5 4b ad e0 cb 8d ea 7b 33 21 95 14 54 74 "
            "2d ad be 74 53 be 7e bc e5 bf 1c 7c 7e 70 60 1f"
        ),
        bytes.fromhex(
            "d0 3e 4c 8d a0 04 5b f6 86 d0 8c ac 6b e6 49 f8 "
            "bf 59 01 85 2d f6 44 42 6f 0c b3 66 64 18 bc 9c"
        ),
    ),
    "quality/semgrep-dispositions.json": (
        bytes.fromhex(
            "01 6d 59 04 d0 1b 4e bf 89 bf 72 7b b8 79 92 b5 "
            "c4 a4 57 f7 b5 5a 8b 92 0b 7e 4b e4 71 7c 17 db"
        ),
        bytes.fromhex(
            "a9 bc 31 86 f5 05 2b 2f 08 94 fb aa 6b a1 a6 11 "
            "18 0c 8d dc 57 d6 cd 2d ea 5c e8 e2 60 12 8a 35"
        ),
    ),
}
_NODE_OUTPUT_INSERTION = (
    b"outputs:\n"
    b"  artifact-id:\n"
    b"    description: Server-issued ID of this same-job upload, "
    b"for presence diagnostics only\n"
    b"    value: ${{ steps.capture_upload.outputs.artifact-id }}\n"
)
_WORKFLOW_ENV_INSERTION = (
    b'        "EXPECTED_NODE_ARTIFACT_ID": (\n'
    b'            "${{ steps.node_action_coverage.outputs.artifact-id }}"\n'
    b"        ),\n"
)


def coverage_snapshot_historical_policy_bytes(actual: bytes) -> bytes:
    policy = json.loads(actual)
    assert actual == (json.dumps(policy, sort_keys=True, indent=2) + "\n").encode(), (
        "coverage snapshot policy is not canonical"
    )
    restored = coverage_snapshot_historical_policy(policy)
    return (json.dumps(restored, sort_keys=True, indent=2) + "\n").encode()


def coverage_snapshot_historical_source_bytes(path: str, actual: bytes) -> bytes:
    """Normalize only exact approved postimages before older source guards run."""
    if path not in _SOURCE_BINDINGS:
        return actual
    current, previous = _SOURCE_BINDINGS[path]
    message = f"conditional disposition source coverage snapshot changed: {path}"
    assert hashlib.sha256(actual).digest() == current, message
    historical = actual
    if path == _LEDGER_PATH:
        for companion in (
            ".github/actions/node-actions-coverage/action.yml",
            "tests/test_quality_workflow_contract.py",
        ):
            new_digest, old_digest = _SOURCE_BINDINGS[companion]
            new_hex = new_digest.hex().encode("ascii")
            assert historical.count(new_hex) == 1, message
            historical = historical.replace(
                new_hex, old_digest.hex().encode("ascii"), 1
            )
    else:
        insertion = (
            _NODE_OUTPUT_INSERTION
            if path.endswith("action.yml")
            else _WORKFLOW_ENV_INSERTION
        )
        assert historical.count(insertion) == 1, message
        historical = historical.replace(insertion, b"", 1)
    assert hashlib.sha256(historical).digest() == previous, message
    return historical


@pytest.mark.parametrize("path", list(_SOURCE_BINDINGS))
def test_coverage_snapshot_source_inverse_is_exact(path: str) -> None:
    root = Path(__file__).resolve().parents[1]
    actual = (root / path).read_bytes()
    restored = coverage_snapshot_historical_source_bytes(path, actual)
    assert hashlib.sha256(restored).digest() == _SOURCE_BINDINGS[path][1]
    assert actual != restored


@pytest.mark.parametrize("path", list(_SOURCE_BINDINGS))
@pytest.mark.parametrize("mutation", ["extra", "missing", "duplicate", "predecessor"])
def test_coverage_snapshot_source_inverse_rejects_drift(
    path: str, mutation: str
) -> None:
    root = Path(__file__).resolve().parents[1]
    actual = (root / path).read_bytes()
    if mutation == "extra":
        actual += b"\n"
    elif mutation == "missing":
        actual = actual[:-1]
    elif mutation == "duplicate":
        actual += actual
    else:
        actual = coverage_snapshot_historical_source_bytes(path, actual)
    with pytest.raises(AssertionError, match="conditional disposition source"):
        coverage_snapshot_historical_source_bytes(path, actual)


def test_coverage_snapshot_source_inverse_leaves_unrelated_paths_unchanged() -> None:
    assert coverage_snapshot_historical_source_bytes("other", b"same") == b"same"


def test_coverage_snapshot_policy_bytes_preserve_exact_predecessor() -> None:
    root = Path(__file__).resolve().parents[1]
    actual = (root / _POLICY_PATH).read_bytes()
    restored = coverage_snapshot_historical_policy_bytes(actual)
    assert json.loads(restored) == coverage_snapshot_historical_policy(
        json.loads(actual)
    )
    with pytest.raises(AssertionError, match="not canonical"):
        coverage_snapshot_historical_policy_bytes(actual + b"\n")
