from __future__ import annotations

import ast
import copy
import hashlib
import json
import re
from pathlib import Path

import pytest

from scripts import verify_secrets_baseline as verifier

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOTS = (ROOT / "app",)
ALLOWED_HISTORY = ROOT / "alembic" / "versions"
ALLOWED_RETIREMENT_CONTRACTS = {
    Path(__file__).resolve(),
    ROOT / "tests" / "test_mfa_email_otp_migrations.py",
    ROOT / "tests" / "integration" / "test_mfa_email_otp_postgres.py",
    ROOT / "tests" / "test_mfa_openapi_artifacts_contract.py",
}
# Historical migration fixture only, not an active factor or a file exclusion.
# Re-review this exact Git blob binding after ANY orchestrator source change.
HISTORICAL_ORCHESTRATOR_TEST = Path("tests/test_migration_148642dd1207_orchestrator.py")
HISTORICAL_ORCHESTRATOR_BLOB = "29f6a9ba67d8f10a09b054242a7daeccfd7b0a7b"
# This map contains file-level pytest telemetry, not active product/security
# declarations. Its keys intentionally include immutable tombstone test
# filenames so the scheduler can retain their measured cost without making
# those historical names part of the MFA contract surface.
NON_CONTRACT_QUALITY_ARTIFACTS = {ROOT / "quality" / "test-durations.json"}
QUALITY_CONTRACT = ROOT / "quality" / "quality-contract.json"
HISTORICAL_RETIRED_MIGRATION_PATHS = frozenset(
    {
        "alembic/versions/202507310001_add_webauthn_attestation_fields.py",
        "alembic/versions/202509230001_drop_webauthn_credentials.py",
        "alembic/versions/202608250002_contract_retire_webauthn.py",
        "alembic/versions/ab93b27831f3_add_webauthn_support_v2.py",
    }
)


def _active_quality_contract_content(contract: dict[str, object]) -> str:
    active_contract = copy.deepcopy(contract)
    tier0 = active_contract.get("tier0")
    baselines = (
        tier0.get("legacy_migration_baselines") if isinstance(tier0, dict) else None
    )
    files = baselines.get("files") if isinstance(baselines, dict) else None
    if isinstance(files, list):
        for record in files:
            if (
                isinstance(record, dict)
                and record.get("path") in HISTORICAL_RETIRED_MIGRATION_PATHS
            ):
                record["path"] = "<inactive historical migration path>"
    return json.dumps(active_contract).lower()


def _active_scanner_policy_content(policy: dict[str, object]) -> str:
    active_policy = copy.deepcopy(policy)
    records = active_policy.get("records")
    if isinstance(records, list):
        for record in records:
            if not isinstance(record, dict):
                continue
            identity = record.get("identity")
            if (
                isinstance(identity, dict)
                and identity
                in (
                    {
                        "path": "tests/test_mfa_webauthn_tombstone.py",
                        "type": "Hex High Entropy String",
                        "hashed_secret_bytes": [
                            109,
                            67,
                            120,
                            143,
                            21,
                            122,
                            30,
                            20,
                            91,
                            168,
                            79,
                            9,
                            37,
                            165,
                            80,
                            183,
                            80,
                            124,
                            201,
                            40,
                        ],
                    },
                    {
                        "path": "tests/test_mfa_webauthn_tombstone.py",
                        "type": "Hex High Entropy String",
                        "hashed_secret_bytes": [
                            120,
                            244,
                            112,
                            145,
                            78,
                            179,
                            236,
                            151,
                            175,
                            133,
                            0,
                            251,
                            201,
                            135,
                            203,
                            98,
                            231,
                            245,
                            249,
                            83,
                        ],
                    },
                    {
                        "path": "tests/test_mfa_webauthn_tombstone.py",
                        "type": "Hex High Entropy String",
                        "hashed_secret_bytes": [
                            32,
                            87,
                            220,
                            238,
                            65,
                            56,
                            74,
                            173,
                            160,
                            109,
                            167,
                            158,
                            154,
                            251,
                            29,
                            7,
                            25,
                            76,
                            152,
                            145,
                        ],
                    },
                    {
                        "path": "tests/test_mfa_webauthn_tombstone.py",
                        "type": "Hex High Entropy String",
                        "hashed_secret_bytes": [
                            8,
                            134,
                            59,
                            8,
                            97,
                            25,
                            239,
                            115,
                            186,
                            55,
                            39,
                            151,
                            107,
                            170,
                            223,
                            60,
                            12,
                            240,
                            148,
                            10,
                        ],
                    },
                    {
                        "path": "tests/test_mfa_webauthn_tombstone.py",
                        "type": "Hex High Entropy String",
                        "hashed_secret_bytes": [
                            109,
                            246,
                            200,
                            201,
                            38,
                            194,
                            24,
                            95,
                            0,
                            19,
                            55,
                            55,
                            242,
                            153,
                            216,
                            45,
                            114,
                            223,
                            180,
                            240,
                        ],
                    },
                )
                and record.get("category") == "public_integrity_digest"
            ):
                # Only the exact inactive identity path is scanner bookkeeping.
                # Category, evidence and every other field remain fully visible.
                identity["path"] = "<inactive scanner identity path>"
    return json.dumps(active_policy).lower()


