"""Adversarial controls for the baseline recorder's bounded SQL snapshots."""

from __future__ import annotations

import pytest

from tests.fixtures.baseline_migration import (
    assert_baseline_operation_kinds,
    assert_exact_statements,
    capture_baseline,
    normalize_sql,
    table_statements,
)


@pytest.mark.parametrize(
    "source",
    [
        "SELECT  \t1",
        "SELECT 'a  b'",
        'SELECT "a  b"',
        "SELECT 'it''s  kept'",
        r"SELECT E'it\'s  kept'",
        "DO $$ BEGIN\n  RETURN; \nEND $$",
        "DO $fn$ a  b\n $fn$",
        "SELECT 1 -- keep  this\n  + 2",
        "SELECT /* keep  /* nested */  this */ 1",
    ],
)
def test_sql_snapshot_trims_only_outer_whitespace(source: str) -> None:
    assert normalize_sql(" \n" + source + "\n ") == source


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("SELECT 1", "SELECT  1"),
        ("SELECT 'a b'", "SELECT 'a  b'"),
        ('SELECT "a b"', 'SELECT "a  b"'),
        ("DO $$ BEGIN RETURN; END $$", "DO $$ BEGIN\nRETURN; END $$"),
        ("SELECT 1 -- keep\n+ 2", "SELECT 1 -- keep  \n+ 2"),
    ],
)
def test_exact_statement_contract_preserves_internal_whitespace(
    before: str, after: str
) -> None:
    with pytest.raises(AssertionError):
        assert_exact_statements([normalize_sql(after)], [before])


@pytest.mark.parametrize(
    "statement",
    [
        "ALTER TABLE PUBLIC.CHAT_SEND_RECEIPTS DISABLE ROW LEVEL SECURITY",
        "alter table chat_send_receipts disable row level security",
        'ALTER TABLE "public"."chat_send_receipts" DISABLE ROW LEVEL SECURITY',
    ],
)
def test_table_selector_retains_extra_case_varied_and_unqualified_ddl(
    statement: str,
) -> None:
    assert table_statements([statement], "chat_send_receipts") == [statement]


@pytest.mark.parametrize(
    "extra",
    [
        "GRANT ue_rls_bypass TO PUBLIC",
        "REVOKE ALL ON public.news FROM PUBLIC",
        "SET ROLE ue_rls_bypass",
        "RESET ALL",
        "DO $$ BEGIN EXECUTE 'SET ROLE ue_rls_bypass'; END $$",
        "SELECT set_config('row_security', 'off', false)",
        "CALL unexpected_security_procedure()",
        "CREATE EXTENSION IF NOT EXISTS unexpected_extension",
        "CREATE FUNCTION public.allow_all() RETURNS boolean "
        "LANGUAGE sql AS $$ SELECT true $$",
    ],
)
def test_global_operation_contract_rejects_extra_authority_commands(
    monkeypatch: pytest.MonkeyPatch, extra: str
) -> None:
    _, operations = capture_baseline(monkeypatch)
    with pytest.raises(AssertionError):
        assert_baseline_operation_kinds([*operations.statements, extra])


@pytest.mark.parametrize(
    "extra",
    [
        "SET session_replication_role = replica",
        "GRANT ue_rls_bypass TO PUBLIC",
    ],
)
def test_global_operation_contract_rejects_compound_statement_overrides(
    monkeypatch: pytest.MonkeyPatch, extra: str
) -> None:
    _, operations = capture_baseline(monkeypatch)
    changed = list(operations.statements)
    position = next(
        index
        for index, sql in enumerate(changed)
        if sql.startswith("CREATE TABLE public.news (")
    )
    changed[position] += "; " + extra
    with pytest.raises(AssertionError):
        assert_baseline_operation_kinds(changed)


@pytest.mark.parametrize("defect", ["missing", "duplicate", "changed", "late"])
def test_global_operation_contract_requires_exact_early_empty_schema_guard(
    monkeypatch: pytest.MonkeyPatch, defect: str
) -> None:
    _, operations = capture_baseline(monkeypatch)
    changed = list(operations.statements)
    guard = changed[2]
    assert guard.startswith("DO $baseline_empty$")
    if defect == "missing":
        del changed[2]
    elif defect == "duplicate":
        changed.insert(2, guard)
    elif defect == "changed":
        changed[2] = guard.replace("IF EXISTS (", "IF FALSE AND EXISTS (", 1)
        assert changed[2] != guard
    else:
        assert defect == "late"
        changed.remove(guard)
        changed.append(guard)
    with pytest.raises(AssertionError):
        assert_baseline_operation_kinds(changed)
