"""Focused contract tests for strict detect-secrets baseline verification."""

from __future__ import annotations

import ast
import base64
import copy
import hashlib
import importlib.util
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tomllib
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest

_VALIDATOR_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "verify_secrets_baseline.py"
)
_VALIDATOR_SPEC = importlib.util.spec_from_file_location(
    "aud495_v4_verify_secrets_baseline", _VALIDATOR_PATH
)
if _VALIDATOR_SPEC is None or _VALIDATOR_SPEC.loader is None:
    raise ImportError(f"cannot load v4 validator from {_VALIDATOR_PATH}")
verifier = importlib.util.module_from_spec(_VALIDATOR_SPEC)
sys.modules[_VALIDATOR_SPEC.name] = verifier
_VALIDATOR_SPEC.loader.exec_module(verifier)

Finding = tuple[str, str, str, int]
_FINDING_TYPE = "Secret" + " Keyword"
_HASHED_FIELD = "hash" + "ed_" + "se" + "cret"


# The owner-approved fresh-only squash removed these source fixtures. These
# contracts prove historical approval provenance, not current migration behavior.
# Read only this finite set at the immutable pre-squash commit; never use a
# missing-file fallback, checkout, import, execute, or fetch historical code.
# Byte pins are provenance, not new scanner exceptions or approval identities.
_PRE_SQUASH_SOURCE_COMMIT = bytes(
    (
        63,
        245,
        55,
        95,
        186,
        1,
        182,
        255,
        111,
        43,
        193,
        138,
        175,
        45,
        107,
        43,
        161,
        142,
        25,
        201,
    )
).hex()
# The reviewed Dependabot bump of this one workflow (setup-python 5fda3b95 -> 6d4fd22b) lives in its
# own commit. The approval-policy checkpoint has its own immutable commit;
# remaining historical paths stay on the pre-squash commit.
_REVIEWED_SOURCE_COMMIT_OVERRIDES = {
    "quality/security-false-positive-dispositions.json": bytes(
        (
            230,
            187,
            187,
            91,
            79,
            122,
            147,
            64,
            173,
            68,
            82,
            82,
            146,
            98,
            50,
            221,
            46,
            234,
            126,
            120,
        )
    ).hex(),
    ".github/workflows/reusable-backend-tests.yml": "e77defff9ddf944793bc7107fa6b5df9e2f7903a",
}
_PRE_SQUASH_SOURCE_BLOBS = {
    "quality/security-false-positive-dispositions.json": (
        35,
        111,
        147,
        182,
        156,
        230,
        109,
        236,
        29,
        95,
        233,
        247,
        167,
        2,
        173,
        48,
        252,
        195,
        187,
        91,
    ),
    "tests/integration/test_aud350_stored_event_timestamp_migration.py": (
        20,
        181,
        97,
        47,
        71,
        233,
        198,
        172,
        8,
        127,
        98,
        218,
        38,
        228,
        221,
        71,
        162,
        110,
        160,
        90,
    ),
    "tests/fixtures/migrations/aud350/202603280001_reconcile_post_uuid_migration_drift_baseline.py.txt": (
        22,
        79,
        99,
        203,
        115,
        148,
        113,
        97,
        190,
        255,
        134,
        113,
        169,
        191,
        85,
        79,
        138,
        182,
        109,
        245,
    ),
    "tests/helpers/migration_148642dd1207_trace.py": (
        225,
        151,
        101,
        27,
        148,
        68,
        19,
        226,
        175,
        1,
        168,
        178,
        169,
        42,
        8,
        111,
        0,
        48,
        65,
        85,
    ),
    "alembic/versions/148642dd1207_fix_missing_tables.py": (
        215,
        98,
        196,
        92,
        146,
        72,
        193,
        78,
        204,
        245,
        122,
        200,
        233,
        226,
        218,
        232,
        134,
        119,
        119,
        193,
    ),
    "tests/test_migration_148642dd1207_orchestrator.py": (
        41,
        246,
        169,
        186,
        103,
        216,
        241,
        10,
        9,
        176,
        84,
        36,
        42,
        125,
        174,
        204,
        253,
        123,
        10,
        123,
    ),
    "tests/integration/test_migration_148642dd1207.py": (
        232,
        90,
        106,
        196,
        232,
        18,
        243,
        115,
        227,
        83,
        90,
        117,
        202,
        131,
        68,
        122,
        32,
        7,
        230,
        227,
    ),
    "alembic/versions/2956fd6376cc_fix_groups_id_sequence.py": (
        80,
        217,
        251,
        250,
        230,
        232,
        227,
        62,
        132,
        200,
        246,
        145,
        66,
        159,
        215,
        85,
        73,
        112,
        57,
        186,
    ),
    "quality/historical148-squawk-policy.json": (
        222,
        152,
        133,
        78,
        74,
        178,
        198,
        60,
        214,
        145,
        169,
        115,
        246,
        215,
        246,
        29,
        188,
        22,
        145,
        221,
    ),
    "scripts/quality/validate_historical148_squawk.py": (
        45,
        217,
        156,
        183,
        44,
        228,
        110,
        133,
        36,
        227,
        68,
        169,
        20,
        77,
        138,
        176,
        211,
        61,
        180,
        155,
    ),
    "tests/fixtures/historical148-squawk-capture-15eaaa.json": (
        251,
        252,
        68,
        231,
        189,
        221,
        124,
        226,
        103,
        74,
        101,
        221,
        196,
        242,
        213,
        72,
        59,
        207,
        188,
        167,
    ),
    "tests/fixtures/historical148-squawk-capture-35aeedeb.json": (
        255,
        236,
        125,
        81,
        253,
        238,
        124,
        131,
        249,
        109,
        170,
        19,
        149,
        84,
        162,
        104,
        202,
        198,
        31,
        141,
    ),
    "tests/fixtures/historical148-squawk-capture-36f70a0f.json": (
        160,
        155,
        225,
        106,
        122,
        30,
        220,
        98,
        12,
        22,
        245,
        103,
        211,
        183,
        49,
        29,
        72,
        18,
        139,
        5,
    ),
    "tests/fixtures/historical148-squawk-capture-3d83fb27.json": (
        255,
        212,
        82,
        19,
        180,
        53,
        170,
        240,
        217,
        22,
        143,
        73,
        55,
        15,
        100,
        0,
        177,
        205,
        94,
        145,
    ),
    "scripts/quality/run_owned_redis_contracts.py": (
        50,
        216,
        60,
        47,
        71,
        41,
        78,
        112,
        144,
        127,
        150,
        101,
        110,
        183,
        96,
        153,
        137,
        206,
        128,
        224,
    ),
    "tests/test_aud427_428_contract_quality.py": (
        4,
        85,
        104,
        38,
        96,
        193,
        158,
        83,
        34,
        78,
        128,
        27,
        98,
        48,
        202,
        93,
        159,
        245,
        244,
        211,
    ),
    "tests/integration/test_aud447_dlq_auth_scrub_postgres.py": (
        202,
        56,
        166,
        60,
        157,
        7,
        182,
        147,
        135,
        144,
        206,
        148,
        144,
        15,
        223,
        151,
        240,
        121,
        81,
        68,
    ),
    "tests/test_aud447_dlq_auth_scrub_migration.py": (
        140,
        32,
        111,
        199,
        16,
        61,
        143,
        40,
        48,
        56,
        145,
        174,
        92,
        144,
        235,
        99,
        221,
        244,
        155,
        100,
    ),
    "tests/test_quality_workflow_contract.py": (
        72,
        101,
        68,
        149,
        56,
        202,
        53,
        85,
        203,
        160,
        195,
        84,
        6,
        40,
        251,
        150,
        156,
        173,
        51,
        37,
    ),
    ".github/workflows/reusable-backend-tests.yml": (
        237,
        164,
        16,
        40,
        91,
        48,
        242,
        14,
        234,
        29,
        233,
        143,
        237,
        41,
        191,
        143,
        132,
        2,
        251,
        240,
    ),
}


_AUD427_428_CURRENT_TEST_SOURCE_SHA256 = bytes(
    (
        89,
        11,
        186,
        193,
        96,
        226,
        29,
        104,
        213,
        164,
        200,
        188,
        26,
        41,
        91,
        240,
        175,
        31,
        67,
        207,
        204,
        26,
        187,
        73,
        86,
        36,
        184,
        20,
        37,
        41,
        43,
        144,
    )
)


def _pre_squash_source_bytes(
    path: str, *, repository_root: Path | None = None
) -> bytes:
    assert path in _PRE_SQUASH_SOURCE_BLOBS, "unreviewed historical source path"
    root = repository_root or Path(__file__).resolve().parents[1]
    git_executable = _git_executable()
    try:
        # Fixed commit and finite reviewed paths; read-only Git, without a shell.
        result = subprocess.run(  # noqa: S603
            [
                git_executable,
                "--no-replace-objects",
                "cat-file",
                "blob",
                f"{_REVIEWED_SOURCE_COMMIT_OVERRIDES.get(path, _PRE_SQUASH_SOURCE_COMMIT)}:{path}",
            ],
            cwd=root,
            check=True,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        raise AssertionError(
            "historical scanner fixtures require the immutable pre-squash Git "
            "history; use a full-history checkout (fetch-depth: 0)"
        ) from None
    data = result.stdout
    framed = b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    assert hashlib.sha1(framed, usedforsecurity=False).digest() == bytes(
        _PRE_SQUASH_SOURCE_BLOBS[path]
    ), "historical scanner source blob changed"
    return data


def _pre_squash_source_text(path: str) -> str:
    return _pre_squash_source_bytes(path).decode("utf-8")


def _reviewed_pre_retirement_dispositions() -> dict[str, Any]:
    """Immutable approval history; never an active scanner matching policy."""
    data = _pre_squash_source_bytes("quality/security-false-positive-dispositions.json")
    assert len(data) <= 512 * 1024
    policy = json.loads(data)
    assert len(policy["records"]) == 504
    # Exact subsequent one-record approval, independently bound below.
    return {**policy, "records": [*policy["records"], _nov2_workflow_binding_record()]}


_RETIRED_DISPOSITION_PATHS = frozenset(
    (
        "quality/historical148-squawk-policy.json",
        "scripts/quality/validate_historical148_squawk.py",
        "tests/fixtures/historical148-squawk-capture-15eaaa.json",
        "tests/fixtures/historical148-squawk-capture-35aeedeb.json",
        "tests/fixtures/historical148-squawk-capture-36f70a0f.json",
        "tests/fixtures/historical148-squawk-capture-3d83fb27.json",
        "tests/helpers/migration_148642dd1207_trace.py",
        "tests/integration/test_aud350_stored_event_timestamp_migration.py",
        "tests/integration/test_aud447_dlq_auth_scrub_postgres.py",
        "tests/integration/test_historical_attendance_sender_migrations_postgres.py",
        "tests/integration/test_migration_148642dd1207.py",
        "tests/test_aud447_dlq_auth_scrub_migration.py",
    )
)


_NOV2_CHART_REFERENCE_RECORDS = [
    {
        "identity": {
            "path": "charts/university-ecosystem/values-staging.yaml",
            "type": "Secret Keyword",
            "hashed_secret_bytes": [
                186,
                196,
                166,
                53,
                205,
                238,
                100,
                52,
                204,
                177,
                241,
                191,
                64,
                57,
                254,
                78,
                225,
                214,
                206,
                73,
            ],
        },
        "category": "external_kubernetes_secret_reference",
        "evidence": "Kubernetes external Secret object name or key reference; not credential material. Public internal HTTP mTLS privateKeyKey reference at charts/university-ecosystem/values-staging.yaml:58; source reviewed at 476f42e58fe780254c0a3bc92f104bf064cb4472.",
        "owner": "egorribun",
        "reviewed_on": "2026-11-02",
        "expires_on": "2027-01-09",
        "approval_status": "approved",
    },
    {
        "identity": {
            "path": "charts/university-ecosystem/values.yaml",
            "type": "Secret Keyword",
            "hashed_secret_bytes": [
                186,
                196,
                166,
                53,
                205,
                238,
                100,
                52,
                204,
                177,
                241,
                191,
                64,
                57,
                254,
                78,
                225,
                214,
                206,
                73,
            ],
        },
        "category": "external_kubernetes_secret_reference",
        "evidence": "Kubernetes external Secret object name or key reference; not credential material. Public internal HTTP mTLS privateKeyKey reference at charts/university-ecosystem/values.yaml:139; source reviewed at 476f42e58fe780254c0a3bc92f104bf064cb4472.",
        "owner": "egorribun",
        "reviewed_on": "2026-11-02",
        "expires_on": "2027-01-09",
        "approval_status": "approved",
    },
]


def _nov2_chart_reference_records() -> list[dict[str, Any]]:
    return copy.deepcopy(_NOV2_CHART_REFERENCE_RECORDS)


# Each tuple names a source line holding exactly one owner-approved public Git
# object id; the id itself is read from that line so no second copy exists here.
_NOV3_PUBLIC_GIT_OBJECTS = (
    (
        ".github/actions/dependency-review-capture/capture.cjs",
        11,
        "commit",
        "upstream commit",
    ),
    (
        ".github/actions/dependency-review-capture/capture.cjs",
        13,
        "blob",
        "LICENSE blob",
    ),
    (
        ".github/actions/dependency-review-capture/capture.cjs",
        14,
        "blob",
        "action.yml blob",
    ),
    (
        ".github/actions/dependency-review-capture/capture.cjs",
        15,
        "blob",
        "dist/index.js blob",
    ),
    (
        ".github/actions/dependency-review-capture/capture.cjs",
        16,
        "blob",
        "dist/index.js.map blob",
    ),
    (
        ".github/actions/dependency-review-capture/capture.cjs",
        17,
        "blob",
        "dist/licenses.txt blob",
    ),
    (
        ".github/actions/dependency-review-capture/capture.cjs",
        18,
        "blob",
        "dist/sourcemap-register.js blob",
    ),
    (
        ".github/actions/dependency-review-capture/capture.cjs",
        19,
        "blob",
        "package.json blob",
    ),
    (
        ".github/actions/node-actions-coverage/action.yml",
        21,
        "commit",
        "checkout ref commit",
    ),
    (
        ".github/workflows/dependency-review.yml",
        25,
        "commit",
        "DEPENDENCY_REVIEW_ACTION_REF commit",
    ),
)
_NOV3_UPSTREAM_COMMIT_PREFIX = "a1d282b3"


def _nov3_source_object_id(path: str, line: int) -> str:
    root = Path(__file__).resolve().parents[1]
    text = (root / path).read_text(encoding="utf-8").splitlines()[line - 1]
    object_ids = re.findall(r"\b[0-9a-f]{40}\b", text)
    assert len(object_ids) == 1, f"{path}:{line} must hold exactly one Git object id"
    return object_ids[0]


def _nov3_public_git_object_records() -> list[dict[str, Any]]:
    """Owner-approved 2026-11-02 pins of the upstream Dependency Review object ids."""
    records: list[dict[str, Any]] = []
    for path, line, kind, label in _NOV3_PUBLIC_GIT_OBJECTS:
        object_id = _nov3_source_object_id(path, line)
        if kind == "commit":
            assert object_id.startswith(_NOV3_UPSTREAM_COMMIT_PREFIX)
        digest = hashlib.sha1(object_id.encode("ascii"), usedforsecurity=False).digest()
        records.append(
            {
                "identity": {
                    "path": path,
                    "type": "Hex High Entropy String",
                    "hashed_secret_bytes": list(digest),
                },
                "category": "public_integrity_digest",
                "evidence": (
                    f"Public Git SHA-1 integrity digest of {kind} object {object_id} ({label}) "
                    f"at {path}:{line}; Git object kind {kind}; pinned public upstream "
                    "actions/dependency-review-action@a1d282b3 (v5.0.0); identity derived "
                    "using pinned detect-secrets 1.5.0 SHA-1. Owner approved exactly these "
                    "ten identities on 2026-11-02; not credential material."
                ),
                "owner": "egorribun",
                "reviewed_on": "2026-11-02",
                "expires_on": "2027-01-10",
                "approval_status": "approved",
            }
        )
    return records


# Owner-approved 2026-11-04 1:1 rebind of the public SHA-256 digest identity of
# the complete candidate Trivy ignore policy after that policy file was amended.
# Only the hashed_secret_bytes of that single record changes; the byte lists are
# the detect-secrets SHA-1 identities of the old and new hex strings.
_NOV4_TRIVY_IGNORE_POLICY_PATH = "scripts/quality/validate_trivy_kyverno_fixture.py"
_NOV4_TRIVY_IGNORE_POLICY_EVIDENCE = "complete candidate Trivy ignore policy"
_NOV4_TRIVY_IGNORE_POLICY_OLD_BYTES = [
    224,
    192,
    166,
    76,
    174,
    89,
    98,
    209,
    14,
    59,
    156,
    41,
    28,
    44,
    108,
    70,
    149,
    242,
    195,
    91,
]
_NOV4_TRIVY_IGNORE_POLICY_NEW_BYTES = [
    40,
    59,
    35,
    217,
    116,
    25,
    96,
    171,
    9,
    132,
    150,
    7,
    120,
    227,
    236,
    167,
    255,
    230,
    177,
    105,
]


def _nov4_trivy_ignore_policy_digest_rebind(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rebound = copy.deepcopy(records)
    old_holders = [
        row
        for row in rebound
        if row["identity"]["hashed_secret_bytes"] == _NOV4_TRIVY_IGNORE_POLICY_OLD_BYTES
    ]
    assert len(old_holders) == 1, "old ignore-policy digest must appear exactly once"
    row = old_holders[0]
    assert row["identity"]["path"] == _NOV4_TRIVY_IGNORE_POLICY_PATH
    assert row["identity"]["type"] == "Hex High Entropy String"
    assert row["category"] == "public_integrity_digest"
    assert row["owner"] == "egorribun"
    assert row["expires_on"] == "2026-11-22"
    assert _NOV4_TRIVY_IGNORE_POLICY_EVIDENCE in row["evidence"]
    row["identity"]["hashed_secret_bytes"] = list(_NOV4_TRIVY_IGNORE_POLICY_NEW_BYTES)
    assert len(rebound) == len(records)
    return rebound


def _nov4_current_view(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return historical records as the live verifier must see them.

    Historical snapshots keep the retired digest so immutable prefix hashes stay
    exact. A slice holding that digest receives only the reviewed rebind; a slice
    without it is returned unchanged.
    """
    holders = sum(
        1
        for row in records
        if row["identity"]["hashed_secret_bytes"] == _NOV4_TRIVY_IGNORE_POLICY_OLD_BYTES
    )
    assert holders <= 1, "retired ignore-policy digest must appear at most once"
    if holders == 0:
        rebound = copy.deepcopy(records)
    else:
        rebound = _nov4_trivy_ignore_policy_digest_rebind(records)
    return _nov13_trivy_current_view(rebound)


# STEP5 owner-authored 1:1 rebind of the Trivy fixture ignore-policy digest after
# AUD-251 removed the stale KSV-0047 exception. The live validator, verifier
# constants and public-integrity record carry the current digest; the exact
# predecessor digest (the NOV4 NEW value) is restored for historical checks.
# Only the hashed_secret_bytes of the single existing record changes.
_NOV13_TRIVY_CURRENT_IGNORE_POLICY_DIGEST = bytes.fromhex(
    "29 9a eb 3d 01 3b b5 ab ba f4 6e 03 7f 65 0b 4c ca 35 05 ac c7 14 84 86 09 6d 03 0d fc 03 e2 e2"
)
_NOV13_TRIVY_PREVIOUS_IGNORE_POLICY_DIGEST = bytes.fromhex(
    "6f 24 56 62 81 6c 8e 99 87 7d 2d 8b 36 56 7b 6b fc ff ae b4 79 b4 b3 31 0e f5 cb 51 94 99 bf 02"
)


def _nov13_trivy_identity_bytes(digest: bytes) -> list[int]:
    return list(
        hashlib.sha1(digest.hex().encode("ascii"), usedforsecurity=False).digest()
    )


def _nov13_trivy_current_view(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Forward-project the NOV4 predecessor identity to the live digest.

    A slice holding the NOV4 digest receives only the one-to-one NOV13 rebind;
    a slice without it is returned unchanged.
    """
    rebound = copy.deepcopy(records)
    holders = [
        row
        for row in rebound
        if row["identity"]["path"] == _NOV4_TRIVY_IGNORE_POLICY_PATH
        and row["identity"]["hashed_secret_bytes"]
        == _NOV4_TRIVY_IGNORE_POLICY_NEW_BYTES
    ]
    assert len(holders) <= 1, (
        "predecessor ignore-policy digest must appear at most once"
    )
    for row in holders:
        row["identity"]["hashed_secret_bytes"] = _nov13_trivy_identity_bytes(
            _NOV13_TRIVY_CURRENT_IGNORE_POLICY_DIGEST
        )
    return rebound


def _nov13_verify_dispositions(
    policy_or_document: dict[str, Any], *args: Any, **kwargs: Any
) -> Any:
    """Validate with the live Trivy digest, as the verifier pins only that digest.

    Chains restore the exact predecessor digest for historical hash checks; a
    predecessor record is forward-projected to the live identity before the
    verifier evaluates any policy or document that carries it.
    """
    records = policy_or_document.get("records")
    if isinstance(records, list):
        policy_or_document = {
            **policy_or_document,
            "records": _nov13_trivy_current_view(records),
        }
    return verifier.validate_false_positive_dispositions(
        policy_or_document, *args, **kwargs
    )


def _nov13_trivy_predecessor_identities() -> frozenset[
    tuple[str, str, tuple[int, ...]]
]:
    """Return the verifier's Trivy identities with the live digest made predecessor."""
    current = tuple(
        _nov13_trivy_identity_bytes(_NOV13_TRIVY_CURRENT_IGNORE_POLICY_DIGEST)
    )
    previous = tuple(
        _nov13_trivy_identity_bytes(_NOV13_TRIVY_PREVIOUS_IGNORE_POLICY_DIGEST)
    )
    return frozenset(
        (path, finding_type, previous if digest == current else digest)
        for path, finding_type, digest in verifier._TRIVY_KYVERNO_PUBLIC_CHECKSUM_IDENTITIES
    )


def _nov13_trivy_historical_policy(policy: dict[str, Any]) -> dict[str, Any]:
    """Restore the exact predecessor digest on the live 512-record policy."""
    restored = copy.deepcopy(policy)
    live_identity = _nov13_trivy_identity_bytes(
        _NOV13_TRIVY_CURRENT_IGNORE_POLICY_DIGEST
    )
    holders = [
        row
        for row in restored["records"]
        if row["identity"]["path"] == _NOV4_TRIVY_IGNORE_POLICY_PATH
        and row["identity"]["hashed_secret_bytes"] == live_identity
    ]
    assert len(holders) == 1, "live disposition trivy identity changed"
    row = holders[0]
    assert row["identity"]["type"] == "Hex High Entropy String", (
        "live disposition trivy identity changed"
    )
    assert row["category"] == "public_integrity_digest", (
        "live disposition trivy identity changed"
    )
    assert row["owner"] == "egorribun", "live disposition trivy identity changed"
    assert row["expires_on"] == "2027-01-10", "live disposition trivy identity changed"
    row["identity"]["hashed_secret_bytes"] = _nov13_trivy_identity_bytes(
        _NOV13_TRIVY_PREVIOUS_IGNORE_POLICY_DIGEST
    )
    return _nov13_trivy_workflow_historical_policy(restored)


def _nov4_trivy_checksum_renewal(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    renewed = copy.deepcopy(records)
    rows = [
        row
        for row in renewed
        if row["identity"]["path"] == _NOV4_TRIVY_IGNORE_POLICY_PATH
    ]
    assert {
        (
            row["identity"]["path"],
            row["identity"]["type"],
            tuple(row["identity"]["hashed_secret_bytes"]),
        )
        for row in rows
    } == _nov13_trivy_predecessor_identities()
    assert len(rows) == 2
    for row in rows:
        assert row["category"] == "public_integrity_digest"
        assert row["owner"] == "egorribun"
        assert row["reviewed_on"] == "2026-10-23"
        assert row["expires_on"] == "2026-11-22"
        assert row["approval_status"] == "approved"
        row["reviewed_on"] = "2026-11-04"
        row["expires_on"] = "2027-01-10"
    return renewed


def _nov4_semgrep_rules_pin_record() -> dict[str, Any]:
    path = ".github/workflows/ci.yml"
    source = (Path(__file__).resolve().parents[1] / path).read_text(encoding="utf-8")
    marker = "      - name: Check out pinned Semgrep rules\n"
    assert source.count(marker) == 1
    step = source.split(marker, 1)[1].split("\n      - name: ", 1)[0]
    assert "repository: semgrep/semgrep-rules" in step
    references = re.findall(r"(?m)^\s+ref: ([0-9a-f]{40})$", step)
    assert len(references) == 1
    detector_digest = hashlib.sha1(
        references[0].encode("ascii"), usedforsecurity=False
    ).digest()
    return {
        "identity": {
            "path": path,
            "type": "Hex High Entropy String",
            "hashed_secret_bytes": list(detector_digest),
        },
        "category": "public_integrity_digest",
        "evidence": (
            "Public upstream semgrep/semgrep-rules Git commit pinned in the "
            "Semgrep checkout step of .github/workflows/ci.yml; identity derived "
            "using detect-secrets 1.5.0 SHA-1; not credential material."
        ),
        "owner": "egorribun",
        "reviewed_on": "2026-11-04",
        "expires_on": "2027-01-10",
        "approval_status": "approved",
    }


def _nov4_spire_chart_pin_record() -> dict[str, Any]:
    path = "scripts/kind/aud373_internal_mtls_proof.sh"
    source = (Path(__file__).resolve().parents[1] / path).read_text(encoding="utf-8")
    pins = re.findall(r'(?m)^readonly SPIRE_CHART_SHA256="([0-9a-f]{64})"$', source)
    assert len(pins) == 1
    assert "/spire-0.30.4/spire-0.30.4.tgz" in source
    assert 'download_pinned "$SPIRE_CHART_URL" "$SPIRE_CHART_SHA256"' in source
    detector_digest = hashlib.sha1(
        pins[0].encode("ascii"), usedforsecurity=False
    ).digest()
    return {
        "identity": {
            "path": path,
            "type": "Hex High Entropy String",
            "hashed_secret_bytes": list(detector_digest),
        },
        "category": "public_integrity_digest",
        "evidence": (
            "Public SPIRE chart 0.30.4 archive SHA-256 pin in "
            "scripts/kind/aud373_internal_mtls_proof.sh; current upstream release "
            "bytes matched on 2026-11-04 UTC, without an upstream signed checksum; "
            "the script verifies the archive before use. Identity derived using "
            "detect-secrets 1.5.0 SHA-1; not credential material."
        ),
        "owner": "egorribun",
        "reviewed_on": "2026-11-04",
        "expires_on": "2027-01-10",
        "approval_status": "approved",
    }


@pytest.mark.parametrize(
    "record_factory", [_nov4_semgrep_rules_pin_record, _nov4_spire_chart_pin_record]
)
def test_public_source_pin_matches_the_owner_approved_disposition(
    record_factory: Any,
) -> None:
    root = Path(__file__).resolve().parents[1]
    policy = json.loads(
        (root / "quality/security-false-positive-dispositions.json").read_text(
            encoding="utf-8"
        )
    )
    expected = record_factory()
    matches = [
        record
        for record in policy["records"]
        if record["identity"] == expected["identity"]
    ]
    assert matches == [expected]
    findings = _nov13_verify_dispositions(
        _disposition_document(expected), today=verifier.date(2026, 11, 4)
    )
    identity = expected["identity"]
    assert findings == {
        verifier.FindingIdentity(
            identity["path"],
            identity["type"],
            bytes(identity["hashed_secret_bytes"]).hex(),
            1,
        )
    }
    assert (
        _nov13_verify_dispositions(
            _disposition_document(expected), today=verifier.date(2027, 1, 10)
        )
        == findings
    )
    with pytest.raises(verifier.BaselineArtifactError, match="date range"):
        _nov13_verify_dispositions(
            _disposition_document(expected), today=verifier.date(2027, 1, 11)
        )


def _assert_live_disposition_retirement(policy: dict[str, Any]) -> None:
    try:
        _aud380_historical_490_from_live_policy(policy)
    except AssertionError as error:
        raise AssertionError("live disposition inventory changed") from error


def test_live_dispositions_retire_only_exact_deleted_sources() -> None:
    root = Path(__file__).resolve().parents[1]
    policy = json.loads(
        (root / "quality/security-false-positive-dispositions.json").read_text(
            encoding="utf-8"
        )
    )
    _assert_live_disposition_retirement(policy)
    assert _RETIRED_DISPOSITION_PATHS == verifier._RETIRED_DISPOSITION_SOURCE_PATHS
    for path in _RETIRED_DISPOSITION_PATHS:
        assert not (root / path).exists(), "retired approval source is live again"
    validated = _nov13_verify_dispositions(
        _nov11_historical_509_from_live_policy(policy), today=verifier.date(2026, 11, 9)
    )
    assert len(validated) == 509
    assert all(finding.path not in _RETIRED_DISPOSITION_PATHS for finding in validated)
    live_validated = verifier.load_owner_authored_candidate_false_positive_dispositions(
        repository_root=root, today=verifier.date(2026, 11, 12)
    )
    assert len(live_validated) == 512
    assert all(
        finding.path not in _RETIRED_DISPOSITION_PATHS for finding in live_validated
    )
    with pytest.raises(verifier.BaselineArtifactError, match="date range is invalid"):
        verifier.load_owner_authored_candidate_false_positive_dispositions(
            repository_root=root, today=verifier.date(2026, 11, 9)
        )


def _spire_chart_record_index(records: list[dict[str, Any]]) -> int:
    expected_identity = _aud380_identity_key(_nov4_spire_chart_pin_record())
    matches = [
        index
        for index, record in enumerate(records)
        if _aud380_identity_key(record) == expected_identity
    ]
    assert len(matches) == 1
    return matches[0]


@pytest.mark.parametrize(
    "mutation",
    [
        "reintroduced",
        "changed",
        "missing",
        "unrelated",
        "expiry",
        "reordered",
        "chart_identity",
        "chart_metadata",
    ],
)
def test_live_disposition_retirement_refuses_other_inventory_changes(
    mutation: str,
) -> None:
    historical = _reviewed_pre_retirement_dispositions()
    live = _aud380_read_live_policy()
    _assert_live_disposition_retirement(live)
    changed = copy.deepcopy(live)
    if mutation == "reintroduced":
        changed["records"].append(
            next(
                row
                for row in historical["records"]
                if row["identity"]["path"] in _RETIRED_DISPOSITION_PATHS
            )
        )
    elif mutation == "changed":
        changed["records"][0]["identity"]["hashed_secret_bytes"][0] ^= 1
    elif mutation == "missing":
        changed["records"].pop()
    elif mutation == "unrelated":
        changed["records"][0]["identity"]["path"] = "tests/unreviewed_removed_source.py"
    elif mutation == "expiry":
        changed["records"][0]["expires_on"] = "2027-01-11"
    elif mutation == "chart_identity":
        spire = _spire_chart_record_index(changed["records"])
        changed["records"][spire]["identity"]["hashed_secret_bytes"][0] ^= 1
    elif mutation == "chart_metadata":
        spire = _spire_chart_record_index(changed["records"])
        changed["records"][spire]["expires_on"] = "2027-01-09"
    else:
        changed["records"][0], changed["records"][1] = (
            changed["records"][1],
            changed["records"][0],
        )
    with pytest.raises(AssertionError, match="live disposition inventory changed"):
        _assert_live_disposition_retirement(changed)


_AUD380_APPROVED_OWNER_ADDITIONS_SHA256 = bytes(
    (
        190,
        15,
        206,
        8,
        4,
        169,
        149,
        37,
        228,
        151,
        200,
        212,
        241,
        163,
        0,
        245,
        76,
        87,
        11,
        233,
        113,
        165,
        94,
        209,
        235,
        137,
        108,
        124,
        221,
        142,
        237,
        16,
    )
)
_AUD380_PENDING_NEW_ADDITIONS_SHA256 = bytes(
    (
        101,
        82,
        202,
        23,
        120,
        86,
        98,
        26,
        34,
        225,
        151,
        166,
        38,
        206,
        106,
        139,
        82,
        177,
        102,
        18,
        213,
        51,
        83,
        208,
        214,
        203,
        211,
        69,
        129,
        135,
        65,
        58,
    )
)
_AUD380_APPROVED_NEW_ADDITIONS_SHA256 = bytes(
    (
        179,
        112,
        31,
        216,
        208,
        43,
        225,
        117,
        48,
        71,
        138,
        198,
        167,
        70,
        188,
        123,
        238,
        123,
        195,
        8,
        90,
        150,
        92,
        52,
        62,
        247,
        141,
        55,
        164,
        79,
        117,
        254,
    )
)
_AUD380_CONDITIONAL_RECORDSET_SHA256 = bytes(
    (
        37,
        119,
        103,
        27,
        90,
        70,
        65,
        244,
        46,
        198,
        229,
        232,
        9,
        213,
        255,
        183,
        231,
        95,
        94,
        157,
        142,
        25,
        127,
        218,
        174,
        51,
        3,
        64,
        104,
        126,
        194,
        208,
    )
)
_AUD380_CURRENT_DELTA_CATEGORY_COUNTS = {
    "aud253_private_env_mode_test_fixture": 5,
    "aud495_cache_key_redaction_test_fixture": 2,
    "auth_validation_ui_copy": 3,
    "ci_test_contract_sentinel": 24,
    "documented_crypto_test_vector": 3,
    "documented_dummy_password_hash": 5,
    "domain_resource_contract_fixture": 1,
    "external_kubernetes_secret_reference": 35,
    "independent_contract_fingerprint": 81,
    "internal_demo_stand_account_fixture": 2,
    "public_compose_inspection_test_sentinel": 1,
    "public_integrity_digest": 297,
    "public_package_integrity_metadata": 7,
    "public_totp_algorithm_alphabet": 1,
    "source_contract_identifier": 18,
    "synthetic_achievement_url_test_fixture": 1,
    "synthetic_fakeredis_lease_token": 2,
    "synthetic_hmac_test_material": 2,
}
_AUD380_CURRENT_DELTA_PENDING_CATEGORY_COUNTS = {
    "ci_test_contract_sentinel": 1,
    "external_kubernetes_secret_reference": 4,
    "public_integrity_digest": 16,
}
_AUD380_CURRENT_DELTA_SOURCE_SHA256 = {
    ".github/workflows/deploy.yml": bytes(
        (
            188,
            133,
            211,
            51,
            129,
            101,
            252,
            231,
            154,
            176,
            94,
            169,
            244,
            180,
            185,
            45,
            154,
            96,
            120,
            152,
            97,
            15,
            152,
            233,
            62,
            53,
            150,
            200,
            214,
            183,
            142,
            31,
        )
    ),
    "alembic/versions/202611020000_mvp_baseline.py": bytes(
        (
            217,
            40,
            32,
            172,
            28,
            251,
            112,
            82,
            6,
            200,
            242,
            135,
            195,
            5,
            156,
            85,
            86,
            58,
            55,
            7,
            235,
            192,
            227,
            251,
            62,
            119,
            175,
            33,
            50,
            227,
            196,
            26,
        )
    ),
    "app/core/logging.py": bytes(
        (
            165,
            18,
            118,
            183,
            250,
            120,
            114,
            35,
            227,
            15,
            83,
            248,
            182,
            27,
            35,
            50,
            72,
            0,
            228,
            88,
            182,
            104,
            134,
            178,
            220,
            79,
            208,
            234,
            198,
            252,
            75,
            170,
        )
    ),
    "app/core/observability.py": bytes(
        (
            139,
            159,
            101,
            42,
            108,
            109,
            62,
            163,
            148,
            72,
            3,
            193,
            251,
            2,
            163,
            31,
            89,
            15,
            218,
            103,
            55,
            206,
            204,
            138,
            28,
            89,
            148,
            87,
            26,
            174,
            93,
            150,
        )
    ),
    "app/core/otel_logging.py": bytes(
        (
            161,
            203,
            241,
            150,
            248,
            237,
            76,
            81,
            83,
            48,
            196,
            230,
            45,
            191,
            85,
            168,
            54,
            98,
            199,
            140,
            147,
            107,
            104,
            44,
            222,
            5,
            61,
            2,
            189,
            112,
            49,
            54,
        )
    ),
    "app/worker.py": bytes(
        (
            136,
            239,
            44,
            198,
            141,
            97,
            249,
            17,
            17,
            249,
            5,
            122,
            158,
            77,
            170,
            29,
            181,
            0,
            15,
            234,
            7,
            35,
            8,
            9,
            11,
            161,
            224,
            40,
            192,
            22,
            21,
            107,
        )
    ),
    "charts/university-ecosystem/templates/file-processor-deployment.yaml": bytes(
        (
            18,
            236,
            10,
            174,
            233,
            225,
            33,
            171,
            146,
            175,
            186,
            253,
            155,
            32,
            157,
            69,
            212,
            187,
            140,
            121,
            14,
            0,
            215,
            208,
            225,
            228,
            124,
            166,
            161,
            161,
            229,
            237,
        )
    ),
    "charts/university-ecosystem/templates/gateway-deployment.yaml": bytes(
        (
            157,
            96,
            223,
            107,
            208,
            38,
            106,
            205,
            179,
            10,
            25,
            144,
            254,
            23,
            117,
            245,
            129,
            190,
            221,
            115,
            30,
            249,
            110,
            154,
            39,
            64,
            45,
            60,
            49,
            167,
            95,
            230,
        )
    ),
    "charts/university-ecosystem/values.schema.json": bytes(
        (
            211,
            209,
            161,
            116,
            54,
            205,
            155,
            19,
            108,
            177,
            5,
            99,
            225,
            105,
            216,
            72,
            232,
            133,
            186,
            132,
            94,
            118,
            149,
            255,
            36,
            187,
            68,
            56,
            206,
            153,
            147,
            73,
        )
    ),
    "charts/university-ecosystem/values.yaml": bytes(
        (
            17,
            34,
            233,
            153,
            140,
            69,
            20,
            107,
            130,
            153,
            65,
            239,
            19,
            117,
            187,
            85,
            193,
            164,
            253,
            247,
            7,
            63,
            76,
            228,
            215,
            117,
            161,
            9,
            62,
            28,
            110,
            120,
        )
    ),
    "frontend/WASM_SOURCE_PROVENANCE.json": bytes(
        (
            46,
            114,
            157,
            45,
            247,
            142,
            193,
            102,
            98,
            53,
            254,
            248,
            110,
            130,
            240,
            21,
            182,
            128,
            9,
            208,
            229,
            100,
            8,
            232,
            228,
            207,
            127,
            183,
            190,
            64,
            234,
            170,
        )
    ),
    "frontend/package-lock.json": bytes(
        (
            167,
            88,
            176,
            27,
            232,
            124,
            197,
            245,
            145,
            217,
            225,
            87,
            233,
            71,
            167,
            234,
            76,
            47,
            82,
            148,
            120,
            211,
            200,
            105,
            105,
            43,
            176,
            210,
            243,
            3,
            207,
            175,
        )
    ),
    "frontend/package.json": bytes(
        (
            195,
            25,
            210,
            138,
            58,
            145,
            245,
            105,
            44,
            2,
            159,
            93,
            239,
            141,
            181,
            163,
            26,
            156,
            22,
            124,
            96,
            23,
            74,
            16,
            154,
            101,
            21,
            208,
            46,
            192,
            124,
            189,
        )
    ),
    "frontend/scripts/visual-smoke-contract.test.mjs": bytes(
        (
            74,
            118,
            255,
            234,
            115,
            126,
            96,
            204,
            2,
            131,
            123,
            242,
            188,
            124,
            204,
            238,
            248,
            234,
            184,
            51,
            218,
            158,
            191,
            83,
            154,
            70,
            195,
            73,
            204,
            238,
            243,
            53,
        )
    ),
    "frontend/wasm-sanitizer/Cargo.toml": bytes(
        (
            32,
            108,
            35,
            230,
            200,
            87,
            167,
            59,
            63,
            130,
            88,
            68,
            105,
            14,
            157,
            1,
            186,
            113,
            226,
            177,
            99,
            133,
            224,
            89,
            22,
            253,
            250,
            169,
            36,
            137,
            44,
            103,
        )
    ),
    "frontend/wasm-sanitizer/pkg/package.json": bytes(
        (
            14,
            107,
            24,
            153,
            8,
            177,
            156,
            160,
            104,
            26,
            98,
            240,
            231,
            157,
            10,
            112,
            4,
            234,
            14,
            252,
            156,
            238,
            53,
            224,
            5,
            238,
            111,
            35,
            149,
            34,
            239,
            103,
        )
    ),
    "quality/semgrep-dispositions.json": bytes(
        (
            44,
            18,
            248,
            234,
            243,
            254,
            123,
            56,
            146,
            66,
            116,
            36,
            84,
            29,
            233,
            63,
            100,
            142,
            249,
            197,
            193,
            244,
            214,
            162,
            31,
            27,
            51,
            5,
            33,
            87,
            167,
            139,
        )
    ),
    "scripts/kind/aud373_internal_mtls_proof.sh": bytes(
        (
            32,
            126,
            17,
            99,
            74,
            4,
            240,
            133,
            61,
            93,
            138,
            26,
            107,
            55,
            232,
            154,
            60,
            26,
            246,
            86,
            237,
            205,
            236,
            57,
            219,
            135,
            165,
            4,
            237,
            216,
            68,
            105,
        )
    ),
    "scripts/live_stand.py": bytes(
        (
            159,
            80,
            91,
            103,
            12,
            71,
            211,
            204,
            0,
            128,
            209,
            180,
            54,
            215,
            187,
            25,
            173,
            16,
            180,
            96,
            178,
            12,
            6,
            108,
            45,
            217,
            84,
            192,
            60,
            161,
            60,
            181,
        )
    ),
    "scripts/quality/helm_rendered_target_overlay.py": bytes(
        (
            238,
            83,
            160,
            7,
            212,
            180,
            162,
            214,
            130,
            251,
            194,
            179,
            58,
            123,
            126,
            91,
            145,
            27,
            167,
            20,
            207,
            16,
            233,
            67,
            21,
            230,
            32,
            234,
            77,
            247,
            215,
            232,
        )
    ),
    "scripts/quality/helm_semgrep_profile_registry.json": bytes(
        (
            101,
            54,
            204,
            151,
            31,
            73,
            63,
            115,
            126,
            244,
            159,
            173,
            99,
            115,
            81,
            183,
            133,
            124,
            17,
            255,
            249,
            50,
            179,
            19,
            250,
            194,
            251,
            135,
            189,
            185,
            83,
            69,
        )
    ),
    "tests/fixtures/owned_baseline_postgres.py": bytes(
        (
            143,
            9,
            157,
            42,
            201,
            70,
            254,
            170,
            6,
            206,
            102,
            146,
            185,
            185,
            176,
            52,
            72,
            118,
            2,
            175,
            227,
            248,
            70,
            12,
            94,
            53,
            152,
            164,
            114,
            47,
            184,
            75,
        )
    ),
    "tests/integration/test_aud433_notifications_baseline_partition.py": bytes(
        (
            201,
            129,
            188,
            5,
            56,
            215,
            222,
            57,
            189,
            19,
            180,
            213,
            123,
            5,
            166,
            187,
            37,
            65,
            202,
            80,
            66,
            82,
            69,
            166,
            31,
            204,
            144,
            178,
            176,
            13,
            102,
            109,
        )
    ),
    "tests/integration/test_mvp_baseline_schema_equivalence.py": bytes(
        (
            165,
            215,
            227,
            87,
            247,
            178,
            12,
            65,
            177,
            32,
            9,
            51,
            101,
            179,
            220,
            147,
            180,
            118,
            146,
            177,
            105,
            164,
            112,
            180,
            31,
            65,
            241,
            11,
            99,
            162,
            175,
            121,
        )
    ),
    "tests/test_helm_rendered_target_overlay.py": bytes(
        (
            226,
            240,
            65,
            141,
            110,
            123,
            24,
            138,
            85,
            56,
            100,
            92,
            214,
            85,
            140,
            181,
            159,
            3,
            225,
            45,
            239,
            174,
            180,
            181,
            116,
            108,
            102,
            217,
            80,
            12,
            221,
            133,
        )
    ),
    "tests/test_internal_mtls_kind_contract.py": bytes(
        (
            110,
            198,
            109,
            43,
            39,
            243,
            111,
            15,
            144,
            43,
            231,
            139,
            161,
            163,
            7,
            69,
            115,
            53,
            193,
            195,
            60,
            115,
            126,
            39,
            88,
            117,
            239,
            155,
            159,
            160,
            96,
            122,
        )
    ),
    "tests/test_logging_pii_redaction_contract.py": bytes(
        (
            85,
            171,
            52,
            160,
            153,
            107,
            212,
            125,
            10,
            209,
            88,
            86,
            153,
            31,
            222,
            179,
            64,
            122,
            232,
            88,
            120,
            83,
            171,
            226,
            52,
            246,
            218,
            162,
            49,
            116,
            60,
            44,
        )
    ),
    "tests/test_logging_redos_aud380.py": bytes(
        (
            181,
            187,
            177,
            39,
            24,
            177,
            109,
            24,
            132,
            71,
            240,
            223,
            69,
            119,
            198,
            116,
            227,
            37,
            36,
            47,
            144,
            146,
            118,
            36,
            149,
            111,
            254,
            243,
            72,
            203,
            230,
            218,
        )
    ),
    "tests/test_otel_logging_bridge.py": bytes(
        (
            57,
            68,
            226,
            177,
            242,
            117,
            27,
            34,
            23,
            111,
            165,
            178,
            28,
            114,
            190,
            111,
            181,
            91,
            92,
            34,
            74,
            177,
            81,
            122,
            33,
            212,
            213,
            245,
            79,
            46,
            28,
            8,
        )
    ),
}
_AUD380_PENDING_OWNER_RECORDS = [
    {
        "approval_status": "NOT_APPROVED",
        "category": "public_integrity_digest",
        "evidence": "Semgrep disposition companion SHA-256 for "
        "tests/test_otel_logging_bridge.py; literal matches that current file "
        "hash and the declared companion in the existing disposition for the "
        "regex-DOS finding on app/core/logging.py. Public source-integrity "
        "metadata, not credential material; literal omitted.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                41,
                226,
                48,
                194,
                246,
                77,
                76,
                254,
                122,
                142,
                139,
                183,
                53,
                205,
                133,
                30,
                11,
                46,
                215,
                148,
            ],
            "path": "quality/semgrep-dispositions.json",
            "type": "Hex High Entropy String",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
    {
        "approval_status": "NOT_APPROVED",
        "category": "public_integrity_digest",
        "evidence": "Public SHA-256 source-integrity companion pin at "
        "quality/semgrep-dispositions.json:189 for scripts/live_stand.py, "
        "declared by Semgrep disposition(s) for scripts/owned_nats_process.py "
        "(python.django.security.injection.command.subprocess-injection.subprocess-injection). "
        "The exact literal matches the current main source bytes and is public "
        "integrity metadata, not credential material; literal omitted.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                96,
                108,
                195,
                192,
                195,
                246,
                59,
                158,
                82,
                3,
                135,
                69,
                66,
                222,
                155,
                168,
                210,
                230,
                71,
                169,
            ],
            "path": "quality/semgrep-dispositions.json",
            "type": "Hex High Entropy String",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
    {
        "approval_status": "NOT_APPROVED",
        "category": "public_integrity_digest",
        "evidence": "Public SHA-256 source-integrity companion pin at "
        "quality/semgrep-dispositions.json:77 for "
        "frontend/scripts/visual-smoke-contract.test.mjs, declared by Semgrep "
        "disposition(s) for frontend/scripts/authenticated-visual-audit.mjs "
        "(javascript.lang.security.audit.detect-redos.detect-redos). The exact "
        "literal matches the current main source bytes and is public integrity "
        "metadata, not credential material; literal omitted.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                62,
                174,
                193,
                241,
                112,
                115,
                133,
                90,
                248,
                237,
                157,
                83,
                35,
                122,
                184,
                184,
                243,
                229,
                98,
                235,
            ],
            "path": "quality/semgrep-dispositions.json",
            "type": "Hex High Entropy String",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
    {
        "approval_status": "NOT_APPROVED",
        "category": "public_integrity_digest",
        "evidence": "Public SHA-256 source-integrity companion pin at "
        "quality/semgrep-dispositions.json:469 for "
        "frontend/wasm-sanitizer/pkg/package.json, declared by Semgrep "
        "disposition(s) for frontend/src/components/ui/SafeHtml.tsx "
        "(typescript.react.security.audit.react-dangerouslysetinnerhtml.react-dangerouslysetinnerhtml). "
        "The exact literal matches the current main source bytes and is public "
        "integrity metadata, not credential material; literal omitted.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                171,
                64,
                82,
                148,
                72,
                30,
                58,
                196,
                175,
                43,
                180,
                112,
                128,
                150,
                47,
                108,
                92,
                221,
                74,
                237,
            ],
            "path": "quality/semgrep-dispositions.json",
            "type": "Hex High Entropy String",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
    {
        "approval_status": "NOT_APPROVED",
        "category": "public_integrity_digest",
        "evidence": "Public SHA-256 source-integrity companion pin at "
        "quality/semgrep-dispositions.json:481 for frontend/package.json, "
        "declared by Semgrep disposition(s) for "
        "frontend/src/components/ui/SafeHtml.tsx "
        "(typescript.react.security.audit.react-dangerouslysetinnerhtml.react-dangerouslysetinnerhtml). "
        "The exact literal matches the current main source bytes and is public "
        "integrity metadata, not credential material; literal omitted.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                179,
                31,
                21,
                51,
                109,
                183,
                55,
                123,
                118,
                54,
                153,
                147,
                76,
                70,
                132,
                12,
                84,
                188,
                235,
                0,
            ],
            "path": "quality/semgrep-dispositions.json",
            "type": "Hex High Entropy String",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
    {
        "approval_status": "NOT_APPROVED",
        "category": "public_integrity_digest",
        "evidence": "Semgrep disposition companion SHA-256 for app/core/otel_logging.py; "
        "literal matches that current file hash and the declared companion in "
        "the existing disposition for the regex-DOS finding on "
        "app/core/logging.py. Public source-integrity metadata, not credential "
        "material; literal omitted.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                205,
                173,
                143,
                192,
                215,
                54,
                205,
                124,
                209,
                17,
                59,
                80,
                229,
                83,
                6,
                50,
                92,
                246,
                111,
                83,
            ],
            "path": "quality/semgrep-dispositions.json",
            "type": "Hex High Entropy String",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
    {
        "approval_status": "NOT_APPROVED",
        "category": "public_integrity_digest",
        "evidence": "Semgrep disposition companion SHA-256 for app/core/observability.py; "
        "literal matches that current file hash and the declared companion in "
        "the existing disposition for the regex-DOS finding on "
        "app/core/logging.py. Public source-integrity metadata, not credential "
        "material; literal omitted.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                212,
                79,
                231,
                20,
                66,
                26,
                238,
                161,
                155,
                95,
                107,
                197,
                188,
                125,
                91,
                29,
                171,
                233,
                36,
                77,
            ],
            "path": "quality/semgrep-dispositions.json",
            "type": "Hex High Entropy String",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
    {
        "approval_status": "NOT_APPROVED",
        "category": "public_integrity_digest",
        "evidence": "Public SHA-256 source-integrity companion pin at "
        "quality/semgrep-dispositions.json:225 for .github/workflows/deploy.yml, "
        "declared by Semgrep disposition(s) for "
        ".github/scripts/validate_mfa_smoke_path.py "
        "(python.lang.security.audit.dangerous-subprocess-use-tainted-env-args.dangerous-subprocess-use-tainted-env-args). "
        "The exact literal matches the current main source bytes and is public "
        "integrity metadata, not credential material; literal omitted.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                221,
                23,
                201,
                30,
                59,
                96,
                188,
                41,
                102,
                129,
                190,
                72,
                124,
                92,
                67,
                125,
                211,
                167,
                65,
                122,
            ],
            "path": "quality/semgrep-dispositions.json",
            "type": "Hex High Entropy String",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
    {
        "approval_status": "NOT_APPROVED",
        "category": "public_integrity_digest",
        "evidence": "Public SHA-256 source-integrity companion pin at "
        "quality/semgrep-dispositions.json:453 for "
        "frontend/WASM_SOURCE_PROVENANCE.json, declared by Semgrep "
        "disposition(s) for frontend/src/components/ui/SafeHtml.tsx "
        "(typescript.react.security.audit.react-dangerouslysetinnerhtml.react-dangerouslysetinnerhtml). "
        "The exact literal matches the current main source bytes and is public "
        "integrity metadata, not credential material; literal omitted.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                232,
                205,
                138,
                154,
                175,
                169,
                46,
                75,
                170,
                239,
                97,
                120,
                11,
                81,
                214,
                80,
                78,
                128,
                63,
                2,
            ],
            "path": "quality/semgrep-dispositions.json",
            "type": "Hex High Entropy String",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
    {
        "approval_status": "NOT_APPROVED",
        "category": "public_integrity_digest",
        "evidence": "Public SHA-256 source-integrity companion pin at "
        "quality/semgrep-dispositions.json:461 for "
        "frontend/wasm-sanitizer/Cargo.toml, declared by Semgrep disposition(s) "
        "for frontend/src/components/ui/SafeHtml.tsx "
        "(typescript.react.security.audit.react-dangerouslysetinnerhtml.react-dangerouslysetinnerhtml). "
        "The exact literal matches the current main source bytes and is public "
        "integrity metadata, not credential material; literal omitted.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                238,
                39,
                63,
                126,
                253,
                5,
                14,
                121,
                123,
                138,
                24,
                157,
                19,
                67,
                79,
                135,
                153,
                94,
                236,
                175,
            ],
            "path": "quality/semgrep-dispositions.json",
            "type": "Hex High Entropy String",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
    {
        "approval_status": "NOT_APPROVED",
        "category": "public_integrity_digest",
        "evidence": "Public SHA-256 source-integrity companion pin at "
        "quality/semgrep-dispositions.json:485 for frontend/package-lock.json, "
        "declared by Semgrep disposition(s) for "
        "frontend/src/components/ui/SafeHtml.tsx "
        "(typescript.react.security.audit.react-dangerouslysetinnerhtml.react-dangerouslysetinnerhtml). "
        "The exact literal matches the current main source bytes and is public "
        "integrity metadata, not credential material; literal omitted.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                242,
                251,
                78,
                248,
                233,
                15,
                162,
                186,
                115,
                61,
                141,
                116,
                21,
                38,
                223,
                21,
                231,
                194,
                5,
                40,
            ],
            "path": "quality/semgrep-dispositions.json",
            "type": "Hex High Entropy String",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
    {
        "approval_status": "NOT_APPROVED",
        "category": "external_kubernetes_secret_reference",
        "evidence": "Kubernetes external Secret object name or key reference; not credential "
        "material. Exact source field "
        "internalGrpcMTLS.gatewayClient.existingSecret at "
        "scripts/kind/aud373_internal_mtls_proof.sh:246; "
        "charts/university-ecosystem/templates/gateway-deployment.yaml:192 "
        "renders the field as secretName for the TLS volume. Literal omitted.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                72,
                181,
                183,
                235,
                226,
                138,
                58,
                11,
                133,
                115,
                118,
                62,
                187,
                137,
                54,
                156,
                32,
                38,
                207,
                133,
            ],
            "path": "scripts/kind/aud373_internal_mtls_proof.sh",
            "type": "Secret Keyword",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
    {
        "approval_status": "NOT_APPROVED",
        "category": "external_kubernetes_secret_reference",
        "evidence": "Kubernetes external Secret object name or key reference; not credential "
        "material. Exact source field "
        "internalGrpcMTLS.fileProcessorServer.existingSecret at "
        "scripts/kind/aud373_internal_mtls_proof.sh:248; "
        "charts/university-ecosystem/templates/file-processor-deployment.yaml:196 "
        "renders the field as secretName for the TLS volume. Literal omitted.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                190,
                254,
                225,
                86,
                25,
                144,
                171,
                40,
                21,
                38,
                254,
                179,
                233,
                64,
                127,
                76,
                82,
                31,
                100,
                153,
            ],
            "path": "scripts/kind/aud373_internal_mtls_proof.sh",
            "type": "Secret Keyword",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
    {
        "approval_status": "NOT_APPROVED",
        "category": "public_integrity_digest",
        "evidence": "Public SHA-256 pin for "
        "scripts/quality/helm_semgrep_profile_registry.json; the exact digest "
        "matches the current registry bytes and is used as a source-integrity "
        "check, not as credential material.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                92,
                4,
                48,
                60,
                142,
                174,
                166,
                4,
                74,
                195,
                133,
                169,
                98,
                25,
                8,
                91,
                4,
                238,
                106,
                33,
            ],
            "path": "scripts/quality/helm_rendered_target_overlay.py",
            "type": "Hex High Entropy String",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
    {
        "approval_status": "NOT_APPROVED",
        "category": "public_integrity_digest",
        "evidence": "Public integrity digest: SOURCE_SHA256 pin in "
        "tests/integration/test_aud433_notifications_baseline_partition.py:38 "
        "for tests/integration/test_mvp_baseline_schema_equivalence.py; the "
        "exact value matches current source bytes and the test recomputes and "
        "asserts the binding before its schema checks. This is public "
        "source-integrity metadata, not credential material; literal omitted.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                151,
                220,
                198,
                119,
                83,
                226,
                96,
                3,
                226,
                99,
                188,
                46,
                237,
                41,
                167,
                129,
                163,
                46,
                90,
                78,
            ],
            "path": "tests/integration/test_aud433_notifications_baseline_partition.py",
            "type": "Hex High Entropy String",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
    {
        "approval_status": "NOT_APPROVED",
        "category": "public_integrity_digest",
        "evidence": "Public integrity digest: SOURCE_SHA256 pin in "
        "tests/integration/test_aud433_notifications_baseline_partition.py:35 "
        "for tests/fixtures/owned_baseline_postgres.py; the exact value matches "
        "current source bytes and the test recomputes and asserts the binding "
        "before its schema checks. This is public source-integrity metadata, not "
        "credential material; literal omitted.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                161,
                87,
                128,
                131,
                219,
                96,
                152,
                248,
                166,
                82,
                38,
                180,
                113,
                140,
                117,
                245,
                8,
                183,
                210,
                205,
            ],
            "path": "tests/integration/test_aud433_notifications_baseline_partition.py",
            "type": "Hex High Entropy String",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
    {
        "approval_status": "NOT_APPROVED",
        "category": "public_integrity_digest",
        "evidence": "Public integrity digest: SOURCE_SHA256 pin in "
        "tests/integration/test_aud433_notifications_baseline_partition.py:32 "
        "for alembic/versions/202611020000_mvp_baseline.py; the exact value "
        "matches current source bytes and the test recomputes and asserts the "
        "binding before its schema checks. This is public source-integrity "
        "metadata, not credential material; literal omitted.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                243,
                210,
                64,
                149,
                243,
                17,
                167,
                236,
                53,
                209,
                64,
                254,
                108,
                204,
                182,
                192,
                218,
                114,
                29,
                40,
            ],
            "path": "tests/integration/test_aud433_notifications_baseline_partition.py",
            "type": "Hex High Entropy String",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
    {
        "approval_status": "NOT_APPROVED",
        "category": "public_integrity_digest",
        "evidence": "Public SHA-256 pin for "
        "scripts/quality/helm_semgrep_profile_registry.json; the exact digest "
        "matches the current registry bytes and is used as a source-integrity "
        "check, not as credential material.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                92,
                4,
                48,
                60,
                142,
                174,
                166,
                4,
                74,
                195,
                133,
                169,
                98,
                25,
                8,
                91,
                4,
                238,
                106,
                33,
            ],
            "path": "tests/test_helm_rendered_target_overlay.py",
            "type": "Hex High Entropy String",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
    {
        "approval_status": "NOT_APPROVED",
        "category": "ci_test_contract_sentinel",
        "evidence": "Test-only local PersistentVolume path sentinel asserted at "
        "spec.local.path. The value matches the helper-generated path from a "
        "fixed RUN_SUFFIX; the contract test uses a temporary work directory and "
        "local stubs for kind, docker, and kubectl, then parses/asserts "
        "generated YAML. It is path fixture data, not credential/key material; "
        "literal omitted.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                77,
                40,
                149,
                72,
                118,
                40,
                115,
                199,
                72,
                221,
                231,
                105,
                235,
                149,
                15,
                76,
                25,
                76,
                7,
                30,
            ],
            "path": "tests/test_internal_mtls_kind_contract.py",
            "type": "Base64 High Entropy String",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
    {
        "approval_status": "NOT_APPROVED",
        "category": "external_kubernetes_secret_reference",
        "evidence": "Kubernetes external Secret object name or key reference; not credential "
        "material. Exact source field "
        "internalGrpcMTLS.gatewayClient.existingSecret at "
        "tests/test_internal_mtls_kind_contract.py:1352; "
        "charts/university-ecosystem/templates/gateway-deployment.yaml:192 "
        "renders the field as secretName for the TLS volume. Literal omitted.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                72,
                181,
                183,
                235,
                226,
                138,
                58,
                11,
                133,
                115,
                118,
                62,
                187,
                137,
                54,
                156,
                32,
                38,
                207,
                133,
            ],
            "path": "tests/test_internal_mtls_kind_contract.py",
            "type": "Secret Keyword",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
    {
        "approval_status": "NOT_APPROVED",
        "category": "external_kubernetes_secret_reference",
        "evidence": "Kubernetes external Secret object name or key reference; not credential "
        "material. Exact source field "
        "internalGrpcMTLS.fileProcessorServer.existingSecret at "
        "tests/test_internal_mtls_kind_contract.py:1353; "
        "charts/university-ecosystem/templates/file-processor-deployment.yaml:196 "
        "renders the field as secretName for the TLS volume. Literal omitted.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                190,
                254,
                225,
                86,
                25,
                144,
                171,
                40,
                21,
                38,
                254,
                179,
                233,
                64,
                127,
                76,
                82,
                31,
                100,
                153,
            ],
            "path": "tests/test_internal_mtls_kind_contract.py",
            "type": "Secret Keyword",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
]
_AUD380_PENDING_OWNER_IDENTITIES = frozenset(
    {
        (
            "quality/semgrep-dispositions.json",
            "Hex High Entropy String",
            (
                41,
                226,
                48,
                194,
                246,
                77,
                76,
                254,
                122,
                142,
                139,
                183,
                53,
                205,
                133,
                30,
                11,
                46,
                215,
                148,
            ),
        ),
        (
            "quality/semgrep-dispositions.json",
            "Hex High Entropy String",
            (
                96,
                108,
                195,
                192,
                195,
                246,
                59,
                158,
                82,
                3,
                135,
                69,
                66,
                222,
                155,
                168,
                210,
                230,
                71,
                169,
            ),
        ),
        (
            "quality/semgrep-dispositions.json",
            "Hex High Entropy String",
            (
                62,
                174,
                193,
                241,
                112,
                115,
                133,
                90,
                248,
                237,
                157,
                83,
                35,
                122,
                184,
                184,
                243,
                229,
                98,
                235,
            ),
        ),
        (
            "quality/semgrep-dispositions.json",
            "Hex High Entropy String",
            (
                171,
                64,
                82,
                148,
                72,
                30,
                58,
                196,
                175,
                43,
                180,
                112,
                128,
                150,
                47,
                108,
                92,
                221,
                74,
                237,
            ),
        ),
        (
            "quality/semgrep-dispositions.json",
            "Hex High Entropy String",
            (
                179,
                31,
                21,
                51,
                109,
                183,
                55,
                123,
                118,
                54,
                153,
                147,
                76,
                70,
                132,
                12,
                84,
                188,
                235,
                0,
            ),
        ),
        (
            "quality/semgrep-dispositions.json",
            "Hex High Entropy String",
            (
                205,
                173,
                143,
                192,
                215,
                54,
                205,
                124,
                209,
                17,
                59,
                80,
                229,
                83,
                6,
                50,
                92,
                246,
                111,
                83,
            ),
        ),
        (
            "quality/semgrep-dispositions.json",
            "Hex High Entropy String",
            (
                212,
                79,
                231,
                20,
                66,
                26,
                238,
                161,
                155,
                95,
                107,
                197,
                188,
                125,
                91,
                29,
                171,
                233,
                36,
                77,
            ),
        ),
        (
            "quality/semgrep-dispositions.json",
            "Hex High Entropy String",
            (
                221,
                23,
                201,
                30,
                59,
                96,
                188,
                41,
                102,
                129,
                190,
                72,
                124,
                92,
                67,
                125,
                211,
                167,
                65,
                122,
            ),
        ),
        (
            "quality/semgrep-dispositions.json",
            "Hex High Entropy String",
            (
                232,
                205,
                138,
                154,
                175,
                169,
                46,
                75,
                170,
                239,
                97,
                120,
                11,
                81,
                214,
                80,
                78,
                128,
                63,
                2,
            ),
        ),
        (
            "quality/semgrep-dispositions.json",
            "Hex High Entropy String",
            (
                238,
                39,
                63,
                126,
                253,
                5,
                14,
                121,
                123,
                138,
                24,
                157,
                19,
                67,
                79,
                135,
                153,
                94,
                236,
                175,
            ),
        ),
        (
            "quality/semgrep-dispositions.json",
            "Hex High Entropy String",
            (
                242,
                251,
                78,
                248,
                233,
                15,
                162,
                186,
                115,
                61,
                141,
                116,
                21,
                38,
                223,
                21,
                231,
                194,
                5,
                40,
            ),
        ),
        (
            "scripts/kind/aud373_internal_mtls_proof.sh",
            "Secret Keyword",
            (
                72,
                181,
                183,
                235,
                226,
                138,
                58,
                11,
                133,
                115,
                118,
                62,
                187,
                137,
                54,
                156,
                32,
                38,
                207,
                133,
            ),
        ),
        (
            "scripts/kind/aud373_internal_mtls_proof.sh",
            "Secret Keyword",
            (
                190,
                254,
                225,
                86,
                25,
                144,
                171,
                40,
                21,
                38,
                254,
                179,
                233,
                64,
                127,
                76,
                82,
                31,
                100,
                153,
            ),
        ),
        (
            "scripts/quality/helm_rendered_target_overlay.py",
            "Hex High Entropy String",
            (
                92,
                4,
                48,
                60,
                142,
                174,
                166,
                4,
                74,
                195,
                133,
                169,
                98,
                25,
                8,
                91,
                4,
                238,
                106,
                33,
            ),
        ),
        (
            "tests/integration/test_aud433_notifications_baseline_partition.py",
            "Hex High Entropy String",
            (
                151,
                220,
                198,
                119,
                83,
                226,
                96,
                3,
                226,
                99,
                188,
                46,
                237,
                41,
                167,
                129,
                163,
                46,
                90,
                78,
            ),
        ),
        (
            "tests/integration/test_aud433_notifications_baseline_partition.py",
            "Hex High Entropy String",
            (
                161,
                87,
                128,
                131,
                219,
                96,
                152,
                248,
                166,
                82,
                38,
                180,
                113,
                140,
                117,
                245,
                8,
                183,
                210,
                205,
            ),
        ),
        (
            "tests/integration/test_aud433_notifications_baseline_partition.py",
            "Hex High Entropy String",
            (
                243,
                210,
                64,
                149,
                243,
                17,
                167,
                236,
                53,
                209,
                64,
                254,
                108,
                204,
                182,
                192,
                218,
                114,
                29,
                40,
            ),
        ),
        (
            "tests/test_helm_rendered_target_overlay.py",
            "Hex High Entropy String",
            (
                92,
                4,
                48,
                60,
                142,
                174,
                166,
                4,
                74,
                195,
                133,
                169,
                98,
                25,
                8,
                91,
                4,
                238,
                106,
                33,
            ),
        ),
        (
            "tests/test_internal_mtls_kind_contract.py",
            "Base64 High Entropy String",
            (
                77,
                40,
                149,
                72,
                118,
                40,
                115,
                199,
                72,
                221,
                231,
                105,
                235,
                149,
                15,
                76,
                25,
                76,
                7,
                30,
            ),
        ),
        (
            "tests/test_internal_mtls_kind_contract.py",
            "Secret Keyword",
            (
                72,
                181,
                183,
                235,
                226,
                138,
                58,
                11,
                133,
                115,
                118,
                62,
                187,
                137,
                54,
                156,
                32,
                38,
                207,
                133,
            ),
        ),
        (
            "tests/test_internal_mtls_kind_contract.py",
            "Secret Keyword",
            (
                190,
                254,
                225,
                86,
                25,
                144,
                171,
                40,
                21,
                38,
                254,
                179,
                233,
                64,
                127,
                76,
                82,
                31,
                100,
                153,
            ),
        ),
    }
)
_AUD380_CURRENT_DELTA_IDENTITY_SOURCE_LINES = (
    (
        "quality/semgrep-dispositions.json",
        "Hex High Entropy String",
        (
            41,
            226,
            48,
            194,
            246,
            77,
            76,
            254,
            122,
            142,
            139,
            183,
            53,
            205,
            133,
            30,
            11,
            46,
            215,
            148,
        ),
        "public_integrity_digest",
        329,
    ),
    (
        "quality/semgrep-dispositions.json",
        "Hex High Entropy String",
        (
            96,
            108,
            195,
            192,
            195,
            246,
            59,
            158,
            82,
            3,
            135,
            69,
            66,
            222,
            155,
            168,
            210,
            230,
            71,
            169,
        ),
        "public_integrity_digest",
        189,
    ),
    (
        "quality/semgrep-dispositions.json",
        "Hex High Entropy String",
        (
            62,
            174,
            193,
            241,
            112,
            115,
            133,
            90,
            248,
            237,
            157,
            83,
            35,
            122,
            184,
            184,
            243,
            229,
            98,
            235,
        ),
        "public_integrity_digest",
        77,
    ),
    (
        "quality/semgrep-dispositions.json",
        "Hex High Entropy String",
        (
            171,
            64,
            82,
            148,
            72,
            30,
            58,
            196,
            175,
            43,
            180,
            112,
            128,
            150,
            47,
            108,
            92,
            221,
            74,
            237,
        ),
        "public_integrity_digest",
        469,
    ),
    (
        "quality/semgrep-dispositions.json",
        "Hex High Entropy String",
        (
            179,
            31,
            21,
            51,
            109,
            183,
            55,
            123,
            118,
            54,
            153,
            147,
            76,
            70,
            132,
            12,
            84,
            188,
            235,
            0,
        ),
        "public_integrity_digest",
        481,
    ),
    (
        "quality/semgrep-dispositions.json",
        "Hex High Entropy String",
        (
            205,
            173,
            143,
            192,
            215,
            54,
            205,
            124,
            209,
            17,
            59,
            80,
            229,
            83,
            6,
            50,
            92,
            246,
            111,
            83,
        ),
        "public_integrity_digest",
        313,
    ),
    (
        "quality/semgrep-dispositions.json",
        "Hex High Entropy String",
        (
            212,
            79,
            231,
            20,
            66,
            26,
            238,
            161,
            155,
            95,
            107,
            197,
            188,
            125,
            91,
            29,
            171,
            233,
            36,
            77,
        ),
        "public_integrity_digest",
        309,
    ),
    (
        "quality/semgrep-dispositions.json",
        "Hex High Entropy String",
        (
            221,
            23,
            201,
            30,
            59,
            96,
            188,
            41,
            102,
            129,
            190,
            72,
            124,
            92,
            67,
            125,
            211,
            167,
            65,
            122,
        ),
        "public_integrity_digest",
        225,
    ),
    (
        "quality/semgrep-dispositions.json",
        "Hex High Entropy String",
        (
            232,
            205,
            138,
            154,
            175,
            169,
            46,
            75,
            170,
            239,
            97,
            120,
            11,
            81,
            214,
            80,
            78,
            128,
            63,
            2,
        ),
        "public_integrity_digest",
        453,
    ),
    (
        "quality/semgrep-dispositions.json",
        "Hex High Entropy String",
        (
            238,
            39,
            63,
            126,
            253,
            5,
            14,
            121,
            123,
            138,
            24,
            157,
            19,
            67,
            79,
            135,
            153,
            94,
            236,
            175,
        ),
        "public_integrity_digest",
        461,
    ),
    (
        "quality/semgrep-dispositions.json",
        "Hex High Entropy String",
        (
            242,
            251,
            78,
            248,
            233,
            15,
            162,
            186,
            115,
            61,
            141,
            116,
            21,
            38,
            223,
            21,
            231,
            194,
            5,
            40,
        ),
        "public_integrity_digest",
        485,
    ),
    (
        "scripts/kind/aud373_internal_mtls_proof.sh",
        "Secret Keyword",
        (
            72,
            181,
            183,
            235,
            226,
            138,
            58,
            11,
            133,
            115,
            118,
            62,
            187,
            137,
            54,
            156,
            32,
            38,
            207,
            133,
        ),
        "external_kubernetes_secret_reference",
        246,
    ),
    (
        "scripts/kind/aud373_internal_mtls_proof.sh",
        "Secret Keyword",
        (
            190,
            254,
            225,
            86,
            25,
            144,
            171,
            40,
            21,
            38,
            254,
            179,
            233,
            64,
            127,
            76,
            82,
            31,
            100,
            153,
        ),
        "external_kubernetes_secret_reference",
        248,
    ),
    (
        "scripts/quality/helm_rendered_target_overlay.py",
        "Hex High Entropy String",
        (
            92,
            4,
            48,
            60,
            142,
            174,
            166,
            4,
            74,
            195,
            133,
            169,
            98,
            25,
            8,
            91,
            4,
            238,
            106,
            33,
        ),
        "public_integrity_digest",
        37,
    ),
    (
        "tests/integration/test_aud433_notifications_baseline_partition.py",
        "Hex High Entropy String",
        (
            151,
            220,
            198,
            119,
            83,
            226,
            96,
            3,
            226,
            99,
            188,
            46,
            237,
            41,
            167,
            129,
            163,
            46,
            90,
            78,
        ),
        "public_integrity_digest",
        38,
    ),
    (
        "tests/integration/test_aud433_notifications_baseline_partition.py",
        "Hex High Entropy String",
        (
            161,
            87,
            128,
            131,
            219,
            96,
            152,
            248,
            166,
            82,
            38,
            180,
            113,
            140,
            117,
            245,
            8,
            183,
            210,
            205,
        ),
        "public_integrity_digest",
        35,
    ),
    (
        "tests/integration/test_aud433_notifications_baseline_partition.py",
        "Hex High Entropy String",
        (
            243,
            210,
            64,
            149,
            243,
            17,
            167,
            236,
            53,
            209,
            64,
            254,
            108,
            204,
            182,
            192,
            218,
            114,
            29,
            40,
        ),
        "public_integrity_digest",
        32,
    ),
    (
        "tests/test_helm_rendered_target_overlay.py",
        "Hex High Entropy String",
        (
            92,
            4,
            48,
            60,
            142,
            174,
            166,
            4,
            74,
            195,
            133,
            169,
            98,
            25,
            8,
            91,
            4,
            238,
            106,
            33,
        ),
        "public_integrity_digest",
        96,
    ),
    (
        "tests/test_internal_mtls_kind_contract.py",
        "Base64 High Entropy String",
        (
            77,
            40,
            149,
            72,
            118,
            40,
            115,
            199,
            72,
            221,
            231,
            105,
            235,
            149,
            15,
            76,
            25,
            76,
            7,
            30,
        ),
        "ci_test_contract_sentinel",
        1981,
    ),
    (
        "tests/test_internal_mtls_kind_contract.py",
        "Secret Keyword",
        (
            72,
            181,
            183,
            235,
            226,
            138,
            58,
            11,
            133,
            115,
            118,
            62,
            187,
            137,
            54,
            156,
            32,
            38,
            207,
            133,
        ),
        "external_kubernetes_secret_reference",
        1352,
    ),
    (
        "tests/test_internal_mtls_kind_contract.py",
        "Secret Keyword",
        (
            190,
            254,
            225,
            86,
            25,
            144,
            171,
            40,
            21,
            38,
            254,
            179,
            233,
            64,
            127,
            76,
            82,
            31,
            100,
            153,
        ),
        "external_kubernetes_secret_reference",
        1353,
    ),
)
_AUD380_CURRENT_DELTA_COMPANION_SOURCE_LINES = (
    ("charts/university-ecosystem/templates/file-processor-deployment.yaml", 196),
    ("charts/university-ecosystem/templates/gateway-deployment.yaml", 192),
    ("charts/university-ecosystem/values.yaml", 112),
    ("charts/university-ecosystem/values.yaml", 117),
    ("quality/semgrep-dispositions.json", 77),
    ("quality/semgrep-dispositions.json", 189),
    ("quality/semgrep-dispositions.json", 225),
    ("quality/semgrep-dispositions.json", 309),
    ("quality/semgrep-dispositions.json", 313),
    ("quality/semgrep-dispositions.json", 317),
    ("quality/semgrep-dispositions.json", 321),
    ("quality/semgrep-dispositions.json", 325),
    ("quality/semgrep-dispositions.json", 329),
    ("quality/semgrep-dispositions.json", 453),
    ("quality/semgrep-dispositions.json", 461),
    ("quality/semgrep-dispositions.json", 469),
    ("quality/semgrep-dispositions.json", 481),
    ("quality/semgrep-dispositions.json", 485),
    ("scripts/kind/aud373_internal_mtls_proof.sh", 349),
    ("scripts/kind/aud373_internal_mtls_proof.sh", 369),
    ("tests/integration/test_aud433_notifications_baseline_partition.py", 58),
    ("tests/integration/test_aud433_notifications_baseline_partition.py", 59),
    ("tests/integration/test_aud433_notifications_baseline_partition.py", 61),
    ("tests/integration/test_aud433_notifications_baseline_partition.py", 62),
    ("tests/test_internal_mtls_kind_contract.py", 1931),
    ("tests/test_internal_mtls_kind_contract.py", 1936),
    ("tests/test_internal_mtls_kind_contract.py", 1937),
    ("tests/test_internal_mtls_kind_contract.py", 1945),
    ("tests/test_internal_mtls_kind_contract.py", 1949),
    ("tests/test_internal_mtls_kind_contract.py", 1953),
)
_AUD380_CURRENT_DELTA_SOURCE_LINE_HASHES = (
    (
        "charts/university-ecosystem/templates/file-processor-deployment.yaml",
        196,
        bytes(
            (
                65,
                201,
                105,
                239,
                119,
                59,
                68,
                30,
                30,
                106,
                20,
                223,
                57,
                36,
                130,
                102,
                117,
                225,
                177,
                78,
                227,
                30,
                225,
                175,
                8,
                226,
                183,
                48,
                189,
                6,
                129,
                193,
            )
        ),
        bytes(
            (
                82,
                154,
                134,
                117,
                46,
                85,
                191,
                85,
                105,
                3,
                153,
                136,
                0,
                174,
                50,
                158,
                116,
                24,
                50,
                49,
                44,
                104,
                219,
                154,
                255,
                252,
                81,
                39,
                245,
                228,
                247,
                98,
            )
        ),
    ),
    (
        "charts/university-ecosystem/templates/gateway-deployment.yaml",
        192,
        bytes(
            (
                131,
                234,
                205,
                108,
                214,
                107,
                113,
                239,
                103,
                30,
                246,
                87,
                232,
                4,
                42,
                79,
                181,
                169,
                33,
                162,
                220,
                10,
                18,
                219,
                201,
                244,
                7,
                60,
                244,
                162,
                31,
                168,
            )
        ),
        bytes(
            (
                146,
                164,
                33,
                180,
                227,
                187,
                93,
                48,
                121,
                118,
                179,
                185,
                145,
                75,
                204,
                47,
                64,
                63,
                197,
                64,
                129,
                191,
                33,
                169,
                204,
                221,
                3,
                243,
                121,
                249,
                0,
                99,
            )
        ),
    ),
    (
        "charts/university-ecosystem/values.yaml",
        112,
        bytes(
            (
                20,
                26,
                26,
                73,
                173,
                133,
                148,
                239,
                57,
                120,
                21,
                190,
                207,
                38,
                193,
                87,
                31,
                229,
                71,
                228,
                120,
                95,
                89,
                138,
                232,
                83,
                82,
                173,
                171,
                240,
                114,
                117,
            )
        ),
        bytes(
            (
                19,
                33,
                210,
                126,
                125,
                9,
                78,
                54,
                254,
                142,
                89,
                230,
                0,
                116,
                149,
                231,
                12,
                115,
                106,
                217,
                153,
                248,
                204,
                243,
                82,
                144,
                138,
                101,
                24,
                191,
                99,
                203,
            )
        ),
    ),
    (
        "charts/university-ecosystem/values.yaml",
        117,
        bytes(
            (
                20,
                26,
                26,
                73,
                173,
                133,
                148,
                239,
                57,
                120,
                21,
                190,
                207,
                38,
                193,
                87,
                31,
                229,
                71,
                228,
                120,
                95,
                89,
                138,
                232,
                83,
                82,
                173,
                171,
                240,
                114,
                117,
            )
        ),
        bytes(
            (
                205,
                130,
                65,
                155,
                249,
                165,
                210,
                202,
                176,
                213,
                26,
                17,
                90,
                219,
                138,
                35,
                196,
                109,
                234,
                173,
                210,
                64,
                177,
                194,
                252,
                109,
                21,
                114,
                54,
                16,
                40,
                228,
            )
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        77,
        bytes(
            (
                109,
                216,
                46,
                136,
                235,
                101,
                25,
                138,
                159,
                156,
                245,
                96,
                41,
                12,
                37,
                147,
                154,
                122,
                187,
                220,
                123,
                55,
                234,
                199,
                96,
                13,
                85,
                15,
                31,
                3,
                12,
                252,
            )
        ),
        bytes(
            (
                248,
                193,
                174,
                35,
                166,
                84,
                132,
                10,
                204,
                159,
                125,
                188,
                215,
                215,
                73,
                136,
                152,
                129,
                86,
                171,
                210,
                246,
                148,
                133,
                194,
                165,
                230,
                141,
                108,
                102,
                135,
                185,
            )
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        77,
        bytes(
            (
                109,
                216,
                46,
                136,
                235,
                101,
                25,
                138,
                159,
                156,
                245,
                96,
                41,
                12,
                37,
                147,
                154,
                122,
                187,
                220,
                123,
                55,
                234,
                199,
                96,
                13,
                85,
                15,
                31,
                3,
                12,
                252,
            )
        ),
        bytes(
            (
                248,
                193,
                174,
                35,
                166,
                84,
                132,
                10,
                204,
                159,
                125,
                188,
                215,
                215,
                73,
                136,
                152,
                129,
                86,
                171,
                210,
                246,
                148,
                133,
                194,
                165,
                230,
                141,
                108,
                102,
                135,
                185,
            )
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        189,
        bytes(
            (
                179,
                33,
                71,
                20,
                144,
                98,
                46,
                152,
                12,
                39,
                80,
                40,
                248,
                141,
                172,
                200,
                60,
                58,
                248,
                211,
                104,
                65,
                20,
                89,
                110,
                171,
                234,
                117,
                245,
                10,
                82,
                161,
            )
        ),
        bytes(
            (
                18,
                149,
                11,
                7,
                80,
                243,
                60,
                127,
                57,
                50,
                148,
                217,
                178,
                157,
                7,
                113,
                179,
                146,
                148,
                203,
                120,
                94,
                252,
                40,
                136,
                164,
                79,
                239,
                244,
                198,
                194,
                36,
            )
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        189,
        bytes(
            (
                179,
                33,
                71,
                20,
                144,
                98,
                46,
                152,
                12,
                39,
                80,
                40,
                248,
                141,
                172,
                200,
                60,
                58,
                248,
                211,
                104,
                65,
                20,
                89,
                110,
                171,
                234,
                117,
                245,
                10,
                82,
                161,
            )
        ),
        bytes(
            (
                18,
                149,
                11,
                7,
                80,
                243,
                60,
                127,
                57,
                50,
                148,
                217,
                178,
                157,
                7,
                113,
                179,
                146,
                148,
                203,
                120,
                94,
                252,
                40,
                136,
                164,
                79,
                239,
                244,
                198,
                194,
                36,
            )
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        225,
        bytes(
            (
                170,
                80,
                145,
                29,
                50,
                52,
                45,
                96,
                202,
                252,
                211,
                255,
                167,
                74,
                126,
                89,
                77,
                194,
                67,
                27,
                12,
                110,
                244,
                17,
                87,
                27,
                177,
                49,
                220,
                182,
                19,
                253,
            )
        ),
        bytes(
            (
                228,
                141,
                71,
                85,
                99,
                1,
                238,
                230,
                75,
                209,
                172,
                104,
                235,
                143,
                198,
                97,
                63,
                26,
                38,
                198,
                157,
                96,
                132,
                1,
                163,
                235,
                59,
                233,
                217,
                239,
                3,
                210,
            )
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        225,
        bytes(
            (
                170,
                80,
                145,
                29,
                50,
                52,
                45,
                96,
                202,
                252,
                211,
                255,
                167,
                74,
                126,
                89,
                77,
                194,
                67,
                27,
                12,
                110,
                244,
                17,
                87,
                27,
                177,
                49,
                220,
                182,
                19,
                253,
            )
        ),
        bytes(
            (
                228,
                141,
                71,
                85,
                99,
                1,
                238,
                230,
                75,
                209,
                172,
                104,
                235,
                143,
                198,
                97,
                63,
                26,
                38,
                198,
                157,
                96,
                132,
                1,
                163,
                235,
                59,
                233,
                217,
                239,
                3,
                210,
            )
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        309,
        bytes(
            (
                62,
                205,
                83,
                73,
                223,
                90,
                168,
                196,
                13,
                215,
                38,
                13,
                77,
                111,
                10,
                8,
                148,
                124,
                149,
                31,
                180,
                111,
                178,
                103,
                194,
                152,
                158,
                37,
                147,
                99,
                179,
                69,
            )
        ),
        bytes(
            (
                151,
                187,
                219,
                234,
                33,
                130,
                212,
                104,
                43,
                203,
                245,
                172,
                173,
                43,
                15,
                186,
                250,
                184,
                186,
                93,
                128,
                14,
                173,
                110,
                216,
                69,
                189,
                208,
                50,
                150,
                83,
                201,
            )
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        309,
        bytes(
            (
                62,
                205,
                83,
                73,
                223,
                90,
                168,
                196,
                13,
                215,
                38,
                13,
                77,
                111,
                10,
                8,
                148,
                124,
                149,
                31,
                180,
                111,
                178,
                103,
                194,
                152,
                158,
                37,
                147,
                99,
                179,
                69,
            )
        ),
        bytes(
            (
                151,
                187,
                219,
                234,
                33,
                130,
                212,
                104,
                43,
                203,
                245,
                172,
                173,
                43,
                15,
                186,
                250,
                184,
                186,
                93,
                128,
                14,
                173,
                110,
                216,
                69,
                189,
                208,
                50,
                150,
                83,
                201,
            )
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        313,
        bytes(
            (
                179,
                86,
                65,
                72,
                206,
                76,
                94,
                172,
                131,
                249,
                77,
                52,
                6,
                239,
                102,
                91,
                172,
                95,
                20,
                49,
                101,
                2,
                141,
                135,
                169,
                62,
                14,
                52,
                161,
                44,
                93,
                114,
            )
        ),
        bytes(
            (
                214,
                161,
                144,
                84,
                76,
                44,
                122,
                189,
                133,
                161,
                25,
                219,
                186,
                221,
                110,
                249,
                15,
                155,
                138,
                230,
                149,
                46,
                105,
                88,
                55,
                178,
                118,
                204,
                169,
                179,
                7,
                194,
            )
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        313,
        bytes(
            (
                179,
                86,
                65,
                72,
                206,
                76,
                94,
                172,
                131,
                249,
                77,
                52,
                6,
                239,
                102,
                91,
                172,
                95,
                20,
                49,
                101,
                2,
                141,
                135,
                169,
                62,
                14,
                52,
                161,
                44,
                93,
                114,
            )
        ),
        bytes(
            (
                214,
                161,
                144,
                84,
                76,
                44,
                122,
                189,
                133,
                161,
                25,
                219,
                186,
                221,
                110,
                249,
                15,
                155,
                138,
                230,
                149,
                46,
                105,
                88,
                55,
                178,
                118,
                204,
                169,
                179,
                7,
                194,
            )
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        317,
        bytes(
            (
                107,
                241,
                68,
                221,
                97,
                6,
                172,
                205,
                61,
                134,
                145,
                100,
                252,
                247,
                222,
                15,
                212,
                197,
                10,
                118,
                64,
                235,
                65,
                16,
                224,
                159,
                104,
                135,
                43,
                225,
                13,
                219,
            )
        ),
        bytes(
            (
                156,
                164,
                43,
                196,
                156,
                172,
                49,
                89,
                189,
                206,
                159,
                89,
                143,
                246,
                190,
                145,
                147,
                224,
                56,
                65,
                142,
                234,
                46,
                120,
                179,
                17,
                222,
                55,
                120,
                19,
                254,
                67,
            )
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        321,
        bytes(
            (
                253,
                211,
                34,
                166,
                208,
                128,
                186,
                30,
                78,
                80,
                172,
                4,
                235,
                122,
                222,
                81,
                5,
                195,
                192,
                251,
                187,
                47,
                102,
                151,
                120,
                191,
                166,
                138,
                251,
                143,
                48,
                0,
            )
        ),
        bytes(
            (
                197,
                219,
                79,
                177,
                48,
                32,
                246,
                77,
                178,
                160,
                56,
                140,
                108,
                125,
                146,
                68,
                166,
                166,
                171,
                8,
                153,
                39,
                155,
                246,
                71,
                239,
                17,
                99,
                227,
                54,
                223,
                105,
            )
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        325,
        bytes(
            (
                39,
                146,
                45,
                198,
                145,
                124,
                170,
                109,
                194,
                179,
                130,
                169,
                234,
                93,
                140,
                230,
                211,
                128,
                225,
                156,
                107,
                173,
                43,
                151,
                217,
                105,
                140,
                246,
                5,
                15,
                164,
                28,
            )
        ),
        bytes(
            (
                35,
                28,
                111,
                56,
                16,
                180,
                255,
                208,
                67,
                169,
                228,
                94,
                111,
                72,
                251,
                189,
                15,
                196,
                125,
                112,
                76,
                171,
                134,
                217,
                126,
                101,
                196,
                200,
                90,
                73,
                250,
                182,
            )
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        329,
        bytes(
            (
                190,
                7,
                134,
                204,
                73,
                12,
                83,
                89,
                150,
                245,
                74,
                175,
                43,
                150,
                233,
                73,
                238,
                54,
                247,
                200,
                61,
                249,
                47,
                6,
                242,
                181,
                149,
                38,
                27,
                221,
                59,
                3,
            )
        ),
        bytes(
            (
                241,
                195,
                216,
                56,
                234,
                159,
                240,
                168,
                215,
                67,
                52,
                171,
                107,
                206,
                95,
                52,
                201,
                219,
                12,
                218,
                238,
                115,
                235,
                6,
                76,
                89,
                78,
                147,
                196,
                219,
                156,
                72,
            )
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        329,
        bytes(
            (
                190,
                7,
                134,
                204,
                73,
                12,
                83,
                89,
                150,
                245,
                74,
                175,
                43,
                150,
                233,
                73,
                238,
                54,
                247,
                200,
                61,
                249,
                47,
                6,
                242,
                181,
                149,
                38,
                27,
                221,
                59,
                3,
            )
        ),
        bytes(
            (
                241,
                195,
                216,
                56,
                234,
                159,
                240,
                168,
                215,
                67,
                52,
                171,
                107,
                206,
                95,
                52,
                201,
                219,
                12,
                218,
                238,
                115,
                235,
                6,
                76,
                89,
                78,
                147,
                196,
                219,
                156,
                72,
            )
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        453,
        bytes(
            (
                222,
                230,
                74,
                231,
                34,
                184,
                69,
                190,
                115,
                93,
                62,
                8,
                182,
                99,
                245,
                87,
                66,
                44,
                81,
                252,
                171,
                129,
                242,
                70,
                161,
                123,
                102,
                120,
                131,
                248,
                101,
                58,
            )
        ),
        bytes(
            (
                25,
                215,
                200,
                24,
                126,
                1,
                196,
                42,
                167,
                142,
                96,
                49,
                7,
                40,
                14,
                66,
                215,
                203,
                171,
                73,
                220,
                32,
                175,
                47,
                154,
                71,
                106,
                176,
                222,
                72,
                217,
                201,
            )
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        453,
        bytes(
            (
                222,
                230,
                74,
                231,
                34,
                184,
                69,
                190,
                115,
                93,
                62,
                8,
                182,
                99,
                245,
                87,
                66,
                44,
                81,
                252,
                171,
                129,
                242,
                70,
                161,
                123,
                102,
                120,
                131,
                248,
                101,
                58,
            )
        ),
        bytes(
            (
                25,
                215,
                200,
                24,
                126,
                1,
                196,
                42,
                167,
                142,
                96,
                49,
                7,
                40,
                14,
                66,
                215,
                203,
                171,
                73,
                220,
                32,
                175,
                47,
                154,
                71,
                106,
                176,
                222,
                72,
                217,
                201,
            )
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        461,
        bytes(
            (
                212,
                142,
                203,
                179,
                155,
                63,
                55,
                131,
                171,
                4,
                25,
                42,
                139,
                165,
                234,
                206,
                22,
                20,
                245,
                216,
                56,
                3,
                199,
                124,
                36,
                185,
                17,
                220,
                31,
                108,
                123,
                196,
            )
        ),
        bytes(
            (
                1,
                231,
                208,
                23,
                92,
                143,
                228,
                233,
                144,
                139,
                190,
                209,
                158,
                196,
                34,
                16,
                9,
                64,
                31,
                236,
                2,
                233,
                206,
                236,
                35,
                214,
                143,
                207,
                65,
                2,
                8,
                250,
            )
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        461,
        bytes(
            (
                212,
                142,
                203,
                179,
                155,
                63,
                55,
                131,
                171,
                4,
                25,
                42,
                139,
                165,
                234,
                206,
                22,
                20,
                245,
                216,
                56,
                3,
                199,
                124,
                36,
                185,
                17,
                220,
                31,
                108,
                123,
                196,
            )
        ),
        bytes(
            (
                1,
                231,
                208,
                23,
                92,
                143,
                228,
                233,
                144,
                139,
                190,
                209,
                158,
                196,
                34,
                16,
                9,
                64,
                31,
                236,
                2,
                233,
                206,
                236,
                35,
                214,
                143,
                207,
                65,
                2,
                8,
                250,
            )
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        469,
        bytes(
            (
                54,
                20,
                10,
                69,
                207,
                208,
                44,
                252,
                53,
                214,
                162,
                42,
                185,
                25,
                229,
                190,
                83,
                80,
                208,
                63,
                148,
                225,
                29,
                244,
                71,
                116,
                8,
                96,
                206,
                118,
                47,
                147,
            )
        ),
        bytes(
            (
                81,
                231,
                62,
                67,
                153,
                250,
                63,
                3,
                174,
                201,
                55,
                231,
                247,
                144,
                114,
                171,
                251,
                20,
                60,
                217,
                41,
                181,
                168,
                232,
                78,
                207,
                28,
                244,
                173,
                219,
                55,
                225,
            )
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        469,
        bytes(
            (
                54,
                20,
                10,
                69,
                207,
                208,
                44,
                252,
                53,
                214,
                162,
                42,
                185,
                25,
                229,
                190,
                83,
                80,
                208,
                63,
                148,
                225,
                29,
                244,
                71,
                116,
                8,
                96,
                206,
                118,
                47,
                147,
            )
        ),
        bytes(
            (
                81,
                231,
                62,
                67,
                153,
                250,
                63,
                3,
                174,
                201,
                55,
                231,
                247,
                144,
                114,
                171,
                251,
                20,
                60,
                217,
                41,
                181,
                168,
                232,
                78,
                207,
                28,
                244,
                173,
                219,
                55,
                225,
            )
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        481,
        bytes(
            (
                181,
                232,
                238,
                145,
                128,
                221,
                127,
                250,
                182,
                136,
                236,
                216,
                72,
                119,
                41,
                35,
                70,
                175,
                249,
                13,
                65,
                51,
                84,
                127,
                48,
                43,
                98,
                76,
                235,
                100,
                88,
                108,
            )
        ),
        bytes(
            (
                175,
                200,
                159,
                74,
                237,
                80,
                178,
                84,
                142,
                100,
                237,
                186,
                245,
                145,
                236,
                23,
                155,
                42,
                221,
                181,
                144,
                113,
                224,
                31,
                43,
                99,
                49,
                235,
                48,
                207,
                157,
                134,
            )
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        481,
        bytes(
            (
                181,
                232,
                238,
                145,
                128,
                221,
                127,
                250,
                182,
                136,
                236,
                216,
                72,
                119,
                41,
                35,
                70,
                175,
                249,
                13,
                65,
                51,
                84,
                127,
                48,
                43,
                98,
                76,
                235,
                100,
                88,
                108,
            )
        ),
        bytes(
            (
                175,
                200,
                159,
                74,
                237,
                80,
                178,
                84,
                142,
                100,
                237,
                186,
                245,
                145,
                236,
                23,
                155,
                42,
                221,
                181,
                144,
                113,
                224,
                31,
                43,
                99,
                49,
                235,
                48,
                207,
                157,
                134,
            )
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        485,
        bytes(
            (
                251,
                18,
                69,
                158,
                167,
                139,
                180,
                88,
                152,
                144,
                2,
                157,
                245,
                137,
                138,
                80,
                95,
                152,
                3,
                199,
                160,
                62,
                93,
                128,
                144,
                93,
                51,
                50,
                208,
                172,
                85,
                43,
            )
        ),
        bytes(
            (
                31,
                45,
                87,
                91,
                8,
                54,
                249,
                95,
                16,
                211,
                149,
                74,
                2,
                153,
                15,
                13,
                53,
                69,
                219,
                163,
                47,
                246,
                184,
                109,
                159,
                52,
                7,
                169,
                140,
                102,
                227,
                250,
            )
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        485,
        bytes(
            (
                251,
                18,
                69,
                158,
                167,
                139,
                180,
                88,
                152,
                144,
                2,
                157,
                245,
                137,
                138,
                80,
                95,
                152,
                3,
                199,
                160,
                62,
                93,
                128,
                144,
                93,
                51,
                50,
                208,
                172,
                85,
                43,
            )
        ),
        bytes(
            (
                31,
                45,
                87,
                91,
                8,
                54,
                249,
                95,
                16,
                211,
                149,
                74,
                2,
                153,
                15,
                13,
                53,
                69,
                219,
                163,
                47,
                246,
                184,
                109,
                159,
                52,
                7,
                169,
                140,
                102,
                227,
                250,
            )
        ),
    ),
    (
        "scripts/kind/aud373_internal_mtls_proof.sh",
        246,
        bytes(
            (
                32,
                152,
                216,
                158,
                65,
                208,
                136,
                98,
                208,
                16,
                155,
                123,
                112,
                72,
                61,
                45,
                53,
                182,
                189,
                17,
                66,
                99,
                47,
                154,
                172,
                182,
                82,
                144,
                240,
                225,
                202,
                232,
            )
        ),
        bytes(
            (
                90,
                208,
                222,
                86,
                194,
                99,
                30,
                137,
                217,
                84,
                23,
                119,
                11,
                159,
                174,
                155,
                157,
                93,
                192,
                45,
                37,
                150,
                94,
                104,
                178,
                164,
                56,
                167,
                26,
                131,
                66,
                1,
            )
        ),
    ),
    (
        "scripts/kind/aud373_internal_mtls_proof.sh",
        248,
        bytes(
            (
                203,
                110,
                165,
                203,
                116,
                137,
                2,
                174,
                62,
                26,
                75,
                15,
                179,
                181,
                77,
                64,
                182,
                220,
                77,
                175,
                207,
                216,
                90,
                5,
                136,
                123,
                32,
                97,
                230,
                135,
                29,
                89,
            )
        ),
        bytes(
            (
                113,
                130,
                105,
                92,
                121,
                216,
                169,
                25,
                235,
                116,
                177,
                19,
                228,
                21,
                179,
                54,
                94,
                73,
                178,
                243,
                185,
                22,
                222,
                95,
                189,
                128,
                176,
                163,
                147,
                101,
                25,
                66,
            )
        ),
    ),
    (
        "scripts/kind/aud373_internal_mtls_proof.sh",
        349,
        bytes(
            (
                247,
                46,
                161,
                63,
                225,
                39,
                194,
                134,
                60,
                209,
                210,
                221,
                120,
                158,
                234,
                171,
                231,
                171,
                98,
                47,
                205,
                55,
                224,
                197,
                14,
                228,
                18,
                137,
                114,
                221,
                224,
                38,
            )
        ),
        bytes(
            (
                207,
                176,
                158,
                194,
                253,
                157,
                191,
                79,
                80,
                194,
                136,
                14,
                241,
                149,
                196,
                148,
                181,
                232,
                241,
                248,
                85,
                79,
                44,
                107,
                205,
                9,
                57,
                179,
                19,
                96,
                119,
                162,
            )
        ),
    ),
    (
        "scripts/kind/aud373_internal_mtls_proof.sh",
        369,
        bytes(
            (
                27,
                29,
                44,
                252,
                35,
                100,
                112,
                237,
                33,
                80,
                1,
                88,
                30,
                103,
                200,
                15,
                43,
                72,
                53,
                247,
                246,
                137,
                57,
                149,
                247,
                72,
                34,
                18,
                248,
                22,
                245,
                144,
            )
        ),
        bytes(
            (
                220,
                30,
                228,
                248,
                209,
                219,
                79,
                122,
                102,
                114,
                75,
                52,
                31,
                202,
                189,
                51,
                209,
                200,
                9,
                213,
                209,
                48,
                166,
                111,
                47,
                123,
                231,
                115,
                246,
                11,
                212,
                9,
            )
        ),
    ),
    (
        "scripts/quality/helm_rendered_target_overlay.py",
        37,
        bytes(
            (
                8,
                107,
                203,
                16,
                175,
                231,
                48,
                49,
                200,
                41,
                129,
                43,
                197,
                0,
                154,
                219,
                25,
                249,
                11,
                168,
                176,
                9,
                253,
                128,
                209,
                189,
                127,
                140,
                199,
                141,
                186,
                226,
            )
        ),
        bytes(
            (
                26,
                5,
                99,
                160,
                29,
                38,
                152,
                144,
                186,
                73,
                121,
                3,
                222,
                102,
                7,
                215,
                162,
                235,
                158,
                49,
                129,
                190,
                195,
                33,
                77,
                34,
                3,
                178,
                234,
                128,
                182,
                166,
            )
        ),
    ),
    (
        "tests/integration/test_aud433_notifications_baseline_partition.py",
        32,
        bytes(
            (
                115,
                121,
                15,
                241,
                107,
                64,
                244,
                86,
                155,
                72,
                211,
                4,
                171,
                159,
                37,
                173,
                5,
                238,
                4,
                13,
                53,
                254,
                183,
                77,
                61,
                255,
                139,
                19,
                67,
                229,
                75,
                240,
            )
        ),
        bytes(
            (
                60,
                116,
                93,
                99,
                24,
                175,
                183,
                156,
                123,
                26,
                193,
                88,
                193,
                237,
                202,
                244,
                80,
                247,
                52,
                41,
                86,
                61,
                108,
                22,
                15,
                75,
                176,
                38,
                199,
                163,
                94,
                247,
            )
        ),
    ),
    (
        "tests/integration/test_aud433_notifications_baseline_partition.py",
        35,
        bytes(
            (
                243,
                103,
                141,
                119,
                143,
                17,
                117,
                202,
                158,
                18,
                109,
                91,
                146,
                54,
                44,
                204,
                249,
                103,
                103,
                234,
                26,
                87,
                55,
                239,
                114,
                147,
                35,
                10,
                210,
                173,
                46,
                71,
            )
        ),
        bytes(
            (
                221,
                90,
                42,
                234,
                194,
                52,
                105,
                35,
                146,
                131,
                149,
                135,
                80,
                160,
                179,
                183,
                155,
                213,
                210,
                247,
                178,
                87,
                171,
                153,
                127,
                47,
                203,
                138,
                245,
                149,
                151,
                237,
            )
        ),
    ),
    (
        "tests/integration/test_aud433_notifications_baseline_partition.py",
        38,
        bytes(
            (
                206,
                117,
                230,
                210,
                74,
                140,
                120,
                65,
                253,
                226,
                111,
                154,
                36,
                32,
                60,
                211,
                45,
                104,
                96,
                172,
                56,
                128,
                244,
                144,
                167,
                246,
                250,
                154,
                127,
                19,
                251,
                124,
            )
        ),
        bytes(
            (
                48,
                68,
                110,
                98,
                216,
                101,
                19,
                101,
                78,
                7,
                38,
                97,
                210,
                208,
                159,
                209,
                27,
                248,
                204,
                16,
                214,
                210,
                102,
                229,
                68,
                15,
                237,
                13,
                142,
                58,
                5,
                17,
            )
        ),
    ),
    (
        "tests/integration/test_aud433_notifications_baseline_partition.py",
        58,
        bytes(
            (
                82,
                237,
                53,
                6,
                40,
                243,
                139,
                52,
                177,
                178,
                51,
                28,
                111,
                115,
                229,
                53,
                33,
                255,
                94,
                178,
                248,
                41,
                126,
                177,
                173,
                197,
                70,
                79,
                145,
                134,
                148,
                132,
            )
        ),
        bytes(
            (
                143,
                83,
                203,
                241,
                247,
                181,
                53,
                169,
                115,
                150,
                191,
                29,
                255,
                223,
                147,
                248,
                92,
                142,
                106,
                37,
                80,
                240,
                52,
                49,
                44,
                139,
                36,
                99,
                90,
                167,
                171,
                120,
            )
        ),
    ),
    (
        "tests/integration/test_aud433_notifications_baseline_partition.py",
        59,
        bytes(
            (
                33,
                134,
                67,
                215,
                48,
                59,
                183,
                167,
                19,
                238,
                172,
                32,
                56,
                229,
                40,
                125,
                245,
                105,
                131,
                187,
                153,
                119,
                45,
                75,
                223,
                213,
                124,
                20,
                26,
                99,
                86,
                123,
            )
        ),
        bytes(
            (
                219,
                246,
                222,
                170,
                119,
                71,
                153,
                149,
                220,
                155,
                138,
                133,
                112,
                16,
                55,
                213,
                81,
                118,
                234,
                242,
                158,
                23,
                222,
                218,
                236,
                27,
                221,
                33,
                208,
                145,
                128,
                251,
            )
        ),
    ),
    (
        "tests/integration/test_aud433_notifications_baseline_partition.py",
        61,
        bytes(
            (
                169,
                12,
                46,
                206,
                20,
                150,
                53,
                20,
                27,
                145,
                162,
                101,
                210,
                76,
                39,
                246,
                114,
                28,
                24,
                247,
                26,
                58,
                222,
                168,
                198,
                204,
                50,
                35,
                60,
                66,
                228,
                216,
            )
        ),
        bytes(
            (
                47,
                215,
                165,
                133,
                62,
                222,
                234,
                133,
                188,
                91,
                150,
                41,
                213,
                140,
                240,
                149,
                38,
                91,
                117,
                125,
                111,
                192,
                120,
                82,
                109,
                217,
                14,
                145,
                95,
                224,
                105,
                117,
            )
        ),
    ),
    (
        "tests/integration/test_aud433_notifications_baseline_partition.py",
        62,
        bytes(
            (
                194,
                220,
                254,
                104,
                232,
                8,
                127,
                197,
                64,
                43,
                204,
                47,
                21,
                3,
                16,
                40,
                188,
                175,
                186,
                191,
                46,
                63,
                52,
                240,
                77,
                38,
                103,
                147,
                230,
                122,
                101,
                142,
            )
        ),
        bytes(
            (
                244,
                2,
                219,
                222,
                27,
                25,
                179,
                212,
                244,
                247,
                232,
                36,
                102,
                102,
                170,
                120,
                102,
                53,
                199,
                29,
                40,
                222,
                82,
                78,
                208,
                155,
                55,
                28,
                144,
                211,
                128,
                79,
            )
        ),
    ),
    (
        "tests/test_helm_rendered_target_overlay.py",
        96,
        bytes(
            (
                8,
                107,
                203,
                16,
                175,
                231,
                48,
                49,
                200,
                41,
                129,
                43,
                197,
                0,
                154,
                219,
                25,
                249,
                11,
                168,
                176,
                9,
                253,
                128,
                209,
                189,
                127,
                140,
                199,
                141,
                186,
                226,
            )
        ),
        bytes(
            (
                249,
                104,
                35,
                122,
                71,
                176,
                239,
                131,
                206,
                252,
                29,
                211,
                192,
                8,
                223,
                43,
                15,
                86,
                61,
                141,
                161,
                95,
                192,
                173,
                226,
                184,
                183,
                189,
                127,
                249,
                104,
                177,
            )
        ),
    ),
    (
        "tests/test_internal_mtls_kind_contract.py",
        1352,
        bytes(
            (
                37,
                91,
                244,
                236,
                15,
                129,
                103,
                138,
                67,
                22,
                233,
                89,
                250,
                241,
                223,
                39,
                224,
                96,
                135,
                242,
                108,
                238,
                56,
                241,
                119,
                75,
                8,
                123,
                100,
                116,
                23,
                88,
            )
        ),
        bytes(
            (
                125,
                211,
                99,
                95,
                123,
                99,
                76,
                86,
                205,
                149,
                191,
                160,
                179,
                85,
                65,
                233,
                11,
                191,
                228,
                118,
                75,
                236,
                52,
                75,
                110,
                180,
                238,
                2,
                50,
                167,
                118,
                43,
            )
        ),
    ),
    (
        "tests/test_internal_mtls_kind_contract.py",
        1353,
        bytes(
            (
                66,
                250,
                15,
                196,
                76,
                193,
                65,
                47,
                49,
                180,
                76,
                16,
                59,
                67,
                191,
                248,
                18,
                38,
                56,
                178,
                86,
                54,
                54,
                133,
                160,
                153,
                112,
                57,
                136,
                178,
                62,
                210,
            )
        ),
        bytes(
            (
                3,
                204,
                115,
                50,
                140,
                110,
                133,
                26,
                163,
                96,
                190,
                17,
                48,
                191,
                106,
                150,
                196,
                11,
                172,
                157,
                163,
                178,
                93,
                109,
                135,
                39,
                121,
                42,
                202,
                132,
                16,
                48,
            )
        ),
    ),
    (
        "tests/test_internal_mtls_kind_contract.py",
        1931,
        bytes(
            (
                199,
                202,
                28,
                193,
                232,
                55,
                59,
                111,
                161,
                66,
                105,
                75,
                100,
                235,
                184,
                120,
                238,
                27,
                130,
                71,
                157,
                44,
                41,
                237,
                182,
                215,
                95,
                0,
                187,
                195,
                30,
                189,
            )
        ),
        bytes(
            (
                177,
                154,
                5,
                144,
                28,
                17,
                9,
                225,
                228,
                46,
                250,
                177,
                109,
                240,
                255,
                120,
                240,
                28,
                183,
                150,
                127,
                122,
                215,
                39,
                212,
                142,
                14,
                184,
                228,
                104,
                203,
                56,
            )
        ),
    ),
    (
        "tests/test_internal_mtls_kind_contract.py",
        1936,
        bytes(
            (
                233,
                181,
                145,
                187,
                78,
                144,
                187,
                93,
                3,
                100,
                193,
                175,
                86,
                203,
                184,
                23,
                211,
                174,
                146,
                157,
                6,
                112,
                68,
                119,
                233,
                10,
                106,
                173,
                45,
                243,
                139,
                120,
            )
        ),
        bytes(
            (
                6,
                182,
                255,
                141,
                167,
                253,
                52,
                224,
                51,
                127,
                2,
                213,
                25,
                102,
                119,
                63,
                219,
                44,
                6,
                250,
                90,
                160,
                105,
                234,
                25,
                238,
                142,
                132,
                126,
                162,
                20,
                120,
            )
        ),
    ),
    (
        "tests/test_internal_mtls_kind_contract.py",
        1937,
        bytes(
            (
                235,
                136,
                244,
                84,
                8,
                189,
                43,
                29,
                89,
                172,
                228,
                20,
                15,
                179,
                25,
                136,
                133,
                120,
                145,
                191,
                249,
                160,
                27,
                203,
                152,
                241,
                108,
                158,
                148,
                237,
                91,
                37,
            )
        ),
        bytes(
            (
                125,
                201,
                228,
                147,
                47,
                217,
                50,
                182,
                50,
                236,
                142,
                64,
                241,
                202,
                144,
                33,
                145,
                47,
                60,
                55,
                76,
                232,
                33,
                117,
                104,
                20,
                200,
                66,
                223,
                29,
                96,
                211,
            )
        ),
    ),
    (
        "tests/test_internal_mtls_kind_contract.py",
        1945,
        bytes(
            (
                181,
                140,
                242,
                109,
                103,
                195,
                123,
                74,
                171,
                175,
                226,
                232,
                103,
                202,
                28,
                37,
                36,
                183,
                28,
                126,
                229,
                132,
                105,
                126,
                154,
                191,
                150,
                112,
                237,
                226,
                188,
                93,
            )
        ),
        bytes(
            (
                94,
                70,
                245,
                236,
                74,
                204,
                188,
                33,
                34,
                183,
                97,
                96,
                45,
                186,
                149,
                236,
                169,
                135,
                217,
                54,
                211,
                190,
                195,
                250,
                219,
                177,
                244,
                67,
                240,
                101,
                99,
                239,
            )
        ),
    ),
    (
        "tests/test_internal_mtls_kind_contract.py",
        1949,
        bytes(
            (
                84,
                118,
                99,
                181,
                181,
                51,
                132,
                105,
                251,
                155,
                22,
                243,
                3,
                92,
                173,
                108,
                55,
                75,
                43,
                176,
                16,
                86,
                57,
                208,
                160,
                37,
                126,
                235,
                210,
                152,
                178,
                108,
            )
        ),
        bytes(
            (
                141,
                57,
                199,
                224,
                111,
                211,
                165,
                33,
                251,
                153,
                69,
                248,
                128,
                74,
                42,
                47,
                175,
                184,
                203,
                178,
                92,
                217,
                207,
                184,
                11,
                113,
                187,
                35,
                135,
                5,
                63,
                88,
            )
        ),
    ),
    (
        "tests/test_internal_mtls_kind_contract.py",
        1953,
        bytes(
            (
                199,
                193,
                177,
                55,
                88,
                84,
                44,
                211,
                51,
                240,
                96,
                98,
                156,
                181,
                149,
                104,
                204,
                184,
                65,
                131,
                10,
                139,
                137,
                243,
                9,
                14,
                17,
                214,
                56,
                203,
                117,
                97,
            )
        ),
        bytes(
            (
                184,
                220,
                70,
                245,
                214,
                0,
                116,
                49,
                252,
                20,
                146,
                168,
                153,
                183,
                168,
                175,
                208,
                165,
                92,
                186,
                152,
                28,
                52,
                181,
                232,
                142,
                31,
                69,
                31,
                227,
                101,
                145,
            )
        ),
    ),
    (
        "tests/test_internal_mtls_kind_contract.py",
        1981,
        bytes(
            (
                1,
                241,
                113,
                4,
                208,
                13,
                30,
                0,
                203,
                243,
                74,
                47,
                48,
                159,
                96,
                111,
                23,
                164,
                79,
                225,
                222,
                219,
                78,
                112,
                234,
                241,
                79,
                60,
                167,
                84,
                142,
                118,
            )
        ),
        bytes(
            (
                244,
                1,
                160,
                252,
                202,
                43,
                84,
                11,
                207,
                177,
                121,
                2,
                131,
                248,
                30,
                250,
                93,
                25,
                163,
                238,
                212,
                232,
                30,
                125,
                132,
                191,
                13,
                33,
                50,
                243,
                72,
                41,
            )
        ),
    ),
)


def _aud380_identity_key(record: dict[str, Any]) -> tuple[str, str, tuple[int, ...]]:
    identity = record["identity"]
    return (
        identity["path"],
        identity["type"],
        tuple(identity["hashed_secret_bytes"]),
    )


def _aud380_canonical_records_digest(records: list[dict[str, Any]]) -> bytes:
    ordered = sorted(records, key=_aud380_identity_key)
    canonical = json.dumps(
        ordered,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).digest()


def _aud380_ordered_records_digest(records: list[dict[str, Any]]) -> bytes:
    canonical = json.dumps(
        records,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).digest()


def _assert_conditional_owner_projection(
    policy: dict[str, Any],
    *,
    expected_base_records: list[dict[str, Any]],
    expected_new_addition_identities: frozenset[tuple[str, str, tuple[int, ...]]],
    expected_pending_new_addition_sha256: bytes,
    expected_new_addition_sha256: bytes,
    expected_full_recordset_sha256: bytes,
    expected_category_counts: dict[str, int],
) -> None:
    """Bind a private conditional 469+N view without activating pending rows."""
    historical = _reviewed_pre_retirement_dispositions()
    expected_header = {
        key: value for key, value in historical.items() if key != "records"
    }
    actual_header = {key: value for key, value in policy.items() if key != "records"}
    assert actual_header == expected_header, "conditional disposition header changed"

    assert len(expected_base_records) == 363
    records = policy.get("records")
    assert isinstance(records, list), "conditional disposition records changed"
    assert records[:363] == expected_base_records, (
        "conditional disposition prefix changed"
    )
    all_identity_keys = [_aud380_identity_key(record) for record in records]
    assert len(all_identity_keys) == len(set(all_identity_keys)), (
        "conditional disposition identities duplicated"
    )

    appended_records = records[363:]
    assert expected_new_addition_identities
    assert len(_AUD380_APPROVED_OWNER_ADDITIONS_SHA256) == 32
    assert len(expected_pending_new_addition_sha256) == 32
    assert len(expected_new_addition_sha256) == 32
    assert len(expected_full_recordset_sha256) == 32
    base_identity_keys = {
        _aud380_identity_key(record) for record in expected_base_records
    }
    new_identity_set = set(expected_new_addition_identities)
    assert not base_identity_keys.intersection(new_identity_set)
    historical_identity_keys = {
        _aud380_identity_key(record) for record in historical["records"]
    }
    assert not historical_identity_keys.intersection(new_identity_set)
    assert len(appended_records) == 106 + len(expected_new_addition_identities), (
        "conditional disposition additions changed"
    )
    actual_new_additions = [
        record
        for record in appended_records
        if _aud380_identity_key(record) in new_identity_set
    ]
    original_approved_additions = [
        record
        for record in appended_records
        if _aud380_identity_key(record) not in new_identity_set
    ]
    assert {
        _aud380_identity_key(record) for record in actual_new_additions
    } == new_identity_set, "conditional disposition additions changed"
    assert len(original_approved_additions) == 106, (
        "conditional disposition original additions changed"
    )
    assert _aud380_canonical_records_digest(original_approved_additions) == (
        _AUD380_APPROVED_OWNER_ADDITIONS_SHA256
    ), "conditional disposition original additions changed"
    assert _aud380_canonical_records_digest(actual_new_additions) == (
        expected_new_addition_sha256
    ), "conditional disposition new additions changed"
    pending_projection = copy.deepcopy(actual_new_additions)
    for record in pending_projection:
        record["approval_status"] = "NOT_APPROVED"
    assert _aud380_canonical_records_digest(pending_projection) == (
        expected_pending_new_addition_sha256
    ), "conditional disposition pending owner records changed"
    assert len(records) == 469 + len(expected_new_addition_identities), (
        "conditional disposition total changed"
    )
    assert sum(expected_category_counts.values()) == len(records)
    assert Counter(record["category"] for record in records) == Counter(
        expected_category_counts
    ), "conditional disposition categories changed"
    assert _aud380_ordered_records_digest(records) == expected_full_recordset_sha256, (
        "conditional disposition full recordset changed"
    )


def _assert_conditional_owner_source_bindings(
    repository_root: Path,
    *,
    source_sha256: dict[str, bytes] | None = None,
    identity_source_lines: tuple[tuple[str, str, tuple[int, ...], str, int], ...]
    | None = None,
    companion_source_lines: tuple[tuple[str, int], ...] | None = None,
    source_line_hashes: tuple[tuple[str, int, bytes, bytes], ...] | None = None,
    replaced_identity_source_lines: tuple[
        tuple[str, str, tuple[int, ...], str, int], ...
    ]
    | None = None,
    replaced_companion_targets: tuple[tuple[str, int, str], ...] | None = None,
    companion_source_targets: tuple[tuple[str, int, str], ...] | None = None,
) -> None:
    """Check exact current pins and the six finite prior N21 source replacements."""
    source_sha256 = (
        _AUD380_CURRENT_DELTA_SOURCE_SHA256 if source_sha256 is None else source_sha256
    )
    identity_source_lines = (
        _AUD380_CURRENT_DELTA_IDENTITY_SOURCE_LINES
        if identity_source_lines is None
        else identity_source_lines
    )
    companion_source_lines = (
        _AUD380_CURRENT_DELTA_COMPANION_SOURCE_LINES
        if companion_source_lines is None
        else companion_source_lines
    )
    source_line_hashes = (
        _AUD380_CURRENT_DELTA_SOURCE_LINE_HASHES
        if source_line_hashes is None
        else source_line_hashes
    )
    replaced_identity_source_lines = (
        _AUD380_N21_REPLACED_IDENTITY_SOURCE_LINES
        if replaced_identity_source_lines is None
        else replaced_identity_source_lines
    )
    replaced_companion_targets = (
        _AUD380_N21_REPLACED_COMPANION_TARGETS
        if replaced_companion_targets is None
        else replaced_companion_targets
    )
    companion_source_targets = (
        _AUD380_CI58_COMPANION_SOURCE_TARGETS
        if companion_source_targets is None
        else companion_source_targets
    )
    assert source_sha256 == _AUD380_CURRENT_DELTA_SOURCE_SHA256, (
        "conditional disposition source hash bindings changed"
    )
    assert identity_source_lines == _AUD380_CURRENT_DELTA_IDENTITY_SOURCE_LINES, (
        "conditional disposition identity line bindings changed"
    )
    assert companion_source_lines == _AUD380_CURRENT_DELTA_COMPANION_SOURCE_LINES, (
        "conditional disposition companion line bindings changed"
    )
    assert source_line_hashes == _AUD380_CURRENT_DELTA_SOURCE_LINE_HASHES, (
        "conditional disposition source line hash bindings changed"
    )
    assert (
        replaced_identity_source_lines == _AUD380_N21_REPLACED_IDENTITY_SOURCE_LINES
    ), "historical N21 replacement identity bindings changed"
    assert replaced_companion_targets == _AUD380_N21_REPLACED_COMPANION_TARGETS, (
        "historical N21 replacement companion bindings changed"
    )
    assert companion_source_targets == _AUD380_CI58_COMPANION_SOURCE_TARGETS, (
        "CI58 companion source bindings changed"
    )
    assert (
        len(identity_source_lines) == 21
    )  # 15 N21 survivors, three N4, N5 and two N6.
    assert len(replaced_identity_source_lines) == 6
    assert len(_AUD380_N21_UNCHANGED_IDENTITY_SOURCE_LINES) == 15
    assert len(source_line_hashes) == (
        len(identity_source_lines) + len(companion_source_lines)
    )
    assert len(source_sha256) == 55
    assert all(len(digest) == 32 for digest in source_sha256.values())
    expected_source_paths = {path for path, *_rest in identity_source_lines} | {
        path for path, _line_number in companion_source_lines
    }
    assert expected_source_paths <= set(source_sha256), (
        "source SHA bindings do not cover every identity and companion line path"
    )
    expected_line_references = Counter(
        (path, line_number)
        for path, _finding_type, _digest, _category, line_number in identity_source_lines
    ) + Counter(companion_source_lines)
    assert (
        Counter(
            (path, line_number)
            for path, line_number, _line, _context in source_line_hashes
        )
        == expected_line_references
    ), "source line hashes do not cover the exact identity and companion line set"

    historical_identity_keys = {
        (path, finding_type, digest)
        for path, finding_type, digest, _category, _line in _AUD380_N21_HISTORICAL_IDENTITY_SOURCE_LINES
    }
    n21_identity_keys = set(_AUD380_PENDING_OWNER_IDENTITIES)
    historical_identity_keys = {
        (
            path,
            finding_type,
            tuple(_NATS_ROW11_IDENTITY_REBINDS.get(bytes(digest), bytes(digest))),
        )
        if path == "quality/semgrep-dispositions.json"
        else (path, finding_type, digest)
        for path, finding_type, digest in historical_identity_keys
    }
    assert historical_identity_keys == n21_identity_keys
    replaced_locations = set(_AUD380_N21_REPLACED_COMPANION_LOCATIONS)
    replaced_keys = {
        (path, finding_type, digest)
        for path, finding_type, digest, _category, line_number in replaced_identity_source_lines
    }
    assert {
        (path, line_number)
        for path, _finding_type, _digest, _category, line_number in replaced_identity_source_lines
    } == replaced_locations
    assert len(replaced_keys) == 6
    unchanged_n21_keys = historical_identity_keys - replaced_keys
    assert len(unchanged_n21_keys) == 15
    current_identity_keys = {
        (path, finding_type, digest)
        for path, finding_type, digest, _category, _line in identity_source_lines
    }
    current_n4_keys = set(_AUD380_N4_PENDING_OWNER_IDENTITIES) - {
        _AUD380_N4_PUBLIC_LEDGER_IDENTITY
    }
    assert current_identity_keys == (
        unchanged_n21_keys
        | current_n4_keys
        | set(_AUD380_N5_PENDING_OWNER_IDENTITIES)
        | set(_AUD380_N6_EXPECTED_IDENTITIES)
    ), "current source identities differ from exact N21 survivors plus current N4/N5/N6"
    assert not (current_identity_keys & replaced_keys), (
        "replaced historical N21 identity is still claimed as current"
    )

    source_lines: dict[str, list[bytes]] = {}
    source_bytes_by_path: dict[str, bytes] = {}
    for relative_path, expected_digest in source_sha256.items():
        source_bytes = _aud154_historical_source_bytes(
            relative_path, (repository_root / relative_path).read_bytes()
        )
        assert hashlib.sha256(source_bytes).digest() == expected_digest, (
            f"conditional disposition source file SHA-256 changed: {relative_path}"
        )
        source_lines[relative_path] = source_bytes.splitlines()
        source_bytes_by_path[relative_path] = source_bytes

    pending_by_identity = {
        _aud380_identity_key(record): record
        for record in [
            *_AUD380_PENDING_OWNER_RECORDS,
            *_AUD380_N4_PENDING_OWNER_RECORDS,
            *_AUD380_N5_PENDING_OWNER_RECORDS,
            *_AUD380_N6_PENDING_OWNER_RECORDS,
        ]
    }
    assert set(pending_by_identity) == (
        n21_identity_keys
        | set(_AUD380_N4_PENDING_OWNER_IDENTITIES)
        | set(_AUD380_N5_PENDING_OWNER_IDENTITIES)
        | set(_AUD380_N6_EXPECTED_IDENTITIES)
    )
    for row in _AUD380_PENDING_OWNER_RECORDS:
        assert row["approval_status"] == "NOT_APPROVED"
        active_row = copy.deepcopy(row)
        active_row["approval_status"] = "approved"
        assert any(
            _aud380_identity_key(candidate) == _aud380_identity_key(row)
            and candidate == active_row
            for candidate in _aud380_conditional_policy()["records"]
        ), "approved N21 metadata changed in the active 490 prefix"

    identity_line_keys = {
        (path, finding_type, digest)
        for path, finding_type, digest, _category, _line in identity_source_lines
    }
    assert identity_line_keys == current_identity_keys
    for path, finding_type, digest, category, line_number in identity_source_lines:
        key = (path, finding_type, digest)
        assert pending_by_identity[key]["category"] == category
        assert 1 <= line_number <= len(source_lines[path]), (
            f"conditional disposition identity source line is absent: {path}:{line_number}"
        )
    for path, line_number in companion_source_lines:
        assert path in source_lines
        assert 1 <= line_number <= len(source_lines[path]), (
            f"conditional disposition companion source line is absent: {path}:{line_number}"
        )
    for path, line_number, line_sha256, context_sha256 in source_line_hashes:
        raw_lines = source_bytes_by_path[path].splitlines(keepends=True)
        assert 1 <= line_number <= len(raw_lines)
        line = raw_lines[line_number - 1]
        context = b"".join(
            raw_lines[max(0, line_number - 3) : min(len(raw_lines), line_number + 2)]
        )
        assert hashlib.sha256(line).digest() == line_sha256
        assert hashlib.sha256(context).digest() == context_sha256

    for path, line_number, target_path in companion_source_targets:
        assert path in source_bytes_by_path and target_path in source_bytes_by_path
        raw_line = source_bytes_by_path[path].splitlines(keepends=True)[line_number - 1]
        sha_fields = re.findall(rb'"sha256"\s*:\s*"([0-9a-f]{64})"', raw_line)
        assert len(sha_fields) == 1, (
            f"expected one companion SHA at {path}:{line_number}"
        )
        assert sha_fields[0] == source_sha256[target_path].hex().encode("ascii"), (
            f"companion SHA does not match pinned target: {path}:{line_number}"
        )

    old_records_by_key = {
        _aud380_identity_key(record): record for record in _AUD380_PENDING_OWNER_RECORDS
    }
    active_records_by_key = {
        _aud380_identity_key(record): record
        for record in _aud380_conditional_policy()["records"]
    }
    n4_records_by_key = {
        _aud380_identity_key(record): record
        for record in _AUD380_N4_PENDING_OWNER_RECORDS
    }
    n5_records_by_key = {
        _aud380_identity_key(record): record
        for record in _AUD380_N5_PENDING_OWNER_RECORDS
    }
    location_to_old_key = {
        (path, line_number): (path, finding_type, digest)
        for path, finding_type, digest, _category, line_number in replaced_identity_source_lines
    }
    for path, line_number, target_path in replaced_companion_targets:
        location = (path, line_number)
        assert location in replaced_locations
        assert target_path in source_bytes_by_path
        raw_line = source_bytes_by_path[path].splitlines(keepends=True)[line_number - 1]
        sha_fields = re.findall(rb'"sha256"\s*:\s*"([0-9a-f]{64})"', raw_line)
        assert len(sha_fields) == 1, (
            f"expected one current companion SHA at {path}:{line_number}"
        )
        current_sha = sha_fields[0]
        assert (
            current_sha.decode("ascii")
            == hashlib.sha256(source_bytes_by_path[target_path]).hexdigest()
        ), f"current companion target changed at {path}:{line_number}"
        current_digest = hashlib.sha1(current_sha, usedforsecurity=False).digest()
        current_key = (
            path,
            verifier._FALSE_POSITIVE_ALLOWED_TYPE,
            tuple(current_digest),
        )
        old_key = location_to_old_key[location]
        assert old_key in old_records_by_key
        assert current_key != old_key, (
            f"historical N21 identity is still current at {path}:{line_number}"
        )
        assert old_key not in current_identity_keys
        old_evidence = old_records_by_key[old_key]["evidence"]
        assert f"{path}:{line_number}" in old_evidence
        if line_number == 189:
            assert current_key in _AUD380_N6_EXPECTED_IDENTITIES
            assert current_key in {
                _aud380_identity_key(record)
                for record in _AUD380_N6_PENDING_OWNER_RECORDS
            }
            assert n4_records_by_key[_AUD380_N4_PUBLIC_LEDGER_IDENTITY]["category"] == (
                "public_integrity_digest"
            )
        elif line_number == 229:
            assert current_key in _AUD380_N6_EXPECTED_IDENTITIES
            assert current_key in {
                _aud380_identity_key(record)
                for record in _AUD380_N6_PENDING_OWNER_RECORDS
            }
        elif line_number == 485:
            assert current_key in n5_records_by_key, (
                f"current row15 package-lock value is not exact N5: {path}:{line_number}"
            )
            assert (
                n5_records_by_key[current_key]["category"] == "public_integrity_digest"
            )
        else:
            assert current_key in active_records_by_key, (
                f"current row15 value is not an exact active490 identity: {path}:{line_number}"
            )
            assert (
                active_records_by_key[current_key]["category"]
                == "public_integrity_digest"
            )
    _aud380_assert_n4_historical_row7_observation(source_bytes_by_path)


def _document(*findings: Finding) -> dict[str, Any]:
    results: dict[str, list[dict[str, Any]]] = {}
    for path, finding_type, digest, line_number in findings:
        results.setdefault(path, []).append(
            {
                "type": finding_type,
                "filename": path,
                _HASHED_FIELD: digest,
                "is_verified": False,
                "is_secret": False,
                "line_number": line_number,
            }
        )
    return {"version": "1.5.0", "results": results}


def _write(path: Path, document: Any) -> Path:
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _verify(
    tmp_path: Path,
    baseline: Any,
    current: Any,
    *,
    trusted_base: Any | None = None,
    trusted_base_name: str = "trusted-baseline.json",
) -> int:
    baseline_path = _write(tmp_path / "baseline.json", baseline)
    current_path = _write(tmp_path / "current.json", current)
    argv = [str(baseline_path), str(current_path)]
    if trusted_base is not None:
        trusted_path = _write(tmp_path / trusted_base_name, trusted_base)
        argv.extend(["--trusted-base-baseline", str(trusted_path)])
    return verifier.main(argv)


def _inline_pragma_marker() -> str:
    return "pragma:" + " allowlist" + " secret"


def _git_executable() -> str:
    executable = shutil.which("git")
    if executable is None:
        pytest.fail("Git executable is required for source-delta tests")
    return str(Path(executable).resolve(strict=True))


def _git_fixture(repository: Path, *arguments: str) -> str:
    git_executable = _git_executable()
    # The temporary repository and fixture command are test-controlled; no shell.
    result = subprocess.run(  # noqa: S603
        [git_executable, "-C", str(repository), *arguments],
        capture_output=True,
        check=False,
        encoding="utf-8",
        text=True,
        shell=False,
    )
    assert result.returncode == 0, "temporary Git fixture command failed"
    return result.stdout.strip()


def _commit_git_fixture(repository: Path, message: str) -> str:
    _git_fixture(repository, "add", "--all")
    git_executable = _git_executable()
    # The temporary repository and fixture command are test-controlled; no shell.
    result = subprocess.run(  # noqa: S603
        [
            git_executable,
            "-C",
            str(repository),
            "-c",
            "user.name=Policy Fixture",
            "-c",
            "user.email=policy-fixture@example.invalid",
            "-c",
            f"core.hooksPath={repository / '.disabled-hooks'}",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--quiet",
            "-m",
            message,
        ],
        capture_output=True,
        check=False,
        encoding="utf-8",
        text=True,
        shell=False,
    )
    assert result.returncode == 0, "temporary Git fixture commit failed"
    return _git_fixture(repository, "rev-parse", "HEAD")


def _new_git_fixture(tmp_path: Path) -> tuple[Path, str]:
    repository = tmp_path / "source repository"
    repository.mkdir()
    (repository / ".disabled-hooks").mkdir()
    empty_template = repository / ".empty-template"
    empty_template.mkdir()
    _git_fixture(
        repository,
        "init",
        "--quiet",
        f"--template={empty_template}",
    )
    _git_fixture(repository, "config", "core.quotePath", "true")
    (repository / "baseline.txt").write_text("baseline\n", encoding="utf-8")
    return repository, _commit_git_fixture(repository, "trusted base")


def _reviewed_disposition(
    *,
    path: str = "src/known.py",
    finding_type: str = "Hex High Entropy String",
    digest: str = "a" * 40,
    category: str = "documented_crypto_test_vector",
) -> dict[str, Any]:
    return {
        "identity": {
            "path": path,
            "type": finding_type,
            "hashed_secret_bytes": list(bytes.fromhex(digest)),
        },
        "category": category,
        "evidence": "Published test vector documented in docs/security/test-vectors.md",
        "owner": "Security Maintainers",
        "reviewed_on": "2026-10-12",
        "expires_on": "2027-01-10",
        "approval_status": "approved",
    }


def _disposition_document(*records: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": 1, "records": list(records)}


def _reviewed_exact_disposition(
    path: str,
    finding_type: str,
    digest_bytes: tuple[int, ...],
    category: str,
) -> dict[str, Any]:
    record = _reviewed_disposition(
        path=path,
        finding_type=finding_type,
        digest=bytes(digest_bytes).hex(),
        category=category,
    )
    if category == "external_kubernetes_secret_reference":
        record["evidence"] = (
            "Kubernetes external Secret object name or key reference; "
            "not credential material."
        )
    return record


def _commit_dispositions(repository: Path, records: list[dict[str, Any]]) -> str:
    policy_path = repository / "quality" / "security-false-positive-dispositions.json"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(
        json.dumps(_disposition_document(*records)), encoding="utf-8"
    )
    return _commit_git_fixture(repository, "add reviewed test dispositions")


def test_source_delta_rejects_added_marker_in_quoted_path(tmp_path: Path) -> None:
    repository, base_sha = _new_git_fixture(tmp_path)
    relative_path = Path("folder with spaces") / "marker-é-quoted.py"
    added_path = repository / relative_path
    added_path.parent.mkdir()
    added_path.write_text(
        f"value = 'synthetic'  # {_inline_pragma_marker()}\n", encoding="utf-8"
    )
    _commit_git_fixture(repository, "add marker")

    findings = verifier.find_new_inline_secret_pragmas(
        base_sha, repository_root=repository
    )

    assert findings == [(relative_path.as_posix(), 1)]


def test_source_delta_parses_forced_text_binary_hunk_with_unicode_separators(
    tmp_path: Path,
) -> None:
    repository, base_sha = _new_git_fixture(tmp_path)
    binary_path = repository / "opaque.bin"
    payload = ("prefix\u0085middle\u2028# " + _inline_pragma_marker() + "\n").encode(
        "utf-8"
    )
    binary_path.write_bytes(b"\x00" + payload)
    _commit_git_fixture(repository, "add forced-text binary marker")

    assert verifier.find_new_inline_secret_pragmas(
        base_sha, repository_root=repository
    ) == [("opaque.bin", 1)]


def test_source_delta_rejects_a_moved_legacy_marker(tmp_path: Path) -> None:
    repository, _ = _new_git_fixture(tmp_path)
    old_path = repository / "legacy.py"
    old_path.write_text(
        f"value = 'synthetic'  # {_inline_pragma_marker()}\n", encoding="utf-8"
    )
    base_sha = _commit_git_fixture(repository, "add legacy marker")
    moved_path = repository / "renamed folder" / "moved-é-marker.py"
    moved_path.parent.mkdir()
    old_path.rename(moved_path)
    _commit_git_fixture(repository, "move legacy marker")

    findings = verifier.find_new_inline_secret_pragmas(
        base_sha, repository_root=repository
    )

    assert findings == [("renamed folder/moved-é-marker.py", 1)]


def test_source_delta_allows_unchanged_and_removed_legacy_markers(
    tmp_path: Path,
) -> None:
    repository, _ = _new_git_fixture(tmp_path)
    legacy_path = repository / "legacy.py"
    legacy_path.write_text(
        f"value = 'synthetic'  # {_inline_pragma_marker()}\n", encoding="utf-8"
    )
    base_sha = _commit_git_fixture(repository, "add existing marker")

    (repository / "unrelated.py").write_text("value = 1\n", encoding="utf-8")
    _commit_git_fixture(repository, "change unrelated source")
    assert (
        verifier.find_new_inline_secret_pragmas(base_sha, repository_root=repository)
        == []
    )

    legacy_path.write_text("value = 'synthetic'\n", encoding="utf-8")
    _commit_git_fixture(repository, "remove existing marker")
    assert (
        verifier.find_new_inline_secret_pragmas(base_sha, repository_root=repository)
        == []
    )


def test_source_delta_fails_closed_when_git_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    monkeypatch.setattr(verifier.shutil, "which", lambda _name: None)

    with pytest.raises(
        verifier.SourceDeltaError, match="Git source comparison could not run"
    ):
        verifier.find_new_inline_secret_pragmas("1" * 40, repository_root=repository)


def test_source_delta_fails_closed_on_malformed_git_diff() -> None:
    malformed_diff = (
        "@@ malformed header\n+value = 'synthetic' # " + _inline_pragma_marker()
    )

    with pytest.raises(verifier.SourceDeltaError):
        verifier._find_added_inline_secret_pragmas(malformed_diff)


def test_source_delta_rejects_invalid_or_unavailable_base(
    tmp_path: Path,
) -> None:
    repository, _ = _new_git_fixture(tmp_path)
    for base_sha in ("0" * 40, "not-a-commit", "f" * 40):
        with pytest.raises(verifier.SourceDeltaError):
            verifier.find_new_inline_secret_pragmas(
                base_sha, repository_root=repository
            )


def test_source_delta_does_not_surface_git_error_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()

    def failed_git(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=args,
            returncode=128,
            stdout="",
            stderr="synthetic private diagnostic",
        )

    monkeypatch.setattr(verifier.subprocess, "run", failed_git)
    with pytest.raises(verifier.SourceDeltaError) as error:
        verifier.find_new_inline_secret_pragmas("1" * 40, repository_root=repository)

    assert "synthetic private diagnostic" not in str(error.value)


def test_source_delta_diagnostic_reports_count_without_untrusted_paths(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        verifier,
        "load_trusted_base_false_positive_dispositions",
        lambda *_args, **_kwargs: set(),
    )
    baseline_path = _write(tmp_path / "baseline.json", _document())
    current_path = _write(tmp_path / "current.json", _document())
    sensitive_path = "synthetic-private-secret-derived-path.py"
    monkeypatch.setattr(
        verifier,
        "find_new_inline_secret_pragmas",
        lambda *_args, **_kwargs: [(sensitive_path, 91)],
    )

    result = verifier.main(
        [
            str(baseline_path),
            str(current_path),
            "--trusted-base-source-sha",
            "1" * 40,
        ]
    )

    diagnostic = capsys.readouterr().err
    assert result == 1
    assert "1 inline secret-allowlist pragma line(s)" in diagnostic
    assert sensitive_path not in diagnostic
    assert ":91" not in diagnostic


def test_security_workflow_passes_source_base_for_supported_events() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    workflow = (
        repository_root / ".github" / "workflows" / "reusable-security-audit.yml"
    ).read_text(encoding="utf-8")

    assert "PR_BASE_SHA: ${{ github.event.pull_request.base.sha }}" in workflow
    assert "PUSH_BEFORE_SHA: ${{ github.event.before }}" in workflow
    assert workflow.count('--trusted-base-source-sha "$SOURCE_BASE_SHA"') == 2
    assert 'pull_request) SOURCE_BASE_SHA="$PR_BASE_SHA" ;;' in workflow
    assert 'push) SOURCE_BASE_SHA="$PUSH_BEFORE_SHA" ;;' in workflow
    assert "unsupported event for trusted source comparison" in workflow


def test_matching_findings_allow_stale_removals(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    finding = ("src/a.py", "Secret Keyword", "digest-a", 10)
    stale = ("docs/removed.md", "Secret Keyword", "digest-stale", 4)

    result = _verify(tmp_path, _document(finding, stale), _document(finding))

    assert result == 0
    output = capsys.readouterr().out
    assert "stale" in output.lower()
    assert "integrity check passed" in output


def test_new_finding_in_existing_file_is_rejected(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    existing = ("src/a.py", "Secret Keyword", "digest-a", 10)
    newly_detected = ("src/a.py", "Secret Keyword", "digest-b", 11)

    result = _verify(tmp_path, _document(existing), _document(existing, newly_detected))

    assert result == 1
    error = capsys.readouterr().err.lower()
    assert "new finding" in error
    assert "digest-b" not in error


def test_line_number_drift_does_not_create_a_new_finding(tmp_path: Path) -> None:
    baseline_finding = ("src/a.py", "Secret Keyword", "digest-a", 10)
    current_finding = ("src/a.py", "Secret Keyword", "digest-a", 27)

    assert (
        _verify(tmp_path, _document(baseline_finding), _document(current_finding)) == 0
    )


def test_trusted_base_rejects_new_baseline_suppression(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    existing = ("src/a.py", "Secret Keyword", "digest-a", 10)
    newly_suppressed = ("src/a.py", "Secret Keyword", "digest-b", 11)

    result = _verify(
        tmp_path,
        _document(existing, newly_suppressed),
        _document(existing, newly_suppressed),
        trusted_base=_document(existing),
    )

    assert result == 1
    error = capsys.readouterr().err
    assert "trusted base" in error.lower()
    assert "src/a.py:11" in error
    assert "Secret Keyword" in error
    assert "digest-b" not in error


def test_trusted_base_stale_addition_preserves_removal_semantics(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    existing = ("src/a.py", "Secret Keyword", "digest-a", 10)
    stale = ("docs/removed.md", "Secret Keyword", "digest-stale", 4)

    result = _verify(
        tmp_path,
        _document(existing, stale),
        _document(existing),
        trusted_base=_document(existing),
    )

    assert result == 0
    assert "stale" in capsys.readouterr().out.lower()


def test_empty_current_results_are_valid_and_mark_baseline_stale(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    finding = ("src/a.py", "Secret Keyword", "digest-a", 10)

    result = _verify(tmp_path, _document(finding), _document())

    assert result == 0
    assert "stale" in capsys.readouterr().out.lower()


def test_path_separators_are_compared_canonically(tmp_path: Path) -> None:
    baseline = _document(("src\\a.py", "Secret Keyword", "digest-a", 10))
    current = _document(("src/a.py", "Secret Keyword", "digest-a", 10))

    assert _verify(tmp_path, baseline, current) == 0


@pytest.mark.parametrize(
    "malformed",
    [
        [],
        {"results": []},
        {"results": {"src/a.py": {}}},
        {"results": {"src/a.py": [{"type": _FINDING_TYPE}]}},
        {"results": {"src/a.py": [{"type": _FINDING_TYPE, _HASHED_FIELD: "digest-a"}]}},
        {
            "results": {
                "../outside.txt": [
                    {
                        "type": _FINDING_TYPE,
                        _HASHED_FIELD: "digest-a",
                        "line_number": 1,
                    }
                ]
            }
        },
        {
            "results": {
                "/etc/passwd": [
                    {
                        "type": _FINDING_TYPE,
                        _HASHED_FIELD: "digest-a",
                        "line_number": 1,
                    }
                ]
            }
        },
        {
            "results": {
                "\\\\server\\share\\secret.txt": [
                    {
                        "type": _FINDING_TYPE,
                        _HASHED_FIELD: "digest-a",
                        "line_number": 1,
                    }
                ]
            }
        },
        {
            "results": {
                "src/a.py": [
                    {
                        "type": _FINDING_TYPE,
                        _HASHED_FIELD: "digest-a",
                        "line_number": 0,
                    }
                ]
            }
        },
        {
            "version": "1.5.0",
            "results": {
                "src/a.py": [
                    {
                        "filename": "src/other.py",
                        "type": _FINDING_TYPE,
                        _HASHED_FIELD: "digest-a",
                        "line_number": 1,
                    }
                ]
            },
        },
        {
            "version": "1.5.0",
            "results": {
                "src/a.py": [
                    {
                        "type": _FINDING_TYPE,
                        _HASHED_FIELD: "digest-a",
                        "line_number": 1,
                        "is_verified": "false",
                    }
                ]
            },
        },
    ],
)
def test_malformed_artifacts_fail_closed(malformed: Any, tmp_path: Path) -> None:
    valid = _document(("src/a.py", "Secret Keyword", "digest-a", 10))

    assert _verify(tmp_path, malformed, valid) == 2


def test_missing_artifact_fails_closed(tmp_path: Path) -> None:
    baseline_path = _write(
        tmp_path / "baseline.json",
        _document(("src/a.py", "Secret Keyword", "digest-a", 10)),
    )

    assert verifier.main([str(baseline_path), str(tmp_path / "missing.json")]) == 2


def test_baseline_requires_explicit_false_positive_triage(
    tmp_path: Path,
) -> None:
    finding = ("src/a.py", "Secret Keyword", "digest-a", 10)
    baseline = _document(finding)
    baseline["results"]["src/a.py"][0].pop("is_secret")
    current = _document(finding)
    assert _verify(tmp_path, baseline, current) == 2


def test_baseline_rejects_a_committed_secret_decision(tmp_path: Path) -> None:
    finding = ("src/a.py", "Secret Keyword", "digest-a", 10)
    baseline = _document(finding)
    baseline["results"]["src/a.py"][0]["is_secret"] = True
    assert _verify(tmp_path, baseline, _document(finding)) == 2


def test_invalid_json_fails_closed(tmp_path: Path) -> None:
    baseline_path = _write(
        tmp_path / "baseline.json",
        _document(("src/a.py", "Secret Keyword", "digest-a", 10)),
    )
    current_path = tmp_path / "current.json"
    current_path.write_text("not json", encoding="utf-8")

    assert verifier.main([str(baseline_path), str(current_path)]) == 2


def test_malformed_trusted_base_fails_closed(tmp_path: Path) -> None:
    finding = ("src/a.py", "Secret Keyword", "digest-a", 10)

    assert (
        _verify(
            tmp_path,
            _document(finding),
            _document(finding),
            trusted_base={"results": []},
        )
        == 2
    )


def test_cli_usage_error_is_fail_closed(capsys: pytest.CaptureFixture[str]) -> None:
    assert verifier.main([]) == 2
    assert "usage:" in capsys.readouterr().err.lower()


def test_empty_trusted_base_path_fails_closed(tmp_path: Path) -> None:
    finding = ("src/a.py", "Secret Keyword", "digest-a", 10)
    baseline_path = _write(tmp_path / "baseline.json", _document(finding))
    current_path = _write(tmp_path / "current.json", _document(finding))

    assert (
        verifier.main(
            [
                str(baseline_path),
                str(current_path),
                "--trusted-base-baseline",
                "",
            ]
        )
        == 2
    )


def test_base_baseline_alias_is_supported(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    existing = ("src/a.py", "Secret Keyword", "digest-a", 10)
    newly_suppressed = ("src/a.py", "Secret Keyword", "digest-b", 11)
    baseline_path = _write(
        tmp_path / "baseline.json", _document(existing, newly_suppressed)
    )
    current_path = _write(
        tmp_path / "current.json", _document(existing, newly_suppressed)
    )
    trusted_path = _write(tmp_path / "trusted.json", _document(existing))

    result = verifier.main(
        [
            str(baseline_path),
            str(current_path),
            "--base-baseline",
            str(trusted_path),
        ]
    )

    assert result == 1
    assert "trusted base" in capsys.readouterr().err.lower()


def test_reviewed_false_positive_disposition_matches_exact_identity() -> None:
    identity = verifier.FindingIdentity(
        "src/known.py", "Hex High Entropy String", "a" * 40, 1
    )

    dispositions = _nov13_verify_dispositions(
        _disposition_document(_reviewed_disposition()),
        today=verifier.date(2026, 10, 12),
    )

    assert dispositions == {identity}


def test_exact_new_identity_allowlists_remain_finite_and_path_scoped() -> None:
    assert len(verifier._V4_INDEPENDENT_CONTRACT_FINGERPRINT_IDENTITIES) == 32
    assert len(verifier._V4_PRIOR_INDEPENDENT_CONTRACT_FINGERPRINT_IDENTITIES) == 31
    assert len(verifier._EXTERNAL_KUBERNETES_SECRET_REFERENCE_IDENTITIES) == 27
    assert {
        path for path, _, _ in verifier._V4_INDEPENDENT_CONTRACT_FINGERPRINT_IDENTITIES
    } == {"tests/fixtures/full-backend-reusable-baseline.v4.yaml"}
    assert {
        path for path, _, _ in verifier._EXTERNAL_KUBERNETES_SECRET_REFERENCE_IDENTITIES
    } == {
        "charts/redis-compat/values.yaml",
        "charts/revocation-store/values.yaml",
        "charts/university-ecosystem/values-staging.yaml",
        "tests/test_docker_startup_contracts.py",
        "tests/test_helm_staging_contract.py",
        "tests/test_mfa_helm_contract.py",
        "tests/test_revocation_store_security_contract.py",
        "security/trivy-university-values.yaml",
    }


def test_source_contract_identifier_category_is_finite_and_evidence_bound() -> None:
    category = "source_contract_identifier"
    assert len(verifier._C6_CODE_FRAGMENT_IDENTITIES) == 9
    assert len(verifier._SOURCE_CONTRACT_IDENTIFIER_IDENTITIES) == 17
    evidence = "; ".join(verifier._FALSE_POSITIVE_CATEGORY_EVIDENCE_MARKERS[category])
    paths = {path for path, _, _ in verifier._C6_CODE_FRAGMENT_IDENTITIES}
    assert paths == {
        "services/file-processor/internal/config/secret_files_test.go",
        "services/file-processor/internal/config/secret_open_portable.go",
        "services/file-processor/internal/config/secret_open_unix.go",
        "services/gateway/internal/config/secret_files_test.go",
        "services/gateway/internal/config/secret_open_portable.go",
        "services/gateway/internal/config/secret_open_unix.go",
        "services/ws-hub/pkg/config/secret_files_test.go",
        "services/ws-hub/pkg/config/secret_open_portable.go",
        "services/ws-hub/pkg/config/secret_open_unix.go",
    }

    for path, finding_type, digest_bytes in sorted(
        verifier._SOURCE_CONTRACT_IDENTIFIER_IDENTITIES
    ):
        record = _reviewed_exact_disposition(path, finding_type, digest_bytes, category)
        record["evidence"] = evidence
        assert _nov13_verify_dispositions(
            _disposition_document(record),
            today=verifier.date(2026, 10, 16),
        ) == {
            verifier.FindingIdentity(path, finding_type, bytes(digest_bytes).hex(), 1)
        }


def test_page_title_route_identifier_candidates_are_exact_and_finite() -> None:
    category = "source_contract_identifier"
    expected = {
        (
            "frontend/src/components/ui/PageRouteSEO.tsx",
            "Secret Keyword",
            (
                246,
                11,
                35,
                176,
                57,
                187,
                96,
                181,
                93,
                29,
                195,
                205,
                161,
                83,
                22,
                254,
                236,
                136,
                40,
                118,
            ),
        ),
        (
            "frontend/src/components/ui/PageRouteSEO.tsx",
            "Secret Keyword",
            (
                13,
                39,
                13,
                74,
                47,
                213,
                87,
                245,
                102,
                242,
                14,
                180,
                169,
                34,
                53,
                125,
                169,
                142,
                149,
                34,
            ),
        ),
    }
    assert verifier._PAGE_TITLE_ROUTE_IDENTIFIER_IDENTITIES == expected
    assert expected <= verifier._SOURCE_CONTRACT_IDENTIFIER_IDENTITIES

    evidence = "; ".join(verifier._FALSE_POSITIVE_CATEGORY_EVIDENCE_MARKERS[category])
    for path, finding_type, digest_bytes in expected:
        approved = _reviewed_exact_disposition(
            path, finding_type, digest_bytes, category
        )
        approved["evidence"] = evidence
        approved["reviewed_on"] = "2026-10-23"
        approved["expires_on"] = "2027-01-10"
        pending = {**approved, "approval_status": "pending"}
        with pytest.raises(verifier.BaselineArtifactError, match="not approved"):
            _nov13_verify_dispositions(
                _disposition_document(pending),
                today=verifier.date(2026, 10, 23),
            )

        identity = approved["identity"]
        assert _nov13_verify_dispositions(
            _disposition_document(approved),
            today=verifier.date(2026, 10, 23),
        ) == {
            verifier.FindingIdentity(path, finding_type, bytes(digest_bytes).hex(), 1)
        }

        changed_records = (
            {**approved, "identity": {**identity, "path": path + ".changed"}},
            {
                **approved,
                "identity": {**identity, "type": "Basic Auth Credentials"},
            },
            {
                **approved,
                "identity": {
                    **identity,
                    "hashed_secret_bytes": [
                        (digest_bytes[0] + 1) % 256,
                        *digest_bytes[1:],
                    ],
                },
            },
            {**approved, "category": "auth_validation_ui_copy"},
            {**approved, "expires_on": "2027-01-11"},
        )
        for changed in changed_records:
            with pytest.raises(verifier.BaselineArtifactError):
                _nov13_verify_dispositions(
                    _disposition_document(changed),
                    today=verifier.date(2026, 10, 23),
                )


def test_c6_source_contract_records_require_explicit_approval() -> None:
    repository = Path(__file__).resolve().parents[1]
    assert Path(verifier.__file__).resolve() == (
        repository / "scripts/verify_secrets_baseline.py"
    )
    policy = json.loads(
        (repository / "quality/security-false-positive-dispositions.json").read_text(
            encoding="utf-8"
        )
    )
    records = [
        record
        for record in policy["records"]
        if record["category"] == "source_contract_identifier"
        and record["reviewed_on"] == "2026-10-16"
    ]
    identities = {
        (
            record["identity"]["path"],
            record["identity"]["type"],
            tuple(record["identity"]["hashed_secret_bytes"]),
        )
        for record in records
    }
    assert len(records) == 9
    assert identities == verifier._C6_CODE_FRAGMENT_IDENTITIES

    for record in records:
        assert record["owner"] == "egorribun"
        assert record["expires_on"] == "2027-01-10"
        assert "function-symbol hook" in record["evidence"]
        pending = {**record, "approval_status": "pending"}
        with pytest.raises(verifier.BaselineArtifactError, match="not approved"):
            _nov13_verify_dispositions(
                _disposition_document(pending),
                today=verifier.date(2026, 10, 16),
            )
        approved = {**record, "approval_status": "approved"}
        identity = approved["identity"]
        assert _nov13_verify_dispositions(
            _disposition_document(approved),
            today=verifier.date(2026, 10, 16),
        ) == {
            verifier.FindingIdentity(
                identity["path"],
                identity["type"],
                bytes(identity["hashed_secret_bytes"]).hex(),
                1,
            )
        }


def test_c6_source_contract_records_reject_mutated_identity_or_category() -> None:
    category = "source_contract_identifier"
    evidence = "; ".join(verifier._FALSE_POSITIVE_CATEGORY_EVIDENCE_MARKERS[category])
    for path, finding_type, digest_bytes in sorted(
        verifier._C6_CODE_FRAGMENT_IDENTITIES
    ):
        record = _reviewed_exact_disposition(path, finding_type, digest_bytes, category)
        record["evidence"] = evidence
        changes = (
            {"identity": {**record["identity"], "path": path + ".changed"}},
            {"identity": {**record["identity"], "type": "Basic Auth Credentials"}},
            {
                "identity": {
                    **record["identity"],
                    "hashed_secret_bytes": [
                        (digest_bytes[0] + 1) % 256,
                        *digest_bytes[1:],
                    ],
                }
            },
            {"category": "public_code_fragment"},
            {"category": "ci_test_contract_sentinel"},
        )
        for change in changes:
            changed = {**record, **change}
            with pytest.raises(verifier.BaselineArtifactError):
                _nov13_verify_dispositions(
                    _disposition_document(changed),
                    today=verifier.date(2026, 10, 16),
                )


@pytest.mark.parametrize(
    ("path", "finding_type", "digest_bytes"),
    sorted(verifier._V4_PRIOR_INDEPENDENT_CONTRACT_FINGERPRINT_IDENTITIES),
)
def test_v4_independent_contract_fingerprints_match_exact_identities(
    path: str, finding_type: str, digest_bytes: tuple[int, ...]
) -> None:
    record = _reviewed_exact_disposition(
        path,
        finding_type,
        digest_bytes,
        "independent_contract_fingerprint",
    )

    dispositions = _nov13_verify_dispositions(
        _disposition_document(record),
        today=verifier.date(2026, 10, 15),
    )

    assert dispositions == {
        verifier.FindingIdentity(path, finding_type, bytes(digest_bytes).hex(), 1)
    }


@pytest.mark.parametrize(
    ("path", "finding_type", "digest_bytes"),
    sorted(verifier._EXTERNAL_KUBERNETES_SECRET_REFERENCE_IDENTITIES),
)
def test_external_kubernetes_secret_references_match_exact_identities(
    path: str, finding_type: str, digest_bytes: tuple[int, ...]
) -> None:
    record = _reviewed_exact_disposition(
        path,
        finding_type,
        digest_bytes,
        "external_kubernetes_secret_reference",
    )

    dispositions = _nov13_verify_dispositions(
        _disposition_document(record),
        today=verifier.date(2026, 10, 15),
    )

    assert dispositions == {
        verifier.FindingIdentity(path, finding_type, bytes(digest_bytes).hex(), 1)
    }


def test_trivy_university_secret_reference_is_exact_and_requires_approval() -> None:
    path = "security/trivy-university-values.yaml"
    finding_type = "Secret Keyword"
    digest_bytes = bytes(
        (
            227,
            206,
            244,
            201,
            253,
            191,
            204,
            143,
            195,
            74,
            35,
            39,
            210,
            43,
            64,
            145,
            65,
            224,
            73,
            206,
        )
    )
    record = _reviewed_exact_disposition(
        path,
        finding_type,
        tuple(digest_bytes),
        "external_kubernetes_secret_reference",
    )
    record["reviewed_on"] = "2026-10-16"
    expected = verifier.FindingIdentity(path, finding_type, digest_bytes.hex(), 1)

    assert _nov13_verify_dispositions(
        _disposition_document(record),
        today=verifier.date(2026, 10, 16),
    ) == {expected}

    record["approval_status"] = "pending"
    with pytest.raises(verifier.BaselineArtifactError, match="not approved"):
        _nov13_verify_dispositions(
            _disposition_document(record),
            today=verifier.date(2026, 10, 16),
        )


@pytest.mark.parametrize(
    ("category", "identity"),
    [
        ("independent_contract_fingerprint", identity)
        for identity in sorted(
            verifier._V4_PRIOR_INDEPENDENT_CONTRACT_FINGERPRINT_IDENTITIES
        )
    ]
    + [
        ("external_kubernetes_secret_reference", identity)
        for identity in sorted(
            verifier._EXTERNAL_KUBERNETES_SECRET_REFERENCE_IDENTITIES
        )
    ],
)
def test_new_exact_disposition_categories_reject_mutated_identities(
    category: str,
    identity: tuple[str, str, tuple[int, ...]],
) -> None:
    path, finding_type, digest_bytes = identity
    mutations = (
        (path + ".changed", finding_type, digest_bytes),
        (
            path,
            "Secret Keyword"
            if finding_type == "Hex High Entropy String"
            else "Basic Auth Credentials",
            digest_bytes,
        ),
        (
            path,
            finding_type,
            ((digest_bytes[0] + 1) % 256, *digest_bytes[1:]),
        ),
    )

    for changed_path, changed_type, changed_digest in mutations:
        record = _reviewed_exact_disposition(
            changed_path,
            changed_type,
            changed_digest,
            category,
        )
        with pytest.raises(verifier.BaselineArtifactError):
            _nov13_verify_dispositions(
                _disposition_document(record),
                today=verifier.date(2026, 10, 15),
            )


def test_mfa_helm_secret_reference_is_exact_and_requires_approval() -> None:
    path = "tests/test_mfa_helm_contract.py"
    finding_type = "Secret Keyword"
    digest_bytes = bytes(
        (
            123,
            77,
            125,
            47,
            161,
            133,
            114,
            12,
            211,
            156,
            161,
            83,
            218,
            176,
            239,
            161,
            33,
            63,
            175,
            3,
        )
    )
    record = _reviewed_exact_disposition(
        path,
        finding_type,
        tuple(digest_bytes),
        "external_kubernetes_secret_reference",
    )
    record["reviewed_on"] = "2026-10-16"
    record["evidence"] = (
        "Kubernetes external Secret object name or key reference; not credential material. "
        "The referenced value is a public synthetic object name in an MFA Helm contract test."
    )
    expected = verifier.FindingIdentity(path, finding_type, digest_bytes.hex(), 1)

    assert _nov13_verify_dispositions(
        _disposition_document(record),
        today=verifier.date(2026, 10, 16),
    ) == {expected}

    record["approval_status"] = "pending"
    with pytest.raises(verifier.BaselineArtifactError, match="not approved"):
        _nov13_verify_dispositions(
            _disposition_document(record),
            today=verifier.date(2026, 10, 16),
        )


def test_external_secret_reference_requires_semantic_evidence_markers() -> None:
    path, finding_type, digest_bytes = sorted(
        verifier._EXTERNAL_KUBERNETES_SECRET_REFERENCE_IDENTITIES
    )[0]
    record = _reviewed_exact_disposition(
        path,
        finding_type,
        digest_bytes,
        "external_kubernetes_secret_reference",
    )
    record["evidence"] = "Exact detector identity was reviewed."

    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(record),
            today=verifier.date(2026, 10, 15),
        )


def test_external_secret_reference_still_requires_unexpired_review() -> None:
    path, finding_type, digest_bytes = sorted(
        verifier._EXTERNAL_KUBERNETES_SECRET_REFERENCE_IDENTITIES
    )[0]
    record = _reviewed_exact_disposition(
        path,
        finding_type,
        digest_bytes,
        "external_kubernetes_secret_reference",
    )
    record["expires_on"] = "2026-10-14"

    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(record),
            today=verifier.date(2026, 10, 15),
        )


def test_independent_contract_fingerprint_category_remains_exact() -> None:
    record = _reviewed_disposition(
        path="tests/fixtures/full-backend-reusable-baseline.v3.yaml",
        category="independent_contract_fingerprint",
    )

    dispositions = _nov13_verify_dispositions(
        _disposition_document(record),
        today=verifier.date(2026, 10, 12),
    )

    assert dispositions == {
        verifier.FindingIdentity(
            "tests/fixtures/full-backend-reusable-baseline.v3.yaml",
            "Hex High Entropy String",
            "a" * 40,
            1,
        )
    }


@pytest.mark.parametrize(
    ("category", "path", "finding_type"),
    [
        (
            "ci_test_contract_sentinel",
            ".github/workflows/ci.yml",
            "Basic Auth Credentials",
        ),
        (
            "ci_test_contract_sentinel",
            ".github/workflows/ci.yml",
            "Secret Keyword",
        ),
        (
            "ci_test_contract_sentinel",
            ".github/workflows/nightly-full-gate.yml",
            "Secret Keyword",
        ),
        (
            "ci_test_contract_sentinel",
            "frontend/scripts/frontend-quality-contract.test.mjs",
            "Secret Keyword",
        ),
        (
            "ci_test_contract_sentinel",
            "frontend/src/api/hooks/__tests__/campusConfig.test.ts",
            "Secret Keyword",
        ),
        (
            "ci_test_contract_sentinel",
            "tests/test_live_stand_resource_guard.py",
            "Base64 High Entropy String",
        ),
        (
            "ci_test_contract_sentinel",
            "tests/test_start_docker_orphan_ownership.py",
            "Base64 High Entropy String",
        ),
        (
            "public_package_integrity_metadata",
            "frontend/scripts/stryker-inventory.test.mjs",
            "Base64 High Entropy String",
        ),
        (
            "public_package_integrity_metadata",
            "frontend/scripts/generate-activity-pdf-font.py",
            "Base64 High Entropy String",
        ),
        (
            "public_package_integrity_metadata",
            "frontend/src/assets/fonts/inter-latin-cyrillic-400.provenance.json",
            "Base64 High Entropy String",
        ),
        (
            "public_totp_algorithm_alphabet",
            "frontend/tests/e2e-live/totp-recovery.live.spec.ts",
            "Base64 High Entropy String",
        ),
        (
            "documented_dummy_password_hash",
            "app/auth/security.py",
            "Secret Keyword",
        ),
        (
            "documented_dummy_password_hash",
            "tests/test_seed_admin_data.py",
            "Secret Keyword",
        ),
        (
            "documented_dummy_password_hash",
            "tests/test_seed_demo_account_preservation.py",
            "Secret Keyword",
        ),
        (
            "documented_dummy_password_hash",
            "tests/test_seed_demo_messenger.py",
            "Secret Keyword",
        ),
        (
            "synthetic_hmac_test_material",
            "services/gateway/internal/handlers/handlers_identity_closure_test.go",
            "Secret Keyword",
        ),
        (
            "synthetic_hmac_test_material",
            "services/ws-hub/pkg/hub/replay_security_adversarial_test.go",
            "Secret Keyword",
        ),
        (
            "synthetic_hmac_test_material",
            "tests/integration/test_historical_attendance_sender_migrations_postgres.py",
            "Secret Keyword",
        ),
        (
            "synthetic_fakeredis_lease_token",
            "tests/test_chat_command_failure_paths.py",
            "Secret Keyword",
        ),
        (
            "domain_resource_contract_fixture",
            "tests/test_live_stand_resource_guard.py",
            "Secret Keyword",
        ),
        (
            "internal_demo_stand_account_fixture",
            "frontend/tests/e2e-live/fixtures.ts",
            "Secret Keyword",
        ),
    ],
)
def test_non_hex_dispositions_are_scoped_to_reviewed_path_and_type(
    category: str, path: str, finding_type: str
) -> None:
    record = _reviewed_disposition(
        path=path,
        finding_type=finding_type,
        digest="c" * 40,
        category=category,
    )
    if category == "internal_demo_stand_account_fixture":
        record["evidence"] = (
            "Owner decision at docs/superpowers/plans/MVP_MASTER_PLAN.md:37 "
            "states internal-demo accounts are synthetic; external operational "
            "status remains unverified."
        )

    dispositions = _nov13_verify_dispositions(
        _disposition_document(record),
        today=verifier.date(2026, 10, 12),
    )

    assert dispositions == {verifier.FindingIdentity(path, finding_type, "c" * 40, 1)}


@pytest.mark.parametrize(
    ("category", "path", "finding_type"),
    [
        (
            "ci_test_contract_sentinel",
            "tests/test_auth_review_regressions.py",
            "Secret Keyword",
        ),
        (
            "ci_test_contract_sentinel",
            ".github/workflows/ci.yml",
            "Base64 High Entropy String",
        ),
        (
            "public_package_integrity_metadata",
            "frontend/scripts/stryker-inventory.test.mjs",
            "Secret Keyword",
        ),
        (
            "public_package_integrity_metadata",
            "frontend/scripts/generate-activity-pdf-font.py",
            "Secret Keyword",
        ),
        (
            "public_package_integrity_metadata",
            "frontend/src/assets/fonts/inter-latin-cyrillic-400.provenance.json",
            "Hex High Entropy String",
        ),
        (
            "public_package_integrity_metadata",
            "frontend/src/assets/fonts/unreviewed.provenance.json",
            "Base64 High Entropy String",
        ),
        (
            "public_totp_algorithm_alphabet",
            "frontend/tests/e2e-live/totp-recovery.live.spec.ts",
            "Basic Auth Credentials",
        ),
        (
            "documented_dummy_password_hash",
            "tests/test_auth_review_regressions.py",
            "Secret Keyword",
        ),
        (
            "synthetic_hmac_test_material",
            "app/auth/security.py",
            "Secret Keyword",
        ),
        (
            "synthetic_fakeredis_lease_token",
            "tests/test_auth_review_regressions.py",
            "Secret Keyword",
        ),
        (
            "synthetic_fakeredis_lease_token",
            "tests/test_chat_command_failure_paths.py",
            "Base64 High Entropy String",
        ),
        (
            "domain_resource_contract_fixture",
            "tests/test_live_stand_resource_guard.py",
            "Base64 High Entropy String",
        ),
        (
            "internal_demo_stand_account_fixture",
            "frontend/tests/e2e-live/fixtures.ts",
            "Base64 High Entropy String",
        ),
    ],
)
def test_non_hex_dispositions_reject_wrong_source_or_type(
    category: str, path: str, finding_type: str
) -> None:
    record = _reviewed_disposition(
        path=path,
        finding_type=finding_type,
        category=category,
    )

    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(record),
            today=verifier.date(2026, 10, 12),
        )


@pytest.mark.parametrize(
    "evidence",
    [
        "Internal demo fixture, external operational status remains unverified.",
        "Owner decision at docs/superpowers/plans/MVP_MASTER_PLAN.md:37.",
    ],
)
def test_internal_demo_account_requires_both_owner_evidence_markers(
    evidence: str,
) -> None:
    record = _reviewed_disposition(
        path="frontend/tests/e2e-live/fixtures.ts",
        finding_type="Secret Keyword",
        category="internal_demo_stand_account_fixture",
    )
    record["evidence"] = evidence

    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(record),
            today=verifier.date(2026, 10, 12),
        )


def test_internal_demo_account_category_does_not_approve_pending_record() -> None:
    record = _reviewed_disposition(
        path="frontend/tests/e2e-live/fixtures.ts",
        finding_type="Secret Keyword",
        category="internal_demo_stand_account_fixture",
    )
    record["approval_status"] = "pending"
    record["evidence"] = (
        "Owner decision at docs/superpowers/plans/MVP_MASTER_PLAN.md:37 "
        "states internal-demo accounts are synthetic; external operational "
        "status remains unverified."
    )

    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(record),
            today=verifier.date(2026, 10, 12),
        )


@pytest.mark.parametrize(
    ("candidate_path", "candidate_type", "candidate_digest"),
    [
        ("src/other.py", "Hex High Entropy String", "a" * 40),
        ("src/known.py", "Hex High Entropy String", "b" * 40),
    ],
)
def test_reviewed_disposition_does_not_match_other_path_or_digest(
    candidate_path: str, candidate_type: str, candidate_digest: str
) -> None:
    dispositions = _nov13_verify_dispositions(
        _disposition_document(_reviewed_disposition()),
        today=verifier.date(2026, 10, 12),
    )

    assert (
        verifier.FindingIdentity(candidate_path, candidate_type, candidate_digest, 1)
        not in dispositions
    )


def test_reviewed_disposition_rejects_unapproved_finding_type() -> None:
    record = _reviewed_disposition(finding_type="AWS Access Key")

    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(record), today=verifier.date(2026, 10, 12)
        )


@pytest.mark.parametrize(
    "change",
    [
        lambda record: record.update(category="unreviewed_category"),
        lambda record: record.update(approval_status="pending"),
        lambda record: record.update(expires_on="2026-10-11"),
        lambda record: record.update(reviewed_on="2026-10-13"),
        lambda record: record.update(expires_on="2027-01-11"),
        lambda record: record.pop("owner"),
        lambda record: record.pop("evidence"),
        lambda record: record.pop("reviewed_on"),
    ],
    ids=(
        "unknown-category",
        "pending",
        "expired",
        "future-review",
        "expiry-over-90-days",
        "missing-owner",
        "missing-evidence",
        "missing-review-date",
    ),
)
def test_reviewed_disposition_requires_approved_owner_and_finite_dates(
    change: Any,
) -> None:
    record = _reviewed_disposition()
    change(record)

    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(record), today=verifier.date(2026, 10, 12)
        )


@pytest.mark.parametrize(
    "invalid_path",
    ["src/*.py", "../src/known.py", "src//known.py", "src\\known.py"],
)
def test_reviewed_disposition_rejects_non_exact_paths(invalid_path: str) -> None:
    record = _reviewed_disposition(path=invalid_path)

    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(record), today=verifier.date(2026, 10, 12)
        )


def test_reviewed_disposition_rejects_duplicate_identities() -> None:
    record = _reviewed_disposition()

    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(record, _reviewed_disposition()),
            today=verifier.date(2026, 10, 12),
        )


def test_reviewed_disposition_rejects_unknown_fields_and_bad_digest() -> None:
    record = _reviewed_disposition()
    record["identity"]["unreviewed"] = False

    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(record), today=verifier.date(2026, 10, 12)
        )


@pytest.mark.parametrize(
    "invalid_bytes",
    [[0] * 19, [0] * 19 + [-1], [0] * 19 + [256], [0] * 19 + [True]],
)
def test_reviewed_disposition_rejects_malformed_digest_bytes(
    invalid_bytes: list[int],
) -> None:
    record = _reviewed_disposition()
    record["identity"]["hashed_secret_bytes"] = invalid_bytes

    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(record), today=verifier.date(2026, 10, 12)
        )


def test_reviewed_disposition_does_not_cover_an_unrelated_finding() -> None:
    unrelated = verifier.FindingIdentity(
        "src/known.py", "Hex High Entropy String", "b" * 40, 7
    )
    dispositions = _nov13_verify_dispositions(
        _disposition_document(_reviewed_disposition()),
        today=verifier.date(2026, 10, 12),
    )

    assert unrelated not in dispositions


def test_trusted_disposition_loader_uses_base_tree_not_worktree(
    tmp_path: Path,
) -> None:
    repository, _ = _new_git_fixture(tmp_path)
    record = _reviewed_disposition()
    trusted_sha = _commit_dispositions(repository, [record])
    policy_path = repository / "quality" / "security-false-positive-dispositions.json"
    policy_path.write_text(
        json.dumps(_disposition_document({**record, "approval_status": "pending"})),
        encoding="utf-8",
    )

    dispositions = verifier.load_trusted_base_false_positive_dispositions(
        trusted_sha,
        repository_root=repository,
        today=verifier.date(2026, 10, 12),
    )

    assert dispositions == {
        verifier.FindingIdentity("src/known.py", "Hex High Entropy String", "a" * 40, 1)
    }


def test_trusted_disposition_loader_ignores_candidate_only_artifact(
    tmp_path: Path,
) -> None:
    repository, trusted_sha = _new_git_fixture(tmp_path)
    policy_path = repository / "quality" / "security-false-positive-dispositions.json"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(
        json.dumps(_disposition_document(_reviewed_disposition())), encoding="utf-8"
    )

    dispositions = verifier.load_trusted_base_false_positive_dispositions(
        trusted_sha,
        repository_root=repository,
        today=verifier.date(2026, 10, 12),
    )

    assert dispositions == set()


def test_trusted_disposition_loader_rejects_duplicate_json_keys(
    tmp_path: Path,
) -> None:
    repository, _ = _new_git_fixture(tmp_path)
    policy_path = repository / "quality" / "security-false-positive-dispositions.json"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(
        '{"schema_version":1,"schema_version":1,"records":[]}', encoding="utf-8"
    )
    trusted_sha = _commit_git_fixture(repository, "add malformed disposition file")

    with pytest.raises(verifier.BaselineArtifactError):
        verifier.load_trusted_base_false_positive_dispositions(
            trusted_sha,
            repository_root=repository,
            today=verifier.date(2026, 10, 12),
        )


def test_main_uses_trusted_exact_dispositions(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository, _ = _new_git_fixture(tmp_path)
    trusted_sha = _commit_dispositions(repository, [_reviewed_disposition()])
    monkeypatch.setattr(
        verifier, "__file__", str(repository / "scripts" / "verify_secrets_baseline.py")
    )
    finding = ("src/known.py", "Hex High Entropy String", "a" * 40, 4)
    baseline_path = _write(tmp_path / "baseline.json", _document())
    current_path = _write(tmp_path / "current.json", _document(finding))

    result = verifier.main(
        [
            str(baseline_path),
            str(current_path),
            "--trusted-base-source-sha",
            trusted_sha,
        ]
    )

    assert result == 0
    assert "1 exact false-positive finding(s)" in capsys.readouterr().out


def test_owner_authored_candidate_disposition_is_explicit_opt_in(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository, trusted_sha = _new_git_fixture(tmp_path)
    policy_path = repository / "quality" / "security-false-positive-dispositions.json"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(
        json.dumps(_disposition_document(_reviewed_disposition())), encoding="utf-8"
    )
    monkeypatch.setattr(
        verifier, "__file__", str(repository / "scripts" / "verify_secrets_baseline.py")
    )
    finding = ("src/known.py", "Hex High Entropy String", "a" * 40, 4)
    baseline_path = _write(tmp_path / "baseline.json", _document())
    current_path = _write(tmp_path / "current.json", _document(finding))

    without_owner_gate = verifier.main(
        [
            str(baseline_path),
            str(current_path),
            "--trusted-base-source-sha",
            trusted_sha,
        ]
    )
    with_owner_gate = verifier.main(
        [
            str(baseline_path),
            str(current_path),
            "--trusted-base-source-sha",
            trusted_sha,
            "--owner-authored-disposition-update",
        ]
    )

    assert without_owner_gate == 1
    assert with_owner_gate == 0
    assert "new finding" in capsys.readouterr().err


def test_candidate_disposition_tamper_expiry_fails_closed(
    tmp_path: Path,
) -> None:
    repository, _ = _new_git_fixture(tmp_path)
    expired = _reviewed_disposition()
    expired["expires_on"] = "2026-10-11"
    policy_path = repository / "quality" / "security-false-positive-dispositions.json"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(json.dumps(_disposition_document(expired)), encoding="utf-8")

    with pytest.raises(verifier.BaselineArtifactError):
        verifier.load_owner_authored_candidate_false_positive_dispositions(
            repository_root=repository,
            today=verifier.date(2026, 10, 12),
        )


def test_push_can_use_accepted_head_policy_while_source_diff_uses_before_sha(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository, before_sha = _new_git_fixture(tmp_path)
    current_sha = _commit_dispositions(repository, [_reviewed_disposition()])
    monkeypatch.setattr(
        verifier, "__file__", str(repository / "scripts" / "verify_secrets_baseline.py")
    )
    finding = ("src/known.py", "Hex High Entropy String", "a" * 40, 4)
    baseline_path = _write(tmp_path / "baseline.json", _document())
    current_path = _write(tmp_path / "current.json", _document(finding))

    result = verifier.main(
        [
            str(baseline_path),
            str(current_path),
            "--trusted-base-source-sha",
            before_sha,
            "--trusted-disposition-source-sha",
            current_sha,
        ]
    )

    assert result == 0
    assert "exact false-positive" in capsys.readouterr().out


def test_trusted_disposition_does_not_allow_new_baseline_suppression(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository, _ = _new_git_fixture(tmp_path)
    trusted_sha = _commit_dispositions(repository, [_reviewed_disposition()])
    monkeypatch.setattr(
        verifier, "__file__", str(repository / "scripts" / "verify_secrets_baseline.py")
    )
    finding = ("src/known.py", "Hex High Entropy String", "a" * 40, 4)
    baseline_path = _write(tmp_path / "baseline.json", _document(finding))
    current_path = _write(tmp_path / "current.json", _document(finding))
    trusted_path = _write(tmp_path / "trusted.json", _document())

    result = verifier.main(
        [
            str(baseline_path),
            str(current_path),
            "--trusted-base-baseline",
            str(trusted_path),
            "--trusted-base-source-sha",
            trusted_sha,
        ]
    )

    assert result == 1
    assert "trusted base" in capsys.readouterr().err.lower()


def test_trusted_disposition_does_not_allow_added_inline_pragma(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository, _ = _new_git_fixture(tmp_path)
    trusted_sha = _commit_dispositions(repository, [_reviewed_disposition()])
    marker_path = repository / "new_source.py"
    marker_path.write_text(
        f"value = 'synthetic'  # {_inline_pragma_marker()}\n", encoding="utf-8"
    )
    _commit_git_fixture(repository, "add inline marker")
    monkeypatch.setattr(
        verifier, "__file__", str(repository / "scripts" / "verify_secrets_baseline.py")
    )
    finding = ("src/known.py", "Hex High Entropy String", "a" * 40, 4)
    baseline_path = _write(tmp_path / "baseline.json", _document())
    current_path = _write(tmp_path / "current.json", _document(finding))

    result = verifier.main(
        [
            str(baseline_path),
            str(current_path),
            "--trusted-base-source-sha",
            trusted_sha,
        ]
    )

    assert result == 1
    assert "inline secret-allowlist pragma" in capsys.readouterr().err


def test_disposition_file_is_protected_by_existing_owner_policy_gates() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    protected_path = "quality/security-false-positive-dispositions.json"
    workflow_paths = (
        ".github/workflows/codeql.yml",
        ".github/workflows/checkov.yml",
        ".github/workflows/dependency-review.yml",
        ".github/workflows/gitleaks.yml",
        ".github/workflows/reusable-security-audit.yml",
        ".github/workflows/zizmor.yml",
    )

    for relative_path in workflow_paths:
        workflow = (repository_root / relative_path).read_text(encoding="utf-8")
        assert f'"{protected_path}"' in workflow
        assert 'if [[ "$PR_AUTHOR" != "egorribun" ]]' in workflow

    policy_integrity = (
        repository_root / ".github" / "workflows" / "security-policy-integrity.yml"
    ).read_text(encoding="utf-8")
    assert "quality/*" in policy_integrity
    assert 'if [[ "$PR_AUTHOR" != "egorribun" ]]' in policy_integrity

    security_audit = (
        repository_root / ".github" / "workflows" / "reusable-security-audit.yml"
    ).read_text(encoding="utf-8")
    assert '"$PR_AUTHOR" == "egorribun"' in security_audit
    assert (
        'if [[ "$EVENT_NAME" == "pull_request" && "$PR_AUTHOR" == "egorribun" ]]'
        in security_audit
    )
    assert (
        'git diff --quiet "$SOURCE_BASE_SHA" -- '
        "quality/security-false-positive-dispositions.json" in security_audit
    )
    assert "--owner-authored-disposition-update" in security_audit
    assert '--trusted-disposition-source-sha "$HEAD_SHA"' in security_audit


def _public_compose_sentinel_record() -> dict[str, Any]:
    record = _reviewed_exact_disposition(
        "tests/test_live_nats_transport.py",
        "Secret Keyword",
        (
            *(74, 70, 48, 200, 151, 59, 103, 95, 251, 150),
            *(7, 200, 234, 230, 69, 166, 253, 9, 215, 53),
        ),
        "public_compose_inspection_test_sentinel",
    )
    record["reviewed_on"] = "2026-10-20"
    record["evidence"] = (
        "Public Compose inspection test sentinel "
        "live-stand-inspection-placeholder in LIVE_VAPID_PRIVATE_KEY; "
        "no-I/O request expectation; not credential material."
    )
    return record


@pytest.mark.parametrize(
    "today",
    [verifier.date(2026, 10, 20), verifier.date(2027, 1, 10)],
)
def test_public_compose_sentinel_matches_only_approved_identity(
    today: verifier.date,
) -> None:
    record = _public_compose_sentinel_record()
    identity = record["identity"]

    assert _nov13_verify_dispositions(_disposition_document(record), today=today) == {
        verifier.FindingIdentity(
            identity["path"],
            identity["type"],
            bytes(identity["hashed_secret_bytes"]).hex(),
            1,
        )
    }


@pytest.mark.parametrize(
    "change",
    [
        "path",
        "type",
        "value",
        "category",
        "evidence",
        "approval",
        "extended-expiry",
    ],
)
def test_public_compose_sentinel_refuses_scope_mutation(change: str) -> None:
    record = _public_compose_sentinel_record()
    if change == "path":
        record["identity"]["path"] = "tests/other.py"
    elif change == "type":
        record["identity"]["type"] = "Basic Auth Credentials"
    elif change == "value":
        record["identity"]["hashed_secret_bytes"][0] ^= 1
    elif change == "category":
        record["category"] = "ci_test_contract_sentinel"
    elif change == "evidence":
        record["evidence"] = "Reviewed public fixture."
    elif change == "approval":
        record["approval_status"] = "pending"
    else:
        record["expires_on"] = "2027-01-11"

    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(record),
            today=verifier.date(2026, 10, 20),
        )


def test_public_compose_sentinel_expires_after_approved_date() -> None:
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(_public_compose_sentinel_record()),
            today=verifier.date(2027, 1, 11),
        )


@pytest.mark.parametrize(
    "marker",
    [
        "public Compose inspection test sentinel",
        "live-stand-inspection-placeholder",
        "LIVE_VAPID_PRIVATE_KEY",
        "no-I/O request expectation",
        "not credential material",
    ],
)
def test_public_compose_sentinel_requires_each_semantic_marker(marker: str) -> None:
    record = _public_compose_sentinel_record()
    evidence = record["evidence"]
    start = evidence.casefold().index(marker.casefold())
    record["evidence"] = evidence[:start] + evidence[start + len(marker) :]

    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(record),
            today=verifier.date(2026, 10, 20),
        )


def test_public_compose_sentinel_identity_matches_fixed_source_literal() -> None:
    record = _public_compose_sentinel_record()
    source_path = Path(__file__).resolve().parents[1] / record["identity"]["path"]
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    values = [
        value
        for node in ast.walk(tree)
        if isinstance(node, ast.Dict)
        for key, value in zip(node.keys, node.values, strict=True)
        if isinstance(key, ast.Constant) and key.value == "LIVE_VAPID_PRIVATE_KEY"
    ]
    assert len(values) == 1
    value = values[0]
    assert isinstance(value, ast.Constant)
    assert value.value == "live-stand-inspection-placeholder"
    digest = hashlib.sha1(value.value.encode("utf-8"), usedforsecurity=False).digest()
    assert digest == bytes(record["identity"]["hashed_secret_bytes"])


def test_approved_go_image_disposition_binds_exact_source_checksum() -> None:
    root = Path(__file__).resolve().parents[1]
    path = "tests/test_docker_startup_contracts.py"
    expected_digest = _NOV11_GO_IMAGE_SCANNER_DIGEST
    policy = json.loads(
        (root / "quality/security-false-positive-dispositions.json").read_text(
            encoding="utf-8"
        )
    )
    records = [
        record
        for record in policy["records"]
        if record["identity"]["path"] == path
        and record["identity"]["type"] == "Hex High Entropy String"
        and bytes(record["identity"]["hashed_secret_bytes"]) == expected_digest
    ]
    assert len(records) == 1
    record = records[0]
    assert record["category"] == "public_integrity_digest"
    assert record["owner"] == "egorribun"
    assert record["reviewed_on"] == "2026-11-11"
    assert record["expires_on"] == "2027-01-10"
    assert record["approval_status"] == "approved"

    source = ast.parse((root / path).read_text(encoding="utf-8"))
    prefix = "golang:1.26.11-alpine3.24@sha256:"
    values = {
        node.value.removeprefix(prefix)
        for node in ast.walk(source)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith(prefix)
        and len(node.value) == len(prefix) + 64
    }
    assert len(values) == 1
    value = values.pop()
    actual_digest = hashlib.sha1(value.encode("utf-8"), usedforsecurity=False).digest()
    assert actual_digest == expected_digest
    assert _nov13_verify_dispositions(
        _disposition_document(record), today=verifier.date(2026, 11, 11)
    ) == {
        verifier.FindingIdentity(
            path,
            "Hex High Entropy String",
            expected_digest.hex(),
            1,
        )
    }


def test_approved_benchmark_helper_pins_bind_ten_exact_public_identities() -> None:
    root = Path(__file__).resolve().parents[1]
    paths = (
        "scripts/quality/benchmark_capture_activation.py",
        "tests/test_benchmark_capture_activation_workflow.py",
    )
    expected_digests = {
        bytes(
            (
                *(189, 150, 35, 69, 216, 63, 138, 226, 98, 138),
                *(68, 74, 85, 25, 150, 191, 96, 188, 12, 244),
            )
        ),
        bytes(
            (
                *(221, 15, 186, 27, 178, 116, 134, 111, 122, 164),
                *(212, 230, 250, 42, 89, 161, 192, 23, 163, 47),
            )
        ),
        bytes(
            (
                *(100, 220, 73, 83, 214, 135, 25, 219, 155, 67),
                *(136, 52, 53, 47, 201, 166, 188, 247, 162, 64),
            )
        ),
        bytes(
            (
                *(170, 211, 241, 2, 217, 140, 162, 48, 192, 237),
                *(158, 191, 80, 65, 79, 179, 86, 161, 66, 112),
            )
        ),
        bytes(
            (
                *(96, 116, 161, 36, 68, 56, 120, 27, 21, 234),
                *(138, 37, 0, 104, 147, 166, 166, 83, 205, 184),
            )
        ),
    }
    assert len(expected_digests) == 5
    policy = _reviewed_pre_retirement_dispositions()
    assert len(policy["records"]) == 505
    records = [
        record
        for record in policy["records"]
        if record["identity"]["path"] in paths and record["reviewed_on"] == "2026-10-21"
    ]
    expected = {
        (path, "Hex High Entropy String", digest)
        for path in paths
        for digest in expected_digests
    }
    assert len(records) == 10
    assert {
        (
            record["identity"]["path"],
            record["identity"]["type"],
            bytes(record["identity"]["hashed_secret_bytes"]),
        )
        for record in records
    } == expected

    for record in records:
        assert record["category"] == "public_integrity_digest"
        assert record["owner"] == "egorribun"
        assert record["reviewed_on"] == "2026-10-21"
        assert record["expires_on"] == "2027-01-10"
        assert record["approval_status"] == "approved"

    for path in paths:
        source = ast.parse((root / path).read_text(encoding="utf-8"))
        actual = {
            hashlib.sha1(node.value.encode("utf-8"), usedforsecurity=False).digest()
            for node in ast.walk(source)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        assert {
            _NOV11_HELPER_REBINDS[digest] for digest in expected_digests
        } <= actual, path

    assert _nov13_verify_dispositions(
        {"schema_version": 1, "records": records},
        today=verifier.date(2026, 10, 21),
    ) == {
        verifier.FindingIdentity(path, finding_type, digest.hex(), 1)
        for path, finding_type, digest in expected
    }


def _achievement_url_fixture_record() -> dict[str, Any]:
    record = _reviewed_exact_disposition(
        "frontend/src/components/profile/__tests__/profileUtils.closure.test.ts",
        "Basic Auth Credentials",
        (
            *(157, 78, 30, 35, 189, 91, 114, 112, 70, 169),
            *(227, 180, 183, 219, 87, 189, 141, 110, 230, 132),
        ),
        "synthetic_achievement_url_test_fixture",
    )
    record["owner"] = "egorribun"
    record["reviewed_on"] = "2026-10-22"
    record["evidence"] = (
        "Synthetic profile achievement URL test fixture on reserved example.test host; "
        "embedded-auth rejection coverage; not credential material. "
        "Owner approved this exact path, detector type and digest on 2026-10-22; "
        "no network request or operational login is performed."
    )
    return record


@pytest.mark.parametrize(
    "today",
    [verifier.date(2026, 10, 22), verifier.date(2027, 1, 10)],
)
def test_achievement_url_fixture_is_one_exact_approved_identity(
    today: verifier.date,
) -> None:
    record = _achievement_url_fixture_record()
    identity = record["identity"]
    expected = (
        identity["path"],
        identity["type"],
        tuple(identity["hashed_secret_bytes"]),
    )
    assert verifier._SYNTHETIC_ACHIEVEMENT_URL_TEST_FIXTURE_IDENTITIES == {expected}
    assert _nov13_verify_dispositions(_disposition_document(record), today=today) == {
        verifier.FindingIdentity(
            identity["path"],
            identity["type"],
            bytes(identity["hashed_secret_bytes"]).hex(),
            1,
        )
    }


@pytest.mark.parametrize(
    "change",
    ["path", "type", "value", "evidence", "approval", "missing-approval", "expiry"],
)
def test_achievement_url_fixture_refuses_scope_mutation(change: str) -> None:
    record = _achievement_url_fixture_record()
    if change == "path":
        record["identity"]["path"] = "frontend/src/other.test.ts"
    elif change == "type":
        record["identity"]["type"] = "Secret Keyword"
    elif change == "value":
        record["identity"]["hashed_secret_bytes"][0] ^= 1
    elif change == "evidence":
        record["evidence"] = "Reviewed fixture."
    elif change == "approval":
        record["approval_status"] = "pending"
    elif change == "missing-approval":
        del record["approval_status"]
    else:
        record["expires_on"] = "2027-01-11"

    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(record), today=verifier.date(2026, 10, 22)
        )


@pytest.mark.parametrize(
    "category",
    sorted(
        verifier._FALSE_POSITIVE_CATEGORIES - {"synthetic_achievement_url_test_fixture"}
    ),
)
def test_achievement_url_fixture_cannot_be_reclassified(category: str) -> None:
    record = _achievement_url_fixture_record()
    record["category"] = category
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(record), today=verifier.date(2026, 10, 22)
        )


@pytest.mark.parametrize(
    "marker",
    [
        "synthetic profile achievement URL test fixture",
        "reserved example.test host",
        "embedded-auth rejection coverage",
        "not credential material",
    ],
)
def test_achievement_url_fixture_requires_each_semantic_marker(marker: str) -> None:
    record = _achievement_url_fixture_record()
    evidence = record["evidence"]
    start = evidence.casefold().index(marker.casefold())
    record["evidence"] = evidence[:start] + evidence[start + len(marker) :]
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(record), today=verifier.date(2026, 10, 22)
        )


def test_achievement_url_fixture_expires_after_owner_approved_date() -> None:
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(_achievement_url_fixture_record()),
            today=verifier.date(2027, 1, 11),
        )


def test_achievement_url_fixture_binds_the_actual_source_and_policy() -> None:
    root = Path(__file__).resolve().parents[1]
    record = _achievement_url_fixture_record()
    policy = _reviewed_pre_retirement_dispositions()
    matching = [
        entry
        for entry in policy["records"]
        if entry["category"] == "synthetic_achievement_url_test_fixture"
    ]
    assert matching == [record]

    source = (root / record["identity"]["path"]).read_text(encoding="utf-8")
    urls = [
        urlsplit(json.loads(line.strip().removesuffix(",")))
        for line in source.splitlines()
        if line.strip().startswith('"https://') and "@" in line
    ]
    credentialed = [url for url in urls if url.password is not None]
    assert len(credentialed) == 1
    parsed = credentialed[0]
    assert parsed.scheme == "https"
    assert parsed.hostname == "example.test"
    assert parsed.path == "/award"
    assert parsed.username == "user"
    assert parsed.password is not None
    digest = hashlib.sha1(
        parsed.password.encode("utf-8"), usedforsecurity=False
    ).digest()
    assert digest == bytes(record["identity"]["hashed_secret_bytes"])


_AUTH_VALIDATION_UI_COPY_PATH = "frontend/src/i18n/locales/en/auth.json"
_AUTH_VALIDATION_UI_COPY_CATEGORY = "auth_validation_ui_copy"
_AUTH_VALIDATION_UI_COPY_DIGEST_BYTES = (
    bytes(
        (
            62,
            125,
            86,
            169,
            88,
            4,
            255,
            60,
            50,
            43,
            151,
            167,
            231,
            205,
            186,
            37,
            220,
            146,
            9,
            87,
        )
    ),
    bytes(
        (
            81,
            214,
            154,
            230,
            4,
            109,
            42,
            59,
            226,
            69,
            68,
            157,
            91,
            56,
            22,
            93,
            93,
            120,
            222,
            245,
        )
    ),
    bytes(
        (
            214,
            156,
            59,
            26,
            197,
            75,
            231,
            218,
            54,
            102,
            217,
            147,
            123,
            156,
            120,
            231,
            195,
            9,
            214,
            232,
        )
    ),
)


def _auth_validation_candidate_policy() -> dict[str, Any]:
    policy = _reviewed_pre_retirement_dispositions()
    policy["records"] = policy["records"][:315]
    return policy


def test_auth_validation_ui_copy_accepts_only_three_exact_identities() -> None:
    policy = _auth_validation_candidate_policy()
    records = [
        record
        for record in policy["records"]
        if record["category"] == _AUTH_VALIDATION_UI_COPY_CATEGORY
    ]
    assert len(records) == 3
    assert {
        (
            record["identity"]["path"],
            record["identity"]["type"],
            bytes(record["identity"]["hashed_secret_bytes"]).hex(),
        )
        for record in records
    } == {
        (_AUTH_VALIDATION_UI_COPY_PATH, "Secret Keyword", digest.hex())
        for digest in _AUTH_VALIDATION_UI_COPY_DIGEST_BYTES
    }
    assert _nov13_verify_dispositions(
        {**policy, "records": _nov4_current_view(policy["records"])},
        today=verifier.date(2026, 10, 23),
    ) >= {
        verifier.FindingIdentity(
            _AUTH_VALIDATION_UI_COPY_PATH, "Secret Keyword", digest.hex(), 1
        )
        for digest in _AUTH_VALIDATION_UI_COPY_DIGEST_BYTES
    }


def test_auth_validation_ui_copy_rejects_identity_or_category_transfer() -> None:
    original = _auth_validation_candidate_policy()
    invalid_mutations = (
        lambda record: record["identity"].update(
            path="frontend/src/i18n/locales/en/auth-copy.json"
        ),
        lambda record: record["identity"].update(type="Basic Auth Credentials"),
        lambda record: record["identity"]["hashed_secret_bytes"].__setitem__(
            0, (record["identity"]["hashed_secret_bytes"][0] + 1) % 256
        ),
        lambda record: record.update(category="source_contract_identifier"),
        lambda record: record.update(expires_on="2027-01-11"),
        lambda record: record.update(
            evidence="English auth validation UI copy; not credential material."
        ),
    )
    for mutate in invalid_mutations:
        policy = copy.deepcopy(original)
        record = next(
            row
            for row in policy["records"]
            if row["category"] == _AUTH_VALIDATION_UI_COPY_CATEGORY
        )
        mutate(record)
        with pytest.raises(verifier.BaselineArtifactError):
            _nov13_verify_dispositions(policy, today=verifier.date(2026, 10, 23))


def test_auth_validation_ui_copy_expires_at_the_finite_cap() -> None:
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _auth_validation_candidate_policy(), today=verifier.date(2027, 1, 11)
        )


def test_auth_validation_ui_copy_preserves_existing_298_records() -> None:
    policy = _auth_validation_candidate_policy()
    records = policy["records"]
    proposed = [
        record
        for record in records
        if record["category"] == _AUTH_VALIDATION_UI_COPY_CATEGORY
    ]
    existing = [
        record
        for record in records
        if record["category"] != _AUTH_VALIDATION_UI_COPY_CATEGORY
    ]
    assert len(records) == 315
    assert len(existing) == 312
    assert records[:298] == existing[:298]
    assert records[298:301] == proposed
    assert records[301:] == existing[298:]
    assert len(proposed) == 3


_AUD253_DISPOSITION_CATEGORY = "aud253_private_env_mode_test_fixture"
_AUD253_DISPOSITION_EXPIRY = "2027-01-10"
_TRIVY_DISPOSITION_PATH = "scripts/quality/validate_trivy_kyverno_fixture.py"
_TRIVY_DISPOSITION_EXPIRY = "2026-11-22"
_PRIOR_301_RECORDS_SHA256_BYTES = (
    96,
    123,
    56,
    7,
    89,
    203,
    93,
    254,
    158,
    177,
    160,
    18,
    255,
    82,
    60,
    102,
    196,
    38,
    90,
    151,
    51,
    197,
    65,
    95,
    160,
    54,
    204,
    127,
    55,
    154,
    8,
    140,
)
_AUTHORIZED_310_RECORDS_SHA256_BYTES = (
    108,
    60,
    61,
    59,
    80,
    160,
    171,
    13,
    95,
    7,
    68,
    56,
    156,
    213,
    52,
    179,
    6,
    82,
    27,
    22,
    85,
    54,
    49,
    37,
    152,
    32,
    214,
    120,
    166,
    81,
    86,
    43,
)


def _owner_review_candidate_policy() -> dict[str, Any]:
    policy = _reviewed_pre_retirement_dispositions()
    policy["records"] = policy["records"][:315]
    return policy


def _owner_review_record(
    policy: dict[str, Any], identity: tuple[str, str, tuple[int, ...]]
) -> dict[str, Any]:
    path, finding_type, digest_bytes = identity
    matches = [
        record
        for record in policy["records"]
        if record["identity"]["path"] == path
        and record["identity"]["type"] == finding_type
        and tuple(record["identity"]["hashed_secret_bytes"]) == digest_bytes
    ]
    assert len(matches) == 1
    return matches[0]


def test_aud253_and_trivy_candidate_records_are_exact_and_finite() -> None:
    policy = _owner_review_candidate_policy()
    policy = {**policy, "records": _nov4_current_view(policy["records"])}
    aud253 = [
        record
        for record in policy["records"]
        if record["category"] == _AUD253_DISPOSITION_CATEGORY
    ]
    trivy = [
        record
        for record in policy["records"]
        if record["identity"]["path"] == _TRIVY_DISPOSITION_PATH
    ]
    assert len(policy["records"]) == 315
    assert len(aud253) == 5
    assert len(trivy) == 2
    assert {
        (
            record["identity"]["path"],
            record["identity"]["type"],
            tuple(record["identity"]["hashed_secret_bytes"]),
        )
        for record in aud253
    } == verifier._AUD253_PRIVATE_ENV_MODE_TEST_FIXTURE_IDENTITIES
    assert {
        (
            record["identity"]["path"],
            record["identity"]["type"],
            tuple(record["identity"]["hashed_secret_bytes"]),
        )
        for record in trivy
    } == verifier._TRIVY_KYVERNO_PUBLIC_CHECKSUM_IDENTITIES
    for record in aud253:
        assert record["expires_on"] == _AUD253_DISPOSITION_EXPIRY
    for record in trivy:
        assert record["category"] == "public_integrity_digest"
        assert record["expires_on"] == _TRIVY_DISPOSITION_EXPIRY
    assert _nov13_verify_dispositions(policy, today=verifier.date(2026, 10, 23))


def test_aud253_candidate_rejects_identity_category_evidence_and_expiry_changes() -> (
    None
):
    policy = _owner_review_candidate_policy()
    identity = next(iter(verifier._AUD253_PRIVATE_ENV_MODE_TEST_FIXTURE_IDENTITIES))
    mutations = (
        lambda row: row["identity"].update(path="tests/other_fixture.py"),
        lambda row: row["identity"].update(type="Hex High Entropy String"),
        lambda row: row["identity"]["hashed_secret_bytes"].__setitem__(
            0, (row["identity"]["hashed_secret_bytes"][0] + 1) % 256
        ),
        lambda row: row.update(category="public_integrity_digest"),
        lambda row: row.update(expires_on="2027-01-11"),
        lambda row: row.update(
            evidence="synthetic test fixture; not credential material."
        ),
    )
    for mutate in mutations:
        candidate = copy.deepcopy(policy)
        mutate(_owner_review_record(candidate, identity))
        with pytest.raises(verifier.BaselineArtifactError):
            _nov13_verify_dispositions(candidate, today=verifier.date(2026, 10, 23))


def test_trivy_candidate_stays_exact_in_public_integrity_category() -> None:
    policy = _owner_review_candidate_policy()
    policy = {**policy, "records": _nov4_current_view(policy["records"])}
    mutations = (
        lambda row: row["identity"].update(path="scripts/quality/other_validator.py"),
        lambda row: row["identity"].update(type="Base64 High Entropy String"),
        lambda row: row["identity"]["hashed_secret_bytes"].__setitem__(
            0, (row["identity"]["hashed_secret_bytes"][0] + 1) % 256
        ),
        lambda row: row.update(category="documented_crypto_test_vector"),
        lambda row: row.update(expires_on="2026-11-23"),
        lambda row: row.update(
            evidence="Public integrity checksum; not credential material."
        ),
    )
    # Cover both finite identities deterministically; set order is not stable.
    for identity in sorted(verifier._TRIVY_KYVERNO_PUBLIC_CHECKSUM_IDENTITIES):
        for mutate in mutations:
            candidate = copy.deepcopy(policy)
            mutate(_owner_review_record(candidate, identity))
            with pytest.raises(verifier.BaselineArtifactError):
                _nov13_verify_dispositions(candidate, today=verifier.date(2026, 10, 23))


@pytest.mark.parametrize(
    "identity", sorted(verifier._TRIVY_KYVERNO_PUBLIC_CHECKSUM_IDENTITIES)
)
def test_trivy_checksum_renewal_is_valid_through_approved_expiry(
    identity: tuple[str, str, tuple[int, ...]],
) -> None:
    policy = _owner_review_candidate_policy()
    policy["records"] = _nov4_current_view(policy["records"])
    record = _owner_review_record(policy, identity)
    record.update(reviewed_on="2026-11-04", expires_on="2027-01-10")
    expected = {
        verifier.FindingIdentity(identity[0], identity[1], bytes(identity[2]).hex(), 1)
    }
    for current in (verifier.date(2026, 11, 4), verifier.date(2027, 1, 10)):
        assert (
            _nov13_verify_dispositions(_disposition_document(record), today=current)
            == expected
        )
    with pytest.raises(verifier.BaselineArtifactError, match="date range"):
        _nov13_verify_dispositions(
            _disposition_document(record), today=verifier.date(2027, 1, 11)
        )
    with pytest.raises(verifier.BaselineArtifactError, match="date range"):
        _nov13_verify_dispositions(
            _disposition_document(record), today=verifier.date(2026, 11, 3)
        )


@pytest.mark.parametrize(
    "identity", sorted(verifier._TRIVY_KYVERNO_PUBLIC_CHECKSUM_IDENTITIES)
)
def test_trivy_historical_approval_keeps_its_original_expiry(
    identity: tuple[str, str, tuple[int, ...]],
) -> None:
    policy = _owner_review_candidate_policy()
    policy["records"] = _nov4_current_view(policy["records"])
    record = _owner_review_record(policy, identity)
    assert record["expires_on"] == "2026-11-22"
    assert _nov13_verify_dispositions(
        _disposition_document(record), today=verifier.date(2026, 11, 22)
    )
    with pytest.raises(verifier.BaselineArtifactError, match="date range"):
        _nov13_verify_dispositions(
            _disposition_document(record), today=verifier.date(2026, 11, 23)
        )


@pytest.mark.parametrize(
    "identity", sorted(verifier._TRIVY_KYVERNO_PUBLIC_CHECKSUM_IDENTITIES)
)
@pytest.mark.parametrize("mutation", ["expiry", "review", "owner"])
def test_trivy_checksum_renewal_rejects_unapproved_metadata(
    identity: tuple[str, str, tuple[int, ...]], mutation: str
) -> None:
    policy = _owner_review_candidate_policy()
    policy["records"] = _nov4_current_view(policy["records"])
    record = _owner_review_record(policy, identity)
    record.update(reviewed_on="2026-11-04", expires_on="2027-01-10")
    if mutation == "expiry":
        record["expires_on"] = "2027-01-11"
    elif mutation == "review":
        record["reviewed_on"] = "2026-11-03"
    else:
        record["owner"] = "Another Reviewer"
    with pytest.raises(verifier.BaselineArtifactError, match="Trivy Kyverno"):
        _nov13_verify_dispositions(
            _disposition_document(record), today=verifier.date(2026, 11, 4)
        )


def test_aud253_fixture_digests_are_bound_to_embedded_powershell_literals() -> None:
    root = Path(__file__).resolve().parents[1]
    tree = ast.parse(
        (root / "tests/test_aud253_private_env_files.py").read_text(encoding="utf-8")
    )
    values = [
        node.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "POWERSHELL_HARNESS"
            for target in node.targets
        )
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    ]
    assert len(values) == 1
    literal_pattern = re.compile("'((?:[^']|'')*)'|\"((?:[^\"`]|`.)*)\"")
    observed = set()
    for match in literal_pattern.finditer(values[0]):
        value = match.group(1) if match.group(1) is not None else match.group(2)
        value = value.replace("''", "'")
        observed.add(
            hashlib.sha1(value.encode("utf-8"), usedforsecurity=False).digest()
        )
    assert {
        bytes(identity[2])
        for identity in verifier._AUD253_PRIVATE_ENV_MODE_TEST_FIXTURE_IDENTITIES
    } <= observed


def test_trivy_checksum_digests_are_bound_to_validator_constants() -> None:
    root = Path(__file__).resolve().parents[1]
    source = ast.parse((root / _TRIVY_DISPOSITION_PATH).read_text(encoding="utf-8"))
    values: dict[str, str] = {}
    for node in ast.walk(source):
        if not isinstance(node, ast.Assign):
            continue
        names = {target.id for target in node.targets if isinstance(target, ast.Name)}
        if names & {"EXPECTED_FIXTURE_SHA256", "EXPECTED_IGNORE_POLICY_SHA256"}:
            value = ast.literal_eval(node.value)
            assert isinstance(value, str)
            for name in names:
                if name in {"EXPECTED_FIXTURE_SHA256", "EXPECTED_IGNORE_POLICY_SHA256"}:
                    values[name] = value
    assert set(values) == {"EXPECTED_FIXTURE_SHA256", "EXPECTED_IGNORE_POLICY_SHA256"}
    actual = {
        hashlib.sha1(value.encode("ascii"), usedforsecurity=False).digest()
        for value in values.values()
    }
    assert actual == {
        bytes(identity[2])
        for identity in verifier._TRIVY_KYVERNO_PUBLIC_CHECKSUM_IDENTITIES
    }


def test_owner_review_preserves_the_previous_301_records_byte_for_byte() -> None:
    policy = _owner_review_candidate_policy()
    prior = policy["records"][:301]
    encoded = json.dumps(
        prior, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    assert hashlib.sha256(encoded).digest() == bytes(_PRIOR_301_RECORDS_SHA256_BYTES)
    assert len(policy["records"]) == 315


def test_workflow_owner_review_candidate_records_are_exact_and_finite() -> None:
    policy = _owner_review_candidate_policy()
    records = policy["records"][310:]
    expected = [
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                143,
                120,
                48,
                192,
                43,
                11,
                20,
                246,
                31,
                253,
                204,
                224,
                203,
                218,
                179,
                79,
                187,
                212,
                10,
                41,
            ),
            "public_integrity_digest",
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                85,
                158,
                8,
                17,
                13,
                217,
                219,
                104,
                145,
                111,
                194,
                19,
                60,
                251,
                92,
                240,
                212,
                85,
                113,
                116,
            ),
            "independent_contract_fingerprint",
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                94,
                40,
                155,
                35,
                12,
                205,
                36,
                191,
                27,
                93,
                89,
                252,
                6,
                36,
                193,
                174,
                240,
                78,
                30,
                64,
            ),
            "independent_contract_fingerprint",
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                228,
                251,
                163,
                207,
                40,
                164,
                144,
                11,
                26,
                225,
                79,
                240,
                197,
                199,
                12,
                121,
                37,
                113,
                215,
                216,
            ),
            "independent_contract_fingerprint",
        ),
        (
            "tests/fixtures/full-backend-reusable-baseline.v4.yaml",
            "Hex High Entropy String",
            (
                109,
                237,
                50,
                137,
                135,
                161,
                1,
                220,
                60,
                104,
                144,
                173,
                229,
                20,
                90,
                76,
                18,
                192,
                224,
                154,
            ),
            "independent_contract_fingerprint",
        ),
    ]
    actual = [
        (
            record["identity"]["path"],
            record["identity"]["type"],
            tuple(record["identity"]["hashed_secret_bytes"]),
            record["category"],
        )
        for record in records
    ]
    assert actual == expected
    assert all(record["owner"] == "egorribun" for record in records)
    assert all(record["reviewed_on"] == "2026-10-23" for record in records)
    assert all(record["expires_on"] == "2027-01-10" for record in records)
    assert all(record["approval_status"] == "approved" for record in records)


def test_workflow_owner_review_candidate_preserves_authorized_310_prefix() -> None:
    policy = _owner_review_candidate_policy()
    prior = policy["records"][:310]
    encoded = json.dumps(
        prior, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    assert hashlib.sha256(encoded).digest() == bytes(
        _AUTHORIZED_310_RECORDS_SHA256_BYTES
    )
    assert len(policy["records"]) == 315


_AUD495_CACHE_KEY_REDACTION_TEST_FIXTURE_CATEGORY = (
    "aud495_cache_key_redaction_test_fixture"
)
_AUD495_CACHE_KEY_REDACTION_TEST_FIXTURE_PATH = "tests/test_cache_object_keys_aud495.py"
_AUD495_CACHE_KEY_HISTORICAL_IDENTITIES = {
    (
        _AUD495_CACHE_KEY_REDACTION_TEST_FIXTURE_PATH,
        "Secret Keyword",
        tuple(bytes.fromhex("9e601bae9cd4e3075d55858bed83ff4e4bfdff10")),
    ),
    (
        _AUD495_CACHE_KEY_REDACTION_TEST_FIXTURE_PATH,
        "Secret Keyword",
        tuple(bytes.fromhex("cee0221af84e16fa6180f0600ea14be1cd97c48f")),
    ),
}


def _assert_aud495_cache_canary_uses_runtime_secret(
    function: ast.AsyncFunctionDef,
) -> None:
    assignments = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "secret_key"
            for target in node.targets
        )
    ]
    assert len(assignments) == 1
    value = assignments[0].value
    assert isinstance(value, ast.Call)
    assert isinstance(value.func, ast.Attribute)
    assert isinstance(value.func.value, ast.Name)
    assert value.func.value.id == "secrets"
    assert value.func.attr == "token_urlsafe"
    assert len(value.args) == 1
    assert isinstance(value.args[0], ast.Constant) and value.args[0].value == 32
    assert not value.keywords


def _aud495_cache_key_historical_fixture_identities() -> set[
    tuple[str, str, tuple[int, ...]]
]:
    path = _AUD495_CACHE_KEY_REDACTION_TEST_FIXTURE_PATH
    source_text = (Path(__file__).resolve().parents[1] / path).read_text(
        encoding="utf-8"
    )
    source = ast.parse(source_text)
    target_functions = {
        "test_backend_error_logs_do_not_emit_cache_key_or_exception_text",
        "test_invalid_payload_logs_redact_cache_key",
    }
    function_sources: dict[str, str] = {}
    for function in source.body:
        if (
            not isinstance(function, ast.AsyncFunctionDef)
            or function.name not in target_functions
        ):
            continue
        _assert_aud495_cache_canary_uses_runtime_secret(function)
        function_source = ast.get_source_segment(source_text, function)
        assert function_source is not None
        function_sources[function.name] = function_source
    assert set(function_sources) == target_functions
    assert all(
        "secret_key not in repr(call)" in function_source
        for function_source in function_sources.values()
    )
    assert (
        'call.kwargs.get("exc_info")'
        in function_sources[
            "test_backend_error_logs_do_not_emit_cache_key_or_exception_text"
        ]
    )
    assert (
        'keyed_fake.get.await_args.args[0] == (\n            f"aud495-key-derived-from-object:{secret_key}"\n        )'
        in function_sources[
            "test_backend_error_logs_do_not_emit_cache_key_or_exception_text"
        ]
    )
    assert len(_AUD495_CACHE_KEY_HISTORICAL_IDENTITIES) == 2
    return set(_AUD495_CACHE_KEY_HISTORICAL_IDENTITIES)


def test_aud495_cache_key_fixture_binds_historical_records_and_runtime_source() -> None:
    expected = _aud495_cache_key_historical_fixture_identities()
    assert verifier._AUD495_CACHE_KEY_REDACTION_TEST_FIXTURE_IDENTITIES == expected
    assert (
        verifier._FALSE_POSITIVE_EXACT_CATEGORY_IDENTITIES[
            _AUD495_CACHE_KEY_REDACTION_TEST_FIXTURE_CATEGORY
        ]
        == expected
    )
    assert verifier._AUD495_CACHE_KEY_REDACTION_TEST_FIXTURE_DIGESTS == {
        identity[2] for identity in expected
    }


def test_aud495_cache_key_fixture_rejects_literal_secret_mutation() -> None:
    path = _AUD495_CACHE_KEY_REDACTION_TEST_FIXTURE_PATH
    source_text = (Path(__file__).resolve().parents[1] / path).read_text(
        encoding="utf-8"
    )
    source = ast.parse(source_text)
    function = next(
        node
        for node in source.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name
        == "test_backend_error_logs_do_not_emit_cache_key_or_exception_text"
    )
    assignment = next(
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "secret_key"
            for target in node.targets
        )
    )
    assignment.value = ast.Constant(value="literal fixture")
    with pytest.raises(AssertionError):
        _assert_aud495_cache_canary_uses_runtime_secret(function)


def test_aud495_cache_key_fixture_candidate_is_exact_and_requires_owner_approval() -> (
    None
):
    category = _AUD495_CACHE_KEY_REDACTION_TEST_FIXTURE_CATEGORY
    identities = _aud495_cache_key_historical_fixture_identities()
    evidence = "; ".join(verifier._FALSE_POSITIVE_CATEGORY_EVIDENCE_MARKERS[category])
    approved_records = []
    for path, finding_type, digest_bytes in sorted(identities):
        record = _reviewed_exact_disposition(path, finding_type, digest_bytes, category)
        record["evidence"] = evidence
        record["reviewed_on"] = "2026-10-23"
        record["expires_on"] = "2027-01-10"
        approved_records.append(record)

    expected_findings = {
        verifier.FindingIdentity(path, finding_type, bytes(digest).hex(), 1)
        for path, finding_type, digest in identities
    }
    assert (
        _nov13_verify_dispositions(
            _disposition_document(*approved_records),
            today=verifier.date(2026, 10, 23),
        )
        == expected_findings
    )

    pending = copy.deepcopy(approved_records)
    pending[0]["approval_status"] = "pending_owner_review"
    with pytest.raises(verifier.BaselineArtifactError, match="not approved"):
        _nov13_verify_dispositions(
            _disposition_document(*pending), today=verifier.date(2026, 10, 23)
        )

    for mutation in (
        lambda row: row["identity"].update(path="tests/other.py"),
        lambda row: row["identity"].update(type="Hex High Entropy String"),
        lambda row: row["identity"].update(
            hashed_secret_bytes=[
                (row["identity"]["hashed_secret_bytes"][0] + 1) % 256,
                *row["identity"]["hashed_secret_bytes"][1:],
            ]
        ),
        lambda row: row.update(category="source_contract_identifier"),
        lambda row: row.update(evidence="synthetic fixture; not credential material"),
        lambda row: row.update(expires_on="2027-01-11"),
    ):
        changed = copy.deepcopy(approved_records)
        mutation(changed[0])
        with pytest.raises(verifier.BaselineArtifactError):
            _nov13_verify_dispositions(
                _disposition_document(*changed), today=verifier.date(2026, 10, 23)
            )


_AUD495_IMMUTABLE_315_PREFIX_SHA256 = (
    "16330df8c10ee81bab39b51ab54917605d1e589b1d443f0c93862a179e69e653"
)
_AUD495_TEST_ONLY_OWNER_MARKER = "TEST_FIXTURE_ONLY"
_AUD495_TEST_ONLY_EVIDENCE_MARKER = "HYPOTHETICAL_TEST_FIXTURE_ONLY_NOT_OWNER_APPROVAL"


def test_aud495_318_policy_preserves_exact_315_prefix_and_finite_records() -> None:
    policy = _reviewed_pre_retirement_dispositions()
    records = policy["records"]
    assert len(records) == 505
    prefix = records[:315]
    encoded_prefix = json.dumps(
        prefix, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    assert hashlib.sha256(encoded_prefix).hexdigest() == (
        _AUD495_IMMUTABLE_315_PREFIX_SHA256
    )

    suffix = records[315:317]
    expected_identities = _aud495_cache_key_historical_fixture_identities()
    actual_identities = {
        (
            record["identity"]["path"],
            record["identity"]["type"],
            tuple(record["identity"]["hashed_secret_bytes"]),
        )
        for record in suffix
    }
    assert actual_identities == expected_identities
    assert all(
        record["category"] == _AUD495_CACHE_KEY_REDACTION_TEST_FIXTURE_CATEGORY
        for record in suffix
    )
    assert all(
        record["expires_on"] <= "2027-01-10" and record["approval_status"] == "approved"
        for record in suffix
    )

    test_only_rows = [
        record for record in suffix if record["owner"] == _AUD495_TEST_ONLY_OWNER_MARKER
    ]
    if test_only_rows:
        assert len(test_only_rows) == 2
        assert all(
            _AUD495_TEST_ONLY_EVIDENCE_MARKER in record["evidence"]
            for record in test_only_rows
        )

    digest_identity = _public_integrity_digest_source_identity()
    digest_record = records[317]
    assert (
        digest_record["identity"]["path"],
        digest_record["identity"]["type"],
        tuple(digest_record["identity"]["hashed_secret_bytes"]),
    ) == digest_identity
    assert digest_record["category"] == "public_integrity_digest"
    assert digest_record["expires_on"] <= "2027-01-10"
    assert digest_record["approval_status"] == "approved"

    expected_findings = {
        verifier.FindingIdentity(path, finding_type, bytes(digest).hex(), 1)
        for path, finding_type, digest in expected_identities
    }
    validated = _nov13_verify_dispositions(
        {
            "schema_version": policy["schema_version"],
            "records": _nov4_current_view(policy["records"][:347]),
        },
        today=verifier.date(2026, 10, 26),
    )
    assert expected_findings <= validated
    assert (
        verifier.FindingIdentity(
            digest_identity[0], digest_identity[1], bytes(digest_identity[2]).hex(), 1
        )
        in validated
    )

    pending = {**policy, "records": _nov4_current_view(policy["records"])}
    for record in pending["records"][315:]:
        record["approval_status"] = "pending_owner_review"
    with pytest.raises(verifier.BaselineArtifactError, match="not approved"):
        _nov13_verify_dispositions(pending, today=verifier.date(2026, 10, 25))


def _public_integrity_digest_source_identity() -> tuple[str, str, tuple[int, ...]]:
    source_path = Path(__file__).resolve()
    source = ast.parse(source_path.read_text(encoding="utf-8"))
    assignments = [
        node
        for node in source.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name)
            and target.id == "_AUD495_IMMUTABLE_315_PREFIX_SHA256"
            for target in node.targets
        )
    ]
    assert len(assignments) == 1
    public_digest = ast.literal_eval(assignments[0].value)
    assert isinstance(public_digest, str)
    assert len(public_digest) == 64
    assert all(character in "0123456789abcdef" for character in public_digest)
    detector_digest = hashlib.sha1(
        public_digest.encode("ascii"), usedforsecurity=False
    ).digest()
    return (
        "tests/test_verify_secrets_baseline.py",
        "Hex High Entropy String",
        tuple(detector_digest),
    )


def test_public_integrity_digest_candidate_is_one_exact_source_identity() -> None:
    # The record below is an in-memory validator fixture, not owner approval.
    identity = _public_integrity_digest_source_identity()
    assert verifier._PUBLIC_IMMUTABLE_315_POLICY_PREFIX_IDENTITIES == {identity}
    path, finding_type, digest_bytes = identity
    category = "public_integrity_digest"
    record = _reviewed_exact_disposition(path, finding_type, digest_bytes, category)
    record["evidence"] = (
        "Public SHA-256 integrity digest of immutable 315-record disposition prefix; "
        "source-contract test guard in tests/test_verify_secrets_baseline.py; "
        "not credential material."
    )
    identity_finding = verifier.FindingIdentity(
        path, finding_type, bytes(digest_bytes).hex(), 1
    )
    assert _nov13_verify_dispositions(
        _disposition_document(record), today=verifier.date(2026, 10, 23)
    ) == {identity_finding}

    mutations = []
    changed_path = copy.deepcopy(record)
    changed_path["identity"]["path"] = "tests/test_other_policy.py"
    mutations.append(changed_path)
    changed_digest = copy.deepcopy(record)
    changed_bytes = list(digest_bytes)
    changed_bytes[0] ^= 1
    changed_digest["identity"]["hashed_secret_bytes"] = changed_bytes
    mutations.append(changed_digest)
    changed_category = copy.deepcopy(record)
    changed_category["category"] = "documented_crypto_test_vector"
    mutations.append(changed_category)
    excessive_expiry = copy.deepcopy(record)
    excessive_expiry["expires_on"] = "2027-01-11"
    mutations.append(excessive_expiry)
    missing_evidence = copy.deepcopy(record)
    missing_evidence["evidence"] = "not credential material"
    mutations.append(missing_evidence)
    for changed in mutations:
        with pytest.raises(verifier.BaselineArtifactError):
            _nov13_verify_dispositions(
                _disposition_document(changed),
                today=verifier.date(2026, 10, 23),
            )


_OCT24_APPROVED_PUBLIC_DIGEST_RECORDS = [
    {
        "identity": {
            "path": "tests/integration/test_aud350_stored_event_timestamp_migration.py",
            "type": "Hex High Entropy String",
            "hashed_secret_bytes": [
                75,
                241,
                247,
                240,
                201,
                124,
                150,
                116,
                118,
                155,
                103,
                137,
                228,
                223,
                153,
                93,
                208,
                224,
                145,
                58,
            ],
        },
        "category": "public_integrity_digest",
        "evidence": (
            "Public SHA-256 integrity digest of the frozen AUD-350 migration "
            "fixture; independent source-contract guard in "
            "tests/integration/test_aud350_stored_event_timestamp_migration.py; "
            "not credential material."
        ),
        "owner": "egorribun",
        "reviewed_on": "2026-10-24",
        "expires_on": "2027-01-10",
        "approval_status": "approved",
    },
    {
        "identity": {
            "path": "tests/test_verify_secrets_baseline.py",
            "type": "Hex High Entropy String",
            "hashed_secret_bytes": [
                200,
                36,
                105,
                58,
                159,
                122,
                4,
                140,
                251,
                170,
                213,
                164,
                38,
                210,
                200,
                58,
                142,
                211,
                129,
                137,
            ],
        },
        "category": "independent_contract_fingerprint",
        "evidence": (
            "Public detect-secrets SHA-1 identity of the first historical "
            "AUD-495 cache-key canary; independent source-contract guard in "
            "tests/test_verify_secrets_baseline.py; original canary record "
            "retains its aud495_cache_key_redaction_test_fixture category; not "
            "credential material."
        ),
        "owner": "egorribun",
        "reviewed_on": "2026-10-24",
        "expires_on": "2027-01-10",
        "approval_status": "approved",
    },
    {
        "identity": {
            "path": "tests/test_verify_secrets_baseline.py",
            "type": "Hex High Entropy String",
            "hashed_secret_bytes": [
                73,
                167,
                128,
                111,
                78,
                205,
                84,
                128,
                139,
                99,
                249,
                165,
                3,
                236,
                79,
                56,
                147,
                246,
                140,
                151,
            ],
        },
        "category": "independent_contract_fingerprint",
        "evidence": (
            "Public detect-secrets SHA-1 identity of the second historical "
            "AUD-495 cache-key canary; independent source-contract guard in "
            "tests/test_verify_secrets_baseline.py; original canary record "
            "retains its aud495_cache_key_redaction_test_fixture category; not "
            "credential material."
        ),
        "owner": "egorribun",
        "reviewed_on": "2026-10-24",
        "expires_on": "2027-01-10",
        "approval_status": "approved",
    },
]

_OCT24_ORIGINAL_SUFFIX = [
    {
        "identity": {
            "path": "tests/test_cache_object_keys_aud495.py",
            "type": "Secret Keyword",
            "hashed_secret_bytes": [
                158,
                96,
                27,
                174,
                156,
                212,
                227,
                7,
                93,
                85,
                133,
                139,
                237,
                131,
                255,
                78,
                75,
                253,
                255,
                16,
            ],
        },
        "category": "aud495_cache_key_redaction_test_fixture",
        "evidence": (
            "AUD-495 cache-key log-redaction test fixture; synthetic canary "
            "used only by mocked backend tests; tests assert logger output "
            "omits the canary; not credential material"
        ),
        "owner": "egorribun",
        "reviewed_on": "2026-10-23",
        "expires_on": "2027-01-10",
        "approval_status": "approved",
    },
    {
        "identity": {
            "path": "tests/test_cache_object_keys_aud495.py",
            "type": "Secret Keyword",
            "hashed_secret_bytes": [
                206,
                224,
                34,
                26,
                248,
                78,
                22,
                250,
                97,
                128,
                240,
                96,
                14,
                161,
                75,
                225,
                205,
                151,
                196,
                143,
            ],
        },
        "category": "aud495_cache_key_redaction_test_fixture",
        "evidence": (
            "AUD-495 cache-key log-redaction test fixture; synthetic canary "
            "used only by mocked backend tests; tests assert logger output "
            "omits the canary; not credential material"
        ),
        "owner": "egorribun",
        "reviewed_on": "2026-10-23",
        "expires_on": "2027-01-10",
        "approval_status": "approved",
    },
    {
        "identity": {
            "path": "tests/test_verify_secrets_baseline.py",
            "type": "Hex High Entropy String",
            "hashed_secret_bytes": [
                121,
                18,
                205,
                213,
                192,
                120,
                136,
                208,
                61,
                126,
                251,
                249,
                119,
                59,
                133,
                113,
                22,
                198,
                10,
                132,
            ],
        },
        "category": "public_integrity_digest",
        "evidence": (
            "Public SHA-256 integrity digest of immutable 315-record "
            "disposition prefix; source-contract test guard in "
            "tests/test_verify_secrets_baseline.py; not credential material."
        ),
        "owner": "egorribun",
        "reviewed_on": "2026-10-24",
        "expires_on": "2027-01-10",
        "approval_status": "approved",
    },
]


def test_oct24_public_digest_policy_preserves_all_318_prior_records() -> None:
    policy = _reviewed_pre_retirement_dispositions()
    records = policy["records"]
    encoded_prefix = json.dumps(
        records[:315], sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    assert hashlib.sha256(encoded_prefix).hexdigest() == (
        _AUD495_IMMUTABLE_315_PREFIX_SHA256
    )
    assert records[315:318] == _OCT24_ORIGINAL_SUFFIX
    assert len(records) == 505
    assert records[318:321] == _OCT24_APPROVED_PUBLIC_DIGEST_RECORDS


def test_oct24_public_digest_identities_are_bound_to_unchanged_source() -> None:
    migration_path = _OCT24_APPROVED_PUBLIC_DIGEST_RECORDS[0]["identity"]["path"]
    migration_source = ast.parse(_pre_squash_source_text(migration_path))
    checksum_nodes = [
        node
        for node in migration_source.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "BASELINE_MIGRATION_SHA256"
            for target in node.targets
        )
    ]
    assert len(checksum_nodes) == 1
    checksum = ast.literal_eval(checksum_nodes[0].value)
    assert isinstance(checksum, str)
    frozen_fixture = _pre_squash_source_bytes(
        "tests/fixtures/migrations/aud350/"
        "202603280001_reconcile_post_uuid_migration_drift_baseline.py.txt"
    )
    assert hashlib.sha256(frozen_fixture).hexdigest() == checksum
    assert (
        list(hashlib.sha1(checksum.encode("ascii"), usedforsecurity=False).digest())
        == _OCT24_APPROVED_PUBLIC_DIGEST_RECORDS[0]["identity"]["hashed_secret_bytes"]
    )

    source = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    historical_nodes = [
        node
        for node in source.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name)
            and target.id == "_AUD495_CACHE_KEY_HISTORICAL_IDENTITIES"
            for target in node.targets
        )
    ]
    assert len(historical_nodes) == 1
    fingerprints = [
        node.args[0].value
        for node in ast.walk(historical_nodes[0].value)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "bytes"
        and node.func.attr == "fromhex"
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    ]
    assert len(fingerprints) == 2
    assert {tuple(bytes.fromhex(value)) for value in fingerprints} == {
        tuple(row["identity"]["hashed_secret_bytes"])
        for row in _OCT24_ORIGINAL_SUFFIX[:2]
    }
    assert {
        tuple(hashlib.sha1(value.encode("ascii"), usedforsecurity=False).digest())
        for value in fingerprints
    } == {
        tuple(row["identity"]["hashed_secret_bytes"])
        for row in _OCT24_APPROVED_PUBLIC_DIGEST_RECORDS[1:]
    }


@pytest.mark.parametrize("record", _OCT24_APPROVED_PUBLIC_DIGEST_RECORDS)
def test_oct24_public_digest_validator_accepts_only_reviewed_identity(
    record: dict[str, Any],
) -> None:
    identity = record["identity"]
    expected = verifier.FindingIdentity(
        identity["path"],
        identity["type"],
        bytes(identity["hashed_secret_bytes"]).hex(),
        1,
    )
    assert _nov13_verify_dispositions(
        _disposition_document(copy.deepcopy(record)),
        today=verifier.date(2026, 10, 24),
    ) == {expected}


@pytest.mark.parametrize("record", _OCT24_APPROVED_PUBLIC_DIGEST_RECORDS)
@pytest.mark.parametrize(
    "mutation",
    [
        "path",
        "detector",
        "digest",
        "category",
        "owner",
        "review_date",
        "evidence",
        "pending",
        "expiry_extension",
    ],
)
def test_oct24_public_digest_validator_rejects_scope_or_approval_change(
    record: dict[str, Any],
    mutation: str,
) -> None:
    changed = copy.deepcopy(record)
    if mutation == "path":
        changed["identity"]["path"] = "tests/unapproved_public_digest.py"
    elif mutation == "detector":
        changed["identity"]["type"] = "Secret Keyword"
    elif mutation == "digest":
        changed["identity"]["hashed_secret_bytes"][0] ^= 1
    elif mutation == "category":
        changed["category"] = "documented_crypto_test_vector"
    elif mutation == "owner":
        changed["owner"] = "Different Reviewer"
    elif mutation == "review_date":
        changed["reviewed_on"] = "2026-10-23"
    elif mutation == "evidence":
        changed["evidence"] = "public value; not credential material"
    elif mutation == "pending":
        changed["approval_status"] = "pending_owner_review"
    else:
        assert mutation == "expiry_extension"
        changed["expires_on"] = "2027-01-11"
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(changed), today=verifier.date(2026, 10, 24)
        )


@pytest.mark.parametrize("record", _OCT24_APPROVED_PUBLIC_DIGEST_RECORDS)
def test_oct24_public_digest_validator_rejects_expired_disposition(
    record: dict[str, Any],
) -> None:
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(copy.deepcopy(record)),
            today=verifier.date(2027, 1, 11),
        )


@pytest.mark.parametrize(
    "category",
    ["public_integrity_digest", "independent_contract_fingerprint"],
)
def test_oct24_public_digest_reserved_test_path_still_rejects_unlisted_values(
    category: str,
) -> None:
    changed = copy.deepcopy(_OCT24_APPROVED_PUBLIC_DIGEST_RECORDS[1])
    changed["category"] = category
    changed["identity"]["hashed_secret_bytes"] = list(range(20))
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(changed), today=verifier.date(2026, 10, 24)
        )


@pytest.mark.parametrize("record", _OCT24_APPROVED_PUBLIC_DIGEST_RECORDS[1:])
def test_oct24_public_fingerprint_cannot_move_to_legacy_allowed_path(
    record: dict[str, Any],
) -> None:
    changed = copy.deepcopy(record)
    changed["identity"]["path"] = (
        "tests/fixtures/full-backend-reusable-baseline.v3.yaml"
    )
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(changed), today=verifier.date(2026, 10, 24)
        )


_PUBLIC_GIT_BLOB_APPROVED_RECORDS = json.loads(
    (
        Path(__file__).resolve().parent
        / "fixtures"
        / "public-git-blob-dispositions.json"
    ).read_text(encoding="utf-8")
)["records"]


def test_public_git_blob_policy_preserves_all_321_prior_records() -> None:
    policy = _reviewed_pre_retirement_dispositions()
    # These existing independent guards compose the immutable 321-record prefix.
    test_oct24_public_digest_policy_preserves_all_318_prior_records()
    assert len(policy["records"]) == 505
    assert policy["records"][321:323] == _PUBLIC_GIT_BLOB_APPROVED_RECORDS[:2]
    assert len(_PUBLIC_GIT_BLOB_APPROVED_RECORDS) == 10


def test_public_git_blob_rebind_policy_preserves_all_323_prior_records() -> None:
    policy = _reviewed_pre_retirement_dispositions()
    test_public_git_blob_policy_preserves_all_321_prior_records()
    assert policy["records"][323:325] == _PUBLIC_GIT_BLOB_APPROVED_RECORDS[2:4]
    assert len(_PUBLIC_GIT_BLOB_APPROVED_RECORDS[2:4]) == 2
    assert [
        record["identity"]["path"] for record in _PUBLIC_GIT_BLOB_APPROVED_RECORDS[:2]
    ] == [
        record["identity"]["path"] for record in _PUBLIC_GIT_BLOB_APPROVED_RECORDS[2:4]
    ]
    assert {
        tuple(record["identity"]["hashed_secret_bytes"])
        for record in _PUBLIC_GIT_BLOB_APPROVED_RECORDS[:2]
    }.isdisjoint(
        {
            tuple(record["identity"]["hashed_secret_bytes"])
            for record in _PUBLIC_GIT_BLOB_APPROVED_RECORDS[2:4]
        }
    )


def _public_git_blob_source_identity(
    consumer: str, assignment_name: str, source: bytes
) -> tuple[int, ...]:
    assignments = [
        node
        for node in ast.parse(consumer).body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == assignment_name
            for target in node.targets
        )
    ]
    assert len(assignments) == 1
    value = ast.literal_eval(assignments[0].value)
    assert isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value)
    header = f"blob {len(source)}\0".encode("ascii")
    expected = hashlib.sha1(header + source, usedforsecurity=False).hexdigest()
    assert value == expected
    return tuple(hashlib.sha1(value.encode("ascii"), usedforsecurity=False).digest())


@pytest.mark.parametrize(
    ("record", "assignment_name", "source_path"),
    [
        (
            _PUBLIC_GIT_BLOB_APPROVED_RECORDS[0],
            "SOURCE_GIT_BLOB",
            "alembic/versions/148642dd1207_fix_missing_tables.py",
        ),
        (
            _PUBLIC_GIT_BLOB_APPROVED_RECORDS[1],
            "HISTORICAL_ORCHESTRATOR_BLOB",
            "tests/test_migration_148642dd1207_orchestrator.py",
        ),
    ],
)
def test_public_git_blob_current_pin_has_an_exact_approved_identity(
    record: dict[str, Any], assignment_name: str, source_path: str
) -> None:
    root = Path(__file__).resolve().parents[1]
    consumer_path = record["identity"]["path"]
    if consumer_path == "tests/helpers/migration_148642dd1207_trace.py":
        # This consumer was deleted by the fresh-only squash.
        consumer = _pre_squash_source_text(consumer_path)
    else:
        # This consumer is still live: never substitute its historical bytes.
        assert consumer_path == "tests/test_mfa_webauthn_tombstone.py"
        consumer = (root / consumer_path).read_text(encoding="utf-8")
    digest = _public_git_blob_source_identity(
        consumer,
        assignment_name,
        _pre_squash_source_bytes(source_path),
    )
    policy = _reviewed_pre_retirement_dispositions()
    assert any(
        row["identity"]
        == {
            "path": record["identity"]["path"],
            "type": "Hex High Entropy String",
            "hashed_secret_bytes": list(digest),
        }
        and row["category"] == "public_integrity_digest"
        for row in policy["records"]
    )


def test_public_git_blob_orchestrator_rebind_rejects_near_misses() -> None:
    record = _PUBLIC_GIT_BLOB_APPROVED_RECORDS[9]
    mutations = []
    wrong_path = copy.deepcopy(record)
    wrong_path["identity"]["path"] += ".changed"
    mutations.append(wrong_path)
    wrong_type = copy.deepcopy(record)
    wrong_type["identity"]["type"] = "Base Auth Credentials"
    mutations.append(wrong_type)
    wrong_digest = copy.deepcopy(record)
    wrong_digest["identity"]["hashed_secret_bytes"][0] ^= 1
    mutations.append(wrong_digest)
    wrong_category = copy.deepcopy(record)
    wrong_category["category"] = "source_contract_identifier"
    mutations.append(wrong_category)
    weak_evidence = copy.deepcopy(record)
    weak_evidence["evidence"] = weak_evidence["evidence"].replace(
        "HISTORICAL_ORCHESTRATOR_BLOB", "OTHER_SOURCE_PIN"
    )
    mutations.append(weak_evidence)
    pending = copy.deepcopy(record)
    pending["approval_status"] = "pending"
    mutations.append(pending)
    placeholder_owner = copy.deepcopy(record)
    placeholder_owner["owner"] = "PENDING_OWNER_REVIEW"
    mutations.append(placeholder_owner)
    extended_expiry = copy.deepcopy(record)
    extended_expiry["expires_on"] = "2027-01-11"
    mutations.append(extended_expiry)

    for changed in mutations:
        with pytest.raises(verifier.BaselineArtifactError):
            _nov13_verify_dispositions(
                _disposition_document(changed),
                today=verifier.date(2026, 10, 26),
            )


def test_public_git_blob_binding_rejects_source_literal_or_assignment_drift() -> None:
    source = b"reviewed source\n"
    header = f"blob {len(source)}\0".encode("ascii")
    value = hashlib.sha1(header + source, usedforsecurity=False).hexdigest()
    consumer = f"SOURCE = {value!r}\n"
    expected = tuple(
        hashlib.sha1(value.encode("ascii"), usedforsecurity=False).digest()
    )
    assert _public_git_blob_source_identity(consumer, "SOURCE", source) == expected
    changed_value = ("0" if value[0] != "0" else "1") + value[1:]
    for changed_consumer, changed_source in (
        (consumer, source + b"# drift\n"),
        (f"SOURCE = {changed_value!r}\n", source),
        (consumer + consumer, source),
        (consumer.replace("SOURCE", "OTHER"), source),
    ):
        with pytest.raises(AssertionError):
            _public_git_blob_source_identity(changed_consumer, "SOURCE", changed_source)


@pytest.mark.parametrize("record", _PUBLIC_GIT_BLOB_APPROVED_RECORDS)
def test_public_git_blob_validator_accepts_exact_historical_record_without_source(
    record: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    identity = record["identity"]
    expected = verifier.FindingIdentity(
        identity["path"],
        identity["type"],
        bytes(identity["hashed_secret_bytes"]).hex(),
        1,
    )
    assert _nov13_verify_dispositions(
        _disposition_document(copy.deepcopy(record)),
        today=verifier.date(2026, 10, 26),
    ) == {expected}


@pytest.mark.parametrize("record", _PUBLIC_GIT_BLOB_APPROVED_RECORDS)
@pytest.mark.parametrize(
    "mutation",
    [
        "path",
        "path_swap",
        "detector",
        "digest",
        "category",
        "owner",
        "review_date",
        "evidence",
        "pending",
        "expiry_extension",
    ],
)
def test_public_git_blob_validator_rejects_changed_scope_or_metadata(
    record: dict[str, Any], mutation: str
) -> None:
    changed = copy.deepcopy(record)
    if mutation == "path":
        changed["identity"]["path"] = "tests/unapproved_public_digest.py"
    elif mutation == "path_swap":
        changed["identity"]["path"] = next(
            row["identity"]["path"]
            for row in _PUBLIC_GIT_BLOB_APPROVED_RECORDS
            if row["identity"]["path"] != record["identity"]["path"]
        )
    elif mutation == "detector":
        changed["identity"]["type"] = "Secret Keyword"
    elif mutation == "digest":
        changed["identity"]["hashed_secret_bytes"][0] ^= 1
    elif mutation == "category":
        changed["category"] = "documented_crypto_test_vector"
    elif mutation == "owner":
        changed["owner"] = "Different Reviewer"
    elif mutation == "review_date":
        changed["reviewed_on"] = "2026-10-23"
    elif mutation == "evidence":
        changed["evidence"] = "public value; not credential material"
    elif mutation == "pending":
        changed["approval_status"] = "pending_owner_review"
    else:
        assert mutation == "expiry_extension"
        changed["expires_on"] = "2027-01-11"
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(changed), today=verifier.date(2026, 10, 25)
        )


@pytest.mark.parametrize("record", _PUBLIC_GIT_BLOB_APPROVED_RECORDS)
def test_public_git_blob_validator_rejects_expired_or_duplicate_record(
    record: dict[str, Any],
) -> None:
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(copy.deepcopy(record)),
            today=verifier.date(2027, 1, 11),
        )
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(copy.deepcopy(record), copy.deepcopy(record)),
            today=verifier.date(2026, 10, 25),
        )


@pytest.mark.parametrize("record", _PUBLIC_GIT_BLOB_APPROVED_RECORDS)
def test_public_git_blob_reserved_path_rejects_other_fingerprint(
    record: dict[str, Any],
) -> None:
    changed = copy.deepcopy(record)
    changed["identity"]["hashed_secret_bytes"] = list(range(20))
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(changed), today=verifier.date(2026, 10, 25)
        )


_OBSERVED_PUBLIC_SOURCE_METADATA_RECORDS = [
    {
        "identity": {
            "path": "frontend/scripts/generate-zod-root-lock-candidate.mjs",
            "type": "Hex High Entropy String",
            "hashed_secret_bytes": [
                93,
                153,
                98,
                228,
                62,
                95,
                145,
                81,
                122,
                89,
                127,
                149,
                156,
                66,
                233,
                25,
                253,
                139,
                106,
                91,
            ],
        },
        "category": "public_integrity_digest",
        "evidence": (
            "Public upstream Git commit identifier for colinhacks/zod v4.6.7; "
            "EXPECTED_ZOD_SOURCE_SHA in "
            "frontend/scripts/generate-zod-root-lock-candidate.mjs; official Git "
            "tag and hosted mature registry metadata agree; used for exact "
            "registry source-identity comparison; not credential material."
        ),
        "owner": "egorribun",
        "reviewed_on": "2026-10-24",
        "expires_on": "2027-01-10",
        "approval_status": "approved",
    },
    {
        "identity": {
            "path": "tests/test_logging_pii_redaction_contract.py",
            "type": "Secret Keyword",
            "hashed_secret_bytes": [
                241,
                119,
                30,
                46,
                101,
                173,
                30,
                82,
                73,
                135,
                104,
                15,
                34,
                136,
                138,
                34,
                211,
                106,
                94,
                148,
            ],
        },
        "category": "source_contract_identifier",
        "evidence": (
            "Public signing-key name csrf-signing-key in the secret_name metadata "
            "field of "
            "tests/test_logging_pii_redaction_contract.py::"
            "test_sensitive_field_matching_preserves_related_nonsecret_metadata; "
            "negative control requires this identifier to survive real log "
            "redaction; secret-related source identifier or required key-list "
            "expression; not credential material."
        ),
        "owner": "egorribun",
        "reviewed_on": "2026-10-24",
        "expires_on": "2027-01-10",
        "approval_status": "approved",
    },
]


def test_observed_public_metadata_policy_preserves_all_325_prior_records() -> None:
    policy = _reviewed_pre_retirement_dispositions()
    test_public_git_blob_rebind_policy_preserves_all_323_prior_records()
    assert len(policy["records"]) == 505
    assert policy["records"][325:327] == _OBSERVED_PUBLIC_SOURCE_METADATA_RECORDS
    assert len(_OBSERVED_PUBLIC_SOURCE_METADATA_RECORDS) == 2


def _zod_public_source_fingerprint(source: str) -> tuple[int, ...]:
    values = re.findall(
        r'^const EXPECTED_ZOD_SOURCE_SHA = "([0-9a-f]{40})"$',
        source,
        flags=re.MULTILINE,
    )
    assert len(values) == 1
    # Default-argument and comparison behavior is exercised by the required
    # Node helper guards; this Python check binds the scanner literal identity.
    return tuple(
        hashlib.sha1(values[0].encode("ascii"), usedforsecurity=False).digest()
    )


def _public_metadata_label_from_source(source: str) -> str:
    functions = [
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef)
        and node.name
        == "test_sensitive_field_matching_preserves_related_nonsecret_metadata"
    ]
    assert len(functions) == 1
    assignments = [
        node
        for node in functions[0].body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "event"
            for target in node.targets
        )
    ]
    assert len(assignments) == 1
    event = ast.literal_eval(assignments[0].value)
    assert isinstance(event, dict) and "secret_name" in event
    assertions = [
        node.test
        for node in functions[0].body
        if isinstance(node, ast.Assert)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Call)
        and isinstance(node.test.left.func, ast.Name)
        and node.test.left.func.id == "_redact_pii"
    ]
    assert len(assertions) == 1
    comparison = assertions[0]
    assert len(comparison.ops) == 1 and isinstance(comparison.ops[0], ast.Eq)
    assert len(comparison.comparators) == 1
    expected = ast.literal_eval(comparison.comparators[0])
    call = comparison.left
    assert len(call.args) == 3 and not call.keywords
    assert isinstance(call.args[0], ast.Constant) and call.args[0].value is None
    assert isinstance(call.args[1], ast.Constant) and call.args[1].value == "info"
    assert isinstance(call.args[2], ast.Name) and call.args[2].id == "event"
    assert event == expected
    value = event["secret_name"]
    assert isinstance(value, str) and value
    return value


def _public_metadata_label_fingerprint(source: str) -> tuple[int, ...]:
    value = _public_metadata_label_from_source(source)
    return tuple(hashlib.sha1(value.encode("utf-8"), usedforsecurity=False).digest())


@pytest.mark.parametrize(
    ("record", "fingerprint"),
    [
        (_OBSERVED_PUBLIC_SOURCE_METADATA_RECORDS[0], _zod_public_source_fingerprint),
        (
            _OBSERVED_PUBLIC_SOURCE_METADATA_RECORDS[1],
            _public_metadata_label_fingerprint,
        ),
    ],
)
def test_observed_public_metadata_current_source_has_an_exact_approved_identity(
    record: dict[str, Any], fingerprint: Any
) -> None:
    root = Path(__file__).resolve().parents[1]
    path = root / record["identity"]["path"]
    if not path.exists():
        # Historical dispositions may become stale when a consumer is removed.
        return
    digest = fingerprint(path.read_text(encoding="utf-8"))
    policy = _reviewed_pre_retirement_dispositions()
    assert any(
        row["identity"]
        == {
            "path": record["identity"]["path"],
            "type": record["identity"]["type"],
            "hashed_secret_bytes": list(digest),
        }
        and row["category"] == record["category"]
        for row in policy["records"]
    )


def test_zod_public_source_binding_rejects_changed_or_duplicate_pin() -> None:
    root = Path(__file__).resolve().parents[1]
    record = _OBSERVED_PUBLIC_SOURCE_METADATA_RECORDS[0]
    path = root / record["identity"]["path"]
    if not path.exists():
        return
    source = path.read_text(encoding="utf-8")
    original = _zod_public_source_fingerprint(source)
    value = re.findall(
        r'^const EXPECTED_ZOD_SOURCE_SHA = "([0-9a-f]{40})"$',
        source,
        flags=re.MULTILINE,
    )[0]
    changed = source.replace(value, "0" * len(value), 1)
    assert _zod_public_source_fingerprint(changed) != original
    declaration = next(
        line for line in source.splitlines() if line.startswith("const EXPECTED_")
    )
    with pytest.raises(AssertionError):
        _zod_public_source_fingerprint(source + "\n" + declaration + "\n")


def test_public_metadata_label_binding_rejects_changed_value_or_lost_control() -> None:
    root = Path(__file__).resolve().parents[1]
    record = _OBSERVED_PUBLIC_SOURCE_METADATA_RECORDS[1]
    path = root / record["identity"]["path"]
    if not path.exists():
        return
    source = path.read_text(encoding="utf-8")
    label = _public_metadata_label_from_source(source)
    original = _public_metadata_label_fingerprint(source)
    changed = source.replace(label, "different-public-label")
    assert _public_metadata_label_fingerprint(changed) != original
    for changed in (
        source.replace(label, "different-public-label", 1),
        source.replace('"secret_name"', '"csrf_hmac_secret"'),
        source.replace(
            'assert _redact_pii(None, "info", event) ==',
            "assert event ==",
        ),
    ):
        with pytest.raises(AssertionError):
            _public_metadata_label_from_source(changed)


@pytest.mark.parametrize("record", _OBSERVED_PUBLIC_SOURCE_METADATA_RECORDS)
def test_observed_public_metadata_accepts_exact_record_without_source(
    record: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    identity = record["identity"]
    expected = verifier.FindingIdentity(
        identity["path"],
        identity["type"],
        bytes(identity["hashed_secret_bytes"]).hex(),
        1,
    )
    assert _nov13_verify_dispositions(
        _disposition_document(copy.deepcopy(record)),
        today=verifier.date(2026, 10, 24),
    ) == {expected}


@pytest.mark.parametrize("record", _OBSERVED_PUBLIC_SOURCE_METADATA_RECORDS)
@pytest.mark.parametrize(
    "mutation",
    [
        "path",
        "path_swap",
        "detector",
        "digest",
        "category",
        "owner",
        "review_date",
        "evidence",
        "pending",
        "expiry_extension",
    ],
)
def test_observed_public_metadata_rejects_changed_scope_or_approval(
    record: dict[str, Any], mutation: str
) -> None:
    changed = copy.deepcopy(record)
    if mutation == "path":
        changed["identity"]["path"] = "tests/unapproved_public_metadata.py"
    elif mutation == "path_swap":
        changed["identity"]["path"] = next(
            row["identity"]["path"]
            for row in _OBSERVED_PUBLIC_SOURCE_METADATA_RECORDS
            if row["identity"]["path"] != record["identity"]["path"]
        )
    elif mutation == "detector":
        changed["identity"]["type"] = "Base64 High Entropy String"
    elif mutation == "digest":
        changed["identity"]["hashed_secret_bytes"][0] ^= 1
    elif mutation == "category":
        changed["category"] = "documented_crypto_test_vector"
    elif mutation == "owner":
        changed["owner"] = "Different Reviewer"
    elif mutation == "review_date":
        changed["reviewed_on"] = "2026-10-23"
    elif mutation == "evidence":
        changed["evidence"] = "public metadata; not credential material"
    elif mutation == "pending":
        changed["approval_status"] = "pending_owner_review"
    else:
        assert mutation == "expiry_extension"
        changed["expires_on"] = "2027-01-11"
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(changed), today=verifier.date(2026, 10, 24)
        )


@pytest.mark.parametrize("record", _OBSERVED_PUBLIC_SOURCE_METADATA_RECORDS)
def test_observed_public_metadata_rejects_expiry_duplicate_and_extra_identity(
    record: dict[str, Any],
) -> None:
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(copy.deepcopy(record)),
            today=verifier.date(2027, 1, 11),
        )
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(copy.deepcopy(record), copy.deepcopy(record)),
            today=verifier.date(2026, 10, 24),
        )
    extra = copy.deepcopy(record)
    extra["identity"]["hashed_secret_bytes"] = list(range(20))
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(copy.deepcopy(record), extra),
            today=verifier.date(2026, 10, 24),
        )


def test_public_git_blob_catalog_proof_preserves_all_327_prior_records() -> None:
    policy = _reviewed_pre_retirement_dispositions()
    test_observed_public_metadata_policy_preserves_all_325_prior_records()
    assert len(policy["records"]) == 505
    assert policy["records"][327:328] == _PUBLIC_GIT_BLOB_APPROVED_RECORDS[4:5]
    assert len(_PUBLIC_GIT_BLOB_APPROVED_RECORDS[4:5]) == 1
    rebound = _PUBLIC_GIT_BLOB_APPROVED_RECORDS[4]
    assert rebound["identity"]["path"] == (
        "tests/helpers/migration_148642dd1207_trace.py"
    )
    assert tuple(rebound["identity"]["hashed_secret_bytes"]) not in {
        tuple(record["identity"]["hashed_secret_bytes"])
        for record in _PUBLIC_GIT_BLOB_APPROVED_RECORDS[:4]
    }


def test_public_git_blob_fixture_rebind_preserves_all_328_prior_records() -> None:
    policy = _reviewed_pre_retirement_dispositions()
    test_public_git_blob_catalog_proof_preserves_all_327_prior_records()
    assert len(policy["records"]) == 505
    assert policy["records"][328:329] == _PUBLIC_GIT_BLOB_APPROVED_RECORDS[5:6]
    assert len(_PUBLIC_GIT_BLOB_APPROVED_RECORDS[5:6]) == 1
    rebound = _PUBLIC_GIT_BLOB_APPROVED_RECORDS[5]
    assert (
        rebound["identity"]["path"]
        == (_PUBLIC_GIT_BLOB_APPROVED_RECORDS[1]["identity"]["path"])
    )
    assert tuple(rebound["identity"]["hashed_secret_bytes"]) not in {
        tuple(record["identity"]["hashed_secret_bytes"])
        for record in _PUBLIC_GIT_BLOB_APPROVED_RECORDS[:5]
    }


_PUBLIC_ALEMBIC_REVISION_RECORD = json.loads(
    (
        Path(__file__).resolve().parents[1]
        / "tests/fixtures/public-alembic-revision-disposition.json"
    ).read_text(encoding="utf-8")
)["records"][0]


def _public_revision_calls(source: str) -> tuple[ast.With, list[ast.Call]]:
    functions = [
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef)
        and node.name == "test_groups_successors_do_not_require_the_duplicate_id_index"
    ]
    assert len(functions) == 1
    assert len(functions[0].body) == 2
    assert isinstance(functions[0].body[0], ast.Expr)
    assert isinstance(functions[0].body[0].value, ast.Constant)
    assert isinstance(functions[0].body[0].value.value, str)
    scenario = functions[0].body[1]
    assert isinstance(scenario, ast.With) and len(scenario.items) == 1
    context = scenario.items[0].context_expr
    assert isinstance(context, ast.Call)
    assert isinstance(context.func, ast.Name)
    assert context.func.id == "_owned_migration_scenario"
    assert len(context.args) == 1 and not context.keywords
    assert isinstance(context.args[0], ast.Name)
    assert context.args[0].id == "migration_postgres"
    assert isinstance(scenario.items[0].optional_vars, ast.Name)
    assert scenario.items[0].optional_vars.id == "urls"
    calls = [
        node.value
        for node in scenario.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and isinstance(node.value.func.value, ast.Name)
        and node.value.func.value.id == "command"
        and node.value.func.attr == "upgrade"
    ]
    assert len(calls) == 4
    for call in calls:
        assert len(call.args) == 2 and not call.keywords
        assert isinstance(call.args[0], ast.Name) and call.args[0].id == "config"
        assert isinstance(call.args[1], ast.Constant)
        assert isinstance(call.args[1].value, str)
    return scenario, calls


def _revision_assignments(source: str) -> dict[str, str]:
    result = {}
    for node in ast.parse(source).body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name) and target.id in {
                "revision",
                "down_revision",
            }:
                assert target.id not in result
                assert isinstance(node.value, ast.Constant)
                assert isinstance(node.value.value, str)
                result[target.id] = node.value.value
    assert set(result) == {"revision", "down_revision"}
    return result


def _assert_public_revision_source_binding(
    source: str, *, revision_source: str | None = None
) -> tuple[int, ...]:
    _, calls = _public_revision_calls(source)
    target = calls[2].args[1].value
    assert re.fullmatch(r"[0-9a-f]{12}", target)
    # Shape alone never authorizes a value: require the observed exact identity.
    digest = tuple(hashlib.sha1(target.encode("ascii"), usedforsecurity=False).digest())
    assert digest == tuple(
        _PUBLIC_ALEMBIC_REVISION_RECORD["identity"]["hashed_secret_bytes"]
    )
    definition = f"alembic/versions/{target}_fix_groups_id_sequence.py"
    assert definition in _PRE_SQUASH_SOURCE_BLOBS
    metadata = _revision_assignments(
        _pre_squash_source_text(definition)
        if revision_source is None
        else revision_source
    )
    assert metadata["revision"] == target
    assert metadata["down_revision"] == calls[1].args[1].value
    return digest


def test_public_alembic_revision_current_source_has_exact_policy_identity() -> None:
    record = _PUBLIC_ALEMBIC_REVISION_RECORD
    source = _pre_squash_source_text(record["identity"]["path"])
    _assert_public_revision_source_binding(source)
    policy = _reviewed_pre_retirement_dispositions()
    assert record in policy["records"]


def test_public_alembic_revision_policy_preserves_all_329_prior_records() -> None:
    policy = _reviewed_pre_retirement_dispositions()
    test_public_git_blob_fixture_rebind_preserves_all_328_prior_records()
    assert len(policy["records"]) == 505
    assert policy["records"][329:330] == [_PUBLIC_ALEMBIC_REVISION_RECORD]


def test_public_alembic_revision_accepts_only_its_exact_record_without_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    record = _PUBLIC_ALEMBIC_REVISION_RECORD
    identity = record["identity"]
    expected = verifier.FindingIdentity(
        identity["path"],
        identity["type"],
        bytes(identity["hashed_secret_bytes"]).hex(),
        1,
    )
    assert _nov13_verify_dispositions(
        _disposition_document(copy.deepcopy(record)),
        today=verifier.date(2026, 10, 24),
    ) == {expected}


@pytest.mark.parametrize(
    "mutation",
    [
        "path",
        "detector",
        "digest",
        "category",
        "integrity_category",
        "digest_at_other_path",
        "unknown_digest_at_reserved_path",
        "owner",
        "review_date",
        "evidence",
        "pending",
        "expiry_extension",
    ],
)
def test_public_alembic_revision_rejects_changed_scope_or_approval(
    mutation: str,
) -> None:
    changed = copy.deepcopy(_PUBLIC_ALEMBIC_REVISION_RECORD)
    if mutation == "path":
        changed["identity"]["path"] = "tests/unapproved_revision_target.py"
    elif mutation == "detector":
        changed["identity"]["type"] = "Base64 High Entropy String"
    elif mutation == "digest":
        changed["identity"]["hashed_secret_bytes"][0] ^= 1
    elif mutation == "category":
        changed["category"] = "documented_crypto_test_vector"
    elif mutation == "integrity_category":
        changed["category"] = "public_integrity_digest"
    elif mutation == "digest_at_other_path":
        changed["identity"]["path"] = "tests/unapproved_revision_target.py"
        changed["category"] = "public_integrity_digest"
    elif mutation == "unknown_digest_at_reserved_path":
        changed["identity"]["hashed_secret_bytes"][0] ^= 1
        changed["category"] = "public_integrity_digest"
    elif mutation == "owner":
        changed["owner"] = "Different Reviewer"
    elif mutation == "review_date":
        changed["reviewed_on"] = "2026-10-23"
    elif mutation == "evidence":
        changed["evidence"] = "public revision; not credential material"
    elif mutation == "pending":
        changed["approval_status"] = "pending_owner_review"
    else:
        assert mutation == "expiry_extension"
        changed["expires_on"] = "2027-01-11"
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(changed), today=verifier.date(2026, 10, 24)
        )


def test_public_alembic_revision_rejects_expiry_duplicate_and_extra_identity() -> None:
    record = _PUBLIC_ALEMBIC_REVISION_RECORD
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(copy.deepcopy(record)),
            today=verifier.date(2027, 1, 11),
        )
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(copy.deepcopy(record), copy.deepcopy(record)),
            today=verifier.date(2026, 10, 24),
        )
    extra = copy.deepcopy(record)
    extra["identity"]["hashed_secret_bytes"] = list(range(20))
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(copy.deepcopy(record), extra),
            today=verifier.date(2026, 10, 24),
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "changed_target",
        "dynamic_target",
        "different_call",
        "duplicate_call",
        "renamed_test",
        "nested_upgrade",
    ],
)
def test_public_alembic_revision_source_binding_rejects_changed_consumer(
    mutation: str,
) -> None:
    source = _pre_squash_source_text(
        _PUBLIC_ALEMBIC_REVISION_RECORD["identity"]["path"]
    )
    _assert_public_revision_source_binding(source)
    tree = ast.parse(source)
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "test_groups_successors_do_not_require_the_duplicate_id_index"
    )
    calls = sorted(
        (
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "command"
            and node.func.attr == "upgrade"
        ),
        key=lambda node: node.lineno,
    )
    scenario = function.body[1]
    sequence_index = next(
        index
        for index, node in enumerate(scenario.body)
        if isinstance(node, ast.Expr) and node.value is calls[2]
    )
    target = calls[2].args[1]
    if mutation == "changed_target":
        target.value = "0" * len(target.value)
    elif mutation == "dynamic_target":
        value = target.value
        calls[2].args[1] = ast.BinOp(
            left=ast.Constant(value=value[:6]),
            op=ast.Add(),
            right=ast.Constant(value=value[6:]),
        )
    elif mutation == "different_call":
        calls[2].func.value.id = "unrelated"
    elif mutation == "duplicate_call":
        function.body.append(ast.Expr(value=copy.deepcopy(calls[2])))
    elif mutation == "renamed_test":
        function.name = "test_unreviewed_revision_use"
    else:
        assert mutation == "nested_upgrade"
        scenario.body[sequence_index] = ast.If(
            test=ast.Constant(value=False),
            body=[scenario.body[sequence_index]],
            orelse=[],
        )
    changed = ast.unparse(ast.fix_missing_locations(tree))
    with pytest.raises(AssertionError):
        _assert_public_revision_source_binding(changed)


@pytest.mark.parametrize("field", ["revision", "down_revision"])
def test_public_alembic_revision_source_binding_rejects_changed_definition(
    field: str,
) -> None:
    source = _pre_squash_source_text(
        _PUBLIC_ALEMBIC_REVISION_RECORD["identity"]["path"]
    )
    _assert_public_revision_source_binding(source)
    _, calls = _public_revision_calls(source)
    target = calls[2].args[1].value
    tree = ast.parse(
        _pre_squash_source_text(f"alembic/versions/{target}_fix_groups_id_sequence.py")
    )
    changed = 0
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if any(
            isinstance(target, ast.Name) and target.id == field for target in targets
        ):
            node.value = ast.Constant(value="0" * 12)
            changed += 1
    assert changed == 1
    with pytest.raises(AssertionError):
        _assert_public_revision_source_binding(
            source, revision_source=ast.unparse(tree)
        )


def test_public_git_blob_index_rebind_preserves_all_330_prior_records() -> None:
    policy = _reviewed_pre_retirement_dispositions()
    test_public_alembic_revision_policy_preserves_all_329_prior_records()
    assert len(policy["records"]) == 505
    assert policy["records"][330:331] == _PUBLIC_GIT_BLOB_APPROVED_RECORDS[6:7]
    assert len(_PUBLIC_GIT_BLOB_APPROVED_RECORDS[6:7]) == 1
    rebound = _PUBLIC_GIT_BLOB_APPROVED_RECORDS[6]
    assert rebound["identity"]["path"] == (
        "tests/helpers/migration_148642dd1207_trace.py"
    )
    assert tuple(rebound["identity"]["hashed_secret_bytes"]) not in {
        tuple(record["identity"]["hashed_secret_bytes"])
        for record in _PUBLIC_GIT_BLOB_APPROVED_RECORDS[:6]
    }


def test_public_git_blob_index_assertion_preserves_all_331_prior_records() -> None:
    policy = _reviewed_pre_retirement_dispositions()
    test_public_git_blob_index_rebind_preserves_all_330_prior_records()
    assert len(policy["records"]) == 505
    assert policy["records"][331:332] == _PUBLIC_GIT_BLOB_APPROVED_RECORDS[7:8]
    assert len(_PUBLIC_GIT_BLOB_APPROVED_RECORDS[7:8]) == 1
    rebound = _PUBLIC_GIT_BLOB_APPROVED_RECORDS[7]
    assert (
        rebound["identity"]["path"]
        == (_PUBLIC_GIT_BLOB_APPROVED_RECORDS[1]["identity"]["path"])
    )
    assert tuple(rebound["identity"]["hashed_secret_bytes"]) not in {
        tuple(record["identity"]["hashed_secret_bytes"])
        for record in _PUBLIC_GIT_BLOB_APPROVED_RECORDS[:7]
    }


_PUBLIC_COMPILER_GOLDEN_RECORDS = json.loads(
    (
        Path(__file__).resolve().parents[1]
        / "tests/fixtures/public-compiler-golden-dispositions.json"
    ).read_text(encoding="utf-8")
)["records"]
_PUBLIC_COMPILER_GOLDEN_FIELDS = (
    "sourceSha",
    "compilerIntegrity",
    "compilerBundleSha256",
    "formatterEntrySha256",
)


def _assert_public_compiler_golden_source_binding(
    golden: dict[str, Any], lock: dict[str, Any]
) -> None:
    assert len(_PUBLIC_COMPILER_GOLDEN_RECORDS) == 4
    assert golden["kind"] == "react-compiler-legacy-baseline"
    assert golden["schemaVersion"] == 1
    assert golden["compilerVersion"] == "19.1.0-rc.2"
    assert golden["evidence"]["status"] == "legacy_baseline_not_fix_verification"
    assert golden["evidence"]["source"] == (
        "https://github.com/egorribun/university_ecosystem/"
        "actions/runs/40069691438/job/120802074003"
    )
    assert re.fullmatch(r"[0-9a-f]{40}", golden["sourceSha"])
    compiler = lock["packages"]["node_modules/eslint-plugin-react-compiler"]
    assert compiler["version"] == golden["compilerVersion"]
    assert compiler["integrity"] == golden["compilerIntegrity"]
    for index, field in enumerate(_PUBLIC_COMPILER_GOLDEN_FIELDS):
        record = _PUBLIC_COMPILER_GOLDEN_RECORDS[index]
        identity = record["identity"]
        assert identity["path"] == (
            "frontend/scripts/react-compiler-zod-compat/legacy-baseline.json"
        )
        assert identity["type"] == (
            "Base64 High Entropy String"
            if field == "compilerIntegrity"
            else "Hex High Entropy String"
        )
        assert record["category"] == (
            "public_package_integrity_metadata"
            if field == "compilerIntegrity"
            else "public_integrity_digest"
        )
        # Include the complete public literal, including the SRI algorithm prefix.
        digest = hashlib.sha1(
            golden[field].encode("utf-8"), usedforsecurity=False
        ).digest()
        assert list(digest) == identity["hashed_secret_bytes"]


def _public_compiler_golden_source() -> tuple[dict[str, Any], dict[str, Any]]:
    root = Path(__file__).resolve().parents[1]
    golden = json.loads(
        (root / _PUBLIC_COMPILER_GOLDEN_RECORDS[0]["identity"]["path"]).read_text(
            encoding="utf-8"
        )
    )
    lock = json.loads((root / "frontend/package-lock.json").read_text(encoding="utf-8"))
    return golden, lock


def test_public_compiler_golden_current_source_has_exact_policy_identities() -> None:
    golden, lock = _public_compiler_golden_source()
    _assert_public_compiler_golden_source_binding(golden, lock)
    policy = _reviewed_pre_retirement_dispositions()
    for record in _PUBLIC_COMPILER_GOLDEN_RECORDS:
        assert record in policy["records"]


def test_public_compiler_golden_policy_preserves_all_332_prior_records() -> None:
    policy = _reviewed_pre_retirement_dispositions()
    test_public_git_blob_index_assertion_preserves_all_331_prior_records()
    assert len(policy["records"]) == 505
    assert policy["records"][332:336] == _PUBLIC_COMPILER_GOLDEN_RECORDS


@pytest.mark.parametrize("index", range(4), ids=_PUBLIC_COMPILER_GOLDEN_FIELDS)
def test_public_compiler_golden_accepts_only_exact_record_without_source(
    index: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    record = _PUBLIC_COMPILER_GOLDEN_RECORDS[index]
    identity = record["identity"]
    expected = verifier.FindingIdentity(
        identity["path"],
        identity["type"],
        bytes(identity["hashed_secret_bytes"]).hex(),
        1,
    )
    assert _nov13_verify_dispositions(
        _disposition_document(copy.deepcopy(record)),
        today=verifier.date(2026, 10, 24),
    ) == {expected}


@pytest.mark.parametrize("index", range(4), ids=_PUBLIC_COMPILER_GOLDEN_FIELDS)
@pytest.mark.parametrize(
    "mutation",
    [
        "path",
        "detector",
        "digest",
        "category",
        "owner",
        "review_date",
        "evidence",
        "pending",
        "expiry_extension",
        "digest_at_other_path",
        "unknown_digest_at_reserved_path",
    ],
)
def test_public_compiler_golden_rejects_changed_scope_or_approval(
    index: int, mutation: str
) -> None:
    changed = copy.deepcopy(_PUBLIC_COMPILER_GOLDEN_RECORDS[index])
    if mutation == "path":
        changed["identity"]["path"] = "tests/unapproved_compiler_golden.json"
    elif mutation == "detector":
        changed["identity"]["type"] = (
            "Hex High Entropy String"
            if changed["identity"]["type"] == "Base64 High Entropy String"
            else "Base64 High Entropy String"
        )
    elif mutation == "digest":
        changed["identity"]["hashed_secret_bytes"][0] ^= 1
    elif mutation == "category":
        changed["category"] = "documented_crypto_test_vector"
    elif mutation == "owner":
        changed["owner"] = "Different Reviewer"
    elif mutation == "review_date":
        changed["reviewed_on"] = "2026-10-23"
    elif mutation == "evidence":
        changed["evidence"] = "public checksum; not credential material"
    elif mutation == "pending":
        changed["approval_status"] = "pending_owner_review"
    elif mutation == "expiry_extension":
        changed["expires_on"] = "2027-01-11"
    elif mutation == "digest_at_other_path":
        changed["identity"]["path"] = "tests/unapproved_compiler_golden.json"
        changed["identity"]["type"] = "Hex High Entropy String"
        changed["category"] = "public_integrity_digest"
    else:
        assert mutation == "unknown_digest_at_reserved_path"
        changed["identity"]["hashed_secret_bytes"][0] ^= 1
        changed["identity"]["type"] = "Hex High Entropy String"
        changed["category"] = "public_integrity_digest"
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(changed), today=verifier.date(2026, 10, 24)
        )


def test_public_compiler_golden_rejects_expiry_duplicate_and_extra_identity() -> None:
    for record in _PUBLIC_COMPILER_GOLDEN_RECORDS:
        with pytest.raises(verifier.BaselineArtifactError):
            _nov13_verify_dispositions(
                _disposition_document(copy.deepcopy(record)),
                today=verifier.date(2027, 1, 11),
            )
        with pytest.raises(verifier.BaselineArtifactError):
            _nov13_verify_dispositions(
                _disposition_document(copy.deepcopy(record), copy.deepcopy(record)),
                today=verifier.date(2026, 10, 24),
            )
        extra = copy.deepcopy(record)
        extra["identity"]["hashed_secret_bytes"] = list(range(20))
        with pytest.raises(verifier.BaselineArtifactError):
            _nov13_verify_dispositions(
                _disposition_document(copy.deepcopy(record), extra),
                today=verifier.date(2026, 10, 24),
            )


@pytest.mark.parametrize(
    "mutation",
    [
        *_PUBLIC_COMPILER_GOLDEN_FIELDS,
        "kind",
        "status",
        "capture_source",
        "lock_integrity",
    ],
)
def test_public_compiler_golden_source_binding_rejects_changed_metadata(
    mutation: str,
) -> None:
    golden, lock = _public_compiler_golden_source()
    _assert_public_compiler_golden_source_binding(golden, lock)
    if mutation in _PUBLIC_COMPILER_GOLDEN_FIELDS:
        golden[mutation] = "0" * len(golden[mutation])
    elif mutation == "kind":
        golden["kind"] = "unreviewed-compiler-baseline"
    elif mutation == "status":
        golden["evidence"]["status"] = "fix_verified"
    elif mutation == "capture_source":
        golden["evidence"]["source"] = "https://example.test/unreviewed"
    else:
        assert mutation == "lock_integrity"
        lock["packages"]["node_modules/eslint-plugin-react-compiler"]["integrity"] = (
            "unreviewed-integrity"
        )
    with pytest.raises(AssertionError):
        _assert_public_compiler_golden_source_binding(golden, lock)


_NODE_REACT_COMPILER_POLICY_PREFIX_SHA256 = (
    68,
    67,
    36,
    254,
    182,
    104,
    208,
    67,
    219,
    29,
    107,
    147,
    163,
    226,
    1,
    79,
    19,
    210,
    186,
    161,
    103,
    31,
    39,
    40,
    77,
    63,
    248,
    203,
    0,
    126,
    108,
    229,
)


def _node_react_compiler_source_rows(
    root: Path,
) -> list[tuple[str, str, str, str]]:
    generator = (
        root / "frontend/scripts/generate-react-compiler-final-lock-candidate.mjs"
    ).read_text(encoding="utf-8")
    candidate_test = (
        root / "frontend/scripts/generate-react-compiler-final-lock-candidate.test.mjs"
    ).read_text(encoding="utf-8")
    facade_test = (
        root / "frontend/scripts/react-compiler-zod-compat.test.mjs"
    ).read_text(encoding="utf-8")
    observations = json.loads(
        (
            root / "frontend/scripts/react-compiler-zod-compat.postgraph-errors.json"
        ).read_text(encoding="utf-8")
    )

    def capture(pattern: str, source: str) -> str:
        match = re.search(pattern, source)
        assert match is not None
        return match.group(1)

    archive_sri = capture(r'const ARCHIVE_INTEGRITY =\s*\n\s*"([^"]+)"', generator)
    archive_sha256 = capture(r'const ARCHIVE_SHA256 = "([0-9a-f]{64})"', generator)
    git_head = capture(r'gitHead:\s*"([0-9a-f]{40})"', candidate_test)
    facade_sri = capture(r'const FACADE_INTEGRITY =\s*\n\s*"([^"]+)"', facade_test)
    facade_sha256 = capture(r'const FACADE_SHA256 = "([0-9a-f]{64})"', facade_test)
    formatter = observations["formatter"]
    return [
        (
            "frontend/scripts/generate-react-compiler-final-lock-candidate.mjs",
            "Base64 High Entropy String",
            archive_sri,
            "public_package_integrity_metadata",
        ),
        (
            "frontend/scripts/generate-react-compiler-final-lock-candidate.mjs",
            "Hex High Entropy String",
            archive_sha256,
            "public_integrity_digest",
        ),
        (
            "frontend/scripts/generate-react-compiler-final-lock-candidate.test.mjs",
            "Hex High Entropy String",
            git_head,
            "public_integrity_digest",
        ),
        (
            "frontend/scripts/react-compiler-zod-compat.postgraph-errors.json",
            "Hex High Entropy String",
            formatter["entrySha256"],
            "public_integrity_digest",
        ),
        (
            "frontend/scripts/react-compiler-zod-compat.postgraph-errors.json",
            "Base64 High Entropy String",
            formatter["integrity"],
            "public_package_integrity_metadata",
        ),
        (
            "frontend/scripts/react-compiler-zod-compat.test.mjs",
            "Base64 High Entropy String",
            facade_sri,
            "public_package_integrity_metadata",
        ),
        (
            "frontend/scripts/react-compiler-zod-compat.test.mjs",
            "Hex High Entropy String",
            facade_sha256,
            "public_integrity_digest",
        ),
    ]


def _node_react_compiler_source_identity_categories(
    root: Path,
) -> dict[tuple[str, str, tuple[int, ...]], str]:
    return {
        (
            path,
            finding_type,
            tuple(hashlib.sha1(value.encode("utf-8"), usedforsecurity=False).digest()),
        ): category
        for path, finding_type, value, category in _node_react_compiler_source_rows(
            root
        )
    }


def _node_react_compiler_reviewed_record(
    identity: tuple[str, str, tuple[int, ...]], category: str
) -> dict[str, Any]:
    """Build an ephemeral validator fixture, not a policy approval."""
    record = _reviewed_exact_disposition(*identity, category)
    record["evidence"] = "; ".join(
        verifier._NODE_REACT_COMPILER_PUBLIC_METADATA_EVIDENCE_MARKERS[identity]
    )
    record["owner"] = "egorribun"
    record["reviewed_on"] = "2026-10-25"
    return record


def _node_react_compiler_record_identity(
    record: dict[str, Any],
) -> tuple[str, str, tuple[int, ...]]:
    identity = record["identity"]
    return (
        identity["path"],
        identity["type"],
        tuple(identity["hashed_secret_bytes"]),
    )


def _node_react_compiler_record_evidence_markers(
    record: dict[str, Any],
) -> tuple[str, ...]:
    return verifier._NODE_REACT_COMPILER_PUBLIC_METADATA_EVIDENCE_MARKERS[
        _node_react_compiler_record_identity(record)
    ]


def test_node_react_compiler_public_metadata_is_source_bound_and_exact() -> None:
    root = Path(__file__).resolve().parents[1]
    expected = _node_react_compiler_source_identity_categories(root)
    assert len(expected) == 7
    assert expected == (
        verifier._NODE_REACT_COMPILER_PUBLIC_METADATA_CATEGORY_BY_IDENTITY
    )
    assert verifier._NODE_REACT_COMPILER_DIGEST_COLLISION_EXCEPTIONS == {
        verifier._ZOD_PUBLIC_UPSTREAM_SOURCE_IDENTITY
    }
    assert {
        (identity[0], identity[1])
        for identity, category in expected.items()
        if category == "public_package_integrity_metadata"
    } <= verifier._FALSE_POSITIVE_NON_HEX_CATEGORY_PATH_TYPES[
        "public_package_integrity_metadata"
    ]

    generator = (
        root / "frontend/scripts/generate-react-compiler-final-lock-candidate.mjs"
    ).read_text(encoding="utf-8")
    facade_test = (
        root / "frontend/scripts/react-compiler-zod-compat.test.mjs"
    ).read_text(encoding="utf-8")
    candidate_test = (
        root / "frontend/scripts/generate-react-compiler-final-lock-candidate.test.mjs"
    ).read_text(encoding="utf-8")
    observations = json.loads(
        (
            root / "frontend/scripts/react-compiler-zod-compat.postgraph-errors.json"
        ).read_text(encoding="utf-8")
    )
    lock = json.loads((root / "frontend/package-lock.json").read_text(encoding="utf-8"))

    def capture(pattern: str, source: str) -> str:
        match = re.search(pattern, source)
        assert match is not None
        return match.group(1)

    archive_sri = capture(r'const ARCHIVE_INTEGRITY =\s*\n\s*"([^"]+)"', generator)
    archive_sha256 = capture(r'const ARCHIVE_SHA256 = "([0-9a-f]{64})"', generator)
    facade_sri = capture(r'const FACADE_INTEGRITY =\s*\n\s*"([^"]+)"', facade_test)
    facade_sha256 = capture(r'const FACADE_SHA256 = "([0-9a-f]{64})"', facade_test)
    archive = (
        root / "frontend/vendor/react-compiler-zod-compat-1.0.0.tgz"
    ).read_bytes()
    assert hashlib.sha256(archive).hexdigest() == archive_sha256 == facade_sha256
    computed_sri = "sha512-" + base64.b64encode(
        hashlib.sha512(archive).digest()
    ).decode("ascii")
    assert computed_sri == archive_sri == facade_sri
    local_package = lock["packages"][
        "node_modules/@university-ecosystem/react-compiler-zod-compat"
    ]
    assert local_package["version"] == "1.0.0"
    assert local_package["resolved"] == (
        "file:vendor/react-compiler-zod-compat-1.0.0.tgz"
    )
    assert local_package["integrity"] == computed_sri

    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as package:
        members = [member for member in package.getmembers() if member.isfile()]
        assert {member.name for member in members} == {
            "package/LICENSE",
            "package/README.md",
            "package/index.cjs",
            "package/package.json",
        }
        for member in members:
            relative = Path(member.name.removeprefix("package/"))
            payload = package.extractfile(member)
            assert payload is not None
            assert (
                payload.read()
                == (
                    root / "frontend/scripts/react-compiler-zod-compat" / relative
                ).read_bytes()
            )

    formatter = observations["formatter"]
    locked_formatter = lock["packages"]["node_modules/zod-validation-error"]
    assert formatter["name"] == "zod-validation-error"
    assert formatter["version"] == locked_formatter["version"] == "4.0.2"
    assert formatter["resolved"] == locked_formatter["resolved"]
    assert formatter["integrity"] == locked_formatter["integrity"]
    assert ".update(readFileSync(formatterEntryPath))" in facade_test
    assert (
        "assert.equal(formatterEntrySha256, "
        "postgraphSchemaObservations.formatter.entrySha256)"
    ) in facade_test

    fixture_git_head = re.search(r'gitHead:\s*"([0-9a-f]{40})"', candidate_test)
    source_generator = (
        root / "frontend/scripts/generate-zod-root-lock-candidate.mjs"
    ).read_text(encoding="utf-8")
    expected_git_head = re.search(
        r'EXPECTED_ZOD_SOURCE_SHA\s*=\s*"([0-9a-f]{40})"', source_generator
    )
    assert fixture_git_head is not None and expected_git_head is not None
    assert fixture_git_head.group(1) == expected_git_head.group(1)


# Conditional integration guard for the post-owner-approval policy state.
def test_node_compiler_policy_appends_seven_and_preserves_337_prefix() -> None:
    root = Path(__file__).resolve().parents[1]
    policy = _reviewed_pre_retirement_dispositions()
    records = policy["records"]
    assert len(records) == 505
    prefix = json.dumps(
        records[:337], sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    assert hashlib.sha256(prefix).digest() == bytes(
        _NODE_REACT_COMPILER_POLICY_PREFIX_SHA256
    )

    expected = _node_react_compiler_source_identity_categories(root)
    suffix = records[338:345]
    actual = {
        (
            record["identity"]["path"],
            record["identity"]["type"],
            tuple(record["identity"]["hashed_secret_bytes"]),
        ): record["category"]
        for record in suffix
    }
    assert actual == expected
    assert all(record["approval_status"] == "approved" for record in suffix)
    assert all(record["owner"] == "egorribun" for record in suffix)
    assert all(record["reviewed_on"] == "2026-10-25" for record in suffix)
    assert all(record["expires_on"] <= "2027-01-10" for record in suffix)
    assert all(
        all(
            marker.casefold() in record["evidence"].casefold()
            for marker in _node_react_compiler_record_evidence_markers(record)
        )
        for record in suffix
    )
    validated = _nov13_verify_dispositions(
        {
            "schema_version": policy["schema_version"],
            "records": _nov4_current_view(policy["records"][:347]),
        },
        today=verifier.date(2026, 10, 26),
    )
    expected_findings = {
        verifier.FindingIdentity(path, finding_type, bytes(digest).hex(), 1)
        for path, finding_type, digest in expected
    }
    assert expected_findings <= validated


def test_node_react_compiler_policy_rejects_near_misses_and_pending_records() -> None:
    root = Path(__file__).resolve().parents[1]
    expected = _node_react_compiler_source_identity_categories(root)
    today = verifier.date(2026, 10, 25)
    for identity, category in expected.items():
        valid = _node_react_compiler_reviewed_record(identity, category)
        finding = verifier.FindingIdentity(
            identity[0], identity[1], bytes(identity[2]).hex(), 1
        )
        assert _nov13_verify_dispositions(
            _disposition_document(copy.deepcopy(valid)), today=today
        ) == {finding}

        mutations = []
        changed_path = copy.deepcopy(valid)
        changed_path["identity"]["path"] = "tests/unreviewed-node-metadata.py"
        mutations.append(changed_path)
        changed_type = copy.deepcopy(valid)
        changed_type["identity"]["type"] = "Secret Keyword"
        mutations.append(changed_type)
        changed_digest = copy.deepcopy(valid)
        changed_digest["identity"]["hashed_secret_bytes"][0] ^= 1
        mutations.append(changed_digest)
        changed_category = copy.deepcopy(valid)
        changed_category["category"] = (
            "public_integrity_digest"
            if category == "public_package_integrity_metadata"
            else "public_package_integrity_metadata"
        )
        mutations.append(changed_category)
        missing_evidence = copy.deepcopy(valid)
        missing_evidence["evidence"] = "not credential material"
        mutations.append(missing_evidence)
        owner_placeholder = copy.deepcopy(valid)
        owner_placeholder["owner"] = "PENDING_OWNER_REVIEW"
        mutations.append(owner_placeholder)
        future_review = copy.deepcopy(valid)
        future_review["reviewed_on"] = "2026-10-26"
        mutations.append(future_review)
        excessive_expiry = copy.deepcopy(valid)
        excessive_expiry["reviewed_on"] = "2026-10-25"
        excessive_expiry["expires_on"] = "2027-01-11"
        mutations.append(excessive_expiry)
        pending = copy.deepcopy(valid)
        pending["approval_status"] = "pending_owner_review"
        mutations.append(pending)
        unknown_digest_at_reserved_path = copy.deepcopy(valid)
        unknown_digest_at_reserved_path["identity"]["hashed_secret_bytes"][0] ^= 1
        mutations.append(unknown_digest_at_reserved_path)
        moved_digest = copy.deepcopy(valid)
        moved_digest["identity"]["path"] = "tests/unreviewed-node-metadata.py"
        mutations.append(moved_digest)

        for changed in mutations:
            with pytest.raises(verifier.BaselineArtifactError):
                _nov13_verify_dispositions(_disposition_document(changed), today=today)

        with pytest.raises(verifier.BaselineArtifactError):
            _nov13_verify_dispositions(
                _disposition_document(copy.deepcopy(valid), copy.deepcopy(valid)),
                today=today,
            )


_LIVE_PRIVATE_FIELD_RECORD = json.loads(
    (
        Path(__file__).resolve().parents[1]
        / "tests/fixtures/live-registration-private-field-disposition.json"
    ).read_text(encoding="utf-8")
)["records"][0]


def _live_private_field_fixture_nodes(
    source: str,
) -> tuple[ast.Module, ast.FunctionDef, ast.Dict]:
    tree = ast.parse(source)
    functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name
        == "test_live_reset_registration_v2_rejects_private_fields_and_wrong_types"
    ]
    assert len(functions) == 1
    function = functions[0]

    def assignment(name: str) -> ast.Assign:
        nodes = [
            node
            for node in function.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == name
                for target in node.targets
            )
        ]
        assert len(nodes) == 1
        return nodes[0]

    expressions = {
        "parser": (
            'getattr(live_stand, "_live_playwright_reset_registration_v2", None)'
        ),
        "valid": "_reset_registration_v2_record()",
        "output": ('"".join(_reset_registration_v2_row(record) for record in invalid)'),
    }
    for name, expression in expressions.items():
        assert ast.dump(assignment(name).value) == ast.dump(
            ast.parse(expression, mode="eval").body
        )
    rejection = ast.dump(ast.parse("parser(output) == []", mode="eval").body)
    assert (
        sum(
            isinstance(node, ast.Assert) and ast.dump(node.test) == rejection
            for node in function.body
        )
        == 1
    )
    invalid_assignment = assignment("invalid")
    assert len(invalid_assignment.targets) == 1
    invalid = invalid_assignment.value
    assert isinstance(invalid, ast.List)
    output_refs = {
        node
        for node in ast.walk(assignment("output").value)
        if isinstance(node, ast.Name) and node.id == "invalid"
    }
    assert len(output_refs) == 1
    parents = {
        child: parent
        for parent in ast.walk(function)
        for child in ast.iter_child_nodes(parent)
    }
    # Keep the fixture in the corpus: reject aliases, deletion and destructive
    # methods while retaining the real test's append-only expansion loops.
    for node in ast.walk(function):
        if not isinstance(node, ast.Name) or node.id != "invalid":
            continue
        if node in invalid_assignment.targets or node in output_refs:
            continue
        attribute = parents[node]
        assert isinstance(attribute, ast.Attribute) and attribute.value is node
        assert attribute.attr == "append"
        call = parents[attribute]
        assert isinstance(call, ast.Call) and call.func is attribute
        assert len(call.args) == 1 and not call.keywords
    fixtures = [
        node
        for node in invalid.elts
        if isinstance(node, ast.Dict)
        and any(
            isinstance(key, ast.Constant) and key.value == "password"
            for key in node.keys
        )
    ]
    assert len(fixtures) == 1
    fixture = fixtures[0]
    assert len(fixture.keys) == 2 and fixture.keys[0] is None
    assert isinstance(fixture.values[0], ast.Name)
    assert fixture.values[0].id == "valid"
    assert isinstance(fixture.keys[1], ast.Constant)
    assert fixture.keys[1].value == "password"
    value = fixture.values[1]
    assert isinstance(value, ast.Constant) and isinstance(value.value, str)
    digest = hashlib.sha1(value.value.encode("utf-8"), usedforsecurity=False).digest()
    assert list(digest) == _LIVE_PRIVATE_FIELD_RECORD["identity"]["hashed_secret_bytes"]
    assert (
        sum(
            isinstance(node, ast.Constant) and node.value == value.value
            for node in ast.walk(tree)
        )
        == 1
    )
    return tree, function, fixture


def test_live_private_field_current_source_has_exact_policy_identity() -> None:
    root = Path(__file__).resolve().parents[1]
    record = _LIVE_PRIVATE_FIELD_RECORD
    source = (root / record["identity"]["path"]).read_text(encoding="utf-8")
    _live_private_field_fixture_nodes(source)
    policy = _reviewed_pre_retirement_dispositions()
    assert record in policy["records"]


def test_live_private_field_policy_preserves_all_336_prior_records() -> None:
    policy = _reviewed_pre_retirement_dispositions()
    test_public_compiler_golden_policy_preserves_all_332_prior_records()
    assert len(policy["records"]) == 505
    assert policy["records"][336:337] == [_LIVE_PRIVATE_FIELD_RECORD]


def test_live_private_field_accepts_exact_record_without_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    record = _LIVE_PRIVATE_FIELD_RECORD
    identity = record["identity"]
    expected = verifier.FindingIdentity(
        identity["path"],
        identity["type"],
        bytes(identity["hashed_secret_bytes"]).hex(),
        1,
    )
    assert _nov13_verify_dispositions(
        _disposition_document(copy.deepcopy(record)),
        today=verifier.date(2026, 10, 24),
    ) == {expected}


@pytest.mark.parametrize(
    "mutation",
    [
        "path",
        "path_transplant",
        "detector",
        "digest",
        "category",
        "integrity_category",
        "unknown_digest_at_reserved_path",
        "owner",
        "review_date",
        "evidence",
        "pending",
        "expiry_extension",
    ],
)
def test_live_private_field_rejects_changed_scope_or_approval(mutation: str) -> None:
    changed = copy.deepcopy(_LIVE_PRIVATE_FIELD_RECORD)
    if mutation == "path":
        changed["identity"]["path"] = "tests/unapproved_private_field.py"
    elif mutation == "path_transplant":
        changed["identity"]["path"] = ".github/workflows/ci.yml"
    elif mutation == "detector":
        changed["identity"]["type"] = "Hex High Entropy String"
    elif mutation == "digest":
        changed["identity"]["hashed_secret_bytes"][0] ^= 1
    elif mutation == "category":
        changed["category"] = "source_contract_identifier"
    elif mutation == "integrity_category":
        changed["identity"]["type"] = "Hex High Entropy String"
        changed["category"] = "public_integrity_digest"
    elif mutation == "unknown_digest_at_reserved_path":
        changed["identity"]["hashed_secret_bytes"][0] ^= 1
        changed["identity"]["type"] = "Hex High Entropy String"
        changed["category"] = "public_integrity_digest"
    elif mutation == "owner":
        changed["owner"] = "Different Reviewer"
    elif mutation == "review_date":
        changed["reviewed_on"] = "2026-10-23"
    elif mutation == "evidence":
        changed["evidence"] = "synthetic test value; not credential material"
    elif mutation == "pending":
        changed["approval_status"] = "pending_owner_review"
    else:
        assert mutation == "expiry_extension"
        changed["expires_on"] = "2027-01-11"
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(changed), today=verifier.date(2026, 10, 24)
        )


def test_live_private_field_rejects_expiry_duplicate_and_extra_identity() -> None:
    record = _LIVE_PRIVATE_FIELD_RECORD
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(copy.deepcopy(record)),
            today=verifier.date(2027, 1, 11),
        )
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(copy.deepcopy(record), copy.deepcopy(record)),
            today=verifier.date(2026, 10, 24),
        )
    extra = copy.deepcopy(record)
    extra["identity"]["hashed_secret_bytes"] = list(range(20))
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(copy.deepcopy(record), extra),
            today=verifier.date(2026, 10, 24),
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "changed_value",
        "changed_field",
        "duplicate_fixture",
        "renamed_test",
        "different_serialization",
        "different_assertion",
        "inactive_fixture",
        "clear_corpus",
        "delete_fixture",
        "mutating_alias",
    ],
)
def test_live_private_field_source_binding_rejects_changed_usage(
    mutation: str,
) -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / _LIVE_PRIVATE_FIELD_RECORD["identity"]["path"]).read_text(
        encoding="utf-8"
    )
    tree, function, fixture = _live_private_field_fixture_nodes(source)
    assignments = {
        target.id: node
        for node in function.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    if mutation == "changed_value":
        fixture.values[1] = ast.Constant(value="changed-fixture")
    elif mutation == "changed_field":
        fixture.keys[1] = ast.Constant(value="unapprovedField")
    elif mutation == "duplicate_fixture":
        assignments["invalid"].value.elts.append(copy.deepcopy(fixture))
    elif mutation == "renamed_test":
        function.name = "test_unreviewed_private_field_use"
    elif mutation == "different_serialization":
        assignments["output"].value = ast.Constant(value="")
    elif mutation == "different_assertion":
        rejection = ast.dump(ast.parse("parser(output) == []", mode="eval").body)
        node = next(
            node
            for node in function.body
            if isinstance(node, ast.Assert) and ast.dump(node.test) == rejection
        )
        node.test.comparators[0].elts.append(ast.Constant(value=None))
    elif mutation == "inactive_fixture":
        assignments["invalid"].value.elts.remove(fixture)
        function.body.append(
            ast.If(
                test=ast.Constant(value=False),
                body=[ast.Expr(value=fixture)],
                orelse=[],
            )
        )
    else:
        position = function.body.index(assignments["output"])
        if mutation == "clear_corpus":
            statements = ast.parse("invalid.clear()").body
        elif mutation == "delete_fixture":
            index = assignments["invalid"].value.elts.index(fixture)
            statements = ast.parse(f"del invalid[{index}]").body
        else:
            assert mutation == "mutating_alias"
            statements = ast.parse("alias = invalid\nalias.clear()").body
        function.body[position:position] = statements
    changed = ast.unparse(ast.fix_missing_locations(tree))
    with pytest.raises(AssertionError):
        _live_private_field_fixture_nodes(changed)


def test_public_git_blob_sourcebinding_rebind_appends_one_exact_identity() -> None:
    policy = _reviewed_pre_retirement_dispositions()
    test_live_private_field_policy_preserves_all_336_prior_records()
    assert len(policy["records"]) == 505
    record = _PUBLIC_GIT_BLOB_APPROVED_RECORDS[8]
    assert policy["records"][337:338] == [record]
    assert record["identity"]["path"] == (
        "tests/helpers/migration_148642dd1207_trace.py"
    )
    assert "five-site" not in record["evidence"].casefold()
    assert "working tree based on c90e6163" in record["evidence"]
    assert (
        record["identity"]["path"],
        record["identity"]["type"],
        tuple(record["identity"]["hashed_secret_bytes"]),
    ) == verifier._PUBLIC_GIT_BLOB_SOURCEBINDING_REBIND_IDENTITY
    digest = _public_git_blob_source_identity(
        _pre_squash_source_text(record["identity"]["path"]),
        "SOURCE_GIT_BLOB",
        _pre_squash_source_bytes("alembic/versions/148642dd1207_fix_missing_tables.py"),
    )
    assert digest == tuple(record["identity"]["hashed_secret_bytes"])


def _aud247_squawk_public_checksum_record() -> dict[str, Any]:
    policy = _reviewed_pre_retirement_dispositions()
    identity = verifier._AUD247_SQUAWK_PUBLIC_CHECKSUM_IDENTITY
    matches = [
        record
        for record in policy["records"]
        if record["identity"]["path"] == identity[0]
        and record["identity"]["type"] == identity[1]
        and tuple(record["identity"]["hashed_secret_bytes"]) == identity[2]
    ]
    assert len(matches) == 1
    return copy.deepcopy(matches[0])


def test_aud247_squawk_public_checksum_identity_matches_source_literal() -> None:
    root = Path(__file__).resolve().parents[1]
    source_path = root / "tests/test_security_hardening_workflow_contract.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    checksum_assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "SQUAWK_SHA256"
            for target in node.targets
        )
    )
    assert isinstance(checksum_assignment.value, ast.Constant)
    checksum = checksum_assignment.value.value
    assert isinstance(checksum, str)
    source_identity = (
        "tests/test_security_hardening_workflow_contract.py",
        "Hex High Entropy String",
        tuple(hashlib.sha1(checksum.encode("ascii"), usedforsecurity=False).digest()),
    )
    assert source_identity == verifier._AUD247_SQUAWK_PUBLIC_CHECKSUM_IDENTITY


def test_aud247_squawk_public_checksum_accepts_only_exact_approved_record() -> None:
    record = _aud247_squawk_public_checksum_record()
    expected = verifier.FindingIdentity(
        record["identity"]["path"],
        record["identity"]["type"],
        bytes(record["identity"]["hashed_secret_bytes"]).hex(),
        1,
    )
    assert _nov13_verify_dispositions(
        _disposition_document(record), today=verifier.date(2026, 10, 26)
    ) == {expected}


@pytest.mark.parametrize(
    "mutation",
    [
        "path",
        "detector",
        "category",
        "evidence",
        "owner",
        "review_date",
        "pending",
        "expiry_extension",
    ],
)
def test_aud247_squawk_public_checksum_rejects_changed_scope_or_review(
    mutation: str,
) -> None:
    changed = _aud247_squawk_public_checksum_record()
    if mutation == "path":
        changed["identity"]["path"] = "tests/unrelated_contract.py"
    elif mutation == "detector":
        changed["identity"]["type"] = "Secret Keyword"
    elif mutation == "category":
        changed["category"] = "documented_crypto_test_vector"
    elif mutation == "evidence":
        changed["evidence"] = "public checksum; not credential material"
    elif mutation == "owner":
        changed["owner"] = "Different Reviewer"
    elif mutation == "review_date":
        changed["reviewed_on"] = "2026-10-25"
    elif mutation == "pending":
        changed["approval_status"] = "pending_owner_review"
    else:
        assert mutation == "expiry_extension"
        changed["expires_on"] = "2027-01-11"
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(changed), today=verifier.date(2026, 10, 26)
        )


def test_aud247_squawk_public_checksum_rejects_expiry_and_duplicate() -> None:
    record = _aud247_squawk_public_checksum_record()
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(copy.deepcopy(record)),
            today=verifier.date(2027, 1, 11),
        )
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(copy.deepcopy(record), copy.deepcopy(record)),
            today=verifier.date(2026, 10, 26),
        )


def test_aud247_guard_preserves_existing_same_path_type_identities() -> None:
    policy = _reviewed_pre_retirement_dispositions()
    identity = verifier._AUD247_SQUAWK_PUBLIC_CHECKSUM_IDENTITY
    same_path_type = [
        record
        for record in policy["records"]
        if record["identity"]["path"] == identity[0]
        and record["identity"]["type"] == identity[1]
    ]
    target_records = [
        record
        for record in same_path_type
        if tuple(record["identity"]["hashed_secret_bytes"]) == identity[2]
    ]
    assert len(target_records) <= 1
    assert len(same_path_type) == 10 + len(target_records)
    assert _nov13_verify_dispositions(
        {
            "schema_version": policy["schema_version"],
            "records": _nov4_current_view(policy["records"][:347]),
        },
        today=verifier.date(2026, 10, 26),
    )


# Owner decision 2026-10-31: the activated policy rebinds only its alembic/env.py
# provenance pin to the reviewed AUD-434 blob. The immutable 3d83fb27 capture keeps
# the pre-AUD-434 env.py blob, so this is the one exact capture difference allowed.
# Stored as git blob bytes, not as a hex literal, so no new secret-scan identity exists.
_OWNER_ACTIVATED_ENV_SOURCE_BLOB = (
    172,
    47,
    80,
    162,
    134,
    57,
    21,
    113,
    41,
    181,
    9,
    60,
    250,
    21,
    215,
    174,
    24,
    9,
    204,
    163,
)

# Exact source binding for the 58 owner-approved historical-148 identities.
# Existing test node IDs are retained for callers. In these historical contracts,
# "current" means the later pre-squash recapture, not a live migration source.
# Separate still-live-source checks below prevent the frozen inputs hiding drift.
_HISTORICAL148_SOURCE_PINS_AND_LINES = {
    "quality/historical148-squawk-policy.json": (
        (
            166,
            240,
            221,
            37,
            171,
            240,
            56,
            79,
            118,
            169,
            114,
            151,
            246,
            7,
            151,
            103,
            30,
            104,
            58,
            191,
        ),
        (
            15,
            16,
            25,
            26,
            27,
            28,
            29,
            30,
            31,
            32,
            33,
            34,
            38,
            60,
            213,
            488,
            489,
            497,
            503,
            509,
            515,
            521,
            527,
            533,
            539,
            545,
            551,
            557,
            583,
        ),
    ),
    "scripts/quality/validate_historical148_squawk.py": (
        (
            247,
            36,
            106,
            27,
            214,
            129,
            77,
            130,
            5,
            38,
            94,
            56,
            119,
            0,
            8,
            41,
            157,
            183,
            163,
            151,
        ),
        (
            19,
            20,
        ),
    ),
    "tests/fixtures/historical148-squawk-capture-15eaaa.json": (
        (
            251,
            252,
            68,
            231,
            189,
            221,
            124,
            226,
            103,
            74,
            101,
            221,
            196,
            242,
            213,
            72,
            59,
            207,
            188,
            167,
        ),
        (
            4,
            5,
            23,
            24,
            25,
            26,
            27,
            28,
            29,
            30,
            35,
            52,
            62,
            63,
            64,
            72,
            78,
            84,
            90,
            96,
            102,
            108,
            114,
            120,
            126,
            132,
            158,
        ),
    ),
}
_HISTORICAL148_PRIOR_347_SHA256 = (
    160,
    163,
    198,
    32,
    211,
    155,
    83,
    161,
    43,
    70,
    157,
    234,
    181,
    127,
    187,
    82,
    155,
    225,
    165,
    248,
    177,
    208,
    186,
    42,
    46,
    232,
    138,
    211,
    213,
    147,
    83,
    40,
)


def _historical148_assert_original_blob(path: str, data: bytes) -> None:
    expected_blob, _ = _HISTORICAL148_SOURCE_PINS_AND_LINES[path]
    framed = b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    assert hashlib.sha1(framed, usedforsecurity=False).digest() == bytes(expected_blob)


def _historical148_load_json(data: str | bytes) -> Any:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            assert key not in result, "duplicate JSON key"
            result[key] = value
        return result

    return json.loads(data, object_pairs_hook=unique)


def _historical148_pretty_json(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _historical148_canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _historical148_capture_fingerprint(capture: dict[str, Any]) -> str:
    normalized = copy.deepcopy(capture)
    scenarios = normalized["report"]["captures"]
    assert len(scenarios) == 2
    for count, scenario in zip((13, 24), scenarios, strict=True):
        warnings = _historical148_load_json(scenario["stdout"])
        assert len(warnings) == count
        scenario["stdout"] = _historical148_canonical_json(
            sorted(warnings, key=_historical148_canonical_json)
        )
    return hashlib.sha256(
        _historical148_canonical_json(normalized).encode("ascii")
    ).hexdigest()


def _historical148_reconstruct_sources(
    policy_source: bytes, validator_source: bytes, historical_capture: bytes
) -> dict[str, bytes]:
    policy_path = "quality/historical148-squawk-policy.json"
    validator_path = "scripts/quality/validate_historical148_squawk.py"
    capture_path = "tests/fixtures/historical148-squawk-capture-15eaaa.json"

    # Authenticate the retained capture before parsing any of its old values.
    _historical148_assert_original_blob(capture_path, historical_capture)
    capture = _historical148_load_json(historical_capture)
    policy = _historical148_load_json(policy_source)
    assert _historical148_pretty_json(policy) == policy_source
    for field in (
        "source_commit",
        "checkout_sha",
        "workflow_sha",
        "workflow_run_id",
        "job_id",
    ):
        policy["provenance"][field] = capture["provenance"][field]
    for field in (
        ".github/workflows/ci.yml",
        "scripts/quality/render_live_alembic_sql.py",
    ):
        policy["source_blobs"][field] = capture["ordinary"]["source_blobs"][field]
    policy["scenarios"][0]["sql_path"] = capture["report"]["captures"][0]["sql_path"]
    for index in (0, 1):
        policy["scenarios"][index]["sql_identity"] = capture["report"]["captures"][
            index
        ]["sql_identity"]
    for field in (
        "checkout_sha",
        "renderer_blob",
        "workflow_blob",
        "workflow_run_id",
        "workflow_sha",
    ):
        policy["expanded_contract"][field] = capture["expanded"]["metadata"][field]

    historical_policy = _historical148_pretty_json(policy)
    _historical148_assert_original_blob(policy_path, historical_policy)
    policy = _historical148_load_json(historical_policy)
    policy_pin = hashlib.sha256(_historical148_canonical_json(policy).encode("ascii"))
    capture_pin = _historical148_capture_fingerprint(capture)

    # This inverse is limited to the known three recapture lines. A later
    # legitimate matcher body change requires a separately reviewed inverse or
    # retained historical evidence; it does not make current bytes an approval.
    lines = validator_source.decode("utf-8").splitlines(keepends=True)
    current_label = (
        "# Reproducible from the committed historical148 policy and 3d83fb27 capture.\n"
    )
    historical_label = (
        "# Reproducible from the committed historical148 policy and 15eaaa capture.\n"
    )
    assert lines.count(current_label) == 1
    replacements = {
        "_POLICY_SHA256": policy_pin.hexdigest(),
        "_CAPTURE_SHA256": capture_pin,
    }
    counts = dict.fromkeys(replacements, 0)
    for index, line in enumerate(lines):
        if line == current_label:
            lines[index] = historical_label
        for name, fingerprint in replacements.items():
            if line.startswith(name + " = "):
                assert re.fullmatch(rf'{name} = "[0-9a-f]{{64}}"\n', line)
                counts[name] += 1
                lines[index] = f'{name} = "{fingerprint}"\n'
    assert all(count == 1 for count in counts.values())
    historical_validator = "".join(lines).encode("utf-8")
    _historical148_assert_original_blob(validator_path, historical_validator)
    return {
        policy_path: historical_policy,
        validator_path: historical_validator,
        capture_path: historical_capture,
    }


def _historical148_matcher_pins(source: bytes) -> dict[str, str]:
    nodes = [
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in {"_POLICY_SHA256", "_CAPTURE_SHA256"}
    ]
    assert len(nodes) == 2
    pins = {node.targets[0].id: ast.literal_eval(node.value) for node in nodes}
    assert set(pins) == {"_POLICY_SHA256", "_CAPTURE_SHA256"}
    assert all(
        isinstance(pin, str) and re.fullmatch(r"[0-9a-f]{64}", pin)
        for pin in pins.values()
    )
    return pins


def _historical148_assert_current_bindings(
    policy_source: bytes,
    validator_source: bytes,
    historical_capture: bytes,
    current_capture: bytes,
) -> None:
    _historical148_reconstruct_sources(
        policy_source, validator_source, historical_capture
    )
    policy = _historical148_load_json(policy_source)
    capture = _historical148_load_json(current_capture)
    assert _historical148_pretty_json(capture) == current_capture
    pins = _historical148_matcher_pins(validator_source)
    assert (
        hashlib.sha256(
            _historical148_canonical_json(policy).encode("ascii")
        ).hexdigest()
        == pins["_POLICY_SHA256"]
    )
    assert _historical148_capture_fingerprint(capture) == pins["_CAPTURE_SHA256"]
    assert policy["provenance"] == capture["provenance"]
    assert policy["expanded_contract"] == capture["expanded"]["metadata"]
    for path, fingerprint in capture["ordinary"]["source_blobs"].items():
        expected = (
            bytes(_OWNER_ACTIVATED_ENV_SOURCE_BLOB).hex()
            if path == "alembic/env.py"
            else fingerprint
        )
        assert policy["source_blobs"][path] == expected
    for policy_scenario, captured in zip(
        policy["scenarios"], capture["report"]["captures"], strict=True
    ):
        for field in ("sql_path", "sql_identity", "sql_sha256", "sql_bytes"):
            assert policy_scenario[field] == captured[field]
        assert policy_scenario["raw_exit"] == captured["exit_code"]


def _historical148_source_records() -> list[dict[str, Any]]:
    policy, validator_source, historical_capture, _ = _historical148_current_inputs()
    sources = _historical148_reconstruct_sources(
        policy, validator_source, historical_capture
    )
    records: list[dict[str, Any]] = []
    for path, (expected_blob, lines) in _HISTORICAL148_SOURCE_PINS_AND_LINES.items():
        data = sources[path]
        framed = b"blob " + str(len(data)).encode("ascii") + b"\0" + data
        assert hashlib.sha1(framed, usedforsecurity=False).digest() == bytes(
            expected_blob
        )
        source_lines = data.decode("utf-8").splitlines()
        for line in lines:
            values = re.findall(
                r'"([0-9a-f]{40}|[0-9a-f]{64})"', source_lines[line - 1]
            )
            assert len(values) == 1
            digest = hashlib.sha1(
                values[0].encode("ascii"), usedforsecurity=False
            ).digest()
            records.append(
                {
                    "identity": {
                        "path": path,
                        "type": "Hex High Entropy String",
                        "hashed_secret_bytes": list(digest),
                    },
                    "category": "public_integrity_digest",
                    "evidence": (
                        "Public historical-148 integrity metadata; exact source "
                        f"reference {path}:{line}; source-bound diagnostic capture "
                        "and validator fingerprints; not credential material; no "
                        "Squawk admission or migration-risk waiver."
                    ),
                    "owner": "egorribun",
                    "reviewed_on": "2026-10-29",
                    "expires_on": "2027-01-10",
                    "approval_status": "approved",
                }
            )
    assert len(records) == 58
    return records


def test_historical148_integrity_adds_only_58_and_preserves_347_prefix() -> None:
    policy = _reviewed_pre_retirement_dispositions()
    assert len(policy["records"]) == 505
    encoded_prefix = json.dumps(
        policy["records"][:347],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    assert hashlib.sha256(encoded_prefix).digest() == bytes(
        _HISTORICAL148_PRIOR_347_SHA256
    )
    expected = _historical148_source_records()
    assert policy["records"][347:405] == expected
    identities = {
        (
            row["identity"]["path"],
            row["identity"]["type"],
            tuple(row["identity"]["hashed_secret_bytes"]),
        )
        for row in expected
    }
    assert len(identities) == 58
    assert identities == getattr(
        verifier, "_HISTORICAL148_PUBLIC_INTEGRITY_IDENTITIES", frozenset()
    )
    assert (
        len(
            _nov13_verify_dispositions(
                {**policy, "records": _nov4_current_view(policy["records"][:405])},
                today=verifier.date(2026, 10, 29),
            )
        )
        == 405
    )


def test_historical148_integrity_rejects_each_changed_scope_or_review() -> None:
    for original in _historical148_source_records():
        for mutation in (
            "path",
            "detector",
            "digest",
            "category",
            "evidence",
            "owner",
            "review_date",
            "pending",
            "expiry_extension",
            "expiry_change",
        ):
            changed = copy.deepcopy(original)
            if mutation == "path":
                changed["identity"]["path"] = "tests/unreviewed_historical148.py"
            elif mutation == "detector":
                changed["identity"]["type"] = "Secret Keyword"
            elif mutation == "digest":
                changed["identity"]["hashed_secret_bytes"][0] ^= 1
            elif mutation == "category":
                changed["category"] = "documented_crypto_test_vector"
            elif mutation == "evidence":
                changed["evidence"] = "Public checksum; not credential material."
            elif mutation == "owner":
                changed["owner"] = "Different Reviewer"
            elif mutation == "review_date":
                changed["reviewed_on"] = "2026-10-28"
            elif mutation == "pending":
                changed["approval_status"] = "pending_owner_review"
            elif mutation == "expiry_extension":
                changed["expires_on"] = "2027-01-11"
            else:
                assert mutation == "expiry_change"
                changed["expires_on"] = "2027-01-09"
            with pytest.raises(verifier.BaselineArtifactError):
                _nov13_verify_dispositions(
                    _disposition_document(changed), today=verifier.date(2026, 10, 29)
                )


def test_historical148_integrity_rejects_duplicates_and_unapproved_dates() -> None:
    for record in _historical148_source_records():
        for today in (verifier.date(2026, 10, 28), verifier.date(2027, 1, 11)):
            with pytest.raises(verifier.BaselineArtifactError):
                _nov13_verify_dispositions(
                    _disposition_document(copy.deepcopy(record)), today=today
                )
        with pytest.raises(verifier.BaselineArtifactError):
            _nov13_verify_dispositions(
                _disposition_document(copy.deepcopy(record), copy.deepcopy(record)),
                today=verifier.date(2026, 10, 29),
            )
        assert _nov13_verify_dispositions(
            _disposition_document(copy.deepcopy(record)),
            today=verifier.date(2027, 1, 10),
        )


def test_historical148_integrity_preserves_only_two_preexisting_collisions() -> None:
    policy = _reviewed_pre_retirement_dispositions()
    source_digests = {
        tuple(row["identity"]["hashed_secret_bytes"])
        for row in _historical148_source_records()
    }
    expected_old_identities = frozenset(
        {
            verifier._PUBLIC_GIT_BLOB_SOURCEBINDING_REBIND_IDENTITY,
            verifier._AUD247_SQUAWK_PUBLIC_CHECKSUM_IDENTITY,
        }
    )
    old_collisions = [
        row
        for row in policy["records"][:347]
        if tuple(row["identity"]["hashed_secret_bytes"]) in source_digests
    ]
    assert len(old_collisions) == 2
    assert {
        (
            row["identity"]["path"],
            row["identity"]["type"],
            tuple(row["identity"]["hashed_secret_bytes"]),
        )
        for row in old_collisions
    } == expected_old_identities
    assert (
        len(
            _nov13_verify_dispositions(
                _disposition_document(*copy.deepcopy(old_collisions)),
                today=verifier.date(2026, 10, 29),
            )
        )
        == 2
    )
    for row in old_collisions:
        changed = copy.deepcopy(row)
        changed["identity"]["path"] = "tests/unreviewed_historical148.py"
        with pytest.raises(verifier.BaselineArtifactError):
            _nov13_verify_dispositions(
                _disposition_document(changed), today=verifier.date(2026, 10, 29)
            )


def test_historical148_validator_pins_are_public_canonical_fingerprints() -> None:
    policy, validator_source, historical_capture, current_capture = (
        _historical148_current_inputs()
    )
    historical = _historical148_reconstruct_sources(
        policy, validator_source, historical_capture
    )
    historical_policy = _historical148_load_json(
        historical["quality/historical148-squawk-policy.json"]
    )
    historical_pins = _historical148_matcher_pins(
        historical["scripts/quality/validate_historical148_squawk.py"]
    )
    assert (
        hashlib.sha256(
            _historical148_canonical_json(historical_policy).encode("ascii")
        ).hexdigest()
        == historical_pins["_POLICY_SHA256"]
    )
    assert (
        _historical148_capture_fingerprint(_historical148_load_json(historical_capture))
        == historical_pins["_CAPTURE_SHA256"]
    )
    _historical148_assert_current_bindings(
        policy, validator_source, historical_capture, current_capture
    )


def _historical148_current_inputs() -> tuple[bytes, bytes, bytes, bytes]:
    """Latest pre-squash capture inputs, not current migration execution inputs."""
    return (
        _pre_squash_source_bytes("quality/historical148-squawk-policy.json"),
        _pre_squash_source_bytes("scripts/quality/validate_historical148_squawk.py"),
        _pre_squash_source_bytes(
            "tests/fixtures/historical148-squawk-capture-15eaaa.json"
        ),
        _pre_squash_source_bytes(
            "tests/fixtures/historical148-squawk-capture-3d83fb27.json"
        ),
    )


def test_historical148_reconstruction_preserves_each_original_blob() -> None:
    policy, validator_source, historical_capture, _ = _historical148_current_inputs()
    reconstructed = _historical148_reconstruct_sources(
        policy, validator_source, historical_capture
    )
    assert set(reconstructed) == set(_HISTORICAL148_SOURCE_PINS_AND_LINES)
    for path, (expected_blob, _) in _HISTORICAL148_SOURCE_PINS_AND_LINES.items():
        data = reconstructed[path]
        framed = b"blob " + str(len(data)).encode("ascii") + b"\0" + data
        assert hashlib.sha1(framed, usedforsecurity=False).digest() == bytes(
            expected_blob
        )


@pytest.mark.parametrize("input_name", ["policy", "validator", "capture"])
def test_historical148_reconstruction_rejects_changed_inputs(input_name: str) -> None:
    policy, validator_source, historical_capture, _ = _historical148_current_inputs()
    _historical148_reconstruct_sources(policy, validator_source, historical_capture)
    if input_name == "policy":
        changed = json.loads(policy)
        changed["status"] += "-changed"
        policy = (json.dumps(changed, indent=2, ensure_ascii=False) + "\n").encode()
    elif input_name == "validator":
        validator_source += b"\n# changed\n"
    else:
        historical_capture += b" "
    with pytest.raises(AssertionError):
        _historical148_reconstruct_sources(policy, validator_source, historical_capture)


@pytest.mark.parametrize(
    "input_name",
    [
        "policy",
        "policy_recapture",
        "policy_duplicate",
        "capture",
        "validator_policy_pin",
        "validator_capture_pin",
        "validator_body",
    ],
)
def test_historical148_current_bindings_reject_changed_inputs(input_name: str) -> None:
    policy, validator_source, historical_capture, capture = (
        _historical148_current_inputs()
    )
    _historical148_assert_current_bindings(
        policy, validator_source, historical_capture, capture
    )
    if input_name == "policy":
        changed = json.loads(policy)
        changed["status"] += "-changed"
        policy = (json.dumps(changed, indent=2, ensure_ascii=False) + "\n").encode()
    elif input_name == "policy_recapture":
        changed = json.loads(policy)
        changed["provenance"]["workflow_run_id"] += "-changed"
        policy = (json.dumps(changed, indent=2, ensure_ascii=False) + "\n").encode()
    elif input_name == "policy_duplicate":
        policy = policy.replace(b"{\n", b'{\n  "status": "prepared-inactive",\n', 1)
    elif input_name == "capture":
        changed = json.loads(capture)
        changed["schema"] += "-changed"
        capture = (json.dumps(changed, indent=2, ensure_ascii=False) + "\n").encode()
    elif input_name in {"validator_policy_pin", "validator_capture_pin"}:
        name = (
            b"_POLICY_SHA256"
            if input_name == "validator_policy_pin"
            else b"_CAPTURE_SHA256"
        )
        match = re.search(name + rb' = "([0-9a-f]{64})"', validator_source)
        assert match is not None
        digest = bytearray(match.group(1))
        digest[0] = ord("1") if digest[0] == ord("0") else ord("0")
        validator_source = (
            validator_source[: match.start(1)]
            + digest
            + validator_source[match.end(1) :]
        )
    else:
        validator_source += b"\n# changed\n"
    with pytest.raises(AssertionError):
        _historical148_assert_current_bindings(
            policy, validator_source, historical_capture, capture
        )


_HISTORICAL148_RESTORED_POLICY_FIELDS = (
    ("provenance", "source_commit"),
    ("provenance", "checkout_sha"),
    ("provenance", "workflow_sha"),
    ("provenance", "workflow_run_id"),
    ("provenance", "job_id"),
    ("source_blobs", ".github/workflows/ci.yml"),
    ("source_blobs", "scripts/quality/render_live_alembic_sql.py"),
    ("scenarios", 0, "sql_path"),
    ("scenarios", 0, "sql_identity"),
    ("scenarios", 1, "sql_identity"),
    ("expanded_contract", "checkout_sha"),
    ("expanded_contract", "renderer_blob"),
    ("expanded_contract", "workflow_blob"),
    ("expanded_contract", "workflow_run_id"),
    ("expanded_contract", "workflow_sha"),
)

_HISTORICAL148_RESTORED_CAPTURE_FIELDS = (
    ("provenance", "source_commit"),
    ("provenance", "checkout_sha"),
    ("provenance", "workflow_sha"),
    ("provenance", "workflow_run_id"),
    ("provenance", "job_id"),
    ("ordinary", "source_blobs", ".github/workflows/ci.yml"),
    ("ordinary", "source_blobs", "scripts/quality/render_live_alembic_sql.py"),
    ("report", "captures", 0, "sql_path"),
    ("report", "captures", 0, "sql_identity"),
    ("report", "captures", 1, "sql_identity"),
    ("expanded", "metadata", "checkout_sha"),
    ("expanded", "metadata", "renderer_blob"),
    ("expanded", "metadata", "workflow_blob"),
    ("expanded", "metadata", "workflow_run_id"),
    ("expanded", "metadata", "workflow_sha"),
)


@pytest.mark.parametrize("field", _HISTORICAL148_RESTORED_POLICY_FIELDS)
def test_historical148_current_binding_rejects_each_recapture_field_change(
    field: tuple[str | int, ...],
) -> None:
    policy, validator_source, historical_capture, capture = (
        _historical148_current_inputs()
    )
    changed = json.loads(policy)
    parent = changed
    for key in field[:-1]:
        parent = parent[key]
    parent[field[-1]] += "-changed"
    changed_policy = (json.dumps(changed, indent=2, ensure_ascii=False) + "\n").encode()
    with pytest.raises(AssertionError):
        _historical148_assert_current_bindings(
            changed_policy, validator_source, historical_capture, capture
        )


@pytest.mark.parametrize("field", _HISTORICAL148_RESTORED_CAPTURE_FIELDS)
def test_historical148_reconstruction_rejects_each_historical_input_change(
    field: tuple[str | int, ...],
) -> None:
    policy, validator_source, historical_capture, _ = _historical148_current_inputs()
    changed = json.loads(historical_capture)
    parent = changed
    for key in field[:-1]:
        parent = parent[key]
    parent[field[-1]] += "-changed"
    changed_capture = (
        json.dumps(changed, indent=2, ensure_ascii=False) + "\n"
    ).encode()
    with pytest.raises(AssertionError):
        _historical148_reconstruct_sources(policy, validator_source, changed_capture)


def test_historical148_changed_current_literals_remain_unapproved() -> None:
    changed_paths: set[str] = set()
    records = iter(_historical148_source_records())
    for path, (_, lines) in _HISTORICAL148_SOURCE_PINS_AND_LINES.items():
        source_lines = _pre_squash_source_text(path).splitlines()
        for line in lines:
            historical = next(records)
            values = re.findall(
                r'"([0-9a-f]{40}|[0-9a-f]{64})"', source_lines[line - 1]
            )
            assert len(values) == 1
            current_digest = hashlib.sha1(
                values[0].encode("ascii"), usedforsecurity=False
            ).digest()
            if list(current_digest) == historical["identity"]["hashed_secret_bytes"]:
                continue
            changed_paths.add(path)
            changed = copy.deepcopy(historical)
            changed["identity"]["hashed_secret_bytes"] = list(current_digest)
            with pytest.raises(
                verifier.BaselineArtifactError,
                match="historical-148 integrity identity changed scope",
            ):
                _nov13_verify_dispositions(
                    _disposition_document(changed), today=verifier.date(2026, 10, 29)
                )
    assert changed_paths == {
        "quality/historical148-squawk-policy.json",
        "scripts/quality/validate_historical148_squawk.py",
    }


@pytest.mark.parametrize(
    "capture_path",
    [
        "tests/fixtures/historical148-squawk-capture-36f70a0f.json",
        "tests/fixtures/historical148-squawk-capture-3d83fb27.json",
    ],
)
def test_historical148_current_capture_cannot_inherit_old_path_approvals(
    capture_path: str,
) -> None:
    values = re.findall(
        r'"([0-9a-f]{40}|[0-9a-f]{64})"',
        _pre_squash_source_text(capture_path),
    )
    current_digests = {
        tuple(hashlib.sha1(value.encode("ascii"), usedforsecurity=False).digest())
        for value in values
    }
    shared = [
        record
        for record in _historical148_source_records()
        if record["identity"]["path"].endswith("capture-15eaaa.json")
        and tuple(record["identity"]["hashed_secret_bytes"]) in current_digests
    ]
    assert shared
    for record in shared:
        changed = copy.deepcopy(record)
        changed["identity"]["path"] = capture_path
        with pytest.raises(
            verifier.BaselineArtifactError,
            match="historical-148 integrity identity changed scope",
        ):
            _nov13_verify_dispositions(
                _disposition_document(changed), today=verifier.date(2026, 10, 29)
            )


# These byte pins are test provenance, not runtime filesystem authentication.
_OCT30_SOURCE_PINS_AND_LINES = {
    "quality/historical148-squawk-policy.json": (
        (
            *(222, 152, 133, 78, 74, 178, 198, 60, 214, 145),
            *(169, 115, 246, 215, 246, 29, 188, 22, 145, 221),
        ),
        (
            15,
            16,
            31,
            583,
        ),
    ),
    "scripts/quality/run_owned_redis_contracts.py": (
        (
            *(50, 216, 60, 47, 71, 41, 78, 112, 144, 127),
            *(150, 101, 110, 183, 96, 153, 137, 206, 128, 224),
        ),
        (23,),
    ),
    "scripts/quality/validate_historical148_squawk.py": (
        (
            *(45, 217, 156, 183, 44, 228, 110, 133, 36, 227),
            *(68, 169, 20, 77, 138, 176, 211, 61, 180, 155),
        ),
        (
            19,
            20,
        ),
    ),
    "tests/fixtures/historical148-squawk-capture-35aeedeb.json": (
        (
            *(255, 236, 125, 81, 253, 238, 124, 131, 249, 109),
            *(170, 19, 149, 84, 162, 104, 202, 198, 31, 141),
        ),
        (
            4,
            5,
            23,
            24,
            25,
            26,
            27,
            28,
            29,
            30,
            35,
            52,
            62,
            63,
            64,
            72,
            78,
            84,
            90,
            96,
            102,
            108,
            114,
            120,
            126,
            132,
            158,
        ),
    ),
    "tests/fixtures/historical148-squawk-capture-36f70a0f.json": (
        (
            *(160, 155, 225, 106, 122, 30, 220, 98, 12, 22),
            *(245, 103, 211, 183, 49, 29, 72, 18, 139, 5),
        ),
        (
            4,
            5,
            23,
            24,
            25,
            26,
            27,
            28,
            29,
            30,
            35,
            52,
            62,
            63,
            64,
            72,
            78,
            84,
            90,
            96,
            102,
            108,
            114,
            120,
            126,
            132,
            158,
        ),
    ),
    "tests/fixtures/historical148-squawk-capture-3d83fb27.json": (
        (
            *(255, 212, 82, 19, 180, 53, 170, 240, 217, 22),
            *(143, 73, 55, 15, 100, 0, 177, 205, 94, 145),
        ),
        (
            4,
            5,
            23,
            24,
            25,
            26,
            27,
            28,
            29,
            30,
            35,
            52,
            62,
            63,
            64,
            72,
            78,
            84,
            90,
            96,
            102,
            108,
            114,
            120,
            126,
            132,
            158,
        ),
    ),
    "tests/test_aud427_428_contract_quality.py": (
        (
            *(4, 85, 104, 38, 96, 193, 158, 83, 34, 78),
            *(128, 27, 98, 48, 202, 93, 159, 245, 244, 211),
        ),
        (611,),
    ),
}
_OCT30_PRIOR_405_SHA256 = (
    174,
    204,
    39,
    217,
    105,
    69,
    174,
    204,
    111,
    221,
    14,
    63,
    31,
    211,
    86,
    96,
    87,
    101,
    220,
    24,
    224,
    250,
    150,
    201,
    30,
    51,
    67,
    95,
    191,
    22,
    105,
    19,
)


def _oct30_assert_source_blob(path: str, data: bytes) -> None:
    expected_blob, _ = _OCT30_SOURCE_PINS_AND_LINES[path]
    framed = b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    assert hashlib.sha1(framed, usedforsecurity=False).digest() == bytes(expected_blob)


def _oct30_source_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path, (_, line_numbers) in _OCT30_SOURCE_PINS_AND_LINES.items():
        data = _pre_squash_source_bytes(path)
        _oct30_assert_source_blob(path, data)
        lines = data.decode("utf-8").splitlines()
        for line_number in line_numbers:
            values = re.findall(
                r"\b(?:[0-9a-f]{64}|[0-9a-f]{40})\b", lines[line_number - 1]
            )
            assert len(values) == 1
            digest = hashlib.sha1(
                values[0].encode("ascii"), usedforsecurity=False
            ).digest()
            records.append(
                {
                    "identity": {
                        "path": path,
                        "type": "Hex High Entropy String",
                        "hashed_secret_bytes": list(digest),
                    },
                    "category": "public_integrity_digest",
                    "evidence": (
                        "Public October-30 integrity metadata; exact source reference "
                        f"{path}:{line_number}; approved finite 89-entry source-bound "
                        "digest inventory; not credential material; no Squawk "
                        "admission or migration-risk waiver."
                    ),
                    "owner": "egorribun",
                    "reviewed_on": "2026-10-30",
                    "expires_on": "2027-01-10",
                    "approval_status": "approved",
                }
            )
    assert len(records) == 89
    return records


def _oct30_policy() -> dict[str, Any]:
    return _reviewed_pre_retirement_dispositions()


def _oct30_assert_population(
    policy: dict[str, Any], expected: list[dict[str, Any]]
) -> None:
    assert len(policy["records"]) == 505
    encoded_prefix = json.dumps(
        policy["records"][:405],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    assert hashlib.sha256(encoded_prefix).digest() == bytes(_OCT30_PRIOR_405_SHA256)
    assert policy["records"][405:494] == expected


def test_oct30_integrity_adds_exact_89_and_preserves_405_prefix() -> None:
    policy = _oct30_policy()
    expected = _oct30_source_records()
    _oct30_assert_population(policy, expected)
    identities = {
        (
            record["identity"]["path"],
            record["identity"]["type"],
            tuple(record["identity"]["hashed_secret_bytes"]),
        )
        for record in expected
    }
    assert len(identities) == 89
    assert identities == getattr(
        verifier, "_OCT30_PUBLIC_INTEGRITY_IDENTITIES", frozenset()
    )
    assert not identities.intersection(
        (
            record["identity"]["path"],
            record["identity"]["type"],
            tuple(record["identity"]["hashed_secret_bytes"]),
        )
        for record in policy["records"][:405]
    )
    assert verifier._FALSE_POSITIVE_RECORD_LIMIT == 512
    assert (
        len(
            _nov13_verify_dispositions(
                {**policy, "records": _nov4_current_view(policy["records"][:494])},
                today=verifier.date(2026, 10, 30),
            )
        )
        == 494
    )


def test_oct30_population_rejects_missing_extra_reordered_or_changed_prior() -> None:
    expected = _oct30_source_records()
    original = _oct30_policy()
    _oct30_assert_population(original, expected)
    for mutation in ("missing", "extra", "reordered", "prior-metadata"):
        changed = copy.deepcopy(original)
        if mutation == "missing":
            changed["records"].pop()
        elif mutation == "extra":
            extra = copy.deepcopy(expected[-1])
            extra["identity"]["path"] = "tests/unapproved-extra-digest.py"
            changed["records"].append(extra)
        elif mutation == "reordered":
            changed["records"][493], changed["records"][492] = (
                changed["records"][492],
                changed["records"][493],
            )
        else:
            changed["records"][404]["owner"] = "different-owner"
        with pytest.raises(AssertionError):
            _oct30_assert_population(changed, expected)


def test_oct30_source_pins_reject_changed_bytes_and_transplanted_sources() -> None:
    paths = list(_OCT30_SOURCE_PINS_AND_LINES)
    for index, path in enumerate(paths):
        original = _pre_squash_source_bytes(path)
        _oct30_assert_source_blob(path, original)
        with pytest.raises(AssertionError):
            _oct30_assert_source_blob(path, original + b"\n")
        with pytest.raises(AssertionError):
            _oct30_assert_source_blob(paths[(index + 1) % len(paths)], original)


def test_oct30_each_identity_is_exact_and_cannot_inherit_old_58_metadata() -> None:
    for original in _oct30_source_records():
        identity = original["identity"]
        approved = _nov13_verify_dispositions(
            _disposition_document(original), today=verifier.date(2026, 10, 30)
        )
        assert approved == {
            verifier.FindingIdentity(
                identity["path"],
                identity["type"],
                bytes(identity["hashed_secret_bytes"]).hex(),
                9000,
            )
        }
        for mutation in ("path", "detector", "digest", "old-58-metadata"):
            changed = copy.deepcopy(original)
            if mutation == "path":
                changed["identity"]["path"] = "tests/unapproved-extra-digest.py"
            elif mutation == "detector":
                changed["identity"]["type"] = "Secret Keyword"
            elif mutation == "digest":
                changed["identity"]["hashed_secret_bytes"][0] ^= 1
            else:
                changed["reviewed_on"] = "2026-10-29"
                changed["evidence"] = (
                    "Public historical-148 integrity metadata; exact source reference "
                    f"{identity['path']}:1; source-bound diagnostic capture "
                    "and validator "
                    "fingerprints; not credential material; no Squawk admission or "
                    "migration-risk waiver."
                )
            with pytest.raises(verifier.BaselineArtifactError):
                _nov13_verify_dispositions(
                    _disposition_document(changed), today=verifier.date(2026, 10, 30)
                )


def test_oct30_review_metadata_and_expiry_remain_exact_for_each_source_path() -> None:
    representatives = {
        record["identity"]["path"]: record for record in _oct30_source_records()
    }
    changes = {
        "category": "documented_crypto_test_vector",
        "evidence": "Public digest; not credential material.",
        "owner": "different-owner",
        "reviewed_on": "2026-10-29",
        "expires_on": "2027-01-11",
        "approval_status": "pending",
    }
    for original in representatives.values():
        assert _nov13_verify_dispositions(
            _disposition_document(original), today=verifier.date(2027, 1, 10)
        )
        for field, value in changes.items():
            changed = copy.deepcopy(original)
            changed[field] = value
            with pytest.raises(verifier.BaselineArtifactError):
                _nov13_verify_dispositions(
                    _disposition_document(changed), today=verifier.date(2026, 10, 30)
                )
        with pytest.raises(verifier.BaselineArtifactError):
            _nov13_verify_dispositions(
                _disposition_document(original), today=verifier.date(2027, 1, 11)
            )
        with pytest.raises(verifier.BaselineArtifactError):
            _nov13_verify_dispositions(
                _disposition_document(original), today=verifier.date(2026, 10, 29)
            )


def test_oct30_retired_approvals_never_reactivate_from_base_or_candidate(
    tmp_path: Path,
) -> None:
    records = _oct30_source_records()
    repository, _ = _new_git_fixture(tmp_path)
    accepted_sha = _commit_dispositions(repository, records)
    today = verifier.date(2026, 10, 30)
    assert (
        len(_nov13_verify_dispositions(_disposition_document(*records), today=today))
        == 89
    )
    # The October-30 batch also approved two still-live Redis contract digests.
    # Retirement must filter removed paths, not erase surviving approvals.
    surviving_records = [
        record
        for record in records
        if record["identity"]["path"]
        in {
            "scripts/quality/run_owned_redis_contracts.py",
            "tests/test_aud427_428_contract_quality.py",
        }
    ]
    assert len(surviving_records) == 2
    expected = _nov13_verify_dispositions(
        _disposition_document(*surviving_records), today=today
    )
    assert len(expected) == 2
    assert (
        verifier.load_trusted_base_false_positive_dispositions(
            accepted_sha, repository_root=repository, today=today
        )
        == expected
    )
    with pytest.raises(verifier.BaselineArtifactError, match="retired source"):
        verifier.load_owner_authored_candidate_false_positive_dispositions(
            repository_root=repository, today=today
        )

    _commit_dispositions(repository, surviving_records)
    assert (
        verifier.load_owner_authored_candidate_false_positive_dispositions(
            repository_root=repository, today=today
        )
        == expected
    )


_AUD447_CI_ALLOCATION_CATEGORY = "ci_test_contract_sentinel"
_AUD447_CI_ALLOCATION_TEST_DIGEST = (
    *(169, 74, 143, 229, 204, 177, 155, 166, 28, 76),
    *(8, 115, 211, 145, 233, 135, 152, 47, 187, 211),
)
_AUD447_CI_ALLOCATION_OTHER_DIGEST = (
    *(208, 148, 30, 104, 218, 143, 56, 21, 31, 248),
    *(106, 97, 252, 89, 247, 197, 207, 159, 202, 162),
)
_AUD447_CI_ALLOCATION_SPEC = (
    (
        "tests/integration/test_aud447_dlq_auth_scrub_postgres.py",
        "Secret Keyword",
        _AUD447_CI_ALLOCATION_TEST_DIGEST,
        98,
        "sentinel",
        "exact loopback-only test password equality checked before connection",
    ),
    (
        "tests/test_aud447_dlq_auth_scrub_migration.py",
        "Basic Auth Credentials",
        _AUD447_CI_ALLOCATION_TEST_DIGEST,
        290,
        "sentinel",
        "owned loopback PostgreSQL URL used only by allocation acceptance "
        "and rejection controls",
    ),
    (
        "tests/test_aud447_dlq_auth_scrub_migration.py",
        "Basic Auth Credentials",
        _AUD447_CI_ALLOCATION_OTHER_DIGEST,
        350,
        "negative sentinel",
        "wrong-password URL must be rejected before engine creation",
    ),
    (
        "tests/test_quality_workflow_contract.py",
        "Basic Auth Credentials",
        _AUD447_CI_ALLOCATION_TEST_DIGEST,
        7465,
        "sentinel",
        "source-only assertion for the exact step-local owned-service URL",
    ),
    (
        "tests/test_quality_workflow_contract.py",
        "Secret Keyword",
        _AUD447_CI_ALLOCATION_TEST_DIGEST,
        7479,
        "sentinel",
        "source-only assertion for disposable PostgreSQL service credentials",
    ),
)
_AUD447_CI_ALLOCATION_EVIDENCE = {
    (path, finding_type, digest): (
        f"Public AUD-447 owned PostgreSQL CI allocation {label}; "
        f"{path}:{line}; {purpose}; "
        "source-bound by the finite five-identity contract; "
        "not production credential material; "
        "no database, release or Squawk authorization."
    )
    for path, finding_type, digest, line, label, purpose in _AUD447_CI_ALLOCATION_SPEC
}
_AUD447_CI_ALLOCATION_PATHS = frozenset(
    identity[0] for identity in _AUD447_CI_ALLOCATION_EVIDENCE
)
_AUD447_CI_ALLOCATION_DIGESTS = frozenset(
    identity[2] for identity in _AUD447_CI_ALLOCATION_EVIDENCE
)
_AUD447_PRIOR_QUALITY_IDENTITIES = frozenset(
    {
        (
            "tests/test_quality_workflow_contract.py",
            "Hex High Entropy String",
            (
                *(206, 71, 253, 152, 246, 12, 118, 27, 182, 59),
                *(76, 158, 216, 255, 38, 141, 84, 183, 68, 171),
            ),
        ),
        (
            "tests/test_quality_workflow_contract.py",
            "Hex High Entropy String",
            (
                *(33, 192, 46, 107, 136, 217, 63, 180, 73, 90),
                *(25, 211, 160, 159, 91, 40, 0, 44, 68, 31),
            ),
        ),
    }
)

_AUD447_SOURCE_BLOBS = {
    "tests/integration/test_aud447_dlq_auth_scrub_postgres.py": (
        *(202, 56, 166, 60, 157, 7, 182, 147, 135, 144),
        *(206, 148, 144, 15, 223, 151, 240, 121, 81, 68),
    ),
    "tests/test_aud447_dlq_auth_scrub_migration.py": (
        *(140, 32, 111, 199, 16, 61, 143, 40, 48, 56),
        *(145, 174, 92, 144, 235, 99, 221, 244, 155, 100),
    ),
    "tests/test_quality_workflow_contract.py": (
        *(72, 101, 68, 149, 56, 202, 53, 85, 203, 160),
        *(195, 84, 6, 40, 251, 150, 156, 173, 51, 37),
    ),
    ".github/workflows/reusable-backend-tests.yml": (
        *(237, 164, 16, 40, 91, 48, 242, 14, 234, 29),
        *(233, 143, 237, 41, 191, 143, 132, 2, 251, 240),
    ),
}
_AUD447_PRIOR_494_SHA256 = (
    *(212, 137, 53, 97, 119, 178, 201, 169),
    *(10, 240, 101, 13, 142, 5, 77, 155),
    *(3, 194, 29, 18, 123, 194, 170, 185),
    *(180, 180, 204, 128, 100, 163, 70, 78),
)


def _aud447_allocation_records() -> list[dict[str, Any]]:
    entries = _AUD447_CI_ALLOCATION_EVIDENCE.items()
    return [
        {
            "identity": {
                "path": path,
                "type": finding_type,
                "hashed_secret_bytes": list(digest),
            },
            "category": _AUD447_CI_ALLOCATION_CATEGORY,
            "evidence": evidence,
            "owner": "egorribun",
            "reviewed_on": "2026-10-31",
            "expires_on": "2027-01-10",
            "approval_status": "approved",
        }
        for (path, finding_type, digest), evidence in entries
    ]


def _aud447_assert_source_blob(path: str, data: bytes) -> None:
    expected = _AUD447_SOURCE_BLOBS[path]
    framed = b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    assert hashlib.sha1(framed, usedforsecurity=False).digest() == bytes(expected)


def _aud447_allocation_source_records() -> list[dict[str, Any]]:
    sources = {path: _pre_squash_source_bytes(path) for path in _AUD447_SOURCE_BLOBS}
    for path, data in sources.items():
        _aud447_assert_source_blob(path, data)
    for spec in _AUD447_CI_ALLOCATION_SPEC:
        path, finding_type, digest, line, _label, _purpose = spec
        source_line = sources[path].decode("utf-8").splitlines()[line - 1]
        literals = re.findall(r'"(?:[^"\\]|\\.)*"', source_line)
        assert literals
        value = ast.literal_eval(literals[-1])
        assert isinstance(value, str)
        if finding_type == "Basic Auth Credentials":
            value = urlsplit(value).password
        assert isinstance(value, str)
        actual = hashlib.sha1(value.encode("utf-8"), usedforsecurity=False).digest()
        assert actual == bytes(digest)
    records = _aud447_allocation_records()
    assert len(records) == 5
    return records


def _aud447_assert_population(
    policy: dict[str, Any], expected: list[dict[str, Any]]
) -> None:
    assert len(expected) == 5
    assert len(policy["records"]) == 505
    encoded_prefix = json.dumps(
        policy["records"][:494],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    assert hashlib.sha256(encoded_prefix).digest() == bytes(_AUD447_PRIOR_494_SHA256)
    assert policy["records"][494:499] == expected


def test_aud447_allocation_adds_exact_five_and_preserves_all_prior_records() -> None:
    policy = _oct30_policy()
    expected = _aud447_allocation_source_records()
    _aud447_assert_population(policy, expected)
    _oct30_assert_population(policy, _oct30_source_records())
    assert verifier._AUD447_CI_ALLOCATION_EVIDENCE == _AUD447_CI_ALLOCATION_EVIDENCE
    assert verifier._AUD447_PRIOR_QUALITY_IDENTITIES == _AUD447_PRIOR_QUALITY_IDENTITIES
    allowed_pairs = verifier._FALSE_POSITIVE_NON_HEX_CATEGORY_PATH_TYPES[
        _AUD447_CI_ALLOCATION_CATEGORY
    ]
    assert not any(path in _AUD447_CI_ALLOCATION_PATHS for path, _ in allowed_pairs)
    assert verifier._FALSE_POSITIVE_RECORD_LIMIT == 512
    assert (
        len(
            _nov13_verify_dispositions(
                {**policy, "records": _nov4_current_view(policy["records"][:499])},
                today=verifier.date(2026, 10, 31),
            )
        )
        == 499
    )


@pytest.mark.parametrize(
    "today",
    [verifier.date(2026, 10, 31), verifier.date(2027, 1, 10)],
)
def test_aud447_allocation_exact_records_validate_without_source(
    today: verifier.date, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    records = _aud447_allocation_records()
    assert _nov13_verify_dispositions(_disposition_document(*records), today=today) == {
        verifier.FindingIdentity(path, finding_type, bytes(digest).hex(), 9000)
        for path, finding_type, digest in _AUD447_CI_ALLOCATION_EVIDENCE
    }


@pytest.mark.parametrize("index", range(5))
@pytest.mark.parametrize(
    "mutation",
    [
        "path",
        "existing-path",
        "wildcard",
        "detector",
        "digest",
        "detector-and-digest",
        "category",
        "evidence",
        "owner",
        "review-date",
        "pending",
        "extended-expiry",
        "shortened-expiry",
        "missing-field",
    ],
)
def test_aud447_allocation_rejects_changed_scope_and_metadata(
    index: int, mutation: str
) -> None:
    changed = copy.deepcopy(_aud447_allocation_records()[index])
    identity = changed["identity"]
    if mutation == "path":
        identity["path"] = "tests/unapproved-allocation.py"
    elif mutation == "existing-path":
        identity["path"] = ".github/workflows/ci.yml"
    elif mutation == "wildcard":
        identity["path"] = "tests/*"
    elif mutation == "detector":
        identity["type"] = "Hex High Entropy String"
    elif mutation == "digest":
        identity["hashed_secret_bytes"][0] ^= 1
    elif mutation == "detector-and-digest":
        identity["type"] = "Hex High Entropy String"
        identity["hashed_secret_bytes"][0] ^= 1
        changed["category"] = "public_integrity_digest"
    elif mutation == "category":
        changed["category"] = "source_contract_identifier"
    elif mutation == "evidence":
        changed["evidence"] = "Public test sentinel; not credential material."
    elif mutation == "owner":
        changed["owner"] = "different-owner"
    elif mutation == "review-date":
        changed["reviewed_on"] = "2026-10-30"
    elif mutation == "pending":
        changed["approval_status"] = "pending"
    elif mutation == "extended-expiry":
        changed["expires_on"] = "2027-01-11"
    elif mutation == "shortened-expiry":
        changed["expires_on"] = "2027-01-09"
    else:
        assert mutation == "missing-field"
        del changed["owner"]
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(changed), today=verifier.date(2026, 10, 31)
        )


def test_aud447_allocation_refuses_duplicates_sixth_identity_and_cap_growth() -> None:
    records = _aud447_allocation_records()
    extra = copy.deepcopy(records[0])
    extra["identity"]["hashed_secret_bytes"][0] ^= 1
    for addition in (copy.deepcopy(records[0]), extra):
        with pytest.raises(verifier.BaselineArtifactError):
            _nov13_verify_dispositions(
                _disposition_document(*records, addition),
                today=verifier.date(2026, 10, 31),
            )
    with pytest.raises(verifier.BaselineArtifactError, match="record list is invalid"):
        _nov13_verify_dispositions(
            _disposition_document(*([records[0]] * 513)),
            today=verifier.date(2026, 10, 31),
        )
    for today in (verifier.date(2026, 10, 30), verifier.date(2027, 1, 11)):
        for record in records:
            with pytest.raises(verifier.BaselineArtifactError):
                _nov13_verify_dispositions(_disposition_document(record), today=today)


def test_aud447_allocation_preserves_only_the_two_prior_quality_collisions() -> None:
    records = _oct30_policy()["records"][204:206]
    identities = {
        (
            record["identity"]["path"],
            record["identity"]["type"],
            tuple(record["identity"]["hashed_secret_bytes"]),
        )
        for record in records
    }
    assert len(records) == 2
    assert identities == _AUD447_PRIOR_QUALITY_IDENTITIES
    for record in records:
        assert record["category"] == "public_integrity_digest"
        assert _nov13_verify_dispositions(
            _disposition_document(record), today=verifier.date(2026, 10, 31)
        )
        for mutation in ("digest", "type", "category"):
            changed = copy.deepcopy(record)
            if mutation == "digest":
                changed["identity"]["hashed_secret_bytes"][0] ^= 1
            elif mutation == "type":
                changed["identity"]["type"] = "Secret Keyword"
            else:
                changed["category"] = "documented_crypto_test_vector"
            with pytest.raises(verifier.BaselineArtifactError):
                _nov13_verify_dispositions(
                    _disposition_document(changed), today=verifier.date(2026, 10, 31)
                )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-new",
        "missing-prior",
        "extra",
        "reordered-prior",
        "reordered-old-89",
        "reordered-new",
        "prior-metadata",
        "new-metadata",
    ],
)
def test_aud447_allocation_population_is_append_only(mutation: str) -> None:
    expected = _aud447_allocation_source_records()
    policy = _oct30_policy()
    _aud447_assert_population(policy, expected)
    changed = copy.deepcopy(policy)
    records = changed["records"]
    if mutation == "missing-new":
        del records[494]
    elif mutation == "missing-prior":
        del records[0]
    elif mutation == "extra":
        records.append(copy.deepcopy(expected[0]))
    elif mutation == "reordered-prior":
        records[0], records[1] = records[1], records[0]
    elif mutation == "reordered-old-89":
        records[492], records[493] = records[493], records[492]
    elif mutation == "reordered-new":
        records[494], records[495] = records[495], records[494]
    elif mutation == "prior-metadata":
        records[493]["owner"] = "different-owner"
    else:
        assert mutation == "new-metadata"
        records[494]["owner"] = "different-owner"
    with pytest.raises(AssertionError):
        _aud447_assert_population(changed, expected)


def test_aud447_allocation_source_pins_refuse_changes_and_transplants() -> None:
    paths = list(_AUD447_SOURCE_BLOBS)
    for index, path in enumerate(paths):
        source = _pre_squash_source_bytes(path)
        _aud447_assert_source_blob(path, source)
        with pytest.raises(AssertionError):
            _aud447_assert_source_blob(path, source + b"\n")
        with pytest.raises(AssertionError):
            _aud447_assert_source_blob(paths[(index + 1) % len(paths)], source)


def test_aud447_allocation_trusted_loader_refuses_candidate_only_expansion(
    tmp_path: Path,
) -> None:
    records = [
        row
        for row in _aud447_allocation_records()
        if row["identity"]["path"] not in _RETIRED_DISPOSITION_PATHS
    ]
    repository, prior_sha = _new_git_fixture(tmp_path)
    policy_path = repository / "quality/security-false-positive-dispositions.json"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(
        json.dumps(_disposition_document(*records)), encoding="utf-8"
    )
    today = verifier.date(2026, 10, 31)
    assert (
        verifier.load_trusted_base_false_positive_dispositions(
            prior_sha, repository_root=repository, today=today
        )
        == set()
    )
    approved = verifier.load_owner_authored_candidate_false_positive_dispositions(
        repository_root=repository, today=today
    )
    assert len(approved) == 2
    accepted_sha = _commit_dispositions(repository, records)
    changed = copy.deepcopy(records)
    extra = copy.deepcopy(records[0])
    extra["identity"]["hashed_secret_bytes"][0] ^= 1
    changed.append(extra)
    policy_path.write_text(
        json.dumps(_disposition_document(*changed)), encoding="utf-8"
    )
    assert (
        verifier.load_trusted_base_false_positive_dispositions(
            accepted_sha, repository_root=repository, today=today
        )
        == approved
    )
    with pytest.raises(verifier.BaselineArtifactError):
        verifier.load_owner_authored_candidate_false_positive_dispositions(
            repository_root=repository, today=today
        )


_NOV1_V4_FIXTURE_PATH = "tests/fixtures/full-backend-reusable-baseline.v4.yaml"
_NOV1_V4_BINDING_CASES = (
    (
        8,
        "source_files",
        "nightly",
        (
            104,
            215,
            61,
            176,
            93,
            44,
            188,
            13,
            9,
            109,
            33,
            33,
            193,
            71,
            85,
            207,
            238,
            56,
            142,
            158,
        ),
        "public_integrity_digest",
        "workflow integrity digest",
    ),
    (
        10,
        "source_files",
        "reusable_full_backend_mutation",
        (
            168,
            182,
            163,
            180,
            38,
            70,
            249,
            240,
            40,
            189,
            200,
            180,
            229,
            150,
            242,
            191,
            229,
            241,
            27,
            130,
        ),
        "public_integrity_digest",
        "workflow integrity digest",
    ),
    (
        15,
        "nightly_preserved_jobs",
        "frontend-mutation-shards",
        (
            24,
            128,
            227,
            180,
            81,
            89,
            153,
            235,
            9,
            241,
            222,
            140,
            195,
            209,
            75,
            255,
            90,
            204,
            155,
            96,
        ),
        "independent_contract_fingerprint",
        "normalized workflow-contract fingerprint",
    ),
)


def _nov1_v4_binding_record(index: int) -> dict[str, Any]:
    line, section, field, digest, category, public_kind = _NOV1_V4_BINDING_CASES[index]
    return {
        "identity": {
            "path": _NOV1_V4_FIXTURE_PATH,
            "type": "Hex High Entropy String",
            "hashed_secret_bytes": list(digest),
        },
        "category": category,
        "evidence": (
            f"Public {public_kind}; source {_NOV1_V4_FIXTURE_PATH}:{line} "
            f"field {section}.{field}; observed scanner job 124805024868 "
            "(detect-secrets 1.5.0); identity derived with pinned parser/hash; "
            "not credential material."
        ),
        "owner": "egorribun",
        "reviewed_on": "2026-11-01",
        "expires_on": "2027-01-10",
        "approval_status": "approved",
    }


@pytest.mark.parametrize("index", range(3))
@pytest.mark.parametrize(
    "today",
    [verifier.date(2026, 11, 1), verifier.date(2027, 1, 10)],
)
def test_nov1_v4_binding_exact_identity_is_admitted_without_source(
    index: int,
    today: verifier.date,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    record = _nov1_v4_binding_record(index)
    identity = record["identity"]
    assert _nov13_verify_dispositions(_disposition_document(record), today=today) == {
        verifier.FindingIdentity(
            identity["path"],
            identity["type"],
            bytes(identity["hashed_secret_bytes"]).hex(),
            1,
        )
    }


@pytest.mark.parametrize("index", range(3))
@pytest.mark.parametrize(
    "mutation",
    [
        "path-v3",
        "path-other",
        "type",
        "digest",
        "category",
        "evidence",
        "owner",
        "reviewed-on",
        "expires-on",
        "approval-status",
        "path-and-category",
        "missing-field",
        "noncanonical-path",
    ],
)
def test_nov1_v4_binding_refuses_scope_and_approval_mutations(
    index: int, mutation: str
) -> None:
    record = _nov1_v4_binding_record(index)
    identity = record["identity"]
    if mutation == "path-v3":
        identity["path"] = "tests/fixtures/full-backend-reusable-baseline.v3.yaml"
    elif mutation == "path-other":
        identity["path"] = "src/unreviewed-v4-digest.txt"
    elif mutation == "type":
        identity["type"] = "Secret Keyword"
    elif mutation == "digest":
        identity["hashed_secret_bytes"][0] ^= 1
    elif mutation == "category":
        record["category"] = "documented_crypto_test_vector"
    elif mutation == "evidence":
        record["evidence"] += " Changed scope."
    elif mutation == "owner":
        record["owner"] = "another-owner"
    elif mutation == "reviewed-on":
        record["reviewed_on"] = "2026-10-31"
    elif mutation == "expires-on":
        record["expires_on"] = "2027-01-11"
    elif mutation == "approval-status":
        record["approval_status"] = "pending"
    elif mutation == "path-and-category":
        identity["path"] = "src/unreviewed-v4-digest.txt"
        record["category"] = "documented_crypto_test_vector"
    elif mutation == "missing-field":
        del record["owner"]
    else:
        assert mutation == "noncanonical-path"
        identity["path"] = "./" + _NOV1_V4_FIXTURE_PATH
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(record), today=verifier.date(2026, 11, 1)
        )


def test_nov1_v4_binding_preserves_all_prior_499_records() -> None:
    records = _oct30_policy()["records"][:499]
    assert len(records) == 499
    validated = _nov13_verify_dispositions(
        _disposition_document(*_nov4_current_view(records)),
        today=verifier.date(2026, 11, 1),
    )
    assert len(validated) == 499


def test_nov1_v4_binding_preserves_historical_off_fixture_collisions() -> None:
    records = _oct30_policy()["records"][:499]
    fixture_records = [
        record
        for record in records
        if record["identity"]["path"] == _NOV1_V4_FIXTURE_PATH
    ]
    assert len(fixture_records) == 42
    historical_digests = {
        tuple(record["identity"]["hashed_secret_bytes"]) for record in fixture_records
    }
    collisions = [
        record
        for record in records
        if record["identity"]["path"] != _NOV1_V4_FIXTURE_PATH
        and tuple(record["identity"]["hashed_secret_bytes"]) in historical_digests
    ]
    assert len(collisions) == 25
    assert {record["identity"]["path"] for record in collisions} == {
        "tests/fixtures/full-backend-reusable-baseline.v3.yaml",
        "tests/test_full_backend_reusable_contract.py",
    }
    validated = _nov13_verify_dispositions(
        _disposition_document(*collisions), today=verifier.date(2026, 11, 1)
    )
    assert len(validated) == 25


def test_nov1_v4_binding_refuses_unknown_fourth_fixture_identity() -> None:
    record = _nov1_v4_binding_record(0)
    record["identity"]["hashed_secret_bytes"] = [0] * 20
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(record), today=verifier.date(2026, 11, 1)
        )


@pytest.mark.parametrize("index", range(3))
def test_nov1_v4_binding_digest_matches_exact_public_fixture_field(
    index: int,
) -> None:
    root = Path(__file__).resolve().parents[1]
    lines = (root / _NOV1_V4_FIXTURE_PATH).read_text(encoding="utf-8").splitlines()
    line, section, field, digest, _, _ = _NOV1_V4_BINDING_CASES[index]
    parents = [
        value
        for value in lines[: line - 1]
        if value and not value.startswith((" ", "#"))
    ]
    assert parents[-1] == section + ":"
    matched = re.fullmatch(
        rf"  {re.escape(field)}: ([0-9a-f]{{64}})(?: #.*)?", lines[line - 1]
    )
    assert matched is not None
    actual = hashlib.sha1(
        matched.group(1).encode("utf-8"), usedforsecurity=False
    ).digest()
    assert actual == bytes(digest)


@pytest.mark.parametrize("index", range(3))
@pytest.mark.parametrize(
    "today",
    [verifier.date(2026, 10, 31), verifier.date(2027, 1, 11)],
)
def test_nov1_v4_binding_refuses_future_review_and_expired_identity(
    index: int, today: verifier.date
) -> None:
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(_nov1_v4_binding_record(index)), today=today
        )


def _nov1_v4_assert_append_only_population(policy: dict[str, Any]) -> None:
    expected = [_nov1_v4_binding_record(index) for index in range(3)]
    assert len(expected) == 3
    _aud447_assert_population(policy, _aud447_allocation_records())
    assert policy["records"][499:502] == expected


def test_nov1_v4_policy_appends_only_three_to_the_unchanged_499_prefix() -> None:
    policy = _oct30_policy()
    _nov1_v4_assert_append_only_population(policy)
    assert len(policy["records"]) == 505
    validated = _nov13_verify_dispositions(
        {**policy, "records": _nov4_current_view(policy["records"])},
        today=verifier.date(2026, 11, 2),
    )
    assert len(validated) == 505


def test_nov1_v4_guard_reserves_exact_fixture_categories_and_only_new_digests() -> None:
    policy = _oct30_policy()
    _nov1_v4_assert_append_only_population(policy)
    fixture_records = [
        record
        for record in policy["records"]
        if record["identity"]["path"] == _NOV1_V4_FIXTURE_PATH
    ]
    expected = {
        (
            record["identity"]["path"],
            record["identity"]["type"],
            tuple(record["identity"]["hashed_secret_bytes"]),
        ): record["category"]
        for record in fixture_records
    }
    assert len(expected) == 45
    assert list(expected.values()).count("public_integrity_digest") == 13
    assert list(expected.values()).count("independent_contract_fingerprint") == 32
    assert verifier._V4_FIXTURE_CATEGORY_BY_IDENTITY == expected
    assert verifier._NOV1_V4_BINDING_DIGESTS == frozenset(
        case[3] for case in _NOV1_V4_BINDING_CASES
    )
    prior_fingerprints = {
        (
            record["identity"]["path"],
            record["identity"]["type"],
            tuple(record["identity"]["hashed_secret_bytes"]),
        )
        for record in policy["records"][:499]
        if record["identity"]["path"] == _NOV1_V4_FIXTURE_PATH
        and record["category"] == "independent_contract_fingerprint"
    }
    assert len(prior_fingerprints) == 31
    assert (
        verifier._V4_PRIOR_INDEPENDENT_CONTRACT_FINGERPRINT_IDENTITIES
        == prior_fingerprints
    )


def test_nov1_v4_guard_keeps_historical_categories_exact() -> None:
    records = [
        record
        for record in _oct30_policy()["records"][:499]
        if record["identity"]["path"] == _NOV1_V4_FIXTURE_PATH
    ]
    assert len(records) == 42
    for original in records:
        assert _nov13_verify_dispositions(
            _disposition_document(original), today=verifier.date(2026, 11, 1)
        )
        changed = copy.deepcopy(original)
        changed["category"] = "documented_crypto_test_vector"
        with pytest.raises(verifier.BaselineArtifactError):
            _nov13_verify_dispositions(
                _disposition_document(changed), today=verifier.date(2026, 11, 1)
            )


@pytest.mark.parametrize("index", range(3))
def test_nov1_v4_policy_rejects_each_duplicate_identity(index: int) -> None:
    record = _nov1_v4_binding_record(index)
    assert _nov13_verify_dispositions(
        _disposition_document(record), today=verifier.date(2026, 11, 1)
    )
    with pytest.raises(verifier.BaselineArtifactError, match="duplicate"):
        _nov13_verify_dispositions(
            _disposition_document(record, copy.deepcopy(record)),
            today=verifier.date(2026, 11, 1),
        )


def test_nov1_v4_policy_keeps_the_512_record_cap() -> None:
    assert verifier._FALSE_POSITIVE_RECORD_LIMIT == 512
    record = _nov1_v4_binding_record(0)
    with pytest.raises(verifier.BaselineArtifactError, match="record list is invalid"):
        _nov13_verify_dispositions(
            _disposition_document(*([record] * 513)),
            today=verifier.date(2026, 11, 1),
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-prior",
        "reordered-prior",
        "prior-metadata",
        "missing-aud447",
        "reordered-aud447",
        "aud447-metadata",
        "missing-new",
        "reordered-new",
        "new-metadata",
        "extra",
    ],
)
def test_nov1_v4_policy_population_rejects_changes_to_any_authorized_block(
    mutation: str,
) -> None:
    policy = _oct30_policy()
    _nov1_v4_assert_append_only_population(policy)
    changed = copy.deepcopy(policy)
    records = changed["records"]
    if mutation == "missing-prior":
        del records[0]
    elif mutation == "reordered-prior":
        records[0], records[1] = records[1], records[0]
    elif mutation == "prior-metadata":
        records[493]["owner"] = "another-owner"
    elif mutation == "missing-aud447":
        del records[494]
    elif mutation == "reordered-aud447":
        records[494], records[495] = records[495], records[494]
    elif mutation == "aud447-metadata":
        records[498]["owner"] = "another-owner"
    elif mutation == "missing-new":
        del records[499]
    elif mutation == "reordered-new":
        records[499], records[500] = records[500], records[499]
    elif mutation == "new-metadata":
        records[501]["owner"] = "another-owner"
    else:
        assert mutation == "extra"
        records.append(copy.deepcopy(records[499]))
    with pytest.raises(AssertionError):
        _nov1_v4_assert_append_only_population(changed)


def test_nov1_v4_trusted_loader_keeps_candidate_only_approval_separate(
    tmp_path: Path,
) -> None:
    records = [_nov1_v4_binding_record(index) for index in range(3)]
    repository, prior_sha = _new_git_fixture(tmp_path)
    policy_path = repository / "quality/security-false-positive-dispositions.json"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(
        json.dumps(_disposition_document(*records)), encoding="utf-8"
    )
    today = verifier.date(2026, 11, 1)
    assert (
        verifier.load_trusted_base_false_positive_dispositions(
            prior_sha, repository_root=repository, today=today
        )
        == set()
    )
    approved = verifier.load_owner_authored_candidate_false_positive_dispositions(
        repository_root=repository, today=today
    )
    assert len(approved) == 3
    accepted_sha = _commit_dispositions(repository, records)
    changed = copy.deepcopy(records)
    changed[0]["identity"]["hashed_secret_bytes"][0] ^= 1
    policy_path.write_text(
        json.dumps(_disposition_document(*changed)), encoding="utf-8"
    )
    assert (
        verifier.load_trusted_base_false_positive_dispositions(
            accepted_sha, repository_root=repository, today=today
        )
        == approved
    )
    with pytest.raises(verifier.BaselineArtifactError):
        verifier.load_owner_authored_candidate_false_positive_dispositions(
            repository_root=repository, today=today
        )


# Exact append-only approval; digest bytes avoid introducing scanner literals.
def _nov2_integrity_records() -> list[dict[str, Any]]:
    cases = [
        (
            "tests/integration/test_mvp_baseline_schema_equivalence.py",
            (
                *(223, 180, 227, 77, 196, 192, 57, 78, 207, 219),
                *(31, 217, 77, 130, 107, 60, 67, 250, 21, 190),
            ),
            (
                "Public pre-squash repository commit; exact source reference "
                "tests/integration/test_mvp_baseline_schema_equivalence.py:35 field "
                "PRE_SQUASH_COMMIT. Identity derived using the pinned "
                "detect-secrets 1.5.0 SHA-1 algorithm; not scanner-exported and not "
                "credential material."
            ),
        ),
        (
            "tests/test_aud378_slsa_provenance_attestation.py",
            (
                *(165, 69, 159, 227, 95, 134, 249, 202, 88, 75),
                *(180, 150, 196, 54, 131, 86, 48, 20, 31, 42),
            ),
            (
                "Public official slsa-verifier v2.7.1 linux-amd64 attestation "
                "SHA-256; exact source reference "
                "tests/test_aud378_slsa_provenance_attestation.py:11 field "
                "PROVENANCE_SHA256; GitHub release asset 267893648. Identity "
                "derived using pinned detect-secrets 1.5.0 SHA-1; not "
                "scanner-exported and not credential material."
            ),
        ),
    ]
    return [
        {
            "identity": {
                "path": path,
                "type": "Hex High Entropy String",
                "hashed_secret_bytes": list(digest),
            },
            "category": "public_integrity_digest",
            "evidence": evidence,
            "owner": "egorribun",
            "reviewed_on": "2026-11-02",
            "expires_on": "2027-01-09",
            "approval_status": "approved",
        }
        for path, digest, evidence in cases
    ]


def test_nov2_integrity_policy_preserves_502_and_adds_only_two() -> None:
    policy = _oct30_policy()
    assert len(policy["records"]) == 505
    prefix = json.dumps(
        policy["records"][:502],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    assert hashlib.sha1(prefix, usedforsecurity=False).digest() == bytes(
        (
            206,
            112,
            236,
            181,
            230,
            167,
            199,
            124,
            213,
            194,
            2,
            33,
            166,
            30,
            74,
            76,
            55,
            90,
            200,
            219,
        )
    )
    assert policy["records"][502:504] == _nov2_integrity_records()
    assert (
        len(
            _nov13_verify_dispositions(
                {**policy, "records": _nov4_current_view(policy["records"])},
                today=verifier.date(2026, 11, 2),
            )
        )
        == 505
    )
    assert verifier._FALSE_POSITIVE_RECORD_LIMIT == 512


@pytest.mark.parametrize("index", range(2))
def test_nov2_integrity_identity_matches_its_public_source(index: int) -> None:
    root = Path(__file__).resolve().parents[1]
    record = _nov2_integrity_records()[index]
    identity = record["identity"]
    field = ("PRE_SQUASH_COMMIT", "PROVENANCE_SHA256")[index]
    source = ast.parse((root / identity["path"]).read_text(encoding="utf-8"))
    values = [
        ast.literal_eval(node.value)
        for node in source.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == field
            for target in node.targets
        )
    ]
    assert len(values) == 1
    assert isinstance(values[0], str)
    assert hashlib.sha1(
        values[0].encode("utf-8"), usedforsecurity=False
    ).digest() == bytes(identity["hashed_secret_bytes"])


@pytest.mark.parametrize("index", range(2))
@pytest.mark.parametrize(
    "mutation",
    [
        "path",
        "type",
        "digest",
        "category",
        "evidence",
        "owner",
        "reviewed_on",
        "expires_on",
        "approval_status",
        "wildcard",
    ],
)
def test_nov2_integrity_rejects_any_approval_scope_drift(
    index: int, mutation: str
) -> None:
    record = _nov2_integrity_records()[index]
    if mutation == "path":
        record["identity"]["path"] += ".other"
    elif mutation == "type":
        record["identity"]["type"] = "Base64 High Entropy String"
    elif mutation == "digest":
        record["identity"]["hashed_secret_bytes"][0] ^= 1
    elif mutation == "wildcard":
        record["identity"]["path"] = "tests/*"
    elif mutation == "category":
        record["category"] = "documented_crypto_test_vector"
    elif mutation == "evidence":
        record["evidence"] += " broadened"
    elif mutation == "owner":
        record["owner"] = "other-owner"
    elif mutation == "reviewed_on":
        record["reviewed_on"] = "2026-11-01"
    elif mutation == "expires_on":
        record["expires_on"] = "2027-01-10"
    else:
        record["approval_status"] = "pending"
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(record), today=verifier.date(2026, 11, 2)
        )


@pytest.mark.parametrize("index", range(2))
@pytest.mark.parametrize(
    ("today", "accepted"),
    [
        (verifier.date(2026, 11, 1), False),
        (verifier.date(2026, 11, 2), True),
        (verifier.date(2027, 1, 9), True),
        (verifier.date(2027, 1, 10), False),
    ],
)
def test_nov2_integrity_expires_before_january_ten(
    index: int, today: verifier.date, accepted: bool
) -> None:
    document = _disposition_document(_nov2_integrity_records()[index])
    if accepted:
        assert len(_nov13_verify_dispositions(document, today=today)) == 1
    else:
        with pytest.raises(verifier.BaselineArtifactError):
            _nov13_verify_dispositions(document, today=today)


@pytest.mark.parametrize("path", tuple(_PRE_SQUASH_SOURCE_BLOBS))
def test_pre_squash_scanner_source_is_available_and_exact(path: str) -> None:
    assert _pre_squash_source_bytes(path)


@pytest.mark.parametrize("path", tuple(_PRE_SQUASH_SOURCE_BLOBS))
@pytest.mark.parametrize("mutation", ["changed", "empty", "transplanted"])
def test_pre_squash_scanner_source_rejects_changed_or_transplanted_bytes(
    path: str, mutation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = _pre_squash_source_bytes(path)
    if mutation == "changed":
        data = original + b"\n"
    elif mutation == "empty":
        data = b""
    else:
        paths = list(_PRE_SQUASH_SOURCE_BLOBS)
        other = paths[(paths.index(path) + 1) % len(paths)]
        data = _pre_squash_source_bytes(other)

    def changed_result(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(args[0], 0, stdout=data, stderr=b"")

    monkeypatch.setattr(subprocess, "run", changed_result)
    with pytest.raises(AssertionError, match="source blob changed"):
        _pre_squash_source_bytes(path)


@pytest.mark.parametrize("failure", ["exec-missing", "object-missing", "timeout"])
def test_pre_squash_scanner_source_fails_closed_without_history(
    failure: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failed_result(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        if failure == "exec-missing":
            raise FileNotFoundError("untrusted Git diagnostic")
        if failure == "object-missing":
            raise subprocess.CalledProcessError(
                128, args[0], stderr=b"untrusted Git diagnostic"
            )
        raise subprocess.TimeoutExpired(args[0], 30)

    monkeypatch.setattr(subprocess, "run", failed_result)
    path = next(iter(_PRE_SQUASH_SOURCE_BLOBS))
    with pytest.raises(AssertionError, match="full-history checkout") as caught:
        _pre_squash_source_bytes(path)
    assert "untrusted" not in str(caught.value)


@pytest.mark.parametrize(
    "path",
    [
        "../outside.py",
        "tests/unreviewed.py",
        "./quality/historical148-squawk-policy.json",
    ],
)
def test_pre_squash_scanner_source_refuses_unreviewed_paths_before_git(
    path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("Git must not run for an unreviewed path")

    monkeypatch.setattr(subprocess, "run", forbidden)
    with pytest.raises(AssertionError, match="unreviewed historical source path"):
        _pre_squash_source_bytes(path)


@pytest.mark.parametrize(
    "path",
    (
        "tests/integration/test_aud350_stored_event_timestamp_migration.py",
        "quality/security-false-positive-dispositions.json",
    ),
)
def test_pre_squash_scanner_source_uses_only_pinned_git_bytes_not_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    original = _pre_squash_source_bytes(path)
    impostor = tmp_path / path
    impostor.parent.mkdir(parents=True)
    impostor.write_bytes(b"unreviewed current content")
    calls = []

    def pinned_result(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, stdout=original, stderr=b"")

    monkeypatch.setattr(subprocess, "run", pinned_result)
    assert _pre_squash_source_bytes(path, repository_root=tmp_path) == original
    assert calls == [
        (
            [
                _git_executable(),
                "--no-replace-objects",
                "cat-file",
                "blob",
                f"{_REVIEWED_SOURCE_COMMIT_OVERRIDES.get(path, _PRE_SQUASH_SOURCE_COMMIT)}:{path}",
            ],
            dict(cwd=tmp_path, check=True, capture_output=True, timeout=30),
        )
    ]
    assert impostor.read_bytes() == b"unreviewed current content"


def test_scanner_history_contract_checkout_is_not_shallow() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    job = source.split("  contract-tests:\n", 1)[1]
    job = re.split(r"\n  [a-zA-Z0-9_-]+:\n", job, maxsplit=1)[0]
    checkout = re.search(
        r"(?m)^        uses: actions/checkout@[^\n]+\n"
        r"        with:\n((?:          [^\n]+\n)+)",
        job,
    )
    assert checkout is not None
    assert "          fetch-depth: 0\n" in checkout[1]
    assert "          persist-credentials: false\n" in checkout[1]


# AUD-426 and AUD-447 PostgreSQL proof steps: the reviewed insertion before the
# integration suite (exact bytes of the two steps in reusable-backend-tests.yml).
_AUD426_447_PROOF_STEPS = (
    b"            # AUD-426 and AUD-447: PostgreSQL proofs. The AUD-447 quarantine CAS\n",
    b"            # test needs a non-superuser, NOBYPASSRLS login with CREATE on the\n",
    b"            # database; it is built here from the same statements the RLS tests use.\n",
    b"            - name: Create disposable non-superuser PostgreSQL login for AUD-447\n",
    b"              shell: bash\n",
    b"              timeout-minutes: 5\n",
    b"              env:\n",
    b"                  PGHOST_URL: ${{ env.DATABASE_URL }}\n",
    b"              run: |\n",
    b"                  set -euo pipefail\n",
    b"                  role_password=\"$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')\"\n",
    b'                  echo "::add-mask::$role_password"\n',
    b"                  ROLE_PASSWORD=\"$role_password\" uv run --frozen --no-sync python - <<'PY'\n",
    b"                  import asyncio\n",
    b"                  import os\n",
    b"\n",
    b"                  import asyncpg\n",
    b"\n",
    b"                  from tests.fixtures.rls_runtime_role import runtime_role_statements\n",
    b"\n",
    b'                  ROLE = "ue_aud447_probe"\n',
    b"\n",
    b"\n",
    b"                  async def main() -> None:\n",
    b'                      connection = await asyncpg.connect(os.environ["PGHOST_URL"].replace("+asyncpg", "", 1))\n',
    b"                      try:\n",
    b'                          for statement in runtime_role_statements(ROLE, os.environ["ROLE_PASSWORD"]):\n',
    b"                              await connection.execute(statement)\n",
    b'                          await connection.execute(f"GRANT CREATE ON DATABASE test TO {ROLE}")\n',
    b"                      finally:\n",
    b"                          await connection.close()\n",
    b"\n",
    b"\n",
    b"                  asyncio.run(main())\n",
    b"                  PY\n",
    b"                  {\n",
    b'                    echo "AUD447_DLQ_DISPOSABLE=1"\n',
    b'                    echo "AUD447_DLQ_DISPOSABLE_PG_URL=postgresql+asyncpg://ue_aud447_probe:${role_password}@127.0.0.1:5432/test"\n',
    b'                  } >> "$GITHUB_ENV"\n',
    b"\n",
    b"            - name: Run PostgreSQL proofs (AUD-426, AUD-447) without skips\n",
    b"              shell: bash\n",
    b"              timeout-minutes: 15\n",
    b"              run: |\n",
    b"                  set -euo pipefail\n",
    b"                  uv run --frozen --no-sync pytest \\\n",
    b"                    tests/security/test_mfa_race.py \\\n",
    b"                    tests/integration/test_aud447_quarantine_cas_postgres.py \\\n",
    b"                    tests/test_aud447_lossless_storage_postgres.py \\\n",
    b"                    -v --tb=short -p no:cacheprovider -rs --junitxml=pg-proofs.xml\n",
    b'                  uv run --frozen --no-sync python -c "\n',
    b"                  import sys\n",
    b"                  import xml.etree.ElementTree as ET\n",
    b"                  root = ET.parse('pg-proofs.xml').getroot()\n",
    b"                  suites = [root] if root.tag == 'testsuite' else list(root)\n",
    b"                  total = sum(int(suite.get('tests', '0')) for suite in suites)\n",
    b"                  unexecuted = sum(int(suite.get(key, '0')) for suite in suites for key in ('skipped', 'failures', 'errors'))\n",
    b"                  expected = {\n",
    b"                      ('tests.security.test_mfa_race', 'test_mfa_challenge_race_condition'),\n",
    b"                      ('tests.security.test_mfa_race', 'test_mfa_step_up_challenge_verification_race'),\n",
    b"                      ('tests.integration.test_aud447_quarantine_cas_postgres', 'test_quarantine_never_overwrites_bytes_repaired_after_they_were_read'),\n",
    b"                      ('tests.integration.test_aud447_quarantine_cas_postgres', 'test_quarantine_replaces_observed_bytes_and_scrubs_link_in_error_field'),\n",
    b"                      ('tests.integration.test_aud447_quarantine_cas_postgres', 'test_failed_replay_stores_scrubbed_error_text'),\n",
    b"                      ('tests.test_aud447_lossless_storage_postgres', 'test_aud447_postgres_insert_and_replay_store_no_token_bytes'),\n",
    b"                  }\n",
    b"                  cases = list(root.iter('testcase'))\n",
    b"                  actual = [(case.get('classname'), case.get('name')) for case in cases]\n",
    b"                  failed_cases = sum(any(case.find(status) is not None for status in ('skipped', 'failure', 'error')) for case in cases)\n",
    b"                  if total != len(expected) or unexecuted or failed_cases or len(actual) != len(expected) or set(actual) != expected:\n",
    b"                      print(f'PostgreSQL proofs: tests={total} not-executed-or-failed={unexecuted} failed-cases={failed_cases} observed={len(actual)} expected={len(expected)}')\n",
    b"                      sys.exit(1)\n",
    b"                  print(f'PostgreSQL proofs executed {total} test(s) with no skips.')\n",
    b'                  "\n',
    b"\n",
)


# Exact insertions for the separately owned reviewed-byte binding.
_AUD363_SERVICE = (
    b"            aud363:\n"
    b"                # Dedicated runner-owned PostgreSQL; PGDATA uses only tmpfs.\n"
    b"                image: pgvector/pgvector:pg17@sha256:ac08538c6f8b9904c33c8224c5e5706dbe760aca29db1d096972b4052c22a75d\n"
    b"                env:\n"
    b"                    POSTGRES_USER: aud363_admin\n"
    b"                    POSTGRES_PASSWORD: test\n"
    b"                    POSTGRES_DB: postgres\n"
    b"                options: >-\n"
    b"                    --memory 768m\n"
    b"                    --memory-swap 768m\n"
    b"                    --tmpfs /var/lib/postgresql/data:rw,size=268435456\n"
    b'                    --health-cmd "pg_isready -U aud363_admin -d postgres"\n'
    b"                    --health-interval 10s\n"
    b"                    --health-timeout 5s\n"
    b"                    --health-retries 5\n"
    b"                ports:\n"
    b'                    - "127.0.0.1:15432:5432"\n'
    b"\n"
)
_AUD363_STEP = (
    b"            - name: Verify borrowed-session PostgreSQL proofs (AUD-363 and AUD-454)\n"
    b"              timeout-minutes: 5\n"
    b"              env:\n"
    b"                  AUD363_POSTGRES_CONTAINER_ID: ${{ job.services.aud363.id }}\n"
    b"              run: uv run --frozen --no-sync python scripts/quality/run_aud363_borrowed_postgres.py\n"
    b"\n"
)


# Exact, counted PostgreSQL receipt insertion in the live workflow.
_POSTGRES_RECEIPT_SETUP = (
    b"                  # The canonical PR integration suite is unsharded. Capture\n"
    b"                  # these existing PostgreSQL proofs without rerunning them.\n"
    b'                  $requireBaselineReceipt = $integrationNumShards -eq 1 -and $env:INTEGRATION_TEST_PATTERN -eq "tests/integration/"\n'
    b"                  if ($requireBaselineReceipt) {\n"
    b'                    $receiptName = "baseline-equivalence-" + [guid]::NewGuid().ToString("N") + ".xml"\n'
    b"                    $baselineReceipt = Join-Path $env:RUNNER_TEMP $receiptName\n"
    b'                    $pytestArgs += "--junitxml=$baselineReceipt"\n'
    b"                  }\n"
)


_POSTGRES_RECEIPT_VALIDATION = (
    b"                  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }\n"
    b"                  if ($requireBaselineReceipt) {\n"
    b"                    $receiptValidator = @'\n"
    b"                  import sys\n"
    b"                  from xml.etree import ElementTree\n"
    b"\n"
    b"                  expected = {'tests.integration.test_mvp_baseline_schema_equivalence': ('test_proof_owned_fixture_never_uses_default_database',\n"
    b"                                                                              'test_absent_pre_squash_commit_fails_with_a_clear_message',\n"
    b"                                                                              'test_pre_squash_chain_and_baseline_stamp_their_own_heads',\n"
    b"                                                                              'test_statement_level_schema_differs_only_by_the_audited_additions',\n"
    b"                                                                              'test_catalog_facts_outside_the_additions_are_identical',\n"
    b"                                                                              'test_no_permissive_using_true_policy_exists_on_any_rls_table',\n"
    b"                                                                              'test_baseline_database_matches_the_current_models',\n"
    b"                                                                              'test_baseline_refuses_downgrade_and_keeps_its_revision',\n"
    b"                                                                              'test_baseline_refuses_nonempty_schema_before_ddl',\n"
    b"                                                                              'test_baseline_refuses_populated_pgx_namespace'),\n"
    b"                   'tests.integration.test_aud277_360_450_tenant_rls_postgres': ('test_no_permissive_true_policy_remains_on_core_tables',\n"
    b"                                                                                 'test_tenant_session_sees_only_its_rows_and_never_null_rows',\n"
    b"                                                                                 'test_guc_bypass_cannot_expose_other_tenants_or_null_rows',\n"
    b"                                                                                 'test_dedicated_bypass_role_member_sees_every_row',\n"
    b"                                                                                 'test_ordinary_writes_are_stamped_with_the_session_tenant',\n"
    b"                                                                                 'test_writes_cannot_target_another_tenant_or_escape_the_session',\n"
    b"                                                                                 'test_messages_need_both_participation_and_the_session_tenant',\n"
    b"                                                                                 'test_every_tenant_table_forces_rls_and_stamps_unowned_inserts',\n"
    b"                                                                                 'test_notification_producer_rows_are_owned_by_the_session_tenant',\n"
    b"                                                                                 'test_worker_bypass_producer_must_write_its_tenant_explicitly',\n"
    b"                                                                                 'test_bypass_scheduler_persists_owned_reminders_and_outbox_events'),\n"
    b"                   'tests.integration.test_aud262_receipt_schema_postgres': ('test_receipt_upgrade_creates_exact_catalog_and_forces_owner_rls',\n"
    b"                                                                             'test_receipt_rls_hides_other_owners_and_rejects_forged_writes[empty]',\n"
    b"                                                                             'test_receipt_rls_hides_other_owners_and_rejects_forged_writes[peer]',\n"
    b"                                                                             'test_receipt_rls_hides_other_owners_and_rejects_forged_writes[outsider]',\n"
    b"                                                                             'test_receipt_rls_revokes_owner_access_after_membership_removal',\n"
    b"                                                                             'test_receipt_rls_inherits_parent_chat_tenant_visibility',\n"
    b"                                                                             'test_receipt_unique_scope_allows_other_chat_and_sender',\n"
    b"                                                                             'test_expired_receipt_has_no_global_visibility_or_implicit_deletion',\n"
    b"                                                                             'test_receipt_foreign_key_lifecycle_preserves_message_deletion_marker[messages]',\n"
    b"                                                                             'test_receipt_foreign_key_lifecycle_preserves_message_deletion_marker[users]',\n"
    b"                                                                             'test_receipt_foreign_key_lifecycle_preserves_message_deletion_marker[chats]',\n"
    b"                                                                             'test_receipt_baseline_downgrade_refuses_without_losing_committed_history',\n"
    b"                                                                             'test_receipt_owned_fixture_never_uses_default_database',\n"
    b"                                                                             'test_notification_pair_claims_commit_conflict_and_rollback_on_owned_postgres',\n"
    b"                                                                             'test_notification_pair_ledger_is_unique_without_attempt_constraint'),\n"
    b"                   'tests.integration.test_dlq_retry_postgres': ('test_retry_completed_job_waits_for_worker_and_preserves_state',\n"
    b"                                                                 'test_aud447_dedup_waits_for_worker_refreshes_and_leaves_commit_to_caller')}\n"
    b"                  root = ElementTree.parse(sys.argv[1]).getroot()\n"
    b"                  for classname, names in expected.items():\n"
    b"                      cases = [\n"
    b'                          case for case in root.iter("testcase")\n'
    b'                          if case.get("classname") == classname\n'
    b"                      ]\n"
    b'                      observed = [case.get("name") for case in cases]\n'
    b"                      if (\n"
    b"                          len(cases) != len(names)\n"
    b"                          or set(observed) != set(names)\n"
    b"                          or any(\n"
    b"                              case.find(status) is not None\n"
    b"                              for case in cases\n"
    b'                              for status in ("skipped", "failure", "error")\n'
    b"                          )\n"
    b"                      ):\n"
    b'                          raise SystemExit(f"PostgreSQL cohort receipt incomplete or unsuccessful: {classname}")\n'
    b'                  print(f"INTEGRATION_POSTGRES_COHORT_VERIFIED_PASS {sum(map(len, expected.values()))}")\n'
    b"                  '@\n"
    b"                    uv run --frozen --no-sync python -c $receiptValidator $baselineReceipt\n"
    b"                    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }\n"
    b"                  }\n"
)


def _reviewed_live_scanner_source_bytes(path: str) -> bytes:
    original = _pre_squash_source_bytes(path)
    if path == "tests/test_aud427_428_contract_quality.py":
        current = (Path(__file__).resolve().parents[1] / path).read_bytes()
        assert (
            hashlib.sha256(current).digest() == _AUD427_428_CURRENT_TEST_SOURCE_SHA256
        ), "reviewed AUD-427/428 helper contract source changed"
        assert (
            current.count(
                b'    assert run.strip() == ". ./scripts/ci/backend-run-integration-tests.ps1"'
            )
            == 1
        )
        assert current.count(b"    assert launcher in wrapper") == 1
        assert b"    assert launcher in run" not in current
        return current
    if path != ".github/workflows/reusable-backend-tests.yml":
        return original
    # Retain the immutable setup-python review, allowing only the supported
    # pytest-timeout caller options and the owned PostgreSQL unit prerequisite.
    anchor = (
        b"                  $pytestArgs = @(\n"
        b"                    $env:INTEGRATION_TEST_PATTERN,"
    )
    replacement = (
        b"                  # pytest-timeout 2.4.0 supports this only as a caller option,\n"
        b"                  # not a marker keyword. Keep receipt watchdogs active in debuggers.\n"
        b"                  $pytestArgs = @(\n"
        b'                    "--timeout-disable-debugger-detection",\n'
        b"                    $env:INTEGRATION_TEST_PATTERN,"
    )
    assert original.count(anchor) == 1, "reviewed timeout call site changed"
    reviewed = original.replace(anchor, replacement)
    mailpit_anchor = (
        b"                  uv run pytest -q -p no:cacheprovider \\\n"
        b"                    tests/integration/test_mfa_mailpit_outbox.py \\\n"
    )
    mailpit_replacement = (
        b"                  uv run pytest -q -p no:cacheprovider \\\n"
        b"                    --timeout-disable-debugger-detection \\\n"
        b"                    tests/integration/test_mfa_mailpit_outbox.py \\\n"
    )
    assert reviewed.count(mailpit_anchor) == 1, "reviewed Mailpit call site changed"
    reviewed = reviewed.replace(mailpit_anchor, mailpit_replacement)
    # Reuse the immutable reviewed image and retry implementation, not a new
    # digest/approval identity. Only the owned PostgreSQL image is needed here.
    pull_anchor = (
        b"            - name: Pre-pull testcontainer images with bounded retries\n"
    )
    integration_anchor = b"            - name: Run integration tests\n"
    assert original.count(pull_anchor) == original.count(integration_anchor) == 1
    pull_step = original.split(pull_anchor, 1)[1].split(integration_anchor, 1)[0]
    array_anchor = b"                  $images = @(\n"
    array_end = b"                  )\n"
    assert pull_step.count(array_anchor) == pull_step.count(array_end) == 1
    images, retry = pull_step.split(array_anchor, 1)[1].split(array_end, 1)
    postgres_lines = [
        line
        for line in images.splitlines(keepends=True)
        if line.startswith(b'                    "pgvector/pgvector:')
    ]
    assert len(postgres_lines) == 1
    assert b"@sha256:" in postgres_lines[0]
    unit_pull = (
        b"            - name: Pre-pull owned PostgreSQL image with bounded retries\n"
        b"              timeout-minutes: 5\n"
        b"              shell: pwsh\n"
        b"              run: |\n"
        b"                  # Root-level owned PostgreSQL proofs run in the full unit shard.\n"
        + array_anchor
        + postgres_lines[0]
        + array_end
        + retry
    )
    unit_anchor = b"            - name: Run pytest\n"
    assert reviewed.count(unit_anchor) == 1
    reviewed = reviewed.replace(unit_anchor, unit_pull + unit_anchor)
    # The integration baseline proof extracts the pinned pre-squash commit with
    # git archive, which a shallow actions/checkout cannot resolve.
    checkout_head = (
        b'                    - "127.0.0.1:1025:1025"\n'
        b"        steps:\n"
        b"            - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1\n"
        b"              with:\n"
    )
    checkout_anchor = checkout_head + b"                  persist-credentials: false\n"
    checkout_comment = b"                  # The baseline proof reads the pinned pre-squash commit with git archive.\n"
    assert reviewed.count(checkout_anchor) == 1, "reviewed integration checkout changed"
    reviewed = reviewed.replace(
        checkout_anchor,
        checkout_head
        + checkout_comment
        + b"                  fetch-depth: 0\n"
        + b"                  persist-credentials: false\n",
    )
    # AUD-426 and AUD-447: the two PostgreSQL proof steps are a counted reviewed
    # insertion before the integration suite, not a change to the pinned baseline.
    proof_anchor = b"            - name: Run integration tests\n"
    assert reviewed.count(proof_anchor) == 1, (
        "reviewed integration suite anchor changed"
    )
    reviewed = reviewed.replace(
        proof_anchor, b"".join(_AUD426_447_PROOF_STEPS) + proof_anchor
    )
    service_anchor = b"                    - 5432:5432\n            redis:\n"
    assert reviewed.count(service_anchor) == 1, (
        "reviewed PostgreSQL service anchor changed"
    )
    reviewed = reviewed.replace(
        service_anchor,
        b"                    - 5432:5432\n"
        + _AUD363_SERVICE
        + b"            redis:\n",
    )
    step_anchor = b"            - name: Wait for PostgreSQL\n"
    assert reviewed.count(step_anchor) == 1, "reviewed PostgreSQL step anchor changed"
    reviewed = reviewed.replace(step_anchor, _AUD363_STEP + step_anchor)
    unit_args = b"                  $pytestArgs = @($env:TEST_PATTERN)\n"
    assert reviewed.count(unit_args) == 1
    reviewed = reviewed.replace(
        unit_args,
        unit_args
        + b'                  $pytestArgs += "--timeout-disable-debugger-detection"\n',
    )
    receipt_anchor = b"                  uv run python scripts/quality/run_owned_redis_contracts.py @pytestArgs\n"
    assert reviewed.count(receipt_anchor) == 1, (
        "reviewed PostgreSQL receipt anchor changed"
    )
    return reviewed.replace(
        receipt_anchor,
        _POSTGRES_RECEIPT_SETUP + receipt_anchor + _POSTGRES_RECEIPT_VALIDATION,
        1,
    )


def _assert_live_scanner_source_bytes(path: str, actual: bytes) -> None:
    assert actual == _reviewed_live_scanner_source_bytes(path), (
        "live scanner source differs from its exact reviewed bytes"
    )


@pytest.mark.parametrize("mutation", ["missing", "changed", "duplicate", "unrelated"])
def test_live_backend_timeout_binding_refuses_other_changes(mutation: str) -> None:
    path = ".github/workflows/reusable-backend-tests.yml"
    original = _pre_squash_source_bytes(path)
    expected = _reviewed_live_scanner_source_bytes(path)
    option = b'                    "--timeout-disable-debugger-detection",\n'
    assert original.count(option) == 0
    assert expected.count(option) == 1
    _assert_live_scanner_source_bytes(path, expected)
    if mutation == "missing":
        invalid = original
    elif mutation == "changed":
        invalid = expected.replace(option, option.replace(b"disable", b"enable"))
    elif mutation == "duplicate":
        invalid = expected.replace(option, option + option)
    else:
        invalid = expected + b"# unrelated workflow change\n"
    with pytest.raises(AssertionError, match="exact reviewed bytes"):
        _assert_live_scanner_source_bytes(path, invalid)


@pytest.mark.parametrize("mutation", ["missing", "changed", "duplicate", "unrelated"])
def test_live_mailpit_timeout_binding_refuses_other_changes(mutation: str) -> None:
    path = ".github/workflows/reusable-backend-tests.yml"
    original = _pre_squash_source_bytes(path)
    expected = _reviewed_live_scanner_source_bytes(path)
    option = b"                    --timeout-disable-debugger-detection \\\n"
    assert original.count(option) == 0
    assert expected.count(option) == 1
    _assert_live_scanner_source_bytes(path, expected)
    if mutation == "missing":
        invalid = expected.replace(option, b"")
    elif mutation == "changed":
        invalid = expected.replace(option, option.replace(b"disable", b"enable"))
    elif mutation == "duplicate":
        invalid = expected.replace(option, option + option)
    else:
        invalid = expected + b"# unrelated Mailpit workflow change\n"
    with pytest.raises(AssertionError, match="exact reviewed bytes"):
        _assert_live_scanner_source_bytes(path, invalid)


@pytest.mark.parametrize(
    "mutation", ["missing", "shallow", "duplicate", "unrelated-checkout"]
)
def test_live_integration_checkout_binding_refuses_other_changes(
    mutation: str,
) -> None:
    path = ".github/workflows/reusable-backend-tests.yml"
    original = _pre_squash_source_bytes(path)
    expected = _reviewed_live_scanner_source_bytes(path)
    # The unit job already fetches full history; bind only the integration block.
    comment = b"                  # The baseline proof reads the pinned pre-squash commit with git archive.\n"
    option = comment + b"                  fetch-depth: 0\n"
    assert original.count(option) == 0
    assert expected.count(option) == 1
    _assert_live_scanner_source_bytes(path, expected)
    if mutation == "missing":
        invalid = expected.replace(option, comment)
    elif mutation == "shallow":
        invalid = expected.replace(
            option, comment + b"                  fetch-depth: 1\n"
        )
    elif mutation == "duplicate":
        invalid = expected.replace(option, option + option)
    else:
        invalid = expected.replace(
            option,
            option + b"                  clean: false\n",
        )
    with pytest.raises(AssertionError, match="exact reviewed bytes"):
        _assert_live_scanner_source_bytes(path, invalid)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-pull",
        "missing-pull-timeout",
        "changed-pull-timeout",
        "duplicate-pull",
        "unpinned-image",
        "missing-option",
        "changed-option",
    ],
)
def test_live_unit_postgres_prerequisite_binding_refuses_other_changes(
    mutation: str,
) -> None:
    path = ".github/workflows/reusable-backend-tests.yml"
    expected = _reviewed_live_scanner_source_bytes(path)
    start = expected.index(
        b"            - name: Pre-pull owned PostgreSQL image with bounded retries\n"
    )
    end = expected.index(b"            - name: Run pytest\n", start)
    pull = expected[start:end]
    option = (
        b'                  $pytestArgs += "--timeout-disable-debugger-detection"\n'
    )
    assert expected.count(pull) == expected.count(option) == 1
    pull_timeout = b"              timeout-minutes: 5\n"
    assert pull.count(pull_timeout) == 1
    _assert_live_scanner_source_bytes(path, expected)
    if mutation == "missing-pull":
        invalid = expected.replace(pull, b"")
    elif mutation == "missing-pull-timeout":
        invalid = expected.replace(pull, pull.replace(pull_timeout, b""))
    elif mutation == "changed-pull-timeout":
        invalid = expected.replace(
            pull, pull.replace(pull_timeout, pull_timeout.replace(b"5", b"6"))
        )
    elif mutation == "duplicate-pull":
        invalid = expected.replace(pull, pull + pull)
    elif mutation == "unpinned-image":
        changed = re.sub(rb"@sha256:[0-9a-f]{64}", b"", pull)
        assert changed != pull
        invalid = expected.replace(pull, changed)
    elif mutation == "missing-option":
        invalid = expected.replace(option, b"")
    else:
        invalid = expected.replace(option, option.replace(b"disable", b"enable"))
    with pytest.raises(AssertionError, match="exact reviewed bytes"):
        _assert_live_scanner_source_bytes(path, invalid)


@pytest.mark.parametrize(
    "path",
    [
        "scripts/quality/run_owned_redis_contracts.py",
        "tests/test_aud427_428_contract_quality.py",
        ".github/workflows/reusable-backend-tests.yml",
    ],
)
def test_still_live_scanner_sources_keep_their_exact_reviewed_bytes(path: str) -> None:
    # Frozen provenance must not conceal a change to a still-live source.
    root = Path(__file__).resolve().parents[1]
    actual = (root / path).read_bytes()
    if path == ".github/workflows/reusable-backend-tests.yml":
        # The reviewed parser fix moved the exact run bodies to sourced helpers.
        # The companion workflow contract checks their shell, env and argv.
        assert hashlib.sha256(actual).digest() == bytes(
            (
                58,
                105,
                19,
                29,
                192,
                199,
                196,
                198,
                99,
                52,
                60,
                136,
                2,
                126,
                58,
                58,
                125,
                130,
                50,
                129,
                225,
                0,
                44,
                106,
                231,
                76,
                150,
                186,
                154,
                214,
                213,
                19,
            )
        ), "reviewed parser-friendly workflow bytes changed"
    else:
        _assert_live_scanner_source_bytes(path, actual)


@pytest.mark.parametrize("mutation", ["call-site", "helper-location", "appended-byte"])
def test_aud427_428_current_source_binding_rejects_mutations(mutation: str) -> None:
    path = "tests/test_aud427_428_contract_quality.py"
    reviewed = _reviewed_live_scanner_source_bytes(path)
    if mutation == "call-site":
        anchor = b'    assert run.strip() == ". ./scripts/ci/backend-run-integration-tests.ps1"'
        replacement = b'    assert run.strip() == "uv run pytest @pytestArgs"'
        assert reviewed.count(anchor) == 1
        mutated = reviewed.replace(anchor, replacement, 1)
    elif mutation == "helper-location":
        anchor = b"    assert launcher in wrapper"
        replacement = b"    assert launcher in run"
        assert reviewed.count(anchor) == 1
        mutated = reviewed.replace(anchor, replacement, 1)
    else:
        mutated = reviewed + b"\n"
    assert mutated != reviewed
    with pytest.raises(AssertionError, match="exact reviewed bytes"):
        _assert_live_scanner_source_bytes(path, mutated)


def test_aud427_428_current_source_context_pins_sourced_helper_invocation() -> None:
    reviewed = _reviewed_live_scanner_source_bytes(
        "tests/test_aud427_428_contract_quality.py"
    )
    assert (
        b'    assert run.strip() == ". ./scripts/ci/backend-run-integration-tests.ps1"'
        in reviewed
    )
    assert b"    assert launcher in wrapper" in reviewed
    assert b"    assert launcher in run" not in reviewed


def _reviewed_live_aud447_allocation_function() -> ast.FunctionDef:
    path = "tests/test_quality_workflow_contract.py"
    name = "_assert_aud447_owned_postgres_allocation"
    historical = ast.parse(_pre_squash_source_text(path))
    expected = [
        node
        for node in historical.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    assert len(expected) == 1
    reviewed = copy.deepcopy(expected[0])
    reviewed.args.args.append(
        ast.arg(arg="helper_source", annotation=ast.Name(id="str", ctx=ast.Load()))
    )
    moved_pattern_assertions = [
        statement
        for statement in reviewed.body
        if isinstance(statement, ast.Assert)
        and isinstance(statement.test, ast.Compare)
        and isinstance(statement.test.left, ast.Constant)
        and statement.test.left.value == "$env:INTEGRATION_TEST_PATTERN"
    ]
    assert len(moved_pattern_assertions) == 1
    reviewed.body.remove(moved_pattern_assertions[0])
    reviewed.body.insert(
        2,
        ast.Expr(
            value=ast.Call(
                func=ast.Name(id="_assert_backend_integration_helper", ctx=ast.Load()),
                args=[
                    ast.Name(id="step", ctx=ast.Load()),
                    ast.Name(id="helper_source", ctx=ast.Load()),
                    ast.Name(id="workflow", ctx=ast.Load()),
                ],
                keywords=[],
            )
        ),
    )
    reviewed.body[-1] = ast.Assert(
        test=ast.Compare(
            left=ast.Constant(
                value="--ignore=tests/integration/test_aud447_dlq_auth_scrub_postgres.py"
            ),
            ops=[ast.NotIn()],
            comparators=[ast.Name(id="helper_source", ctx=ast.Load())],
        ),
        msg=None,
    )
    return ast.fix_missing_locations(reviewed)


def _assert_live_aud447_allocation_source(source: str) -> None:
    expected = _reviewed_live_aud447_allocation_function()
    current = ast.parse(source)
    actual = [
        node
        for node in current.body
        if isinstance(node, ast.FunctionDef) and node.name == expected.name
    ]
    assert len(actual) == 1
    assert ast.dump(actual[0]) == ast.dump(expected)


def test_live_aud447_allocation_source_keeps_exact_reviewed_scope() -> None:
    # Other workflow contracts evolved; the approved live sentinel's complete
    # allocation function must remain unchanged, not merely its literal value.
    root = Path(__file__).resolve().parents[1]
    source = (root / "tests/test_quality_workflow_contract.py").read_text(
        encoding="utf-8"
    )
    _assert_live_aud447_allocation_source(source)


@pytest.mark.parametrize("mutation", ["renamed", "duplicate", "changed", "removed"])
def test_live_aud447_allocation_binding_refuses_changed_scope(mutation: str) -> None:
    source = ast.unparse(_reviewed_live_aud447_allocation_function())
    tree = ast.parse(source)
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_assert_aud447_owned_postgres_allocation"
    )
    if mutation == "renamed":
        function.name = "unreviewed_allocation"
    elif mutation == "duplicate":
        tree.body.append(copy.deepcopy(function))
    elif mutation == "changed":
        function.body.append(ast.Pass())
    else:
        tree.body.remove(function)
    with pytest.raises(AssertionError):
        _assert_live_aud447_allocation_source(
            ast.unparse(ast.fix_missing_locations(tree))
        )


def test_pre_squash_scanner_source_requires_installed_git(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("Subprocess must not run without Git")

    monkeypatch.setattr(subprocess, "run", forbidden)
    with pytest.raises(pytest.fail.Exception, match="Git executable is required"):
        _pre_squash_source_bytes(next(iter(_PRE_SQUASH_SOURCE_BLOBS)))


# Independently recorded exact owner approval; the older504 records are unchanged.
def _nov2_workflow_binding_record() -> dict[str, Any]:
    return {
        "identity": {
            "path": "tests/test_verify_secrets_baseline.py",
            "type": "Hex High Entropy String",
            "hashed_secret_bytes": [
                244,
                50,
                31,
                105,
                80,
                18,
                33,
                30,
                183,
                134,
                78,
                182,
                238,
                65,
                118,
                170,
                130,
                66,
                138,
                133,
            ],
        },
        "category": "public_integrity_digest",
        "evidence": "Public repository commit for the reviewed setup-python workflow pin update; exact source reference tests/test_verify_secrets_baseline.py field _REVIEWED_SOURCE_COMMIT_OVERRIDES for .github/workflows/reusable-backend-tests.yml. Identity derived using pinned detect-secrets 1.5.0 SHA-1; not credential material.",
        "owner": "egorribun",
        "reviewed_on": "2026-11-02",
        "expires_on": "2027-01-09",
        "approval_status": "approved",
    }


def test_nov2_workflow_binding_appends_only_one_and_preserves_504() -> None:
    policy = _oct30_policy()
    assert len(policy["records"]) == 505
    encoded = json.dumps(
        policy["records"][:504],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    assert hashlib.sha256(encoded).digest() == bytes(
        (
            233,
            57,
            129,
            156,
            205,
            251,
            73,
            248,
            21,
            183,
            234,
            18,
            38,
            231,
            181,
            23,
            43,
            240,
            129,
            115,
            78,
            249,
            7,
            123,
            119,
            33,
            58,
            112,
            180,
            254,
            183,
            226,
        )
    )
    assert policy["records"][504:] == [_nov2_workflow_binding_record()]
    record = _nov2_workflow_binding_record()
    assert hashlib.sha1(
        _REVIEWED_SOURCE_COMMIT_OVERRIDES[
            ".github/workflows/reusable-backend-tests.yml"
        ].encode("ascii"),
        usedforsecurity=False,
    ).digest() == bytes(record["identity"]["hashed_secret_bytes"])
    assert (
        len(
            _nov13_verify_dispositions(
                {**policy, "records": _nov4_current_view(policy["records"])},
                today=verifier.date(2026, 11, 2),
            )
        )
        == 505
    )
    older_same_path = [
        row
        for row in policy["records"][:504]
        if row["identity"]["path"] == record["identity"]["path"]
    ]
    assert len(older_same_path) == 3
    assert (
        len(
            _nov13_verify_dispositions(
                _disposition_document(*older_same_path),
                today=verifier.date(2026, 11, 2),
            )
        )
        == 3
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "path",
        "type",
        "digest",
        "category",
        "evidence",
        "owner",
        "reviewed_on",
        "expires_on",
        "approval_status",
        "wildcard",
    ],
)
def test_nov2_workflow_binding_refuses_scope_or_approval_drift(mutation: str) -> None:
    row = _nov2_workflow_binding_record()
    if mutation == "path":
        row["identity"]["path"] += ".other"
    elif mutation == "type":
        row["identity"]["type"] = "Base64 High Entropy String"
    elif mutation == "digest":
        row["identity"]["hashed_secret_bytes"][0] ^= 1
    elif mutation == "wildcard":
        row["identity"]["path"] = "tests/*"
    else:
        row[mutation] = {
            "category": "independent_contract_fingerprint",
            "evidence": row["evidence"] + " broadened",
            "owner": "other-owner",
            "reviewed_on": "2026-11-01",
            "expires_on": "2027-01-10",
            "approval_status": "pending",
        }[mutation]
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(row), today=verifier.date(2026, 11, 2)
        )


@pytest.mark.parametrize(
    ("today", "accepted"),
    [
        (verifier.date(2026, 11, 1), False),
        (verifier.date(2026, 11, 2), True),
        (verifier.date(2027, 1, 9), True),
        (verifier.date(2027, 1, 10), False),
    ],
)
def test_nov2_workflow_binding_keeps_existing_exclusive_expiry(
    today: verifier.date, accepted: bool
) -> None:
    policy = _disposition_document(_nov2_workflow_binding_record())
    if accepted:
        assert len(_nov13_verify_dispositions(policy, today=today)) == 1
    else:
        with pytest.raises(verifier.BaselineArtifactError):
            _nov13_verify_dispositions(policy, today=today)


@pytest.mark.parametrize("retired_path", sorted(_RETIRED_DISPOSITION_PATHS))
def test_candidate_loader_never_reactivates_a_retired_source(
    tmp_path: Path, retired_path: str
) -> None:
    historical = _reviewed_pre_retirement_dispositions()
    rows = [
        row for row in historical["records"] if row["identity"]["path"] == retired_path
    ]
    assert rows
    today = verifier.date(2026, 11, 2)
    # Historical metadata remains independently valid; activation is denied.
    assert len(
        _nov13_verify_dispositions(_disposition_document(*rows), today=today)
    ) == len(rows)
    policy_path = tmp_path / "quality/security-false-positive-dispositions.json"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(json.dumps(_disposition_document(*rows)), encoding="utf-8")
    with pytest.raises(verifier.BaselineArtifactError, match="retired source"):
        verifier.load_owner_authored_candidate_false_positive_dispositions(
            repository_root=tmp_path, today=today
        )
    # Recreating a removed path never expands the finite authorization set.
    source = tmp_path / retired_path
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("recreated source", encoding="utf-8")
    with pytest.raises(verifier.BaselineArtifactError, match="retired source"):
        verifier.load_owner_authored_candidate_false_positive_dispositions(
            repository_root=tmp_path, today=today
        )


def test_trusted_pre_retirement_policy_keeps_only_exact_live_survivors(
    tmp_path: Path,
) -> None:
    policy = _reviewed_pre_retirement_dispositions()
    policy = {**policy, "records": _nov4_current_view(policy["records"])}
    repository, _ = _new_git_fixture(tmp_path)
    accepted_sha = _commit_dispositions(repository, policy["records"])
    today = verifier.date(2026, 11, 2)
    expected = _nov13_verify_dispositions(
        _disposition_document(
            *[
                row
                for row in policy["records"]
                if row["identity"]["path"] not in _RETIRED_DISPOSITION_PATHS
            ]
        ),
        today=today,
    )
    assert len(expected) == 349
    assert (
        verifier.load_trusted_base_false_positive_dispositions(
            accepted_sha, repository_root=repository, today=today
        )
        == expected
    )
    # Retired records are validated before filtering, never silently forgiven.
    with pytest.raises(verifier.BaselineArtifactError):
        verifier.load_trusted_base_false_positive_dispositions(
            accepted_sha, repository_root=repository, today=verifier.date(2027, 1, 11)
        )


@pytest.mark.parametrize("record", _nov2_chart_reference_records())
def test_nov2_chart_reference_exact_scope(record: dict[str, Any]) -> None:
    assert len(verifier._NOV2_CHART_REFERENCE_EVIDENCE) == 2
    assert (
        len(
            verifier._FALSE_POSITIVE_EXACT_CATEGORY_IDENTITIES[
                "external_kubernetes_secret_reference"
            ]
        )
        == _AUD380_CURRENT_DELTA_CATEGORY_COUNTS["external_kubernetes_secret_reference"]
    )
    accepted = _nov13_verify_dispositions(
        _disposition_document(record), today=verifier.date(2027, 1, 9)
    )
    assert len(accepted) == 1
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(record), today=verifier.date(2027, 1, 10)
        )


@pytest.mark.parametrize("record", _nov2_chart_reference_records())
@pytest.mark.parametrize(
    "field",
    [
        "path",
        "type",
        "digest",
        "category",
        "evidence",
        "owner",
        "reviewed_on",
        "expires_on",
        "approval_status",
    ],
)
def test_nov2_chart_reference_rejects_mutation(
    record: dict[str, Any], field: str
) -> None:
    changed = copy.deepcopy(record)
    if field in {"path", "type"}:
        changed["identity"][field] += "-unreviewed"
    elif field == "digest":
        changed["identity"]["hashed_secret_bytes"][0] ^= 1
    else:
        changed[field] = "2027-01-10" if field == "expires_on" else "unreviewed"
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(changed), today=verifier.date(2026, 11, 2)
        )


@pytest.mark.parametrize(
    ("filename", "field", "value", "digest_bytes"),
    [
        (
            "values-staging.yaml",
            "privateKeyKey",
            "tls.key",
            (
                186,
                196,
                166,
                53,
                205,
                238,
                100,
                52,
                204,
                177,
                241,
                191,
                64,
                57,
                254,
                78,
                225,
                214,
                206,
                73,
            ),
        ),
        (
            "values.yaml",
            "privateKeyKey",
            "tls.key",
            (
                186,
                196,
                166,
                53,
                205,
                238,
                100,
                52,
                204,
                177,
                241,
                191,
                64,
                57,
                254,
                78,
                225,
                214,
                206,
                73,
            ),
        ),
    ],
)
def test_nov2_chart_reference_source_values(
    filename: str, field: str, value: str, digest_bytes: tuple[int, ...]
) -> None:
    import yaml

    root = Path(__file__).resolve().parents[1]
    path = f"charts/university-ecosystem/{filename}"
    document = yaml.safe_load((root / path).read_text(encoding="utf-8"))
    assert "backendServer" not in document["internalHttpMTLS"]
    assert "university-internal-http-backend-server" not in (root / path).read_text(
        encoding="utf-8"
    )
    for consumer in ("gatewayClient", "fileProcessorServer"):
        assert document["internalGrpcMTLS"][consumer][field] == value
    assert (
        tuple(hashlib.sha1(value.encode("utf-8"), usedforsecurity=False).digest())
        == digest_bytes
    )
    assert (
        path,
        "Secret Keyword",
        digest_bytes,
    ) in verifier._NOV2_CHART_REFERENCE_EVIDENCE


def test_nov2_removed_backend_secret_reference_is_not_approved() -> None:
    record = {
        "identity": {
            "path": "charts/university-ecosystem/values-staging.yaml",
            "type": "Secret Keyword",
            "hashed_secret_bytes": [
                137,
                48,
                149,
                253,
                216,
                125,
                70,
                132,
                49,
                17,
                188,
                104,
                56,
                234,
                54,
                223,
                41,
                47,
                61,
                125,
            ],
        },
        "category": "external_kubernetes_secret_reference",
        "evidence": "Kubernetes external Secret object name or key reference; not credential material. Public internal HTTP mTLS existingSecret reference at charts/university-ecosystem/values-staging.yaml:56; source reviewed at 476f42e58fe780254c0a3bc92f104bf064cb4472.",
        "owner": "egorribun",
        "reviewed_on": "2026-11-02",
        "expires_on": "2027-01-09",
        "approval_status": "approved",
    }
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(record), today=verifier.date(2026, 11, 2)
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-service",
        "missing-step",
        "changed-port",
        "changed-command",
        "duplicate-service",
        "duplicate-step",
        "unrelated",
    ],
)
def test_live_aud363_binding_refuses_other_changes(mutation: str) -> None:
    path = ".github/workflows/reusable-backend-tests.yml"
    expected = _reviewed_live_scanner_source_bytes(path)
    assert expected.count(_AUD363_SERVICE) == expected.count(_AUD363_STEP) == 1
    _assert_live_scanner_source_bytes(path, expected)
    if mutation == "missing-service":
        invalid = expected.replace(_AUD363_SERVICE, b"", 1)
    elif mutation == "missing-step":
        invalid = expected.replace(_AUD363_STEP, b"", 1)
    elif mutation == "changed-port":
        invalid = expected.replace(b"127.0.0.1:15432:5432", b"127.0.0.1:15433:5432", 1)
    elif mutation == "changed-command":
        invalid = expected.replace(
            b"run_aud363_borrowed_postgres.py", b"unexpected.py", 1
        )
    elif mutation == "duplicate-service":
        invalid = expected.replace(_AUD363_SERVICE, _AUD363_SERVICE * 2, 1)
    elif mutation == "duplicate-step":
        invalid = expected.replace(_AUD363_STEP, _AUD363_STEP * 2, 1)
    else:
        invalid = expected + b"# unrelated workflow change\n"
    with pytest.raises(AssertionError, match="exact reviewed bytes"):
        _assert_live_scanner_source_bytes(path, invalid)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-setup",
        "missing-validation",
        "changed-guard",
        "changed-test",
        "allow-skips",
        "ignore-exit",
        "duplicate-validation",
        "unrelated",
    ],
)
def test_live_postgres_receipt_binding_refuses_other_changes(mutation: str) -> None:
    path = ".github/workflows/reusable-backend-tests.yml"
    expected = _reviewed_live_scanner_source_bytes(path)
    setup = _POSTGRES_RECEIPT_SETUP
    validation = _POSTGRES_RECEIPT_VALIDATION
    assert expected.count(setup) == expected.count(validation) == 1
    _assert_live_scanner_source_bytes(path, expected)

    def replace_once(source: bytes, old: bytes, new: bytes) -> bytes:
        assert source.count(old) == 1
        return source.replace(old, new, 1)

    if mutation == "missing-setup":
        invalid = replace_once(expected, setup, b"")
    elif mutation == "missing-validation":
        invalid = replace_once(expected, validation, b"")
    elif mutation == "changed-guard":
        changed = replace_once(
            setup, b"$integrationNumShards -eq 1", b"$integrationNumShards -eq 2"
        )
        invalid = replace_once(expected, setup, changed)
    elif mutation == "changed-test":
        changed = replace_once(
            validation,
            b"test_proof_owned_fixture_never_uses_default_database",
            b"test_unreviewed_proof",
        )
        invalid = replace_once(expected, validation, changed)
    elif mutation == "allow-skips":
        changed = replace_once(
            validation,
            b'for status in ("skipped", "failure", "error")',
            b'for status in ("failure", "error")',
        )
        invalid = replace_once(expected, validation, changed)
    elif mutation == "ignore-exit":
        changed = replace_once(
            validation,
            b"                  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }\n"
            b"                  if ($requireBaselineReceipt) {\n",
            b"                  if ($requireBaselineReceipt) {\n",
        )
        invalid = replace_once(expected, validation, changed)
    elif mutation == "duplicate-validation":
        invalid = replace_once(expected, validation, validation + validation)
    else:
        invalid = expected + b"# unrelated workflow change\n"
    assert invalid != expected
    with pytest.raises(AssertionError, match="exact reviewed bytes"):
        _assert_live_scanner_source_bytes(path, invalid)


def _aud380_history_repository_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if parent.name == ".git":
            return parent.parent
    return Path(__file__).resolve().parents[1]


def _aud380_bind_history_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    original_reader = _pre_squash_source_bytes
    history_root = _aud380_history_repository_root()

    def read_pinned_source(path: str, *, repository_root: Path | None = None) -> bytes:
        return original_reader(
            path,
            repository_root=repository_root or history_root,
        )

    monkeypatch.setattr(
        sys.modules[__name__], "_pre_squash_source_bytes", read_pinned_source
    )


def _aud380_read_live_policy() -> dict[str, Any]:
    policy_path = (
        Path(__file__).resolve().parents[1]
        / "quality/security-false-positive-dispositions.json"
    )
    policy_bytes = policy_path.read_bytes()
    policy = json.loads(policy_bytes.decode("utf-8"))
    _nov9_assert_live_policy_bytes(policy_bytes)
    return _nov11_historical_509_from_live_policy(policy)


def _aud380_assert_live_policy_is_exact_505(
    live_policy: dict[str, Any], historical_490: dict[str, Any]
) -> None:
    """Validate the exact 505-record prefix as of the 2026-11-06 snapshot."""
    live_records = live_policy.get("records")
    assert isinstance(live_records, list), "live disposition records changed"
    assert len(live_records) == 505, "historical 505-row prefix changed"
    expected_header = {
        key: value for key, value in historical_490.items() if key != "records"
    }
    actual_header = {
        key: value for key, value in live_policy.items() if key != "records"
    }
    assert actual_header == expected_header, "live disposition header changed"
    assert live_records[:490] == historical_490["records"], (
        "live approved 490-row prefix changed"
    )
    live_494 = {key: value for key, value in live_policy.items() if key != "records"}
    live_494["records"] = copy.deepcopy(live_records[:494])
    _assert_aud380_n4_conditional_policy(live_494, historical_490)
    live_495 = copy.deepcopy(live_494)
    live_495["records"] = copy.deepcopy(live_records[:495])
    _assert_aud380_n5_conditional_policy(live_495, live_494)
    live_497 = copy.deepcopy(live_495)
    live_497["records"] = copy.deepcopy(live_records[:497])
    _assert_aud380_n6_conditional_policy(live_497, live_495)
    assert live_records[497:505] == _NOV6_ZLIB_EXPECTED_RECORDS, (
        "approved zlib APK suffix changed"
    )
    accepted = _nov13_verify_dispositions(live_policy, today=verifier.date(2026, 11, 6))
    assert len(accepted) == 505, "historical approved disposition count changed"


def _aud380_historical_490_from_live_policy(
    live_policy: dict[str, Any],
) -> dict[str, Any]:
    live_policy = _nov9_historical_506_from_live_policy(live_policy)
    live_records = live_policy.get("records")
    assert isinstance(live_records, list), "live disposition records changed"
    assert len(live_records) == 506, "live disposition row count changed"

    history = _reviewed_pre_retirement_dispositions()
    expected_base_records = _aud380_expected_active_363(history)
    historical_490 = {
        key: value for key, value in live_policy.items() if key != "records"
    }
    historical_490["records"] = copy.deepcopy(live_records[:490])
    _assert_aud380_conditional_policy(historical_490, expected_base_records)
    _aud428_assert_live_policy_is_exact_506(live_policy, historical_490)
    return historical_490


def _aud380_conditional_policy() -> dict[str, Any]:
    """Return the exact historical 490 prefix after validating live 509 bytes."""
    return _aud380_historical_490_from_live_policy(_aud380_read_live_policy())


def _aud380_expected_active_363(history: dict[str, Any]) -> list[dict[str, Any]]:
    retired = [
        row
        for row in history["records"]
        if row["identity"]["path"] in _RETIRED_DISPOSITION_PATHS
    ]
    survivors = [
        row
        for row in history["records"]
        if row["identity"]["path"] not in _RETIRED_DISPOSITION_PATHS
    ]
    assert len(retired) == 156
    assert len(survivors) == 349
    records = [
        *_nov4_trivy_checksum_renewal(
            [
                *_nov4_trivy_ignore_policy_digest_rebind(survivors),
                *_nov2_chart_reference_records(),
                *_nov3_public_git_object_records(),
            ]
        ),
        _nov4_semgrep_rules_pin_record(),
        _nov4_spire_chart_pin_record(),
    ]
    assert len(records) == 363
    return records


def _assert_aud380_conditional_policy(
    policy: dict[str, Any], expected_base_records: list[dict[str, Any]]
) -> None:
    assert len(_AUD380_APPROVED_OWNER_ADDITIONS_SHA256) == 32
    assert len(_AUD380_PENDING_NEW_ADDITIONS_SHA256) == 32
    assert len(_AUD380_APPROVED_NEW_ADDITIONS_SHA256) == 32
    assert len(_AUD380_CONDITIONAL_RECORDSET_SHA256) == 32
    pending_records = copy.deepcopy(_AUD380_PENDING_OWNER_RECORDS)
    assert len(pending_records) == len(_AUD380_PENDING_OWNER_IDENTITIES)
    assert all(row["approval_status"] == "NOT_APPROVED" for row in pending_records)
    assert all(
        row["reviewed_on"] == "2026-11-06" and row["expires_on"] == "2027-01-10"
        for row in pending_records
    )
    assert Counter(row["category"] for row in pending_records) == Counter(
        _AUD380_CURRENT_DELTA_PENDING_CATEGORY_COUNTS
    )
    assert _aud380_canonical_records_digest(pending_records) == (
        _AUD380_PENDING_NEW_ADDITIONS_SHA256
    )
    assert {_aud380_identity_key(row) for row in pending_records} == set(
        _AUD380_PENDING_OWNER_IDENTITIES
    )

    _assert_conditional_owner_projection(
        policy,
        expected_base_records=expected_base_records,
        expected_new_addition_identities=_AUD380_PENDING_OWNER_IDENTITIES,
        expected_pending_new_addition_sha256=_AUD380_PENDING_NEW_ADDITIONS_SHA256,
        expected_new_addition_sha256=_AUD380_APPROVED_NEW_ADDITIONS_SHA256,
        expected_full_recordset_sha256=_AUD380_CONDITIONAL_RECORDSET_SHA256,
        expected_category_counts=_AUD380_CURRENT_DELTA_CATEGORY_COUNTS,
    )


def test_aud380_conditional_owner_projection_is_exact_current_delta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _aud380_bind_history_reader(monkeypatch)
    history = _reviewed_pre_retirement_dispositions()
    policy = _aud380_conditional_policy()
    _assert_aud380_conditional_policy(policy, _aud380_expected_active_363(history))
    accepted = _nov13_verify_dispositions(policy, today=verifier.date(2026, 11, 7))
    assert len(accepted) == 469 + len(_AUD380_PENDING_OWNER_IDENTITIES)


@pytest.mark.parametrize(
    "mutation",
    [
        "header",
        "base_record",
        "original106_metadata",
        "new_evidence",
        "new_category",
        "new_owner",
        "new_review_date",
        "new_expiry",
        "new_path",
        "new_type",
        "new_digest",
        "new_status",
        "missing_new_record",
        "unknown_new_record",
        "duplicate_new_record",
        "suffix_order",
    ],
)
def test_aud380_conditional_owner_projection_rejects_mutations(
    monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    _aud380_bind_history_reader(monkeypatch)
    history = _reviewed_pre_retirement_dispositions()
    expected_base_records = _aud380_expected_active_363(history)
    policy = copy.deepcopy(_aud380_conditional_policy())
    new_index = 469
    records = policy["records"]
    if mutation == "header":
        policy["schema_version"] = 2
    elif mutation == "base_record":
        records[0]["owner"] = "unreviewed-owner"
    elif mutation == "original106_metadata":
        records[363]["evidence"] += " changed"
    elif mutation == "new_evidence":
        secret_record = next(
            record
            for record in records[469:]
            if record["category"] == "external_kubernetes_secret_reference"
        )
        secret_record["evidence"] = secret_record["evidence"].replace(
            ".existingSecret", ".unreviewedSecret", 1
        )
    elif mutation == "new_category":
        category_record = next(
            record
            for record in records[469:]
            if record["category"] != "public_integrity_digest"
        )
        category_record["category"] = "public_integrity_digest"
    elif mutation == "new_owner":
        records[new_index]["owner"] = "unreviewed-owner"
    elif mutation == "new_review_date":
        records[new_index]["reviewed_on"] = "2026-11-05"
    elif mutation == "new_expiry":
        records[new_index]["expires_on"] = "2027-01-11"
    elif mutation == "new_path":
        records[new_index]["identity"]["path"] += ".unreviewed"
    elif mutation == "new_type":
        records[new_index]["identity"]["type"] = "unreviewed type"
    elif mutation == "new_digest":
        records[new_index]["identity"]["hashed_secret_bytes"][0] ^= 1
    elif mutation == "new_status":
        records[new_index]["approval_status"] = "NOT_APPROVED"
    elif mutation == "missing_new_record":
        records.pop(new_index)
    elif mutation == "unknown_new_record":
        records[new_index]["identity"]["path"] = "tests/unreviewed-new-source.py"
    elif mutation == "duplicate_new_record":
        records.append(copy.deepcopy(records[new_index]))
    else:
        records[363], records[364] = records[364], records[363]

    with pytest.raises(AssertionError):
        _assert_aud380_conditional_policy(policy, expected_base_records)


def test_aud380_new_owner_rows_keep_explicit_review_and_expiry_boundaries() -> None:
    policy = _aud380_conditional_policy()
    new_rows = copy.deepcopy(policy["records"][469:])
    assert len(new_rows) == len(_AUD380_PENDING_OWNER_IDENTITIES)
    pending_policy = {"schema_version": 1, "records": new_rows}
    for today in (verifier.date(2026, 11, 6), verifier.date(2027, 1, 10)):
        assert len(_nov13_verify_dispositions(pending_policy, today=today)) == len(
            new_rows
        )
    for today in (verifier.date(2026, 11, 5), verifier.date(2027, 1, 11)):
        with pytest.raises(verifier.BaselineArtifactError, match="date range"):
            _nov13_verify_dispositions(pending_policy, today=today)


def test_aud380_validator_requires_exact_kind_secret_reference_evidence() -> None:
    policy = _aud380_conditional_policy()
    new_rows = policy["records"][469:]
    secret_rows = [
        row
        for row in new_rows
        if row["category"] == "external_kubernetes_secret_reference"
    ]
    assert (
        len(secret_rows)
        == _AUD380_CURRENT_DELTA_PENDING_CATEGORY_COUNTS[
            "external_kubernetes_secret_reference"
        ]
    )
    for row in secret_rows:
        single_record_policy = {"schema_version": 1, "records": [row]}
        accepted = _nov13_verify_dispositions(
            single_record_policy, today=verifier.date(2026, 11, 7)
        )
        assert len(accepted) == 1

        evidence = row["evidence"]
        marker = "Kubernetes external Secret object name or key reference"
        assert marker in evidence
        changed_row = {
            **row,
            "evidence": evidence.replace(marker, "unbound.reference", 1),
        }
        with pytest.raises(verifier.BaselineArtifactError, match="evidence"):
            _nov13_verify_dispositions(
                {"schema_version": 1, "records": [changed_row]},
                today=verifier.date(2026, 11, 7),
            )


def test_aud380_conditional_source_bindings_and_mutations(
    tmp_path: Path,
) -> None:
    source_root = Path(__file__).resolve().parents[1]
    _assert_conditional_owner_source_bindings(source_root)

    changed_hashes = dict(_AUD380_CURRENT_DELTA_SOURCE_SHA256)
    first_source = sorted(changed_hashes)[0]
    changed_hashes[first_source] = (
        bytes([changed_hashes[first_source][0] ^ 1])
        + (changed_hashes[first_source][1:])
    )
    with pytest.raises(AssertionError, match="source hash bindings changed"):
        _assert_conditional_owner_source_bindings(
            source_root, source_sha256=changed_hashes
        )

    changed_identity_lines = list(_AUD380_CURRENT_DELTA_IDENTITY_SOURCE_LINES)
    identity_line = changed_identity_lines[0]
    changed_identity_lines[0] = (*identity_line[:-1], identity_line[-1] + 1)
    with pytest.raises(AssertionError, match="identity line bindings changed"):
        _assert_conditional_owner_source_bindings(
            source_root,
            identity_source_lines=tuple(changed_identity_lines),
        )

    changed_companion_lines = list(_AUD380_CURRENT_DELTA_COMPANION_SOURCE_LINES)
    companion_line = changed_companion_lines[0]
    changed_companion_lines[0] = (companion_line[0], companion_line[1] + 1)
    with pytest.raises(AssertionError, match="companion line bindings changed"):
        _assert_conditional_owner_source_bindings(
            source_root,
            companion_source_lines=tuple(changed_companion_lines),
        )

    changed_line_hashes = list(_AUD380_CURRENT_DELTA_SOURCE_LINE_HASHES)
    line_hash = changed_line_hashes[0]
    changed_line_hashes[0] = (
        *line_hash[:-1],
        bytes([line_hash[-1][0] ^ 1]) + line_hash[-1][1:],
    )
    with pytest.raises(AssertionError, match="source line hash bindings changed"):
        _assert_conditional_owner_source_bindings(
            source_root,
            source_line_hashes=tuple(changed_line_hashes),
        )

    changed_replaced_lines = list(_AUD380_N21_REPLACED_IDENTITY_SOURCE_LINES)
    replaced_line = changed_replaced_lines[0]
    changed_replaced_lines[0] = (*replaced_line[:-1], replaced_line[-1] + 1)
    with pytest.raises(
        AssertionError, match="historical N21 replacement identity bindings changed"
    ):
        _assert_conditional_owner_source_bindings(
            source_root,
            replaced_identity_source_lines=tuple(changed_replaced_lines),
        )

    changed_replacement_targets = list(_AUD380_N21_REPLACED_COMPANION_TARGETS)
    path, line_number, target_path = changed_replacement_targets[0]
    changed_replacement_targets[0] = (path, line_number, target_path + ".unreviewed")
    with pytest.raises(
        AssertionError, match="historical N21 replacement companion bindings changed"
    ):
        _assert_conditional_owner_source_bindings(
            source_root,
            replaced_companion_targets=tuple(changed_replacement_targets),
        )

    changed_source_targets = list(_AUD380_CI58_COMPANION_SOURCE_TARGETS)
    path, line_number, target_path = changed_source_targets[0]
    changed_source_targets[0] = (path, line_number, target_path + ".unreviewed")
    with pytest.raises(AssertionError, match="CI58 companion source bindings changed"):
        _assert_conditional_owner_source_bindings(
            source_root, companion_source_targets=tuple(changed_source_targets)
        )

    mutated_root = tmp_path
    for relative_path in _AUD380_CURRENT_DELTA_SOURCE_SHA256:
        target = mutated_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((source_root / relative_path).read_bytes())
    mutated_path = mutated_root / first_source
    mutated_path.write_bytes(mutated_path.read_bytes() + b"\n# source drift control\n")
    with pytest.raises(AssertionError, match="source file SHA-256 changed"):
        _assert_conditional_owner_source_bindings(mutated_root)


# AUD380 N3 conditional owner delta. These rows remain pending and inactive.
_AUD380_N3_PENDING_OWNER_RECORDS = [
    {
        "approval_status": "NOT_APPROVED",
        "category": "ci_test_contract_sentinel",
        "evidence": "Test-only CI contract sentinel: fixed mocked user.hashed_password "
        "output equality in test_owned_seed_uses_an_explicit_test_password at "
        "tests/test_seed_demo_data.py:112. It is deterministic seed-unit test "
        "data, not a runtime authentication input or external credential; not "
        "credential material.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                95,
                180,
                135,
                74,
                188,
                185,
                142,
                12,
                51,
                173,
                10,
                211,
                168,
                117,
                247,
                144,
                131,
                222,
                96,
                33,
            ],
            "path": "tests/test_seed_demo_data.py",
            "type": "Secret Keyword",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
    {
        "approval_status": "NOT_APPROVED",
        "category": "ci_test_contract_sentinel",
        "evidence": "Test-only CI contract sentinel: replaceable administrator-side shell "
        "template marker in the fake CLI contract fixture at "
        "tests/test_temporal_namespace_init_fake_cli.py:45. It is substituted "
        "test data, not an authentication input or runtime credential; not "
        "credential material.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                5,
                7,
                180,
                175,
                200,
                103,
                100,
                106,
                164,
                44,
                199,
                230,
                34,
                191,
                164,
                53,
                52,
                135,
                142,
                180,
            ],
            "path": "tests/test_temporal_namespace_init_fake_cli.py",
            "type": "Secret Keyword",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
    {
        "approval_status": "NOT_APPROVED",
        "category": "ci_test_contract_sentinel",
        "evidence": "Test-only CI contract sentinel: replaceable worker-side shell template "
        "marker in the fake CLI contract fixture at "
        "tests/test_temporal_namespace_init_fake_cli.py:41. It is substituted "
        "test data, not an authentication input or runtime credential; not "
        "credential material.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                27,
                153,
                57,
                99,
                96,
                18,
                95,
                133,
                152,
                102,
                91,
                168,
                40,
                71,
                175,
                76,
                96,
                207,
                38,
                11,
            ],
            "path": "tests/test_temporal_namespace_init_fake_cli.py",
            "type": "Secret Keyword",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
]
_AUD380_N4_PENDING_OWNER_RECORDS = [
    {
        "approval_status": "NOT_APPROVED",
        "category": "public_integrity_digest",
        "evidence": "Public source-integrity metadata; exact source reference "
        "`quality/semgrep-dispositions.json:189`, Semgrep row 7 companion "
        "SHA-256 for `scripts/live_stand.py`. The value is a repository source "
        "digest, not credential material.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                166,
                110,
                177,
                206,
                147,
                218,
                249,
                66,
                1,
                241,
                95,
                73,
                8,
                215,
                24,
                86,
                67,
                165,
                227,
                57,
            ],
            "path": "quality/semgrep-dispositions.json",
            "type": "Hex High Entropy String",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
    {
        "approval_status": "NOT_APPROVED",
        "category": "ci_test_contract_sentinel",
        "evidence": "Test-only CI contract sentinel: fixed mocked user.hashed_password "
        "output equality in test_owned_seed_uses_an_explicit_test_password at "
        "tests/test_seed_demo_data.py:112. It is deterministic seed-unit test "
        "data, not a runtime authentication input or external credential; not "
        "credential material.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                95,
                180,
                135,
                74,
                188,
                185,
                142,
                12,
                51,
                173,
                10,
                211,
                168,
                117,
                247,
                144,
                131,
                222,
                96,
                33,
            ],
            "path": "tests/test_seed_demo_data.py",
            "type": "Secret Keyword",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
    {
        "approval_status": "NOT_APPROVED",
        "category": "ci_test_contract_sentinel",
        "evidence": "Test-only CI contract sentinel: replaceable administrator-side shell "
        "template marker in the fake CLI contract fixture at "
        "tests/test_temporal_namespace_init_fake_cli.py:45. It is substituted "
        "test data, not an authentication input or runtime credential; not "
        "credential material.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                5,
                7,
                180,
                175,
                200,
                103,
                100,
                106,
                164,
                44,
                199,
                230,
                34,
                191,
                164,
                53,
                52,
                135,
                142,
                180,
            ],
            "path": "tests/test_temporal_namespace_init_fake_cli.py",
            "type": "Secret Keyword",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
    {
        "approval_status": "NOT_APPROVED",
        "category": "ci_test_contract_sentinel",
        "evidence": "Test-only CI contract sentinel: replaceable worker-side shell template "
        "marker in the fake CLI contract fixture at "
        "tests/test_temporal_namespace_init_fake_cli.py:41. It is substituted "
        "test data, not an authentication input or runtime credential; not "
        "credential material.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                27,
                153,
                57,
                99,
                96,
                18,
                95,
                133,
                152,
                102,
                91,
                168,
                40,
                71,
                175,
                76,
                96,
                207,
                38,
                11,
            ],
            "path": "tests/test_temporal_namespace_init_fake_cli.py",
            "type": "Secret Keyword",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
]
_AUD380_N3_PENDING_OWNER_IDENTITIES = frozenset(
    (
        (
            "tests/test_seed_demo_data.py",
            "Secret Keyword",
            (
                95,
                180,
                135,
                74,
                188,
                185,
                142,
                12,
                51,
                173,
                10,
                211,
                168,
                117,
                247,
                144,
                131,
                222,
                96,
                33,
            ),
        ),
        (
            "tests/test_temporal_namespace_init_fake_cli.py",
            "Secret Keyword",
            (
                5,
                7,
                180,
                175,
                200,
                103,
                100,
                106,
                164,
                44,
                199,
                230,
                34,
                191,
                164,
                53,
                52,
                135,
                142,
                180,
            ),
        ),
        (
            "tests/test_temporal_namespace_init_fake_cli.py",
            "Secret Keyword",
            (
                27,
                153,
                57,
                99,
                96,
                18,
                95,
                133,
                152,
                102,
                91,
                168,
                40,
                71,
                175,
                76,
                96,
                207,
                38,
                11,
            ),
        ),
    )
)
_AUD380_N4_PUBLIC_LEDGER_IDENTITY = (
    "quality/semgrep-dispositions.json",
    "Hex High Entropy String",
    (
        166,
        110,
        177,
        206,
        147,
        218,
        249,
        66,
        1,
        241,
        95,
        73,
        8,
        215,
        24,
        86,
        67,
        165,
        227,
        57,
    ),
)
_AUD380_N4_PENDING_OWNER_IDENTITIES = frozenset(
    {*_AUD380_N3_PENDING_OWNER_IDENTITIES, _AUD380_N4_PUBLIC_LEDGER_IDENTITY}
)
_AUD380_N4_PENDING_ADDITIONS_SHA256 = bytes(
    (
        126,
        187,
        40,
        152,
        0,
        194,
        161,
        137,
        135,
        213,
        168,
        66,
        92,
        137,
        247,
        129,
        54,
        81,
        121,
        157,
        219,
        119,
        189,
        139,
        191,
        72,
        241,
        17,
        255,
        200,
        174,
        199,
    )
)

_AUD380_N3_PENDING_CATEGORY_COUNTS = {"ci_test_contract_sentinel": 3}
_AUD380_N3_PENDING_ADDITIONS_SHA256 = bytes(
    (
        174,
        27,
        118,
        30,
        112,
        101,
        146,
        19,
        229,
        188,
        212,
        0,
        117,
        8,
        18,
        179,
        202,
        14,
        182,
        214,
        254,
        155,
        10,
        52,
        134,
        45,
        53,
        97,
        148,
        10,
        176,
        135,
    )
)
_AUD380_N3_APPROVED_ADDITIONS_SHA256 = bytes(
    (
        135,
        203,
        117,
        186,
        43,
        193,
        153,
        134,
        55,
        15,
        19,
        10,
        241,
        184,
        220,
        116,
        166,
        35,
        177,
        8,
        26,
        139,
        25,
        252,
        84,
        224,
        172,
        167,
        129,
        0,
        126,
        218,
    )
)
_AUD380_N3_PENDING_493_RECORDSET_SHA256 = bytes(
    (
        53,
        70,
        209,
        114,
        123,
        183,
        235,
        86,
        2,
        210,
        122,
        91,
        39,
        13,
        22,
        147,
        199,
        52,
        250,
        203,
        231,
        151,
        180,
        139,
        230,
        226,
        183,
        42,
        202,
        79,
        41,
        162,
    )
)
_AUD380_N3_CONDITIONAL_493_RECORDSET_SHA256 = bytes(
    (
        60,
        143,
        77,
        2,
        150,
        103,
        245,
        69,
        214,
        129,
        157,
        102,
        90,
        86,
        104,
        214,
        12,
        235,
        23,
        181,
        146,
        184,
        90,
        72,
        105,
        80,
        26,
        176,
        83,
        219,
        176,
        79,
    )
)
_AUD380_N3_SOURCE_SHA256 = {
    "tests/test_seed_demo_data.py": bytes(
        (
            158,
            118,
            66,
            16,
            195,
            83,
            13,
            66,
            116,
            173,
            254,
            114,
            96,
            246,
            179,
            54,
            66,
            15,
            5,
            193,
            163,
            231,
            79,
            77,
            211,
            9,
            142,
            172,
            44,
            234,
            51,
            206,
        )
    ),
    "tests/test_temporal_namespace_init_fake_cli.py": bytes(
        (
            116,
            30,
            99,
            150,
            71,
            223,
            210,
            237,
            164,
            46,
            114,
            82,
            160,
            149,
            4,
            65,
            60,
            136,
            221,
            129,
            142,
            111,
            36,
            41,
            94,
            173,
            124,
            92,
            12,
            4,
            190,
            163,
        )
    ),
}
_AUD380_N3_IDENTITY_SOURCE_LINES = (
    (
        "tests/test_seed_demo_data.py",
        "Secret Keyword",
        (
            95,
            180,
            135,
            74,
            188,
            185,
            142,
            12,
            51,
            173,
            10,
            211,
            168,
            117,
            247,
            144,
            131,
            222,
            96,
            33,
        ),
        "ci_test_contract_sentinel",
        112,
    ),
    (
        "tests/test_temporal_namespace_init_fake_cli.py",
        "Secret Keyword",
        (
            5,
            7,
            180,
            175,
            200,
            103,
            100,
            106,
            164,
            44,
            199,
            230,
            34,
            191,
            164,
            53,
            52,
            135,
            142,
            180,
        ),
        "ci_test_contract_sentinel",
        45,
    ),
    (
        "tests/test_temporal_namespace_init_fake_cli.py",
        "Secret Keyword",
        (
            27,
            153,
            57,
            99,
            96,
            18,
            95,
            133,
            152,
            102,
            91,
            168,
            40,
            71,
            175,
            76,
            96,
            207,
            38,
            11,
        ),
        "ci_test_contract_sentinel",
        41,
    ),
)
_AUD380_N3_SOURCE_LINE_HASHES = (
    (
        "tests/test_seed_demo_data.py",
        112,
        bytes(
            (
                40,
                85,
                172,
                159,
                248,
                155,
                29,
                5,
                95,
                156,
                33,
                13,
                240,
                181,
                142,
                125,
                150,
                83,
                83,
                169,
                40,
                43,
                138,
                195,
                62,
                76,
                122,
                112,
                95,
                232,
                91,
                16,
            )
        ),
        bytes(
            (
                29,
                58,
                151,
                107,
                191,
                10,
                41,
                4,
                74,
                49,
                50,
                138,
                88,
                112,
                51,
                182,
                172,
                251,
                79,
                224,
                249,
                21,
                255,
                49,
                86,
                135,
                65,
                138,
                183,
                43,
                25,
                238,
            )
        ),
    ),
    (
        "tests/test_temporal_namespace_init_fake_cli.py",
        45,
        bytes(
            (
                152,
                189,
                127,
                123,
                113,
                85,
                231,
                147,
                37,
                71,
                138,
                87,
                247,
                39,
                116,
                32,
                89,
                19,
                237,
                202,
                221,
                239,
                68,
                19,
                120,
                122,
                128,
                72,
                57,
                132,
                203,
                164,
            )
        ),
        bytes(
            (
                222,
                82,
                179,
                35,
                202,
                255,
                42,
                74,
                139,
                50,
                3,
                207,
                163,
                210,
                103,
                76,
                194,
                58,
                140,
                31,
                249,
                216,
                205,
                163,
                70,
                241,
                220,
                151,
                184,
                65,
                37,
                48,
            )
        ),
    ),
    (
        "tests/test_temporal_namespace_init_fake_cli.py",
        41,
        bytes(
            (
                202,
                187,
                39,
                119,
                255,
                15,
                213,
                226,
                2,
                241,
                18,
                68,
                234,
                223,
                40,
                85,
                241,
                148,
                94,
                50,
                204,
                224,
                18,
                60,
                16,
                94,
                42,
                38,
                53,
                143,
                196,
                95,
            )
        ),
        bytes(
            (
                247,
                223,
                224,
                132,
                72,
                145,
                23,
                130,
                58,
                151,
                71,
                136,
                238,
                40,
                219,
                236,
                58,
                94,
                90,
                57,
                193,
                172,
                3,
                110,
                13,
                78,
                135,
                127,
                75,
                9,
                104,
                149,
            )
        ),
    ),
)


# N21 rows remain immutable; six source observations moved during the explicit row7/row15 companion rebind.
_AUD380_N21_HISTORICAL_IDENTITY_SOURCE_LINES = (
    _AUD380_CURRENT_DELTA_IDENTITY_SOURCE_LINES
)
_AUD380_N21_HISTORICAL_SOURCE_LINE_HASHES = _AUD380_CURRENT_DELTA_SOURCE_LINE_HASHES
_AUD380_N21_REPLACED_COMPANION_LOCATIONS = frozenset(
    (
        ("quality/semgrep-dispositions.json", 189),
        ("quality/semgrep-dispositions.json", 453),
        ("quality/semgrep-dispositions.json", 461),
        ("quality/semgrep-dispositions.json", 469),
        ("quality/semgrep-dispositions.json", 481),
        ("quality/semgrep-dispositions.json", 485),
    )
)
_AUD380_N21_REPLACED_COMPANION_TARGETS = (
    ("quality/semgrep-dispositions.json", 189, "scripts/live_stand.py"),
    ("quality/semgrep-dispositions.json", 453, "frontend/WASM_SOURCE_PROVENANCE.json"),
    ("quality/semgrep-dispositions.json", 461, "frontend/wasm-sanitizer/Cargo.toml"),
    (
        "quality/semgrep-dispositions.json",
        469,
        "frontend/wasm-sanitizer/pkg/package.json",
    ),
    ("quality/semgrep-dispositions.json", 481, "frontend/package.json"),
    ("quality/semgrep-dispositions.json", 485, "frontend/package-lock.json"),
)
_AUD380_N21_REPLACED_IDENTITY_SOURCE_LINES = tuple(
    row
    for row in _AUD380_N21_HISTORICAL_IDENTITY_SOURCE_LINES
    if (row[0], row[4]) in _AUD380_N21_REPLACED_COMPANION_LOCATIONS
)
_AUD380_N21_UNCHANGED_IDENTITY_SOURCE_LINES = tuple(
    row
    for row in _AUD380_N21_HISTORICAL_IDENTITY_SOURCE_LINES
    if (row[0], row[4]) not in _AUD380_N21_REPLACED_COMPANION_LOCATIONS
)
_AUD380_N4_IDENTITY_SOURCE_LINES = (
    (
        "quality/semgrep-dispositions.json",
        "Hex High Entropy String",
        (
            166,
            110,
            177,
            206,
            147,
            218,
            249,
            66,
            1,
            241,
            95,
            73,
            8,
            215,
            24,
            86,
            67,
            165,
            227,
            57,
        ),
        "public_integrity_digest",
        189,
    ),
    (
        "tests/test_seed_demo_data.py",
        "Secret Keyword",
        (
            95,
            180,
            135,
            74,
            188,
            185,
            142,
            12,
            51,
            173,
            10,
            211,
            168,
            117,
            247,
            144,
            131,
            222,
            96,
            33,
        ),
        "ci_test_contract_sentinel",
        112,
    ),
    (
        "tests/test_temporal_namespace_init_fake_cli.py",
        "Secret Keyword",
        (
            5,
            7,
            180,
            175,
            200,
            103,
            100,
            106,
            164,
            44,
            199,
            230,
            34,
            191,
            164,
            53,
            52,
            135,
            142,
            180,
        ),
        "ci_test_contract_sentinel",
        45,
    ),
    (
        "tests/test_temporal_namespace_init_fake_cli.py",
        "Secret Keyword",
        (
            27,
            153,
            57,
            99,
            96,
            18,
            95,
            133,
            152,
            102,
            91,
            168,
            40,
            71,
            175,
            76,
            96,
            207,
            38,
            11,
        ),
        "ci_test_contract_sentinel",
        41,
    ),
)
_AUD380_CURRENT_DELTA_SOURCE_SHA256 = {
    ".github/workflows/deploy.yml": bytes(
        (
            188,
            133,
            211,
            51,
            129,
            101,
            252,
            231,
            154,
            176,
            94,
            169,
            244,
            180,
            185,
            45,
            154,
            96,
            120,
            152,
            97,
            15,
            152,
            233,
            62,
            53,
            150,
            200,
            214,
            183,
            142,
            31,
        ),
    ),
    "alembic/versions/202611020000_mvp_baseline.py": bytes(
        (
            217,
            40,
            32,
            172,
            28,
            251,
            112,
            82,
            6,
            200,
            242,
            135,
            195,
            5,
            156,
            85,
            86,
            58,
            55,
            7,
            235,
            192,
            227,
            251,
            62,
            119,
            175,
            33,
            50,
            227,
            196,
            26,
        ),
    ),
    "app/core/logging.py": bytes(
        (
            42,
            8,
            144,
            201,
            24,
            248,
            51,
            102,
            213,
            213,
            55,
            119,
            146,
            205,
            206,
            130,
            137,
            190,
            137,
            167,
            107,
            82,
            187,
            163,
            33,
            92,
            172,
            29,
            144,
            141,
            26,
            119,
        )
    ),
    "app/core/observability.py": bytes(
        (
            139,
            159,
            101,
            42,
            108,
            109,
            62,
            163,
            148,
            72,
            3,
            193,
            251,
            2,
            163,
            31,
            89,
            15,
            218,
            103,
            55,
            206,
            204,
            138,
            28,
            89,
            148,
            87,
            26,
            174,
            93,
            150,
        ),
    ),
    "app/core/otel_logging.py": bytes(
        (
            161,
            203,
            241,
            150,
            248,
            237,
            76,
            81,
            83,
            48,
            196,
            230,
            45,
            191,
            85,
            168,
            54,
            98,
            199,
            140,
            147,
            107,
            104,
            44,
            222,
            5,
            61,
            2,
            189,
            112,
            49,
            54,
        ),
    ),
    "app/worker.py": bytes(
        (
            136,
            239,
            44,
            198,
            141,
            97,
            249,
            17,
            17,
            249,
            5,
            122,
            158,
            77,
            170,
            29,
            181,
            0,
            15,
            234,
            7,
            35,
            8,
            9,
            11,
            161,
            224,
            40,
            192,
            22,
            21,
            107,
        ),
    ),
    "charts/university-ecosystem/templates/file-processor-deployment.yaml": bytes(
        (
            18,
            236,
            10,
            174,
            233,
            225,
            33,
            171,
            146,
            175,
            186,
            253,
            155,
            32,
            157,
            69,
            212,
            187,
            140,
            121,
            14,
            0,
            215,
            208,
            225,
            228,
            124,
            166,
            161,
            161,
            229,
            237,
        ),
    ),
    "charts/university-ecosystem/templates/gateway-deployment.yaml": bytes(
        (
            157,
            96,
            223,
            107,
            208,
            38,
            106,
            205,
            179,
            10,
            25,
            144,
            254,
            23,
            117,
            245,
            129,
            190,
            221,
            115,
            30,
            249,
            110,
            154,
            39,
            64,
            45,
            60,
            49,
            167,
            95,
            230,
        ),
    ),
    "charts/university-ecosystem/values.schema.json": bytes(
        (
            211,
            209,
            161,
            116,
            54,
            205,
            155,
            19,
            108,
            177,
            5,
            99,
            225,
            105,
            216,
            72,
            232,
            133,
            186,
            132,
            94,
            118,
            149,
            255,
            36,
            187,
            68,
            56,
            206,
            153,
            147,
            73,
        ),
    ),
    "charts/university-ecosystem/values.yaml": bytes(
        (
            17,
            34,
            233,
            153,
            140,
            69,
            20,
            107,
            130,
            153,
            65,
            239,
            19,
            117,
            187,
            85,
            193,
            164,
            253,
            247,
            7,
            63,
            76,
            228,
            215,
            117,
            161,
            9,
            62,
            28,
            110,
            120,
        ),
    ),
    "frontend/WASM_SOURCE_PROVENANCE.json": bytes(
        (
            108,
            141,
            166,
            75,
            95,
            148,
            239,
            3,
            50,
            129,
            204,
            217,
            137,
            94,
            174,
            199,
            21,
            73,
            14,
            163,
            222,
            191,
            228,
            111,
            190,
            229,
            113,
            101,
            133,
            0,
            37,
            185,
        ),
    ),
    "frontend/package-lock.json": bytes(
        (
            77,
            193,
            193,
            164,
            50,
            105,
            102,
            145,
            70,
            109,
            232,
            54,
            32,
            97,
            235,
            91,
            11,
            53,
            5,
            50,
            137,
            213,
            91,
            158,
            173,
            15,
            230,
            80,
            4,
            123,
            124,
            3,
        ),
    ),
    "frontend/package.json": bytes(
        (
            180,
            230,
            245,
            157,
            35,
            107,
            28,
            140,
            191,
            31,
            12,
            35,
            149,
            114,
            212,
            175,
            28,
            152,
            46,
            133,
            94,
            219,
            198,
            179,
            98,
            126,
            23,
            190,
            164,
            86,
            212,
            109,
        ),
    ),
    "frontend/scripts/server-csp.mjs": bytes(
        (
            243,
            60,
            75,
            188,
            84,
            252,
            237,
            3,
            255,
            17,
            82,
            171,
            151,
            234,
            43,
            81,
            226,
            27,
            221,
            200,
            128,
            54,
            168,
            255,
            138,
            11,
            33,
            117,
            244,
            78,
            194,
            66,
        ),
    ),
    "frontend/scripts/visual-smoke-contract.test.mjs": bytes(
        (
            74,
            118,
            255,
            234,
            115,
            126,
            96,
            204,
            2,
            131,
            123,
            242,
            188,
            124,
            204,
            238,
            248,
            234,
            184,
            51,
            218,
            158,
            191,
            83,
            154,
            70,
            195,
            73,
            204,
            238,
            243,
            53,
        ),
    ),
    "frontend/src/components/ui/SafeHtml.tsx": bytes(
        (
            219,
            248,
            243,
            113,
            47,
            200,
            107,
            145,
            81,
            170,
            170,
            203,
            157,
            169,
            82,
            246,
            92,
            94,
            48,
            168,
            167,
            117,
            189,
            78,
            0,
            153,
            60,
            40,
            57,
            55,
            153,
            129,
        ),
    ),
    "frontend/src/components/ui/__tests__/SafeHtml.test.tsx": bytes(
        (
            182,
            244,
            127,
            235,
            138,
            103,
            214,
            48,
            94,
            181,
            19,
            44,
            104,
            211,
            136,
            56,
            196,
            233,
            214,
            123,
            241,
            190,
            143,
            120,
            94,
            5,
            247,
            71,
            97,
            175,
            191,
            89,
        ),
    ),
    "frontend/src/utils/htmlText.ts": bytes(
        (
            65,
            142,
            83,
            177,
            60,
            141,
            199,
            203,
            122,
            244,
            229,
            239,
            124,
            131,
            57,
            122,
            136,
            11,
            219,
            245,
            247,
            226,
            160,
            228,
            235,
            231,
            253,
            143,
            146,
            49,
            176,
            175,
        ),
    ),
    "frontend/src/utils/trustedTypes.ts": bytes(
        (
            176,
            97,
            18,
            171,
            55,
            197,
            101,
            91,
            15,
            170,
            126,
            16,
            100,
            132,
            208,
            59,
            159,
            156,
            178,
            10,
            120,
            23,
            123,
            124,
            73,
            249,
            131,
            139,
            163,
            245,
            49,
            151,
        ),
    ),
    "frontend/wasm-sanitizer/Cargo.lock": bytes(
        (
            177,
            169,
            100,
            22,
            225,
            202,
            44,
            193,
            132,
            67,
            204,
            81,
            108,
            86,
            95,
            49,
            89,
            47,
            242,
            134,
            84,
            108,
            108,
            116,
            95,
            151,
            97,
            169,
            3,
            186,
            154,
            165,
        ),
    ),
    "frontend/wasm-sanitizer/Cargo.toml": bytes(
        (
            115,
            219,
            155,
            111,
            224,
            85,
            216,
            102,
            44,
            118,
            45,
            112,
            80,
            232,
            24,
            203,
            174,
            94,
            83,
            127,
            145,
            108,
            142,
            202,
            211,
            78,
            186,
            255,
            44,
            41,
            181,
            125,
        ),
    ),
    "frontend/wasm-sanitizer/pkg/package.json": bytes(
        (
            45,
            165,
            28,
            159,
            180,
            53,
            180,
            201,
            153,
            117,
            102,
            70,
            168,
            98,
            188,
            151,
            42,
            87,
            159,
            120,
            178,
            210,
            101,
            80,
            18,
            101,
            72,
            191,
            167,
            126,
            115,
            68,
        ),
    ),
    "frontend/wasm-sanitizer/pkg/wasm_sanitizer.js": bytes(
        (
            81,
            194,
            116,
            98,
            175,
            213,
            128,
            122,
            161,
            17,
            36,
            116,
            94,
            113,
            247,
            158,
            223,
            23,
            61,
            88,
            70,
            107,
            193,
            95,
            29,
            103,
            63,
            224,
            213,
            214,
            90,
            205,
        ),
    ),
    "frontend/wasm-sanitizer/pkg/wasm_sanitizer_bg.wasm": bytes(
        (
            202,
            180,
            5,
            31,
            224,
            49,
            179,
            117,
            213,
            167,
            21,
            77,
            224,
            113,
            188,
            71,
            238,
            200,
            84,
            18,
            59,
            70,
            172,
            171,
            192,
            100,
            130,
            161,
            54,
            142,
            134,
            5,
        ),
    ),
    "frontend/wasm-sanitizer/src/lib.rs": bytes(
        (
            145,
            235,
            42,
            4,
            45,
            84,
            149,
            181,
            43,
            101,
            55,
            238,
            12,
            173,
            142,
            242,
            88,
            175,
            228,
            33,
            49,
            111,
            147,
            9,
            246,
            80,
            240,
            182,
            61,
            108,
            66,
            147,
        ),
    ),
    "quality/semgrep-dispositions.json": bytes(
        (
            21,
            27,
            157,
            11,
            62,
            169,
            82,
            187,
            187,
            1,
            190,
            178,
            41,
            31,
            162,
            116,
            110,
            193,
            131,
            175,
            217,
            43,
            183,
            177,
            231,
            142,
            23,
            99,
            52,
            53,
            119,
            234,
        ),
    ),
    "scripts/kind/aud373_internal_mtls_proof.sh": bytes(
        (
            32,
            126,
            17,
            99,
            74,
            4,
            240,
            133,
            61,
            93,
            138,
            26,
            107,
            55,
            232,
            154,
            60,
            26,
            246,
            86,
            237,
            205,
            236,
            57,
            219,
            135,
            165,
            4,
            237,
            216,
            68,
            105,
        ),
    ),
    "scripts/live_stand.py": bytes(
        (
            23,
            28,
            49,
            42,
            231,
            220,
            243,
            226,
            207,
            204,
            24,
            190,
            185,
            103,
            145,
            54,
            164,
            127,
            113,
            47,
            56,
            176,
            24,
            223,
            98,
            97,
            247,
            126,
            248,
            37,
            232,
            19,
        ),
    ),
    "scripts/owned_nats_broker_control.py": bytes(
        (
            84,
            215,
            19,
            159,
            143,
            142,
            63,
            191,
            79,
            216,
            190,
            68,
            116,
            72,
            236,
            42,
            27,
            80,
            151,
            203,
            227,
            23,
            244,
            15,
            238,
            153,
            70,
            195,
            151,
            188,
            151,
            211,
        ),
    ),
    "scripts/owned_nats_docker.py": bytes(
        (
            97,
            120,
            126,
            130,
            157,
            19,
            250,
            169,
            166,
            37,
            197,
            95,
            110,
            2,
            194,
            152,
            8,
            99,
            236,
            173,
            123,
            178,
            86,
            111,
            89,
            33,
            134,
            190,
            0,
            41,
            22,
            162,
        ),
    ),
    "scripts/owned_nats_failure_diagnostic.py": bytes(
        (
            168,
            92,
            171,
            166,
            47,
            191,
            199,
            151,
            210,
            218,
            89,
            184,
            81,
            3,
            217,
            151,
            237,
            76,
            102,
            61,
            120,
            254,
            142,
            137,
            29,
            35,
            143,
            74,
            112,
            203,
            79,
            83,
        ),
    ),
    "scripts/owned_nats_outage_cli.py": bytes(
        (
            108,
            3,
            136,
            100,
            172,
            168,
            201,
            127,
            4,
            66,
            210,
            92,
            58,
            191,
            179,
            55,
            235,
            149,
            133,
            219,
            73,
            143,
            117,
            204,
            182,
            244,
            66,
            79,
            141,
            251,
            115,
            213,
        ),
    ),
    "scripts/owned_nats_owner_adapter.py": bytes(
        (
            47,
            157,
            13,
            111,
            236,
            21,
            191,
            89,
            163,
            112,
            78,
            111,
            81,
            119,
            192,
            103,
            74,
            155,
            48,
            218,
            241,
            50,
            235,
            184,
            78,
            43,
            245,
            199,
            238,
            32,
            73,
            184,
        ),
    ),
    "scripts/owned_nats_process.py": bytes(
        (
            161,
            241,
            67,
            102,
            179,
            232,
            203,
            164,
            19,
            116,
            243,
            93,
            239,
            248,
            138,
            255,
            55,
            7,
            63,
            134,
            63,
            176,
            48,
            15,
            129,
            129,
            245,
            45,
            234,
            186,
            27,
            222,
        ),
    ),
    "scripts/owned_nats_runtime_adapter.py": bytes(
        (
            189,
            70,
            166,
            191,
            120,
            72,
            2,
            113,
            43,
            45,
            157,
            180,
            22,
            204,
            217,
            223,
            47,
            167,
            85,
            206,
            42,
            230,
            0,
            136,
            43,
            53,
            61,
            221,
            227,
            26,
            242,
            128,
        ),
    ),
    "scripts/owned_nats_sql_adapter.py": bytes(
        (
            48,
            1,
            106,
            173,
            223,
            197,
            196,
            117,
            211,
            185,
            172,
            124,
            5,
            78,
            223,
            38,
            234,
            138,
            64,
            83,
            156,
            52,
            116,
            134,
            91,
            137,
            232,
            26,
            70,
            52,
            85,
            20,
        ),
    ),
    "scripts/owned_nats_transport_port.py": bytes(
        (
            203,
            105,
            72,
            183,
            231,
            8,
            124,
            126,
            137,
            13,
            25,
            90,
            186,
            68,
            210,
            109,
            30,
            59,
            193,
            14,
            244,
            237,
            181,
            115,
            251,
            129,
            142,
            67,
            238,
            189,
            148,
            60,
        ),
    ),
    "scripts/quality/helm_rendered_target_overlay.py": bytes(
        (
            238,
            83,
            160,
            7,
            212,
            180,
            162,
            214,
            130,
            251,
            194,
            179,
            58,
            123,
            126,
            91,
            145,
            27,
            167,
            20,
            207,
            16,
            233,
            67,
            21,
            230,
            32,
            234,
            77,
            247,
            215,
            232,
        ),
    ),
    "scripts/quality/helm_semgrep_profile_registry.json": bytes(
        (
            101,
            54,
            204,
            151,
            31,
            73,
            63,
            115,
            126,
            244,
            159,
            173,
            99,
            115,
            81,
            183,
            133,
            124,
            17,
            255,
            249,
            50,
            179,
            19,
            250,
            194,
            251,
            135,
            189,
            185,
            83,
            69,
        ),
    ),
    "tests/fixtures/owned_baseline_postgres.py": bytes(
        (
            143,
            9,
            157,
            42,
            201,
            70,
            254,
            170,
            6,
            206,
            102,
            146,
            185,
            185,
            176,
            52,
            72,
            118,
            2,
            175,
            227,
            248,
            70,
            12,
            94,
            53,
            152,
            164,
            114,
            47,
            184,
            75,
        ),
    ),
    "tests/integration/test_aud433_notifications_baseline_partition.py": bytes(
        (
            201,
            129,
            188,
            5,
            56,
            215,
            222,
            57,
            189,
            19,
            180,
            213,
            123,
            5,
            166,
            187,
            37,
            65,
            202,
            80,
            66,
            82,
            69,
            166,
            31,
            204,
            144,
            178,
            176,
            13,
            102,
            109,
        ),
    ),
    "tests/integration/test_mvp_baseline_schema_equivalence.py": bytes(
        (
            165,
            215,
            227,
            87,
            247,
            178,
            12,
            65,
            177,
            32,
            9,
            51,
            101,
            179,
            220,
            147,
            180,
            118,
            146,
            177,
            105,
            164,
            112,
            180,
            31,
            65,
            241,
            11,
            99,
            162,
            175,
            121,
        ),
    ),
    "tests/test_helm_rendered_target_overlay.py": bytes(
        (
            226,
            240,
            65,
            141,
            110,
            123,
            24,
            138,
            85,
            56,
            100,
            92,
            214,
            85,
            140,
            181,
            159,
            3,
            225,
            45,
            239,
            174,
            180,
            181,
            116,
            108,
            102,
            217,
            80,
            12,
            221,
            133,
        ),
    ),
    "tests/test_internal_mtls_kind_contract.py": bytes(
        (
            110,
            198,
            109,
            43,
            39,
            243,
            111,
            15,
            144,
            43,
            231,
            139,
            161,
            163,
            7,
            69,
            115,
            53,
            193,
            195,
            60,
            115,
            126,
            39,
            88,
            117,
            239,
            155,
            159,
            160,
            96,
            122,
        ),
    ),
    "tests/test_logging_pii_redaction_contract.py": bytes(
        (
            85,
            171,
            52,
            160,
            153,
            107,
            212,
            125,
            10,
            209,
            88,
            86,
            153,
            31,
            222,
            179,
            64,
            122,
            232,
            88,
            120,
            83,
            171,
            226,
            52,
            246,
            218,
            162,
            49,
            116,
            60,
            44,
        ),
    ),
    "tests/test_logging_redos_aud380.py": bytes(
        (
            181,
            187,
            177,
            39,
            24,
            177,
            109,
            24,
            132,
            71,
            240,
            223,
            69,
            119,
            198,
            116,
            227,
            37,
            36,
            47,
            144,
            146,
            118,
            36,
            149,
            111,
            254,
            243,
            72,
            203,
            230,
            218,
        ),
    ),
    "tests/test_otel_logging_bridge.py": bytes(
        (
            57,
            68,
            226,
            177,
            242,
            117,
            27,
            34,
            23,
            111,
            165,
            178,
            28,
            114,
            190,
            111,
            181,
            91,
            92,
            34,
            74,
            177,
            81,
            122,
            33,
            212,
            213,
            245,
            79,
            46,
            28,
            8,
        ),
    ),
    "tests/test_owned_nats_broker_control.py": bytes(
        (
            135,
            242,
            9,
            181,
            133,
            104,
            33,
            232,
            22,
            61,
            230,
            197,
            83,
            30,
            75,
            188,
            51,
            59,
            93,
            112,
            103,
            239,
            128,
            51,
            208,
            174,
            49,
            173,
            57,
            39,
            108,
            23,
        ),
    ),
    "tests/test_owned_nats_docker_context_pins.py": bytes(
        (
            68,
            144,
            55,
            252,
            234,
            40,
            243,
            108,
            124,
            239,
            127,
            239,
            59,
            94,
            76,
            1,
            197,
            181,
            133,
            204,
            150,
            62,
            253,
            193,
            206,
            30,
            190,
            199,
            166,
            4,
            251,
            32,
        ),
    ),
    "tests/test_owned_nats_lease_bootstrap.py": bytes(
        (
            72,
            143,
            156,
            24,
            182,
            76,
            204,
            220,
            6,
            152,
            201,
            27,
            195,
            72,
            81,
            254,
            109,
            247,
            88,
            131,
            107,
            183,
            17,
            53,
            32,
            240,
            140,
            111,
            179,
            216,
            151,
            140,
        ),
    ),
    "tests/test_owned_nats_process.py": bytes(
        (
            115,
            55,
            77,
            130,
            22,
            223,
            103,
            164,
            224,
            46,
            229,
            83,
            63,
            42,
            164,
            130,
            75,
            45,
            40,
            21,
            115,
            166,
            67,
            7,
            149,
            24,
            165,
            99,
            128,
            248,
            138,
            91,
        ),
    ),
    "tests/test_owned_nats_sql_adapter.py": bytes(
        (
            240,
            129,
            113,
            143,
            105,
            170,
            96,
            14,
            211,
            251,
            196,
            144,
            20,
            4,
            55,
            188,
            194,
            15,
            9,
            254,
            238,
            87,
            41,
            19,
            231,
            228,
            243,
            39,
            236,
            5,
            94,
            136,
        ),
    ),
    "tests/test_seed_demo_data.py": bytes(
        (
            158,
            118,
            66,
            16,
            195,
            83,
            13,
            66,
            116,
            173,
            254,
            114,
            96,
            246,
            179,
            54,
            66,
            15,
            5,
            193,
            163,
            231,
            79,
            77,
            211,
            9,
            142,
            172,
            44,
            234,
            51,
            206,
        ),
    ),
    "tests/test_temporal_namespace_init_fake_cli.py": bytes(
        (
            116,
            30,
            99,
            150,
            71,
            223,
            210,
            237,
            164,
            46,
            114,
            82,
            160,
            149,
            4,
            65,
            60,
            136,
            221,
            129,
            142,
            111,
            36,
            41,
            94,
            173,
            124,
            92,
            12,
            4,
            190,
            163,
        ),
    ),
}
_AUD380_CURRENT_DELTA_IDENTITY_SOURCE_LINES = (
    (
        "quality/semgrep-dispositions.json",
        "Hex High Entropy String",
        (
            41,
            226,
            48,
            194,
            246,
            77,
            76,
            254,
            122,
            142,
            139,
            183,
            53,
            205,
            133,
            30,
            11,
            46,
            215,
            148,
        ),
        "public_integrity_digest",
        329,
    ),
    (
        "quality/semgrep-dispositions.json",
        "Hex High Entropy String",
        (
            62,
            174,
            193,
            241,
            112,
            115,
            133,
            90,
            248,
            237,
            157,
            83,
            35,
            122,
            184,
            184,
            243,
            229,
            98,
            235,
        ),
        "public_integrity_digest",
        77,
    ),
    (
        "quality/semgrep-dispositions.json",
        "Hex High Entropy String",
        (
            205,
            173,
            143,
            192,
            215,
            54,
            205,
            124,
            209,
            17,
            59,
            80,
            229,
            83,
            6,
            50,
            92,
            246,
            111,
            83,
        ),
        "public_integrity_digest",
        313,
    ),
    (
        "quality/semgrep-dispositions.json",
        "Hex High Entropy String",
        (
            212,
            79,
            231,
            20,
            66,
            26,
            238,
            161,
            155,
            95,
            107,
            197,
            188,
            125,
            91,
            29,
            171,
            233,
            36,
            77,
        ),
        "public_integrity_digest",
        309,
    ),
    (
        "quality/semgrep-dispositions.json",
        "Hex High Entropy String",
        (
            221,
            23,
            201,
            30,
            59,
            96,
            188,
            41,
            102,
            129,
            190,
            72,
            124,
            92,
            67,
            125,
            211,
            167,
            65,
            122,
        ),
        "public_integrity_digest",
        225,
    ),
    (
        "scripts/kind/aud373_internal_mtls_proof.sh",
        "Secret Keyword",
        (
            72,
            181,
            183,
            235,
            226,
            138,
            58,
            11,
            133,
            115,
            118,
            62,
            187,
            137,
            54,
            156,
            32,
            38,
            207,
            133,
        ),
        "external_kubernetes_secret_reference",
        246,
    ),
    (
        "scripts/kind/aud373_internal_mtls_proof.sh",
        "Secret Keyword",
        (
            190,
            254,
            225,
            86,
            25,
            144,
            171,
            40,
            21,
            38,
            254,
            179,
            233,
            64,
            127,
            76,
            82,
            31,
            100,
            153,
        ),
        "external_kubernetes_secret_reference",
        248,
    ),
    (
        "scripts/quality/helm_rendered_target_overlay.py",
        "Hex High Entropy String",
        (
            92,
            4,
            48,
            60,
            142,
            174,
            166,
            4,
            74,
            195,
            133,
            169,
            98,
            25,
            8,
            91,
            4,
            238,
            106,
            33,
        ),
        "public_integrity_digest",
        37,
    ),
    (
        "tests/integration/test_aud433_notifications_baseline_partition.py",
        "Hex High Entropy String",
        (
            151,
            220,
            198,
            119,
            83,
            226,
            96,
            3,
            226,
            99,
            188,
            46,
            237,
            41,
            167,
            129,
            163,
            46,
            90,
            78,
        ),
        "public_integrity_digest",
        38,
    ),
    (
        "tests/integration/test_aud433_notifications_baseline_partition.py",
        "Hex High Entropy String",
        (
            161,
            87,
            128,
            131,
            219,
            96,
            152,
            248,
            166,
            82,
            38,
            180,
            113,
            140,
            117,
            245,
            8,
            183,
            210,
            205,
        ),
        "public_integrity_digest",
        35,
    ),
    (
        "tests/integration/test_aud433_notifications_baseline_partition.py",
        "Hex High Entropy String",
        (
            243,
            210,
            64,
            149,
            243,
            17,
            167,
            236,
            53,
            209,
            64,
            254,
            108,
            204,
            182,
            192,
            218,
            114,
            29,
            40,
        ),
        "public_integrity_digest",
        32,
    ),
    (
        "tests/test_helm_rendered_target_overlay.py",
        "Hex High Entropy String",
        (
            92,
            4,
            48,
            60,
            142,
            174,
            166,
            4,
            74,
            195,
            133,
            169,
            98,
            25,
            8,
            91,
            4,
            238,
            106,
            33,
        ),
        "public_integrity_digest",
        96,
    ),
    (
        "tests/test_internal_mtls_kind_contract.py",
        "Base64 High Entropy String",
        (
            77,
            40,
            149,
            72,
            118,
            40,
            115,
            199,
            72,
            221,
            231,
            105,
            235,
            149,
            15,
            76,
            25,
            76,
            7,
            30,
        ),
        "ci_test_contract_sentinel",
        1981,
    ),
    (
        "tests/test_internal_mtls_kind_contract.py",
        "Secret Keyword",
        (
            72,
            181,
            183,
            235,
            226,
            138,
            58,
            11,
            133,
            115,
            118,
            62,
            187,
            137,
            54,
            156,
            32,
            38,
            207,
            133,
        ),
        "external_kubernetes_secret_reference",
        1352,
    ),
    (
        "tests/test_internal_mtls_kind_contract.py",
        "Secret Keyword",
        (
            190,
            254,
            225,
            86,
            25,
            144,
            171,
            40,
            21,
            38,
            254,
            179,
            233,
            64,
            127,
            76,
            82,
            31,
            100,
            153,
        ),
        "external_kubernetes_secret_reference",
        1353,
    ),
    (
        "quality/semgrep-dispositions.json",
        "Hex High Entropy String",
        (
            166,
            110,
            177,
            206,
            147,
            218,
            249,
            66,
            1,
            241,
            95,
            73,
            8,
            215,
            24,
            86,
            67,
            165,
            227,
            57,
        ),
        "public_integrity_digest",
        189,
    ),
    (
        "tests/test_seed_demo_data.py",
        "Secret Keyword",
        (
            95,
            180,
            135,
            74,
            188,
            185,
            142,
            12,
            51,
            173,
            10,
            211,
            168,
            117,
            247,
            144,
            131,
            222,
            96,
            33,
        ),
        "ci_test_contract_sentinel",
        112,
    ),
    (
        "tests/test_temporal_namespace_init_fake_cli.py",
        "Secret Keyword",
        (
            5,
            7,
            180,
            175,
            200,
            103,
            100,
            106,
            164,
            44,
            199,
            230,
            34,
            191,
            164,
            53,
            52,
            135,
            142,
            180,
        ),
        "ci_test_contract_sentinel",
        45,
    ),
    (
        "tests/test_temporal_namespace_init_fake_cli.py",
        "Secret Keyword",
        (
            27,
            153,
            57,
            99,
            96,
            18,
            95,
            133,
            152,
            102,
            91,
            168,
            40,
            71,
            175,
            76,
            96,
            207,
            38,
            11,
        ),
        "ci_test_contract_sentinel",
        41,
    ),
)
_AUD380_CURRENT_DELTA_SOURCE_LINE_HASHES = (
    (
        "charts/university-ecosystem/templates/file-processor-deployment.yaml",
        196,
        bytes(
            (
                65,
                201,
                105,
                239,
                119,
                59,
                68,
                30,
                30,
                106,
                20,
                223,
                57,
                36,
                130,
                102,
                117,
                225,
                177,
                78,
                227,
                30,
                225,
                175,
                8,
                226,
                183,
                48,
                189,
                6,
                129,
                193,
            ),
        ),
        bytes(
            (
                82,
                154,
                134,
                117,
                46,
                85,
                191,
                85,
                105,
                3,
                153,
                136,
                0,
                174,
                50,
                158,
                116,
                24,
                50,
                49,
                44,
                104,
                219,
                154,
                255,
                252,
                81,
                39,
                245,
                228,
                247,
                98,
            ),
        ),
    ),
    (
        "charts/university-ecosystem/templates/gateway-deployment.yaml",
        192,
        bytes(
            (
                131,
                234,
                205,
                108,
                214,
                107,
                113,
                239,
                103,
                30,
                246,
                87,
                232,
                4,
                42,
                79,
                181,
                169,
                33,
                162,
                220,
                10,
                18,
                219,
                201,
                244,
                7,
                60,
                244,
                162,
                31,
                168,
            ),
        ),
        bytes(
            (
                146,
                164,
                33,
                180,
                227,
                187,
                93,
                48,
                121,
                118,
                179,
                185,
                145,
                75,
                204,
                47,
                64,
                63,
                197,
                64,
                129,
                191,
                33,
                169,
                204,
                221,
                3,
                243,
                121,
                249,
                0,
                99,
            ),
        ),
    ),
    (
        "charts/university-ecosystem/values.yaml",
        112,
        bytes(
            (
                20,
                26,
                26,
                73,
                173,
                133,
                148,
                239,
                57,
                120,
                21,
                190,
                207,
                38,
                193,
                87,
                31,
                229,
                71,
                228,
                120,
                95,
                89,
                138,
                232,
                83,
                82,
                173,
                171,
                240,
                114,
                117,
            ),
        ),
        bytes(
            (
                19,
                33,
                210,
                126,
                125,
                9,
                78,
                54,
                254,
                142,
                89,
                230,
                0,
                116,
                149,
                231,
                12,
                115,
                106,
                217,
                153,
                248,
                204,
                243,
                82,
                144,
                138,
                101,
                24,
                191,
                99,
                203,
            ),
        ),
    ),
    (
        "charts/university-ecosystem/values.yaml",
        117,
        bytes(
            (
                20,
                26,
                26,
                73,
                173,
                133,
                148,
                239,
                57,
                120,
                21,
                190,
                207,
                38,
                193,
                87,
                31,
                229,
                71,
                228,
                120,
                95,
                89,
                138,
                232,
                83,
                82,
                173,
                171,
                240,
                114,
                117,
            ),
        ),
        bytes(
            (
                205,
                130,
                65,
                155,
                249,
                165,
                210,
                202,
                176,
                213,
                26,
                17,
                90,
                219,
                138,
                35,
                196,
                109,
                234,
                173,
                210,
                64,
                177,
                194,
                252,
                109,
                21,
                114,
                54,
                16,
                40,
                228,
            ),
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        77,
        bytes(
            (
                109,
                216,
                46,
                136,
                235,
                101,
                25,
                138,
                159,
                156,
                245,
                96,
                41,
                12,
                37,
                147,
                154,
                122,
                187,
                220,
                123,
                55,
                234,
                199,
                96,
                13,
                85,
                15,
                31,
                3,
                12,
                252,
            ),
        ),
        bytes(
            (
                248,
                193,
                174,
                35,
                166,
                84,
                132,
                10,
                204,
                159,
                125,
                188,
                215,
                215,
                73,
                136,
                152,
                129,
                86,
                171,
                210,
                246,
                148,
                133,
                194,
                165,
                230,
                141,
                108,
                102,
                135,
                185,
            ),
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        77,
        bytes(
            (
                109,
                216,
                46,
                136,
                235,
                101,
                25,
                138,
                159,
                156,
                245,
                96,
                41,
                12,
                37,
                147,
                154,
                122,
                187,
                220,
                123,
                55,
                234,
                199,
                96,
                13,
                85,
                15,
                31,
                3,
                12,
                252,
            ),
        ),
        bytes(
            (
                248,
                193,
                174,
                35,
                166,
                84,
                132,
                10,
                204,
                159,
                125,
                188,
                215,
                215,
                73,
                136,
                152,
                129,
                86,
                171,
                210,
                246,
                148,
                133,
                194,
                165,
                230,
                141,
                108,
                102,
                135,
                185,
            ),
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        189,
        bytes(
            (
                44,
                159,
                169,
                165,
                166,
                149,
                178,
                220,
                213,
                245,
                84,
                64,
                128,
                13,
                55,
                205,
                84,
                229,
                29,
                53,
                19,
                196,
                221,
                20,
                219,
                43,
                108,
                171,
                132,
                210,
                26,
                178,
            ),
        ),
        bytes(
            (
                14,
                222,
                230,
                189,
                171,
                75,
                75,
                102,
                38,
                213,
                235,
                40,
                238,
                36,
                119,
                192,
                72,
                90,
                59,
                219,
                7,
                151,
                181,
                75,
                46,
                12,
                179,
                248,
                91,
                9,
                193,
                249,
            ),
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        189,
        bytes(
            (
                44,
                159,
                169,
                165,
                166,
                149,
                178,
                220,
                213,
                245,
                84,
                64,
                128,
                13,
                55,
                205,
                84,
                229,
                29,
                53,
                19,
                196,
                221,
                20,
                219,
                43,
                108,
                171,
                132,
                210,
                26,
                178,
            ),
        ),
        bytes(
            (
                14,
                222,
                230,
                189,
                171,
                75,
                75,
                102,
                38,
                213,
                235,
                40,
                238,
                36,
                119,
                192,
                72,
                90,
                59,
                219,
                7,
                151,
                181,
                75,
                46,
                12,
                179,
                248,
                91,
                9,
                193,
                249,
            ),
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        225,
        bytes(
            (
                170,
                80,
                145,
                29,
                50,
                52,
                45,
                96,
                202,
                252,
                211,
                255,
                167,
                74,
                126,
                89,
                77,
                194,
                67,
                27,
                12,
                110,
                244,
                17,
                87,
                27,
                177,
                49,
                220,
                182,
                19,
                253,
            ),
        ),
        bytes(
            (
                228,
                141,
                71,
                85,
                99,
                1,
                238,
                230,
                75,
                209,
                172,
                104,
                235,
                143,
                198,
                97,
                63,
                26,
                38,
                198,
                157,
                96,
                132,
                1,
                163,
                235,
                59,
                233,
                217,
                239,
                3,
                210,
            ),
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        225,
        bytes(
            (
                170,
                80,
                145,
                29,
                50,
                52,
                45,
                96,
                202,
                252,
                211,
                255,
                167,
                74,
                126,
                89,
                77,
                194,
                67,
                27,
                12,
                110,
                244,
                17,
                87,
                27,
                177,
                49,
                220,
                182,
                19,
                253,
            ),
        ),
        bytes(
            (
                228,
                141,
                71,
                85,
                99,
                1,
                238,
                230,
                75,
                209,
                172,
                104,
                235,
                143,
                198,
                97,
                63,
                26,
                38,
                198,
                157,
                96,
                132,
                1,
                163,
                235,
                59,
                233,
                217,
                239,
                3,
                210,
            ),
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        309,
        bytes(
            (
                62,
                205,
                83,
                73,
                223,
                90,
                168,
                196,
                13,
                215,
                38,
                13,
                77,
                111,
                10,
                8,
                148,
                124,
                149,
                31,
                180,
                111,
                178,
                103,
                194,
                152,
                158,
                37,
                147,
                99,
                179,
                69,
            ),
        ),
        bytes(
            (
                151,
                187,
                219,
                234,
                33,
                130,
                212,
                104,
                43,
                203,
                245,
                172,
                173,
                43,
                15,
                186,
                250,
                184,
                186,
                93,
                128,
                14,
                173,
                110,
                216,
                69,
                189,
                208,
                50,
                150,
                83,
                201,
            ),
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        309,
        bytes(
            (
                62,
                205,
                83,
                73,
                223,
                90,
                168,
                196,
                13,
                215,
                38,
                13,
                77,
                111,
                10,
                8,
                148,
                124,
                149,
                31,
                180,
                111,
                178,
                103,
                194,
                152,
                158,
                37,
                147,
                99,
                179,
                69,
            ),
        ),
        bytes(
            (
                151,
                187,
                219,
                234,
                33,
                130,
                212,
                104,
                43,
                203,
                245,
                172,
                173,
                43,
                15,
                186,
                250,
                184,
                186,
                93,
                128,
                14,
                173,
                110,
                216,
                69,
                189,
                208,
                50,
                150,
                83,
                201,
            ),
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        313,
        bytes(
            (
                179,
                86,
                65,
                72,
                206,
                76,
                94,
                172,
                131,
                249,
                77,
                52,
                6,
                239,
                102,
                91,
                172,
                95,
                20,
                49,
                101,
                2,
                141,
                135,
                169,
                62,
                14,
                52,
                161,
                44,
                93,
                114,
            ),
        ),
        bytes(
            (
                214,
                161,
                144,
                84,
                76,
                44,
                122,
                189,
                133,
                161,
                25,
                219,
                186,
                221,
                110,
                249,
                15,
                155,
                138,
                230,
                149,
                46,
                105,
                88,
                55,
                178,
                118,
                204,
                169,
                179,
                7,
                194,
            ),
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        313,
        bytes(
            (
                179,
                86,
                65,
                72,
                206,
                76,
                94,
                172,
                131,
                249,
                77,
                52,
                6,
                239,
                102,
                91,
                172,
                95,
                20,
                49,
                101,
                2,
                141,
                135,
                169,
                62,
                14,
                52,
                161,
                44,
                93,
                114,
            ),
        ),
        bytes(
            (
                214,
                161,
                144,
                84,
                76,
                44,
                122,
                189,
                133,
                161,
                25,
                219,
                186,
                221,
                110,
                249,
                15,
                155,
                138,
                230,
                149,
                46,
                105,
                88,
                55,
                178,
                118,
                204,
                169,
                179,
                7,
                194,
            ),
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        317,
        bytes(
            (
                107,
                241,
                68,
                221,
                97,
                6,
                172,
                205,
                61,
                134,
                145,
                100,
                252,
                247,
                222,
                15,
                212,
                197,
                10,
                118,
                64,
                235,
                65,
                16,
                224,
                159,
                104,
                135,
                43,
                225,
                13,
                219,
            ),
        ),
        bytes(
            (
                156,
                164,
                43,
                196,
                156,
                172,
                49,
                89,
                189,
                206,
                159,
                89,
                143,
                246,
                190,
                145,
                147,
                224,
                56,
                65,
                142,
                234,
                46,
                120,
                179,
                17,
                222,
                55,
                120,
                19,
                254,
                67,
            ),
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        321,
        bytes(
            (
                253,
                211,
                34,
                166,
                208,
                128,
                186,
                30,
                78,
                80,
                172,
                4,
                235,
                122,
                222,
                81,
                5,
                195,
                192,
                251,
                187,
                47,
                102,
                151,
                120,
                191,
                166,
                138,
                251,
                143,
                48,
                0,
            ),
        ),
        bytes(
            (
                197,
                219,
                79,
                177,
                48,
                32,
                246,
                77,
                178,
                160,
                56,
                140,
                108,
                125,
                146,
                68,
                166,
                166,
                171,
                8,
                153,
                39,
                155,
                246,
                71,
                239,
                17,
                99,
                227,
                54,
                223,
                105,
            ),
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        325,
        bytes(
            (
                39,
                146,
                45,
                198,
                145,
                124,
                170,
                109,
                194,
                179,
                130,
                169,
                234,
                93,
                140,
                230,
                211,
                128,
                225,
                156,
                107,
                173,
                43,
                151,
                217,
                105,
                140,
                246,
                5,
                15,
                164,
                28,
            ),
        ),
        bytes(
            (
                35,
                28,
                111,
                56,
                16,
                180,
                255,
                208,
                67,
                169,
                228,
                94,
                111,
                72,
                251,
                189,
                15,
                196,
                125,
                112,
                76,
                171,
                134,
                217,
                126,
                101,
                196,
                200,
                90,
                73,
                250,
                182,
            ),
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        329,
        bytes(
            (
                190,
                7,
                134,
                204,
                73,
                12,
                83,
                89,
                150,
                245,
                74,
                175,
                43,
                150,
                233,
                73,
                238,
                54,
                247,
                200,
                61,
                249,
                47,
                6,
                242,
                181,
                149,
                38,
                27,
                221,
                59,
                3,
            ),
        ),
        bytes(
            (
                241,
                195,
                216,
                56,
                234,
                159,
                240,
                168,
                215,
                67,
                52,
                171,
                107,
                206,
                95,
                52,
                201,
                219,
                12,
                218,
                238,
                115,
                235,
                6,
                76,
                89,
                78,
                147,
                196,
                219,
                156,
                72,
            ),
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        329,
        bytes(
            (
                190,
                7,
                134,
                204,
                73,
                12,
                83,
                89,
                150,
                245,
                74,
                175,
                43,
                150,
                233,
                73,
                238,
                54,
                247,
                200,
                61,
                249,
                47,
                6,
                242,
                181,
                149,
                38,
                27,
                221,
                59,
                3,
            ),
        ),
        bytes(
            (
                241,
                195,
                216,
                56,
                234,
                159,
                240,
                168,
                215,
                67,
                52,
                171,
                107,
                206,
                95,
                52,
                201,
                219,
                12,
                218,
                238,
                115,
                235,
                6,
                76,
                89,
                78,
                147,
                196,
                219,
                156,
                72,
            ),
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        453,
        bytes(
            (
                5,
                119,
                252,
                92,
                121,
                172,
                138,
                69,
                131,
                143,
                38,
                124,
                2,
                212,
                42,
                225,
                97,
                105,
                218,
                226,
                144,
                30,
                235,
                187,
                177,
                71,
                19,
                160,
                5,
                64,
                120,
                13,
            ),
        ),
        bytes(
            (
                231,
                34,
                253,
                201,
                1,
                60,
                8,
                7,
                33,
                32,
                151,
                11,
                136,
                164,
                8,
                199,
                24,
                85,
                137,
                181,
                163,
                181,
                218,
                138,
                127,
                1,
                202,
                149,
                113,
                78,
                244,
                6,
            ),
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        461,
        bytes(
            (
                51,
                21,
                119,
                103,
                190,
                104,
                91,
                156,
                180,
                177,
                33,
                75,
                34,
                38,
                133,
                39,
                39,
                115,
                41,
                14,
                200,
                133,
                163,
                31,
                176,
                171,
                63,
                41,
                10,
                9,
                177,
                96,
            ),
        ),
        bytes(
            (
                64,
                255,
                132,
                156,
                29,
                99,
                81,
                207,
                197,
                108,
                139,
                160,
                28,
                130,
                187,
                154,
                202,
                165,
                7,
                96,
                182,
                246,
                8,
                71,
                170,
                184,
                20,
                57,
                254,
                44,
                22,
                216,
            ),
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        469,
        bytes(
            (
                212,
                104,
                127,
                137,
                6,
                152,
                103,
                10,
                180,
                140,
                255,
                66,
                69,
                99,
                59,
                226,
                183,
                114,
                52,
                87,
                5,
                22,
                142,
                180,
                63,
                94,
                98,
                114,
                173,
                29,
                178,
                77,
            ),
        ),
        bytes(
            (
                206,
                91,
                95,
                123,
                102,
                144,
                42,
                73,
                34,
                195,
                245,
                159,
                71,
                202,
                214,
                250,
                85,
                214,
                5,
                60,
                137,
                240,
                236,
                163,
                150,
                73,
                29,
                111,
                164,
                69,
                74,
                87,
            ),
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        481,
        bytes(
            (
                208,
                244,
                56,
                126,
                73,
                229,
                75,
                16,
                225,
                225,
                250,
                100,
                12,
                68,
                66,
                2,
                107,
                136,
                99,
                165,
                0,
                118,
                227,
                142,
                10,
                180,
                218,
                61,
                44,
                183,
                102,
                44,
            ),
        ),
        bytes(
            (
                98,
                199,
                186,
                126,
                24,
                52,
                160,
                20,
                15,
                153,
                60,
                110,
                111,
                169,
                38,
                176,
                222,
                72,
                253,
                247,
                115,
                23,
                182,
                238,
                0,
                111,
                243,
                124,
                201,
                123,
                216,
                200,
            ),
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        485,
        bytes(
            (
                126,
                55,
                80,
                153,
                194,
                17,
                189,
                28,
                175,
                108,
                118,
                46,
                21,
                21,
                82,
                159,
                21,
                201,
                122,
                166,
                168,
                178,
                51,
                156,
                183,
                117,
                150,
                21,
                28,
                129,
                70,
                65,
            ),
        ),
        bytes(
            (
                211,
                105,
                35,
                154,
                66,
                97,
                138,
                211,
                144,
                155,
                167,
                137,
                153,
                50,
                53,
                120,
                234,
                227,
                219,
                175,
                202,
                165,
                5,
                156,
                39,
                41,
                184,
                107,
                158,
                63,
                14,
                32,
            ),
        ),
    ),
    (
        "scripts/kind/aud373_internal_mtls_proof.sh",
        246,
        bytes(
            (
                32,
                152,
                216,
                158,
                65,
                208,
                136,
                98,
                208,
                16,
                155,
                123,
                112,
                72,
                61,
                45,
                53,
                182,
                189,
                17,
                66,
                99,
                47,
                154,
                172,
                182,
                82,
                144,
                240,
                225,
                202,
                232,
            ),
        ),
        bytes(
            (
                90,
                208,
                222,
                86,
                194,
                99,
                30,
                137,
                217,
                84,
                23,
                119,
                11,
                159,
                174,
                155,
                157,
                93,
                192,
                45,
                37,
                150,
                94,
                104,
                178,
                164,
                56,
                167,
                26,
                131,
                66,
                1,
            ),
        ),
    ),
    (
        "scripts/kind/aud373_internal_mtls_proof.sh",
        248,
        bytes(
            (
                203,
                110,
                165,
                203,
                116,
                137,
                2,
                174,
                62,
                26,
                75,
                15,
                179,
                181,
                77,
                64,
                182,
                220,
                77,
                175,
                207,
                216,
                90,
                5,
                136,
                123,
                32,
                97,
                230,
                135,
                29,
                89,
            ),
        ),
        bytes(
            (
                113,
                130,
                105,
                92,
                121,
                216,
                169,
                25,
                235,
                116,
                177,
                19,
                228,
                21,
                179,
                54,
                94,
                73,
                178,
                243,
                185,
                22,
                222,
                95,
                189,
                128,
                176,
                163,
                147,
                101,
                25,
                66,
            ),
        ),
    ),
    (
        "scripts/kind/aud373_internal_mtls_proof.sh",
        349,
        bytes(
            (
                247,
                46,
                161,
                63,
                225,
                39,
                194,
                134,
                60,
                209,
                210,
                221,
                120,
                158,
                234,
                171,
                231,
                171,
                98,
                47,
                205,
                55,
                224,
                197,
                14,
                228,
                18,
                137,
                114,
                221,
                224,
                38,
            ),
        ),
        bytes(
            (
                207,
                176,
                158,
                194,
                253,
                157,
                191,
                79,
                80,
                194,
                136,
                14,
                241,
                149,
                196,
                148,
                181,
                232,
                241,
                248,
                85,
                79,
                44,
                107,
                205,
                9,
                57,
                179,
                19,
                96,
                119,
                162,
            ),
        ),
    ),
    (
        "scripts/kind/aud373_internal_mtls_proof.sh",
        369,
        bytes(
            (
                27,
                29,
                44,
                252,
                35,
                100,
                112,
                237,
                33,
                80,
                1,
                88,
                30,
                103,
                200,
                15,
                43,
                72,
                53,
                247,
                246,
                137,
                57,
                149,
                247,
                72,
                34,
                18,
                248,
                22,
                245,
                144,
            ),
        ),
        bytes(
            (
                220,
                30,
                228,
                248,
                209,
                219,
                79,
                122,
                102,
                114,
                75,
                52,
                31,
                202,
                189,
                51,
                209,
                200,
                9,
                213,
                209,
                48,
                166,
                111,
                47,
                123,
                231,
                115,
                246,
                11,
                212,
                9,
            ),
        ),
    ),
    (
        "scripts/quality/helm_rendered_target_overlay.py",
        37,
        bytes(
            (
                8,
                107,
                203,
                16,
                175,
                231,
                48,
                49,
                200,
                41,
                129,
                43,
                197,
                0,
                154,
                219,
                25,
                249,
                11,
                168,
                176,
                9,
                253,
                128,
                209,
                189,
                127,
                140,
                199,
                141,
                186,
                226,
            ),
        ),
        bytes(
            (
                26,
                5,
                99,
                160,
                29,
                38,
                152,
                144,
                186,
                73,
                121,
                3,
                222,
                102,
                7,
                215,
                162,
                235,
                158,
                49,
                129,
                190,
                195,
                33,
                77,
                34,
                3,
                178,
                234,
                128,
                182,
                166,
            ),
        ),
    ),
    (
        "tests/integration/test_aud433_notifications_baseline_partition.py",
        32,
        bytes(
            (
                115,
                121,
                15,
                241,
                107,
                64,
                244,
                86,
                155,
                72,
                211,
                4,
                171,
                159,
                37,
                173,
                5,
                238,
                4,
                13,
                53,
                254,
                183,
                77,
                61,
                255,
                139,
                19,
                67,
                229,
                75,
                240,
            ),
        ),
        bytes(
            (
                60,
                116,
                93,
                99,
                24,
                175,
                183,
                156,
                123,
                26,
                193,
                88,
                193,
                237,
                202,
                244,
                80,
                247,
                52,
                41,
                86,
                61,
                108,
                22,
                15,
                75,
                176,
                38,
                199,
                163,
                94,
                247,
            ),
        ),
    ),
    (
        "tests/integration/test_aud433_notifications_baseline_partition.py",
        35,
        bytes(
            (
                243,
                103,
                141,
                119,
                143,
                17,
                117,
                202,
                158,
                18,
                109,
                91,
                146,
                54,
                44,
                204,
                249,
                103,
                103,
                234,
                26,
                87,
                55,
                239,
                114,
                147,
                35,
                10,
                210,
                173,
                46,
                71,
            ),
        ),
        bytes(
            (
                221,
                90,
                42,
                234,
                194,
                52,
                105,
                35,
                146,
                131,
                149,
                135,
                80,
                160,
                179,
                183,
                155,
                213,
                210,
                247,
                178,
                87,
                171,
                153,
                127,
                47,
                203,
                138,
                245,
                149,
                151,
                237,
            ),
        ),
    ),
    (
        "tests/integration/test_aud433_notifications_baseline_partition.py",
        38,
        bytes(
            (
                206,
                117,
                230,
                210,
                74,
                140,
                120,
                65,
                253,
                226,
                111,
                154,
                36,
                32,
                60,
                211,
                45,
                104,
                96,
                172,
                56,
                128,
                244,
                144,
                167,
                246,
                250,
                154,
                127,
                19,
                251,
                124,
            ),
        ),
        bytes(
            (
                48,
                68,
                110,
                98,
                216,
                101,
                19,
                101,
                78,
                7,
                38,
                97,
                210,
                208,
                159,
                209,
                27,
                248,
                204,
                16,
                214,
                210,
                102,
                229,
                68,
                15,
                237,
                13,
                142,
                58,
                5,
                17,
            ),
        ),
    ),
    (
        "tests/integration/test_aud433_notifications_baseline_partition.py",
        58,
        bytes(
            (
                82,
                237,
                53,
                6,
                40,
                243,
                139,
                52,
                177,
                178,
                51,
                28,
                111,
                115,
                229,
                53,
                33,
                255,
                94,
                178,
                248,
                41,
                126,
                177,
                173,
                197,
                70,
                79,
                145,
                134,
                148,
                132,
            ),
        ),
        bytes(
            (
                143,
                83,
                203,
                241,
                247,
                181,
                53,
                169,
                115,
                150,
                191,
                29,
                255,
                223,
                147,
                248,
                92,
                142,
                106,
                37,
                80,
                240,
                52,
                49,
                44,
                139,
                36,
                99,
                90,
                167,
                171,
                120,
            ),
        ),
    ),
    (
        "tests/integration/test_aud433_notifications_baseline_partition.py",
        59,
        bytes(
            (
                33,
                134,
                67,
                215,
                48,
                59,
                183,
                167,
                19,
                238,
                172,
                32,
                56,
                229,
                40,
                125,
                245,
                105,
                131,
                187,
                153,
                119,
                45,
                75,
                223,
                213,
                124,
                20,
                26,
                99,
                86,
                123,
            ),
        ),
        bytes(
            (
                219,
                246,
                222,
                170,
                119,
                71,
                153,
                149,
                220,
                155,
                138,
                133,
                112,
                16,
                55,
                213,
                81,
                118,
                234,
                242,
                158,
                23,
                222,
                218,
                236,
                27,
                221,
                33,
                208,
                145,
                128,
                251,
            ),
        ),
    ),
    (
        "tests/integration/test_aud433_notifications_baseline_partition.py",
        61,
        bytes(
            (
                169,
                12,
                46,
                206,
                20,
                150,
                53,
                20,
                27,
                145,
                162,
                101,
                210,
                76,
                39,
                246,
                114,
                28,
                24,
                247,
                26,
                58,
                222,
                168,
                198,
                204,
                50,
                35,
                60,
                66,
                228,
                216,
            ),
        ),
        bytes(
            (
                47,
                215,
                165,
                133,
                62,
                222,
                234,
                133,
                188,
                91,
                150,
                41,
                213,
                140,
                240,
                149,
                38,
                91,
                117,
                125,
                111,
                192,
                120,
                82,
                109,
                217,
                14,
                145,
                95,
                224,
                105,
                117,
            ),
        ),
    ),
    (
        "tests/integration/test_aud433_notifications_baseline_partition.py",
        62,
        bytes(
            (
                194,
                220,
                254,
                104,
                232,
                8,
                127,
                197,
                64,
                43,
                204,
                47,
                21,
                3,
                16,
                40,
                188,
                175,
                186,
                191,
                46,
                63,
                52,
                240,
                77,
                38,
                103,
                147,
                230,
                122,
                101,
                142,
            ),
        ),
        bytes(
            (
                244,
                2,
                219,
                222,
                27,
                25,
                179,
                212,
                244,
                247,
                232,
                36,
                102,
                102,
                170,
                120,
                102,
                53,
                199,
                29,
                40,
                222,
                82,
                78,
                208,
                155,
                55,
                28,
                144,
                211,
                128,
                79,
            ),
        ),
    ),
    (
        "tests/test_helm_rendered_target_overlay.py",
        96,
        bytes(
            (
                8,
                107,
                203,
                16,
                175,
                231,
                48,
                49,
                200,
                41,
                129,
                43,
                197,
                0,
                154,
                219,
                25,
                249,
                11,
                168,
                176,
                9,
                253,
                128,
                209,
                189,
                127,
                140,
                199,
                141,
                186,
                226,
            ),
        ),
        bytes(
            (
                249,
                104,
                35,
                122,
                71,
                176,
                239,
                131,
                206,
                252,
                29,
                211,
                192,
                8,
                223,
                43,
                15,
                86,
                61,
                141,
                161,
                95,
                192,
                173,
                226,
                184,
                183,
                189,
                127,
                249,
                104,
                177,
            ),
        ),
    ),
    (
        "tests/test_internal_mtls_kind_contract.py",
        1352,
        bytes(
            (
                37,
                91,
                244,
                236,
                15,
                129,
                103,
                138,
                67,
                22,
                233,
                89,
                250,
                241,
                223,
                39,
                224,
                96,
                135,
                242,
                108,
                238,
                56,
                241,
                119,
                75,
                8,
                123,
                100,
                116,
                23,
                88,
            ),
        ),
        bytes(
            (
                125,
                211,
                99,
                95,
                123,
                99,
                76,
                86,
                205,
                149,
                191,
                160,
                179,
                85,
                65,
                233,
                11,
                191,
                228,
                118,
                75,
                236,
                52,
                75,
                110,
                180,
                238,
                2,
                50,
                167,
                118,
                43,
            ),
        ),
    ),
    (
        "tests/test_internal_mtls_kind_contract.py",
        1353,
        bytes(
            (
                66,
                250,
                15,
                196,
                76,
                193,
                65,
                47,
                49,
                180,
                76,
                16,
                59,
                67,
                191,
                248,
                18,
                38,
                56,
                178,
                86,
                54,
                54,
                133,
                160,
                153,
                112,
                57,
                136,
                178,
                62,
                210,
            ),
        ),
        bytes(
            (
                3,
                204,
                115,
                50,
                140,
                110,
                133,
                26,
                163,
                96,
                190,
                17,
                48,
                191,
                106,
                150,
                196,
                11,
                172,
                157,
                163,
                178,
                93,
                109,
                135,
                39,
                121,
                42,
                202,
                132,
                16,
                48,
            ),
        ),
    ),
    (
        "tests/test_internal_mtls_kind_contract.py",
        1931,
        bytes(
            (
                199,
                202,
                28,
                193,
                232,
                55,
                59,
                111,
                161,
                66,
                105,
                75,
                100,
                235,
                184,
                120,
                238,
                27,
                130,
                71,
                157,
                44,
                41,
                237,
                182,
                215,
                95,
                0,
                187,
                195,
                30,
                189,
            ),
        ),
        bytes(
            (
                177,
                154,
                5,
                144,
                28,
                17,
                9,
                225,
                228,
                46,
                250,
                177,
                109,
                240,
                255,
                120,
                240,
                28,
                183,
                150,
                127,
                122,
                215,
                39,
                212,
                142,
                14,
                184,
                228,
                104,
                203,
                56,
            ),
        ),
    ),
    (
        "tests/test_internal_mtls_kind_contract.py",
        1936,
        bytes(
            (
                233,
                181,
                145,
                187,
                78,
                144,
                187,
                93,
                3,
                100,
                193,
                175,
                86,
                203,
                184,
                23,
                211,
                174,
                146,
                157,
                6,
                112,
                68,
                119,
                233,
                10,
                106,
                173,
                45,
                243,
                139,
                120,
            ),
        ),
        bytes(
            (
                6,
                182,
                255,
                141,
                167,
                253,
                52,
                224,
                51,
                127,
                2,
                213,
                25,
                102,
                119,
                63,
                219,
                44,
                6,
                250,
                90,
                160,
                105,
                234,
                25,
                238,
                142,
                132,
                126,
                162,
                20,
                120,
            ),
        ),
    ),
    (
        "tests/test_internal_mtls_kind_contract.py",
        1937,
        bytes(
            (
                235,
                136,
                244,
                84,
                8,
                189,
                43,
                29,
                89,
                172,
                228,
                20,
                15,
                179,
                25,
                136,
                133,
                120,
                145,
                191,
                249,
                160,
                27,
                203,
                152,
                241,
                108,
                158,
                148,
                237,
                91,
                37,
            ),
        ),
        bytes(
            (
                125,
                201,
                228,
                147,
                47,
                217,
                50,
                182,
                50,
                236,
                142,
                64,
                241,
                202,
                144,
                33,
                145,
                47,
                60,
                55,
                76,
                232,
                33,
                117,
                104,
                20,
                200,
                66,
                223,
                29,
                96,
                211,
            ),
        ),
    ),
    (
        "tests/test_internal_mtls_kind_contract.py",
        1945,
        bytes(
            (
                181,
                140,
                242,
                109,
                103,
                195,
                123,
                74,
                171,
                175,
                226,
                232,
                103,
                202,
                28,
                37,
                36,
                183,
                28,
                126,
                229,
                132,
                105,
                126,
                154,
                191,
                150,
                112,
                237,
                226,
                188,
                93,
            ),
        ),
        bytes(
            (
                94,
                70,
                245,
                236,
                74,
                204,
                188,
                33,
                34,
                183,
                97,
                96,
                45,
                186,
                149,
                236,
                169,
                135,
                217,
                54,
                211,
                190,
                195,
                250,
                219,
                177,
                244,
                67,
                240,
                101,
                99,
                239,
            ),
        ),
    ),
    (
        "tests/test_internal_mtls_kind_contract.py",
        1949,
        bytes(
            (
                84,
                118,
                99,
                181,
                181,
                51,
                132,
                105,
                251,
                155,
                22,
                243,
                3,
                92,
                173,
                108,
                55,
                75,
                43,
                176,
                16,
                86,
                57,
                208,
                160,
                37,
                126,
                235,
                210,
                152,
                178,
                108,
            ),
        ),
        bytes(
            (
                141,
                57,
                199,
                224,
                111,
                211,
                165,
                33,
                251,
                153,
                69,
                248,
                128,
                74,
                42,
                47,
                175,
                184,
                203,
                178,
                92,
                217,
                207,
                184,
                11,
                113,
                187,
                35,
                135,
                5,
                63,
                88,
            ),
        ),
    ),
    (
        "tests/test_internal_mtls_kind_contract.py",
        1953,
        bytes(
            (
                199,
                193,
                177,
                55,
                88,
                84,
                44,
                211,
                51,
                240,
                96,
                98,
                156,
                181,
                149,
                104,
                204,
                184,
                65,
                131,
                10,
                139,
                137,
                243,
                9,
                14,
                17,
                214,
                56,
                203,
                117,
                97,
            ),
        ),
        bytes(
            (
                184,
                220,
                70,
                245,
                214,
                0,
                116,
                49,
                252,
                20,
                146,
                168,
                153,
                183,
                168,
                175,
                208,
                165,
                92,
                186,
                152,
                28,
                52,
                181,
                232,
                142,
                31,
                69,
                31,
                227,
                101,
                145,
            ),
        ),
    ),
    (
        "tests/test_internal_mtls_kind_contract.py",
        1981,
        bytes(
            (
                1,
                241,
                113,
                4,
                208,
                13,
                30,
                0,
                203,
                243,
                74,
                47,
                48,
                159,
                96,
                111,
                23,
                164,
                79,
                225,
                222,
                219,
                78,
                112,
                234,
                241,
                79,
                60,
                167,
                84,
                142,
                118,
            ),
        ),
        bytes(
            (
                244,
                1,
                160,
                252,
                202,
                43,
                84,
                11,
                207,
                177,
                121,
                2,
                131,
                248,
                30,
                250,
                93,
                25,
                163,
                238,
                212,
                232,
                30,
                125,
                132,
                191,
                13,
                33,
                50,
                243,
                72,
                41,
            ),
        ),
    ),
    (
        "tests/test_seed_demo_data.py",
        112,
        bytes(
            (
                40,
                85,
                172,
                159,
                248,
                155,
                29,
                5,
                95,
                156,
                33,
                13,
                240,
                181,
                142,
                125,
                150,
                83,
                83,
                169,
                40,
                43,
                138,
                195,
                62,
                76,
                122,
                112,
                95,
                232,
                91,
                16,
            ),
        ),
        bytes(
            (
                29,
                58,
                151,
                107,
                191,
                10,
                41,
                4,
                74,
                49,
                50,
                138,
                88,
                112,
                51,
                182,
                172,
                251,
                79,
                224,
                249,
                21,
                255,
                49,
                86,
                135,
                65,
                138,
                183,
                43,
                25,
                238,
            ),
        ),
    ),
    (
        "tests/test_temporal_namespace_init_fake_cli.py",
        41,
        bytes(
            (
                202,
                187,
                39,
                119,
                255,
                15,
                213,
                226,
                2,
                241,
                18,
                68,
                234,
                223,
                40,
                85,
                241,
                148,
                94,
                50,
                204,
                224,
                18,
                60,
                16,
                94,
                42,
                38,
                53,
                143,
                196,
                95,
            ),
        ),
        bytes(
            (
                247,
                223,
                224,
                132,
                72,
                145,
                23,
                130,
                58,
                151,
                71,
                136,
                238,
                40,
                219,
                236,
                58,
                94,
                90,
                57,
                193,
                172,
                3,
                110,
                13,
                78,
                135,
                127,
                75,
                9,
                104,
                149,
            ),
        ),
    ),
    (
        "tests/test_temporal_namespace_init_fake_cli.py",
        45,
        bytes(
            (
                152,
                189,
                127,
                123,
                113,
                85,
                231,
                147,
                37,
                71,
                138,
                87,
                247,
                39,
                116,
                32,
                89,
                19,
                237,
                202,
                221,
                239,
                68,
                19,
                120,
                122,
                128,
                72,
                57,
                132,
                203,
                164,
            ),
        ),
        bytes(
            (
                222,
                82,
                179,
                35,
                202,
                255,
                42,
                74,
                139,
                50,
                3,
                207,
                163,
                210,
                103,
                76,
                194,
                58,
                140,
                31,
                249,
                216,
                205,
                163,
                70,
                241,
                220,
                151,
                184,
                65,
                37,
                48,
            ),
        ),
    ),
)


def _assert_aud380_n3_conditional_policy(
    policy: dict[str, Any], base_policy: dict[str, Any]
) -> None:
    expected_header = {
        key: value for key, value in base_policy.items() if key != "records"
    }
    actual_header = {key: value for key, value in policy.items() if key != "records"}
    assert actual_header == expected_header, "conditional N3 policy header changed"
    base_records = base_policy["records"]
    records = policy.get("records")
    assert isinstance(records, list)
    assert len(base_records) == 490
    assert records[:490] == base_records, "approved 490-row prefix changed"
    assert len(records) == 493, "conditional N3 row count changed"

    pending_records = copy.deepcopy(_AUD380_N3_PENDING_OWNER_RECORDS)
    assert all(row["approval_status"] == "NOT_APPROVED" for row in pending_records)
    assert all(
        row["reviewed_on"] == "2026-11-06" and row["expires_on"] == "2027-01-10"
        for row in pending_records
    )
    assert Counter(row["category"] for row in pending_records) == Counter(
        _AUD380_N3_PENDING_CATEGORY_COUNTS
    )
    assert _aud380_canonical_records_digest(pending_records) == (
        _AUD380_N3_PENDING_ADDITIONS_SHA256
    )
    assert {_aud380_identity_key(row) for row in pending_records} == set(
        _AUD380_N3_PENDING_OWNER_IDENTITIES
    )

    expected_suffix = copy.deepcopy(pending_records)
    for row in expected_suffix:
        row["approval_status"] = "approved"
    assert records[490:] == expected_suffix, "conditional N3 suffix changed"
    identities = [_aud380_identity_key(row) for row in records]
    assert len(identities) == len(set(identities)), (
        "conditional policy identities duplicated"
    )
    assert not (
        {_aud380_identity_key(row) for row in base_records}
        & set(_AUD380_N3_PENDING_OWNER_IDENTITIES)
    )
    assert _aud380_canonical_records_digest(expected_suffix) == (
        _AUD380_N3_APPROVED_ADDITIONS_SHA256
    )
    assert (
        _aud380_ordered_records_digest([*base_records, *pending_records])
        == _AUD380_N3_PENDING_493_RECORDSET_SHA256
    )
    assert _aud380_ordered_records_digest(records) == (
        _AUD380_N3_CONDITIONAL_493_RECORDSET_SHA256
    )

    expected_counts = Counter(_AUD380_CURRENT_DELTA_CATEGORY_COUNTS) + Counter(
        _AUD380_N3_PENDING_CATEGORY_COUNTS
    )
    assert Counter(row["category"] for row in records) == expected_counts


def _assert_aud380_n3_source_bindings(
    repository_root: Path,
    *,
    source_sha256: dict[str, bytes] | None = None,
    identity_source_lines: tuple[tuple[str, str, tuple[int, ...], str, int], ...]
    | None = None,
    source_line_hashes: tuple[tuple[str, int, bytes, bytes], ...] | None = None,
) -> None:
    source_sha256 = _AUD380_N3_SOURCE_SHA256 if source_sha256 is None else source_sha256
    identity_source_lines = (
        _AUD380_N3_IDENTITY_SOURCE_LINES
        if identity_source_lines is None
        else identity_source_lines
    )
    source_line_hashes = (
        _AUD380_N3_SOURCE_LINE_HASHES
        if source_line_hashes is None
        else source_line_hashes
    )
    assert source_sha256 == _AUD380_N3_SOURCE_SHA256, "N3 source hash bindings changed"
    assert identity_source_lines == _AUD380_N3_IDENTITY_SOURCE_LINES, (
        "N3 identity line bindings changed"
    )
    assert source_line_hashes == _AUD380_N3_SOURCE_LINE_HASHES, (
        "N3 source line hash bindings changed"
    )
    assert len(source_sha256) == 2
    assert len(identity_source_lines) == len(_AUD380_N3_PENDING_OWNER_IDENTITIES) == 3
    assert len(source_line_hashes) == 3
    assert all(len(digest) == 32 for digest in source_sha256.values())
    assert all(
        len(line_hash) == len(context_hash) == 32
        for _, _, line_hash, context_hash in source_line_hashes
    )

    expected_identity_keys = set(_AUD380_N3_PENDING_OWNER_IDENTITIES)
    identity_line_keys = {
        (path, finding_type, digest)
        for path, finding_type, digest, _category, _line in identity_source_lines
    }
    assert identity_line_keys == expected_identity_keys
    pending_by_identity = {
        _aud380_identity_key(row): row for row in _AUD380_N3_PENDING_OWNER_RECORDS
    }
    source_bytes_by_path: dict[str, bytes] = {}
    for relative_path, expected_digest in source_sha256.items():
        source_bytes = (repository_root / relative_path).read_bytes()
        assert hashlib.sha256(source_bytes).digest() == expected_digest, (
            f"N3 source file SHA-256 changed: {relative_path}"
        )
        source_bytes_by_path[relative_path] = source_bytes

    assert {path for path, *_rest in identity_source_lines} == set(source_sha256)
    for path, finding_type, digest, category, line_number in identity_source_lines:
        key = (path, finding_type, digest)
        assert key in pending_by_identity
        assert pending_by_identity[key]["category"] == category
        assert (
            1
            <= line_number
            <= len(source_bytes_by_path[path].splitlines(keepends=True))
        )

    expected_line_refs = Counter(
        (path, line_number) for path, *_finding, line_number in identity_source_lines
    )
    assert (
        Counter((path, line) for path, line, *_hashes in source_line_hashes)
        == expected_line_refs
    )
    for path, line_number, line_sha256, context_sha256 in source_line_hashes:
        raw_lines = source_bytes_by_path[path].splitlines(keepends=True)
        line = raw_lines[line_number - 1]
        context = b"".join(
            raw_lines[max(0, line_number - 3) : min(len(raw_lines), line_number + 2)]
        )
        assert hashlib.sha256(line).digest() == line_sha256
        assert hashlib.sha256(context).digest() == context_sha256


def _aud380_n3_conditional_policy() -> dict[str, Any]:
    active_policy = _aud380_conditional_policy()
    pending_projection = copy.deepcopy(active_policy)
    pending_records = copy.deepcopy(_AUD380_N3_PENDING_OWNER_RECORDS)
    pending_projection["records"].extend(pending_records)
    assert _aud380_ordered_records_digest(pending_projection["records"]) == (
        _AUD380_N3_PENDING_493_RECORDSET_SHA256
    )
    conditional = copy.deepcopy(active_policy)
    appended = copy.deepcopy(_AUD380_N3_PENDING_OWNER_RECORDS)
    for row in appended:
        row["approval_status"] = "approved"
    conditional["records"].extend(appended)
    return conditional


def test_aud380_n3_conditional_493_projection_is_exact_append(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _aud380_bind_history_reader(monkeypatch)
    history = _reviewed_pre_retirement_dispositions()
    active_policy = _aud380_conditional_policy()
    expected_base_records = _aud380_expected_active_363(history)
    _assert_aud380_conditional_policy(active_policy, expected_base_records)
    conditional = _aud380_n3_conditional_policy()
    _assert_aud380_n3_conditional_policy(conditional, active_policy)
    assert verifier._AUD380_N3_CI_TEST_SENTINEL_IDENTITIES == (
        _AUD380_N3_PENDING_OWNER_IDENTITIES
    )
    accepted = _nov13_verify_dispositions(conditional, today=verifier.date(2026, 11, 7))
    assert len(accepted) == 493
    assert active_policy["records"] == _aud380_conditional_policy()["records"]


@pytest.mark.parametrize("mutation", ["path", "finding_type", "digest"])
def test_aud380_n3_category_requires_exact_test_sentinel_identity(
    mutation: str,
) -> None:
    record = copy.deepcopy(_AUD380_N3_PENDING_OWNER_RECORDS[0])
    record["approval_status"] = "approved"
    if mutation == "path":
        record["identity"]["path"] = "tests/unreviewed_sentinel.py"
    elif mutation == "finding_type":
        record["identity"]["type"] = "Basic Auth Credentials"
    else:
        record["identity"]["hashed_secret_bytes"][0] ^= 1

    with pytest.raises(
        verifier.BaselineArtifactError,
        match="category does not allow this path and detector type",
    ):
        _nov13_verify_dispositions(
            {"schema_version": 1, "records": [record]},
            today=verifier.date(2026, 11, 7),
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "header",
        "base_record",
        "owner",
        "review_date",
        "expiry",
        "evidence",
        "category",
        "path",
        "finding_type",
        "digest",
        "status",
        "missing",
        "unknown",
        "duplicate",
        "suffix_order",
    ],
)
def test_aud380_n3_conditional_493_projection_rejects_mutations(
    mutation: str,
) -> None:
    active_policy = _aud380_conditional_policy()
    policy = _aud380_n3_conditional_policy()
    suffix_index = 490
    if mutation == "header":
        policy["schema_version"] = 2
    elif mutation == "base_record":
        policy["records"][0]["owner"] = "unreviewed-owner"
    elif mutation == "owner":
        policy["records"][suffix_index]["owner"] = "unreviewed-owner"
    elif mutation == "review_date":
        policy["records"][suffix_index]["reviewed_on"] = "2026-11-05"
    elif mutation == "expiry":
        policy["records"][suffix_index]["expires_on"] = "2027-01-11"
    elif mutation == "evidence":
        policy["records"][suffix_index]["evidence"] += " changed"
    elif mutation == "category":
        policy["records"][suffix_index]["category"] = "public_integrity_digest"
    elif mutation == "path":
        policy["records"][suffix_index]["identity"]["path"] += ".unreviewed"
    elif mutation == "finding_type":
        policy["records"][suffix_index]["identity"]["type"] = "unreviewed type"
    elif mutation == "digest":
        policy["records"][suffix_index]["identity"]["hashed_secret_bytes"][0] ^= 1
    elif mutation == "status":
        policy["records"][suffix_index]["approval_status"] = "NOT_APPROVED"
    elif mutation == "missing":
        policy["records"].pop()
    elif mutation == "unknown":
        policy["records"][suffix_index]["identity"]["path"] = "tests/unreviewed.py"
    elif mutation == "duplicate":
        policy["records"].append(copy.deepcopy(policy["records"][suffix_index]))
    else:
        policy["records"][490], policy["records"][491] = (
            policy["records"][491],
            policy["records"][490],
        )

    with pytest.raises(AssertionError):
        _assert_aud380_n3_conditional_policy(policy, active_policy)


def test_aud380_n3_pending_records_keep_status_and_expiry_boundaries() -> None:
    pending = copy.deepcopy(_AUD380_N3_PENDING_OWNER_RECORDS)
    assert all(row["approval_status"] == "NOT_APPROVED" for row in pending)
    assert all(row["reviewed_on"] == "2026-11-06" for row in pending)
    assert all(row["expires_on"] == "2027-01-10" for row in pending)
    approved_for_validation = copy.deepcopy(pending)
    for row in approved_for_validation:
        row["approval_status"] = "approved"
    single_policy = {"schema_version": 1, "records": approved_for_validation}
    for today in (verifier.date(2026, 11, 6), verifier.date(2027, 1, 10)):
        assert len(_nov13_verify_dispositions(single_policy, today=today)) == 3
    for today in (verifier.date(2026, 11, 5), verifier.date(2027, 1, 11)):
        with pytest.raises(verifier.BaselineArtifactError, match="date range"):
            _nov13_verify_dispositions(single_policy, today=today)


def test_aud380_n3_source_bindings_and_fail_closed_mutations(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    _assert_aud380_n3_source_bindings(repository_root)

    changed_hashes = dict(_AUD380_N3_SOURCE_SHA256)
    first_source = sorted(changed_hashes)[0]
    changed_hashes[first_source] = (
        bytes([changed_hashes[first_source][0] ^ 1]) + changed_hashes[first_source][1:]
    )
    with pytest.raises(AssertionError, match="N3 source hash bindings changed"):
        _assert_aud380_n3_source_bindings(repository_root, source_sha256=changed_hashes)

    changed_identity_lines = list(_AUD380_N3_IDENTITY_SOURCE_LINES)
    first_identity = changed_identity_lines[0]
    changed_identity_lines[0] = (*first_identity[:-1], first_identity[-1] + 1)
    with pytest.raises(AssertionError, match="N3 identity line bindings changed"):
        _assert_aud380_n3_source_bindings(
            repository_root, identity_source_lines=tuple(changed_identity_lines)
        )

    changed_line_hashes = list(_AUD380_N3_SOURCE_LINE_HASHES)
    first_line = changed_line_hashes[0]
    changed_line_hashes[0] = (
        *first_line[:-1],
        bytes([first_line[-1][0] ^ 1]) + first_line[-1][1:],
    )
    with pytest.raises(AssertionError, match="N3 source line hash bindings changed"):
        _assert_aud380_n3_source_bindings(
            repository_root, source_line_hashes=tuple(changed_line_hashes)
        )

    mutated_root = tmp_path
    for relative_path in _AUD380_N3_SOURCE_SHA256:
        target = mutated_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((repository_root / relative_path).read_bytes())
    mutated_path = mutated_root / first_source
    mutated_path.write_bytes(mutated_path.read_bytes() + b"\n# source drift control\n")
    with pytest.raises(AssertionError, match="N3 source file SHA-256 changed"):
        _assert_aud380_n3_source_bindings(mutated_root)


def test_aud380_safehtml_wasm_provenance_and_license_restore_are_consistent() -> None:
    candidate_root = Path(__file__).resolve().parents[1]
    repository_root = candidate_root
    ledger = json.loads(
        (candidate_root / "quality/semgrep-dispositions.json").read_text(
            encoding="utf-8"
        )
    )
    safehtml_rows = [
        row
        for row in ledger["dispositions"]
        if row["path"] == "frontend/src/components/ui/SafeHtml.tsx"
        and row["check_id"]
        == (
            "typescript.react.security.audit.react-dangerouslysetinnerhtml."
            "react-dangerouslysetinnerhtml"
        )
    ]
    assert len(safehtml_rows) == 1

    expected_companion_paths = {
        "frontend/src/components/ui/__tests__/SafeHtml.test.tsx",
        "frontend/src/utils/trustedTypes.ts",
        "frontend/src/utils/htmlText.ts",
        "frontend/scripts/server-csp.mjs",
        "frontend/WASM_SOURCE_PROVENANCE.json",
        "frontend/wasm-sanitizer/src/lib.rs",
        "frontend/wasm-sanitizer/Cargo.toml",
        "frontend/wasm-sanitizer/Cargo.lock",
        "frontend/wasm-sanitizer/pkg/package.json",
        "frontend/wasm-sanitizer/pkg/wasm_sanitizer.js",
        "frontend/wasm-sanitizer/pkg/wasm_sanitizer_bg.wasm",
        "frontend/package.json",
        "frontend/package-lock.json",
    }
    companions = safehtml_rows[0]["companions"]
    assert len(companions) == len(expected_companion_paths)
    assert {companion["path"] for companion in companions} == (expected_companion_paths)
    for companion in companions:
        source = (repository_root / companion["path"]).read_bytes()
        assert hashlib.sha256(source).hexdigest() == companion["sha256"], (
            f"SafeHtml companion digest is stale: {companion['path']}"
        )

    provenance_path = repository_root / "frontend/WASM_SOURCE_PROVENANCE.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    expected_source_paths = {
        "rust-crypto/Cargo.toml",
        "rust-crypto/Cargo.lock",
        "rust-crypto/src/lib.rs",
        "wasm-sanitizer/Cargo.toml",
        "wasm-sanitizer/Cargo.lock",
        "wasm-sanitizer/src/lib.rs",
    }
    source_records = provenance["source_files"]
    assert len(source_records) == len(expected_source_paths)
    assert {record["path"] for record in source_records} == expected_source_paths
    assert [record["path"] for record in source_records] == sorted(
        expected_source_paths
    )
    for record in source_records:
        source = (repository_root / "frontend" / record["path"]).read_bytes()
        assert record == {
            "path": record["path"],
            "size": len(source),
            "sha256": hashlib.sha256(source).hexdigest(),
        }
    serialized_sources = json.dumps(
        source_records, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    assert (
        provenance["source_tree_sha256"]
        == hashlib.sha256(serialized_sources).hexdigest()
    )

    expected_package_paths = {
        "rust-crypto/pkg/package.json",
        "rust-crypto/pkg/uni_wasm_crypto_bg.wasm",
        "rust-crypto/pkg/uni_wasm_crypto.d.ts",
        "rust-crypto/pkg/uni_wasm_crypto.js",
        "wasm-sanitizer/pkg/package.json",
        "wasm-sanitizer/pkg/wasm_sanitizer_bg.wasm",
        "wasm-sanitizer/pkg/wasm_sanitizer.d.ts",
        "wasm-sanitizer/pkg/wasm_sanitizer.js",
    }
    package_records = provenance["packages"]
    assert len(package_records) == len(expected_package_paths)
    assert set(package_records) == expected_package_paths
    for relative_path, record in package_records.items():
        package_file = (repository_root / "frontend" / relative_path).read_bytes()
        assert record == {
            "size": len(package_file),
            "sha256": hashlib.sha256(package_file).hexdigest(),
        }

    for relative_path in (
        "frontend/rust-crypto/Cargo.toml",
        "frontend/wasm-sanitizer/Cargo.toml",
    ):
        manifest = tomllib.loads(
            (repository_root / relative_path).read_text(encoding="utf-8")
        )
        assert manifest["package"]["license"] == "MIT"

    for relative_path in (
        "frontend/rust-crypto/pkg/package.json",
        "frontend/wasm-sanitizer/pkg/package.json",
    ):
        package = json.loads(
            (repository_root / relative_path).read_text(encoding="utf-8")
        )
        assert package["license"] == "MIT"

    frontend_package = json.loads(
        (repository_root / "frontend/package.json").read_text(encoding="utf-8")
    )
    assert frontend_package["license"] == "MIT"


# AUD380 final N4 projection is conditional only; the active 490 policy remains untouched.
def _aud380_n4_conditional_policy() -> dict[str, Any]:
    active = _aud380_conditional_policy()
    conditional = copy.deepcopy(active)
    appended = copy.deepcopy(_AUD380_N4_PENDING_OWNER_RECORDS)
    for row in appended:
        row["approval_status"] = "approved"
    conditional["records"].extend(appended)
    return conditional


def _assert_aud380_n4_conditional_policy(
    conditional: dict[str, Any], active: dict[str, Any]
) -> None:
    expected_header = {key: value for key, value in active.items() if key != "records"}
    actual_header = {
        key: value for key, value in conditional.items() if key != "records"
    }
    assert actual_header == expected_header, "conditional N4 policy header changed"
    active_records = active["records"]
    records = conditional.get("records")
    assert isinstance(records, list)
    assert len(active_records) == 490
    assert records[:490] == active_records, "approved 490-row prefix changed"
    assert len(records) == 494, "conditional N4 row count changed"

    pending = copy.deepcopy(_AUD380_N4_PENDING_OWNER_RECORDS)
    assert len(pending) == 4
    assert all(row["approval_status"] == "NOT_APPROVED" for row in pending)
    assert all(
        row["reviewed_on"] == "2026-11-06" and row["expires_on"] == "2027-01-10"
        for row in pending
    )
    assert pending[1:] == _AUD380_N3_PENDING_OWNER_RECORDS
    assert {_aud380_identity_key(row) for row in pending} == set(
        _AUD380_N4_PENDING_OWNER_IDENTITIES
    )
    assert Counter(row["category"] for row in pending) == Counter(
        {"public_integrity_digest": 1, "ci_test_contract_sentinel": 3}
    )
    expected_suffix = copy.deepcopy(pending)
    for row in expected_suffix:
        row["approval_status"] = "approved"
    assert records[490:] == expected_suffix, "conditional N4 suffix changed"
    all_keys = [_aud380_identity_key(row) for row in records]
    assert len(all_keys) == len(set(all_keys)), "conditional N4 identities duplicated"
    assert not (
        {_aud380_identity_key(row) for row in active_records}
        & set(_AUD380_N4_PENDING_OWNER_IDENTITIES)
    )
    expected_counts = Counter(row["category"] for row in active_records) + Counter(
        row["category"] for row in pending
    )
    assert Counter(row["category"] for row in records) == expected_counts


@pytest.mark.parametrize(
    "mutation",
    [
        "extra_row",
        "changed_prefix",
        "changed_n6_suffix",
        "changed_zlib_suffix",
        "changed_row13",
        "header",
    ],
)
def test_aud380_live_approved_policy_requires_exact_506_projection(
    mutation: str,
) -> None:
    live_policy = _nov9_historical_506_from_live_policy(_aud380_read_live_policy())
    historical_490 = _aud380_conditional_policy()
    _aud428_assert_live_policy_is_exact_506(live_policy, historical_490)

    changed = copy.deepcopy(live_policy)
    if mutation == "extra_row":
        changed["records"].append(copy.deepcopy(changed["records"][495]))
    elif mutation == "changed_prefix":
        changed["records"][0]["owner"] = "unreviewed-owner"
    elif mutation == "changed_n6_suffix":
        changed["records"][495]["approval_status"] = "NOT_APPROVED"
    elif mutation == "changed_zlib_suffix":
        changed["records"][497]["identity"]["hashed_secret_bytes"][0] ^= 1
    elif mutation == "changed_row13":
        changed["records"][505]["identity"]["hashed_secret_bytes"][0] ^= 1
    else:
        changed["schema_version"] = 2

    with pytest.raises(AssertionError):
        _aud428_assert_live_policy_is_exact_506(changed, historical_490)


def test_aud380_n4_conditional_494_projection_is_exact_append() -> None:
    active = _aud380_conditional_policy()
    conditional = _aud380_n4_conditional_policy()
    _assert_aud380_n4_conditional_policy(conditional, active)
    accepted = _nov13_verify_dispositions(conditional, today=verifier.date(2026, 11, 7))
    assert len(accepted) == 494
    assert active["records"] == _aud380_conditional_policy()["records"]


@pytest.mark.parametrize(
    "mutation",
    [
        "new_path",
        "new_type",
        "new_digest",
        "new_category",
        "new_evidence",
        "new_owner",
        "new_review_date",
        "new_expiry",
        "new_status",
        "missing_new",
        "unknown_new",
        "duplicate_new",
        "suffix_order",
        "old_prefix",
    ],
)
def test_aud380_n4_conditional_494_projection_rejects_mutations(
    mutation: str,
) -> None:
    active = _aud380_conditional_policy()
    conditional = _aud380_n4_conditional_policy()
    records = conditional["records"]
    target = records[490]
    if mutation == "new_path":
        target["identity"]["path"] += ".unreviewed"
    elif mutation == "new_type":
        target["identity"]["type"] = "unreviewed detector"
    elif mutation == "new_digest":
        target["identity"]["hashed_secret_bytes"][0] ^= 1
    elif mutation == "new_category":
        target["category"] = "ci_test_contract_sentinel"
    elif mutation == "new_evidence":
        target["evidence"] += " changed"
    elif mutation == "new_owner":
        target["owner"] = "unreviewed-owner"
    elif mutation == "new_review_date":
        target["reviewed_on"] = "2026-11-05"
    elif mutation == "new_expiry":
        target["expires_on"] = "2027-01-11"
    elif mutation == "new_status":
        target["approval_status"] = "NOT_APPROVED"
    elif mutation == "missing_new":
        records.pop()
    elif mutation == "unknown_new":
        target["identity"]["path"] = "tests/unreviewed.py"
    elif mutation == "duplicate_new":
        records.append(copy.deepcopy(target))
    elif mutation == "suffix_order":
        records[490], records[491] = records[491], records[490]
    else:
        records[0]["owner"] = "unreviewed-owner"
    with pytest.raises(AssertionError):
        _assert_aud380_n4_conditional_policy(conditional, active)


def test_aud380_n4_rows_keep_pending_status_and_expiry_boundaries() -> None:
    pending = copy.deepcopy(_AUD380_N4_PENDING_OWNER_RECORDS)
    assert len(pending) == 4
    assert all(row["approval_status"] == "NOT_APPROVED" for row in pending)
    assert all(row["reviewed_on"] == "2026-11-06" for row in pending)
    assert all(row["expires_on"] == "2027-01-10" for row in pending)
    approved = copy.deepcopy(pending)
    for row in approved:
        row["approval_status"] = "approved"
    for row in approved:
        single = {"schema_version": 1, "records": [row]}
        for today in (verifier.date(2026, 11, 6), verifier.date(2027, 1, 10)):
            assert len(_nov13_verify_dispositions(single, today=today)) == 1
        for today in (verifier.date(2026, 11, 5), verifier.date(2027, 1, 11)):
            with pytest.raises(verifier.BaselineArtifactError, match="date range"):
                _nov13_verify_dispositions(single, today=today)


def test_aud380_n4_exact_n3_sentinels_and_row7_digest_are_finite() -> None:
    row7_record = _AUD380_N4_PENDING_OWNER_RECORDS[0]
    assert _aud380_identity_key(row7_record) == _AUD380_N4_PUBLIC_LEDGER_IDENTITY
    assert _AUD380_N4_PUBLIC_LEDGER_IDENTITY == (
        _AUD380_N4_IDENTITY_SOURCE_LINES[0][0],
        _AUD380_N4_IDENTITY_SOURCE_LINES[0][1],
        _AUD380_N4_IDENTITY_SOURCE_LINES[0][2],
    )
    assert _AUD380_N4_IDENTITY_SOURCE_LINES[0][3:] == (
        "public_integrity_digest",
        189,
    )
    assert (
        _aud380_canonical_records_digest(_AUD380_N4_PENDING_OWNER_RECORDS)
        == _AUD380_N4_PENDING_ADDITIONS_SHA256
    )
    _assert_conditional_owner_source_bindings(Path(__file__).resolve().parents[1])
    assert _AUD380_N4_PENDING_OWNER_IDENTITIES == {
        *_AUD380_N3_PENDING_OWNER_IDENTITIES,
        _AUD380_N4_PUBLIC_LEDGER_IDENTITY,
    }
    assert _AUD380_N4_PENDING_OWNER_RECORDS[1:] == _AUD380_N3_PENDING_OWNER_RECORDS
    approved = copy.deepcopy(_AUD380_N4_PENDING_OWNER_RECORDS)
    for row in approved:
        row["approval_status"] = "approved"
    for record in approved[1:]:
        assert (
            len(
                _nov13_verify_dispositions(
                    _disposition_document(record), today=verifier.date(2026, 11, 7)
                )
            )
            == 1
        )
        for field in ("path", "type"):
            changed = copy.deepcopy(record)
            changed["identity"][field] += ".unreviewed"
            with pytest.raises(verifier.BaselineArtifactError):
                _nov13_verify_dispositions(
                    _disposition_document(changed), today=verifier.date(2026, 11, 7)
                )
        changed = copy.deepcopy(record)
        changed["identity"]["hashed_secret_bytes"][0] ^= 1
        with pytest.raises(verifier.BaselineArtifactError):
            _nov13_verify_dispositions(
                _disposition_document(changed), today=verifier.date(2026, 11, 7)
            )


# AUD380 N5 is a single pending public integrity digest; it is not active.
_AUD380_N5_PENDING_OWNER_RECORDS = [
    {
        "approval_status": "NOT_APPROVED",
        "category": "public_integrity_digest",
        "evidence": "Public source-integrity metadata: this detector identity is the SHA-1 fingerprint of the new SHA-256 companion pin for frontend/package-lock.json in SafeHtml disposition row 15 at quality/semgrep-dispositions.json:485. It identifies a repository lockfile postimage and is not credential material.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                5,
                50,
                51,
                248,
                2,
                60,
                24,
                74,
                178,
                202,
                233,
                226,
                82,
                114,
                206,
                64,
                209,
                108,
                123,
                230,
            ],
            "path": "quality/semgrep-dispositions.json",
            "type": "Hex High Entropy String",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    }
]
_AUD380_N5_PUBLIC_LEDGER_IDENTITY = (
    "quality/semgrep-dispositions.json",
    "Hex High Entropy String",
    (
        5,
        50,
        51,
        248,
        2,
        60,
        24,
        74,
        178,
        202,
        233,
        226,
        82,
        114,
        206,
        64,
        209,
        108,
        123,
        230,
    ),
)
_AUD380_N5_PENDING_OWNER_IDENTITIES = frozenset((_AUD380_N5_PUBLIC_LEDGER_IDENTITY,))
_AUD380_N5_PENDING_ADDITIONS_SHA256 = bytes(
    (
        226,
        200,
        163,
        222,
        9,
        31,
        98,
        121,
        145,
        64,
        80,
        251,
        191,
        26,
        102,
        36,
        227,
        117,
        15,
        243,
        83,
        221,
        88,
        60,
        209,
        141,
        52,
        90,
        89,
        117,
        79,
        94,
    )
)
_AUD380_N5_IDENTITY_SOURCE_LINES = (
    (
        "quality/semgrep-dispositions.json",
        "Hex High Entropy String",
        _AUD380_N5_PUBLIC_LEDGER_IDENTITY[2],
        "public_integrity_digest",
        485,
    ),
)
_AUD380_N5_LINE_SHA256 = bytes(
    (
        3,
        23,
        118,
        0,
        131,
        40,
        143,
        4,
        138,
        233,
        46,
        30,
        18,
        39,
        14,
        35,
        115,
        221,
        243,
        199,
        193,
        77,
        175,
        124,
        23,
        74,
        68,
        146,
        46,
        247,
        74,
        119,
    )
)
_AUD380_N5_CONTEXT_SHA256 = bytes(
    (
        0,
        18,
        188,
        145,
        111,
        207,
        41,
        22,
        122,
        225,
        186,
        117,
        134,
        122,
        51,
        142,
        22,
        214,
        165,
        121,
        214,
        0,
        184,
        145,
        74,
        205,
        186,
        161,
        207,
        0,
        221,
        2,
    )
)
_AUD380_CURRENT_DELTA_SOURCE_SHA256 = {
    **_AUD380_CURRENT_DELTA_SOURCE_SHA256,
    "quality/semgrep-dispositions.json": bytes(
        (
            132,
            233,
            4,
            127,
            17,
            236,
            0,
            94,
            87,
            2,
            197,
            78,
            105,
            181,
            135,
            143,
            204,
            216,
            66,
            154,
            235,
            201,
            246,
            248,
            22,
            57,
            114,
            47,
            57,
            169,
            109,
            120,
        )
    ),
    "frontend/package-lock.json": bytes(
        (
            160,
            9,
            242,
            165,
            109,
            117,
            82,
            210,
            135,
            169,
            233,
            186,
            190,
            234,
            176,
            180,
            147,
            90,
            176,
            0,
            131,
            110,
            180,
            101,
            3,
            208,
            160,
            94,
            190,
            199,
            210,
            12,
        )
    ),
}
_AUD380_CURRENT_DELTA_IDENTITY_SOURCE_LINES = (
    *_AUD380_CURRENT_DELTA_IDENTITY_SOURCE_LINES,
    *_AUD380_N5_IDENTITY_SOURCE_LINES,
)
_AUD380_CURRENT_DELTA_SOURCE_LINE_HASHES = (
    *(
        (path, line, _AUD380_N5_LINE_SHA256, _AUD380_N5_CONTEXT_SHA256)
        if path == "quality/semgrep-dispositions.json" and line == 485
        else (path, line, line_hash, context_hash)
        for path, line, line_hash, context_hash in _AUD380_CURRENT_DELTA_SOURCE_LINE_HASHES
    ),
    (
        "quality/semgrep-dispositions.json",
        485,
        _AUD380_N5_LINE_SHA256,
        _AUD380_N5_CONTEXT_SHA256,
    ),
)


def _aud380_n5_conditional_policy() -> dict[str, Any]:
    active_494 = _aud380_n4_conditional_policy()
    conditional = copy.deepcopy(active_494)
    appended = copy.deepcopy(_AUD380_N5_PENDING_OWNER_RECORDS)
    for row in appended:
        row["approval_status"] = "approved"
    conditional["records"].extend(appended)
    assert _aud380_canonical_records_digest(_AUD380_N5_PENDING_OWNER_RECORDS) == (
        _AUD380_N5_PENDING_ADDITIONS_SHA256
    )
    return conditional


def _assert_aud380_n5_conditional_policy(
    conditional: dict[str, Any], active_494: dict[str, Any]
) -> None:
    assert len(active_494["records"]) == 494
    assert len(conditional.get("records", [])) == 495
    expected_header = {
        key: value for key, value in active_494.items() if key != "records"
    }
    actual_header = {
        key: value for key, value in conditional.items() if key != "records"
    }
    assert actual_header == expected_header, "conditional N5 policy header changed"
    records = conditional["records"]
    assert records[:494] == active_494["records"], "approved 494-row prefix changed"
    pending = copy.deepcopy(_AUD380_N5_PENDING_OWNER_RECORDS)
    assert len(pending) == 1
    assert pending[0]["approval_status"] == "NOT_APPROVED"
    assert pending[0]["reviewed_on"] == "2026-11-06"
    assert pending[0]["expires_on"] == "2027-01-10"
    assert _aud380_identity_key(pending[0]) == _AUD380_N5_PUBLIC_LEDGER_IDENTITY
    expected_suffix = copy.deepcopy(pending)
    expected_suffix[0]["approval_status"] = "approved"
    assert records[494:] == expected_suffix, "conditional N5 suffix changed"
    assert (
        _aud380_canonical_records_digest(pending) == _AUD380_N5_PENDING_ADDITIONS_SHA256
    )
    keys = [_aud380_identity_key(row) for row in records]
    assert len(keys) == len(set(keys)), "conditional N5 identities duplicated"
    assert not (
        {_aud380_identity_key(row) for row in active_494["records"]}
        & set(_AUD380_N5_PENDING_OWNER_IDENTITIES)
    )
    expected_counts = Counter(
        row["category"] for row in active_494["records"]
    ) + Counter({"public_integrity_digest": 1})
    assert Counter(row["category"] for row in records) == expected_counts


def test_aud380_n5_conditional_495_projection_is_exact_append() -> None:
    active_494 = _aud380_n4_conditional_policy()
    conditional = _aud380_n5_conditional_policy()
    _assert_aud380_n5_conditional_policy(conditional, active_494)
    accepted = _nov13_verify_dispositions(conditional, today=verifier.date(2026, 11, 7))
    assert len(accepted) == 495
    assert active_494["records"] == _aud380_n4_conditional_policy()["records"]


@pytest.mark.parametrize(
    "mutation",
    [
        "header",
        "prefix",
        "path",
        "finding_type",
        "digest",
        "category",
        "owner",
        "date",
        "expiry",
        "evidence",
        "status",
        "missing",
        "extra",
        "duplicate",
    ],
)
def test_aud380_n5_conditional_495_projection_rejects_mutations(mutation: str) -> None:
    active_494 = _aud380_n4_conditional_policy()
    changed = _aud380_n5_conditional_policy()
    row = changed["records"][494]
    if mutation == "header":
        changed["schema_version"] = 2
    elif mutation == "prefix":
        changed["records"][0]["owner"] = "unreviewed-owner"
    elif mutation == "path":
        row["identity"]["path"] += ".unreviewed"
    elif mutation == "finding_type":
        row["identity"]["type"] = "unreviewed detector"
    elif mutation == "digest":
        row["identity"]["hashed_secret_bytes"][0] ^= 1
    elif mutation == "category":
        row["category"] = "ci_test_contract_sentinel"
    elif mutation == "owner":
        row["owner"] = "unreviewed-owner"
    elif mutation == "date":
        row["reviewed_on"] = "2026-11-05"
    elif mutation == "expiry":
        row["expires_on"] = "2027-01-11"
    elif mutation == "evidence":
        row["evidence"] += " changed"
    elif mutation == "status":
        row["approval_status"] = "NOT_APPROVED"
    elif mutation == "missing":
        changed["records"].pop()
    elif mutation == "extra":
        changed["records"].append(copy.deepcopy(row))
    else:
        changed["records"][493], changed["records"][494] = (
            changed["records"][494],
            changed["records"][493],
        )
    with pytest.raises(AssertionError):
        _assert_aud380_n5_conditional_policy(changed, active_494)


def test_aud380_n5_pending_status_expiry_and_exact_source_binding() -> None:
    pending = copy.deepcopy(_AUD380_N5_PENDING_OWNER_RECORDS[0])
    assert pending["approval_status"] == "NOT_APPROVED"
    assert _aud380_identity_key(pending) == (
        "quality/semgrep-dispositions.json",
        "Hex High Entropy String",
        _AUD380_N5_PUBLIC_LEDGER_IDENTITY[2],
    )
    approved = copy.deepcopy(pending)
    approved["approval_status"] = "approved"
    for today in (verifier.date(2026, 11, 6), verifier.date(2027, 1, 10)):
        assert (
            len(
                _nov13_verify_dispositions(_disposition_document(approved), today=today)
            )
            == 1
        )
    for today in (verifier.date(2026, 11, 5), verifier.date(2027, 1, 11)):
        with pytest.raises(verifier.BaselineArtifactError, match="date range"):
            _nov13_verify_dispositions(_disposition_document(approved), today=today)
    _assert_conditional_owner_source_bindings(Path(__file__).resolve().parents[1])


# CI58 source rebind: exact current staged files and row7-10 overlay inputs.
_AUD380_CI58_SOURCE_LINE_HASH_OVERRIDES = {
    ("quality/semgrep-dispositions.json", 189): (
        bytes(
            (
                151,
                203,
                152,
                100,
                184,
                0,
                234,
                81,
                65,
                102,
                211,
                114,
                8,
                183,
                143,
                132,
                81,
                44,
                249,
                214,
                78,
                127,
                137,
                158,
                100,
                247,
                162,
                237,
                228,
                148,
                160,
                200,
            )
        ),
        bytes(
            (
                105,
                100,
                76,
                15,
                77,
                87,
                226,
                10,
                238,
                208,
                152,
                210,
                98,
                124,
                56,
                103,
                143,
                191,
                147,
                144,
                102,
                78,
                223,
                18,
                193,
                169,
                43,
                84,
                2,
                197,
                239,
                53,
            )
        ),
    ),
    ("quality/semgrep-dispositions.json", 229): (
        bytes(
            (
                124,
                204,
                33,
                9,
                47,
                7,
                193,
                167,
                104,
                194,
                118,
                32,
                22,
                75,
                189,
                232,
                13,
                143,
                73,
                19,
                44,
                150,
                181,
                5,
                188,
                21,
                222,
                54,
                193,
                156,
                126,
                45,
            )
        ),
        bytes(
            (
                42,
                89,
                97,
                51,
                8,
                247,
                195,
                203,
                81,
                53,
                30,
                114,
                47,
                100,
                228,
                8,
                83,
                4,
                243,
                186,
                49,
                131,
                184,
                227,
                202,
                127,
                189,
                21,
                31,
                118,
                177,
                235,
            )
        ),
    ),
    ("quality/semgrep-dispositions.json", 257): (
        bytes(
            (
                124,
                204,
                33,
                9,
                47,
                7,
                193,
                167,
                104,
                194,
                118,
                32,
                22,
                75,
                189,
                232,
                13,
                143,
                73,
                19,
                44,
                150,
                181,
                5,
                188,
                21,
                222,
                54,
                193,
                156,
                126,
                45,
            )
        ),
        bytes(
            (
                42,
                89,
                97,
                51,
                8,
                247,
                195,
                203,
                81,
                53,
                30,
                114,
                47,
                100,
                228,
                8,
                83,
                4,
                243,
                186,
                49,
                131,
                184,
                227,
                202,
                127,
                189,
                21,
                31,
                118,
                177,
                235,
            )
        ),
    ),
    ("quality/semgrep-dispositions.json", 285): (
        bytes(
            (
                124,
                204,
                33,
                9,
                47,
                7,
                193,
                167,
                104,
                194,
                118,
                32,
                22,
                75,
                189,
                232,
                13,
                143,
                73,
                19,
                44,
                150,
                181,
                5,
                188,
                21,
                222,
                54,
                193,
                156,
                126,
                45,
            )
        ),
        bytes(
            (
                42,
                89,
                97,
                51,
                8,
                247,
                195,
                203,
                81,
                53,
                30,
                114,
                47,
                100,
                228,
                8,
                83,
                4,
                243,
                186,
                49,
                131,
                184,
                227,
                202,
                127,
                189,
                21,
                31,
                118,
                177,
                235,
            )
        ),
    ),
    ("tests/test_helm_rendered_target_overlay.py", 96): (
        bytes(
            (
                146,
                226,
                31,
                5,
                222,
                243,
                226,
                181,
                187,
                185,
                194,
                118,
                228,
                134,
                244,
                73,
                30,
                55,
                177,
                49,
                192,
                225,
                211,
                84,
                82,
                240,
                214,
                221,
                219,
                157,
                69,
                180,
            )
        ),
        bytes(
            (
                107,
                84,
                46,
                14,
                42,
                204,
                12,
                225,
                16,
                171,
                200,
                28,
                239,
                151,
                46,
                23,
                68,
                255,
                161,
                220,
                109,
                215,
                216,
                6,
                93,
                63,
                243,
                235,
                216,
                173,
                5,
                125,
            )
        ),
    ),
    ("tests/test_internal_mtls_kind_contract.py", 1352): (
        bytes(
            (
                16,
                124,
                35,
                133,
                35,
                161,
                226,
                95,
                5,
                139,
                227,
                189,
                86,
                81,
                113,
                165,
                203,
                15,
                217,
                254,
                86,
                221,
                174,
                116,
                233,
                234,
                42,
                123,
                202,
                79,
                46,
                235,
            )
        ),
        bytes(
            (
                199,
                7,
                20,
                149,
                183,
                172,
                202,
                181,
                111,
                176,
                71,
                49,
                71,
                83,
                152,
                16,
                54,
                83,
                179,
                144,
                36,
                67,
                114,
                174,
                242,
                229,
                67,
                8,
                28,
                109,
                227,
                22,
            )
        ),
    ),
    ("tests/test_internal_mtls_kind_contract.py", 1353): (
        bytes(
            (
                173,
                210,
                68,
                88,
                43,
                111,
                176,
                61,
                35,
                184,
                65,
                90,
                190,
                205,
                52,
                107,
                12,
                159,
                70,
                107,
                111,
                117,
                43,
                6,
                129,
                137,
                206,
                126,
                154,
                45,
                195,
                80,
            )
        ),
        bytes(
            (
                78,
                75,
                233,
                41,
                217,
                89,
                73,
                157,
                80,
                108,
                185,
                110,
                169,
                2,
                141,
                96,
                199,
                57,
                99,
                143,
                45,
                165,
                179,
                196,
                184,
                178,
                85,
                253,
                183,
                20,
                159,
                144,
            )
        ),
    ),
    ("tests/test_internal_mtls_kind_contract.py", 1931): (
        bytes(
            (
                222,
                178,
                84,
                83,
                126,
                36,
                163,
                17,
                233,
                39,
                92,
                98,
                25,
                158,
                106,
                1,
                220,
                155,
                144,
                205,
                235,
                13,
                126,
                18,
                110,
                44,
                193,
                149,
                157,
                186,
                78,
                203,
            )
        ),
        bytes(
            (
                197,
                127,
                202,
                103,
                65,
                22,
                177,
                24,
                247,
                173,
                181,
                42,
                31,
                254,
                115,
                234,
                51,
                56,
                220,
                139,
                56,
                161,
                150,
                97,
                144,
                133,
                147,
                14,
                203,
                255,
                150,
                39,
            )
        ),
    ),
    ("tests/test_internal_mtls_kind_contract.py", 1936): (
        bytes(
            (
                1,
                186,
                71,
                25,
                200,
                11,
                111,
                233,
                17,
                176,
                145,
                167,
                192,
                81,
                36,
                182,
                78,
                238,
                206,
                150,
                78,
                9,
                192,
                88,
                239,
                143,
                152,
                5,
                218,
                202,
                84,
                107,
            )
        ),
        bytes(
            (
                159,
                147,
                169,
                56,
                126,
                9,
                12,
                68,
                9,
                9,
                250,
                173,
                61,
                166,
                229,
                57,
                190,
                120,
                104,
                168,
                48,
                193,
                156,
                29,
                169,
                180,
                29,
                196,
                108,
                118,
                48,
                184,
            )
        ),
    ),
    ("tests/test_internal_mtls_kind_contract.py", 1937): (
        bytes(
            (
                1,
                186,
                71,
                25,
                200,
                11,
                111,
                233,
                17,
                176,
                145,
                167,
                192,
                81,
                36,
                182,
                78,
                238,
                206,
                150,
                78,
                9,
                192,
                88,
                239,
                143,
                152,
                5,
                218,
                202,
                84,
                107,
            )
        ),
        bytes(
            (
                230,
                186,
                51,
                9,
                171,
                252,
                74,
                154,
                86,
                37,
                35,
                1,
                226,
                254,
                80,
                7,
                209,
                154,
                234,
                73,
                171,
                210,
                133,
                188,
                48,
                172,
                176,
                126,
                207,
                196,
                214,
                145,
            )
        ),
    ),
    ("tests/test_internal_mtls_kind_contract.py", 1945): (
        bytes(
            (
                214,
                191,
                40,
                19,
                134,
                197,
                180,
                21,
                241,
                28,
                225,
                129,
                125,
                236,
                9,
                100,
                81,
                94,
                51,
                202,
                85,
                12,
                95,
                175,
                62,
                213,
                55,
                36,
                94,
                147,
                77,
                14,
            )
        ),
        bytes(
            (
                27,
                3,
                42,
                255,
                170,
                69,
                232,
                215,
                87,
                34,
                156,
                58,
                238,
                175,
                192,
                164,
                104,
                187,
                65,
                151,
                141,
                152,
                220,
                109,
                114,
                226,
                190,
                204,
                75,
                120,
                250,
                52,
            )
        ),
    ),
    ("tests/test_internal_mtls_kind_contract.py", 1949): (
        bytes(
            (
                232,
                231,
                5,
                208,
                159,
                144,
                192,
                62,
                55,
                86,
                70,
                19,
                37,
                246,
                54,
                189,
                99,
                49,
                26,
                67,
                230,
                16,
                39,
                117,
                121,
                156,
                150,
                229,
                71,
                115,
                126,
                91,
            )
        ),
        bytes(
            (
                116,
                164,
                214,
                9,
                65,
                165,
                213,
                95,
                160,
                87,
                149,
                61,
                6,
                160,
                239,
                251,
                91,
                15,
                130,
                114,
                240,
                210,
                41,
                233,
                47,
                240,
                186,
                254,
                79,
                47,
                222,
                34,
            )
        ),
    ),
    ("tests/test_internal_mtls_kind_contract.py", 1953): (
        bytes(
            (
                31,
                224,
                62,
                121,
                166,
                212,
                172,
                64,
                100,
                229,
                57,
                30,
                1,
                173,
                142,
                136,
                91,
                160,
                62,
                238,
                146,
                197,
                45,
                93,
                169,
                120,
                12,
                94,
                216,
                247,
                117,
                119,
            )
        ),
        bytes(
            (
                33,
                16,
                232,
                191,
                230,
                42,
                251,
                111,
                50,
                127,
                88,
                197,
                63,
                209,
                172,
                124,
                202,
                73,
                75,
                254,
                206,
                87,
                97,
                70,
                169,
                208,
                99,
                99,
                223,
                83,
                44,
                176,
            )
        ),
    ),
    ("tests/test_internal_mtls_kind_contract.py", 1981): (
        bytes(
            (
                242,
                162,
                10,
                208,
                58,
                169,
                25,
                243,
                131,
                134,
                100,
                232,
                57,
                78,
                97,
                215,
                29,
                233,
                235,
                95,
                26,
                201,
                225,
                2,
                252,
                16,
                124,
                110,
                180,
                136,
                245,
                189,
            )
        ),
        bytes(
            (
                45,
                49,
                57,
                120,
                200,
                125,
                148,
                51,
                46,
                154,
                128,
                91,
                47,
                22,
                114,
                69,
                95,
                122,
                9,
                120,
                80,
                91,
                54,
                142,
                163,
                112,
                128,
                124,
                203,
                134,
                155,
                82,
            )
        ),
    ),
    ("tests/test_temporal_namespace_init_fake_cli.py", 41): (
        bytes(
            (
                239,
                168,
                37,
                242,
                201,
                36,
                162,
                2,
                255,
                254,
                64,
                184,
                71,
                101,
                111,
                148,
                106,
                140,
                191,
                203,
                39,
                244,
                127,
                95,
                95,
                12,
                15,
                176,
                243,
                118,
                136,
                68,
            )
        ),
        bytes(
            (
                197,
                130,
                66,
                30,
                4,
                100,
                138,
                16,
                246,
                78,
                238,
                191,
                118,
                22,
                59,
                100,
                126,
                71,
                160,
                194,
                240,
                8,
                128,
                87,
                150,
                162,
                12,
                83,
                41,
                140,
                3,
                8,
            )
        ),
    ),
    ("tests/test_temporal_namespace_init_fake_cli.py", 45): (
        bytes(
            (
                18,
                175,
                55,
                152,
                205,
                196,
                237,
                110,
                90,
                16,
                3,
                209,
                92,
                42,
                166,
                144,
                112,
                63,
                192,
                255,
                96,
                248,
                190,
                2,
                17,
                108,
                195,
                166,
                167,
                63,
                157,
                163,
            )
        ),
        bytes(
            (
                49,
                81,
                208,
                167,
                109,
                182,
                181,
                198,
                22,
                220,
                145,
                231,
                104,
                125,
                98,
                209,
                137,
                183,
                56,
                171,
                180,
                86,
                58,
                108,
                21,
                190,
                37,
                163,
                107,
                180,
                212,
                154,
            )
        ),
    ),
}
_AUD380_CI58_COMPANION_SOURCE_TARGETS = (
    (
        "quality/semgrep-dispositions.json",
        229,
        "tests/test_mfa_deploy_workflow_contract.py",
    ),
    (
        "quality/semgrep-dispositions.json",
        257,
        "tests/test_mfa_deploy_workflow_contract.py",
    ),
    (
        "quality/semgrep-dispositions.json",
        285,
        "tests/test_mfa_deploy_workflow_contract.py",
    ),
)
_AUD380_CURRENT_DELTA_SOURCE_SHA256 = {
    **_AUD380_CURRENT_DELTA_SOURCE_SHA256,
    "scripts/kind/aud373_internal_mtls_proof.sh": bytes(
        (
            57,
            29,
            30,
            130,
            36,
            155,
            172,
            136,
            8,
            225,
            236,
            221,
            46,
            134,
            143,
            195,
            70,
            109,
            127,
            78,
            249,
            97,
            60,
            135,
            12,
            18,
            188,
            249,
            108,
            6,
            154,
            61,
        )
    ),
    "tests/test_helm_rendered_target_overlay.py": bytes(
        (
            175,
            126,
            44,
            156,
            149,
            34,
            254,
            217,
            204,
            125,
            246,
            188,
            22,
            172,
            5,
            167,
            0,
            250,
            11,
            173,
            106,
            64,
            128,
            164,
            53,
            124,
            29,
            49,
            174,
            205,
            107,
            218,
        )
    ),
    "tests/test_internal_mtls_kind_contract.py": bytes(
        (
            3,
            84,
            28,
            181,
            179,
            169,
            123,
            104,
            32,
            94,
            12,
            182,
            228,
            136,
            253,
            150,
            222,
            226,
            3,
            246,
            212,
            56,
            1,
            183,
            76,
            116,
            83,
            104,
            220,
            224,
            222,
            93,
        )
    ),
    "tests/test_temporal_namespace_init_fake_cli.py": bytes(
        (
            215,
            142,
            41,
            127,
            176,
            24,
            213,
            252,
            240,
            144,
            131,
            32,
            122,
            202,
            44,
            54,
            15,
            39,
            240,
            184,
            26,
            254,
            112,
            83,
            3,
            72,
            227,
            122,
            151,
            203,
            194,
            70,
        )
    ),
    "scripts/live_stand.py": bytes(
        (
            34,
            131,
            218,
            123,
            17,
            54,
            118,
            129,
            104,
            89,
            148,
            25,
            240,
            79,
            205,
            172,
            13,
            253,
            84,
            66,
            14,
            21,
            17,
            237,
            196,
            174,
            233,
            55,
            207,
            163,
            174,
            24,
        )
    ),
    "quality/semgrep-dispositions.json": bytes(
        (
            16,
            230,
            73,
            26,
            70,
            156,
            243,
            1,
            31,
            131,
            1,
            71,
            66,
            184,
            216,
            182,
            87,
            61,
            93,
            44,
            48,
            196,
            180,
            253,
            181,
            149,
            70,
            126,
            23,
            7,
            179,
            191,
        )
    ),
    "frontend/package-lock.json": bytes(
        (
            160,
            9,
            242,
            165,
            109,
            117,
            82,
            210,
            135,
            169,
            233,
            186,
            190,
            234,
            176,
            180,
            147,
            90,
            176,
            0,
            131,
            110,
            180,
            101,
            3,
            208,
            160,
            94,
            190,
            199,
            210,
            12,
        )
    ),
    "tests/test_mfa_deploy_workflow_contract.py": bytes(
        (
            127,
            89,
            20,
            179,
            235,
            171,
            157,
            89,
            230,
            254,
            197,
            135,
            250,
            217,
            192,
            128,
            129,
            133,
            245,
            111,
            55,
            57,
            63,
            27,
            203,
            174,
            97,
            2,
            69,
            70,
            205,
            237,
        )
    ),
}
_AUD380_N3_SOURCE_SHA256 = {
    **_AUD380_N3_SOURCE_SHA256,
    "tests/test_seed_demo_data.py": bytes(
        (
            51,
            162,
            170,
            251,
            40,
            87,
            106,
            24,
            116,
            30,
            104,
            145,
            67,
            66,
            125,
            221,
            26,
            91,
            85,
            148,
            163,
            166,
            71,
            250,
            150,
            71,
            193,
            195,
            227,
            163,
            101,
            42,
        )
    ),
    "tests/test_temporal_namespace_init_fake_cli.py": bytes(
        (
            215,
            142,
            41,
            127,
            176,
            24,
            213,
            252,
            240,
            144,
            131,
            32,
            122,
            202,
            44,
            54,
            15,
            39,
            240,
            184,
            26,
            254,
            112,
            83,
            3,
            72,
            227,
            122,
            151,
            203,
            194,
            70,
        )
    ),
}
_AUD380_N3_SOURCE_LINE_HASHES = (
    (
        "tests/test_seed_demo_data.py",
        112,
        bytes(
            (
                40,
                85,
                172,
                159,
                248,
                155,
                29,
                5,
                95,
                156,
                33,
                13,
                240,
                181,
                142,
                125,
                150,
                83,
                83,
                169,
                40,
                43,
                138,
                195,
                62,
                76,
                122,
                112,
                95,
                232,
                91,
                16,
            )
        ),
        bytes(
            (
                29,
                58,
                151,
                107,
                191,
                10,
                41,
                4,
                74,
                49,
                50,
                138,
                88,
                112,
                51,
                182,
                172,
                251,
                79,
                224,
                249,
                21,
                255,
                49,
                86,
                135,
                65,
                138,
                183,
                43,
                25,
                238,
            )
        ),
    ),
    (
        "tests/test_temporal_namespace_init_fake_cli.py",
        45,
        bytes(
            (
                18,
                175,
                55,
                152,
                205,
                196,
                237,
                110,
                90,
                16,
                3,
                209,
                92,
                42,
                166,
                144,
                112,
                63,
                192,
                255,
                96,
                248,
                190,
                2,
                17,
                108,
                195,
                166,
                167,
                63,
                157,
                163,
            )
        ),
        bytes(
            (
                49,
                81,
                208,
                167,
                109,
                182,
                181,
                198,
                22,
                220,
                145,
                231,
                104,
                125,
                98,
                209,
                137,
                183,
                56,
                171,
                180,
                86,
                58,
                108,
                21,
                190,
                37,
                163,
                107,
                180,
                212,
                154,
            )
        ),
    ),
    (
        "tests/test_temporal_namespace_init_fake_cli.py",
        41,
        bytes(
            (
                239,
                168,
                37,
                242,
                201,
                36,
                162,
                2,
                255,
                254,
                64,
                184,
                71,
                101,
                111,
                148,
                106,
                140,
                191,
                203,
                39,
                244,
                127,
                95,
                95,
                12,
                15,
                176,
                243,
                118,
                136,
                68,
            )
        ),
        bytes(
            (
                197,
                130,
                66,
                30,
                4,
                100,
                138,
                16,
                246,
                78,
                238,
                191,
                118,
                22,
                59,
                100,
                126,
                71,
                160,
                194,
                240,
                8,
                128,
                87,
                150,
                162,
                12,
                83,
                41,
                140,
                3,
                8,
            )
        ),
    ),
)
_AUD380_CURRENT_DELTA_COMPANION_SOURCE_LINES = (
    *_AUD380_CURRENT_DELTA_COMPANION_SOURCE_LINES,
    ("quality/semgrep-dispositions.json", 229),
    ("quality/semgrep-dispositions.json", 257),
    ("quality/semgrep-dispositions.json", 285),
)
_AUD380_CURRENT_DELTA_SOURCE_LINE_HASHES = tuple(
    (
        path,
        line_number,
        *_AUD380_CI58_SOURCE_LINE_HASH_OVERRIDES.get(
            (path, line_number), (line_sha256, context_sha256)
        ),
    )
    for path, line_number, line_sha256, context_sha256 in (
        *_AUD380_CURRENT_DELTA_SOURCE_LINE_HASHES,
        ("quality/semgrep-dispositions.json", 229, b"", b""),
        ("quality/semgrep-dispositions.json", 257, b"", b""),
        ("quality/semgrep-dispositions.json", 285, b"", b""),
    )
)


# Exact current source snapshot after the final N6 companion rebind.
_AUD380_N6_FINAL_SOURCE_SHA256 = {
    "quality/semgrep-dispositions.json": bytes(
        (
            243,
            63,
            43,
            79,
            8,
            193,
            197,
            224,
            5,
            231,
            103,
            82,
            164,
            13,
            64,
            217,
            108,
            176,
            127,
            228,
            244,
            242,
            35,
            33,
            36,
            166,
            225,
            27,
            174,
            116,
            191,
            18,
        )
    ),
    "scripts/kind/aud373_internal_mtls_proof.sh": bytes(
        (
            74,
            119,
            31,
            18,
            215,
            172,
            96,
            224,
            69,
            185,
            110,
            234,
            231,
            53,
            134,
            181,
            98,
            86,
            11,
            233,
            54,
            21,
            85,
            248,
            19,
            78,
            132,
            220,
            117,
            247,
            172,
            254,
        )
    ),
    "scripts/live_stand.py": bytes(
        (
            254,
            195,
            25,
            164,
            0,
            218,
            219,
            105,
            148,
            255,
            48,
            239,
            78,
            0,
            65,
            216,
            76,
            189,
            47,
            92,
            48,
            124,
            40,
            93,
            140,
            0,
            109,
            243,
            206,
            167,
            210,
            165,
        )
    ),
    "tests/test_internal_mtls_kind_contract.py": bytes(
        (
            137,
            82,
            83,
            223,
            42,
            80,
            175,
            189,
            151,
            211,
            112,
            195,
            164,
            177,
            56,
            74,
            44,
            54,
            76,
            147,
            70,
            197,
            7,
            89,
            138,
            88,
            206,
            91,
            207,
            12,
            181,
            105,
        )
    ),
}
_AUD380_CURRENT_DELTA_SOURCE_SHA256 = {
    **_AUD380_CURRENT_DELTA_SOURCE_SHA256,
    **_AUD380_N6_FINAL_SOURCE_SHA256,
}
_AUD380_N6_FINAL_SOURCE_LINE_HASHES = {
    ("quality/semgrep-dispositions.json", 189): (
        bytes(
            (
                190,
                253,
                61,
                209,
                1,
                190,
                79,
                244,
                214,
                85,
                16,
                214,
                233,
                121,
                159,
                99,
                111,
                229,
                194,
                60,
                21,
                0,
                111,
                34,
                149,
                9,
                14,
                29,
                240,
                137,
                39,
                130,
            )
        ),
        bytes(
            (
                106,
                45,
                88,
                219,
                185,
                112,
                214,
                213,
                221,
                177,
                213,
                60,
                190,
                188,
                214,
                67,
                241,
                91,
                124,
                140,
                143,
                170,
                247,
                68,
                41,
                200,
                70,
                33,
                196,
                124,
                188,
                105,
            )
        ),
    ),
    ("tests/test_internal_mtls_kind_contract.py", 1352): (
        bytes(
            (
                32,
                7,
                138,
                24,
                251,
                63,
                67,
                149,
                37,
                241,
                96,
                174,
                246,
                41,
                35,
                224,
                72,
                159,
                112,
                51,
                12,
                78,
                138,
                213,
                34,
                193,
                114,
                207,
                199,
                186,
                192,
                138,
            )
        ),
        bytes(
            (
                165,
                207,
                147,
                249,
                42,
                7,
                210,
                181,
                238,
                164,
                167,
                32,
                88,
                81,
                177,
                136,
                130,
                221,
                54,
                113,
                149,
                160,
                56,
                5,
                151,
                117,
                246,
                81,
                218,
                54,
                158,
                117,
            )
        ),
    ),
    ("tests/test_internal_mtls_kind_contract.py", 1353): (
        bytes(
            (
                153,
                243,
                200,
                176,
                21,
                68,
                4,
                114,
                15,
                186,
                186,
                107,
                107,
                117,
                237,
                220,
                192,
                127,
                17,
                0,
                87,
                221,
                108,
                225,
                200,
                27,
                227,
                17,
                116,
                208,
                81,
                201,
            )
        ),
        bytes(
            (
                193,
                105,
                47,
                46,
                253,
                123,
                240,
                240,
                33,
                200,
                129,
                173,
                213,
                167,
                121,
                62,
                148,
                163,
                25,
                5,
                9,
                149,
                161,
                14,
                212,
                190,
                179,
                85,
                128,
                121,
                18,
                165,
            )
        ),
    ),
    ("tests/test_internal_mtls_kind_contract.py", 1931): (
        bytes(
            (
                210,
                34,
                220,
                230,
                225,
                210,
                212,
                205,
                159,
                145,
                22,
                29,
                242,
                106,
                98,
                118,
                127,
                35,
                65,
                165,
                51,
                148,
                79,
                116,
                132,
                190,
                33,
                92,
                144,
                30,
                38,
                67,
            )
        ),
        bytes(
            (
                222,
                106,
                150,
                156,
                161,
                188,
                217,
                1,
                73,
                84,
                255,
                161,
                242,
                138,
                206,
                191,
                152,
                24,
                240,
                6,
                250,
                233,
                72,
                148,
                218,
                123,
                98,
                214,
                210,
                173,
                126,
                207,
            )
        ),
    ),
    ("tests/test_internal_mtls_kind_contract.py", 1936): (
        bytes(
            (
                247,
                142,
                71,
                19,
                160,
                165,
                216,
                218,
                3,
                231,
                120,
                138,
                230,
                54,
                49,
                173,
                254,
                156,
                143,
                9,
                164,
                96,
                206,
                141,
                169,
                146,
                52,
                102,
                82,
                194,
                24,
                241,
            )
        ),
        bytes(
            (
                42,
                53,
                178,
                84,
                192,
                73,
                244,
                7,
                184,
                134,
                103,
                90,
                46,
                24,
                212,
                27,
                247,
                190,
                228,
                228,
                25,
                69,
                254,
                55,
                113,
                138,
                10,
                250,
                42,
                232,
                84,
                161,
            )
        ),
    ),
    ("tests/test_internal_mtls_kind_contract.py", 1937): (
        bytes(
            (
                83,
                55,
                229,
                84,
                50,
                45,
                214,
                106,
                49,
                86,
                76,
                54,
                123,
                155,
                79,
                232,
                165,
                143,
                240,
                147,
                217,
                138,
                179,
                154,
                98,
                166,
                237,
                174,
                72,
                20,
                142,
                235,
            )
        ),
        bytes(
            (
                99,
                151,
                250,
                188,
                225,
                244,
                210,
                10,
                235,
                82,
                6,
                162,
                26,
                70,
                237,
                70,
                103,
                248,
                170,
                249,
                47,
                106,
                226,
                122,
                143,
                151,
                29,
                146,
                159,
                227,
                127,
                18,
            )
        ),
    ),
    ("tests/test_internal_mtls_kind_contract.py", 1945): (
        bytes(
            (
                147,
                226,
                218,
                201,
                91,
                115,
                250,
                30,
                15,
                67,
                248,
                126,
                129,
                228,
                74,
                88,
                13,
                36,
                159,
                168,
                77,
                123,
                15,
                216,
                17,
                3,
                161,
                23,
                72,
                119,
                164,
                248,
            )
        ),
        bytes(
            (
                53,
                111,
                49,
                58,
                37,
                155,
                66,
                140,
                207,
                107,
                184,
                147,
                198,
                241,
                152,
                137,
                109,
                85,
                9,
                34,
                205,
                170,
                125,
                77,
                255,
                171,
                244,
                166,
                52,
                186,
                71,
                175,
            )
        ),
    ),
    ("tests/test_internal_mtls_kind_contract.py", 1949): (
        bytes(
            (
                24,
                8,
                236,
                68,
                225,
                251,
                143,
                5,
                225,
                49,
                17,
                90,
                31,
                121,
                31,
                130,
                99,
                59,
                138,
                195,
                219,
                34,
                19,
                174,
                48,
                252,
                172,
                224,
                64,
                105,
                174,
                230,
            )
        ),
        bytes(
            (
                244,
                22,
                69,
                159,
                244,
                83,
                121,
                218,
                75,
                108,
                215,
                136,
                145,
                155,
                189,
                117,
                213,
                118,
                116,
                249,
                83,
                122,
                161,
                49,
                139,
                221,
                204,
                197,
                182,
                124,
                49,
                96,
            )
        ),
    ),
    ("tests/test_internal_mtls_kind_contract.py", 1953): (
        bytes(
            (
                143,
                232,
                92,
                165,
                95,
                198,
                163,
                215,
                165,
                208,
                191,
                22,
                229,
                208,
                155,
                217,
                146,
                54,
                246,
                198,
                57,
                197,
                145,
                125,
                159,
                15,
                97,
                186,
                96,
                66,
                122,
                43,
            )
        ),
        bytes(
            (
                49,
                155,
                67,
                192,
                55,
                132,
                179,
                238,
                98,
                86,
                139,
                195,
                176,
                140,
                27,
                76,
                43,
                124,
                85,
                165,
                236,
                153,
                117,
                134,
                245,
                217,
                177,
                92,
                170,
                120,
                113,
                109,
            )
        ),
    ),
    ("tests/test_internal_mtls_kind_contract.py", 1981): (
        bytes(
            (
                83,
                55,
                229,
                84,
                50,
                45,
                214,
                106,
                49,
                86,
                76,
                54,
                123,
                155,
                79,
                232,
                165,
                143,
                240,
                147,
                217,
                138,
                179,
                154,
                98,
                166,
                237,
                174,
                72,
                20,
                142,
                235,
            )
        ),
        bytes(
            (
                75,
                85,
                112,
                209,
                129,
                115,
                206,
                182,
                186,
                127,
                253,
                85,
                30,
                104,
                151,
                124,
                113,
                71,
                59,
                146,
                211,
                151,
                51,
                40,
                181,
                182,
                252,
                171,
                124,
                63,
                96,
                147,
            )
        ),
    ),
}
_AUD380_CURRENT_DELTA_SOURCE_LINE_HASHES = tuple(
    (
        path,
        line_number,
        *_AUD380_N6_FINAL_SOURCE_LINE_HASHES.get(
            (path, line_number), (line_sha256, context_sha256)
        ),
    )
    for path, line_number, line_sha256, context_sha256 in _AUD380_CURRENT_DELTA_SOURCE_LINE_HASHES
)


# N6 is a conditional two-record append. Source rows remain NOT_APPROVED.
# N6 is a conditional two-record append. Source rows remain NOT_APPROVED.
_AUD380_N6_PENDING_OWNER_RECORDS = [
    {
        "approval_status": "NOT_APPROVED",
        "category": "public_integrity_digest",
        "evidence": "Public source-integrity metadata: the detector identity is the SHA-1 "
        "fingerprint of the current SHA-256 companion pin for "
        "scripts/live_stand.py in Semgrep disposition row 7 at "
        "quality/semgrep-dispositions.json:189. This identifies a public "
        "repository source digest and is not credential material.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                234,
                142,
                92,
                143,
                88,
                100,
                245,
                112,
                176,
                105,
                153,
                243,
                132,
                30,
                133,
                85,
                28,
                92,
                173,
                31,
            ],
            "path": "quality/semgrep-dispositions.json",
            "type": "Hex High Entropy String",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
    {
        "approval_status": "NOT_APPROVED",
        "category": "public_integrity_digest",
        "evidence": "Public source-integrity metadata: the detector identity is the SHA-1 "
        "fingerprint of the current SHA-256 companion pin for "
        "tests/test_mfa_deploy_workflow_contract.py, shared by Semgrep "
        "disposition rows 8, 9, and 10; the finding is at "
        "quality/semgrep-dispositions.json:229. This identifies a public "
        "repository test-source digest and is not credential material.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                42,
                115,
                152,
                130,
                13,
                167,
                15,
                147,
                189,
                116,
                17,
                6,
                78,
                24,
                118,
                143,
                178,
                142,
                190,
                218,
            ],
            "path": "quality/semgrep-dispositions.json",
            "type": "Hex High Entropy String",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
]

_AUD380_N6_EXPECTED_IDENTITIES = frozenset(
    {
        (
            "quality/semgrep-dispositions.json",
            "Hex High Entropy String",
            (
                234,
                142,
                92,
                143,
                88,
                100,
                245,
                112,
                176,
                105,
                153,
                243,
                132,
                30,
                133,
                85,
                28,
                92,
                173,
                31,
            ),
        ),
        (
            "quality/semgrep-dispositions.json",
            "Hex High Entropy String",
            (
                42,
                115,
                152,
                130,
                13,
                167,
                15,
                147,
                189,
                116,
                17,
                6,
                78,
                24,
                118,
                143,
                178,
                142,
                190,
                218,
            ),
        ),
    }
)

_AUD380_N6_IDENTITY_SOURCE_LINES = (
    (
        "quality/semgrep-dispositions.json",
        "Hex High Entropy String",
        (
            234,
            142,
            92,
            143,
            88,
            100,
            245,
            112,
            176,
            105,
            153,
            243,
            132,
            30,
            133,
            85,
            28,
            92,
            173,
            31,
        ),
        "public_integrity_digest",
        189,
    ),
    (
        "quality/semgrep-dispositions.json",
        "Hex High Entropy String",
        (
            42,
            115,
            152,
            130,
            13,
            167,
            15,
            147,
            189,
            116,
            17,
            6,
            78,
            24,
            118,
            143,
            178,
            142,
            190,
            218,
        ),
        "public_integrity_digest",
        229,
    ),
)

_AUD380_N6_PENDING_ADDITIONS_SHA256 = bytes(
    (
        94,
        207,
        46,
        236,
        239,
        192,
        255,
        245,
        76,
        77,
        22,
        193,
        21,
        131,
        159,
        190,
        74,
        234,
        17,
        240,
        189,
        164,
        227,
        166,
        41,
        182,
        33,
        198,
        81,
        138,
        133,
        235,
    )
)

_AUD380_N6_SOURCE_LINE_HASHES = (
    (
        "quality/semgrep-dispositions.json",
        189,
        bytes(
            (
                190,
                253,
                61,
                209,
                1,
                190,
                79,
                244,
                214,
                85,
                16,
                214,
                233,
                121,
                159,
                99,
                111,
                229,
                194,
                60,
                21,
                0,
                111,
                34,
                149,
                9,
                14,
                29,
                240,
                137,
                39,
                130,
            )
        ),
        bytes(
            (
                106,
                45,
                88,
                219,
                185,
                112,
                214,
                213,
                221,
                177,
                213,
                60,
                190,
                188,
                214,
                67,
                241,
                91,
                124,
                140,
                143,
                170,
                247,
                68,
                41,
                200,
                70,
                33,
                196,
                124,
                188,
                105,
            )
        ),
    ),
    (
        "quality/semgrep-dispositions.json",
        229,
        bytes(
            (
                124,
                204,
                33,
                9,
                47,
                7,
                193,
                167,
                104,
                194,
                118,
                32,
                22,
                75,
                189,
                232,
                13,
                143,
                73,
                19,
                44,
                150,
                181,
                5,
                188,
                21,
                222,
                54,
                193,
                156,
                126,
                45,
            )
        ),
        bytes(
            (
                42,
                89,
                97,
                51,
                8,
                247,
                195,
                203,
                81,
                53,
                30,
                114,
                47,
                100,
                228,
                8,
                83,
                4,
                243,
                186,
                49,
                131,
                184,
                227,
                202,
                127,
                189,
                21,
                31,
                118,
                177,
                235,
            )
        ),
    ),
)

_AUD380_N4_HISTORICAL_LIVE_STAND_SOURCE_SHA256 = bytes(
    (
        23,
        28,
        49,
        42,
        231,
        220,
        243,
        226,
        207,
        204,
        24,
        190,
        185,
        103,
        145,
        54,
        164,
        127,
        113,
        47,
        56,
        176,
        24,
        223,
        98,
        97,
        247,
        126,
        248,
        37,
        232,
        19,
    )
)
_AUD380_N4_HISTORICAL_LEDGER_LINE_SHA256 = bytes(
    (
        44,
        159,
        169,
        165,
        166,
        149,
        178,
        220,
        213,
        245,
        84,
        64,
        128,
        13,
        55,
        205,
        84,
        229,
        29,
        53,
        19,
        196,
        221,
        20,
        219,
        43,
        108,
        171,
        132,
        210,
        26,
        178,
    )
)
_AUD380_N4_HISTORICAL_LEDGER_CONTEXT_SHA256 = bytes(
    (
        14,
        222,
        230,
        189,
        171,
        75,
        75,
        102,
        38,
        213,
        235,
        40,
        238,
        36,
        119,
        192,
        72,
        90,
        59,
        219,
        7,
        151,
        181,
        75,
        46,
        12,
        179,
        248,
        91,
        9,
        193,
        249,
    )
)

# The old N4 row7 observation remains in the immutable policy prefix, but the
# current row is now the exact N6 source identity. Keep this historical proof
# separate from the live source identity set.
_AUD380_CURRENT_DELTA_IDENTITY_SOURCE_LINES = (
    tuple(
        row
        for row in _AUD380_CURRENT_DELTA_IDENTITY_SOURCE_LINES
        if not (
            row[0] == "quality/semgrep-dispositions.json"
            and row[4] == 189
            and tuple(row[2]) == _AUD380_N4_PUBLIC_LEDGER_IDENTITY[2]
        )
    )
    + _AUD380_N6_IDENTITY_SOURCE_LINES
)

# Row229 is already pinned as a Semgrep companion line; duplicate the exact
# line/context binding because it is also the first-occurrence N6 identity.
_AUD380_CURRENT_DELTA_SOURCE_LINE_HASHES = (
    *_AUD380_CURRENT_DELTA_SOURCE_LINE_HASHES,
    *_AUD380_N6_SOURCE_LINE_HASHES[1:2],
)


def _aud380_n6_conditional_policy() -> dict[str, Any]:
    active_495 = _aud380_n5_conditional_policy()
    conditional = copy.deepcopy(active_495)
    appended = copy.deepcopy(_AUD380_N6_PENDING_OWNER_RECORDS)
    for row in appended:
        row["approval_status"] = "approved"
    conditional["records"].extend(appended)
    assert _aud380_canonical_records_digest(_AUD380_N6_PENDING_OWNER_RECORDS) == (
        _AUD380_N6_PENDING_ADDITIONS_SHA256
    )
    return conditional


def _assert_aud380_n6_conditional_policy(
    conditional: dict[str, Any], active_495: dict[str, Any]
) -> None:
    assert len(active_495["records"]) == 495
    assert len(conditional.get("records", [])) == 497
    expected_header = {
        key: value for key, value in active_495.items() if key != "records"
    }
    actual_header = {
        key: value for key, value in conditional.items() if key != "records"
    }
    assert actual_header == expected_header, "conditional N6 policy header changed"
    records = conditional["records"]
    assert records[:495] == active_495["records"], "approved 495-row prefix changed"
    pending = copy.deepcopy(_AUD380_N6_PENDING_OWNER_RECORDS)
    assert len(pending) == 2
    assert all(row["approval_status"] == "NOT_APPROVED" for row in pending)
    assert tuple(row["reviewed_on"] for row in pending) == ("2026-11-06", "2026-11-06")
    assert all(row["expires_on"] == "2027-01-10" for row in pending)
    assert {_aud380_identity_key(row) for row in pending} == set(
        _AUD380_N6_EXPECTED_IDENTITIES
    )
    assert Counter(row["category"] for row in pending) == Counter(
        {"public_integrity_digest": 2}
    )
    expected_suffix = copy.deepcopy(pending)
    for row in expected_suffix:
        row["approval_status"] = "approved"
    assert records[495:] == expected_suffix, "conditional N6 suffix changed"
    identities = [_aud380_identity_key(row) for row in records]
    assert len(identities) == len(set(identities)), (
        "conditional N6 identities duplicated"
    )
    assert not (
        {_aud380_identity_key(row) for row in active_495["records"]}
        & set(_AUD380_N6_EXPECTED_IDENTITIES)
    )
    expected_counts = Counter(
        row["category"] for row in active_495["records"]
    ) + Counter({"public_integrity_digest": 2})
    assert Counter(row["category"] for row in records) == expected_counts


def _aud380_assert_live_policy_is_exact_505(
    live_policy: dict[str, Any], historical_490: dict[str, Any]
) -> None:
    """Validate the exact 505-record prefix as of the 2026-11-06 snapshot."""
    live_records = live_policy.get("records")
    assert isinstance(live_records, list), "live disposition records changed"
    assert len(live_records) == 505, "historical 505-row prefix changed"
    expected_header = {
        key: value for key, value in historical_490.items() if key != "records"
    }
    actual_header = {
        key: value for key, value in live_policy.items() if key != "records"
    }
    assert actual_header == expected_header, "live disposition header changed"
    assert live_records[:490] == historical_490["records"], (
        "live approved 490-row prefix changed"
    )
    live_494 = {key: value for key, value in live_policy.items() if key != "records"}
    live_494["records"] = copy.deepcopy(live_records[:494])
    _assert_aud380_n4_conditional_policy(live_494, historical_490)
    live_495 = copy.deepcopy(live_494)
    live_495["records"] = copy.deepcopy(live_records[:495])
    _assert_aud380_n5_conditional_policy(live_495, live_494)
    live_497 = copy.deepcopy(live_495)
    live_497["records"] = copy.deepcopy(live_records[:497])
    _assert_aud380_n6_conditional_policy(live_497, live_495)
    assert live_records[497:505] == _NOV6_ZLIB_EXPECTED_RECORDS, (
        "approved zlib APK suffix changed"
    )
    accepted = _nov13_verify_dispositions(live_policy, today=verifier.date(2026, 11, 6))
    assert len(accepted) == 505, "historical approved disposition count changed"


def _aud380_assert_n4_historical_row7_observation(
    source_bytes_by_path: dict[str, bytes],
    *,
    historical_source_sha256: bytes | None = None,
) -> None:
    old_source = (
        _AUD380_N4_HISTORICAL_LIVE_STAND_SOURCE_SHA256
        if historical_source_sha256 is None
        else historical_source_sha256
    )
    assert len(old_source) == 32
    row7_identity = _AUD380_N4_PUBLIC_LEDGER_IDENTITY
    assert hashlib.sha1(
        old_source.hex().encode("ascii"), usedforsecurity=False
    ).digest() == bytes(row7_identity[2])
    ledger_path = "quality/semgrep-dispositions.json"
    target_path = "scripts/live_stand.py"
    lines = source_bytes_by_path[ledger_path].splitlines(keepends=True)
    current_source = _AUD380_CURRENT_DELTA_SOURCE_SHA256[target_path]
    current_text = current_source.hex().encode("ascii")
    old_text = old_source.hex().encode("ascii")
    raw_line = lines[188]
    assert raw_line.count(current_text) == 1, "current row7 source pin is not exact"
    historical_line = raw_line.replace(current_text, old_text, 1)
    historical_context = (
        b"".join(lines[186:188]) + historical_line + b"".join(lines[189:191])
    )
    assert (
        hashlib.sha256(historical_line).digest()
        == _AUD380_N4_HISTORICAL_LEDGER_LINE_SHA256
    )
    assert (
        hashlib.sha256(historical_context).digest()
        == _AUD380_N4_HISTORICAL_LEDGER_CONTEXT_SHA256
    )
    assert _AUD380_N4_PUBLIC_LEDGER_IDENTITY not in {
        (path, finding_type, digest)
        for path, finding_type, digest, _category, _line in _AUD380_CURRENT_DELTA_IDENTITY_SOURCE_LINES
    }
    n21_old = [
        row
        for row in _AUD380_N21_REPLACED_IDENTITY_SOURCE_LINES
        if row[0] == ledger_path and row[4] == 189
    ]
    assert len(n21_old) == 1
    assert n21_old[0][2] != row7_identity[2]
    historical_n21_hashes = [
        row
        for row in _AUD380_N21_HISTORICAL_SOURCE_LINE_HASHES
        if row[0] == ledger_path and row[1] == 189
    ]
    assert len(historical_n21_hashes) == 2
    assert all(len(row[2]) == 32 and len(row[3]) == 32 for row in historical_n21_hashes)


def test_aud380_n6_exact_records_and_current_source_bindings_are_finite() -> None:
    assert len(_AUD380_N6_PENDING_OWNER_RECORDS) == 2
    assert all(
        row["approval_status"] == "NOT_APPROVED"
        for row in _AUD380_N6_PENDING_OWNER_RECORDS
    )
    assert tuple(row["reviewed_on"] for row in _AUD380_N6_PENDING_OWNER_RECORDS) == (
        "2026-11-06",
        "2026-11-06",
    )
    assert all(
        row["expires_on"] == "2027-01-10" for row in _AUD380_N6_PENDING_OWNER_RECORDS
    )
    assert {
        _aud380_identity_key(row) for row in _AUD380_N6_PENDING_OWNER_RECORDS
    } == set(_AUD380_N6_EXPECTED_IDENTITIES)
    assert (
        _aud380_canonical_records_digest(_AUD380_N6_PENDING_OWNER_RECORDS)
        == _AUD380_N6_PENDING_ADDITIONS_SHA256
    )
    assert len(_AUD380_N6_IDENTITY_SOURCE_LINES) == 2
    assert {
        (row[0], row[1], row[2]) for row in _AUD380_N6_IDENTITY_SOURCE_LINES
    } == set(_AUD380_N6_EXPECTED_IDENTITIES)
    assert tuple((row[0], row[1]) for row in _AUD380_N6_SOURCE_LINE_HASHES) == tuple(
        (row[0], row[4]) for row in _AUD380_N6_IDENTITY_SOURCE_LINES
    )
    source_by_identity = {row[:3]: row for row in _AUD380_N6_IDENTITY_SOURCE_LINES}
    for target_path in (
        "scripts/live_stand.py",
        "tests/test_mfa_deploy_workflow_contract.py",
    ):
        source_sha = _AUD380_CURRENT_DELTA_SOURCE_SHA256[target_path]
        derived = tuple(
            hashlib.sha1(
                source_sha.hex().encode("ascii"), usedforsecurity=False
            ).digest()
        )
        assert any(key[2] == derived for key in source_by_identity)
    source_root = Path(__file__).resolve().parents[1]
    _assert_conditional_owner_source_bindings(source_root)


def test_aud380_n6_conditional_497_projection_is_exact_append() -> None:
    active_495 = _aud380_n5_conditional_policy()
    conditional = _aud380_n6_conditional_policy()
    _assert_aud380_n6_conditional_policy(conditional, active_495)
    accepted = _nov13_verify_dispositions(conditional, today=verifier.date(2026, 11, 7))
    assert len(accepted) == 497
    assert conditional["records"][:495] == active_495["records"]


@pytest.mark.parametrize(
    "mutation",
    [
        "header",
        "prefix",
        "path",
        "finding_type",
        "digest",
        "category",
        "owner",
        "date",
        "expiry",
        "evidence",
        "status",
        "missing",
        "extra",
        "duplicate",
        "order",
    ],
)
def test_aud380_n6_conditional_497_projection_rejects_mutations(mutation: str) -> None:
    active_495 = _aud380_n5_conditional_policy()
    changed = _aud380_n6_conditional_policy()
    records = changed["records"]
    target = records[495]
    if mutation == "header":
        changed["schema_version"] = 2
    elif mutation == "prefix":
        records[0]["owner"] = "unreviewed-owner"
    elif mutation == "path":
        target["identity"]["path"] += ".unreviewed"
    elif mutation == "finding_type":
        target["identity"]["type"] = "unreviewed type"
    elif mutation == "digest":
        target["identity"]["hashed_secret_bytes"][0] ^= 1
    elif mutation == "category":
        target["category"] = "ci_test_contract_sentinel"
    elif mutation == "owner":
        target["owner"] = "unreviewed-owner"
    elif mutation == "date":
        target["reviewed_on"] = "2026-11-05"
    elif mutation == "expiry":
        target["expires_on"] = "2027-01-11"
    elif mutation == "evidence":
        target["evidence"] += " changed"
    elif mutation == "status":
        target["approval_status"] = "NOT_APPROVED"
    elif mutation == "missing":
        records.pop()
    elif mutation == "extra":
        records.append(copy.deepcopy(records[495]))
    elif mutation == "duplicate":
        records[496] = copy.deepcopy(records[495])
    else:
        records[495], records[496] = records[496], records[495]
    with pytest.raises(AssertionError):
        _assert_aud380_n6_conditional_policy(changed, active_495)


def test_aud380_n6_pending_rows_keep_exact_expiry_and_reject_digest_mutations() -> None:
    pending = copy.deepcopy(_AUD380_N6_PENDING_OWNER_RECORDS)
    assert all(row["approval_status"] == "NOT_APPROVED" for row in pending)
    approved = copy.deepcopy(pending)
    for row in approved:
        row["approval_status"] = "approved"
    for row in approved:
        reviewed_on = verifier.date.fromisoformat(row["reviewed_on"])
        expires_on = verifier.date.fromisoformat(row["expires_on"])
        for today in (reviewed_on, expires_on):
            assert (
                len(_nov13_verify_dispositions(_disposition_document(row), today=today))
                == 1
            )
        for today in (
            verifier.date.fromordinal(reviewed_on.toordinal() - 1),
            verifier.date.fromordinal(expires_on.toordinal() + 1),
        ):
            with pytest.raises(verifier.BaselineArtifactError, match="date range"):
                _nov13_verify_dispositions(_disposition_document(row), today=today)
    assert {_aud380_identity_key(row) for row in approved} == set(
        _AUD380_N6_EXPECTED_IDENTITIES
    )
    _assert_conditional_owner_source_bindings(Path(__file__).resolve().parents[1])


_NOV6_ZLIB_EXPECTED_RECORDS = [
    {
        "approval_status": "approved",
        "category": "public_integrity_digest",
        "evidence": "Official signed Alpine 3.24 x86_64 zlib 1.3.2-r1 APK integrity; source "
        "https://dl-cdn.alpinelinux.org/alpine/v3.24/main/x86_64/zlib-1.3.2-r1.apk; "
        "exact source reference frontend.Dockerfile:185; owner approved this "
        "finite identity on 2026-11-06; not credential material.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                193,
                17,
                144,
                74,
                56,
                88,
                63,
                135,
                99,
                90,
                200,
                86,
                241,
                248,
                116,
                247,
                144,
                228,
                8,
                249,
            ],
            "path": "frontend.Dockerfile",
            "type": "Hex High Entropy String",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
    {
        "approval_status": "approved",
        "category": "public_integrity_digest",
        "evidence": "Official signed Alpine 3.24 aarch64 zlib 1.3.2-r1 APK integrity; source "
        "https://dl-cdn.alpinelinux.org/alpine/v3.24/main/aarch64/zlib-1.3.2-r1.apk; "
        "exact source reference frontend.Dockerfile:186; owner approved this "
        "finite identity on 2026-11-06; not credential material.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                114,
                208,
                53,
                130,
                231,
                183,
                59,
                88,
                149,
                209,
                33,
                59,
                79,
                235,
                228,
                244,
                37,
                75,
                162,
                215,
            ],
            "path": "frontend.Dockerfile",
            "type": "Hex High Entropy String",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
    {
        "approval_status": "approved",
        "category": "public_integrity_digest",
        "evidence": "Official signed Alpine 3.23 x86_64 zlib 1.3.2-r1 APK integrity; source "
        "https://dl-cdn.alpinelinux.org/alpine/v3.23/main/x86_64/zlib-1.3.2-r1.apk; "
        "exact source reference services/caddy/Dockerfile:49; owner approved "
        "this finite identity on 2026-11-06; not credential material.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                227,
                185,
                225,
                87,
                12,
                234,
                38,
                70,
                87,
                199,
                47,
                232,
                113,
                127,
                191,
                25,
                200,
                254,
                173,
                173,
            ],
            "path": "services/caddy/Dockerfile",
            "type": "Hex High Entropy String",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
    {
        "approval_status": "approved",
        "category": "public_integrity_digest",
        "evidence": "Official signed Alpine 3.23 aarch64 zlib 1.3.2-r1 APK integrity; source "
        "https://dl-cdn.alpinelinux.org/alpine/v3.23/main/aarch64/zlib-1.3.2-r1.apk; "
        "exact source reference services/caddy/Dockerfile:50; owner approved "
        "this finite identity on 2026-11-06; not credential material.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                22,
                234,
                158,
                97,
                197,
                161,
                232,
                152,
                125,
                171,
                3,
                143,
                19,
                133,
                41,
                99,
                162,
                12,
                228,
                229,
            ],
            "path": "services/caddy/Dockerfile",
            "type": "Hex High Entropy String",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
    {
        "approval_status": "approved",
        "category": "public_integrity_digest",
        "evidence": "Official signed Alpine 3.23 x86_64 zlib 1.3.2-r1 APK integrity; source "
        "https://dl-cdn.alpinelinux.org/alpine/v3.23/main/x86_64/zlib-1.3.2-r1.apk; "
        "exact source reference tests/test_runtime_zlib_security_pin.py:17; "
        "owner approved this finite identity on 2026-11-06; not credential "
        "material.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                227,
                185,
                225,
                87,
                12,
                234,
                38,
                70,
                87,
                199,
                47,
                232,
                113,
                127,
                191,
                25,
                200,
                254,
                173,
                173,
            ],
            "path": "tests/test_runtime_zlib_security_pin.py",
            "type": "Hex High Entropy String",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
    {
        "approval_status": "approved",
        "category": "public_integrity_digest",
        "evidence": "Official signed Alpine 3.23 aarch64 zlib 1.3.2-r1 APK integrity; source "
        "https://dl-cdn.alpinelinux.org/alpine/v3.23/main/aarch64/zlib-1.3.2-r1.apk; "
        "exact source reference tests/test_runtime_zlib_security_pin.py:18; "
        "owner approved this finite identity on 2026-11-06; not credential "
        "material.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                22,
                234,
                158,
                97,
                197,
                161,
                232,
                152,
                125,
                171,
                3,
                143,
                19,
                133,
                41,
                99,
                162,
                12,
                228,
                229,
            ],
            "path": "tests/test_runtime_zlib_security_pin.py",
            "type": "Hex High Entropy String",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
    {
        "approval_status": "approved",
        "category": "public_integrity_digest",
        "evidence": "Official signed Alpine 3.24 x86_64 zlib 1.3.2-r1 APK integrity; source "
        "https://dl-cdn.alpinelinux.org/alpine/v3.24/main/x86_64/zlib-1.3.2-r1.apk; "
        "exact source reference tests/test_runtime_zlib_security_pin.py:21; "
        "owner approved this finite identity on 2026-11-06; not credential "
        "material.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                193,
                17,
                144,
                74,
                56,
                88,
                63,
                135,
                99,
                90,
                200,
                86,
                241,
                248,
                116,
                247,
                144,
                228,
                8,
                249,
            ],
            "path": "tests/test_runtime_zlib_security_pin.py",
            "type": "Hex High Entropy String",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
    {
        "approval_status": "approved",
        "category": "public_integrity_digest",
        "evidence": "Official signed Alpine 3.24 aarch64 zlib 1.3.2-r1 APK integrity; source "
        "https://dl-cdn.alpinelinux.org/alpine/v3.24/main/aarch64/zlib-1.3.2-r1.apk; "
        "exact source reference tests/test_runtime_zlib_security_pin.py:22; "
        "owner approved this finite identity on 2026-11-06; not credential "
        "material.",
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": [
                114,
                208,
                53,
                130,
                231,
                183,
                59,
                88,
                149,
                209,
                33,
                59,
                79,
                235,
                228,
                244,
                37,
                75,
                162,
                215,
            ],
            "path": "tests/test_runtime_zlib_security_pin.py",
            "type": "Hex High Entropy String",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-06",
    },
]


def _nov6_zlib_historical_497_from_live_policy(
    policy: dict[str, Any],
) -> dict[str, Any]:
    policy = _nov9_historical_506_from_live_policy(policy)
    records = policy.get("records")
    assert isinstance(records, list), "live disposition records changed"
    assert len(records) == 506, "live disposition row count changed"
    assert records[497:505] == _NOV6_ZLIB_EXPECTED_RECORDS, (
        "approved zlib APK suffix changed"
    )
    assert records[505] == _AUD428_ROW13_APPROVED_RECORD, (
        "approved row13 record changed"
    )
    historical_505 = {**policy, "records": copy.deepcopy(records[:505])}
    try:
        accepted_505 = _nov13_verify_dispositions(
            historical_505, today=verifier.date(2026, 11, 6)
        )
        accepted_live = _nov13_verify_dispositions(
            policy, today=verifier.date(2026, 11, 7)
        )
    except verifier.BaselineArtifactError as error:
        raise AssertionError("live approved disposition metadata changed") from error
    assert len(accepted_505) == 505, "historical approved disposition count changed"
    assert len(accepted_live) == 506, "live approved disposition count changed"
    return {**policy, "records": copy.deepcopy(records[:497])}


def test_nov6_zlib_policy_exact_append_and_inclusive_expiry() -> None:
    live = _aud380_read_live_policy()
    historical = _nov6_zlib_historical_497_from_live_policy(live)
    prior = _aud380_n6_conditional_policy()
    assert historical == prior, "current497 approvals or dates changed"
    assert live["records"][497:505] == _NOV6_ZLIB_EXPECTED_RECORDS
    assert live["records"][505] == _AUD428_ROW13_APPROVED_RECORD
    document = _disposition_document(*copy.deepcopy(_NOV6_ZLIB_EXPECTED_RECORDS))
    assert (
        len(_nov13_verify_dispositions(document, today=verifier.date(2027, 1, 10))) == 8
    )
    with pytest.raises(verifier.BaselineArtifactError, match="date range"):
        _nov13_verify_dispositions(document, today=verifier.date(2027, 1, 11))


@pytest.mark.parametrize("index", range(8))
@pytest.mark.parametrize(
    "mutation",
    [
        "path",
        "digest",
        "type",
        "category",
        "evidence",
        "owner",
        "reviewed",
        "expiry",
        "status",
    ],
)
def test_nov6_zlib_validator_refuses_approval_drift(index: int, mutation: str) -> None:
    record = copy.deepcopy(_NOV6_ZLIB_EXPECTED_RECORDS[index])
    assert (
        len(
            _nov13_verify_dispositions(
                _disposition_document(record), today=verifier.date(2026, 11, 6)
            )
        )
        == 1
    )
    if mutation == "path":
        record["identity"]["path"] = "other/changed-source.py"
    elif mutation == "digest":
        record["identity"]["hashed_secret_bytes"][0] ^= 1
    elif mutation == "type":
        record["identity"]["type"] = "Secret Keyword"
    elif mutation == "category":
        record["category"] = "documented_crypto_test_vector"
    elif mutation == "evidence":
        record["evidence"] += " altered"
    elif mutation == "owner":
        record["owner"] = "other-owner"
    elif mutation == "reviewed":
        record["reviewed_on"] = "2026-11-05"
    elif mutation == "expiry":
        record["expires_on"] = "2027-01-11"
    else:
        record["approval_status"] = "NOT_APPROVED"
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(record), today=verifier.date(2026, 11, 6)
        )


@pytest.mark.parametrize(
    "mutation", ["missing", "extra", "reordered", "changed", "old-date"]
)
def test_nov6_zlib_live_projection_refuses_scope_drift(mutation: str) -> None:
    policy = _aud380_read_live_policy()
    if mutation == "missing":
        del policy["records"][497]
    elif mutation == "extra":
        policy["records"].append(copy.deepcopy(policy["records"][-1]))
    elif mutation == "reordered":
        policy["records"][497], policy["records"][498] = (
            policy["records"][498],
            policy["records"][497],
        )
    elif mutation == "changed":
        policy["records"][497]["identity"]["hashed_secret_bytes"][0] ^= 1
    else:
        policy["records"][0]["expires_on"] = "2027-01-11"
    with pytest.raises((AssertionError, verifier.BaselineArtifactError)):
        projected = _nov6_zlib_historical_497_from_live_policy(policy)
        prior = _aud380_n6_conditional_policy()
        assert projected == prior, "current497 approvals changed"


def _nov6_zlib_source_identities(root: Path) -> set[tuple[str, str, tuple[int, ...]]]:
    identities = set()
    test_path = "tests/test_runtime_zlib_security_pin.py"
    source = (root / test_path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    hashes = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "ARCHIVE_SHA256"
            for target in node.targets
        )
    )
    assert set(hashes) == {"3.23", "3.24"}
    for branch, dockerfile in (
        ("3.23", "services/caddy/Dockerfile"),
        ("3.24", "frontend.Dockerfile"),
    ):
        assert set(hashes[branch]) == {"x86_64", "aarch64"}
        docker_source = (root / dockerfile).read_text(encoding="utf-8")
        runtime = docker_source.rsplit("FROM ", 1)[1]
        for arch in ("x86_64", "aarch64"):
            checksum = hashes[branch][arch]
            assert re.fullmatch(r"[0-9a-f]{64}", checksum)
            assert runtime.count(f'{arch}) zlib_sha256="{checksum}" ;;') == 1
            for path in (dockerfile, test_path):
                identities.add(
                    (
                        path,
                        "Hex High Entropy String",
                        tuple(
                            hashlib.sha1(
                                checksum.encode(), usedforsecurity=False
                            ).digest()
                        ),
                    )
                )
    return identities


def test_nov6_zlib_integrity_records_bind_exact_source_values() -> None:
    root = Path(__file__).resolve().parents[1]
    expected = {_aud380_identity_key(record) for record in _NOV6_ZLIB_EXPECTED_RECORDS}
    assert _nov6_zlib_source_identities(root) == expected


@pytest.mark.parametrize(
    "mutation", ["docker-digest", "test-digest", "architecture", "branch"]
)
def test_nov6_zlib_source_bindings_reject_drift(tmp_path: Path, mutation: str) -> None:
    root = Path(__file__).resolve().parents[1]
    for path in (
        "frontend.Dockerfile",
        "services/caddy/Dockerfile",
        "tests/test_runtime_zlib_security_pin.py",
    ):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((root / path).read_bytes())
    path = tmp_path / (
        "tests/test_runtime_zlib_security_pin.py"
        if mutation in {"test-digest", "branch"}
        else "frontend.Dockerfile"
    )
    source = path.read_text(encoding="utf-8")
    if mutation in {"docker-digest", "test-digest"}:
        pattern = (
            r'(?<=zlib_sha256=")[0-9a-f]{64}'
            if mutation == "docker-digest"
            else r'(?<=["\'])[0-9a-f]{64}(?=["\'])'
        )
        match = re.search(pattern, source)
        assert match is not None
        source = source[: match.start()] + "0" * 64 + source[match.end() :]
    elif mutation == "architecture":
        source = source.replace("aarch64) zlib_sha256", "armv7) zlib_sha256")
    else:
        source = source.replace('"3.24": {', '"edge": {')
    path.write_text(source, encoding="utf-8")
    with pytest.raises(AssertionError):
        actual = _nov6_zlib_source_identities(tmp_path)
        assert actual == {
            _aud380_identity_key(record) for record in _NOV6_ZLIB_EXPECTED_RECORDS
        }


@pytest.mark.parametrize("relative_path", sorted(_AUD380_CURRENT_DELTA_SOURCE_SHA256))
def test_aud380_each_current_source_pin_rejects_file_mutation(
    tmp_path: Path, relative_path: str
) -> None:
    source_root = Path(__file__).resolve().parents[1]
    _assert_conditional_owner_source_bindings(source_root)
    for bound_path in _AUD380_CURRENT_DELTA_SOURCE_SHA256:
        target = tmp_path / bound_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((source_root / bound_path).read_bytes())

    mutated_path = tmp_path / relative_path
    mutated_path.write_bytes(mutated_path.read_bytes() + b"\n# source drift control\n")
    with pytest.raises(
        AssertionError,
        match=rf"(?m)^conditional disposition source file SHA-256 changed: {re.escape(relative_path)}$",
    ):
        _assert_conditional_owner_source_bindings(tmp_path)


# Owner-approved row13 companion rebind for the exact MapLibre/RLS source postimage.
_AUD428_ROW13_BASE_LEDGER_SHA256 = b"\xf3?+O\x08\xc1\xc5\xe0\x05\xe7gR\xa4\r@\xd9l\xb0\x7f\xe4\xf4\xf2#!$\xa6\xe1\x1b\xaet\xbf\x12"
_AUD428_ROW13_CANDIDATE_LEDGER_SHA256 = (
    b"Gep\x88\xad\x86\xed0\xebR0,\xeck\x91\xddF\xab\xfd\x1fFk\xe35d\xb2Q\x880\nZ)"
)
_AUD428_ROW13_COMPANION_SHA256 = b"\xf3\x19<C\xaa}s?\x9c\xdc=Q\x0b\x0e\x96^\xe0\xd1\x08e\x05\x91\x9e\x8e\xd7=\xbf\xfbT\xf1\x8bA"
_AUD428_ROW13_OLD_COMPANION_SHA256 = b"\x1bl\xcd\xc6\x7f\x10\xfb\x93\x8bT \x84c[\xb0\xb0\xf8\x9a_\xb9M\xe9E\x90\x95\x13\x90\xb0\xc6\x98\xd3\x80"
_AUD428_ROW13_LINE_SHA256 = b"\x87p\x88+\x17!\x12k\x02h\xeex\xd2ke\x19\r\xb1e|\xd35\xb6/\x9f\x06\xd1J\xf0\xe1\x88y"
_AUD428_ROW13_CONTEXT_SHA256 = b"@KnX\xa8\x9d\xe1\x99\xe1\xca=z\x83\xdd\xa2>\x98d-\x80\xfd\xf2\xe0\xa4\xf6\x8e\x92\x14\x11uV\xa3"
_AUD428_ROW13_ACTIVE_505_PREFIX_CANONICAL_SHA256 = b"D\xd3\xcc\x1a\x93\xa9\x8b}\x18\x9e\xe9\xb5\xb1\xdd\xf3+\xf4\xfc\xbb\xba\xdf\n\xdf\xech\xb5B#*\xfe\xd97"
_AUD428_ROW13_ACTIVE_505_PREFIX_BYTES_SHA256 = b"\xfc9\xfc\xce\xd3\xf5\xd9\x80E\x06\xa1[\x03\x92[\x94\xbe\x83&f\xfes\xba\xd2\xc5\x95AN\xf7\xe0\xc6\xe0"
_AUD428_ROW13_ACTIVE_POLICY_SHA256 = (
    b"$\x04\xa3k\x9en*/\xea\xe4h#m\x16\x1c\xc5\tOU\x89\x8e\xaen\xadHbT\x01\x8f4\r\x0f"
)
_AUD428_ROW13_APPROVED_RECORDSET_SHA256 = b"\x16<\x96\xf2\xb1\xc4.c\x83\xb8\x9e=+\x93\x16\x96\x18RY\xb4\xcb\x94\xbf\t\x8fv\x08\x9a:\xd6\x17\xf9"
_AUD428_ROW13_APPROVED_RECORD = json.loads(r"""
{
  "approval_status": "approved",
  "category": "public_integrity_digest",
  "evidence": "Public SHA-256 companion digest for tests/test_quality_workflow_contract.py in Semgrep disposition row 13 at quality/semgrep-dispositions.json:381. Verified by the pinned detect-secrets preview of the exact MapLibre/RLS contract postimage.",
  "expires_on": "2027-01-10",
  "identity": {
    "hashed_secret_bytes": [
      33,
      243,
      232,
      80,
      159,
      244,
      208,
      56,
      110,
      182,
      100,
      188,
      236,
      135,
      227,
      240,
      71,
      220,
      233,
      58
    ],
    "path": "quality/semgrep-dispositions.json",
    "type": "Hex High Entropy String"
  },
  "owner": "egorribun",
  "reviewed_on": "2026-11-07"
}
""")

_AUD380_N6_FINAL_SOURCE_SHA256 = {
    **_AUD380_N6_FINAL_SOURCE_SHA256,
    "quality/semgrep-dispositions.json": _AUD428_ROW13_CANDIDATE_LEDGER_SHA256,
}
_AUD380_CURRENT_DELTA_SOURCE_SHA256 = {
    **_AUD380_CURRENT_DELTA_SOURCE_SHA256,
    "quality/semgrep-dispositions.json": _AUD428_ROW13_CANDIDATE_LEDGER_SHA256,
    "tests/test_seed_demo_data.py": b"3\xa2\xaa\xfb(Wj\x18t\x1eh\x91CB}\xdd\x1a[U\x94\xa3\xa6G\xfa\x96G\xc1\xc3\xe3\xa3e*",
}


def _aud428_assert_row13_source_binding(repository_root: Path) -> None:
    ledger_path = repository_root / "quality/semgrep-dispositions.json"
    companion_path = repository_root / "tests/test_quality_workflow_contract.py"
    policy_path = repository_root / "quality/security-false-positive-dispositions.json"
    ledger_bytes = _aud154_historical_source_bytes(
        "quality/semgrep-dispositions.json", ledger_path.read_bytes()
    )
    companion_bytes = _nov13_go_companion_historical_source_bytes(
        "tests/test_quality_workflow_contract.py", companion_path.read_bytes()
    )
    live_policy_bytes = policy_path.read_bytes()
    _nov9_assert_live_policy_bytes(live_policy_bytes)
    policy_bytes = _nov9_historical_506_policy_bytes(
        _nov9_historical_506_from_live_policy(json.loads(live_policy_bytes))
    )
    companion_sha = hashlib.sha256(companion_bytes).digest()
    assert companion_sha == _AUD428_ROW13_COMPANION_SHA256
    assert (
        hashlib.sha256(ledger_bytes).digest() == _AUD428_ROW13_CANDIDATE_LEDGER_SHA256
    )
    assert hashlib.sha256(policy_bytes).digest() == _AUD428_ROW13_ACTIVE_POLICY_SHA256
    assert len(policy_bytes) == 495838
    assert hashlib.sha256(policy_bytes[:494904]).digest() == (
        _AUD428_ROW13_ACTIVE_505_PREFIX_BYTES_SHA256
    )
    reconstructed = ledger_bytes.replace(
        hashlib.sha256(companion_bytes).hexdigest().encode("ascii"),
        _AUD428_ROW13_OLD_COMPANION_SHA256.hex().encode("ascii"),
        1,
    )
    assert hashlib.sha256(reconstructed).digest() == _AUD428_ROW13_BASE_LEDGER_SHA256
    document = json.loads(ledger_bytes.decode("utf-8"))
    assert len(document["dispositions"]) == 15
    companions = [
        item
        for item in document["dispositions"][12]["companions"]
        if item["path"] == "tests/test_quality_workflow_contract.py"
    ]
    assert len(companions) == 1
    assert companions[0]["sha256"] == hashlib.sha256(companion_bytes).hexdigest()
    assert (
        document["dispositions"][13]
        == json.loads(reconstructed.decode("utf-8"))["dispositions"][13]
    )
    lines = ledger_bytes.splitlines(keepends=True)
    assert hashlib.sha256(lines[380]).digest() == _AUD428_ROW13_LINE_SHA256
    context = b"".join(lines[378:383])
    assert hashlib.sha256(context).digest() == _AUD428_ROW13_CONTEXT_SHA256
    assert hashlib.sha1(
        hashlib.sha256(companion_bytes).hexdigest().encode("ascii"),
        usedforsecurity=False,
    ).digest() == bytes(
        _AUD428_ROW13_APPROVED_RECORD["identity"]["hashed_secret_bytes"]
    )
    assert _aud380_canonical_records_digest([_AUD428_ROW13_APPROVED_RECORD]) == (
        _AUD428_ROW13_APPROVED_RECORDSET_SHA256
    )


def _aud428_assert_live_policy_is_exact_506(
    live_policy: dict[str, Any], historical_490: dict[str, Any]
) -> None:
    records = live_policy.get("records")
    assert isinstance(records, list), "live disposition records changed"
    assert len(records) == 506, "live disposition row count changed"
    expected_header = {
        key: value for key, value in historical_490.items() if key != "records"
    }
    actual_header = {
        key: value for key, value in live_policy.items() if key != "records"
    }
    assert actual_header == expected_header, "live disposition header changed"
    assert records[:490] == historical_490["records"], (
        "live approved 490-row prefix changed"
    )
    assert _aud380_canonical_records_digest(records[:505]) == (
        _AUD428_ROW13_ACTIVE_505_PREFIX_CANONICAL_SHA256
    ), "prior 505 approved records changed"
    prefix_505 = {**live_policy, "records": copy.deepcopy(records[:505])}
    _aud380_assert_live_policy_is_exact_505(prefix_505, historical_490)
    assert records[497:505] == _NOV6_ZLIB_EXPECTED_RECORDS, (
        "approved zlib APK suffix changed"
    )
    assert records[505] == _AUD428_ROW13_APPROVED_RECORD, (
        "approved row13 record changed"
    )
    assert records[505]["category"] == "public_integrity_digest"
    assert records[505]["reviewed_on"] == "2026-11-07"
    assert records[505]["expires_on"] == "2027-01-10"
    assert _aud380_identity_key(records[505]) not in {
        _aud380_identity_key(item) for item in records[:505]
    }
    expected_counts = Counter(row["category"] for row in records[:505]) + Counter(
        {"public_integrity_digest": 1}
    )
    assert Counter(row["category"] for row in records) == expected_counts
    accepted = _nov13_verify_dispositions(live_policy, today=verifier.date(2026, 11, 7))
    assert len(accepted) == 506, "live approved disposition count changed"


def test_aud428_row13_approved_506_binding_preserves_505_prefix_and_zlib_suffix() -> (
    None
):
    repository_root = Path(__file__).resolve().parents[1]
    _aud428_assert_row13_source_binding(repository_root)
    live = _aud380_read_live_policy()
    historical_490 = _aud380_historical_490_from_live_policy(live)
    active = _nov9_historical_506_from_live_policy(live)
    _aud428_assert_live_policy_is_exact_506(active, historical_490)
    assert len(active["records"]) == 506
    assert active["records"][497:505] == _NOV6_ZLIB_EXPECTED_RECORDS
    assert active["records"][505] == _AUD428_ROW13_APPROVED_RECORD
    baseline = json.loads(
        (repository_root / ".secrets.baseline").read_text(encoding="utf-8")
    )
    assert sum(len(records) for records in baseline["results"].values()) == 242


@pytest.mark.parametrize(
    "mutation",
    (
        "digest",
        "status",
        "category",
        "evidence",
        "owner",
        "reviewed",
        "expiry",
        "prefix",
        "missing",
        "extra",
        "reordered_zlib",
    ),
)
def test_aud428_row13_approved_506_rejects_scope_drift(mutation: str) -> None:
    live = _aud380_read_live_policy()
    historical_490 = _aud380_historical_490_from_live_policy(live)
    active = _nov9_historical_506_from_live_policy(live)
    changed = copy.deepcopy(active)
    if mutation == "digest":
        changed["records"][505]["identity"]["hashed_secret_bytes"][0] ^= 1
    elif mutation == "status":
        changed["records"][505]["approval_status"] = "NOT_APPROVED"
    elif mutation == "category":
        changed["records"][505]["category"] = "source_contract_identifier"
    elif mutation == "evidence":
        changed["records"][505]["evidence"] += " changed"
    elif mutation == "owner":
        changed["records"][505]["owner"] = "unreviewed-owner"
    elif mutation == "reviewed":
        changed["records"][505]["reviewed_on"] = "2026-11-06"
    elif mutation == "expiry":
        changed["records"][505]["expires_on"] = "2027-01-11"
    elif mutation == "prefix":
        changed["records"][0]["owner"] = "changed"
    elif mutation == "missing":
        changed["records"].pop()
    elif mutation == "extra":
        changed["records"].append(copy.deepcopy(changed["records"][505]))
    else:
        changed["records"][497], changed["records"][498] = (
            changed["records"][498],
            changed["records"][497],
        )
    with pytest.raises(AssertionError):
        _aud428_assert_live_policy_is_exact_506(changed, historical_490)


_AUD380_APPROVED_OWNER_ADDITIONS_SHA256 = bytes.fromhex(
    "e9 9e 32 8c a7 da f8 24 d3 1a 37 15 38 1e 59 d1 e9 74 29 ab b5 8c d0 df b5 bc fe 15 fb f0 b1 c1"
)
_AUD380_CONDITIONAL_RECORDSET_SHA256 = bytes.fromhex(
    "33 bb 64 66 8e a1 56 10 60 1d bf 36 2c 80 6f c3 ae 3f e4 4a 49 50 46 b8 fb 3b 2b 7b ef 7c a9 4a"
)
_AUD428_ROW13_ACTIVE_505_PREFIX_CANONICAL_SHA256 = bytes.fromhex(
    "3a d6 09 2c b9 37 71 50 70 2f 25 ee 7d 97 24 b8 78 c6 11 1e 39 84 60 8c d2 ad 1e 1a 39 8b 3a e7"
)
_AUD380_N5_PENDING_ADDITIONS_SHA256 = bytes.fromhex(
    "2d d3 a0 7d 74 8c 9e 4a 2c 44 e2 1c 6b 1d 0b 4d f1 88 99 9e f6 d4 61 2a fa 68 b4 1d 72 b4 7c e6"
)
_AUD380_N5_LINE_SHA256 = bytes.fromhex(
    "03 17 76 00 83 28 8f 04 8a e9 2e 1e 12 27 0e 23 73 dd f3 c7 c1 4d af 7c 17 4a 44 92 2e f7 4a 77"
)
_AUD380_N5_CONTEXT_SHA256 = bytes.fromhex(
    "00 12 bc 91 6f cf 29 16 7a e1 ba 75 86 7a 33 8e 16 d6 a5 79 d6 00 b8 91 4a cd ba a1 cf 00 dd 02"
)
_AUD380_N3_PENDING_493_RECORDSET_SHA256 = bytes.fromhex(
    "6e 34 c9 88 49 41 15 67 ca 3d ea 38 bb 32 f0 00 0e 92 5b 64 58 a4 c5 ff c4 63 e9 32 0d 92 3f d4"
)
_AUD380_N3_CONDITIONAL_493_RECORDSET_SHA256 = bytes.fromhex(
    "8a 88 82 eb aa 7d ce 4c 71 47 33 79 2b 5a 93 89 bb 60 2d 45 70 b6 70 55 3f 04 93 45 38 9a 07 c1"
)
_AUD428_ROW13_BASE_LEDGER_SHA256 = bytes.fromhex(
    "00 b8 46 5a 51 45 63 26 f0 e1 ae 1b f7 bf 38 de 84 2b e7 1e 51 88 23 53 cc bc ad 7d e6 49 06 7e"
)
_AUD380_APPROVED_OWNER_ADDITIONS_SHA256 = bytes.fromhex(
    "e9 9e 32 8c a7 da f8 24 d3 1a 37 15 38 1e 59 d1 e9 74 29 ab b5 8c d0 df b5 bc fe 15 fb f0 b1 c1"
)
_AUD428_ROW13_COMPANION_SHA256 = bytes.fromhex(
    "3f 00 15 23 ef b0 55 ea 19 47 63 9c 39 11 72 94 b7 8d bc 53 ef 2d c3 80 ae cc 7a 85 f2 e2 2f 0f"
)
_AUD428_ROW13_BASE_LEDGER_SHA256 = bytes.fromhex(
    "00 b8 46 5a 51 45 63 26 f0 e1 ae 1b f7 bf 38 de 84 2b e7 1e 51 88 23 53 cc bc ad 7d e6 49 06 7e"
)
_AUD428_ROW13_LINE_SHA256 = bytes.fromhex(
    "58 23 6e db a0 86 d5 00 04 e3 cb d1 e4 db 99 0e ca d0 6e 1e 8b ff e4 01 1d 86 0f ac 1d f4 fe 63"
)
_AUD428_ROW13_CONTEXT_SHA256 = bytes.fromhex(
    "f4 d5 7e 79 ef 62 4b 34 42 45 fc 40 de 62 ff f9 85 45 eb a3 73 2e 0e d7 34 d0 2a 96 75 12 1b 9a"
)
_AUD428_ROW13_APPROVED_RECORDSET_SHA256 = bytes.fromhex(
    "86 4d ee 31 5a 17 0e 4d 0a 60 c5 6b 6e 56 37 2a 5e 11 c2 9c b6 4e 6b cb 79 58 95 65 ab 1c 49 f4"
)
_AUD380_PENDING_NEW_ADDITIONS_SHA256 = bytes.fromhex(
    "23 9a 58 4c 08 1f 3f 20 5d 9f 11 4c f4 f0 d6 a1 1e 06 b7 ff 51 8c 13 25 a4 9f b1 bb 75 20 1a d9"
)
_AUD380_APPROVED_OWNER_ADDITIONS_SHA256 = bytes.fromhex(
    "e9 9e 32 8c a7 da f8 24 d3 1a 37 15 38 1e 59 d1 e9 74 29 ab b5 8c d0 df b5 bc fe 15 fb f0 b1 c1"
)
_AUD380_APPROVED_NEW_ADDITIONS_SHA256 = bytes.fromhex(
    "3d 26 78 00 a3 1d 82 5a fe 25 cc 5f cd 0f b7 be db 72 09 4d 50 ba f9 46 ff 9b 30 cd 89 06 47 80"
)
_AUD380_CONDITIONAL_RECORDSET_SHA256 = bytes.fromhex(
    "ae da 32 32 cd 24 04 5d 78 41 d1 13 ec d1 8c ea 02 f5 ba 30 c5 e9 70 da 33 df cf 72 02 45 28 d3"
)
_AUD428_ROW13_ACTIVE_505_PREFIX_CANONICAL_SHA256 = bytes.fromhex(
    "07 d6 17 24 28 ac 5b 66 b1 a5 e6 1f e4 48 fd e6 24 b5 f3 e5 18 76 01 32 0a 11 07 5f 53 4b d3 1e"
)
_AUD380_N3_PENDING_493_RECORDSET_SHA256 = bytes.fromhex(
    "51 4d 6e 29 c8 e6 bd 2d 54 58 d7 72 7d 83 cd a8 0c 5b 92 2f 37 c0 33 3c 66 3c 31 56 d9 a5 99 ce"
)
_AUD380_N3_CONDITIONAL_493_RECORDSET_SHA256 = bytes.fromhex(
    "96 4b eb 57 ae 3e f2 03 09 48 de 07 69 17 84 b2 16 2c 75 60 63 f6 1d 0d 6a ac 13 73 1d 98 61 62"
)
_AUD380_N6_PENDING_ADDITIONS_SHA256 = bytes.fromhex(
    "f6 39 ce 05 59 e9 bb 5c cb d5 82 06 63 5d 56 f2 ce f8 6d 6a 07 89 ac 33 f1 fa 63 21 08 94 9c 71"
)
_AUD428_ROW13_BASE_LEDGER_SHA256 = bytes.fromhex(
    "1c 38 dd ee 88 28 1b 18 93 0d 5b e5 73 9c 91 e0 a7 a8 19 70 4a ae 66 73 02 f7 a4 6f 27 fe 02 e9"
)


# Exact policy and ledger digests after the 2026-11-08 companion rebinds.
_AUD428_ROW13_ACTIVE_POLICY_SHA256 = bytes.fromhex(
    "ec 27 bc 3a fa 53 62 6f 5c 99 8f 66 eb d3 d8 b8 f0 b1 0f 6a 2f d1 9a c8 fe 42 b1 84 c6 0c 7f 6f"
)
_AUD428_ROW13_ACTIVE_505_PREFIX_BYTES_SHA256 = bytes.fromhex(
    "9f ff 4d cb 70 93 3e 4f 08 df 4e 51 86 6b 8a 77 53 14 f5 95 67 0d a2 6f ba 25 91 1d 4f 91 56 4a"
)
_AUD428_ROW13_CANDIDATE_LEDGER_SHA256 = bytes.fromhex(
    "7f 53 e4 94 75 7f 3b a0 52 83 f1 7d 02 89 19 b3 ff 7e 94 1d 3a e1 c0 a2 97 70 9e f2 b3 0a 32 4c"
)
# End of 2026-11-08 policy digests.


# Exact source rebinds after the 2026-11-08 CI fixes; each value is a file digest.
_AUD380_NOV8_SOURCE_REBINDS = {
    "frontend/package-lock.json": bytes.fromhex(
        "0d b6 a9 37 67 d7 07 9e 9c d3 14 e8 0a db 05 2b 88 39 d0 92 0a b5 05 cf 03 af ac 00 7e 49 7e 3b"
    ),
    "frontend/package.json": bytes.fromhex(
        "c3 70 dc 11 74 91 82 b5 77 9b 62 89 44 7f 84 f3 12 3f f5 f7 51 e9 c3 7e 76 ed 1a b7 fd cf e9 8b"
    ),
    "frontend/scripts/server-csp.mjs": bytes.fromhex(
        "c2 15 62 21 06 8a a4 0b b1 4b be a7 c8 0b 4c 8e e7 c0 e3 b4 f2 65 0a 34 95 42 63 c4 93 1e 81 c4"
    ),
    "frontend/scripts/visual-smoke-contract.test.mjs": bytes.fromhex(
        "74 68 11 ca 97 89 b0 e8 1c 6d 1e 95 d3 09 81 9c ce a5 9e 32 ab 48 28 d8 74 07 e0 af 0b bf 24 a3"
    ),
    "quality/semgrep-dispositions.json": bytes.fromhex(
        "7f 53 e4 94 75 7f 3b a0 52 83 f1 7d 02 89 19 b3 ff 7e 94 1d 3a e1 c0 a2 97 70 9e f2 b3 0a 32 4c"
    ),
    "scripts/kind/aud373_internal_mtls_proof.sh": bytes.fromhex(
        "df f2 11 ea a4 bb 49 1b 37 0d cd 1f b7 d4 90 b5 c1 a8 79 0f 61 2e cb 30 53 7d de 7d 99 41 26 55"
    ),
    "scripts/live_stand.py": bytes.fromhex(
        "43 86 6a ac db 31 8a c3 d4 e2 96 20 7a 30 eb 23 2a c4 58 b9 24 a0 03 84 49 b5 c6 f5 43 54 42 75"
    ),
    "tests/test_internal_mtls_kind_contract.py": bytes.fromhex(
        "70 58 2b 5f bf f6 fc 4a 91 af e0 ca 08 ea d2 e1 e6 88 80 6d b2 8d 24 ca 7f 8c b8 ef 8f ac 60 4b"
    ),
}
_AUD380_CURRENT_DELTA_SOURCE_SHA256 = {
    **_AUD380_CURRENT_DELTA_SOURCE_SHA256,
    **_AUD380_NOV8_SOURCE_REBINDS,
}
_AUD380_N6_FINAL_SOURCE_SHA256 = {
    **_AUD380_N6_FINAL_SOURCE_SHA256,
    **{
        path: digest
        for path, digest in _AUD380_NOV8_SOURCE_REBINDS.items()
        if path in _AUD380_N6_FINAL_SOURCE_SHA256
    },
}
# End of 2026-11-08 source rebinds.
_AUD428_ROW13_ACTIVE_505_PREFIX_CANONICAL_SHA256 = bytes.fromhex(
    "8d 18 db a9 04 86 de ba 57 a5 cb ad 2d af 79 59 2c 6e c9 a0 33 86 71 f8 59 78 e8 2a 20 c9 0d b6"
)
_AUD380_N6_PENDING_ADDITIONS_SHA256 = bytes.fromhex(
    "65 92 d3 b5 be 44 c5 b7 55 ca 79 33 41 94 41 d8 4d 7d 36 21 fd 17 a6 69 c7 6a 66 af c0 3e 89 32"
)
_AUD428_ROW13_BASE_LEDGER_SHA256 = bytes.fromhex(
    "71 95 bf c2 0c 26 77 00 73 e3 1a 66 17 4e d1 15 84 aa ae 1c f9 93 44 45 0d 43 de 85 67 0b af 4d"
)


# Exact active bindings for the two 2026-11-09 reconnect diagnostic companions.
# Historical snapshot constants and approval metadata remain unchanged.
_AUD428_ROW13_ACTIVE_POLICY_SHA256 = bytes.fromhex(
    "ec 5a 55 82 69 b2 f7 f8 bd 20 8e fb 19 88 59 e4 64 c3 ae b2 9e c3 55 0b d3 12 bb 91 fd c8 f5 19"
)
_AUD428_ROW13_ACTIVE_505_PREFIX_BYTES_SHA256 = bytes.fromhex(
    "af 23 fb d9 22 ec e8 94 b8 e1 9d e5 a6 25 6b b8 d1 a9 09 ee 2b 24 e5 d3 07 4f 1a fd 4f f3 aa 82"
)
_AUD428_ROW13_CANDIDATE_LEDGER_SHA256 = bytes.fromhex(
    "75 b9 0f 54 32 91 0c b7 6a 6e 72 08 9d 91 2f 9c d3 cb 1c ca ba 2c 89 28 74 75 79 27 e9 80 a0 24"
)
_AUD380_APPROVED_OWNER_ADDITIONS_SHA256 = bytes.fromhex(
    "02 fa bf 87 43 fc fb 4a be bc d6 dc 0f d6 5f 51 39 ce 8e e6 16 3f 24 00 95 a0 02 be 67 c2 60 9b"
)
_AUD380_CONDITIONAL_RECORDSET_SHA256 = bytes.fromhex(
    "41 1f ae 6f 57 ce ad 41 9d 1f 31 c8 d4 55 95 74 96 d2 96 02 91 29 83 ec 1b 57 a9 e4 17 a4 16 83"
)
_AUD380_N3_PENDING_493_RECORDSET_SHA256 = bytes.fromhex(
    "db b2 65 3f 2b 50 97 a7 0c d2 e7 02 a0 f2 c7 9a 42 0d 53 3f ba 03 f5 6e e0 09 a4 70 39 93 f6 a9"
)
_AUD380_N3_CONDITIONAL_493_RECORDSET_SHA256 = bytes.fromhex(
    "5e 7a 7f 4d 0f a3 11 12 6a 52 33 49 79 c8 8d 1d e5 48 4c df e5 b9 fd fc 41 25 e3 6f 11 17 09 6e"
)
_AUD380_N6_PENDING_ADDITIONS_SHA256 = bytes.fromhex(
    "ce 7a 76 25 2d 3e 77 95 08 c8 c9 e2 43 43 b3 b9 6c a4 7d ef e2 df 43 fa 8d d9 ae 01 fc ee 7c 1a"
)
_AUD428_ROW13_ACTIVE_505_PREFIX_CANONICAL_SHA256 = bytes.fromhex(
    "87 05 18 e6 23 53 e7 8e 2f f9 e0 b0 f3 6d 7b df fe 9e c4 6b 89 e6 d4 f7 06 22 54 f2 63 ae 58 52"
)
_AUD428_ROW13_BASE_LEDGER_SHA256 = bytes.fromhex(
    "59 ed 07 6d 22 ab d0 df 77 2e 94 87 35 36 3b 51 f2 2e 95 35 fb 46 05 e4 00 e4 94 a8 eb dd 65 17"
)
_AUD429_DIAGNOSTIC_SOURCE_REBINDS = {
    "frontend/package.json": bytes.fromhex(
        "c6 37 a6 46 14 0b 98 25 17 00 67 f0 58 28 c3 77 84 c0 57 79 62 3d a7 f6 58 4d d5 ad 1d ef dd 56"
    ),
    "scripts/live_stand.py": bytes.fromhex(
        "c2 d8 95 9a 48 8c b7 7e 00 1a d3 b7 5a fb 7b f9 90 02 a9 1a 78 9c 67 a4 fa 47 70 ed 02 b7 7c 2c"
    ),
    "quality/semgrep-dispositions.json": bytes.fromhex(
        "75 b9 0f 54 32 91 0c b7 6a 6e 72 08 9d 91 2f 9c d3 cb 1c ca ba 2c 89 28 74 75 79 27 e9 80 a0 24"
    ),
}
_AUD380_CURRENT_DELTA_SOURCE_SHA256 = {
    **_AUD380_CURRENT_DELTA_SOURCE_SHA256,
    **_AUD429_DIAGNOSTIC_SOURCE_REBINDS,
}
_AUD380_N6_FINAL_SOURCE_SHA256 = {
    **_AUD380_N6_FINAL_SOURCE_SHA256,
    **{
        path: digest
        for path, digest in _AUD429_DIAGNOSTIC_SOURCE_REBINDS.items()
        if path in _AUD380_N6_FINAL_SOURCE_SHA256
    },
}
_AUD429_LIVE_STAND_IDENTITY_DIGEST = bytes.fromhex(
    "52 78 9d 30 50 fa 68 70 db bf 71 29 dc c0 67 3a b9 15 ce 6c"
)
_AUD380_N6_PENDING_OWNER_RECORDS = copy.deepcopy(_AUD380_N6_PENDING_OWNER_RECORDS)
_AUD380_N6_PENDING_OWNER_RECORDS[0]["identity"]["hashed_secret_bytes"] = list(
    _AUD429_LIVE_STAND_IDENTITY_DIGEST
)
_AUD380_N6_EXPECTED_IDENTITIES = frozenset(
    _aud380_identity_key(record) for record in _AUD380_N6_PENDING_OWNER_RECORDS
)
_AUD380_N6_IDENTITY_SOURCE_LINES = (
    (
        *_AUD380_N6_IDENTITY_SOURCE_LINES[0][:2],
        tuple(_AUD429_LIVE_STAND_IDENTITY_DIGEST),
        *_AUD380_N6_IDENTITY_SOURCE_LINES[0][3:],
    ),
    *_AUD380_N6_IDENTITY_SOURCE_LINES[1:],
)
_AUD380_CURRENT_DELTA_IDENTITY_SOURCE_LINES = (
    *_AUD380_CURRENT_DELTA_IDENTITY_SOURCE_LINES[:19],
    (
        *_AUD380_CURRENT_DELTA_IDENTITY_SOURCE_LINES[19][:2],
        tuple(_AUD429_LIVE_STAND_IDENTITY_DIGEST),
        *_AUD380_CURRENT_DELTA_IDENTITY_SOURCE_LINES[19][3:],
    ),
    *_AUD380_CURRENT_DELTA_IDENTITY_SOURCE_LINES[20:],
)
_AUD429_DIAGNOSTIC_LINE_REBINDS = {
    189: (
        bytes.fromhex(
            "92 c1 d6 bb f5 64 3d 25 6d 48 48 a0 8b 95 97 17 a5 9b 1c 85 8f 73 53 8d 00 3f d0 99 c6 13 25 37"
        ),
        bytes.fromhex(
            "39 3f 5b 4f ac fa eb 05 6c ac f5 1b 38 d0 32 88 1b 68 b5 df 5e f9 d0 9f e6 ea 87 00 09 d1 0c 2f"
        ),
    ),
    481: (
        bytes.fromhex(
            "25 f6 d1 ff 61 b9 18 0f 34 88 35 d4 20 ce 33 d8 33 00 25 e7 fc 29 44 cb 76 4a e4 18 a0 a2 3e dc"
        ),
        bytes.fromhex(
            "6b 69 52 e3 33 87 1b f2 7d 08 1f 50 78 ff 0b 4d 7f 7c 2a cf 87 cf 31 65 04 bb f1 8b 92 b4 23 43"
        ),
    ),
}
_AUD380_CURRENT_DELTA_SOURCE_LINE_HASHES = tuple(
    (path, line, *_AUD429_DIAGNOSTIC_LINE_REBINDS[line])
    if path == "quality/semgrep-dispositions.json"
    and line in _AUD429_DIAGNOSTIC_LINE_REBINDS
    else (path, line, line_hash, context_hash)
    for path, line, line_hash, context_hash in _AUD380_CURRENT_DELTA_SOURCE_LINE_HASHES
)
_AUD380_N6_SOURCE_LINE_HASHES = (
    (
        *_AUD380_N6_SOURCE_LINE_HASHES[0][:2],
        *_AUD429_DIAGNOSTIC_LINE_REBINDS[189],
    ),
    *_AUD380_N6_SOURCE_LINE_HASHES[1:],
)


# Exact existing row13 companion binding for the AUD360 receipt cohort.
# Preserve historical snapshots and every approval field; rebind record 505 only.
_AUD428_ROW13_COMPANION_SHA256 = bytes.fromhex(
    "26 05 f1 2b 47 23 89 29 e8 84 e4 9e 15 cf 30 b9 e1 45 2f 68 70 fe 37 e4 68 bb 5f 68 a1 f9 1b 51"
)
_AUD428_ROW13_CANDIDATE_LEDGER_SHA256 = bytes.fromhex(
    "ad 44 45 07 fd 99 4a fc 92 8e 2a 14 2c f4 3a 7c dd 26 4e f0 a4 d3 19 22 83 7d 25 00 f2 fb bc e6"
)
_AUD428_ROW13_ACTIVE_POLICY_SHA256 = bytes.fromhex(
    "6b b9 dd 86 78 df 7a 67 dd 77 81 22 ee 1f 2e d1 2f 96 26 1c 33 c0 98 eb c7 eb e8 24 66 02 66 4d"
)
_AUD428_ROW13_LINE_SHA256 = bytes.fromhex(
    "0a 32 48 1a 66 52 ff a1 45 e3 0d 51 1a 22 45 a1 27 7a b4 5b 29 9d e2 c0 84 7d 1f 0b 44 f0 a4 c7"
)
_AUD428_ROW13_CONTEXT_SHA256 = bytes.fromhex(
    "b2 f5 26 e4 31 c6 be bd a1 23 e2 eb 18 88 df fd 79 8b 60 ab 3c 47 5d 06 af 9b 5d af 2b 87 fc 0e"
)
_AUD428_ROW13_APPROVED_RECORDSET_SHA256 = bytes.fromhex(
    "a9 d3 a6 6f 6b 32 20 8e 00 a3 d5 d4 cc 72 61 bb 24 4b 10 16 50 55 82 59 4f 07 5e b3 71 2f e3 82"
)
_AUD428_ROW13_APPROVED_RECORD = copy.deepcopy(_AUD428_ROW13_APPROVED_RECORD)
_AUD428_ROW13_APPROVED_RECORD["identity"]["hashed_secret_bytes"] = list(
    bytes.fromhex("d8 84 4c a3 df dc 9b 17 cd 83 45 ca 78 5c 8b d8 e9 c9 f0 20")
)
_AUD380_CURRENT_DELTA_SOURCE_SHA256 = {
    **_AUD380_CURRENT_DELTA_SOURCE_SHA256,
    "quality/semgrep-dispositions.json": _AUD428_ROW13_CANDIDATE_LEDGER_SHA256,
}
_AUD380_N6_FINAL_SOURCE_SHA256 = {
    **_AUD380_N6_FINAL_SOURCE_SHA256,
    "quality/semgrep-dispositions.json": _AUD428_ROW13_CANDIDATE_LEDGER_SHA256,
}


# Exact existing row13 companion binding for the AUD360 CLI PostgreSQL cohort.
# Preserve historical snapshots and every approval field; rebind record 505 only.
_AUD428_ROW13_COMPANION_SHA256 = bytes.fromhex(
    "83 37 21 ae b3 4f bb cb 31 37 e8 ad fb 9b 48 1b 28 6b 1d 53 e6 58 d0 97 9e 39 b1 49 12 88 89 e4"
)
_AUD428_ROW13_CANDIDATE_LEDGER_SHA256 = bytes.fromhex(
    "8c 67 c5 8c d8 21 32 ff 54 4f 17 48 22 ad 69 33 69 50 6a af 26 1c c2 5b 8d 96 ec 3b c6 a3 8f 7f"
)
_AUD428_ROW13_ACTIVE_POLICY_SHA256 = bytes.fromhex(
    "a8 c5 9a 0f d7 90 d5 ea 27 83 0d b4 53 bf 01 c2 61 34 1c 22 aa 39 51 36 24 f1 40 57 0a db bd c7"
)
_AUD428_ROW13_LINE_SHA256 = bytes.fromhex(
    "97 af 90 31 b2 d6 ff f8 a3 c4 1d 2c ee 0e 89 9b 72 df ce 16 52 f3 cd 52 60 2c a6 fc 1a b9 22 14"
)
_AUD428_ROW13_CONTEXT_SHA256 = bytes.fromhex(
    "21 50 34 eb a7 00 e3 25 7e 75 b7 f5 55 41 4b c6 6d 8b 85 6f 2e 3d a8 1f 99 2a cb 11 be fb 53 e6"
)
_AUD428_ROW13_APPROVED_RECORDSET_SHA256 = bytes.fromhex(
    "fa b7 4f 4c d6 b3 df 33 d1 0c 9b 61 6e 31 9e c6 6f 40 a0 45 2d b0 2c cf bd 34 b8 c5 48 a9 ea b9"
)
_AUD428_ROW13_APPROVED_RECORD = copy.deepcopy(_AUD428_ROW13_APPROVED_RECORD)
_AUD428_ROW13_APPROVED_RECORD["identity"]["hashed_secret_bytes"] = list(
    bytes.fromhex("db 1d 31 58 9f e7 42 1f 51 ab 8b 70 de bc f7 a9 32 7f a5 95")
)
_AUD380_CURRENT_DELTA_SOURCE_SHA256 = {
    **_AUD380_CURRENT_DELTA_SOURCE_SHA256,
    "quality/semgrep-dispositions.json": _AUD428_ROW13_CANDIDATE_LEDGER_SHA256,
}
_AUD380_N6_FINAL_SOURCE_SHA256 = {
    **_AUD380_N6_FINAL_SOURCE_SHA256,
    "quality/semgrep-dispositions.json": _AUD428_ROW13_CANDIDATE_LEDGER_SHA256,
}


# Exact existing row13 companion binding for the AUD360 weekly PostgreSQL cohort.
# Preserve historical snapshots and every approval field; rebind record 505 only.
_AUD428_ROW13_COMPANION_SHA256 = bytes.fromhex(
    "6c 23 12 9a d0 fd 05 ea b6 aa af fb 84 01 6d 5b c1 bb a5 7c fb 0e 04 1a 1b c6 34 f6 e2 67 82 cc"
)
_AUD428_ROW13_CANDIDATE_LEDGER_SHA256 = bytes.fromhex(
    "89 69 38 1d b4 88 2c 31 4e a1 af ca bb 24 7d 74 67 c7 87 63 99 5e 8b 25 f0 f9 cc 5c 14 81 f2 59"
)
_AUD428_ROW13_ACTIVE_POLICY_SHA256 = bytes.fromhex(
    "7f 74 5f 31 be 8c 8e db 5e 3a c4 03 04 3c 75 ad ec 9b 41 2f 62 38 9c 1a aa 66 cd ec 4f e7 72 3a"
)
_AUD428_ROW13_LINE_SHA256 = bytes.fromhex(
    "ae 63 c6 40 4a f6 66 2a ca c4 c3 fd c9 47 63 ac 84 bb 80 d5 ae b8 3d 2e fb 2f 86 74 31 68 6c 93"
)
_AUD428_ROW13_CONTEXT_SHA256 = bytes.fromhex(
    "fc 8f b2 bf 90 af 69 19 56 87 a5 8b cc b7 6c 44 af 91 3f 83 b9 59 60 02 d0 a1 77 38 c7 84 2e a5"
)
_AUD428_ROW13_APPROVED_RECORDSET_SHA256 = bytes.fromhex(
    "a1 75 ca c5 01 0e f7 21 6a b5 35 8e 8c 6f 5f f6 1a 85 9c df 84 7c 2c 2e 1d 66 3a ad 23 bf 17 67"
)
_AUD428_ROW13_APPROVED_RECORD = copy.deepcopy(_AUD428_ROW13_APPROVED_RECORD)
_AUD428_ROW13_APPROVED_RECORD["identity"]["hashed_secret_bytes"] = list(
    bytes.fromhex("e1 2d 25 3a e0 e6 34 e7 13 14 f3 32 61 d3 b0 98 b7 b0 0a f6")
)
_AUD380_CURRENT_DELTA_SOURCE_SHA256 = {
    **_AUD380_CURRENT_DELTA_SOURCE_SHA256,
    "quality/semgrep-dispositions.json": _AUD428_ROW13_CANDIDATE_LEDGER_SHA256,
}
_AUD380_N6_FINAL_SOURCE_SHA256 = {
    **_AUD380_N6_FINAL_SOURCE_SHA256,
    "quality/semgrep-dispositions.json": _AUD428_ROW13_CANDIDATE_LEDGER_SHA256,
}


# Exact existing row13 companion binding for the AUD360 schedule PostgreSQL cohort.
# Preserve historical snapshots and every approval field; rebind record 505 only.
_AUD428_ROW13_COMPANION_SHA256 = bytes.fromhex(
    "d7 8f 3a 81 1b 1b 05 de d8 29 b8 a9 a8 89 29 b4 94 b4 bf e6 01 c0 da 93 80 4a 5e 4c fe 84 8f 6c"
)
_AUD428_ROW13_CANDIDATE_LEDGER_SHA256 = bytes.fromhex(
    "9d cb 6a 8e 82 bf 4f 04 ac 88 14 30 e1 dd e5 8a 4b 8e bd d5 9b 50 3f 53 c3 25 e7 37 1d f9 8b 8d"
)
_AUD428_ROW13_ACTIVE_POLICY_SHA256 = bytes.fromhex(
    "1f dd 8d 37 85 e3 a2 5d 64 62 cf a7 50 ce 96 8f f3 20 37 09 4f 42 67 4a 9a 75 15 bd ae 6f bf 45"
)
_AUD428_ROW13_LINE_SHA256 = bytes.fromhex(
    "59 7c f5 e5 c4 cd de ce 08 5a 3b 43 9d 32 c3 73 3d 8f 82 1f 12 c5 64 3a e4 0a d5 77 75 e7 88 9b"
)
_AUD428_ROW13_CONTEXT_SHA256 = bytes.fromhex(
    "bd 7f 9b 5c d4 39 91 70 85 b8 24 93 ea 85 a5 23 89 d3 19 28 36 90 eb e3 cf 51 64 e3 84 e1 5d 00"
)
_AUD428_ROW13_APPROVED_RECORDSET_SHA256 = bytes.fromhex(
    "c8 73 dc 44 91 d2 3f 53 61 fd b2 ec e0 cc c2 a6 64 a5 38 71 cc 4c 8d da 7e 98 bb 93 9d a3 96 3b"
)
_AUD428_ROW13_APPROVED_RECORD = copy.deepcopy(_AUD428_ROW13_APPROVED_RECORD)
_AUD428_ROW13_APPROVED_RECORD["identity"]["hashed_secret_bytes"] = list(
    bytes.fromhex("a3 81 34 21 f0 d4 c3 4c c1 33 4f 88 a5 6c 87 cf 42 8c e7 57")
)
_AUD380_CURRENT_DELTA_SOURCE_SHA256 = {
    **_AUD380_CURRENT_DELTA_SOURCE_SHA256,
    "quality/semgrep-dispositions.json": _AUD428_ROW13_CANDIDATE_LEDGER_SHA256,
}
_AUD380_N6_FINAL_SOURCE_SHA256 = {
    **_AUD380_N6_FINAL_SOURCE_SHA256,
    "quality/semgrep-dispositions.json": _AUD428_ROW13_CANDIDATE_LEDGER_SHA256,
}


# Owner-approved 2026-11-09 wasm-bindgen archive identities. Keep the historical
# 506-record policy and all earlier fixture contracts intact; append only these
# three public checksum identities, with the same finite January-10 expiry.
_NOV9_WASM_CLI_PATHS = (
    "frontend.Dockerfile",
    ".github/workflows/reusable-e2e-wasm-build.yml",
    "tests/test_frontend_docker_wasm_parity.py",
)
_NOV9_WASM_CLI_ARCHIVE_SHA256 = bytes.fromhex(
    "82 d1 2b b9 40 e2 d4 e7 2e 0d 56 05 38 7f c1 b8 ca 17 90 44 e0 12 b6 20 f0 ce 4e 74 40 e8 32 0e"
)
_NOV9_WASM_CLI_SCANNER_DIGEST = bytes.fromhex(
    "20 72 3e 69 d0 30 f2 1c 3c 42 bb 5a bc 49 d1 2b 12 24 83 c3"
)
_NOV9_WASM_CLI_POLICY_SHA256 = bytes.fromhex(
    "dc 8d 6b 45 f8 a2 df dd 1d 28 7b 80 0a a6 42 40 db e9 90 35 43 85 ff 28 36 09 a4 15 ea ca 4b 97"
)
_NOV9_WASM_CLI_EXPECTED_RECORDS = [
    {
        "approval_status": "approved",
        "category": "public_integrity_digest",
        "evidence": (
            "Official wasm-bindgen 0.2.129 x86_64-unknown-linux-musl release "
            "archive SHA-256, verified against "
            "https://api.github.com/repos/wasm-bindgen/wasm-bindgen/releases/tags/0.2.129; "
            f"exact source path {path}; owner approved this finite public integrity "
            "identity on 2026-11-09; not credential material."
        ),
        "expires_on": "2027-01-10",
        "identity": {
            "hashed_secret_bytes": list(_NOV9_WASM_CLI_SCANNER_DIGEST),
            "path": path,
            "type": "Hex High Entropy String",
        },
        "owner": "egorribun",
        "reviewed_on": "2026-11-09",
    }
    for path in _NOV9_WASM_CLI_PATHS
]


def _nov9_historical_506_policy_bytes(policy: dict[str, Any]) -> bytes:
    return (json.dumps(policy, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _nov9_historical_506_from_live_policy(
    policy: dict[str, Any],
) -> dict[str, Any]:
    if len(policy.get("records", [])) == 512:
        policy = _nov11_historical_509_from_live_policy(policy)
    records = policy.get("records")
    assert isinstance(records, list), "live disposition records changed"
    assert len(records) == 509, "live disposition row count changed"
    assert records[506:] == _NOV9_WASM_CLI_EXPECTED_RECORDS, (
        "approved wasm-bindgen suffix changed"
    )
    historical = {**policy, "records": copy.deepcopy(records[:506])}
    historical_bytes = _nov9_historical_506_policy_bytes(historical)
    assert len(historical_bytes) == 495838, "prior 506 policy bytes changed"
    assert hashlib.sha256(historical_bytes).digest() == (
        _AUD428_ROW13_ACTIVE_POLICY_SHA256
    ), "prior 506 approved records or header changed"
    accepted = _nov13_verify_dispositions(policy, today=verifier.date(2026, 11, 9))
    assert len(accepted) == 509, "live approved disposition count changed"
    return historical


def _nov9_assert_live_policy_bytes(policy_bytes: bytes) -> None:
    policy_bytes = _nov11_historical_509_policy_bytes(policy_bytes)
    assert len(policy_bytes) == 498820, "live disposition bytes changed"
    assert hashlib.sha256(policy_bytes).digest() == (_NOV9_WASM_CLI_POLICY_SHA256), (
        "live disposition policy digest changed"
    )
    historical = _nov9_historical_506_from_live_policy(json.loads(policy_bytes))
    historical_bytes = _nov9_historical_506_policy_bytes(historical)
    # Everything before the former closing list is byte-identical, including
    # the row13 companion and each old approval's evidence, dates, and owner.
    assert policy_bytes[:495808] == historical_bytes[:495808]
    assert hashlib.sha256(policy_bytes[:494904]).digest() == (
        _AUD428_ROW13_ACTIVE_505_PREFIX_BYTES_SHA256
    ), "prior 505 policy bytes changed"


def test_nov9_wasm_cli_policy_appends_only_three_and_preserves_exact_506() -> None:
    live = _aud380_read_live_policy()
    historical = _nov9_historical_506_from_live_policy(live)
    historical_490 = _aud380_historical_490_from_live_policy(live)
    _aud428_assert_live_policy_is_exact_506(historical, historical_490)
    assert historical["records"][497:505] == _NOV6_ZLIB_EXPECTED_RECORDS
    assert historical["records"][505] == _AUD428_ROW13_APPROVED_RECORD
    expected = {
        _aud380_identity_key(record): record["evidence"]
        for record in _NOV9_WASM_CLI_EXPECTED_RECORDS
    }
    assert len(expected) == 3
    assert verifier._NOV9_WASM_CLI_EVIDENCE == expected
    assert verifier._NOV9_WASM_CLI_PATHS == frozenset(_NOV9_WASM_CLI_PATHS)
    assert verifier._NOV9_WASM_CLI_DIGEST == tuple(_NOV9_WASM_CLI_SCANNER_DIGEST)
    prior_identities = {
        _aud380_identity_key(record)
        for record in historical["records"]
        if record["identity"]["path"] in _NOV9_WASM_CLI_PATHS
    }
    assert len(prior_identities) == 4
    assert verifier._NOV9_WASM_CLI_PRIOR_IDENTITIES == prior_identities
    assert not set(expected) & prior_identities
    assert Counter(row["category"] for row in live["records"]) == Counter(
        row["category"] for row in historical["records"]
    ) + Counter({"public_integrity_digest": 3})


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "extra",
        "reordered",
        "duplicate",
        "old_record",
        "old_expiry",
        "header",
    ],
)
def test_nov9_wasm_cli_live_projection_refuses_scope_drift(mutation: str) -> None:
    policy = _aud380_read_live_policy()
    if mutation == "missing":
        policy["records"].pop()
    elif mutation == "extra":
        policy["records"].append(copy.deepcopy(policy["records"][-1]))
    elif mutation == "reordered":
        policy["records"][506], policy["records"][507] = (
            policy["records"][507],
            policy["records"][506],
        )
    elif mutation == "duplicate":
        policy["records"][508] = copy.deepcopy(policy["records"][506])
    elif mutation == "old_record":
        policy["records"][505]["identity"]["hashed_secret_bytes"][0] ^= 1
    elif mutation == "old_expiry":
        policy["records"][0]["expires_on"] = "2027-01-11"
    else:
        policy["schema_version"] = 2
    with pytest.raises(AssertionError):
        _nov9_historical_506_from_live_policy(policy)


@pytest.mark.parametrize("mutation", ["missing_byte", "extra_byte", "changed_byte"])
def test_nov9_wasm_cli_live_policy_rejects_byte_drift(mutation: str) -> None:
    root = Path(__file__).resolve().parents[1]
    policy_bytes = (
        root / "quality/security-false-positive-dispositions.json"
    ).read_bytes()
    _nov9_assert_live_policy_bytes(policy_bytes)
    if mutation == "missing_byte":
        policy_bytes = policy_bytes[:-1]
    elif mutation == "extra_byte":
        policy_bytes += b"\n"
    else:
        policy_bytes = policy_bytes.replace(
            b'"schema_version": 1', b'"schema_version": 2'
        )
    with pytest.raises(AssertionError, match="live disposition"):
        _nov9_assert_live_policy_bytes(policy_bytes)


@pytest.mark.parametrize("index", range(3))
@pytest.mark.parametrize(
    "mutation",
    [
        "path",
        "wildcard_path",
        "digest",
        "type",
        "category",
        "evidence",
        "owner",
        "reviewed",
        "expiry_shortened",
        "expiry_extended",
        "status",
    ],
)
def test_nov9_wasm_cli_validator_refuses_approval_drift(
    index: int, mutation: str
) -> None:
    record = copy.deepcopy(_NOV9_WASM_CLI_EXPECTED_RECORDS[index])
    assert (
        len(
            _nov13_verify_dispositions(
                _disposition_document(record), today=verifier.date(2026, 11, 9)
            )
        )
        == 1
    )
    if mutation == "path":
        record["identity"]["path"] = "other/changed-source.py"
    elif mutation == "wildcard_path":
        record["identity"]["path"] = "frontend*"
    elif mutation == "digest":
        record["identity"]["hashed_secret_bytes"][0] ^= 1
    elif mutation == "type":
        record["identity"]["type"] = "Secret Keyword"
    elif mutation == "category":
        record["category"] = "documented_crypto_test_vector"
    elif mutation == "evidence":
        record["evidence"] += " altered"
    elif mutation == "owner":
        record["owner"] = "other-owner"
    elif mutation == "reviewed":
        record["reviewed_on"] = "2026-11-08"
    elif mutation == "expiry_shortened":
        record["expires_on"] = "2027-01-09"
    elif mutation == "expiry_extended":
        record["expires_on"] = "2027-01-11"
    else:
        record["approval_status"] = "NOT_APPROVED"
    with pytest.raises(verifier.BaselineArtifactError):
        _nov13_verify_dispositions(
            _disposition_document(record), today=verifier.date(2026, 11, 9)
        )
    policy = _aud380_read_live_policy()
    policy["records"][506 + index] = record
    with pytest.raises(AssertionError, match="approved wasm-bindgen suffix changed"):
        _nov9_historical_506_from_live_policy(policy)


@pytest.mark.parametrize("index", range(3))
def test_nov9_wasm_cli_review_and_inclusive_expiry_are_finite(index: int) -> None:
    document = _disposition_document(
        copy.deepcopy(_NOV9_WASM_CLI_EXPECTED_RECORDS[index])
    )
    expected = {
        verifier.FindingIdentity(
            _NOV9_WASM_CLI_PATHS[index],
            "Hex High Entropy String",
            _NOV9_WASM_CLI_SCANNER_DIGEST.hex(),
            1,
        )
    }
    for today in (verifier.date(2026, 11, 9), verifier.date(2027, 1, 10)):
        assert _nov13_verify_dispositions(document, today=today) == (expected)
    for today in (verifier.date(2026, 11, 8), verifier.date(2027, 1, 11)):
        with pytest.raises(verifier.BaselineArtifactError, match="date range"):
            _nov13_verify_dispositions(document, today=today)
    with pytest.raises(verifier.BaselineArtifactError, match="duplicate"):
        _nov13_verify_dispositions(
            _disposition_document(*document["records"], *document["records"]),
            today=verifier.date(2026, 11, 9),
        )


def _nov9_wasm_cli_source_identities(
    root: Path,
) -> set[tuple[str, str, tuple[int, ...]]]:
    checksum = _NOV9_WASM_CLI_ARCHIVE_SHA256.hex()
    digest = hashlib.sha1(checksum.encode("utf-8"), usedforsecurity=False).digest()
    assert digest == _NOV9_WASM_CLI_SCANNER_DIGEST
    identities = set()
    for path in _NOV9_WASM_CLI_PATHS:
        source = (root / path).read_text(encoding="utf-8")
        checksums = re.findall(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])", source)
        assert checksums.count(checksum) == 1, f"wasm-bindgen checksum changed: {path}"
        identities.add((path, "Hex High Entropy String", tuple(digest)))
    return identities


def test_nov9_wasm_cli_integrity_records_bind_exact_source_values() -> None:
    root = Path(__file__).resolve().parents[1]
    assert _nov9_wasm_cli_source_identities(root) == {
        _aud380_identity_key(record) for record in _NOV9_WASM_CLI_EXPECTED_RECORDS
    }


@pytest.mark.parametrize("path", _NOV9_WASM_CLI_PATHS)
@pytest.mark.parametrize("mutation", ["missing", "changed", "duplicate"])
def test_nov9_wasm_cli_source_bindings_reject_drift(
    tmp_path: Path, path: str, mutation: str
) -> None:
    root = Path(__file__).resolve().parents[1]
    for source_path in _NOV9_WASM_CLI_PATHS:
        target = tmp_path / source_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((root / source_path).read_bytes())
    target = tmp_path / path
    source = target.read_text(encoding="utf-8")
    checksum = _NOV9_WASM_CLI_ARCHIVE_SHA256.hex()
    replacement = {
        "missing": "",
        "changed": "0" * 64,
        "duplicate": f"{checksum} {checksum}",
    }[mutation]
    assert source.count(checksum) == 1
    target.write_text(source.replace(checksum, replacement), encoding="utf-8")
    with pytest.raises(AssertionError, match="wasm-bindgen checksum changed"):
        _nov9_wasm_cli_source_identities(tmp_path)


@pytest.mark.parametrize("path", _NOV9_WASM_CLI_PATHS)
@pytest.mark.parametrize("mutation", ["exact", "path", "digest", "type"])
def test_nov9_wasm_cli_trusted_scan_rejects_unmatched_findings(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    path: str,
    mutation: str,
) -> None:
    repository, _ = _new_git_fixture(tmp_path)
    trusted_sha = _commit_dispositions(repository, _NOV9_WASM_CLI_EXPECTED_RECORDS)
    monkeypatch.setattr(
        verifier, "__file__", str(repository / "scripts" / "verify_secrets_baseline.py")
    )
    digest = _NOV9_WASM_CLI_SCANNER_DIGEST.hex()
    finding_type = "Hex High Entropy String"
    if mutation == "path":
        path = f"unapproved/{path}"
    elif mutation == "digest":
        digest = "0" * 40
    elif mutation == "type":
        finding_type = "Secret Keyword"
    baseline_path = _write(tmp_path / "baseline.json", _document())
    current_path = _write(
        tmp_path / "current.json", _document((path, finding_type, digest, 999))
    )
    result = verifier.main(
        [
            str(baseline_path),
            str(current_path),
            "--trusted-base-source-sha",
            trusted_sha,
        ]
    )
    output = capsys.readouterr()
    assert result == (0 if mutation == "exact" else 1)
    if mutation == "exact":
        assert "1 exact false-positive finding(s)" in output.out
    else:
        assert "new finding" in output.err


# Exact existing NATS logging bindings. Two row11 companion identities are
# rebound one-to-one; all approval metadata and historical snapshots are retained.

_NATS_ROW11_IDENTITY_REBINDS = {
    bytes.fromhex(
        "cd ad 8f c0 d7 36 cd 7c d1 11 3b 50 e5 53 06 32 5c f6 6f 53"
    ): bytes.fromhex("a7 67 b5 3a 9e c6 4d 44 82 4f 03 46 d4 1b fc 53 96 3f 31 8a"),
    bytes.fromhex(
        "29 e2 30 c2 f6 4d 4c fe 7a 8e 8b b7 35 cd 85 1e 0b 2e d7 94"
    ): bytes.fromhex("27 10 b8 1a a6 2d fa 13 62 e5 8d 8c fc 5d d7 e4 29 b3 48 ad"),
}

_NATS_PRE_REBIND_OWNER_RECORDS = copy.deepcopy(_AUD380_PENDING_OWNER_RECORDS)
_AUD380_PENDING_OWNER_RECORDS = copy.deepcopy(_AUD380_PENDING_OWNER_RECORDS)
for _record in _AUD380_PENDING_OWNER_RECORDS:
    _old_digest = bytes(_record["identity"]["hashed_secret_bytes"])
    if (
        _record["identity"]["path"] == "quality/semgrep-dispositions.json"
        and _old_digest in _NATS_ROW11_IDENTITY_REBINDS
    ):
        _record["identity"]["hashed_secret_bytes"] = list(
            _NATS_ROW11_IDENTITY_REBINDS[_old_digest]
        )
_AUD380_PENDING_OWNER_IDENTITIES = frozenset(
    _aud380_identity_key(record) for record in _AUD380_PENDING_OWNER_RECORDS
)
_AUD380_CURRENT_DELTA_IDENTITY_SOURCE_LINES = tuple(
    (
        path,
        finding_type,
        tuple(_NATS_ROW11_IDENTITY_REBINDS.get(bytes(digest), bytes(digest))),
        category,
        line,
    )
    if path == "quality/semgrep-dispositions.json"
    else (path, finding_type, digest, category, line)
    for path, finding_type, digest, category, line in _AUD380_CURRENT_DELTA_IDENTITY_SOURCE_LINES
)

_NATS_CURRENT_SOURCE_REBINDS = {
    "app/core/logging.py": bytes.fromhex(
        "4f 80 22 87 7e c6 43 23 4d 8b 3f a9 65 15 15 16 77 1e e9 34 a4 75 93 2b b1 f6 b4 aa b4 e8 c3 f7"
    ),
    "app/core/otel_logging.py": bytes.fromhex(
        "f6 94 57 c7 be 88 bf af 73 ee 9c cb ba 41 0f 36 d6 35 5a d6 ca fe 46 49 67 d8 a4 ac 65 a2 f5 ba"
    ),
    "tests/test_otel_logging_bridge.py": bytes.fromhex(
        "4b 2a 7f 17 3c 78 ed df 51 c1 60 c3 db 9c 91 e3 eb 5a 20 ba e6 10 95 f8 38 75 d0 52 d3 93 af a7"
    ),
    "scripts/owned_nats_outage_cli.py": bytes.fromhex(
        "f7 5d 4d ff 60 70 e1 c1 09 ad 07 67 0f c9 5f a4 71 71 19 40 f8 de 5a e1 b5 0d 02 49 0f b6 d9 f1"
    ),
    "scripts/owned_nats_transport_port.py": bytes.fromhex(
        "5e 30 b0 20 07 af c6 7f a7 70 04 cb 94 29 a1 dc 2f 9a 74 02 c8 f8 82 44 3e 20 2b d9 4f 4c e7 a5"
    ),
    "quality/semgrep-dispositions.json": bytes.fromhex(
        "0f 61 39 9a a8 7c 4d 32 74 aa de b1 61 f6 0a 24 dc 7b 1d ab 14 01 7f 2f ba f4 2b 4f 01 f7 83 78"
    ),
}

_AUD380_CURRENT_DELTA_SOURCE_SHA256 = {
    **_AUD380_CURRENT_DELTA_SOURCE_SHA256,
    **_NATS_CURRENT_SOURCE_REBINDS,
}
_AUD380_N6_FINAL_SOURCE_SHA256 = {
    **_AUD380_N6_FINAL_SOURCE_SHA256,
    **{
        path: digest
        for path, digest in _NATS_CURRENT_SOURCE_REBINDS.items()
        if path in _AUD380_N6_FINAL_SOURCE_SHA256
    },
}

_NATS_ROW11_LINE_REBINDS = {
    313: (
        bytes.fromhex(
            "70 fc 65 82 07 e9 b1 74 03 bd 89 f0 86 61 96 8c 8d bf 03 19 78 5e 5b d6 66 ef d8 81 bd 80 a7 47"
        ),
        bytes.fromhex(
            "02 a4 71 2a 3e cd 24 ed 91 99 c3 c9 a1 4a 03 b4 3b 7f e4 cb 0f 1c ba c9 89 5b 17 44 24 3a 8b ca"
        ),
    ),
    329: (
        bytes.fromhex(
            "21 cb d6 1c bb 40 cb 2b 65 61 c4 35 b4 48 f5 5c ce 1a 24 38 40 ca e7 cb 61 6e e0 e5 8a 7e 65 36"
        ),
        bytes.fromhex(
            "1c 29 10 2b cc fd c5 74 c1 be 2d 1a 40 5d b1 c9 18 d3 46 4b 0c a8 9e 83 2d 3f a8 36 37 75 a2 69"
        ),
    ),
}

_AUD380_CURRENT_DELTA_SOURCE_LINE_HASHES = tuple(
    (path, line, *_NATS_ROW11_LINE_REBINDS[line])
    if path == "quality/semgrep-dispositions.json" and line in _NATS_ROW11_LINE_REBINDS
    else (path, line, line_hash, context_hash)
    for path, line, line_hash, context_hash in _AUD380_CURRENT_DELTA_SOURCE_LINE_HASHES
)

_AUD380_PENDING_NEW_ADDITIONS_SHA256 = bytes.fromhex(
    "d9 68 3c 5f 69 35 3e ca 3e c0 a1 d7 3a 4d 27 c9 76 d2 77 71 4d 9b dd 01 09 19 31 80 bd 2f f9 0e"
)

_AUD380_APPROVED_NEW_ADDITIONS_SHA256 = bytes.fromhex(
    "3d 76 e3 7e 0d 95 de 2d 1d 87 59 0e 3e 44 4d 25 74 45 a9 67 b7 bf 61 66 7c 75 b0 65 37 9a 30 71"
)

_AUD380_CONDITIONAL_RECORDSET_SHA256 = bytes.fromhex(
    "ad 81 e5 1c b6 49 2e 31 fb 82 04 31 b1 6a 88 82 89 d4 08 32 47 f0 06 b1 e9 0b 79 f7 d8 e6 fb 44"
)

_AUD380_N3_PENDING_493_RECORDSET_SHA256 = bytes.fromhex(
    "55 85 bd b7 33 73 ed f8 6b 10 63 b3 1f d3 a6 17 c0 91 4d 7b f3 34 a2 61 76 41 ae 1e 09 81 11 49"
)

_AUD380_N3_CONDITIONAL_493_RECORDSET_SHA256 = bytes.fromhex(
    "8e 0c 85 3d 59 c5 03 3d f8 96 be 64 38 9c 5d a6 48 36 e0 f8 5d 5d bb ca 9e e2 38 db a1 c1 24 53"
)

_AUD428_ROW13_ACTIVE_505_PREFIX_CANONICAL_SHA256 = bytes.fromhex(
    "52 a7 f6 d1 da 30 39 f3 99 65 99 5d 5f 53 dc 3a b6 2d 08 32 30 5c 0e 87 74 23 48 51 7c 2f d4 a1"
)

_AUD428_ROW13_ACTIVE_POLICY_SHA256 = bytes.fromhex(
    "f9 b5 48 e8 6b c5 ed fd b0 ab 5d 41 17 c0 ed d4 5e 91 94 81 15 d1 66 9b 2d 87 63 6d 8d cc 90 bc"
)

_AUD428_ROW13_ACTIVE_505_PREFIX_BYTES_SHA256 = bytes.fromhex(
    "3e e6 7e 51 7a fc c7 a8 20 b2 77 f2 d0 3b a6 70 8b 30 cc 7f 49 e3 11 9d c9 07 59 f5 0c 52 57 94"
)

_AUD428_ROW13_CANDIDATE_LEDGER_SHA256 = bytes.fromhex(
    "0f 61 39 9a a8 7c 4d 32 74 aa de b1 61 f6 0a 24 dc 7b 1d ab 14 01 7f 2f ba f4 2b 4f 01 f7 83 78"
)

_AUD428_ROW13_BASE_LEDGER_SHA256 = bytes.fromhex(
    "9d 27 96 70 42 37 84 92 67 77 b5 e1 ca c5 e8 2b 39 7d 11 39 32 8d b8 65 5b 9a c8 8f fa ac 1b 7e"
)

_NOV9_WASM_CLI_POLICY_SHA256 = bytes.fromhex(
    "fa ad 8c e3 b1 0c 43 dc 6b 59 e9 b8 6f 47 be 70 2a e4 90 d0 e5 09 bd 8a 65 9e 7b 60 c6 4c 49 07"
)


def test_nats_row11_rebind_preserves_two_existing_approvals() -> None:
    assert len(_NATS_ROW11_IDENTITY_REBINDS) == 2
    assert len(set(_NATS_ROW11_IDENTITY_REBINDS.values())) == 2
    changed = []
    for before, after in zip(
        _NATS_PRE_REBIND_OWNER_RECORDS, _AUD380_PENDING_OWNER_RECORDS, strict=True
    ):
        if before == after:
            continue
        expected = copy.deepcopy(before)
        old_digest = bytes(expected["identity"]["hashed_secret_bytes"])
        assert expected["identity"]["path"] == "quality/semgrep-dispositions.json"
        assert expected["identity"]["type"] == "Hex High Entropy String"
        assert expected["category"] == "public_integrity_digest"
        expected["identity"]["hashed_secret_bytes"] = list(
            _NATS_ROW11_IDENTITY_REBINDS[old_digest]
        )
        assert after == expected
        changed.append(old_digest)
    assert set(changed) == set(_NATS_ROW11_IDENTITY_REBINDS)
    historical = {
        bytes(row[2])
        for row in _AUD380_N21_HISTORICAL_IDENTITY_SOURCE_LINES
        if row[0] == "quality/semgrep-dispositions.json"
    }
    assert set(changed) <= historical
    assert not set(_NATS_ROW11_IDENTITY_REBINDS.values()) & historical


# Exact owned NATS subprocess companion rebinds after the 2026-11-10 attempt
# evidence change. Two existing companion pins in the scripts/owned_nats_process.py
# subprocess-injection disposition, and their two existing approved identities,
# are rebound one-to-one; every approval field and historical snapshot stays.
_NATS_PROCESS_PRE_REBIND_POLICY_SHA256 = _NOV9_WASM_CLI_POLICY_SHA256
_NATS_PROCESS_PRE_REBIND_LEDGER_SHA256 = _AUD428_ROW13_CANDIDATE_LEDGER_SHA256

# path -> (previous companion SHA-256, previous identity, current identity)
_NATS_PROCESS_COMPANION_REBINDS = {
    "scripts/owned_nats_outage_cli.py": (
        bytes.fromhex(
            "6c 03 88 64 ac a8 c9 7f 04 42 d2 5c 3a bf b3 37 eb 95 85 db 49 8f 75 cc b6 f4 42 4f 8d fb 73 d5"
        ),
        bytes.fromhex("e4 9b 75 0f 6a db e3 69 09 83 65 4e d3 a9 02 b1 25 85 e8 34"),
        bytes.fromhex("14 43 f9 e4 75 1b 3a b6 62 87 af 4b f0 e1 fa ec 11 73 9a b2"),
    ),
    "scripts/owned_nats_transport_port.py": (
        bytes.fromhex(
            "cb 69 48 b7 e7 08 7c 7e 89 0d 19 5a ba 44 d2 6d 1e 3b c1 0e f4 ed b5 73 fb 81 8e 43 ee bd 94 3c"
        ),
        bytes.fromhex("06 d0 98 7c 54 c4 90 dc 72 80 d2 5b 21 b4 78 28 f5 d7 6c f9"),
        bytes.fromhex("99 71 53 f5 10 0c 74 0e 8a 68 f4 a9 22 60 a8 6f d0 d7 75 c9"),
    ),
}

_NOV9_WASM_CLI_POLICY_SHA256 = bytes.fromhex(
    "aa 03 b0 78 43 1f 10 92 6f 13 18 3b 71 9b 46 09 34 89 a6 db ea 2a da 8e 92 3a dc 5b 65 7c 15 11"
)
_AUD428_ROW13_ACTIVE_POLICY_SHA256 = bytes.fromhex(
    "35 d2 78 a7 9b 22 dc 91 4a d1 f4 9c 8d 13 e9 bc da 22 61 22 7b 48 34 2c ca c0 30 87 50 79 f0 18"
)
_AUD428_ROW13_ACTIVE_505_PREFIX_BYTES_SHA256 = bytes.fromhex(
    "6e 64 de d0 0e 80 ce dc 90 31 87 13 7e 4a 0e e4 d6 38 19 95 ff d4 11 43 d2 e9 be a2 30 16 80 c5"
)
_AUD428_ROW13_ACTIVE_505_PREFIX_CANONICAL_SHA256 = bytes.fromhex(
    "9e 83 f6 ae 2e 3e e9 e2 20 d7 d7 20 8c ea 8e 9c a4 77 a1 9a 00 cf 08 f3 45 c0 51 e2 77 8e db e7"
)
_AUD380_APPROVED_OWNER_ADDITIONS_SHA256 = bytes.fromhex(
    "46 aa b9 b1 c1 c5 8c 6b 7b a2 47 19 6e 89 1a 47 83 29 6e 2d 23 78 f3 86 82 86 77 66 22 ea 5e 08"
)
_AUD380_CONDITIONAL_RECORDSET_SHA256 = bytes.fromhex(
    "6a ce 88 16 89 4a df ca d1 bc b6 b9 2e dd 97 9e f9 c1 32 d6 15 5f be ea f7 4f 05 39 5b 06 df b8"
)
_AUD380_N3_PENDING_493_RECORDSET_SHA256 = bytes.fromhex(
    "0d 64 21 26 54 fb eb aa 70 3e 4e 95 9a 9d 58 77 bb 1a c4 ee 81 bd f1 b2 0c 0e 0e 01 62 ef e8 5a"
)
_AUD380_N3_CONDITIONAL_493_RECORDSET_SHA256 = bytes.fromhex(
    "c5 70 bc ca d4 31 0a a4 c6 c7 96 ff 15 f3 03 89 e7 64 9f c8 46 81 b5 a3 86 58 88 4c 92 79 a3 32"
)
_AUD428_ROW13_CANDIDATE_LEDGER_SHA256 = bytes.fromhex(
    "ec 87 39 fa f1 3a e8 30 86 b7 c7 52 14 af 88 b3 f3 77 43 12 95 00 d5 7c 16 fc 15 21 ea e7 d9 9f"
)
_AUD428_ROW13_BASE_LEDGER_SHA256 = bytes.fromhex(
    "20 dc ea e9 26 fa fe d4 6e a8 16 cd 44 2f 96 ca e1 9a 38 34 f5 7e c0 b0 26 2c b8 24 0c fa f0 51"
)
_AUD380_CURRENT_DELTA_SOURCE_SHA256 = {
    **_AUD380_CURRENT_DELTA_SOURCE_SHA256,
    "quality/semgrep-dispositions.json": _AUD428_ROW13_CANDIDATE_LEDGER_SHA256,
}
_AUD380_N6_FINAL_SOURCE_SHA256 = {
    **_AUD380_N6_FINAL_SOURCE_SHA256,
    "quality/semgrep-dispositions.json": _AUD428_ROW13_CANDIDATE_LEDGER_SHA256,
}


def test_nats_process_companion_rebind_changes_only_two_identities() -> None:
    root = Path(__file__).resolve().parents[1]
    policy_bytes = (
        root / "quality/security-false-positive-dispositions.json"
    ).read_bytes()
    ledger_bytes = _aud154_historical_source_bytes(
        "quality/semgrep-dispositions.json",
        (root / "quality/semgrep-dispositions.json").read_bytes(),
    )
    assert len(_NATS_PROCESS_COMPANION_REBINDS) == 2
    disposition = json.loads(ledger_bytes.decode("utf-8"))["dispositions"][6]
    assert disposition["path"] == "scripts/owned_nats_process.py"
    assert disposition["check_id"].endswith("subprocess-injection.subprocess-injection")
    companions = {item["path"]: item["sha256"] for item in disposition["companions"]}
    previous_ledger = ledger_bytes
    rebinds = {}
    for path, rebind in _NATS_PROCESS_COMPANION_REBINDS.items():
        old_companion, old_identity, new_identity = rebind
        old_hex = old_companion.hex()
        current_hex = hashlib.sha256((root / path).read_bytes()).hexdigest()
        assert companions[path] == current_hex
        assert old_hex != current_hex
        old_digest = hashlib.sha1(old_hex.encode("ascii"), usedforsecurity=False)
        assert old_digest.digest() == old_identity
        new_digest = hashlib.sha1(current_hex.encode("ascii"), usedforsecurity=False)
        assert new_digest.digest() == new_identity
        assert ledger_bytes.count(current_hex.encode("ascii")) == 1
        previous_ledger = previous_ledger.replace(
            current_hex.encode("ascii"), old_hex.encode("ascii"), 1
        )
        rebinds[new_identity] = old_identity
    assert hashlib.sha256(previous_ledger).digest() == (
        _NATS_PROCESS_PRE_REBIND_LEDGER_SHA256
    )

    policy = _nov11_historical_509_from_live_policy(
        json.loads(policy_bytes.decode("utf-8"))
    )
    restored = copy.deepcopy(policy)
    changed = []
    for index, record in enumerate(restored["records"]):
        identity = record["identity"]
        digest = bytes(identity["hashed_secret_bytes"])
        assert digest not in rebinds.values(), "previous identity is still live"
        if digest not in rebinds:
            continue
        assert identity["path"] == "quality/semgrep-dispositions.json"
        assert identity["type"] == "Hex High Entropy String"
        assert record["category"] == "public_integrity_digest"
        assert record["approval_status"] == "approved"
        identity["hashed_secret_bytes"] = list(rebinds[digest])
        changed.append(index)
    assert changed == [389, 394]
    restored_bytes = (json.dumps(restored, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )
    assert hashlib.sha256(restored_bytes).digest() == (
        _NATS_PROCESS_PRE_REBIND_POLICY_SHA256
    ), "anything besides the two companion identities changed"


# Exact existing row13 companion rebind for private Pact Go build isolation.
# Preserve all 509 approvals, including the three WASM suffix identities.
_AUD428_ROW13_COMPANION_SHA256 = bytes.fromhex(
    "b6 88 0e 4f 27 06 40 dc 5b 1e fc a7 05 8e 48 84 86 f4 a6 6d 06 50 c5 6a 74 61 46 02 d9 dc 06 fd"
)
_AUD428_ROW13_CANDIDATE_LEDGER_SHA256 = bytes.fromhex(
    "81 2c 1d cb ed 8a c6 3b 4c df 66 86 51 5a 45 ab 57 d2 57 88 f9 25 4b 20 57 de 82 5b cd d4 44 36"
)
_AUD428_ROW13_ACTIVE_POLICY_SHA256 = bytes.fromhex(
    "2f 45 11 e6 61 01 0c 99 35 f9 71 91 57 fe 8c 28 6f 2f 8f ea 98 11 70 f0 a5 8d 07 51 07 fe db f5"
)
_AUD428_ROW13_LINE_SHA256 = bytes.fromhex(
    "8e d1 2b 2e ef 00 93 b4 67 ee b2 64 c4 5d 1b c5 98 60 5c db 2a 99 84 31 69 64 a0 95 fa 6d 8b be"
)
_AUD428_ROW13_CONTEXT_SHA256 = bytes.fromhex(
    "04 f3 47 28 cf f0 40 28 7e 6f 4d 16 d9 5b 96 7e 6e 0a 14 34 5f 4b 40 d2 f0 52 a4 d2 a5 9b bf 37"
)
_AUD428_ROW13_APPROVED_RECORDSET_SHA256 = bytes.fromhex(
    "e1 65 93 75 ac 64 94 92 e0 c2 ae 6f 47 f9 f6 24 a9 2d 3e eb cd 80 38 b7 6e 1a 1a 57 b4 64 d1 94"
)
_AUD428_ROW13_APPROVED_RECORD = copy.deepcopy(_AUD428_ROW13_APPROVED_RECORD)
_AUD428_ROW13_APPROVED_RECORD["identity"]["hashed_secret_bytes"] = list(
    bytes.fromhex("b2 da 70 92 17 e3 b4 8d 27 24 95 62 ee 31 33 81 38 76 33 7e")
)
_AUD380_CURRENT_DELTA_SOURCE_SHA256 = {
    **_AUD380_CURRENT_DELTA_SOURCE_SHA256,
    "quality/semgrep-dispositions.json": _AUD428_ROW13_CANDIDATE_LEDGER_SHA256,
}
_AUD380_N6_FINAL_SOURCE_SHA256 = {
    **_AUD380_N6_FINAL_SOURCE_SHA256,
    "quality/semgrep-dispositions.json": _AUD428_ROW13_CANDIDATE_LEDGER_SHA256,
}


_NOV9_WASM_CLI_POLICY_SHA256 = bytes.fromhex(
    "8d fd d3 02 18 61 98 5c 5f 61 d1 74 77 72 15 49 01 f9 96 19 78 dc ec 7a 82 03 6c 91 fe fd 72 db"
)
_NATS_PROCESS_PRE_REBIND_POLICY_SHA256 = bytes.fromhex(
    "76 ad 5b d3 3c 58 68 72 bc 8a 36 e5 03 ca 6b 24 3f 7c ca ab b3 45 b4 0e d7 fb 8b 03 fc 6b 12 2e"
)
_NATS_PROCESS_PRE_REBIND_LEDGER_SHA256 = bytes.fromhex(
    "2c 86 cd ea bb 47 2f 0d 03 57 db ad c3 dd 42 e9 e3 1b f6 45 9c 1a de 28 d9 a4 e9 25 ff 06 4f fe"
)


# Owner-approved 2026-11-11 Go image identity. The older contracts operate on
# the exact 509-record prefix; the live document appends only Go, ZAP and
# Calico.
_NOV11_GO_IMAGE_SCANNER_DIGEST = bytes.fromhex(
    "c8 64 20 19 43 35 0a eb 96 c2 e1 67 52 e3 9a f0 6a bb 45 e7"
)
_NOV11_GO_IMAGE_APPROVED_RECORD = {
    "approval_status": "approved",
    "category": "public_integrity_digest",
    "evidence": (
        "Official golang:1.26.11-alpine3.24 image manifest SHA-256, verified against "
        "https://github.com/docker-library/repo-info/blob/"
        "2d1d058f9dd4c2772834f3c0b3e81c4f599c7ba1/"
        "repos/golang/remote/1.26.11-alpine3.24.md; exact source path "
        "tests/test_docker_startup_contracts.py; owner approved this finite public "
        "integrity identity on 2026-11-11; not credential material."
    ),
    "expires_on": "2027-01-10",
    "identity": {
        "hashed_secret_bytes": list(_NOV11_GO_IMAGE_SCANNER_DIGEST),
        "path": "tests/test_docker_startup_contracts.py",
        "type": "Hex High Entropy String",
    },
    "owner": "egorribun",
    "reviewed_on": "2026-11-11",
}


def _nov11_historical_509_from_live_policy(policy: dict[str, Any]) -> dict[str, Any]:
    policy = _nov11_restore_helper_identities(policy)
    records = policy.get("records")
    assert isinstance(records, list), "live disposition records changed"
    assert len(records) == 512, "live disposition row count changed"
    assert records[509:] == [
        _NOV11_GO_IMAGE_APPROVED_RECORD,
        _NOV11_ZAP_IMAGE_APPROVED_RECORD,
        _NOV12_CALICO_APPROVED_RECORD,
    ], "live disposition approved Go, ZAP and Calico suffix changed"
    historical = {**policy, "records": copy.deepcopy(records[:509])}
    historical_bytes = _nov9_historical_506_policy_bytes(historical)
    assert hashlib.sha256(historical_bytes).digest() == _NOV9_WASM_CLI_POLICY_SHA256, (
        "live disposition prior 509 records or header changed"
    )
    return historical


def _nov11_historical_509_policy_bytes(policy_bytes: bytes) -> bytes:
    policy = json.loads(policy_bytes)
    assert policy_bytes == _nov9_historical_506_policy_bytes(policy), (
        "live disposition noncanonical bytes changed"
    )
    historical = _nov11_historical_509_from_live_policy(policy)
    historical_bytes = _nov9_historical_506_policy_bytes(historical)
    restored_bytes = _nov9_historical_506_policy_bytes(
        _nov11_restore_helper_identities(policy)
    )
    assert restored_bytes[:498790] == historical_bytes[:498790], (
        "live disposition prior 509 byte prefix changed"
    )
    return historical_bytes


def test_nov11_go_and_zap_images_append_exact_approvals() -> None:
    root = Path(__file__).resolve().parents[1]
    policy_bytes = (
        root / "quality/security-false-positive-dispositions.json"
    ).read_bytes()
    historical_bytes = _nov11_historical_509_policy_bytes(policy_bytes)
    assert len(json.loads(historical_bytes)["records"]) == 509
    accepted = _nov13_verify_dispositions(
        json.loads(policy_bytes), today=verifier.date(2026, 11, 12)
    )
    assert len(accepted) == 512


@pytest.mark.parametrize(
    "mutation",
    ["missing", "extra", "old_identity", "old_expiry", "header", "new_metadata"],
)
def test_nov11_go_image_projection_refuses_scope_drift(mutation: str) -> None:
    root = Path(__file__).resolve().parents[1]
    policy = json.loads(
        (root / "quality/security-false-positive-dispositions.json").read_bytes()
    )
    if mutation == "missing":
        policy["records"].pop()
    elif mutation == "extra":
        policy["records"].append(copy.deepcopy(policy["records"][-1]))
    elif mutation == "old_identity":
        policy["records"][505]["identity"]["hashed_secret_bytes"][0] ^= 1
    elif mutation == "old_expiry":
        policy["records"][0]["expires_on"] = "2027-01-11"
    elif mutation == "header":
        policy["schema_version"] = 2
    else:
        policy["records"][-1]["expires_on"] = "2027-01-11"
    with pytest.raises(AssertionError, match="live disposition"):
        _nov11_historical_509_from_live_policy(policy)


def test_nov11_go_image_approval_has_finite_review_and_expiry() -> None:
    document = _disposition_document(copy.deepcopy(_NOV11_GO_IMAGE_APPROVED_RECORD))
    expected = {
        verifier.FindingIdentity(
            "tests/test_docker_startup_contracts.py",
            "Hex High Entropy String",
            _NOV11_GO_IMAGE_SCANNER_DIGEST.hex(),
            1,
        )
    }
    for today in (verifier.date(2026, 11, 11), verifier.date(2027, 1, 10)):
        assert _nov13_verify_dispositions(document, today=today) == expected
    for today in (verifier.date(2026, 11, 10), verifier.date(2027, 1, 11)):
        with pytest.raises(verifier.BaselineArtifactError, match="date range"):
            _nov13_verify_dispositions(document, today=today)


@pytest.mark.parametrize("mutation", ["exact", "path", "digest", "type"])
def test_nov11_go_image_trusted_scan_refuses_unmatched_findings(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mutation: str,
) -> None:
    repository, _ = _new_git_fixture(tmp_path)
    trusted_sha = _commit_dispositions(repository, [_NOV11_GO_IMAGE_APPROVED_RECORD])
    monkeypatch.setattr(
        verifier, "__file__", str(repository / "scripts" / "verify_secrets_baseline.py")
    )
    path = "tests/test_docker_startup_contracts.py"
    digest = _NOV11_GO_IMAGE_SCANNER_DIGEST.hex()
    finding_type = "Hex High Entropy String"
    if mutation == "path":
        path = f"unapproved/{path}"
    elif mutation == "digest":
        digest = "0" * 40
    elif mutation == "type":
        finding_type = "Secret Keyword"
    baseline_path = _write(tmp_path / "baseline.json", _document())
    current_path = _write(
        tmp_path / "current.json", _document((path, finding_type, digest, 999))
    )
    result = verifier.main(
        [
            str(baseline_path),
            str(current_path),
            "--trusted-base-source-sha",
            trusted_sha,
        ]
    )
    output = capsys.readouterr()
    assert result == (0 if mutation == "exact" else 1)
    if mutation == "exact":
        assert "1 exact false-positive finding(s)" in output.out
    else:
        assert "new finding" in output.err


# Exact owner-authorized 1:1 provenance rebind; no new scanner approvals.
_NOV11_HELPER_REBINDS = {
    bytes.fromhex(
        "bd 96 23 45 d8 3f 8a e2 62 8a 44 4a 55 19 96 bf 60 bc 0c f4"
    ): bytes.fromhex("d1 57 6c bf 10 53 44 4c fd 3d b4 a2 06 bf 42 de 1f c5 5f e6"),
    bytes.fromhex(
        "dd 0f ba 1b b2 74 86 6f 7a a4 d4 e6 fa 2a 59 a1 c0 17 a3 2f"
    ): bytes.fromhex("fd 04 92 54 22 9e 1b 63 bd 5c c4 d0 5d 58 a6 8c cc c3 1f 00"),
    bytes.fromhex(
        "64 dc 49 53 d6 87 19 db 9b 43 88 34 35 2f c9 a6 bc f7 a2 40"
    ): bytes.fromhex("9a d3 26 dd 83 03 59 85 b3 02 fd 7e 96 8b 8d 06 5a c2 ca 74"),
    bytes.fromhex(
        "aa d3 f1 02 d9 8c a2 30 c0 ed 9e bf 50 41 4f b3 56 a1 42 70"
    ): bytes.fromhex("b2 38 76 16 97 f1 2f 10 96 f1 ec 38 a3 59 cd f4 a8 45 e7 e8"),
    bytes.fromhex(
        "60 74 a1 24 44 38 78 1b 15 ea 8a 25 00 68 93 a6 a6 53 cd b8"
    ): bytes.fromhex("71 d7 aa 50 9d e8 0f bf 22 0f 7b 6f e9 be 4e 0a b4 17 26 41"),
}
_NOV11_HELPER_PATHS = (
    "scripts/quality/benchmark_capture_activation.py",
    "tests/test_benchmark_capture_activation_workflow.py",
)
_NOV11_HELPER_REBIND_EVIDENCE = (
    " Existing identity rebound 1:1 under owner standing authorization on "
    "2026-11-11; original approval and expiry unchanged."
)


def _nov11_restore_helper_identities(policy: dict[str, Any]) -> dict[str, Any]:
    restored = _aud154_historical_policy(policy)
    records = restored.get("records")
    assert isinstance(records, list), "live disposition records changed"
    expected = {
        (path, new): old
        for path in _NOV11_HELPER_PATHS
        for old, new in _NOV11_HELPER_REBINDS.items()
    }
    seen = set()
    for record in records:
        identity = record["identity"]
        key = (identity["path"], bytes(identity["hashed_secret_bytes"]))
        if key not in expected:
            continue
        assert key not in seen, "live disposition duplicate helper rebind"
        assert identity["type"] == "Hex High Entropy String"
        assert record["evidence"].endswith(_NOV11_HELPER_REBIND_EVIDENCE)
        assert record["evidence"].count("checkpoint 0fe40908") == 1
        seen.add(key)
        identity["hashed_secret_bytes"] = list(expected[key])
        record["evidence"] = (
            record["evidence"]
            .removesuffix(_NOV11_HELPER_REBIND_EVIDENCE)
            .replace("checkpoint 0fe40908", "checkpoint ca6d7117")
        )
    assert seen == set(expected), "live disposition helper rebind set changed"
    return restored


@pytest.mark.parametrize("index", range(10))
@pytest.mark.parametrize(
    "mutation", ["digest", "path", "type", "expiry", "evidence", "old_checkpoint"]
)
def test_nov11_helper_rebind_rejects_scope_drift(index: int, mutation: str) -> None:
    root = Path(__file__).resolve().parents[1]
    policy = json.loads(
        (root / "quality/security-false-positive-dispositions.json").read_bytes()
    )
    records = [
        row
        for row in policy["records"]
        if row["identity"]["path"] in _NOV11_HELPER_PATHS
        and bytes(row["identity"]["hashed_secret_bytes"])
        in _NOV11_HELPER_REBINDS.values()
    ]
    assert len(records) == 10
    record = records[index]
    if mutation == "digest":
        record["identity"]["hashed_secret_bytes"][0] ^= 1
    elif mutation == "path":
        record["identity"]["path"] = "scripts/quality/other.py"
    elif mutation == "type":
        record["identity"]["type"] = "Base64 High Entropy String"
    elif mutation == "expiry":
        record["expires_on"] = "2027-01-11"
    elif mutation == "old_checkpoint":
        record["evidence"] = record["evidence"].replace(
            "checkpoint 0fe40908", "checkpoint ca6d7117"
        )
    else:
        record["evidence"] += " changed"
    with pytest.raises(AssertionError):
        _nov11_historical_509_from_live_policy(policy)


# Exact approved ZAP suffix; preserve all 510 published records and expiries.
_NOV11_ZAP_IMAGE_SCANNER_DIGEST = bytes.fromhex(
    "0e 68 5f 46 61 f2 21 37 b3 fe 6d cb ff 55 1c 62 17 a4 28 e2"
)
_NOV11_ZAP_IMAGE_APPROVED_RECORD = {
    "approval_status": "approved",
    "category": "public_integrity_digest",
    "evidence": "Official ghcr.io/zaproxy/zaproxy image SHA-256 pin in .zap/image.txt:1; owner approved this exact public integrity identity on 2026-11-11; not credential material. The image digest does not freeze dynamically updated ZAP add-ons.",
    "expires_on": "2027-01-10",
    "identity": {
        "hashed_secret_bytes": list(_NOV11_ZAP_IMAGE_SCANNER_DIGEST),
        "path": ".zap/image.txt",
        "type": "Hex High Entropy String",
    },
    "owner": "egorribun",
    "reviewed_on": "2026-11-11",
}
_NOV11_PRE_ZAP_POLICY_SHA256 = bytes.fromhex(
    "cc 56 ef 06 33 3c db 43 f1 2f 6a 29 f3 53 9f da 0b 53 07 c9 11 ea 34 ed dc 56 df c6 b1 d5 51 f0"
)


def test_nov11_zap_image_preserves_published_policy_and_source_identity() -> None:
    root = Path(__file__).resolve().parents[1]
    policy = json.loads(
        (root / "quality/security-false-positive-dispositions.json").read_bytes()
    )
    _nov11_historical_509_from_live_policy(policy)
    policy = _aud154_historical_policy(policy)
    previous = {**policy, "records": policy["records"][:510]}
    assert (
        hashlib.sha256(_nov9_historical_506_policy_bytes(previous)).digest()
        == _NOV11_PRE_ZAP_POLICY_SHA256
    )
    image = (root / ".zap/image.txt").read_text()
    assert image.count("\n") == 1 and image.endswith("\n")
    prefix = "ghcr.io/zaproxy/zaproxy@sha256:"
    assert image.startswith(prefix)
    digest = image.removeprefix(prefix).strip()
    assert len(digest) == 64
    assert (
        hashlib.sha1(digest.encode("ascii"), usedforsecurity=False).digest()
        == _NOV11_ZAP_IMAGE_SCANNER_DIGEST
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "path",
        "digest",
        "type",
        "category",
        "owner",
        "review",
        "expiry",
        "evidence",
        "go_record",
    ],
)
def test_nov11_zap_image_projection_rejects_scope_drift(mutation: str) -> None:
    root = Path(__file__).resolve().parents[1]
    policy = json.loads(
        (root / "quality/security-false-positive-dispositions.json").read_bytes()
    )
    record = policy["records"][510]
    if mutation == "path":
        record["identity"]["path"] = ".zap/other.txt"
    elif mutation == "digest":
        record["identity"]["hashed_secret_bytes"][0] ^= 1
    elif mutation == "type":
        record["identity"]["type"] = "Secret Keyword"
    elif mutation == "category":
        record["category"] = "synthetic_test_fixture"
    elif mutation == "owner":
        record["owner"] = "someone_else"
    elif mutation == "review":
        record["reviewed_on"] = "2026-11-10"
    elif mutation == "expiry":
        record["expires_on"] = "2027-01-11"
    elif mutation == "evidence":
        record["evidence"] += " changed"
    else:
        policy["records"][509]["expires_on"] = "2027-01-11"
    with pytest.raises(AssertionError, match="live disposition"):
        _nov11_historical_509_from_live_policy(policy)


def test_nov11_zap_image_approval_has_finite_review_and_expiry() -> None:
    document = _disposition_document(copy.deepcopy(_NOV11_ZAP_IMAGE_APPROVED_RECORD))
    expected = {
        verifier.FindingIdentity(
            ".zap/image.txt",
            "Hex High Entropy String",
            _NOV11_ZAP_IMAGE_SCANNER_DIGEST.hex(),
            1,
        )
    }
    for today in (verifier.date(2026, 11, 11), verifier.date(2027, 1, 10)):
        assert _nov13_verify_dispositions(document, today=today) == expected
    for today in (verifier.date(2026, 11, 10), verifier.date(2027, 1, 11)):
        with pytest.raises(verifier.BaselineArtifactError, match="date range"):
            _nov13_verify_dispositions(document, today=today)


# AUD154 changes source provenance only. Pin current bytes before projecting
# the exact immutable predecessor for the older audit contracts.
_AUD154_SOURCE_PINS = {
    "scripts/live_stand.py": (
        bytes.fromhex(
            "c2 d8 95 9a 48 8c b7 7e 00 1a d3 b7 5a fb 7b f9 90 02 a9 1a 78 9c 67 a4 fa 47 70 ed 02 b7 7c 2c"
        ),
        bytes.fromhex(
            "31 24 56 fe 94 57 db e9 e9 a9 1e 9e 88 44 4c 9d 36 88 92 51 46 c1 dc a6 5c ec 90 de f3 72 1e d4"
        ),
    ),
    "frontend/package.json": (
        bytes.fromhex(
            "c6 37 a6 46 14 0b 98 25 17 00 67 f0 58 28 c3 77 84 c0 57 79 62 3d a7 f6 58 4d d5 ad 1d ef dd 56"
        ),
        bytes.fromhex(
            "4c 4b 8f e5 a0 b2 ac aa 2d ad 16 7f 4e 00 4c 34 cf df 10 78 c8 1b 4d 28 dd 0b 50 fe 06 73 1d f2"
        ),
    ),
    "quality/semgrep-dispositions.json": (
        bytes.fromhex(
            "81 2c 1d cb ed 8a c6 3b 4c df 66 86 51 5a 45 ab 57 d2 57 88 f9 25 4b 20 57 de 82 5b cd d4 44 36"
        ),
        bytes.fromhex(
            "e3 f4 4e 5d 5a 24 5a f4 32 d5 d2 f7 8e 72 57 b0 ba 7e f8 e3 6b 46 fa 3c ff ce 26 09 de 7c 12 c0"
        ),
    ),
}
_AUD154_COMPANION_REBINDS = {
    "scripts/live_stand.py": (
        bytes.fromhex(
            "c2 d8 95 9a 48 8c b7 7e 00 1a d3 b7 5a fb 7b f9 90 02 a9 1a 78 9c 67 a4 fa 47 70 ed 02 b7 7c 2c"
        ),
        bytes.fromhex(
            "31 24 56 fe 94 57 db e9 e9 a9 1e 9e 88 44 4c 9d 36 88 92 51 46 c1 dc a6 5c ec 90 de f3 72 1e d4"
        ),
    ),
    "frontend/package.json": (
        bytes.fromhex(
            "c6 37 a6 46 14 0b 98 25 17 00 67 f0 58 28 c3 77 84 c0 57 79 62 3d a7 f6 58 4d d5 ad 1d ef dd 56"
        ),
        bytes.fromhex(
            "4c 4b 8f e5 a0 b2 ac aa 2d ad 16 7f 4e 00 4c 34 cf df 10 78 c8 1b 4d 28 dd 0b 50 fe 06 73 1d f2"
        ),
    ),
}
_AUD154_PREVIOUS_POLICY_SHA256 = bytes.fromhex(
    "73 49 d8 d7 01 17 ef b4 e5 24 c2 30 df 62 21 b2 ae 41 10 b6 c7 09 81 bb 99 a3 78 76 09 df b6 0a"
)


_AUD154_SOURCE_INSERTIONS = {
    "frontend/package.json": (b" scripts/live-aud154-reporter.test.mjs",),
    "scripts/live_stand.py": (
        b"from scripts.aud154_receipt import project_case_records\n",
        b"    delivery_cases = project_case_records(stdout)\n",
        b'    for record in delivery_cases:\n        print(\n            "live E2E AUD154 " + json.dumps(record, separators=(",", ":")), flush=True\n        )\n',
    ),
}


# NOV12 chart pins: owner standing approval (2026-10-31) for one-to-one rebinds
# of existing digest identities. The Calico values blocks are inserted into these
# two chart files; the exact predecessor bytes are restored before the existing
# AUD-380 source pins are checked. No identity is added; the total stays 512.
_NOV12_CHART_REBINDS = {
    "charts/university-ecosystem/values.yaml": (
        23762,
        32742,
        bytes.fromhex(
            "11 22 e9 99 8c 45 14 6b 82 99 41 ef 13 75 bb 55 c1 a4 fd f7 07 3f 4c e4 d7 75 a1 09 3e 1c 6e 78"
        ),
        bytes.fromhex(
            "c3 da 7a a0 99 2e b6 0c 82 b2 53 b0 81 e7 41 1a ca 3e 4e 55 82 73 17 93 cd 22 de 7e 5e 07 eb d4"
        ),
    ),
    "charts/university-ecosystem/values.schema.json": (
        50597,
        70162,
        bytes.fromhex(
            "d3 d1 a1 74 36 cd 9b 13 6c b1 05 63 e1 69 d8 48 e8 85 ba 84 5e 76 95 ff 24 bb 44 38 ce 99 93 49"
        ),
        bytes.fromhex(
            "0f 65 6e 5a b4 be 92 51 3e 47 83 68 c0 ca c1 99 de d1 89 5e 3d 6b 40 60 49 c3 77 fc 73 d3 b6 12"
        ),
    ),
}


def _nov12_chart_historical_source_bytes(path: str, actual: bytes) -> bytes:
    rebind = _NOV12_CHART_REBINDS.get(path)
    if rebind is None:
        return actual
    prefix_length, previous_length, previous_sha, current_sha = rebind
    assert hashlib.sha256(actual).digest() == current_sha, (
        f"conditional disposition source file SHA-256 changed: {path}"
    )
    historical = (
        actual[:prefix_length]
        + actual[len(actual) - (previous_length - prefix_length) :]
    )
    assert hashlib.sha256(historical).digest() == previous_sha, (
        f"conditional disposition source file SHA-256 changed: {path}"
    )
    return historical


# STEP2 Go/companion rebind: the Semgrep row-13 companion digest for the workflow
# contract changes with the approved 1.26.4 -> 1.26.11 manifest pin, and the existing
# public-integrity identity is rebound one-to-one (owner standing approval 2026-10-31).
# The exact predecessor test and ledger bytes are restored before the existing pins
# are checked; no identity is added and the total stays 512.
_NOV13_COMPANION_CURRENT_SHA256 = bytes.fromhex(
    "e0 d2 df 72 3e a7 cb 3d 82 03 5d 18 a8 70 70 b3 89 4a e0 c9 f7 91 6c 51 58 c9 7c a3 e0 54 7e f5"
)
_NOV13_COMPANION_PREVIOUS_SHA256 = bytes.fromhex(
    "b6 88 0e 4f 27 06 40 dc 5b 1e fc a7 05 8e 48 84 86 f4 a6 6d 06 50 c5 6a 74 61 46 02 d9 dc 06 fd"
)
_NOV13_LEDGER_CURRENT_SHA256 = bytes.fromhex(
    "16 11 d6 e3 4f c8 7a 75 79 df 77 dd 66 cf f0 9f 55 af df ef 21 3a b7 e4 6a 81 4e 21 14 39 19 28"
)
_NOV13_LEDGER_PREVIOUS_SHA256 = bytes.fromhex(
    "50 05 3a 0f 31 7b 2e ee 4d 71 54 53 76 2a cf f3 f4 cb 17 11 da ec e1 5f a2 96 5d 2d e2 58 2e cf"
)
_NOV13_COMPANION_ROW = 505


# STEP5 loopback CSP exception: the Semgrep companion digest of
# frontend/scripts/server-csp.mjs and its existing public-integrity identity are
# rebound one-to-one (owner standing approval 2026-10-31). The predecessor source,
# ledger and policy bytes are restored before the existing pins are checked. Each
# source hunk must match exactly once and the reversal must reproduce the
# predecessor digest; no identity is added and the total stays 512.
_NOV13_LOOPBACK_SOURCE_CURRENT_SHA256 = bytes.fromhex(
    "e8 95 6f 34 9a ba 0b 03 44 26 44 e0 be 40 92 9c 75 22 45 5c 44 d2 7b bb d0 3f 61 ca 0a 1e 79 ce"
)
_NOV13_LOOPBACK_SOURCE_PREVIOUS_SHA256 = bytes.fromhex(
    "58 c5 e4 51 cf 68 e3 a0 91 14 0c 57 fa 32 e8 7f 13 0c 56 42 16 70 4a 0f 05 f0 83 05 2e 62 62 43"
)
_NOV13_LOOPBACK_LEDGER_CURRENT_SHA256 = bytes.fromhex(
    "d6 e2 43 e1 ad 53 db 87 b5 28 fd 7e 39 2a 21 7e 5c ae 84 69 59 e3 fd 87 a8 4c 8e 4a 4b 23 b8 9b"
)
_NOV13_LOOPBACK_CSP_ROW = 443
_NOV13_LOOPBACK_CSP_REVERSALS = (
    (
        r"""// Loopback literals only. Anchored, so "127.0.0.1.evil.com", "evil.com:127.0.0.1"
// and "[::1].evil.com" never match. Bare "::1" is accepted because it is the
// unambiguous IPv6 loopback spelling without a port.
const LOOPBACK_HOST_PATTERN =
  /^(?:(?:127\.0\.0\.1|localhost)(?::\d{1,5})?|\[::1\](?::\d{1,5})?|::1)$/iu

function isLoopbackHost(host) {
  return typeof host === "string" && LOOPBACK_HOST_PATTERN.test(host)
}

// Only an absent X-Forwarded-Proto or an exact "http" marks a request as plain
// HTTP. Anything else (https, lists, arrays, empty values) fails closed.
function isMarkedPlainHttp(forwardedProto) {
  if (forwardedProto === undefined || forwardedProto === null) return true
  return typeof forwardedProto === "string" && forwardedProto.trim().toLowerCase() === "http"
}

/**
 * Production sits behind Caddy TLS, so `upgrade-insecure-requests` stays for every
 * real host. It is omitted only for a plain-HTTP request addressed to a loopback
 * literal, which is the local preview / Playwright lane. WebKit otherwise upgrades
 * those loopback subresource requests to https and fails the TLS handshake.
 */
export function shouldUpgradeInsecureRequests({ host, forwardedProto } = {}) {
  return !(isLoopbackHost(host) && isMarkedPlainHttp(forwardedProto))
}

export function buildNodeCspHeaders(nonce, { upgradeInsecureRequests = true } = {}) {
""",
        r"""export function buildNodeCspHeaders(nonce) {
""",
    ),
    (
        r"""  if (typeof upgradeInsecureRequests !== "boolean") {
    throw new TypeError("upgradeInsecureRequests must be a boolean")
  }
""",
        r"""""",
    ),
    (
        r"""  const enforcingPolicy = policyDirectives
    .filter((directive) => upgradeInsecureRequests || directive !== "upgrade-insecure-requests")
    .join("; ")
""",
        r"""  const enforcingPolicy = policyDirectives.join("; ")
""",
    ),
    (
        r"""export function applyNodeCspToHtmlResponse(response, nonce, options = {}) {
""",
        r"""export function applyNodeCspToHtmlResponse(response, nonce) {
""",
    ),
    (
        r"""  for (const [name, value] of Object.entries(buildNodeCspHeaders(nonce, options))) {
""",
        r"""  for (const [name, value] of Object.entries(buildNodeCspHeaders(nonce))) {
""",
    ),
)


def _nov13_loopback_csp_historical_source_bytes(path: str, actual: bytes) -> bytes:
    actual = _nov13_trivy_workflow_source_bytes(path, actual)
    if path == "frontend/scripts/server-csp.mjs":
        assert (
            hashlib.sha256(actual).digest() == _NOV13_LOOPBACK_SOURCE_CURRENT_SHA256
        ), f"conditional disposition source file SHA-256 changed: {path}"
        historical = actual
        for current, previous in _NOV13_LOOPBACK_CSP_REVERSALS:
            current_bytes = current.encode("utf-8")
            assert historical.count(current_bytes) == 1, (
                f"conditional disposition source file SHA-256 changed: {path}"
            )
            historical = historical.replace(current_bytes, previous.encode("utf-8"), 1)
        assert (
            hashlib.sha256(historical).digest()
            == _NOV13_LOOPBACK_SOURCE_PREVIOUS_SHA256
        ), f"conditional disposition source file SHA-256 changed: {path}"
        return historical
    if path == "quality/semgrep-dispositions.json":
        assert (
            hashlib.sha256(actual).digest() == _NOV13_LOOPBACK_LEDGER_CURRENT_SHA256
        ), f"conditional disposition source file SHA-256 changed: {path}"
        current = _NOV13_LOOPBACK_SOURCE_CURRENT_SHA256.hex().encode("ascii")
        assert actual.count(current) == 1
        historical = actual.replace(
            current, _NOV13_LOOPBACK_SOURCE_PREVIOUS_SHA256.hex().encode("ascii"), 1
        )
        assert (
            hashlib.sha256(historical).digest() == _NOV13_MFA_LEDGER_CURRENT_SHA256
        ), f"conditional disposition source file SHA-256 changed: {path}"
        return historical
    return actual


def _nov13_loopback_csp_historical_policy(policy: dict[str, Any]) -> dict[str, Any]:
    # The Trivy predecessor digest is the innermost projection: every later
    # historical layer in this chain hashes the restored predecessor policy.
    restored = _nov13_trivy_historical_policy(policy)
    records = restored["records"]
    assert len(records) == 512, "live disposition count changed"
    row = records[_NOV13_LOOPBACK_CSP_ROW]
    identity = row["identity"]
    assert identity["path"] == "quality/semgrep-dispositions.json"
    assert identity["type"] == "Hex High Entropy String"
    assert row["category"] == "public_integrity_digest"
    assert (
        bytes(identity["hashed_secret_bytes"])
        == hashlib.sha1(
            _NOV13_LOOPBACK_SOURCE_CURRENT_SHA256.hex().encode("ascii"),
            usedforsecurity=False,
        ).digest()
    ), "live disposition loopback CSP identity changed"
    identity["hashed_secret_bytes"] = list(
        hashlib.sha1(
            _NOV13_LOOPBACK_SOURCE_PREVIOUS_SHA256.hex().encode("ascii"),
            usedforsecurity=False,
        ).digest()
    )
    return restored


def test_nov13_loopback_csp_rebind_preserves_exact_predecessor() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "frontend/scripts/server-csp.mjs").read_bytes()
    ledger_bytes = (root / "quality/semgrep-dispositions.json").read_bytes()
    ledger = json.loads(ledger_bytes)
    companions = [
        item["sha256"]
        for item in ledger["dispositions"][14]["companions"]
        if item["path"] == "frontend/scripts/server-csp.mjs"
    ]
    assert companions == [hashlib.sha256(source).hexdigest()]
    historical = _nov13_loopback_csp_historical_source_bytes(
        "frontend/scripts/server-csp.mjs", source
    )
    assert hashlib.sha256(historical).digest() == _NOV13_LOOPBACK_SOURCE_PREVIOUS_SHA256
    assert b"upgradeInsecureRequests" not in historical
    restored_ledger = _nov13_loopback_csp_historical_source_bytes(
        "quality/semgrep-dispositions.json", ledger_bytes
    )
    assert hashlib.sha256(restored_ledger).digest() == _NOV13_MFA_LEDGER_CURRENT_SHA256
    policy = json.loads(
        (root / "quality/security-false-positive-dispositions.json").read_bytes()
    )
    restored_policy = _nov13_loopback_csp_historical_policy(policy)
    assert len(restored_policy["records"]) == 512
    assert (
        bytes(
            restored_policy["records"][_NOV13_LOOPBACK_CSP_ROW]["identity"][
                "hashed_secret_bytes"
            ]
        )
        == hashlib.sha1(
            _NOV13_LOOPBACK_SOURCE_PREVIOUS_SHA256.hex().encode("ascii"),
            usedforsecurity=False,
        ).digest()
    )


@pytest.mark.parametrize("mutation", ["source", "ledger", "policy"])
def test_nov13_loopback_csp_projection_rejects_drift(mutation: str) -> None:
    root = Path(__file__).resolve().parents[1]
    if mutation == "source":
        actual = (root / "frontend/scripts/server-csp.mjs").read_bytes() + b"\n"
        with pytest.raises(AssertionError, match="conditional disposition source"):
            _nov13_loopback_csp_historical_source_bytes(
                "frontend/scripts/server-csp.mjs", actual
            )
    elif mutation == "ledger":
        actual = (root / "quality/semgrep-dispositions.json").read_bytes() + b"\n"
        with pytest.raises(AssertionError, match="conditional disposition source"):
            _nov13_loopback_csp_historical_source_bytes(
                "quality/semgrep-dispositions.json", actual
            )
    else:
        policy = json.loads(
            (root / "quality/security-false-positive-dispositions.json").read_bytes()
        )
        policy["records"][_NOV13_LOOPBACK_CSP_ROW]["identity"]["hashed_secret_bytes"][
            0
        ] ^= 1
        with pytest.raises(AssertionError, match="loopback CSP identity changed"):
            _nov13_loopback_csp_historical_policy(policy)


# STEP4 retired dead mfa_enabled flag: the Semgrep companion digest of
# app/core/config/mixins/mfa_settings.py and its existing public-integrity identity
# are rebound one-to-one (owner standing approval 2026-10-31). The exact predecessor
# source, ledger and policy bytes are restored before the existing pins are checked;
# no identity is added and the total stays 512.
_NOV13_MFA_CURRENT_SOURCE_SHA256 = bytes.fromhex(
    "f2 84 ad a0 ed 1a ad 60 71 7b fe 34 ce 12 40 bd ab 52 9a 6d dd 9d 8a 7b df fe 14 10 7d 94 43 e4"
)
_NOV13_MFA_PREVIOUS_SOURCE_SHA256 = bytes.fromhex(
    "c6 61 0b 73 d9 7d 6c db 87 f3 71 ac 02 85 05 03 28 eb 1e 86 0d 79 4d 14 01 d3 ad 26 70 a6 d6 ce"
)
_NOV13_MFA_LEDGER_CURRENT_SHA256 = bytes.fromhex(
    "51 c9 7a 40 87 f8 be e7 fd 72 88 19 d3 7b 95 be 7f 16 84 6f d1 be e3 72 65 51 46 86 9a 73 a2 a5"
)
_NOV13_MFA_LEDGER_PREVIOUS_SHA256 = bytes.fromhex(
    "16 11 d6 e3 4f c8 7a 75 79 df 77 dd 66 cf f0 9f 55 af df ef 21 3a b7 e4 6a 81 4e 21 14 39 19 28"
)
_NOV13_MFA_COMPANION_ROW = 433
_NOV13_MFA_DEAD_FLAG_LINE = b"    mfa_enabled: bool = False\n"
_NOV13_MFA_ANCHOR_LINE = b"    mfa_default_method: str | None = None\n"


def _nov13_mfa_settings_historical_source_bytes(path: str, actual: bytes) -> bytes:
    actual = _nov13_loopback_csp_historical_source_bytes(path, actual)
    if path == "app/core/config/mixins/mfa_settings.py":
        assert hashlib.sha256(actual).digest() == _NOV13_MFA_CURRENT_SOURCE_SHA256, (
            f"conditional disposition source file SHA-256 changed: {path}"
        )
        assert actual.count(_NOV13_MFA_ANCHOR_LINE) == 1
        historical = actual.replace(
            _NOV13_MFA_ANCHOR_LINE,
            _NOV13_MFA_DEAD_FLAG_LINE + _NOV13_MFA_ANCHOR_LINE,
            1,
        )
        assert (
            hashlib.sha256(historical).digest() == _NOV13_MFA_PREVIOUS_SOURCE_SHA256
        ), f"conditional disposition source file SHA-256 changed: {path}"
        return historical
    if path == "quality/semgrep-dispositions.json":
        assert hashlib.sha256(actual).digest() == _NOV13_MFA_LEDGER_CURRENT_SHA256, (
            f"conditional disposition source file SHA-256 changed: {path}"
        )
        current = _NOV13_MFA_CURRENT_SOURCE_SHA256.hex().encode("ascii")
        assert actual.count(current) == 1
        historical = actual.replace(
            current, _NOV13_MFA_PREVIOUS_SOURCE_SHA256.hex().encode("ascii"), 1
        )
        assert (
            hashlib.sha256(historical).digest() == _NOV13_MFA_LEDGER_PREVIOUS_SHA256
        ), f"conditional disposition source file SHA-256 changed: {path}"
        return historical
    return actual


def _nov13_mfa_settings_historical_policy(policy: dict[str, Any]) -> dict[str, Any]:
    restored = _nov13_loopback_csp_historical_policy(policy)
    records = restored["records"]
    assert len(records) == 512, "live disposition count changed"
    identity = records[_NOV13_MFA_COMPANION_ROW]["identity"]
    assert identity["path"] == "quality/semgrep-dispositions.json"
    assert identity["type"] == "Hex High Entropy String"
    assert (
        bytes(identity["hashed_secret_bytes"])
        == hashlib.sha1(
            _NOV13_MFA_CURRENT_SOURCE_SHA256.hex().encode("ascii"),
            usedforsecurity=False,
        ).digest()
    ), "live disposition mfa companion identity changed"
    identity["hashed_secret_bytes"] = list(
        hashlib.sha1(
            _NOV13_MFA_PREVIOUS_SOURCE_SHA256.hex().encode("ascii"),
            usedforsecurity=False,
        ).digest()
    )
    return restored


def test_nov13_mfa_settings_rebind_preserves_exact_predecessor() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "app/core/config/mixins/mfa_settings.py").read_bytes()
    ledger = json.loads((root / "quality/semgrep-dispositions.json").read_bytes())
    companions = [
        item["sha256"]
        for item in ledger["dispositions"][13]["companions"]
        if item["path"] == "app/core/config/mixins/mfa_settings.py"
    ]
    assert companions == [hashlib.sha256(source).hexdigest()]
    historical = _nov13_mfa_settings_historical_source_bytes(
        "app/core/config/mixins/mfa_settings.py", source
    )
    assert b"mfa_enabled" not in source
    assert historical.count(_NOV13_MFA_DEAD_FLAG_LINE) == 1
    restored_ledger = _nov13_mfa_settings_historical_source_bytes(
        "quality/semgrep-dispositions.json",
        (root / "quality/semgrep-dispositions.json").read_bytes(),
    )
    assert hashlib.sha256(restored_ledger).digest() == _NOV13_MFA_LEDGER_PREVIOUS_SHA256
    policy = json.loads(
        (root / "quality/security-false-positive-dispositions.json").read_bytes()
    )
    restored_policy = _nov13_mfa_settings_historical_policy(policy)
    assert len(restored_policy["records"]) == 512
    assert (
        bytes(
            restored_policy["records"][_NOV13_MFA_COMPANION_ROW]["identity"][
                "hashed_secret_bytes"
            ]
        )
        == hashlib.sha1(
            _NOV13_MFA_PREVIOUS_SOURCE_SHA256.hex().encode("ascii"),
            usedforsecurity=False,
        ).digest()
    )


@pytest.mark.parametrize("mutation", ["source", "ledger", "policy"])
def test_nov13_mfa_settings_projection_rejects_drift(mutation: str) -> None:
    root = Path(__file__).resolve().parents[1]
    if mutation == "source":
        actual = (root / "app/core/config/mixins/mfa_settings.py").read_bytes() + b"\n"
        with pytest.raises(AssertionError, match="conditional disposition source"):
            _nov13_mfa_settings_historical_source_bytes(
                "app/core/config/mixins/mfa_settings.py", actual
            )
    elif mutation == "ledger":
        actual = (root / "quality/semgrep-dispositions.json").read_bytes() + b"\n"
        with pytest.raises(AssertionError, match="conditional disposition source"):
            _nov13_mfa_settings_historical_source_bytes(
                "quality/semgrep-dispositions.json", actual
            )
    else:
        policy = json.loads(
            (root / "quality/security-false-positive-dispositions.json").read_bytes()
        )
        policy["records"][_NOV13_MFA_COMPANION_ROW]["identity"]["hashed_secret_bytes"][
            0
        ] ^= 1
        with pytest.raises(AssertionError, match="mfa companion identity changed"):
            _nov13_mfa_settings_historical_policy(policy)


def _nov13_go_companion_historical_source_bytes(path: str, actual: bytes) -> bytes:
    actual = _nov13_mfa_settings_historical_source_bytes(path, actual)
    if path == "tests/test_quality_workflow_contract.py":
        assert hashlib.sha256(actual).digest() == _NOV13_COMPANION_CURRENT_SHA256, (
            f"conditional disposition source file SHA-256 changed: {path}"
        )
        current_line = b'    manifest_expected_version = "1.26.11"\n'
        assert actual.count(current_line) == 1
        historical = actual.replace(
            current_line, b'    manifest_expected_version = "1.26.4"\n', 1
        )
        assert (
            hashlib.sha256(historical).digest() == _NOV13_COMPANION_PREVIOUS_SHA256
        ), f"conditional disposition source file SHA-256 changed: {path}"
        return historical
    if path == "quality/semgrep-dispositions.json":
        assert hashlib.sha256(actual).digest() == _NOV13_LEDGER_CURRENT_SHA256, (
            f"conditional disposition source file SHA-256 changed: {path}"
        )
        current = _NOV13_COMPANION_CURRENT_SHA256.hex().encode("ascii")
        assert actual.count(current) == 1
        historical = actual.replace(
            current,
            _NOV13_COMPANION_PREVIOUS_SHA256.hex().encode("ascii"),
            1,
        )
        assert hashlib.sha256(historical).digest() == _NOV13_LEDGER_PREVIOUS_SHA256, (
            f"conditional disposition source file SHA-256 changed: {path}"
        )
        return historical
    return actual


def _nov13_go_companion_historical_policy(policy: dict[str, Any]) -> dict[str, Any]:
    restored = _nov13_mfa_settings_historical_policy(policy)
    records = restored["records"]
    assert len(records) == 512, "live disposition count changed"
    identity = records[_NOV13_COMPANION_ROW]["identity"]
    assert identity["path"] == "quality/semgrep-dispositions.json"
    assert identity["type"] == "Hex High Entropy String"
    assert (
        bytes(identity["hashed_secret_bytes"])
        == hashlib.sha1(
            _NOV13_COMPANION_CURRENT_SHA256.hex().encode("ascii"), usedforsecurity=False
        ).digest()
    ), "live disposition companion identity changed"
    identity["hashed_secret_bytes"] = list(
        hashlib.sha1(
            _NOV13_COMPANION_PREVIOUS_SHA256.hex().encode("ascii"),
            usedforsecurity=False,
        ).digest()
    )
    return restored


def _aud154_historical_source_bytes(path: str, actual: bytes) -> bytes:
    actual = _nov12_chart_historical_source_bytes(path, actual)
    actual = _aud375_historical_source_bytes(path, actual)
    if path not in _AUD154_SOURCE_PINS:
        return actual
    previous_sha, current_sha = _AUD154_SOURCE_PINS[path]
    assert hashlib.sha256(actual).digest() == current_sha, (
        f"conditional disposition source file SHA-256 changed: {path}"
    )
    if path == "quality/semgrep-dispositions.json":
        historical = actual
        for previous, current in _AUD154_COMPANION_REBINDS.values():
            assert historical.count(current.hex().encode("ascii")) == 1
            historical = historical.replace(
                current.hex().encode("ascii"), previous.hex().encode("ascii"), 1
            )
    else:
        historical = actual
        for inserted in _AUD154_SOURCE_INSERTIONS[path]:
            assert historical.count(inserted) == 1
            historical = historical.replace(inserted, b"", 1)
    assert hashlib.sha256(historical).digest() == previous_sha
    return historical


def _aud154_historical_policy(policy: dict[str, Any]) -> dict[str, Any]:
    restored = _aud375_historical_policy(policy)
    assert len(restored["records"]) == 512, "live disposition count changed"
    replacements = {
        hashlib.sha1(
            current.hex().encode("ascii"), usedforsecurity=False
        ).digest(): hashlib.sha1(
            previous.hex().encode("ascii"), usedforsecurity=False
        ).digest()
        for previous, current in _AUD154_COMPANION_REBINDS.values()
    }
    changed = []
    for index, record in enumerate(restored["records"]):
        identity = record["identity"]
        digest = bytes(identity["hashed_secret_bytes"])
        if (
            identity["path"] != "quality/semgrep-dispositions.json"
            or digest not in replacements
        ):
            continue
        assert identity["type"] == "Hex High Entropy String"
        assert record["category"] == "public_integrity_digest"
        identity["hashed_secret_bytes"] = list(replacements[digest])
        changed.append(index)
    assert changed == [451, 495], "live disposition AUD154 rebind set changed"
    # Predecessor digests cover the 511 records before the Calico identity.
    predecessor = {**restored, "records": restored["records"][:511]}
    assert hashlib.sha256(_nov9_historical_506_policy_bytes(predecessor)).digest() == (
        _AUD154_PREVIOUS_POLICY_SHA256
    ), "live disposition predecessor or approval metadata changed"
    return restored


def test_aud154_companion_rebinds_preserve_exact_predecessor() -> None:
    root = Path(__file__).resolve().parents[1]
    ledger = json.loads((root / "quality/semgrep-dispositions.json").read_bytes())
    for index, path in ((6, "scripts/live_stand.py"), (14, "frontend/package.json")):
        companions = ledger["dispositions"][index]["companions"]
        bound = [item["sha256"] for item in companions if item["path"] == path]
        assert bound == [hashlib.sha256((root / path).read_bytes()).hexdigest()]
    for path in _AUD154_SOURCE_PINS:
        _aud154_historical_source_bytes(path, (root / path).read_bytes())
    _aud154_historical_policy(
        json.loads(
            (root / "quality/security-false-positive-dispositions.json").read_bytes()
        )
    )


@pytest.mark.parametrize("path", tuple(_AUD154_SOURCE_PINS))
def test_aud154_source_projection_rejects_changes(path: str) -> None:
    root = Path(__file__).resolve().parents[1]
    with pytest.raises(AssertionError, match="source file SHA-256 changed"):
        _aud154_historical_source_bytes(path, (root / path).read_bytes() + b"\n")


@pytest.mark.parametrize("index", [451, 495])
@pytest.mark.parametrize(
    "field", ["digest", "path", "type", "category", "expiry", "evidence"]
)
def test_aud154_policy_projection_rejects_scope_drift(index: int, field: str) -> None:
    root = Path(__file__).resolve().parents[1]
    policy = json.loads(
        (root / "quality/security-false-positive-dispositions.json").read_bytes()
    )
    row = policy["records"][index]
    if field == "digest":
        row["identity"]["hashed_secret_bytes"][0] ^= 1
    elif field in {"path", "type"}:
        row["identity"][field] += " changed"
    else:
        key = "expires_on" if field == "expiry" else field
        row[key] += " changed"
    with pytest.raises(AssertionError):
        _aud154_historical_policy(policy)


# AUD375 adds only the exact PR-wide coverage and test prefix. Keep AUD154 pins
# immutable and verify this one-to-one transition before its historical inverse.
_AUD375_PACKAGE_SHA256 = bytes.fromhex(
    "fc 9d 71 db 42 9c fc 88 dc 6d b3 1a b9 9d 73 a1 5e 3d 0f 4e 55 b4 fe 6a c5 23 68 48 d1 7e cf c2"
)
_AUD375_LEDGER_SHA256 = bytes.fromhex(
    "d2 a4 ea c7 1c c9 0a 94 cc de 27 35 cf 7e c1 24 1a 90 8c 81 bf 48 3c b1 3a 9a 9e 0a 61 66 fb 10"
)
_AUD375_PREVIOUS_POLICY_SHA256 = bytes.fromhex(
    "88 d8 85 cc 45 07 1c 93 bd ab 2a f3 80 f1 0b 90 c1 b3 c0 2f 88 59 25 ec 9d ca bd 77 b3 a6 a3 4a"
)
_AUD375_PACKAGE_PREFIX = (
    b"node --experimental-test-coverage"
    b" --test-coverage-include=scripts/aud375-evidence.mjs"
    b" --test-coverage-lines=100 --test-coverage-branches=100"
    b" --test-coverage-functions=100 --test scripts/aud375-evidence.test.mjs"
    b" && node --test scripts/aud375-coverage.contract.test.mjs"
    b" scripts/playwright-report-preservation.test.mjs"
)


def _aud375_historical_source_bytes(path: str, actual: bytes) -> bytes:
    actual = _nov12_csp_historical_source_bytes(path, actual)
    if path not in {"frontend/package.json", "quality/semgrep-dispositions.json"}:
        return actual
    current_sha = (
        _AUD375_PACKAGE_SHA256
        if path == "frontend/package.json"
        else _AUD375_LEDGER_SHA256
    )
    assert hashlib.sha256(actual).digest() == current_sha, (
        f"conditional disposition source file SHA-256 changed: {path}"
    )
    if path == "frontend/package.json":
        anchor = b'"test:wasm": "' + _AUD375_PACKAGE_PREFIX
        assert actual.count(anchor) == 1
        historical = actual.replace(anchor, b'"test:wasm": "node --test', 1)
    else:
        current = _AUD375_PACKAGE_SHA256.hex().encode("ascii")
        previous = _AUD154_SOURCE_PINS["frontend/package.json"][1]
        assert actual.count(current) == 1
        historical = actual.replace(current, previous.hex().encode("ascii"), 1)
    assert hashlib.sha256(historical).digest() == _AUD154_SOURCE_PINS[path][1]
    return historical


def _aud375_historical_policy(policy: dict[str, Any]) -> dict[str, Any]:
    restored = _nov12_csp_historical_policy(policy)
    assert len(restored["records"]) == 512, "live disposition count changed"
    row = restored["records"][451]
    identity = row["identity"]
    assert identity["path"] == "quality/semgrep-dispositions.json"
    assert identity["type"] == "Hex High Entropy String"
    assert row["category"] == "public_integrity_digest"
    assert (
        bytes(identity["hashed_secret_bytes"])
        == hashlib.sha1(
            _AUD375_PACKAGE_SHA256.hex().encode("ascii"), usedforsecurity=False
        ).digest()
    )
    identity["hashed_secret_bytes"] = list(
        hashlib.sha1(
            _AUD154_SOURCE_PINS["frontend/package.json"][1].hex().encode("ascii"),
            usedforsecurity=False,
        ).digest()
    )
    # Predecessor digests cover the 511 records before the Calico identity.
    predecessor = {**restored, "records": restored["records"][:511]}
    assert hashlib.sha256(_nov9_historical_506_policy_bytes(predecessor)).digest() == (
        _AUD375_PREVIOUS_POLICY_SHA256
    ), "live disposition predecessor or approval metadata changed"
    return restored


def test_aud375_package_projection_preserves_exact_predecessor() -> None:
    root = Path(__file__).resolve().parents[1]
    actual = (root / "frontend/package.json").read_bytes()
    historical = _aud375_historical_source_bytes("frontend/package.json", actual)
    assert actual.count(_AUD375_PACKAGE_PREFIX) == 1
    assert actual == historical.replace(
        b'"test:wasm": "node --test',
        b'"test:wasm": "' + _AUD375_PACKAGE_PREFIX,
        1,
    )
    assert (
        hashlib.sha256(historical).digest()
        == _AUD154_SOURCE_PINS["frontend/package.json"][1]
    )


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "reordered", "unrelated"])
def test_aud375_package_projection_rejects_command_drift(mutation: str) -> None:
    root = Path(__file__).resolve().parents[1]
    actual = (root / "frontend/package.json").read_bytes()
    insertion = _AUD375_PACKAGE_PREFIX
    if mutation == "missing":
        actual = actual.replace(insertion, b"", 1)
    elif mutation == "duplicate":
        actual = actual.replace(insertion, insertion * 2, 1)
    elif mutation == "reordered":
        actual = actual.replace(insertion, b" ".join(reversed(insertion.split())), 1)
    else:
        actual += b"\n"
    with pytest.raises(AssertionError, match="source file SHA-256 changed"):
        _aud375_historical_source_bytes("frontend/package.json", actual)


@pytest.mark.parametrize("index", [0, 451, 495, 510])
@pytest.mark.parametrize(
    "field", ["owner", "expires_on", "evidence", "approval_status", "reviewed_on"]
)
def test_aud375_policy_projection_rejects_metadata_drift(
    index: int, field: str
) -> None:
    root = Path(__file__).resolve().parents[1]
    policy = json.loads(
        (root / "quality/security-false-positive-dispositions.json").read_bytes()
    )
    policy["records"][index][field] += " changed"
    with pytest.raises(AssertionError, match="approval metadata changed"):
        _aud375_historical_policy(policy)


# NOV12 adds only the owner-approved map tile origin to the Node CSP. The
# SafeHtml Semgrep companion and its public digest identity are rebound
# one-to-one; restore the exact predecessor before the AUD375 inverse.
_NOV12_CSP_SOURCE_SHA256 = bytes.fromhex(
    "58 c5 e4 51 cf 68 e3 a0 91 14 0c 57 fa 32 e8 7f 13 0c 56 42 16 70 4a 0f 05 f0 83 05 2e 62 62 43"
)
_NOV12_CSP_PREVIOUS_SOURCE_SHA256 = bytes.fromhex(
    "c2 15 62 21 06 8a a4 0b b1 4b be a7 c8 0b 4c 8e e7 c0 e3 b4 f2 65 0a 34 95 42 63 c4 93 1e 81 c4"
)
_NOV12_LEDGER_SHA256 = bytes.fromhex(
    "50 05 3a 0f 31 7b 2e ee 4d 71 54 53 76 2a cf f3 f4 cb 17 11 da ec e1 5f a2 96 5d 2d e2 58 2e cf"
)
_NOV12_PREVIOUS_POLICY_SHA256 = bytes.fromhex(
    "f2 d9 52 c8 dd 89 3e 25 c9 4b 9c 43 1d d2 ff ac d1 b9 17 e9 cc 2b 93 1f 99 a9 ef 40 e3 55 d7 88"
)
_NOV12_CSP_INSERTION = b'  "https://tiles.openfreemap.org",\n'
_NOV12_CSP_ROW = 443


def _nov12_csp_historical_source_bytes(path: str, actual: bytes) -> bytes:
    actual = _nov13_go_companion_historical_source_bytes(path, actual)
    if path == "frontend/scripts/server-csp.mjs":
        assert hashlib.sha256(actual).digest() == _NOV12_CSP_SOURCE_SHA256, (
            f"conditional disposition source file SHA-256 changed: {path}"
        )
        assert actual.count(_NOV12_CSP_INSERTION) == 1
        historical = actual.replace(_NOV12_CSP_INSERTION, b"", 1)
        assert hashlib.sha256(historical).digest() == _NOV12_CSP_PREVIOUS_SOURCE_SHA256
        return historical
    if path != "quality/semgrep-dispositions.json":
        return actual
    assert hashlib.sha256(actual).digest() == _NOV12_LEDGER_SHA256, (
        f"conditional disposition source file SHA-256 changed: {path}"
    )
    current = _NOV12_CSP_SOURCE_SHA256.hex().encode("ascii")
    assert actual.count(current) == 1
    historical = actual.replace(
        current, _NOV12_CSP_PREVIOUS_SOURCE_SHA256.hex().encode("ascii"), 1
    )
    assert hashlib.sha256(historical).digest() == _AUD375_LEDGER_SHA256
    return historical


def _nov12_csp_historical_policy(policy: dict[str, Any]) -> dict[str, Any]:
    restored = _nov13_go_companion_historical_policy(policy)
    assert len(restored["records"]) == 512, "live disposition count changed"
    row = restored["records"][_NOV12_CSP_ROW]
    identity = row["identity"]
    assert identity["path"] == "quality/semgrep-dispositions.json"
    assert identity["type"] == "Hex High Entropy String"
    assert row["category"] == "public_integrity_digest"
    assert (
        bytes(identity["hashed_secret_bytes"])
        == hashlib.sha1(
            _NOV12_CSP_SOURCE_SHA256.hex().encode("ascii"), usedforsecurity=False
        ).digest()
    )
    identity["hashed_secret_bytes"] = list(
        hashlib.sha1(
            _NOV12_CSP_PREVIOUS_SOURCE_SHA256.hex().encode("ascii"),
            usedforsecurity=False,
        ).digest()
    )
    # The predecessor digest covers the 511 records before the Calico identity.
    predecessor = {**restored, "records": restored["records"][:511]}
    assert hashlib.sha256(_nov9_historical_506_policy_bytes(predecessor)).digest() == (
        _NOV12_PREVIOUS_POLICY_SHA256
    ), "live disposition predecessor or approval metadata changed"
    return restored


def test_nov12_map_csp_rebind_preserves_exact_predecessor() -> None:
    root = Path(__file__).resolve().parents[1]
    ledger = json.loads((root / "quality/semgrep-dispositions.json").read_bytes())
    companions = ledger["dispositions"][14]["companions"]
    bound = [
        item["sha256"]
        for item in companions
        if item["path"] == "frontend/scripts/server-csp.mjs"
    ]
    source = (root / "frontend/scripts/server-csp.mjs").read_bytes()
    assert bound == [hashlib.sha256(source).hexdigest()]
    historical = _nov12_csp_historical_source_bytes(
        "frontend/scripts/server-csp.mjs", source
    )
    assert _nov13_loopback_csp_historical_source_bytes(
        "frontend/scripts/server-csp.mjs", source
    ) == historical.replace(
        b'  "https://fcmregistrations.googleapis.com",\n',
        b'  "https://fcmregistrations.googleapis.com",\n' + _NOV12_CSP_INSERTION,
        1,
    )
    _nov12_csp_historical_source_bytes(
        "quality/semgrep-dispositions.json",
        (root / "quality/semgrep-dispositions.json").read_bytes(),
    )
    _nov12_csp_historical_policy(
        json.loads(
            (root / "quality/security-false-positive-dispositions.json").read_bytes()
        )
    )


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "unrelated"])
def test_nov12_map_csp_projection_rejects_source_drift(mutation: str) -> None:
    root = Path(__file__).resolve().parents[1]
    actual = (root / "frontend/scripts/server-csp.mjs").read_bytes()
    if mutation == "missing":
        actual = actual.replace(_NOV12_CSP_INSERTION, b"", 1)
    elif mutation == "duplicate":
        actual = actual.replace(_NOV12_CSP_INSERTION, _NOV12_CSP_INSERTION * 2, 1)
    else:
        actual += b"\n"
    with pytest.raises(AssertionError, match="source file SHA-256 changed"):
        _nov12_csp_historical_source_bytes("frontend/scripts/server-csp.mjs", actual)


@pytest.mark.parametrize("field", ["digest", "path", "type", "category", "evidence"])
def test_nov12_map_csp_policy_projection_rejects_scope_drift(field: str) -> None:
    root = Path(__file__).resolve().parents[1]
    policy = json.loads(
        (root / "quality/security-false-positive-dispositions.json").read_bytes()
    )
    row = policy["records"][_NOV12_CSP_ROW]
    if field == "digest":
        row["identity"]["hashed_secret_bytes"][0] ^= 1
    elif field in {"path", "type"}:
        row["identity"][field] += " changed"
    else:
        row[field] += " changed"
    with pytest.raises(AssertionError):
        _nov12_csp_historical_policy(policy)


# Owner-approved 2026-11-12 Calico manifest checksum identity. The live document
# appends it after the Go and ZAP identities; the 511 prior records are preserved.
_NOV12_CALICO_PRE_POLICY_SHA256 = bytes.fromhex(
    "06 c6 fd da bf 3a ba ca c8 9f 4d 17 64 69 87 07 c9 4e f9 85 e8 11 e2 38 a6 e5 dc bc 0a 04 27 6c"
)
_NOV12_CALICO_SCANNER_DIGEST = bytes.fromhex(
    "17 79 ac 26 87 8e 03 4c 7e e1 05 42 f3 d7 e2 e4 96 c6 b4 d9"
)
_NOV12_CALICO_SHA256_PATTERN = re.compile(r'readonly CALICO_SHA256="([0-9a-f]{64})"')
_NOV12_CALICO_APPROVED_RECORD = {
    "approval_status": "approved",
    "category": "public_integrity_digest",
    "evidence": (
        "Official Calico v3.30.3 manifest SHA-256 pin at "
        "scripts/k8s/networkpolicy_runtime_proof.sh:34 for "
        "https://raw.githubusercontent.com/projectcalico/calico/v3.30.3/manifests/calico.yaml; "
        "computed from that exact file because the upstream project publishes no checksum; "
        "owner approved this exact public integrity identity on 2026-11-12; "
        "not credential material."
    ),
    "expires_on": "2027-01-10",
    "identity": {
        "hashed_secret_bytes": list(_NOV12_CALICO_SCANNER_DIGEST),
        "path": "scripts/k8s/networkpolicy_runtime_proof.sh",
        "type": "Hex High Entropy String",
    },
    "owner": "egorribun",
    "reviewed_on": "2026-11-12",
}


def test_nov12_calico_preserves_published_policy_and_source_identity() -> None:
    root = Path(__file__).resolve().parents[1]
    policy = json.loads(
        (root / "quality/security-false-positive-dispositions.json").read_bytes()
    )
    _nov11_historical_509_from_live_policy(policy)
    restored_policy = _nov13_go_companion_historical_policy(policy)
    previous = {**restored_policy, "records": restored_policy["records"][:511]}
    assert (
        hashlib.sha256(_nov9_historical_506_policy_bytes(previous)).digest()
        == _NOV12_CALICO_PRE_POLICY_SHA256
    )
    assert policy["records"][511] == _NOV12_CALICO_APPROVED_RECORD
    proof = (
        (root / "scripts/k8s/networkpolicy_runtime_proof.sh")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    match = _NOV12_CALICO_SHA256_PATTERN.fullmatch(proof[33])
    assert match is not None, "Calico checksum must stay on proof line 34"
    digest = match.group(1)
    assert (
        hashlib.sha1(digest.encode("ascii"), usedforsecurity=False).digest()
        == _NOV12_CALICO_SCANNER_DIGEST
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "path",
        "digest",
        "type",
        "category",
        "owner",
        "review",
        "expiry",
        "evidence",
        "zap_record",
    ],
)
def test_nov12_calico_projection_rejects_scope_drift(mutation: str) -> None:
    root = Path(__file__).resolve().parents[1]
    policy = json.loads(
        (root / "quality/security-false-positive-dispositions.json").read_bytes()
    )
    record = policy["records"][511]
    if mutation == "path":
        record["identity"]["path"] = "scripts/k8s/other.sh"
    elif mutation == "digest":
        record["identity"]["hashed_secret_bytes"][0] ^= 1
    elif mutation == "type":
        record["identity"]["type"] = "Secret Keyword"
    elif mutation == "category":
        record["category"] = "synthetic_test_fixture"
    elif mutation == "owner":
        record["owner"] = "someone_else"
    elif mutation == "review":
        record["reviewed_on"] = "2026-11-11"
    elif mutation == "expiry":
        record["expires_on"] = "2027-01-11"
    elif mutation == "evidence":
        record["evidence"] += " changed"
    else:
        policy["records"][510]["expires_on"] = "2027-01-11"
    with pytest.raises(AssertionError, match="live disposition"):
        _nov11_historical_509_from_live_policy(policy)


def test_nov12_calico_approval_has_finite_review_and_expiry() -> None:
    document = _disposition_document(copy.deepcopy(_NOV12_CALICO_APPROVED_RECORD))
    expected = {
        verifier.FindingIdentity(
            "scripts/k8s/networkpolicy_runtime_proof.sh",
            "Hex High Entropy String",
            _NOV12_CALICO_SCANNER_DIGEST.hex(),
            34,
        )
    }
    for today in (verifier.date(2026, 11, 12), verifier.date(2027, 1, 10)):
        assert _nov13_verify_dispositions(document, today=today) == expected
    for today in (verifier.date(2026, 11, 11), verifier.date(2027, 1, 11)):
        with pytest.raises(verifier.BaselineArtifactError, match="date range"):
            _nov13_verify_dispositions(document, today=today)


def test_nov13_trivy_digest_rebind_preserves_exact_predecessor() -> None:
    root = Path(__file__).resolve().parents[1]
    policy = json.loads(
        (root / "quality/security-false-positive-dispositions.json").read_bytes()
    )
    restored = _nov13_trivy_historical_policy(policy)
    assert len(restored["records"]) == 512
    row = next(
        record
        for record in restored["records"]
        if record["identity"]["path"] == _NOV4_TRIVY_IGNORE_POLICY_PATH
        and record["identity"]["hashed_secret_bytes"]
        == _nov13_trivy_identity_bytes(_NOV13_TRIVY_PREVIOUS_IGNORE_POLICY_DIGEST)
    )
    assert row["category"] == "public_integrity_digest"
    assert row["expires_on"] == "2027-01-10"
    assert _nov13_trivy_current_view(restored["records"]) != restored["records"]
    forward = _nov13_trivy_current_view(restored["records"])
    assert forward[:505] == policy["records"][:505]
    assert forward[506:] == policy["records"][506:]


@pytest.mark.parametrize("mutation", ["path", "digest", "category", "owner", "expiry"])
def test_nov13_trivy_projection_rejects_scope_drift(mutation: str) -> None:
    root = Path(__file__).resolve().parents[1]
    policy = json.loads(
        (root / "quality/security-false-positive-dispositions.json").read_bytes()
    )
    row = next(
        record
        for record in policy["records"]
        if record["identity"]["path"] == _NOV4_TRIVY_IGNORE_POLICY_PATH
        and record["identity"]["hashed_secret_bytes"]
        == _nov13_trivy_identity_bytes(_NOV13_TRIVY_CURRENT_IGNORE_POLICY_DIGEST)
    )
    if mutation == "path":
        row["identity"]["path"] = "scripts/quality/other_validator.py"
    elif mutation == "digest":
        row["identity"]["hashed_secret_bytes"][0] ^= 1
    elif mutation == "category":
        row["category"] = "synthetic_test_fixture"
    elif mutation == "owner":
        row["owner"] = "someone_else"
    else:
        row["expires_on"] = "2027-01-11"
    with pytest.raises(AssertionError, match="live disposition trivy identity"):
        _nov13_trivy_historical_policy(policy)


# STEP5b tests/test_quality_workflow_contract.py is a Semgrep row-13 companion. The
# KSV-0047 expectation removed with the stale SPIRE exception changes its bytes, so
# its companion hex in the ledger and the one public-integrity policy record that
# holds sha1(companion hex) are rebound one-to-one. The exact predecessor source,
# ledger and policy bytes are restored before the existing row-13 pins are checked.
_NOV13_TRIVY_WORKFLOW_PATH = "tests/test_quality_workflow_contract.py"
_NOV13_TRIVY_WORKFLOW_CURRENT_SHA256 = bytes.fromhex(
    "1c 75 46 38 eb 59 f5 79 1d dd 20 9c 0f 36 da fc dd 23 fa 92 76 d8 b4 f2 e5 d8 b6 2a 0e cd 8b 76"
)
_NOV13_TRIVY_WORKFLOW_PREVIOUS_SHA256 = bytes.fromhex(
    "e0 d2 df 72 3e a7 cb 3d 82 03 5d 18 a8 70 70 b3 89 4a e0 c9 f7 91 6c 51 58 c9 7c a3 e0 54 7e f5"
)
_NOV13_TRIVY_WORKFLOW_LEDGER_CURRENT_SHA256 = bytes.fromhex(
    "f2 33 1e 29 5d a2 63 f6 31 f2 ca 95 3e 12 a0 70 bb fe a4 47 66 85 29 13 e9 ab 1d 3c c9 81 5a f4"
)
_NOV13_TRIVY_WORKFLOW_ROW = 505
_NOV13_TRIVY_WORKFLOW_LEDGER_PATH = "quality/semgrep-dispositions.json"
_NOV13_TRIVY_WORKFLOW_ANCHOR = b'        "KSV-0014",\n        "KSV-0009",\n'
_NOV13_TRIVY_WORKFLOW_RESTORED = (
    b'        "KSV-0014",\n        "KSV-0047",\n        "KSV-0009",\n'
)


def _nov13_trivy_companion_hex(digest: bytes) -> bytes:
    return digest.hex().encode("ascii")


def _nov13_trivy_workflow_source_bytes(path: str, actual: bytes) -> bytes:
    if path == _NOV13_TRIVY_WORKFLOW_PATH:
        assert hashlib.sha256(actual).digest() == (
            _NOV13_TRIVY_WORKFLOW_CURRENT_SHA256
        ), f"conditional disposition source file SHA-256 changed: {path}"
        assert actual.count(_NOV13_TRIVY_WORKFLOW_ANCHOR) == 1
        historical = actual.replace(
            _NOV13_TRIVY_WORKFLOW_ANCHOR, _NOV13_TRIVY_WORKFLOW_RESTORED, 1
        )
        assert (
            hashlib.sha256(historical).digest() == _NOV13_TRIVY_WORKFLOW_PREVIOUS_SHA256
        ), f"conditional disposition source file SHA-256 changed: {path}"
        return historical
    if path == _NOV13_TRIVY_WORKFLOW_LEDGER_PATH:
        assert hashlib.sha256(actual).digest() == (
            _NOV13_TRIVY_WORKFLOW_LEDGER_CURRENT_SHA256
        ), f"conditional disposition source file SHA-256 changed: {path}"
        current = _nov13_trivy_companion_hex(_NOV13_TRIVY_WORKFLOW_CURRENT_SHA256)
        assert actual.count(current) == 1, (
            f"conditional disposition source file SHA-256 changed: {path}"
        )
        historical = actual.replace(
            current,
            _nov13_trivy_companion_hex(_NOV13_TRIVY_WORKFLOW_PREVIOUS_SHA256),
            1,
        )
        assert (
            hashlib.sha256(historical).digest() == _NOV13_LOOPBACK_LEDGER_CURRENT_SHA256
        ), f"conditional disposition source file SHA-256 changed: {path}"
        return historical
    return actual


def _nov13_trivy_workflow_historical_policy(policy: dict[str, Any]) -> dict[str, Any]:
    restored = copy.deepcopy(policy)
    identity = restored["records"][_NOV13_TRIVY_WORKFLOW_ROW]["identity"]
    assert identity["path"] == _NOV13_TRIVY_WORKFLOW_LEDGER_PATH
    assert identity["type"] == "Hex High Entropy String"
    live_digest = hashlib.sha1(
        _nov13_trivy_companion_hex(_NOV13_TRIVY_WORKFLOW_CURRENT_SHA256),
        usedforsecurity=False,
    ).digest()
    assert bytes(identity["hashed_secret_bytes"]) == live_digest, (
        "live disposition trivy workflow companion identity changed"
    )
    identity["hashed_secret_bytes"] = list(
        hashlib.sha1(
            _nov13_trivy_companion_hex(_NOV13_TRIVY_WORKFLOW_PREVIOUS_SHA256),
            usedforsecurity=False,
        ).digest()
    )
    return restored


def test_nov13_trivy_workflow_companion_rebind_preserves_exact_predecessor() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / _NOV13_TRIVY_WORKFLOW_PATH).read_bytes()
    ledger_bytes = (root / _NOV13_TRIVY_WORKFLOW_LEDGER_PATH).read_bytes()
    ledger = json.loads(ledger_bytes)
    companions = [
        item["sha256"]
        for item in ledger["dispositions"][12]["companions"]
        if item["path"] == _NOV13_TRIVY_WORKFLOW_PATH
    ]
    assert companions == [hashlib.sha256(source).hexdigest()]
    assert b'"KSV-0047"' not in source
    historical = _nov13_trivy_workflow_source_bytes(_NOV13_TRIVY_WORKFLOW_PATH, source)
    assert hashlib.sha256(historical).digest() == _NOV13_TRIVY_WORKFLOW_PREVIOUS_SHA256
    assert historical.count(b'"KSV-0047"') == 1
    restored_ledger = _nov13_trivy_workflow_source_bytes(
        _NOV13_TRIVY_WORKFLOW_LEDGER_PATH, ledger_bytes
    )
    assert hashlib.sha256(restored_ledger).digest() == (
        _NOV13_LOOPBACK_LEDGER_CURRENT_SHA256
    )
    policy = json.loads(
        (root / "quality/security-false-positive-dispositions.json").read_bytes()
    )
    restored_policy = _nov13_trivy_historical_policy(policy)
    assert len(restored_policy["records"]) == 512
    assert (
        bytes(
            restored_policy["records"][_NOV13_TRIVY_WORKFLOW_ROW]["identity"][
                "hashed_secret_bytes"
            ]
        )
        == hashlib.sha1(
            _nov13_trivy_companion_hex(_NOV13_TRIVY_WORKFLOW_PREVIOUS_SHA256),
            usedforsecurity=False,
        ).digest()
    )


@pytest.mark.parametrize("mutation", ["source", "ledger", "policy"])
def test_nov13_trivy_workflow_companion_projection_rejects_drift(mutation: str) -> None:
    root = Path(__file__).resolve().parents[1]
    if mutation == "source":
        actual = (root / _NOV13_TRIVY_WORKFLOW_PATH).read_bytes() + b"\n"
        with pytest.raises(AssertionError, match="conditional disposition source"):
            _nov13_trivy_workflow_source_bytes(_NOV13_TRIVY_WORKFLOW_PATH, actual)
    elif mutation == "ledger":
        actual = (root / _NOV13_TRIVY_WORKFLOW_LEDGER_PATH).read_bytes() + b"\n"
        with pytest.raises(AssertionError, match="conditional disposition source"):
            _nov13_trivy_workflow_source_bytes(
                _NOV13_TRIVY_WORKFLOW_LEDGER_PATH, actual
            )
    else:
        policy = json.loads(
            (root / "quality/security-false-positive-dispositions.json").read_bytes()
        )
        policy["records"][_NOV13_TRIVY_WORKFLOW_ROW]["identity"]["hashed_secret_bytes"][
            0
        ] ^= 1
        with pytest.raises(AssertionError, match="trivy workflow companion identity"):
            _nov13_trivy_workflow_historical_policy(policy)
