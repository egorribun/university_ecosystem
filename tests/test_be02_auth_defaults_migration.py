"""Independent auth-boolean contracts for the fresh-only MVP baseline.

Emitted DDL is recorded, not executed. These checks do not certify PostgreSQL
catalog convergence or revive deleted phase-one migration behavior.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

import app.models  # noqa: F401  # register all mapped metadata
from app.core.database import Base
from tests.fixtures.baseline_defaults import assert_default_columns, replace_column
from tests.fixtures.baseline_migration import BASELINE_PATH, capture_baseline

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

# Finite reviewed indexes referencing these ten auth columns. They must each
# occur exactly once; any extra or changed reference still reaches the shared
# fail-closed column oracle. Expectations are not read from baseline SQL.
_AUTH_INDEXES = (
    "CREATE INDEX ix_active_sessions_mfa_required ON public.active_sessions "
    "USING btree (mfa_required)",
    "CREATE INDEX ix_email_change_tokens_used ON public.email_change_tokens "
    "USING btree (used)",
    "CREATE INDEX ix_invite_codes_is_active ON public.invite_codes USING btree (is_active)",
    "CREATE INDEX ix_invite_codes_is_used ON public.invite_codes USING btree (is_used)",
    "CREATE INDEX ix_mfa_totp_enrollments_active ON public.mfa_totp_enrollments "
    "USING btree (user_id, is_active)",
    "CREATE INDEX ix_mfa_totp_enrollments_is_active ON public.mfa_totp_enrollments "
    "USING btree (is_active)",
    "CREATE INDEX ix_password_reset_tokens_used ON public.password_reset_tokens "
    "USING btree (used)",
    "CREATE INDEX ix_recovery_codes_is_used ON public.recovery_codes USING btree (is_used)",
    "CREATE INDEX ix_users_is_active ON public.users USING btree (is_active)",
    "CREATE INDEX ix_users_mfa_required ON public.users USING btree (mfa_required)",
)


def _declarations() -> dict[str, str]:
    return {
        qualified: f"{qualified.split('.', 1)[1]} boolean DEFAULT {value} NOT NULL"
        for qualified, value in EXPECTED_COLUMNS.items()
    }


def _assert_auth_defaults(statements: list[str]) -> None:
    for index in _AUTH_INDEXES:
        assert statements.count(index) == 1, index
    assert_default_columns(
        [sql for sql in statements if sql not in _AUTH_INDEXES], _declarations()
    )


def test_auth_boolean_phase_is_dual_declared() -> None:
    assert len(EXPECTED_COLUMNS) == 10
    for qualified_name, expected in EXPECTED_COLUMNS.items():
        table_name, column_name = qualified_name.split(".", 1)
        column = Base.metadata.tables[table_name].c[column_name]
        assert isinstance(column.type, sa.Boolean), qualified_name
        assert column.nullable is False, qualified_name
        assert column.default is not None, qualified_name
        assert type(column.default.arg) is bool, qualified_name
        assert column.default.arg is (expected == "true"), qualified_name
        assert column.server_default is not None, qualified_name
        assert str(column.server_default.arg).lower() == expected, qualified_name


def test_baseline_declares_every_auth_boolean_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, operations = capture_baseline(monkeypatch)
    _assert_auth_defaults(operations.statements)


def test_migration_revision_is_current_single_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, _ = capture_baseline(monkeypatch)
    assert migration.revision == "202611020000"
    assert migration.down_revision is None
    assert sorted(BASELINE_PATH.parent.glob("*.py")) == [BASELINE_PATH]


@pytest.mark.parametrize("qualified", EXPECTED_COLUMNS)
@pytest.mark.parametrize(
    "defect", ["value", "type", "nullable", "missing", "duplicate"]
)
def test_baseline_auth_defaults_reject_column_drift(
    qualified: str, defect: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, operations = capture_baseline(monkeypatch)
    before = _declarations()[qualified]
    value = EXPECTED_COLUMNS[qualified]
    replacements = {
        "value": before.replace(value, "false" if value == "true" else "true"),
        "type": before.replace("boolean", "text"),
        "nullable": before.removesuffix(" NOT NULL"),
        "missing": "",
        "duplicate": before + ",\n    " + before,
    }
    changed = replace_column(
        operations.statements, qualified.split(".", 1)[0], before, replacements[defect]
    )
    with pytest.raises(AssertionError):
        _assert_auth_defaults(changed)


@pytest.mark.parametrize(
    "extra",
    [
        "ALTER TABLE public.users ALTER COLUMN mfa_required SET DEFAULT true",
        "ALTER TABLE users ALTER COLUMN is_active DROP NOT NULL",
        "ALTER TABLE public.recovery_codes RENAME TO old_codes",
        "ALTER TABLE public.password_reset_tokens SET SCHEMA archive",
        'ALTER TABLE public.users ALTER COLUMN "mfa_required" DROP DEFAULT',
        r'ALTER TABLE public.users ALTER COLUMN U&"mfa_\0072equired" DROP DEFAULT',
    ],
)
def test_baseline_auth_defaults_reject_later_overrides(
    extra: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, operations = capture_baseline(monkeypatch)
    with pytest.raises(AssertionError):
        _assert_auth_defaults([*operations.statements, extra])


@pytest.mark.parametrize(
    "defect",
    [
        "missing",
        "duplicate",
        "changed-options",
        "changed-target",
        "unexpected-reference",
    ],
)
def test_baseline_auth_index_admission_is_exact(
    defect: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, operations = capture_baseline(monkeypatch)
    changed = list(operations.statements)
    index = _AUTH_INDEXES[0]
    if defect == "missing":
        changed.remove(index)
    elif defect == "duplicate":
        changed.append(index)
    elif defect == "changed-options":
        changed[changed.index(index)] = index + " WHERE mfa_required"
    elif defect == "changed-target":
        changed[changed.index(index)] = index.replace(
            "public.active_sessions", "public.users"
        )
    else:
        changed.append(
            index.replace("ix_active_sessions_mfa_required", "unexpected_auth_index")
        )
    with pytest.raises(AssertionError):
        _assert_auth_defaults(changed)
