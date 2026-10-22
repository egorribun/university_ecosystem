from __future__ import annotations

import ast
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOTS = (ROOT / "app",)
ALLOWED_HISTORY = ROOT / "alembic" / "versions"
ALLOWED_RETIREMENT_CONTRACTS = {
    Path(__file__).resolve(),
    ROOT / "tests" / "test_mfa_email_otp_migrations.py",
    ROOT / "tests" / "integration" / "test_mfa_email_otp_postgres.py",
    ROOT / "tests" / "test_mfa_openapi_artifacts_contract.py",
}
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
        if (
            "webauthn" in path.read_text(encoding="utf-8").lower()
            or "passkey" in path.read_text(encoding="utf-8").lower()
        ):
            findings.append(str(path.relative_to(ROOT)))
    assert findings == []
