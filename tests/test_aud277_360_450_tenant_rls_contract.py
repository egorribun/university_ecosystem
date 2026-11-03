"""Executed baseline tenant RLS contracts and the mapped news write path.

SQL recording checks the real upgrade's emitted statements, not PostgreSQL's
runtime enforcement. The independent expected predicates remain fail-closed:
role-only bypass, non-null tenant scope, restrictive message isolation and
matching USING/WITH CHECK predicates.
"""

from __future__ import annotations

import importlib.util
import re
from contextlib import nullcontext
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import insert
from sqlalchemy.dialects import postgresql

from tests.fixtures.baseline_migration import (
    assert_baseline_operation_kinds,
    assert_downgrade_refuses,
    assert_exact_statements,
    bind_baseline,
    capture_baseline,
    table_statements,
)

# Compatibility only: the existing password-preflight integration fixture
# imports this historical recorder for a minimal users schema. Keep its current
# deleted-revision failure explicit until that fixture is redesigned; do not
# substitute full public-schema baseline DDL here.
ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "alembic/versions/202607230001_multi_tenant_rls.py"


def _load_migration(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"audit_{path.stem}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def capture_tenant_upgrade(
    monkeypatch: pytest.MonkeyPatch,
    tables: tuple[str, ...] | None = None,
    *,
    missing_tenant_column: bool = False,
    tenants_present: bool = True,
    dialect: str = "postgresql",
) -> tuple[ModuleType, list[str], list[Any]]:
    """Run the historical upgrade against an inspector/DDL recording adapter."""
    migration = _load_migration(MIGRATION)
    selected = tables if tables is not None else migration.CORE_TABLES
    statements: list[str] = []
    columns: list[Any] = []
    bind = SimpleNamespace(dialect=SimpleNamespace(name=dialect))
    inspector = SimpleNamespace(
        get_table_names=lambda: [
            *(["tenants"] if tenants_present else []),
            *selected,
        ],
        get_columns=lambda _name: []
        if missing_tenant_column
        else [{"name": "tenant_id"}],
    )

    class Operations:
        def get_bind(self) -> Any:
            return bind

        def execute(self, statement: Any) -> None:
            statements.append(str(statement))

        def add_column(self, _name: str, column: Any) -> None:
            columns.append(column)

        def create_table(self, name: str, *_args: Any, **_kwargs: Any) -> None:
            statements.append(f"-- create_table {name}")

        def get_context(self) -> Any:
            return self

        def autocommit_block(self) -> Any:
            return nullcontext()

        def create_index(self, *args: Any, **_kwargs: Any) -> None:
            statements.append(f"-- create_index {args[0]} {args[1]}")

    monkeypatch.setattr(migration, "op", Operations())
    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: inspector)
    migration.upgrade()
    return migration, statements, columns


_TENANT_TABLES = (
    "users",
    "groups",
    "schedule",
    "events",
    "chats",
    "messages",
    "news",
    "stories",
    "notifications",
)
_TENANT_PREDICATE = (
    "((pg_has_role(CURRENT_USER, 'ue_rls_bypass'::name, 'MEMBER'::text) OR "
    "((tenant_id IS NOT NULL) AND (tenant_id = "
    "(NULLIF(current_setting('app.current_tenant'::text, true), ''::text))::uuid))))"
)
_ROLE_SQL = (
    "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = "
    "'ue_rls_bypass') THEN CREATE ROLE ue_rls_bypass NOLOGIN; END IF; END $$"
)
_STAMP_FUNCTION_SQL = (
    "CREATE FUNCTION public.ue_rls_assign_session_tenant() RETURNS trigger\n"
    "    LANGUAGE plpgsql\n"
    "    AS $$ BEGIN IF NEW.tenant_id IS NULL THEN NEW.tenant_id := "
    "NULLIF(current_setting('app.current_tenant', true), '')::uuid; "
    "END IF; RETURN NEW; END $$"
)
_MESSAGE_PARTICIPANT_SQL = (
    "CREATE POLICY messages_participant_isolation ON public.messages "
    "USING ((chat_id IN ( SELECT chat_participants.chat_id\n"
    "   FROM public.chat_participants\n"
    "  WHERE (chat_participants.user_id = "
    "(current_setting('app.current_user_id'::text, true))::uuid))))"
)
_TENANTS_TABLE_SQL = """
CREATE TABLE public.tenants (
    id uuid NOT NULL,
    name character varying(256) NOT NULL,
    slug character varying(64) NOT NULL,
    domain character varying(256),
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT tenants_pkey PRIMARY KEY (id)
)
"""


