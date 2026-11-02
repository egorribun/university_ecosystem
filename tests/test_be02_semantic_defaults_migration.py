"""BE-02 timestamp and role defaults on the fresh-only MVP baseline.

The historical loader remains lazy for its existing integration importer.
Catalog preflight and contract-preserving downgrade belong to the deleted
migration; these unit tests exercise the actual baseline's emitted schema.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

import pytest
import sqlalchemy as sa

import app.models  # noqa: F401 - register mapped metadata
from app.core.database import Base
from tests.fixtures.baseline_defaults import (
    ROLE_TYPE_SQL,
    SEMANTIC_DEFAULTS,
    assert_default_columns,
    assert_role_type,
    replace_column,
)
from tests.fixtures.baseline_migration import (
    assert_downgrade_refuses,
    bind_baseline,
    capture_baseline,
)

TIMESTAMP_COLUMNS = (
    "attachments.created_at",
    "chats.created_at",
    "chats.updated_at",
    "dead_letter_jobs.created_at",
    "dead_letter_jobs.updated_at",
    "failed_outbox_events.failed_at",
    "grades.created_at",
    "grades.updated_at",
    "message_reactions.created_at",
    "messages.created_at",
    "stored_events.created_at",
)
MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic/versions/202609250001_phase_semantic_defaults.py"
)


def _migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "be02_semantic_defaults", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_remaining_timestamp_candidates_are_dual_declared() -> None:
    for qualified in TIMESTAMP_COLUMNS:
        table, field = qualified.split(".", 1)
        column = Base.metadata.tables[table].c[field]
        assert column.default is not None, qualified
        assert column.server_default is not None, qualified


@pytest.mark.filterwarnings("error::pytest.PytestUnraisableExceptionWarning")
def test_user_role_default_is_dual_declared_and_sqlite_compatible() -> None:
    role = Base.metadata.tables["users"].c.role
    assert role.default is not None
    assert role.server_default is not None

    engine = sa.create_engine("sqlite://")
    try:
        probe = sa.Table(
            "role_default_probe",
            sa.MetaData(),
            sa.Column("role", role.type, server_default=role.server_default.arg),
        )
        probe.create(engine)
        with engine.begin() as connection:
            inserted = connection.execute(probe.insert().returning(probe.c.role))
            assert inserted.scalar_one() == "student"
    finally:
        engine.dispose()


def _assert_semantic_defaults(statements: list[str]) -> None:
    assert_default_columns(statements, SEMANTIC_DEFAULTS)
    assert_role_type(statements)


def test_baseline_installs_reviewed_timestamp_and_role_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, operations = capture_baseline(monkeypatch)
    assert migration.revision == "202611020000"
    assert migration.down_revision is None
    assert set(SEMANTIC_DEFAULTS) == {*TIMESTAMP_COLUMNS, "users.role"}
    _assert_semantic_defaults(operations.statements)


def test_phase_four_policy_accounts_for_all_remaining_exceptions() -> None:
    policy = json.loads(
        (
            Path(__file__).resolve().parents[1] / "quality/model-default-policy.json"
        ).read_text(encoding="utf-8")
    )
    # The source-derived inventory follows migrations after this historical phase.
    assert policy["expected"]["migration_head"] == "202611020000"
    assert policy["expected"]["effective_counts"] == {
        "both": 87,
        "python_only": 42,
        "server_only": 0,
    }
    assert len(policy["exceptions"]) == 42
    quarantine_id = next(
        item
        for item in policy["exceptions"]
        if item["column"] == "quarantine_reservations.id"
    )
    assert quarantine_id["kind"] == "inherited_uuid7_primary_key"
    assert quarantine_id["owner"] == "backend-platform"
    receipt_id = next(
        item
        for item in policy["exceptions"]
        if item["column"] == "chat_send_receipts.id"
    )
    assert receipt_id == {
        "column": "chat_send_receipts.id",
        "kind": "inherited_uuid7_primary_key",
        "owner": "backend-platform",
        "reason": (
            "UUIDv7 is supplied by UUID7PrimaryKeyMixin; a database fallback "
            "could violate the time-ordered identifier contract."
        ),
    }


@pytest.mark.parametrize("qualified", TIMESTAMP_COLUMNS)
def test_timestamp_model_defaults_keep_utc_wall_clock_and_transaction_fallback(
    qualified: str,
) -> None:
    table, field = qualified.split(".", 1)
    column = Base.metadata.tables[table].c[field]
    assert isinstance(column.type, sa.DateTime), qualified
    assert column.type.timezone is True, qualified
    assert column.nullable is False, qualified
    assert column.default is not None, qualified
    assert column.server_default is not None, qualified
    assert str(column.server_default.arg) == "now()", qualified
    assert callable(column.default.arg), qualified
    before = datetime.now(UTC)
    value = column.default.arg(None)
    after = datetime.now(UTC)
    assert isinstance(value, datetime), qualified
    assert value.tzinfo is not None, qualified
    assert value.utcoffset() == timedelta(0), qualified
    assert before <= value <= after, qualified


def test_role_model_keeps_native_enum_and_lowercase_student_default() -> None:
    column = Base.metadata.tables["users"].c.role
    assert isinstance(column.type, sa.Enum)
    assert column.type.native_enum is True
    assert column.type.name == "userrole"
    assert "student" in column.type.enums
    assert column.nullable is False
    assert column.default is not None
    assert column.default.arg == "student"
    assert column.server_default is not None
    assert str(column.server_default.arg) == "student"


def test_conflicting_timestamp_default_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, operations = capture_baseline(monkeypatch)
    before = SEMANTIC_DEFAULTS["attachments.created_at"]
    changed = replace_column(
        operations.statements,
        "attachments",
        before,
        "created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL",
    )
    with pytest.raises(AssertionError):
        _assert_semantic_defaults(changed)


@pytest.mark.parametrize(
    "declaration",
    [
        "created_at timestamp without time zone DEFAULT now() NOT NULL",
        "created_at timestamp with time zone DEFAULT now()",
        "created_at timestamp with time zone NOT NULL",
        "created_at timestamp with time zone DEFAULT NULL NOT NULL",
    ],
    ids=("naive", "nullable", "missing-default", "null-default"),
)
def test_baseline_contract_rejects_timestamp_schema_drift(
    declaration: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, operations = capture_baseline(monkeypatch)
    changed = replace_column(
        operations.statements,
        "attachments",
        SEMANTIC_DEFAULTS["attachments.created_at"],
        declaration,
    )
    with pytest.raises(AssertionError):
        _assert_semantic_defaults(changed)


@pytest.mark.parametrize(
    "declaration",
    [
        "role text DEFAULT 'student'::text NOT NULL",
        "role public.otherrole DEFAULT 'student'::public.otherrole NOT NULL",
        "role other.userrole DEFAULT 'student'::other.userrole NOT NULL",
        "role public.userrole DEFAULT 'STUDENT'::public.userrole NOT NULL",
        "role public.userrole DEFAULT 'pen ding'::public.userrole NOT NULL",
        "role public.userrole DEFAULT 'student'::public.userrole",
    ],
    ids=("text", "wrong-enum", "wrong-schema", "case", "payload", "nullable"),
)
def test_baseline_contract_rejects_role_type_or_default_drift(
    declaration: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, operations = capture_baseline(monkeypatch)
    changed = replace_column(
        operations.statements, "users", SEMANTIC_DEFAULTS["users.role"], declaration
    )
    with pytest.raises(AssertionError):
        _assert_semantic_defaults(changed)


@pytest.mark.parametrize(
    "extra",
    [
        "ALTER TABLE public.attachments ALTER COLUMN created_at "
        "SET DEFAULT clock_timestamp()",
        "alter table attachments alter column created_at drop not null",
        'ALTER TABLE "public"."users" ALTER COLUMN "role" '
        "SET DEFAULT 'ADMIN'::public.userrole",
        "ALTER TABLE users ALTER COLUMN role DROP DEFAULT",
        "ALTER TABLE public.users RENAME TO old_users",
        "ALTER TABLE public.attachments SET SCHEMA archive",
    ],
)
def test_baseline_contract_rejects_later_semantic_default_overrides(
    extra: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, operations = capture_baseline(monkeypatch)
    with pytest.raises(AssertionError):
        _assert_semantic_defaults([*operations.statements, extra])


@pytest.mark.parametrize("defect", ["missing", "duplicate"])
def test_baseline_contract_rejects_missing_or_duplicate_timestamp_columns(
    defect: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, operations = capture_baseline(monkeypatch)
    before = SEMANTIC_DEFAULTS["attachments.created_at"]
    after = "" if defect == "missing" else before + ",\n    " + before + ",\n"
    changed = replace_column(
        operations.statements, "attachments", before + ",\n", after
    )
    with pytest.raises(AssertionError):
        _assert_semantic_defaults(changed)


def test_default_ddl_is_scoped_to_the_reviewed_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, operations = capture_baseline(monkeypatch)
    assert_default_columns(
        operations.statements, {"users.role": SEMANTIC_DEFAULTS["users.role"]}
    )
    assert_role_type(operations.statements)


@pytest.mark.parametrize(
    "replacement",
    [
        "CREATE TABLE other.users (",
        "CREATE TABLE users (",
        'CREATE TABLE "public"."users" (',
    ],
)
def test_baseline_defaults_are_public_schema_qualified(
    replacement: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, operations = capture_baseline(monkeypatch)
    changed = replace_column(
        operations.statements, "users", "CREATE TABLE public.users (", replacement
    )
    with pytest.raises(AssertionError):
        _assert_semantic_defaults(changed)


@pytest.mark.parametrize(
    "defect",
    ["missing-type", "duplicate-type", "missing-student", "not-native-enum"],
)
def test_baseline_contract_rejects_missing_or_changed_native_role_type(
    defect: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, operations = capture_baseline(monkeypatch)
    changed = list(operations.statements)
    assert changed.count(ROLE_TYPE_SQL) == 1
    if defect == "missing-type":
        changed.remove(ROLE_TYPE_SQL)
    elif defect == "duplicate-type":
        changed.append(ROLE_TYPE_SQL)
    else:
        replacement = (
            ROLE_TYPE_SQL.replace("    'student',\n", "")
            if defect == "missing-student"
            else ROLE_TYPE_SQL.replace("AS ENUM", "AS DOMAIN")
        )
        changed[changed.index(ROLE_TYPE_SQL)] = replacement
    with pytest.raises(AssertionError):
        _assert_semantic_defaults(changed)


@pytest.mark.parametrize("dialect", ["sqlite", "mysql"])
def test_baseline_rejects_non_postgresql_before_ddl(
    dialect: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    migration, operations = bind_baseline(monkeypatch, dialect=dialect)
    with pytest.raises(RuntimeError, match="The MVP baseline requires PostgreSQL"):
        migration.upgrade()
    assert operations.bind_requests == 1
    assert operations.bind.reads == []
    assert operations.statements == []


def test_baseline_downgrade_refuses_before_database_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, operations = bind_baseline(monkeypatch)
    assert_downgrade_refuses(migration, operations)


@pytest.mark.parametrize(
    "extra",
    [
        r'ALTER TABLE public.attachments ALTER COLUMN U&"created_\0061t" '
        "SET DEFAULT clock_timestamp()",
        r'ALTER TABLE public.U&"\0061ttachments" ALTER COLUMN created_at '
        "DROP DEFAULT",
        'ALTER TABLE public.attachments ALTER COLUMN U&"created_!0061t" '
        "UESCAPE '!' SET DEFAULT clock_timestamp()",
    ],
    ids=("encoded-column", "encoded-table", "explicit-escape-character"),
)
def test_baseline_semantic_contract_rejects_encoded_identifier_overrides(
    extra: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, operations = capture_baseline(monkeypatch)
    with pytest.raises(AssertionError):
        _assert_semantic_defaults([*operations.statements, extra])
