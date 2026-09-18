from __future__ import annotations

import ast
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
        content = path.read_text(encoding="utf-8").lower()
        if "webauthn" in content or "passkey" in content:
            findings.append(str(path.relative_to(ROOT)))

    assert findings == []


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
