"""Regression contracts for the first BE-02 dual-default migration phase."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import app.models  # noqa: F401  # register all mapped metadata
from app.core.database import Base

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT / "alembic" / "versions" / "202609150001_phase_auth_boolean_defaults.py"
)

EXPECTED_COLUMNS = {
    "active_sessions.mfa_required": "false",
    "mfa_totp_enrollments.is_active": "false",
    "password_reset_tokens.used": "false",
    "email_change_tokens.used": "false",
    "recovery_codes.is_used": "false",
    "login_history.is_suspicious": "false",
    "users.is_active": "true",
    "users.mfa_required": "false",
    "invite_codes.is_active": "true",
    "invite_codes.is_used": "false",
}


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("be02_auth_defaults", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_auth_boolean_phase_is_dual_declared() -> None:
    for qualified_name in EXPECTED_COLUMNS:
        table_name, column_name = qualified_name.split(".", 1)
        column = Base.metadata.tables[table_name].c[column_name]
        assert column.default is not None, qualified_name
        assert column.server_default is not None, qualified_name


def test_migration_declares_every_target_and_phased_safety_contract() -> None:
    migration = _load_migration()
    specs = {f"{item.table}.{item.column}": item for item in migration.DEFAULT_SPECS}

    assert set(specs) == set(EXPECTED_COLUMNS)
    assert {str(item.server_default).lower() for item in specs.values()} == {
        "false",
        "true",
    }
    source = MIGRATION.read_text(encoding="utf-8").lower()
    for required in (
        "pg_get_expr",
        "pg_attribute",
        "statement_timeout",
        "lock_timeout",
        "not valid",
        "validate constraint",
        "set not null",
        "backfill",
        "requires online postgresql catalog preflight",
    ):
        assert required in source


def test_migration_revision_is_current_single_head() -> None:
    migration = _load_migration()

    assert migration.revision == "202609150001"
    assert migration.down_revision == "202608270003"