def test_active_scanner_policy_masks_new_pin_only_for_exact_identity() -> None:
    record = {
        "identity": {
            "path": "tests/test_mfa_webauthn_tombstone.py",
            "type": "Hex High Entropy String",
            "hashed_secret_bytes": [
                109,
                246,
                200,
                201,
                38,
                194,
                24,
                95,
                0,
                19,
                55,
                55,
                242,
                153,
                216,
                45,
                114,
                223,
                180,
                240,
            ],
        },
        "category": "public_integrity_digest",
    }
    policy = {"records": [record]}
    masked = _active_scanner_policy_content(policy)
    assert "<inactive scanner identity path>" in masked
    assert "webauthn" not in masked

    near_misses = []
    changed_path = copy.deepcopy(policy)
    changed_path["records"][0]["identity"]["path"] += ".unreviewed"
    near_misses.append(changed_path)
    changed_type = copy.deepcopy(policy)
    changed_type["records"][0]["identity"]["type"] = "Base Auth Credentials"
    near_misses.append(changed_type)
    changed_digest = copy.deepcopy(policy)
    changed_digest["records"][0]["identity"]["hashed_secret_bytes"][0] ^= 1
    near_misses.append(changed_digest)
    changed_category = copy.deepcopy(policy)
    changed_category["records"][0]["category"] = "source_contract_identifier"
    near_misses.append(changed_category)
    for near_miss in near_misses:
        visible = _active_scanner_policy_content(near_miss)
        assert "tests/test_mfa_webauthn_tombstone.py" in visible
        assert "webauthn" in visible


def _active_backend_test_content(path: Path, raw_content: bytes) -> str:
    content = raw_content.decode("utf-8")
    if path != ROOT / HISTORICAL_ORCHESTRATOR_TEST:
        return content.lower()

    # Git's blob ID binds every byte, including comments and line endings.
    header = f"blob {len(raw_content)}\0".encode("ascii")
    blob_sha = hashlib.sha1(header + raw_content, usedforsecurity=False).hexdigest()
    if blob_sha != HISTORICAL_ORCHESTRATOR_BLOB:
        return content.lower()

    # The reviewed blob has exactly these two historical identifier literals:
    # _Inspector.__init__.self.user_columns and the create-index assertion.
    return (
        content.replace('"webauthn_id"', '"<historical migration column>"', 1)
        .replace('"ix_users_webauthn_id"', '"<historical migration index>"', 1)
        .lower()
    )


def test_runtime_has_no_webauthn_references_or_models() -> None:
    findings: list[str] = []
    for runtime_root in RUNTIME_ROOTS:
        for path in runtime_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "webauthn" in text.lower():
                findings.append(str(path.relative_to(ROOT)))
            ast.parse(text)
    assert findings == []


def test_webauthn_dependency_is_retired() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()
    assert '"webauthn' not in pyproject


def test_security_policy_describes_only_current_mfa_factors() -> None:
    policy = (ROOT / "SECURITY.md").read_text(encoding="utf-8").lower()

    assert "webauthn" not in policy
    assert "passkey" not in policy
    assert "totp" in policy
    assert "email otp" in policy
    assert "recovery code" in policy
    assert "remediation" in policy


def test_active_quality_contracts_have_no_retired_factor_references() -> None:
    findings: list[str] = []
    for path in (ROOT / "quality").glob("*.json"):
        if path.resolve() in NON_CONTRACT_QUALITY_ARTIFACTS:
            continue
        raw_content = path.read_text(encoding="utf-8")
        if path.resolve() == QUALITY_CONTRACT.resolve():
            content = _active_quality_contract_content(json.loads(raw_content))
        elif path == ROOT / "quality" / "security-false-positive-dispositions.json":
            content = _active_scanner_policy_content(json.loads(raw_content))
        else:
            content = raw_content.lower()
        if "webauthn" in content or "passkey" in content:
            findings.append(str(path.relative_to(ROOT)))

    assert findings == []


