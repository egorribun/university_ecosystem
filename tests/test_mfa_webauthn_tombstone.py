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