def _tenant_security_statements(statements: list[str]) -> list[str]:
    names = "|".join(_TENANT_TABLES)
    target = rf'(?:(?:"public"|public)\.)?"?(?:{names})"?(?=\s|[,;]|$)'
    flags = re.ASCII | re.IGNORECASE | re.DOTALL
    policy = re.compile(rf"\b(?:CREATE|ALTER|DROP) POLICY\b.*?\bON {target}", flags)
    trigger = re.compile(
        rf"\b(?:CREATE|ALTER|DROP) (?:CONSTRAINT )?TRIGGER\b.*?\bON {target}", flags
    )
    table_control = re.compile(
        rf"\bALTER TABLE(?: ONLY)? {target}.*?"
        r"\b(?:ROW LEVEL SECURITY|(?:ENABLE|DISABLE).*?TRIGGER|"
        r"RENAME|OWNER TO|SET SCHEMA)\b",
        flags,
    )
    table_removal = re.compile(
        rf"\b(?:DROP|TRUNCATE) TABLE (?:(?:IF EXISTS|ONLY) )*{target}", flags
    )
    return [
        sql
        for sql in statements
        if (
            "ue_rls_" in sql.lower()
            or policy.search(sql)
            or trigger.search(sql)
            or table_control.search(sql)
            or table_removal.search(sql)
        )
    ]


def _expected_tenant_security() -> list[str]:
    expected = [_ROLE_SQL, _STAMP_FUNCTION_SQL, _MESSAGE_PARTICIPANT_SQL]
    for table in _TENANT_TABLES:
        policy_type = " AS RESTRICTIVE" if table == "messages" else ""
        expected.extend(
            (
                f"ALTER TABLE ONLY public.{table} FORCE ROW LEVEL SECURITY",
                f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY",
                f"CREATE POLICY tenant_isolation_policy ON public.{table}"
                f"{policy_type} USING {_TENANT_PREDICATE} "
                f"WITH CHECK {_TENANT_PREDICATE}",
                f"CREATE TRIGGER ue_rls_assign_tenant BEFORE INSERT ON public.{table} "
                "FOR EACH ROW EXECUTE FUNCTION public.ue_rls_assign_session_tenant()",
            )
        )
    return expected


def _assert_tenant_schema(statements: list[str]) -> None:
    expected_tenants = [
        _TENANTS_TABLE_SQL,
        "CREATE UNIQUE INDEX ix_tenants_domain ON public.tenants USING btree (domain)",
        "CREATE INDEX ix_tenants_is_active ON public.tenants USING btree (is_active)",
        "CREATE UNIQUE INDEX ix_tenants_slug ON public.tenants USING btree (slug)",
    ]
    expected_indexes = []
    expected_foreign_keys = []
    validated_tables = []
    for table in _TENANT_TABLES:
        creates = [
            sql
            for sql in statements
            if sql.startswith(f"CREATE TABLE public.{table} (")
        ]
        assert len(creates) == 1
        tenant_columns = [
            line.strip().removesuffix(",")
            for line in creates[0].splitlines()
            if re.match(r'^\s*"?tenant_id"?\s', line, re.ASCII | re.IGNORECASE)
        ]
        assert tenant_columns == ["tenant_id uuid"], (
            f"Unexpected {table}.tenant_id contract"
        )
        validated_tables.append(creates[0])
        only = "" if table == "notifications" else "ONLY "
        foreign_key = (
            f"ALTER TABLE {only}public.{table}\n"
            f"    ADD CONSTRAINT {table}_tenant_id_fkey FOREIGN KEY (tenant_id) "
            "REFERENCES public.tenants(id) ON DELETE CASCADE"
        )
        expected_tenants.append(foreign_key)
        expected_foreign_keys.append(foreign_key)
        index_only = "ONLY " if table == "notifications" else ""
        expected_indexes.append(
            f"CREATE INDEX ix_{table}_tenant_id ON {index_only}public.{table} "
            "USING btree (tenant_id)"
        )
    assert_exact_statements(table_statements(statements, "tenants"), expected_tenants)
    tenant_mentions = [
        sql
        for sql in table_statements(statements, *_TENANT_TABLES)
        if re.search(r"\btenant_id\b", sql, re.ASCII | re.IGNORECASE)
    ]
    expected_policies = [
        sql
        for sql in _expected_tenant_security()
        if sql.startswith("CREATE POLICY tenant_isolation_policy ")
    ]
    assert_exact_statements(
        tenant_mentions,
        [
            *validated_tables,
            *expected_foreign_keys,
            *expected_indexes,
            *expected_policies,
        ],
    )


def _assert_tenant_contract(statements: list[str]) -> None:
    assert_baseline_operation_kinds(statements)
    security = _tenant_security_statements(statements)
    assert_exact_statements(security, _expected_tenant_security())
    assert not any("app.bypass_rls" in sql.lower() for sql in statements)
    assert not any("default_permissive_policy" in sql.lower() for sql in statements)
    assert not any("USING (true)" in sql for sql in security)
    _assert_tenant_schema(statements)
    function_position = statements.index(_STAMP_FUNCTION_SQL)
    for table in _TENANT_TABLES:
        trigger = (
            f"CREATE TRIGGER ue_rls_assign_tenant BEFORE INSERT ON public.{table} "
            "FOR EACH ROW EXECUTE FUNCTION public.ue_rls_assign_session_tenant()"
        )
        assert function_position < statements.index(trigger)


def test_aud277_removes_permissive_true_and_scopes_each_tenant_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, operations = capture_baseline(monkeypatch)
    _assert_tenant_contract(operations.statements)