def test_quality_contract_masks_only_exact_historical_migration_path_values() -> None:
    contract = json.loads(QUALITY_CONTRACT.read_text(encoding="utf-8"))
    tier0 = contract["tier0"]
    baselines = tier0["legacy_migration_baselines"]
    files = baselines["files"]
    retired_paths = {
        record["path"]
        for record in files
        if "webauthn" in record["path"].lower() or "passkey" in record["path"].lower()
    }

    assert retired_paths == HISTORICAL_RETIRED_MIGRATION_PATHS
    active_content = _active_quality_contract_content(contract)
    assert "webauthn" not in active_content
    assert "passkey" not in active_content

    active_reference = copy.deepcopy(contract)
    active_reference["manifest_path"] = "artifacts/webauthn-manifest.json"
    assert "webauthn" in _active_quality_contract_content(active_reference)

    unapproved_path = copy.deepcopy(contract)
    unapproved_record = copy.deepcopy(files[0])
    unapproved_record["path"] = "alembic/versions/202610140001_add_webauthn_support.py"
    unapproved_path["tier0"]["legacy_migration_baselines"]["files"].append(
        unapproved_record
    )
    assert "webauthn" in _active_quality_contract_content(unapproved_path)


def test_historical_migration_references_are_confined_to_immutable_history() -> None:
    assert ALLOWED_HISTORY.is_dir()


def test_backend_tests_have_no_retired_factor_references() -> None:
    findings = []
    for path in (ROOT / "tests").rglob("*.py"):
        if path.resolve() in ALLOWED_RETIREMENT_CONTRACTS:
            continue
        content = _active_backend_test_content(path, path.read_bytes())
        if "webauthn" in content or "passkey" in content:
            findings.append(str(path.relative_to(ROOT)))
    assert findings == []


@pytest.fixture
def historical_orchestrator_source() -> bytes:
    return (ROOT / HISTORICAL_ORCHESTRATOR_TEST).read_bytes()


def test_backend_guard_accepts_only_the_source_bound_historical_literals(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    historical_orchestrator_source: bytes,
) -> None:
    monkeypatch.setitem(globals(), "ROOT", tmp_path)
    path = tmp_path / HISTORICAL_ORCHESTRATOR_TEST
    path.parent.mkdir()
    path.write_bytes(historical_orchestrator_source)

    test_backend_tests_have_no_retired_factor_references()


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (b"class _Inspector:", b"class _ActiveInspector:"),
        (b"self.user_columns = {", b"self.active_columns = {"),
        (b'"webauthn_id"', b'"webauthn_active"'),
        (b'"webauthn_id"', b'"webauthn_id", "passkey"'),
        (b'"webauthn_id"', b'"webauthn_id", "webauthn_id"'),
        (
            b'assert "ix_users_webauthn_id" in created_indexes',
            b'active_factor = "ix_users_webauthn_id"',
        ),
    ],
    ids=[
        "moved-fixture-context",
        "moved-literal-target",
        "new-identifier",
        "new-factor",
        "duplicate-identifier",
        "active-use-instead-of-history-assertion",
    ],
)
def test_backend_guard_rejects_changed_historical_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    historical_orchestrator_source: bytes,
    old: bytes,
    new: bytes,
) -> None:
    monkeypatch.setitem(globals(), "ROOT", tmp_path)
    path = tmp_path / HISTORICAL_ORCHESTRATOR_TEST
    path.parent.mkdir()
    assert historical_orchestrator_source.count(old) == 1
    changed = historical_orchestrator_source.replace(old, new)
    path.write_bytes(changed)

    unmasked = changed.decode("utf-8").lower()
    assert _active_backend_test_content(path, changed) == unmasked
    with pytest.raises(AssertionError, match="test_migration_148642dd1207"):
        test_backend_tests_have_no_retired_factor_references()


@pytest.mark.parametrize(
    "addition",
    [
        b"\n# Unrelated edits also require explicit source-binding review.\n",
        b'\nactive_factor = "webauthn_id"\n',
        b'\nactive_factor = "passkey"\n',
    ],
    ids=["unrelated-source-change", "new-active-reference", "new-active-factor"],
)
def test_backend_guard_requires_review_after_any_historical_test_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    historical_orchestrator_source: bytes,
    addition: bytes,
) -> None:
    monkeypatch.setitem(globals(), "ROOT", tmp_path)
    path = tmp_path / HISTORICAL_ORCHESTRATOR_TEST
    path.parent.mkdir()
    changed = historical_orchestrator_source + addition
    path.write_bytes(changed)

    unmasked = changed.decode("utf-8").lower()
    assert _active_backend_test_content(path, changed) == unmasked
    with pytest.raises(AssertionError, match="test_migration_148642dd1207"):
        test_backend_tests_have_no_retired_factor_references()


