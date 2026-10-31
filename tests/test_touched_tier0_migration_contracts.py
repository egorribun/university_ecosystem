"""Focused fail-closed contracts for the recent Tier-0 migration revisions."""

from __future__ import annotations

import importlib.util
import re
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import sqlalchemy as sa

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ROOT / "alembic" / "versions"


def _load_revision(filename: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, VERSIONS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _CatalogResult:
    def __init__(self, *, scalar: Any = None, rows: list[dict[str, Any]] | None = None):
        self._scalar = scalar
        self._rows = [] if rows is None else rows

    def scalar_one(self) -> Any:
        return self._scalar

    def mappings(self) -> list[dict[str, Any]]:
        return self._rows


class _CatalogBind:
    def __init__(
        self, *, schema: Any = "synthetic_schema", dialect: str = "postgresql"
    ):
        self.dialect = SimpleNamespace(name=dialect)
        self.schema = schema
        self.statements: list[str] = []
        self.constraint_flags = [{"condeferrable": False, "condeferred": False}]

    def execute(self, statement: Any, _parameters: dict[str, Any] | None = None):
        sql = str(statement)
        self.statements.append(sql)
        if "SELECT current_schema()" in sql:
            return _CatalogResult(scalar=self.schema)
        if "FROM pg_catalog.pg_constraint" in sql:
            return _CatalogResult(rows=self.constraint_flags)
        raise AssertionError("unexpected catalog query in migration guard test")


class _CatalogInspector:
    def __init__(self, schema: str = "synthetic_schema"):
        self.schema = schema
        self.constraint_flags = [{"condeferrable": False, "condeferred": False}]
        self.columns = [
            {"name": "id", "type": sa.Uuid(), "nullable": False, "default": None},
            {
                "name": "storage_url",
                "type": sa.String(length=2048),
                "nullable": False,
                "default": None,
            },
            {
                "name": "owner_user_id",
                "type": sa.Uuid(),
                "nullable": True,
                "default": None,
            },
            {
                "name": "news_id",
                "type": sa.Uuid(),
                "nullable": True,
                "default": None,
            },
            {
                "name": "created_at",
                "type": sa.DateTime(timezone=True),
                "nullable": False,
                "default": "now()",
            },
        ]
        for column in self.columns:
            column.update(identity=None, computed=None)
        self.primary_key = {"constrained_columns": ["id"], "dialect_options": {}}
        self.unique_constraints = [
            {
                "name": "uq_news_media_asset_storage_url",
                "column_names": ["storage_url"],
                "dialect_options": {},
            },
            {
                "name": "uq_news_media_asset_news_id",
                "column_names": ["news_id"],
                "dialect_options": {},
            },
        ]
        self.foreign_keys = [
            {
                "name": "news_media_assets_owner_user_id_fkey",
                "constrained_columns": ["owner_user_id"],
                "referred_schema": None,
                "referred_table": "users",
                "referred_columns": ["id"],
                "options": {"ondelete": "SET NULL"},
            },
            {
                "name": "news_media_assets_news_id_fkey",
                "constrained_columns": ["news_id"],
                "referred_schema": schema,
                "referred_table": "news",
                "referred_columns": ["id"],
                "options": {"ondelete": "SET NULL"},
            },
        ]
        self.check_constraints: list[dict[str, Any]] = []
        self.indexes = [
            {
                "name": "ix_news_media_assets_owner_user_id",
                "column_names": ["owner_user_id"],
                "unique": False,
                "duplicates_constraint": None,
                "dialect_options": None,
                "expressions": None,
                "include_columns": None,
                "column_sorting": None,
            }
        ]

    def has_table(self, _table: str, schema: str | None = None) -> bool:
        assert schema == self.schema
        return True

    def get_columns(self, _table: str, schema: str | None = None):
        assert schema == self.schema
        return self.columns

    def get_pk_constraint(self, _table: str, schema: str | None = None):
        assert schema == self.schema
        return self.primary_key

    def get_unique_constraints(self, _table: str, schema: str | None = None):
        assert schema == self.schema
        return self.unique_constraints

    def get_foreign_keys(self, _table: str, schema: str | None = None):
        assert schema == self.schema
        return self.foreign_keys

    def get_check_constraints(self, _table: str, schema: str | None = None):
        assert schema == self.schema
        return self.check_constraints

    def get_indexes(self, _table: str, schema: str | None = None):
        assert schema == self.schema
        return self.indexes


class _MigrationOperations:
    def __init__(self, bind: _CatalogBind | None, *, as_sql: bool = False):
        self._bind = bind
        self._context = SimpleNamespace(as_sql=as_sql)
        self.get_bind_calls = 0
        self.schema_writes: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def get_context(self):
        return self._context

    def get_bind(self):
        self.get_bind_calls += 1
        return self._bind

    def execute(self, *args: Any, **kwargs: Any) -> None:
        self.schema_writes.append(("execute", args, kwargs))

    def create_table(self, *args: Any, **kwargs: Any) -> None:
        self.schema_writes.append(("create_table", args, kwargs))

    def create_index(self, *args: Any, **kwargs: Any) -> None:
        self.schema_writes.append(("create_index", args, kwargs))

    def drop_table(self, *args: Any, **kwargs: Any) -> None:
        self.schema_writes.append(("drop_table", args, kwargs))


def _bind_news_migration(
    monkeypatch: pytest.MonkeyPatch,
    *,
    inspector: _CatalogInspector | None = None,
    bind: _CatalogBind | None = None,
    as_sql: bool = False,
):
    migration = _load_revision(
        "202610120002_add_news_media_asset_ownership.py",
        "news_media_asset_ownership_contract_test",
    )
    operations = _MigrationOperations(bind, as_sql=as_sql)
    monkeypatch.setattr(migration, "op", operations)
    if inspector is not None:
        if bind is not None:
            # The synthetic catalog SELECT must use the inspector's same metadata.
            bind.constraint_flags = inspector.constraint_flags
        monkeypatch.setattr(migration.sa, "inspect", lambda _bind: inspector)
    return migration, operations


def test_dnd_wall_clock_downgrade_refuses_to_invent_lost_offsets() -> None:
    migration = _load_revision(
        "202610120001_dnd_wall_clock_time.py", "dnd_wall_clock_contract_test"
    )
    assert migration.downgrade_policy == "irreversible"
    expected = "quiet-hour wall-clock conversion discards per-value TIMETZ offsets"
    assert migration.downgrade_reason == expected
    with pytest.raises(RuntimeError, match=re.escape(expected)):
        migration.downgrade()


@pytest.mark.parametrize(
    "invalid_schema", [None, "", 17], ids=["null", "empty", "non-string"]
)
def test_news_media_migration_rejects_unresolved_current_schema(
    monkeypatch: pytest.MonkeyPatch, invalid_schema: Any
) -> None:
    bind = _CatalogBind(schema=invalid_schema)
    migration, operations = _bind_news_migration(monkeypatch, bind=bind)

    with pytest.raises(RuntimeError, match="Cannot resolve current schema"):
        migration.upgrade()

    assert operations.schema_writes == []
    assert bind.statements == ["SELECT current_schema()"]


def test_news_media_migration_rejects_offline_execution_before_binding() -> None:
    migration = _load_revision(
        "202610120002_add_news_media_asset_ownership.py",
        "news_media_asset_ownership_offline_contract_test",
    )
    operations = _MigrationOperations(None, as_sql=True)
    migration.op = operations

    with pytest.raises(RuntimeError, match="requires online PostgreSQL"):
        migration.upgrade()

    assert operations.get_bind_calls == 0
    assert operations.schema_writes == []


def test_news_media_migration_rejects_non_postgresql_without_schema_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bind = _CatalogBind(dialect="sqlite")
    migration, operations = _bind_news_migration(monkeypatch, bind=bind)

    with pytest.raises(RuntimeError, match="requires PostgreSQL"):
        migration.upgrade()

    assert operations.get_bind_calls == 1
    assert operations.schema_writes == []
    assert bind.statements == []


def test_news_media_migration_accepts_exact_existing_catalog_without_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspector = _CatalogInspector()
    bind = _CatalogBind()
    migration, operations = _bind_news_migration(
        monkeypatch, inspector=inspector, bind=bind
    )

    migration.upgrade()

    assert operations.schema_writes == []
    assert bind.statements[0] == "SELECT current_schema()"
    assert any(
        "FROM pg_catalog.pg_constraint" in statement for statement in bind.statements
    )


def test_news_media_upgrade_emits_expected_ddl_when_table_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bind = _CatalogBind()
    migration, operations = _bind_news_migration(monkeypatch, bind=bind)
    inspector_calls: list[tuple[str, str | None]] = []

    def has_table(table: str, schema: str | None = None) -> bool:
        inspector_calls.append((table, schema))
        return False

    monkeypatch.setattr(
        migration.sa,
        "inspect",
        lambda _bind: SimpleNamespace(has_table=has_table),
    )

    migration.upgrade()

    assert inspector_calls == [("news_media_assets", "synthetic_schema")]
    assert operations.get_bind_calls == 1
    assert bind.statements == ["SELECT current_schema()"]
    assert [kind for kind, _args, _kwargs in operations.schema_writes] == [
        "execute",
        "execute",
        "create_table",
        "create_index",
    ]
    execute_statements = [
        str(args[0])
        for kind, args, _kwargs in operations.schema_writes
        if kind == "execute"
    ]
    assert execute_statements == [
        "SET LOCAL lock_timeout = '10s'",
        "SET LOCAL statement_timeout = '60s'",
    ]

    create_table_kind, create_table_args, create_table_kwargs = (
        operations.schema_writes[2]
    )
    assert create_table_kind == "create_table"
    assert create_table_kwargs == {}
    assert create_table_args[0] == "news_media_assets"
    # Alembic binds emitted constraints to their Table before DDL compilation.
    table = sa.Table(create_table_args[0], sa.MetaData(), *create_table_args[1:])
    columns = {column.name: column for column in table.columns}
    assert tuple(columns) == (
        "id",
        "storage_url",
        "owner_user_id",
        "news_id",
        "created_at",
    )
    assert isinstance(columns["id"].type, sa.UUID)
    assert columns["id"].nullable is False
    assert columns["id"].server_default is None
    assert isinstance(columns["storage_url"].type, sa.String)
    assert columns["storage_url"].type.length == 2048
    assert columns["storage_url"].nullable is False
    assert columns["storage_url"].server_default is None
    assert isinstance(columns["owner_user_id"].type, sa.UUID)
    assert columns["owner_user_id"].nullable is True
    assert columns["owner_user_id"].server_default is None
    assert isinstance(columns["news_id"].type, sa.UUID)
    assert columns["news_id"].nullable is True
    assert columns["news_id"].server_default is None
    assert isinstance(columns["created_at"].type, sa.DateTime)
    assert columns["created_at"].type.timezone is True
    assert columns["created_at"].nullable is False
    assert str(columns["created_at"].server_default.arg) == "now()"

    constraints = list(table.constraints)
    assert len(constraints) == 5
    primary_keys = [
        item for item in constraints if isinstance(item, sa.PrimaryKeyConstraint)
    ]
    assert len(primary_keys) == 1
    assert tuple(column.name for column in primary_keys[0].columns) == ("id",)
    unique_constraints = [
        item for item in constraints if isinstance(item, sa.UniqueConstraint)
    ]
    assert {
        (item.name, tuple(column.name for column in item.columns))
        for item in unique_constraints
    } == {
        ("uq_news_media_asset_storage_url", ("storage_url",)),
        ("uq_news_media_asset_news_id", ("news_id",)),
    }
    foreign_keys = [
        item for item in constraints if isinstance(item, sa.ForeignKeyConstraint)
    ]
    assert {
        (
            tuple(item.column_keys),
            tuple(element.target_fullname for element in item.elements),
            item.ondelete,
        )
        for item in foreign_keys
    } == {
        (("owner_user_id",), ("users.id",), "SET NULL"),
        (("news_id",), ("news.id",), "SET NULL"),
    }

    create_index_kind, index_args, index_kwargs = operations.schema_writes[3]
    assert create_index_kind == "create_index"
    assert index_kwargs == {}
    assert index_args == (
        "ix_news_media_assets_owner_user_id",
        "news_media_assets",
        ["owner_user_id"],
    )


def test_news_media_downgrade_retains_assets_without_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, operations = _bind_news_migration(monkeypatch)

    result = migration.downgrade()

    assert result is None
    assert operations.get_bind_calls == 0
    assert operations.schema_writes == []


def _bad_catalog_cases() -> list[tuple[str, Callable[[_CatalogInspector], None], str]]:
    return [
        (
            "unexpected-columns",
            lambda catalog: catalog.columns[0].update(name="unexpected"),
            "Existing news_media_assets has unexpected columns",
        ),
        (
            "uuid-type",
            lambda catalog: catalog.columns[0].update(type=sa.String(length=36)),
            "Existing news_media_assets.id is incompatible",
        ),
        (
            "storage-url-length",
            lambda catalog: catalog.columns[1].update(type=sa.String(length=512)),
            "Existing news_media_assets.storage_url is incompatible",
        ),
        (
            "created-at-timezone",
            lambda catalog: catalog.columns[4].update(type=sa.DateTime(timezone=False)),
            "Existing news_media_assets.created_at is incompatible",
        ),
        (
            "nullability",
            lambda catalog: catalog.columns[1].update(nullable=True),
            "Existing news_media_assets.storage_url is incompatible",
        ),
        (
            "unexpected-default",
            lambda catalog: catalog.columns[1].update(
                default="'synthetic'::character varying"
            ),
            "Existing news_media_assets.storage_url has an unexpected default",
        ),
        (
            "wrong-created-at-default",
            lambda catalog: catalog.columns[4].update(default="CURRENT_TIMESTAMP"),
            "Existing news_media_assets.created_at has an unexpected default",
        ),
        (
            "generated-column",
            lambda catalog: catalog.columns[1].update(
                computed={"sqltext": "'synthetic'"}
            ),
            "Existing news_media_assets.storage_url has generated-column metadata",
        ),
        (
            "primary-key-columns",
            lambda catalog: catalog.primary_key.update(
                constrained_columns=["storage_url"]
            ),
            "Existing news_media_assets has an unexpected primary key",
        ),
        (
            "primary-key-options",
            lambda catalog: catalog.primary_key.update(
                dialect_options={"fillfactor": 80}
            ),
            "Existing news_media_assets has modified primary key options",
        ),
        (
            "unique-constraint-options",
            lambda catalog: catalog.unique_constraints[0].update(
                dialect_options={"postgresql_nulls_not_distinct": True}
            ),
            "Existing news_media_assets has modified unique constraints",
        ),
        (
            "unique-constraint-set",
            lambda catalog: catalog.unique_constraints[0].update(
                name="unapproved_unique"
            ),
            "Existing news_media_assets has unexpected unique constraints",
        ),
        (
            "deferrable-constraint",
            lambda catalog: catalog.__setattr__(
                "constraint_flags", [{"condeferrable": True, "condeferred": False}]
            ),
            "Existing news_media_assets has deferrable constraints",
        ),
        (
            "external-foreign-key-schema",
            lambda catalog: catalog.foreign_keys[0].update(
                referred_schema="other_schema"
            ),
            "Existing news_media_assets has an external foreign key",
        ),
        (
            "foreign-key-shape",
            lambda catalog: catalog.foreign_keys[0]["options"].update(
                ondelete="CASCADE"
            ),
            "Existing news_media_assets has unexpected foreign keys",
        ),
        (
            "check-constraint",
            lambda catalog: catalog.check_constraints.append(
                {"name": "unexpected_check"}
            ),
            "Existing news_media_assets has unexpected check constraints",
        ),
        (
            "modified-index-options",
            lambda catalog: catalog.indexes[0].update(
                dialect_options={"fillfactor": 80}
            ),
            "Existing news_media_assets has modified indexes",
        ),
        (
            "modified-index-expression",
            lambda catalog: catalog.indexes[0].update(
                expressions=["owner_user_id::text"]
            ),
            "Existing news_media_assets has modified indexes",
        ),
        (
            "index-set",
            lambda catalog: catalog.indexes[0].update(name="unapproved_index"),
            "Existing news_media_assets has unexpected indexes",
        ),
    ]


@pytest.mark.parametrize(
    ("case", "mutate", "expected_error"),
    _bad_catalog_cases(),
    ids=[case[0] for case in _bad_catalog_cases()],
)
def test_news_media_upgrade_fails_closed_on_catalog_drift_before_writes(
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    mutate: Callable[[_CatalogInspector], None],
    expected_error: str,
) -> None:
    inspector = _CatalogInspector()
    mutate(inspector)
    bind = _CatalogBind()
    migration, operations = _bind_news_migration(
        monkeypatch, inspector=inspector, bind=bind
    )

    with pytest.raises(RuntimeError, match=re.escape(expected_error)):
        migration.upgrade()

    assert operations.schema_writes == [], case


def test_merge_noop_migration_upgrade_and_downgrade_are_covered() -> None:
    migration = _load_revision(
        "202509010001_merge_push_topics_and_email_heads.py",
        "merge_noop_migration_coverage_contract",
    )

    assert migration.upgrade() is None
    assert migration.downgrade() is None


def test_groups_key_offline_rendering_does_not_emit_uninspected_index_drop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Offline rendering must not emit a drop for an uninspected index."""
    from io import StringIO

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy.dialects import postgresql

    migration = _load_revision(
        "148642dd1207_fix_missing_tables.py",
        "groups_key_offline_index_contract_test",
    )
    output = StringIO()
    migration_context = MigrationContext.configure(
        dialect=postgresql.dialect(),
        opts={"as_sql": True, "output_buffer": output},
    )

    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: True)
    with Operations.context(migration_context):
        migration._postgresql_groups_id_upgrade(None)

    normalized_sql = " ".join(output.getvalue().split()).upper()
    assert (
        "ALTER TABLE GROUPS ADD COLUMN IF NOT EXISTS ID__INTEGER INTEGER"
        in normalized_sql
    )
    assert "DROP INDEX IF EXISTS IX_GROUPS_ID" not in normalized_sql
    assert (
        "ALTER TABLE GROUPS ADD CONSTRAINT GROUPS_PKEY "
        "PRIMARY KEY USING INDEX GROUPS_PKEY_IDX"
    ) in normalized_sql
