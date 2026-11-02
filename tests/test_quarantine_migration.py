"""Executed baseline contracts for the retained quarantine quota ledger."""

from __future__ import annotations

import pytest

from tests.fixtures.baseline_migration import (
    assert_baseline_operation_kinds,
    assert_downgrade_refuses,
    assert_exact_statements,
    bind_baseline,
    capture_baseline,
    normalize_sql,
    table_statements,
)

_EXPECTED_LEDGER_SQL = (
    (
        "CREATE TABLE public.quarantine_storage_scopes (\n"
        "    scope_id character varying(64) NOT NULL,\n"
        "    inventory_complete boolean DEFAULT false NOT NULL,\n"
        "    inventory_cursor text,\n"
        "    created_at timestamp with time zone DEFAULT now() NOT NULL\n"
        ")"
    ),
    (
        "CREATE TABLE public.quarantine_reservations (\n"
        "    id uuid NOT NULL,\n"
        "    scope_id character varying(64) NOT NULL,\n"
        "    object_key character varying(2048) NOT NULL,\n"
        "    size_bytes bigint NOT NULL,\n"
        "    status character varying(16) DEFAULT 'pending'::character "
        "varying NOT NULL,\n"
        "    created_at timestamp with time zone DEFAULT now() NOT NULL,\n"
        "    expires_at timestamp with time zone,\n"
        "    CONSTRAINT ck_quarantine_reservation_size CHECK ((size_bytes >= 0)),\n"
        "    CONSTRAINT ck_quarantine_reservation_status CHECK (status IN "
        "('pending', 'stored', 'deleting'))\n"
        ")"
    ),
    (
        "ALTER TABLE ONLY public.quarantine_reservations\n"
        "    ADD CONSTRAINT quarantine_reservations_pkey PRIMARY KEY (id)"
    ),
    (
        "ALTER TABLE ONLY public.quarantine_storage_scopes\n"
        "    ADD CONSTRAINT quarantine_storage_scopes_pkey PRIMARY KEY (scope_id)"
    ),
    (
        "ALTER TABLE ONLY public.quarantine_reservations\n"
        "    ADD CONSTRAINT uq_quarantine_reservation_object UNIQUE "
        "(scope_id, object_key)"
    ),
    (
        "ALTER TABLE ONLY public.quarantine_reservations\n"
        "    ADD CONSTRAINT quarantine_reservations_scope_id_fkey FOREIGN "
        "KEY (scope_id) REFERENCES public.quarantine_storage_scopes(scope_id)"
    ),
    (
        "CREATE INDEX ix_quarantine_reservations_expiry ON "
        "public.quarantine_reservations USING btree (scope_id, status, expires_at)"
    ),
)


def _assert_ledger_contract(statements: list[str]) -> None:
    assert_baseline_operation_kinds(statements)
    selected = table_statements(
        statements, "quarantine_storage_scopes", "quarantine_reservations"
    )
    assert_exact_statements(selected, _EXPECTED_LEDGER_SQL)
    table_positions = [
        selected.index(normalize_sql(sql)) for sql in _EXPECTED_LEDGER_SQL[:2]
    ]
    for sql in _EXPECTED_LEDGER_SQL[2:]:
        assert selected.index(normalize_sql(sql)) > max(table_positions)


def test_baseline_rejects_non_postgresql_without_schema_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, operations = bind_baseline(monkeypatch, dialect="sqlite")
    with pytest.raises(RuntimeError, match="The MVP baseline requires PostgreSQL"):
        migration.upgrade()
    assert operations.bind_requests == 1
    assert operations.bind.reads == []
    assert operations.statements == []


def test_baseline_emits_both_ledger_tables_and_bounded_expiry_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, operations = capture_baseline(monkeypatch)
    _assert_ledger_contract(operations.statements)


@pytest.mark.parametrize("mutation", ["missing", "duplicate"])
def test_ledger_contract_rejects_missing_or_duplicate_statements(
    monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    _, operations = capture_baseline(monkeypatch)
    _assert_ledger_contract(operations.statements)
    selected = table_statements(
        operations.statements, "quarantine_storage_scopes", "quarantine_reservations"
    )
    for statement in selected:
        changed = list(operations.statements)
        if mutation == "missing":
            changed.remove(statement)
        else:
            changed.append(statement)
        with pytest.raises(AssertionError):
            _assert_ledger_contract(changed)


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (
            "inventory_complete boolean DEFAULT false",
            "inventory_complete boolean DEFAULT true",
        ),
        ("CHECK ((size_bytes >= 0))", "CHECK ((size_bytes > 0))"),
        ("'pending'::character varying", "'stored'::character varying"),
        ("UNIQUE (scope_id, object_key)", "UNIQUE (object_key)"),
        (
            "REFERENCES public.quarantine_storage_scopes(scope_id)",
            "REFERENCES public.quarantine_storage_scopes(scope_id) ON DELETE CASCADE",
        ),
        (
            "USING btree (scope_id, status, expires_at)",
            "USING btree (expires_at, scope_id, status)",
        ),
    ],
    ids=(
        "inventory-not-complete",
        "nonnegative-size",
        "pending-by-default",
        "scope-and-object-identity",
        "quota-evidence-not-cascaded",
        "bounded-expiry-index",
    ),
)
def test_ledger_contract_rejects_quota_evidence_drift(
    monkeypatch: pytest.MonkeyPatch, before: str, after: str
) -> None:
    _, operations = capture_baseline(monkeypatch)
    _assert_ledger_contract(operations.statements)
    changed = [sql.replace(before, after) for sql in operations.statements]
    assert changed != operations.statements
    with pytest.raises(AssertionError):
        _assert_ledger_contract(changed)


def test_migration_downgrade_refuses_to_drop_quota_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, operations = bind_baseline(monkeypatch)
    assert_downgrade_refuses(migration, operations)


@pytest.mark.parametrize(
    "extra",
    [
        "ALTER TABLE QUARANTINE_STORAGE_SCOPES "
        "ALTER COLUMN inventory_complete SET DEFAULT true",
        "ALTER TABLE quarantine_reservations "
        "DROP CONSTRAINT ck_quarantine_reservation_size",
    ],
)
def test_ledger_contract_rejects_append_only_overrides(
    monkeypatch: pytest.MonkeyPatch, extra: str
) -> None:
    _, operations = capture_baseline(monkeypatch)
    _assert_ledger_contract(operations.statements)
    with pytest.raises(AssertionError):
        _assert_ledger_contract([*operations.statements, extra])