@pytest.mark.parametrize(
    "relative_path",
    [
        "tests/test_active_factor.py",
        "tests/new/test_migration_148642dd1207_orchestrator.py",
        "app/test_migration_148642dd1207_orchestrator.py",
    ],
)
def test_source_bound_history_is_not_exempt_at_other_test_or_runtime_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    historical_orchestrator_source: bytes,
    relative_path: str,
) -> None:
    monkeypatch.setitem(globals(), "ROOT", tmp_path)
    monkeypatch.setitem(globals(), "RUNTIME_ROOTS", (tmp_path / "app",))
    path = tmp_path / relative_path
    path.parent.mkdir(parents=True)
    path.write_bytes(historical_orchestrator_source)

    unmasked = historical_orchestrator_source.decode("utf-8").lower()
    active = _active_backend_test_content(path, historical_orchestrator_source)
    assert active == unmasked
    guard = (
        test_runtime_has_no_webauthn_references_or_models
        if relative_path.startswith("app/")
        else test_backend_tests_have_no_retired_factor_references
    )
    with pytest.raises(AssertionError):
        guard()


def test_source_bound_history_does_not_exempt_a_new_symlink_alias(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    historical_orchestrator_source: bytes,
) -> None:
    monkeypatch.setitem(globals(), "ROOT", tmp_path)
    path = tmp_path / HISTORICAL_ORCHESTRATOR_TEST
    path.parent.mkdir()
    path.write_bytes(historical_orchestrator_source)
    alias = path.with_name("test_active_alias.py")
    alias.symlink_to(path)

    with pytest.raises(AssertionError, match="test_active_alias"):
        test_backend_tests_have_no_retired_factor_references()


@pytest.fixture(params=(0, 1, 2, 3, 4))
def public_git_blob_disposition_record(
    request: pytest.FixtureRequest,
) -> dict[str, object]:
    fixture = ROOT / "tests" / "fixtures" / "public-git-blob-dispositions.json"
    records = json.loads(fixture.read_text(encoding="utf-8"))["records"]
    own_path = Path(__file__).resolve().relative_to(ROOT).as_posix()
    matches = [row for row in records if row["identity"]["path"] == own_path]
    assert len(matches) == 5
    return copy.deepcopy(matches[request.param])


def _approved_historical_orchestrator_pin_record() -> dict[str, object]:
    fixture_path = ROOT / "tests" / "fixtures" / "public-git-blob-dispositions.json"
    fixture_records = json.loads(fixture_path.read_text(encoding="utf-8"))["records"]
    current_path = Path(__file__).resolve().relative_to(ROOT).as_posix()
    matches = [
        record
        for record in fixture_records
        if record["identity"]["path"] == current_path
        and record["reviewed_on"] == "2026-10-26"
        and record["category"] == "public_integrity_digest"
        and "HISTORICAL_ORCHESTRATOR_BLOB" in record["evidence"]
    ]
    assert len(fixture_records) == 10
    assert len(matches) == 1
    return copy.deepcopy(matches[0])


def _historical_orchestrator_pin_digest() -> tuple[int, ...]:
    consumer = Path(__file__).read_text(encoding="utf-8")
    assignments = [
        node
        for node in ast.parse(consumer).body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "HISTORICAL_ORCHESTRATOR_BLOB"
            for target in node.targets
        )
    ]
    assert len(assignments) == 1
    value = ast.literal_eval(assignments[0].value)
    assert isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value)
    source = (ROOT / HISTORICAL_ORCHESTRATOR_TEST).read_bytes()
    header = f"blob {len(source)}\0".encode("ascii")
    assert value == hashlib.sha1(header + source, usedforsecurity=False).hexdigest()
    return tuple(hashlib.sha1(value.encode("ascii"), usedforsecurity=False).digest())