def test_aud360_mapped_news_insert_omits_nullable_migration_owned_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.database import Base
    from app.core.db.retained_table_metadata import build_migration_metadata
    from app.models.news import News

    migration, operations = capture_baseline(monkeypatch)
    _assert_tenant_schema(operations.statements)
    assert migration.revision == "202611020000"

    runtime_table = Base.metadata.tables["news"]
    assert "tenant_id" not in runtime_table.c
    retained = (
        build_migration_metadata(Base.metadata, dialect_name="postgresql")
        .tables["news"]
        .c.tenant_id
    )
    assert retained.nullable is True
    assert retained.server_default is None
    assert retained.info["migration_owned_by_revision"] == migration.revision

    compiled = (
        insert(News)
        .values(title="A title", content="A body")
        .compile(dialect=postgresql.dialect())
    )
    assert "tenant_id" not in compiled.params
    assert "tenant_id" not in str(compiled)


def test_baseline_creates_tenants_and_partitioned_tenant_indexes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, operations = capture_baseline(monkeypatch)
    _assert_tenant_schema(operations.statements)


def test_baseline_downgrade_refuses_before_removing_tenant_controls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, operations = bind_baseline(monkeypatch)
    assert_downgrade_refuses(migration, operations)


def test_non_postgres_baseline_refuses_before_catalog_or_ddl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, operations = bind_baseline(monkeypatch, dialect="sqlite")
    with pytest.raises(RuntimeError, match="The MVP baseline requires PostgreSQL"):
        migration.upgrade()
    assert operations.bind_requests == 1
    assert operations.bind.reads == []
    assert operations.statements == []


@pytest.mark.parametrize("mutation", ["missing", "duplicate"])
def test_tenant_contract_rejects_missing_or_duplicate_security_statements(
    monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    _, operations = capture_baseline(monkeypatch)
    _assert_tenant_contract(operations.statements)
    for statement in _tenant_security_statements(operations.statements):
        changed = list(operations.statements)
        if mutation == "missing":
            changed.remove(statement)
        else:
            changed.append(statement)
        with pytest.raises(AssertionError):
            _assert_tenant_contract(changed)


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("tenant_id IS NOT NULL", "tenant_id IS NULL"),
        ("ON public.messages AS RESTRICTIVE", "ON public.messages AS PERMISSIVE"),
        (f"WITH CHECK {_TENANT_PREDICATE}", "WITH CHECK (true)"),
        ("BEFORE INSERT ON public.news", "AFTER INSERT ON public.news"),
        ("tenant_id uuid", "tenant_id uuid DEFAULT gen_random_uuid()"),
        ("CREATE ROLE ue_rls_bypass NOLOGIN", "CREATE ROLE ue_rls_bypass LOGIN"),
        (
            "pg_has_role(CURRENT_USER, 'ue_rls_bypass'::name, 'MEMBER'::text)",
            "current_setting('app.bypass_rls', true) = 'true'",
        ),
        (
            "current_setting('app.current_user_id'::text, true)",
            "current_setting('app.current_tenant'::text, true)",
        ),
    ],
    ids=(
        "non-null-tenant",
        "restrictive-messages",
        "with-check-scope",
        "before-insert-stamp",
        "no-tenant-default",
        "nologin-bypass-role",
        "no-setting-bypass",
        "participant-user-scope",
    ),
)
def test_tenant_contract_rejects_weakened_security(
    monkeypatch: pytest.MonkeyPatch, before: str, after: str
) -> None:
    _, operations = capture_baseline(monkeypatch)
    _assert_tenant_contract(operations.statements)
    changed = [sql.replace(before, after) for sql in operations.statements]
    assert changed != operations.statements
    with pytest.raises(AssertionError):
        _assert_tenant_contract(changed)


@pytest.mark.parametrize(
    "extra",
    [
        'CREATE POLICY allow_all ON public."news" USING (true)',
        "CREATE POLICY allow_all ON NEWS USING (true)",
        "ALTER POLICY tenant_isolation_policy ON public.news USING (true)",
        "DROP POLICY messages_participant_isolation ON public.messages",
        "ALTER TABLE public.news ALTER COLUMN tenant_id SET NOT NULL",
        "ALTER TABLE public.news ALTER COLUMN tenant_id SET DEFAULT gen_random_uuid()",
        "ALTER TABLE public.news RENAME COLUMN tenant_id TO old_tenant_id",
        "ALTER TABLE PUBLIC.NEWS DISABLE ROW LEVEL SECURITY",
        "ALTER TABLE news DISABLE TRIGGER USER",
        "DROP TRIGGER ue_rls_assign_tenant ON public.news",
        "CREATE INDEX extra_tenant_index ON public.news (tenant_id)",
        "DROP INDEX public.ix_news_tenant_id",
        "DROP TABLE public.news",
    ],
)
def test_tenant_contract_rejects_append_only_control_overrides(
    monkeypatch: pytest.MonkeyPatch, extra: str
) -> None:
    _, operations = capture_baseline(monkeypatch)
    _assert_tenant_contract(operations.statements)
    with pytest.raises(AssertionError):
        _assert_tenant_contract([*operations.statements, extra])
