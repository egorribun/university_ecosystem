"""AUD-278: the fresh-only baseline includes the event search GIN index.

There is no existing index to repair concurrently on an empty schema. Assert
the actual recorded baseline DDL rather than loading a deleted upgrade.
"""

from __future__ import annotations

import pytest

from tests.fixtures.baseline_migration import (
    assert_exact_statements,
    capture_baseline,
)

GIN_INDEX_SQL = (
    "CREATE INDEX ix_events_search_vector ON public.events USING gin (search_vector)"
)
_SEARCH_VECTOR = (
    "    search_vector tsvector GENERATED ALWAYS AS "
    "(to_tsvector('simple'::regconfig, (((((((((((((((COALESCE(title, "
    "''::character varying))::text || ' '::text) || COALESCE(description, "
    "''::text)) || ' '::text) || (COALESCE(location, ''::character "
    "varying))::text) || ' '::text) || (COALESCE(title_en, ''::character "
    "varying))::text) || ' '::text) || COALESCE(description_en, ''::text)) || ' "
    "'::text) || (COALESCE(location_en, ''::character varying))::text) || ' "
    "'::text) || COALESCE(about, ''::text)) || ' '::text) || COALESCE(about_en, "
    "''::text)))) STORED,"
)


def _assert_search_index(statements: list[str]) -> None:
    tables = [
        sql for sql in statements if sql.startswith("CREATE TABLE public.events (")
    ]
    assert len(tables) == 1
    assert [line for line in tables[0].splitlines() if "search_vector" in line] == [
        _SEARCH_VECTOR
    ]
    assert_exact_statements(
        (sql for sql in statements if "search_vector" in sql and sql != tables[0]),
        [GIN_INDEX_SQL],
    )
    assert statements.index(tables[0]) < statements.index(GIN_INDEX_SQL)
    assert not any(
        sql.upper().startswith(("DROP ", "UPDATE ", "DELETE ")) for sql in statements
    )


def test_baseline_creates_exactly_one_gin_after_generated_search_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, operations = capture_baseline(monkeypatch)
    _assert_search_index(operations.statements)


@pytest.mark.parametrize(
    "mutation",
    ["missing", "duplicate", "btree", "wrong_column", "expression", "drop", "order"],
)
def test_search_index_contract_rejects_missing_or_changed_search_ddl(
    monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    _, operations = capture_baseline(monkeypatch)
    changed = list(operations.statements)
    if mutation == "missing":
        changed.remove(GIN_INDEX_SQL)
    elif mutation == "duplicate":
        changed.append(GIN_INDEX_SQL)
    elif mutation == "btree":
        changed[changed.index(GIN_INDEX_SQL)] = GIN_INDEX_SQL.replace("gin", "btree")
    elif mutation == "wrong_column":
        changed[changed.index(GIN_INDEX_SQL)] = GIN_INDEX_SQL.replace(
            "(search_vector)", "(title)"
        )
    elif mutation == "expression":
        changed = [
            sql.replace("COALESCE(about_en,", "COALESCE(about,") for sql in changed
        ]
    elif mutation == "drop":
        changed.append("DROP INDEX ix_events_search_vector")
    else:
        changed.remove(GIN_INDEX_SQL)
        changed.insert(0, GIN_INDEX_SQL)
    assert changed != operations.statements
    with pytest.raises(AssertionError):
        _assert_search_index(changed)