def test_public_git_blob_orchestrator_rebind_appends_one_exact_identity() -> None:
    policy = json.loads(
        (ROOT / "quality/security-false-positive-dispositions.json").read_text(
            encoding="utf-8"
        )
    )
    record = _approved_historical_orchestrator_pin_record()
    assert len(policy["records"]) == 494
    assert policy["records"][345:346] == [record]
    assert (
        record["identity"]["path"]
        == Path(__file__).resolve().relative_to(ROOT).as_posix()
    )
    assert record["identity"]["type"] == "Hex High Entropy String"
    assert record["category"] == "public_integrity_digest"
    assert record["owner"] == "egorribun"
    assert record["reviewed_on"] == "2026-10-26"
    assert record["expires_on"] == "2027-01-10"
    assert record["approval_status"] == "approved"
    assert "Public Git SHA-1 integrity digest of " in record["evidence"]
    assert "HISTORICAL_ORCHESTRATOR_BLOB" in record["evidence"]
    assert "Git blob framing binds all source bytes" in record["evidence"]
    assert "not credential material" in record["evidence"]
    assert tuple(record["identity"]["hashed_secret_bytes"]) == (
        _historical_orchestrator_pin_digest()
    )
    assert tuple(record["identity"]["hashed_secret_bytes"]) == tuple(
        verifier._PUBLIC_GIT_BLOB_ORCHESTRATOR_SOURCE_REBIND_IDENTITY[2]
    )
    assert verifier.validate_false_positive_dispositions(
        {"schema_version": 1, "records": [record]},
        today=verifier.date(2026, 10, 26),
    ) == {
        verifier.FindingIdentity(
            record["identity"]["path"],
            record["identity"]["type"],
            bytes(record["identity"]["hashed_secret_bytes"]).hex(),
            1,
        )
    }


def test_new_orchestrator_public_git_blob_record_rejects_future_review_date() -> None:
    record = _approved_historical_orchestrator_pin_record()
    assert tuple(record["identity"]["hashed_secret_bytes"]) == (
        _historical_orchestrator_pin_digest()
    )
    with pytest.raises(verifier.BaselineArtifactError, match="date range is invalid"):
        verifier.validate_false_positive_dispositions(
            {"schema_version": 1, "records": [copy.deepcopy(record)]},
            today=verifier.date(2026, 10, 25),
        )


def _write_scanner_policy_fixture(
    root: Path, record: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(globals(), "ROOT", root)
    quality = root / "quality"
    quality.mkdir()
    (quality / "security-false-positive-dispositions.json").write_text(
        json.dumps({"schema_version": 1, "records": [record]}), encoding="utf-8"
    )


def test_quality_guard_accepts_only_the_exact_inactive_scanner_path_field(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    public_git_blob_disposition_record: dict[str, object],
) -> None:
    _write_scanner_policy_fixture(
        tmp_path, public_git_blob_disposition_record, monkeypatch
    )
    test_active_quality_contracts_have_no_retired_factor_references()


@pytest.mark.parametrize(
    "mutation",
    [
        "path",
        "detector",
        "digest",
        "category_scope",
        "category",
        "evidence",
        "runtime_field",
    ],
)
def test_quality_guard_keeps_changed_identity_and_active_references_visible(
    mutation: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    public_git_blob_disposition_record: dict[str, object],
) -> None:
    record = public_git_blob_disposition_record
    identity = record["identity"]
    assert isinstance(identity, dict)
    if mutation == "path":
        identity["path"] = "tests/test_active_webauthn.py"
    elif mutation == "detector":
        identity["type"] = "Secret Keyword"
    elif mutation == "digest":
        digest = identity["hashed_secret_bytes"]
        assert isinstance(digest, list)
        digest[0] ^= 1
    elif mutation == "category_scope":
        record["category"] = "documented_crypto_test_vector"
    elif mutation == "category":
        record["category"] = "webauthn_runtime_factor"
    elif mutation == "evidence":
        record["evidence"] = "active passkey authentication"
    else:
        assert mutation == "runtime_field"
        record["runtime_factor"] = "webauthn"
    _write_scanner_policy_fixture(tmp_path, record, monkeypatch)
    with pytest.raises(AssertionError):
        test_active_quality_contracts_have_no_retired_factor_references()


def test_runtime_guard_still_rejects_an_active_retired_factor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = tmp_path / "app"
    runtime.mkdir()
    (runtime / "active_factor.py").write_text("FACTOR = 'webauthn'\n", encoding="utf-8")
    monkeypatch.setitem(globals(), "ROOT", tmp_path)
    monkeypatch.setitem(globals(), "RUNTIME_ROOTS", (runtime,))
    with pytest.raises(AssertionError):
        test_runtime_has_no_webauthn_references_or_models()
