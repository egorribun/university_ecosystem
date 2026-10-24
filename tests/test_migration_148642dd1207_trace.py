"""Contracts for the inactive, test-only expanded-DDL diagnostic."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import psycopg as pg_psycopg

from tests.helpers import migration_148642dd1207_trace as trace

SOURCE = trace.MIGRATION_PATH.read_bytes()


def _connection():
    return SimpleNamespace(dialect=pg_psycopg.dialect())


def _record(recorder, statement, *, parameters=None, executemany=False):
    connection = _connection()
    compiled = str(sa.text(statement).compile(dialect=connection.dialect))
    return recorder.before_cursor_execute(
        connection, None, compiled, parameters, None, executemany
    )


def test_source_binding_rejects_any_changed_migration_bytes() -> None:
    assert trace.git_blob_id(SOURCE) == trace.SOURCE_GIT_BLOB
    assert len(trace.reviewed_sites(SOURCE)) == 5
    with pytest.raises(trace.TraceContractError, match="source changed"):
        trace.reviewed_sites(SOURCE + b"\n")


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing_function", "Missing reviewed"),
        ("missing_constant", "exactly one"),
        ("duplicate_constant", "exactly one"),
        ("missing_execute", "remain an EXECUTE"),
        ("missing_terminator", "terminator"),
        ("duplicate_execute", "occur exactly once"),
    ],
)
def test_site_extraction_is_finite_and_fail_closed(mutation, message) -> None:
    source = SOURCE.decode()
    site = next(s for s in trace.reviewed_sites(SOURCE) if s.name == "child_fk_drop")
    if mutation == "missing_function":
        source = source.replace(
            "def _capture_groups_foreign_keys()", "def _unexpected_function()"
        )
    elif mutation == "missing_constant":
        source = source.replace("DROP CONSTRAINT %I", "UNEXPECTED OPERATION %I", 1)
    elif mutation == "duplicate_constant":
        declaration = "def _capture_groups_foreign_keys() -> None:"
        source = source.replace(
            declaration, declaration + "\n    duplicate = " + repr(site.outer_sql)
        )
    elif mutation == "missing_execute":
        source = source.replace(
            site.outer_sql, site.outer_sql.replace("EXECUTE ", "PERFORM ")
        )
    elif mutation == "missing_terminator":
        source = source.replace(site.outer_sql, site.outer_sql.replace(";", ""))
    else:
        source = source.replace(
            site.outer_sql,
            site.outer_sql.replace(site.executable, site.executable * 2),
        )
    with pytest.raises(trace.TraceContractError, match=message):
        trace._extract_sites(source)


def test_every_insertion_preserves_exact_original_sql_and_driver_escaping() -> None:
    recorder = trace.ExpandedDdlTrace(SOURCE, instrument=True)
    recorder.on_begin(None)
    for site in recorder.sites:
        ordinal = len(recorder.events)
        transformed, observation = site.instrument(ordinal)
        assert transformed.replace(observation, "", 1) == site.outer_sql
        assert transformed.count(site.executable) == 1
        result, parameters = _record(recorder, site.outer_sql)
        dialect = _connection().dialect
        assert result == str(sa.text(transformed).compile(dialect=dialect))
        assert parameters is None
        assert recorder.events[-1]["sql"] == site.outer_sql
        assert recorder.replacements[-1] == {
            "outer_ordinal": ordinal,
            "site": site.name,
        }
    with pytest.raises(trace.TraceContractError, match="nonnegative"):
        recorder.sites[0].instrument(-1)


def test_control_run_observes_but_never_modifies_known_or_other_statements() -> None:
    recorder = trace.ExpandedDdlTrace(SOURCE, instrument=False)
    for statement in [recorder.sites[0].outer_sql, "SELECT 1"]:
        expected = str(sa.text(statement).compile(dialect=_connection().dialect))
        assert _record(recorder, statement) == (expected, None)
    assert recorder.replacements == []
    with pytest.raises(trace.TraceContractError, match="instrumented run"):
        recorder.expanded_sql([])


@pytest.mark.parametrize("executemany", [False, True])
def test_reviewed_ddl_with_unexpected_bind_or_batch_fails(executemany) -> None:
    recorder = trace.ExpandedDdlTrace(SOURCE, instrument=True)
    parameters = None if executemany else {"unexpected": object()}
    with pytest.raises(trace.TraceContractError, match="acquired binds"):
        _record(
            recorder,
            recorder.sites[0].outer_sql,
            parameters=parameters,
            executemany=executemany,
        )


def test_statement_limit_and_transformation_corruption_fail_closed(monkeypatch) -> None:
    recorder = trace.ExpandedDdlTrace(SOURCE, instrument=True)
    recorder.events = [{"kind": "begin"}] * 10_000
    with pytest.raises(trace.TraceContractError, match="limit exceeded"):
        _record(recorder, "SELECT 1")
    recorder.events.clear()
    monkeypatch.setattr(
        trace.DdlSite, "instrument", lambda *_: ("changed original", "trace only")
    )
    with pytest.raises(trace.TraceContractError, match="changed original SQL"):
        _record(recorder, recorder.sites[0].outer_sql)


def _successful_inventory():
    recorder = trace.ExpandedDdlTrace(SOURCE, instrument=True)
    recorder.on_begin(None)
    rows = []
    for site in recorder.sites:
        ordinal = len(recorder.events)
        _record(recorder, site.outer_sql)
        rows.append((ordinal, site.name, "ALTER TABLE example ADD COLUMN marker int"))
    return recorder, rows


def test_expansion_preserves_order_context_and_never_includes_bound_values() -> None:
    recorder, rows = _successful_inventory()
    for statement, parameters in [
        ("SET LOCAL lock_timeout = '10s'", None),
        ("UPDATE example SET marker = 1", None),
        ("UPDATE example SET marker = :value", {"value": "not-for-artifacts"}),
        ("DO $$ BEGIN PERFORM 1; END $$", None),
        ("SELECT pg_advisory_xact_lock(824148642)", None),
        ("SELECT 1", None),
    ]:
        _record(recorder, statement, parameters=parameters)
    recorder.on_commit(None)
    output = recorder.expanded_sql(rows)
    assert output.count("ALTER TABLE example ADD COLUMN marker int;") == 5
    assert output.index("BEGIN;") < output.index("ALTER TABLE example")
    assert output.index("UPDATE example SET marker = 1;") < output.index("COMMIT;")
    assert "guard DO; body retained" in output
    assert "parameterized DML; values omitted" in output
    assert "not-for-artifacts" not in repr(recorder.events) + output
    assert "pg_advisory_xact_lock(824148642)" in output
    assert "SELECT 1;" not in output


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("no_commit", "one transaction"),
        ("no_begin", "one transaction"),
        ("rollback", "Rolled-back"),
        ("wrong_site", "does not match"),
        ("missing_site", "all five sites"),
        ("missing_outer", "no nested evidence"),
    ],
)
def test_incomplete_or_rolled_back_inventory_is_not_accepted(case, message) -> None:
    recorder, rows = _successful_inventory()
    if case != "no_commit":
        recorder.on_commit(None)
    if case == "no_begin":
        recorder.events.pop(0)
    elif case == "rollback":
        recorder.on_rollback(None)
    elif case == "wrong_site":
        ordinal, _, statement = rows[0]
        rows[0] = (ordinal, "unknown_site", statement)
    elif case == "missing_site":
        rows.pop()
    elif case == "missing_outer":
        duplicate = dict(recorder.replacements[0])
        duplicate["outer_ordinal"] = 999
        recorder.replacements.append(duplicate)
    with pytest.raises(trace.TraceContractError, match=message):
        recorder.expanded_sql(rows)


def test_non_pyformat_cursor_text_is_observed_without_percent_rewriting() -> None:
    recorder = trace.ExpandedDdlTrace(SOURCE, instrument=False)
    connection = SimpleNamespace(dialect=sa.engine.default.DefaultDialect())
    statement = "SELECT '%%' AS literal"
    assert recorder.before_cursor_execute(
        connection, None, statement, None, None, False
    ) == (statement, None)
    assert recorder.events[-1]["sql"] == statement
