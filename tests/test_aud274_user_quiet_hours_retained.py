"""AUD-274: the fresh-only baseline retains quiet hours in user_preferences.

The squashed baseline creates the final schema, not the removed legacy users
backfill. These recorded-call contracts do not claim PostgreSQL execution.
"""

from __future__ import annotations

import re

import pytest

from tests.fixtures.baseline_migration import (
    assert_downgrade_refuses,
    assert_exact_statements,
    bind_baseline,
    capture_baseline,
    table_statements,
)

_PREFERENCES_DDL = (
    "CREATE TABLE public.user_preferences (\n"
    "    dnd_enabled boolean DEFAULT false NOT NULL,\n"
    "    dnd_start time without time zone,\n"
    "    dnd_end time without time zone,\n"
    "    timezone character varying(64),\n"
    "    user_id uuid NOT NULL\n"
    ")",
    "ALTER TABLE ONLY public.user_preferences\n"
    "    ADD CONSTRAINT user_preferences_pkey PRIMARY KEY (user_id)",
    "ALTER TABLE ONLY public.user_preferences\n"
    "    ADD CONSTRAINT fk_user_preferences_user_id FOREIGN KEY (user_id) "
    "REFERENCES public.users(id) ON DELETE CASCADE",
)


def _assert_quiet_hours(statements: list[str]) -> None:
    assert_exact_statements(
        table_statements(statements, "user_preferences"), _PREFERENCES_DDL
    )
    users = [sql for sql in statements if sql.startswith("CREATE TABLE public.users (")]
    assert len(users) == 1
    assert (
        re.search(r"\b(?:dnd_enabled|dnd_start|dnd_end|timezone)\b", users[0]) is None
    )
    # No legacy copying, destructive DDL, or preference writes are supported.
    assert not any(
        sql.upper().startswith(("UPDATE ", "INSERT ", "DELETE ", "DROP "))
        for sql in statements
    )


def test_baseline_creates_final_quiet_hours_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, operations = capture_baseline(monkeypatch)
    _assert_quiet_hours(operations.statements)


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("dnd_enabled boolean DEFAULT false NOT NULL", "dnd_enabled boolean"),
        ("dnd_start time without time zone", "dnd_start time with time zone"),
        ("dnd_end time without time zone", "dnd_end time with time zone"),
        ("timezone character varying(64)", "timezone character varying(32)"),
        ("ON DELETE CASCADE", "ON DELETE SET NULL"),
    ],
)
def test_quiet_hours_contract_rejects_schema_drift(
    monkeypatch: pytest.MonkeyPatch, before: str, after: str
) -> None:
    _, operations = capture_baseline(monkeypatch)
    changed = [sql.replace(before, after) for sql in operations.statements]
    assert changed != operations.statements
    with pytest.raises(AssertionError):
        _assert_quiet_hours(changed)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "legacy", "drop"])
def test_quiet_hours_contract_rejects_missing_duplicate_and_legacy_operations(
    monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    _, operations = capture_baseline(monkeypatch)
    changed = list(operations.statements)
    if mutation == "missing":
        changed.remove(_PREFERENCES_DDL[0])
    elif mutation == "duplicate":
        changed.append(_PREFERENCES_DDL[0])
    elif mutation == "legacy":
        changed.append("UPDATE users SET dnd_enabled = false")
    else:
        changed.append("ALTER TABLE public.user_preferences DROP COLUMN dnd_start")
    with pytest.raises(AssertionError):
        _assert_quiet_hours(changed)


def test_baseline_downgrade_refuses_before_touching_preferences(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, operations = bind_baseline(monkeypatch)
    assert_downgrade_refuses(migration, operations)


def test_baseline_rejects_sqlite_before_touching_preferences(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration, operations = bind_baseline(monkeypatch, dialect="sqlite")
    with pytest.raises(RuntimeError, match="requires PostgreSQL"):
        migration.upgrade()
    assert operations.bind_requests == 1
    assert operations.bind.reads == []
    assert operations.statements == []
