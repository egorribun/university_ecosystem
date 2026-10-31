"""Security contracts for the database EXPLAIN performance gate."""

import runpy
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from sqlalchemy import Column, MetaData, Table, Text, bindparam, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from scripts import db_explain_check


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        (" SELECT * FROM users WHERE id = $1; ", "SELECT * FROM users WHERE id = $1"),
        (
            "WITH active AS (SELECT 1) SELECT * FROM active",
            "WITH active AS (SELECT 1) SELECT * FROM active",
        ),
        (
            "UPDATE users SET is_active = false WHERE id = $1",
            "UPDATE users SET is_active = false WHERE id = $1",
        ),
        (
            "SELECT * FROM users WHERE note = ';'",
            "SELECT * FROM users WHERE note = ';'",
        ),
        (
            "SELECT * FROM users WHERE id = 1 -- ; comment",
            "SELECT * FROM users WHERE id = 1 -- ; comment",
        ),
        (
            "SELECT * FROM users /* ; comment */ WHERE id = 1",
            "SELECT * FROM users /* ; comment */ WHERE id = 1",
        ),
    ],
)
def test_normalize_explainable_query_accepts_one_dml_statement(
    query: str, expected: str
) -> None:
    assert db_explain_check.normalize_explainable_query(query) == expected


@pytest.mark.parametrize(
    "query",
    [
        "",
        "DROP TABLE users",
        "SELECT 1; DROP TABLE users",
        "SELECT '\x00'",
        ";",
    ],
)
def test_normalize_explainable_query_rejects_unsafe_input(query: str) -> None:
    message = "single explainable|multiple SQL statements"
    with pytest.raises(ValueError, match=message):
        db_explain_check.normalize_explainable_query(query)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        (
            "SELECT * FROM users WHERE id = :user_id",
            "SELECT * FROM users WHERE id = $1",
        ),
        (
            "SELECT * FROM users WHERE id = ? AND email = ?",
            "SELECT * FROM users WHERE id = $1 AND email = $2",
        ),
        (
            "SELECT * FROM users WHERE id = $7 AND owner_id = $7",
            "SELECT * FROM users WHERE id = $1 AND owner_id = $1",
        ),
        (
            "SELECT id = $7 AND flag$1 AND owner_id = $2",
            "SELECT id = $1 AND flag$1 AND owner_id = $2",
        ),
        (
            "SELECT flag$4 AND id = $7 AND flag$1 AND owner_id = $2 AND flag$3",
            "SELECT flag$4 AND id = $1 AND flag$1 AND owner_id = $2 AND flag$3",
        ),
        (
            "SELECT a = $7 AND b = $3 AND c = $7 AND d = $1",
            "SELECT a = $1 AND b = $2 AND c = $1 AND d = $3",
        ),
        (
            "SELECT * FROM users WHERE user_id = :user_id "
            "AND id = $7 AND email = ? AND owner_id = :user_id",
            "SELECT * FROM users WHERE user_id = $1 "
            "AND id = $2 AND email = $3 AND owner_id = $1",
        ),
        (
            "SELECT * FROM users WHERE metadata ? 'admin' AND id = :user_id",
            "SELECT * FROM users WHERE metadata ? 'admin' AND id = $1",
        ),
        (
            "SELECT * FROM users WHERE json_data ? ? AND id = :user_id",
            "SELECT * FROM users WHERE json_data ? $1 AND id = $2",
        ),
        (
            "SELECT * FROM users WHERE search_vector @@ ?",
            "SELECT * FROM users WHERE search_vector @@ $1",
        ),
        (
            "SELECT * FROM users WHERE json_data ?| array['admin'] "
            "AND json_data ?& array['active']",
            "SELECT * FROM users WHERE json_data ?| array['admin'] "
            "AND json_data ?& array['active']",
        ),
        (
            "SELECT ':hidden ? $9' AS marker, * FROM users WHERE id = :user_id "
            "-- :comment ? $8",
            "SELECT ':hidden ? $9' AS marker, * FROM users WHERE id = $1 "
            "-- :comment ? $8",
        ),
        (
            "SELECT * FROM users WHERE id = :user_id::uuid",
            "SELECT * FROM users WHERE id = $1::uuid",
        ),
        (
            "SELECT ? FROM users",
            "SELECT $1 FROM users",
        ),
        (
            "SELECT E'escaped \\' :inside ? $9', "
            "'it''s :single ? $6' AS single_text, "
            '"quoted ""? :quoted $5""" AS ident, '
            "$tag$:dollar ? $8$tag$ AS dollar_text, "
            "* FROM users WHERE id = :user_id "
            "/* :block ? $7 /* :nested ? */ */",
            "SELECT E'escaped \\' :inside ? $9', "
            "'it''s :single ? $6' AS single_text, "
            '"quoted ""? :quoted $5""" AS ident, '
            "$tag$:dollar ? $8$tag$ AS dollar_text, "
            "* FROM users WHERE id = $1 "
            "/* :block ? $7 /* :nested ? */ */",
        ),
        (
            "SELECT * FROM users WHERE metadata ? 'admin' "
            "AND payload @? '$.active' AND id = :user_id",
            "SELECT * FROM users WHERE metadata ? 'admin' "
            "AND payload @? '$.active' AND id = $1",
        ),
        (
            "SELECT embedding <=> :embedding FROM items",
            "SELECT embedding <=> array_fill(0::real, ARRAY[1536])::vector FROM items",
        ),
    ],
)
def test_substitute_placeholders_preserves_bind_semantics(
    query: str, expected: str
) -> None:
    assert db_explain_check.substitute_placeholders(query) == expected


@pytest.mark.parametrize(
    ("method", "bind_type", "compiled_suffix", "rewritten_suffix"),
    [
        (
            "has_key",
            Text(),
            "items.json_data ? ?",
            "items.json_data ? $1",
        ),
        (
            "has_any",
            ARRAY(Text()),
            "items.json_data ?| ?::TEXT[]",
            "items.json_data ?| $1::TEXT[]",
        ),
        (
            "has_all",
            ARRAY(Text()),
            "items.json_data ?& ?::TEXT[]",
            "items.json_data ?& $1::TEXT[]",
        ),
        (
            "contains",
            JSONB(),
            "items.json_data @> ?::JSONB",
            "items.json_data @> $1::JSONB",
        ),
    ],
)
def test_jsonb_qmark_compilation_keeps_operand_types_and_operators(
    method: str,
    bind_type: Any,
    compiled_suffix: str,
    rewritten_suffix: str,
) -> None:
    metadata = MetaData()
    table = Table("items", metadata, Column("json_data", JSONB))
    bind = bindparam("lookup_value", type_=bind_type)
    predicate = getattr(table.c.json_data, method)(bind)
    compiled = (
        select(table)
        .where(predicate)
        .compile(dialect=postgresql.dialect(paramstyle="qmark"))
    )

    assert compiled.binds["lookup_value"].type is bind_type
    assert str(compiled).endswith(compiled_suffix)
    assert db_explain_check.substitute_placeholders(str(compiled)).endswith(
        rewritten_suffix
    )
    if isinstance(bind_type, ARRAY):
        assert str(compiled.binds["lookup_value"].type.item_type) == "TEXT"


def test_sql_parameter_count_ignores_dollar_digit_identifier_suffixes() -> None:
    query = db_explain_check.substitute_placeholders(
        "SELECT id = $7 AND flag$1 AND owner_id = $2"
    )

    assert query == "SELECT id = $1 AND flag$1 AND owner_id = $2"
    assert db_explain_check._sql_parameter_count(query) == 2
    assert db_explain_check._sql_parameter_count("SELECT flag$7") == 0


@pytest.mark.parametrize(
    "query",
    [
        "SELECT * FROM users WHERE status ?",
        "SELECT * FROM users WHERE search_vector @@? '$.active'",
        "SELECT * FROM users WHERE json_data ?? 'active'",
    ],
    ids=("trailing-operator", "compact-unknown-at-run", "unknown-double-qmark"),
)
def test_unsupported_question_mark_syntax_raises(query: str) -> None:
    with pytest.raises(
        db_explain_check.UnsupportedPlaceholderError,
        match="question mark",
    ):
        db_explain_check.substitute_placeholders(query)


def test_ordinary_quoted_backslash_is_rejected_without_setting_evidence() -> None:
    with pytest.raises(
        db_explain_check.UnsupportedPlaceholderError,
        match="standard_conforming_strings evidence",
    ):
        db_explain_check.substitute_placeholders(
            r"SELECT * FROM users WHERE note = 'it\'s ?'"
        )


def test_sql_parameter_count_ignores_literals_and_comments() -> None:
    assert (
        db_explain_check._sql_parameter_count(
            "SELECT '$9' FROM users WHERE id = $1 -- $8"
        )
        == 1
    )


@pytest.mark.asyncio
async def test_unsupported_qmark_fails_closed_with_other_queries_checked() -> None:
    engine, query_connection, _ = _make_analysis_engine()

    violations, checked = await db_explain_check.run_explain_analysis(
        engine,
        [
            "SELECT * FROM users WHERE status ?",
            "SELECT * FROM users WHERE id = 42",
        ],
        ["users"],
        500.0,
        fail_on_analysis_error=True,
    )

    assert violations is True
    assert checked == 1
    query_connection.exec_driver_sql.assert_awaited_once()


@pytest.mark.asyncio
async def test_semicolons_inside_literals_and_comments_are_still_planned() -> None:
    engine, query_connection, _ = _make_analysis_engine()

    violations, checked = await db_explain_check.run_explain_analysis(
        engine,
        [
            "SELECT * FROM users WHERE note = ';'",
            "SELECT * FROM users WHERE id = 1 -- ; comment",
            "SELECT * FROM users /* ; comment */ WHERE id = 2",
        ],
        ["users"],
        500.0,
        fail_on_analysis_error=True,
    )

    assert violations is False
    assert checked == 3
    assert query_connection.exec_driver_sql.await_count == 3


@pytest.mark.asyncio
async def test_unsupported_target_statement_is_violation_beside_valid_query() -> None:
    engine, query_connection, _ = _make_analysis_engine()

    violations, checked = await db_explain_check.run_explain_analysis(
        engine,
        [
            "SELECT * FROM users WHERE id = 1; SELECT 1",
            "SELECT * FROM users WHERE id = 2",
        ],
        ["users"],
        500.0,
        fail_on_analysis_error=True,
    )

    assert violations is True
    assert checked == 1
    query_connection.exec_driver_sql.assert_awaited_once()


@pytest.mark.asyncio
async def test_transaction_control_is_intentionally_ineligible() -> None:
    engine, query_connection, _ = _make_analysis_engine()

    violations, checked = await db_explain_check.run_explain_analysis(
        engine,
        ["BEGIN;", "SELECT * FROM users WHERE id = 1"],
        ["users"],
        500.0,
        fail_on_analysis_error=True,
    )

    assert violations is False
    assert checked == 1
    query_connection.exec_driver_sql.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw_query", "expected_query"),
    [
        (
            "SELECT * FROM users WHERE id = :user_id",
            "SELECT * FROM users WHERE id = $1",
        ),
        (
            "SELECT * FROM users WHERE id = ?",
            "SELECT * FROM users WHERE id = $1",
        ),
    ],
    ids=("named", "anonymous"),
)
async def test_named_and_anonymous_binds_use_generic_explain_plan(
    raw_query: str, expected_query: str
) -> None:
    engine, query_connection, _ = _make_analysis_engine()

    violations, checked = await db_explain_check.run_explain_analysis(
        engine,
        [raw_query],
        ["users"],
        500.0,
        fail_on_analysis_error=True,
    )

    assert violations is False
    assert checked == 1
    statement_name = db_explain_check._plan_statement_name(expected_query)
    assert query_connection.exec_driver_sql.await_args_list == [
        call(f"PREPARE {statement_name} AS {expected_query}"),
        call(f"EXPLAIN (FORMAT JSON) EXECUTE {statement_name}(NULL)"),
        call(f"DEALLOCATE {statement_name}"),
    ]


@pytest.mark.asyncio
async def test_explain_plan_retry_deallocates_after_error() -> None:
    _, query_connection, _ = _make_analysis_engine()
    plan_result = MagicMock()
    plan_result.scalar.return_value = [{"Plan": {"Node Type": "Index Scan"}}]
    prepared: set[str] = set()
    statements: list[str] = []
    fail_first_explain = True

    async def execute_sql(statement: str) -> MagicMock:
        nonlocal fail_first_explain
        statements.append(statement)
        if statement.startswith("PREPARE "):
            statement_name = statement.split()[1]
            if statement_name in prepared:
                raise RuntimeError("prepared statement already exists")
            prepared.add(statement_name)
        elif statement.startswith("EXPLAIN "):
            if fail_first_explain:
                fail_first_explain = False
                raise RuntimeError("transient EXPLAIN failure")
        elif statement.startswith("DEALLOCATE "):
            prepared.remove(statement.split()[1])
        return plan_result

    query_connection.exec_driver_sql = AsyncMock(side_effect=execute_sql)
    query = "SELECT * FROM users WHERE id = $1"
    statement_name = db_explain_check._plan_statement_name(query)

    with pytest.raises(RuntimeError, match="transient EXPLAIN failure"):
        await db_explain_check.explain_plan(query_connection, query)

    plan = await db_explain_check.explain_plan(query_connection, query)

    assert plan == plan_result.scalar.return_value
    assert prepared == set()
    assert statements == [
        f"PREPARE {statement_name} AS {query}",
        f"EXPLAIN (FORMAT JSON) EXECUTE {statement_name}(NULL)",
        f"DEALLOCATE {statement_name}",
        f"PREPARE {statement_name} AS {query}",
        f"EXPLAIN (FORMAT JSON) EXECUTE {statement_name}(NULL)",
        f"DEALLOCATE {statement_name}",
    ]


@pytest.mark.asyncio
async def test_run_explain_analysis_binds_calibration_and_uses_planner_only_explain() -> (
    None
):
    engine, query_connection, transaction = _make_analysis_engine()

    with patch.object(db_explain_check.logger, "warning") as warning:
        violations, checked = await db_explain_check.run_explain_analysis(
            engine,
            ["SELECT * FROM users WHERE id = $1", "SELECT 1; DROP TABLE users"],
            ["users"],
            500.0,
        )

    assert violations is False
    assert checked == 1
    calibration_calls = [
        awaited
        for awaited in query_connection.execute.await_args_list
        if str(awaited.args[0]).startswith("UPDATE pg_class")
    ]
    assert len(calibration_calls) == 2
    for awaited in calibration_calls:
        assert awaited.args[1] == {"table_names": ["users"]}
    assert [
        str(awaited.args[0])
        for awaited in query_connection.execute.await_args_list
        if str(awaited.args[0]).startswith("SET ")
    ] == [
        "SET statement_timeout = '15s'",
        "SET LOCAL enable_seqscan = off",
        "SET LOCAL plan_cache_mode = force_generic_plan",
    ]
    engine.begin.assert_not_called()
    # AUD-461: $n stays a parameter. It is prepared and planned under
    # force_generic_plan, so a bound NULL cannot fold the filter away.
    assert query_connection.exec_driver_sql.await_args_list == [
        call("PREPARE db_perf_gate_843923b9a025 AS SELECT * FROM users WHERE id = $1"),
        call("EXPLAIN (FORMAT JSON) EXECUTE db_perf_gate_843923b9a025(NULL)"),
        call("DEALLOCATE db_perf_gate_843923b9a025"),
    ]
    transaction.rollback.assert_awaited_once()
    warning.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "expected_calls"),
    [
        (
            "INSERT INTO users (email) VALUES ($1)",
            [
                call(
                    "PREPARE db_perf_gate_0cc254288794 "
                    "AS INSERT INTO users (email) VALUES ($1)"
                ),
                call("EXPLAIN (FORMAT JSON) EXECUTE db_perf_gate_0cc254288794(NULL)"),
                call("DEALLOCATE db_perf_gate_0cc254288794"),
            ],
        ),
        (
            "WITH changed AS (DELETE FROM users WHERE id = $1 RETURNING id) "
            "SELECT * FROM changed",
            [
                call(
                    "PREPARE db_perf_gate_ae1abf040c15 AS WITH changed AS "
                    "(DELETE FROM users WHERE id = $1 RETURNING id) "
                    "SELECT * FROM changed"
                ),
                call("EXPLAIN (FORMAT JSON) EXECUTE db_perf_gate_ae1abf040c15(NULL)"),
                call("DEALLOCATE db_perf_gate_ae1abf040c15"),
            ],
        ),
    ],
    ids=("insert", "data-modifying-cte"),
)
async def test_logged_mutations_use_planner_only_explain(
    query: str, expected_calls: list[object]
) -> None:
    engine, query_connection, _ = _make_analysis_engine()

    violations, checked = await db_explain_check.run_explain_analysis(
        engine,
        [query],
        ["users"],
        500.0,
        fail_on_analysis_error=True,
    )

    assert violations is False
    assert checked == 1
    # PREPARE only defines the statement; EXPLAIN without ANALYZE plans it and
    # never executes the DML or the data-modifying CTE.
    assert query_connection.exec_driver_sql.await_args_list == expected_calls


@pytest.mark.asyncio
async def test_run_explain_analysis_rejects_unsafe_table_identifiers() -> None:
    with pytest.raises(ValueError, match="safe SQL identifiers"):
        await db_explain_check.run_explain_analysis(
            MagicMock(), ["SELECT 1"], ["users;drop"], 500.0
        )


def _make_analysis_engine(
    *,
    explain_error: Exception | None = None,
    calibration_error: Exception | None = None,
    plan: object | None = None,
    standard_conforming_strings: str | None = "on",
    standard_conforming_strings_error: Exception | None = None,
) -> tuple[MagicMock, MagicMock, MagicMock]:
    plan_result = MagicMock()
    plan_result.scalar.return_value = (
        plan
        if plan is not None
        else [{"Plan": {"Node Type": "Index Scan", "Total Cost": 1.0}}]
    )
    show_result = MagicMock()
    show_result.scalar_one.return_value = standard_conforming_strings

    statement_events: list[str] = []

    async def execute(statement, parameters=None):
        statement_events.append(str(statement))
        if calibration_error is not None and "pg_index" in str(statement):
            raise calibration_error

    async def execute_driver_sql(statement: str, *args: object, **kwargs: object):
        statement_events.append(statement)
        if statement == "SHOW standard_conforming_strings":
            if standard_conforming_strings_error is not None:
                raise standard_conforming_strings_error
            return show_result
        if explain_error is not None:
            raise explain_error
        return query_connection.exec_driver_sql.return_value

    query_connection = MagicMock()
    query_connection.statement_events = statement_events
    query_connection.execute = AsyncMock(side_effect=execute)
    query_connection.exec_driver_sql = AsyncMock(return_value=plan_result)
    query_connection.exec_driver_sql.side_effect = execute_driver_sql
    savepoint_context = MagicMock()
    savepoint_context.__aenter__ = AsyncMock(return_value=MagicMock())
    savepoint_context.__aexit__ = AsyncMock(return_value=False)
    query_connection.begin_nested.return_value = savepoint_context

    transaction = MagicMock()
    transaction.rollback = AsyncMock()
    transaction_context = MagicMock()
    transaction_context.__aenter__ = AsyncMock(return_value=transaction)
    transaction_context.__aexit__ = AsyncMock(return_value=False)
    query_connection.begin.return_value = transaction_context
    query_context = MagicMock()
    query_context.__aenter__ = AsyncMock(return_value=query_connection)
    query_context.__aexit__ = AsyncMock(return_value=False)

    engine = MagicMock()
    engine.connect.return_value = query_context
    engine.dispose = AsyncMock()
    return engine, query_connection, transaction


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [TimeoutError("statement timeout"), RuntimeError("EXPLAIN failed")],
    ids=("timeout", "driver-error"),
)
@pytest.mark.parametrize(
    ("strict", "expected_violation"),
    [(False, False), (True, True)],
    ids=("optional-warning", "strict-failure"),
)
async def test_explain_failures_only_fail_strict_gate(
    error: Exception, strict: bool, expected_violation: bool
) -> None:
    engine, query_connection, _ = _make_analysis_engine(explain_error=error)

    with patch.object(db_explain_check.logger, "warning") as warning:
        violations, checked = await db_explain_check.run_explain_analysis(
            engine,
            ["SELECT * FROM users WHERE id = 1"],
            ["users"],
            500.0,
            fail_on_analysis_error=strict,
        )

    assert violations is expected_violation
    assert checked == 1
    query_connection.exec_driver_sql.assert_awaited_once()
    warning.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("strict", "expected_violation"),
    [(False, False), (True, True)],
    ids=("optional-warning", "strict-failure"),
)
async def test_calibration_failure_only_fails_strict_gate(
    strict: bool, expected_violation: bool
) -> None:
    engine, query_connection, transaction = _make_analysis_engine(
        calibration_error=RuntimeError("statistics unavailable")
    )

    with patch.object(db_explain_check.logger, "warning") as warning:
        violations, checked = await db_explain_check.run_explain_analysis(
            engine,
            ["SELECT * FROM users WHERE id = 1"],
            ["users"],
            500.0,
            fail_on_analysis_error=strict,
        )

    assert violations is expected_violation
    assert checked == 1
    query_connection.exec_driver_sql.assert_awaited_once()
    transaction.rollback.assert_awaited_once()
    warning.assert_called_once()


@pytest.mark.asyncio
async def test_missing_explain_plan_fails_strict_gate() -> None:
    engine, _, _ = _make_analysis_engine()
    plan_result = engine.connect.return_value.__aenter__.return_value.exec_driver_sql
    plan_result.return_value.scalar.return_value = None

    violations, checked = await db_explain_check.run_explain_analysis(
        engine,
        ["SELECT * FROM users WHERE id = 1"],
        ["users"],
        500.0,
        fail_on_analysis_error=True,
    )

    assert violations is True
    assert checked == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("strict", "expected_exit"),
    [(False, 0), (True, 1)],
    ids=("optional-skip", "strict-failure"),
)
async def test_main_missing_database_url_respects_strict_mode(
    monkeypatch: pytest.MonkeyPatch, strict: bool, expected_exit: int
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    argv = ["db_explain_check.py", "--tables", "users"]
    if strict:
        argv.append("--fail-on-seq-scan")
    monkeypatch.setattr(sys, "argv", argv)

    with pytest.raises(SystemExit) as exit_info:
        await db_explain_check.main()

    assert exit_info.value.code == expected_exit


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("strict", "expected_exit"),
    [(False, 0), (True, 1)],
    ids=("optional-skip", "strict-failure"),
)
async def test_main_empty_query_logs_respect_strict_mode(
    monkeypatch: pytest.MonkeyPatch, strict: bool, expected_exit: int
) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    argv = ["db_explain_check.py", "--tables", "users"]
    if strict:
        argv.append("--fail-on-seq-scan")
    monkeypatch.setattr(sys, "argv", argv)
    engine = MagicMock()
    engine.dispose = AsyncMock()

    with (
        patch.object(db_explain_check, "create_async_engine", return_value=engine),
        patch.object(db_explain_check, "extract_queries_from_logs", return_value=[]),
        pytest.raises(SystemExit) as exit_info,
    ):
        await db_explain_check.main()

    assert exit_info.value.code == expected_exit
    engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_main_strict_gate_fails_when_explain_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "db_explain_check.py",
            "--fail-on-seq-scan",
            "--tables",
            "users",
        ],
    )
    engine, _, _ = _make_analysis_engine(
        explain_error=TimeoutError("statement timeout")
    )

    with (
        patch.object(db_explain_check, "create_async_engine", return_value=engine),
        patch.object(
            db_explain_check,
            "extract_queries_from_logs",
            return_value=["SELECT * FROM users WHERE id = 1"],
        ),
        pytest.raises(SystemExit) as exit_info,
    ):
        await db_explain_check.main()

    assert exit_info.value.code == 1
    engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_main_strict_gate_fails_when_no_target_query_is_checked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "db_explain_check.py",
            "--fail-on-seq-scan",
            "--tables",
            "users",
        ],
    )
    engine, query_connection, _ = _make_analysis_engine()

    with (
        patch.object(db_explain_check, "create_async_engine", return_value=engine),
        patch.object(
            db_explain_check,
            "extract_queries_from_logs",
            return_value=["SELECT * FROM audit_entries WHERE id = 1"],
        ),
        pytest.raises(SystemExit) as exit_info,
    ):
        await db_explain_check.main()

    assert exit_info.value.code == 1
    engine.dispose.assert_awaited_once()
    query_connection.exec_driver_sql.assert_not_awaited()


@pytest.mark.asyncio
async def test_main_strict_gate_fails_unsupported_target_even_if_other_query_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "db_explain_check.py",
            "--fail-on-seq-scan",
            "--tables",
            "users",
        ],
    )
    engine, query_connection, _ = _make_analysis_engine()

    with (
        patch.object(db_explain_check, "create_async_engine", return_value=engine),
        patch.object(
            db_explain_check,
            "extract_queries_from_logs",
            return_value=[
                "SELECT * FROM users WHERE id = 1; SELECT 1",
                "SELECT * FROM users WHERE id = 2",
            ],
        ),
        patch.object(db_explain_check.logger, "info") as info,
        pytest.raises(SystemExit) as exit_info,
    ):
        await db_explain_check.main()

    assert exit_info.value.code == 1
    assert not any("PASSED" in str(record.args[0]) for record in info.call_args_list)
    engine.dispose.assert_awaited_once()
    query_connection.exec_driver_sql.assert_awaited_once()


def _set_plan_payload(engine: MagicMock, plan: object) -> None:
    plan_result = (
        engine.connect.return_value.__aenter__.return_value.exec_driver_sql.return_value
    )
    plan_result.scalar.return_value = plan


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "plan",
    [
        None,
        [],
        [{}],
        {"Plan": {}},
        {"Plan": [{"Node Type": "Index Scan", "Total Cost": 1.0}]},
        [{"Plan": {"Node Type": "", "Total Cost": 1.0}}],
        [{"Plan": {"Node Type": "Index Scan", "Total Cost": "1.0"}}],
        [{"Plan": {"Node Type": "Index Scan", "Total Cost": float("nan")}}],
        [
            {
                "Plan": {
                    "Node Type": "Index Scan",
                    "Total Cost": 1.0,
                    "Plans": [{}],
                }
            }
        ],
        [{"Plan": {"Node Type": "Seq Scan", "Total Cost": 1.0}}],
    ],
    ids=(
        "none",
        "empty-list",
        "empty-document",
        "empty-plan",
        "wrong-plan-shape",
        "empty-node-type",
        "non-numeric-cost",
        "non-finite-cost",
        "malformed-child",
        "seq-scan-without-relation",
    ),
)
async def test_unusable_plan_fails_strict_analysis(plan: object) -> None:
    engine, query_connection, _ = _make_analysis_engine()
    _set_plan_payload(engine, plan)

    violations, checked = await db_explain_check.run_explain_analysis(
        engine,
        ["SELECT * FROM users WHERE id = 1"],
        ["users"],
        500.0,
        fail_on_analysis_error=True,
    )

    assert violations is True
    assert checked == 1
    query_connection.exec_driver_sql.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "plan",
    [None, [], [{}], {"Plan": {}}],
    ids=("none", "empty-list", "empty-document", "empty-plan"),
)
async def test_unusable_plan_remains_nonfatal_in_optional_mode(plan: object) -> None:
    engine, query_connection, _ = _make_analysis_engine()
    _set_plan_payload(engine, plan)

    violations, checked = await db_explain_check.run_explain_analysis(
        engine,
        ["SELECT * FROM users WHERE id = 1"],
        ["users"],
        500.0,
    )

    assert violations is False
    assert checked == 1
    query_connection.exec_driver_sql.assert_awaited_once()


@pytest.mark.asyncio
async def test_usable_index_plan_passes_strict_analysis() -> None:
    engine, query_connection, _ = _make_analysis_engine()

    violations, checked = await db_explain_check.run_explain_analysis(
        engine,
        ["SELECT * FROM users WHERE id = 1"],
        ["users"],
        500.0,
        fail_on_analysis_error=True,
    )

    assert violations is False
    assert checked == 1
    query_connection.exec_driver_sql.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("standard_conforming_strings", "raw_query"),
    [
        ("on", r"SELECT * FROM users WHERE note = 'C:\' AND id = :user_id"),
        ("off", r"SELECT * FROM users WHERE note = 'it\'s ?' AND id = :user_id"),
    ],
    ids=("standard-strings-on", "standard-strings-off"),
)
async def test_cli_reads_standard_conforming_strings_before_parsing_ambiguous_literal(
    monkeypatch: pytest.MonkeyPatch,
    standard_conforming_strings: str,
    raw_query: str,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["db_explain_check.py", "--fail-on-seq-scan", "--tables", "users"],
    )
    engine, query_connection, _ = _make_analysis_engine(
        standard_conforming_strings=standard_conforming_strings
    )
    expected_query = raw_query.replace(":user_id", "$1")

    with (
        monkeypatch.context() as database_url,
        patch.object(db_explain_check, "create_async_engine", return_value=engine),
        patch.object(
            db_explain_check,
            "extract_queries_from_logs",
            return_value=[raw_query],
        ),
    ):
        database_url.setenv("DATABASE_URL", "postgresql+asyncpg://db/perf")
        await db_explain_check.main()

    statement_name = db_explain_check._plan_statement_name(expected_query)
    assert query_connection.statement_events[:2] == [
        "SET statement_timeout = '15s'",
        "SHOW standard_conforming_strings",
    ]
    assert query_connection.exec_driver_sql.await_args_list == [
        call("SHOW standard_conforming_strings"),
        call(f"PREPARE {statement_name} AS {expected_query}"),
        call(f"EXPLAIN (FORMAT JSON) EXECUTE {statement_name}(NULL)"),
        call(f"DEALLOCATE {statement_name}"),
    ]
    engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("setting", "show_error"),
    [("unknown", None), (None, RuntimeError("SHOW failed"))],
    ids=("invalid-setting", "show-error"),
)
async def test_cli_fails_closed_when_standard_conforming_strings_is_unverified(
    monkeypatch: pytest.MonkeyPatch,
    setting: str | None,
    show_error: Exception | None,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["db_explain_check.py", "--fail-on-seq-scan", "--tables", "users"],
    )
    engine, query_connection, _ = _make_analysis_engine(
        standard_conforming_strings=setting,
        standard_conforming_strings_error=show_error,
    )
    raw_query = r"SELECT * FROM users WHERE note = 'C:\' AND id = :user_id"

    with (
        monkeypatch.context() as database_url,
        patch.object(db_explain_check, "create_async_engine", return_value=engine),
        patch.object(
            db_explain_check,
            "extract_queries_from_logs",
            return_value=[raw_query],
        ),
        pytest.raises(SystemExit) as exit_info,
    ):
        database_url.setenv("DATABASE_URL", "postgresql+asyncpg://db/perf")
        await db_explain_check.main()

    assert exit_info.value.code == 1
    assert query_connection.statement_events[:2] == [
        "SET statement_timeout = '15s'",
        "SHOW standard_conforming_strings",
    ]
    assert query_connection.exec_driver_sql.await_args_list == [
        call("SHOW standard_conforming_strings")
    ]
    engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_strict_main_returns_success_for_usable_index_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "db_explain_check.py",
            "--fail-on-seq-scan",
            "--tables",
            "users",
        ],
    )
    engine, query_connection, _ = _make_analysis_engine()

    with (
        monkeypatch.context() as database_url,
        patch.object(db_explain_check, "create_async_engine", return_value=engine),
        patch.object(
            db_explain_check,
            "extract_queries_from_logs",
            return_value=["SELECT * FROM users WHERE id = 1"],
        ),
    ):
        database_url.setenv("DATABASE_URL", "postgresql+asyncpg://db/perf")
        await db_explain_check.main()

    engine.dispose.assert_awaited_once()
    query_connection.exec_driver_sql.assert_awaited_once()


@pytest.mark.asyncio
async def test_strict_analysis_still_detects_a_usable_seq_scan() -> None:
    engine, query_connection, _ = _make_analysis_engine()
    _set_plan_payload(
        engine,
        [
            {
                "Plan": {
                    "Node Type": "Seq Scan",
                    "Relation Name": "users",
                    "Total Cost": 1.0,
                }
            }
        ],
    )

    violations, checked = await db_explain_check.run_explain_analysis(
        engine,
        ["SELECT * FROM users WHERE id = 1"],
        ["users"],
        500.0,
        fail_on_analysis_error=True,
    )

    assert violations is True
    assert checked == 1
    query_connection.exec_driver_sql.assert_awaited_once()


@pytest.mark.asyncio
async def test_optional_gate_never_reports_passed_after_violations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AUD-225: non-gating mode must not claim PASSED after logged violations."""

    monkeypatch.setattr(sys, "argv", ["db_explain_check.py", "--tables", "users"])
    seq_scan_plan = [
        {"Plan": {"Node Type": "Seq Scan", "Relation Name": "users", "Total Cost": 1.0}}
    ]
    engine, _, _ = _make_analysis_engine(plan=seq_scan_plan)

    with (
        monkeypatch.context() as database_url,
        patch.object(db_explain_check, "create_async_engine", return_value=engine),
        patch.object(
            db_explain_check,
            "extract_queries_from_logs",
            return_value=["SELECT * FROM users WHERE id = 1"],
        ),
        patch.object(db_explain_check.logger, "info") as info,
        patch.object(db_explain_check.logger, "warning") as warning,
    ):
        database_url.setenv("DATABASE_URL", "postgresql+asyncpg://db/perf")
        await db_explain_check.main()

    logged = [recorded.args[0] for recorded in info.call_args_list]
    assert not any("PASSED" in str(message) for message in logged)
    assert any(
        "optional mode" in str(recorded.args[0]) for recorded in warning.call_args_list
    )


@pytest.mark.asyncio
async def test_optional_gate_warns_when_no_target_query_is_eligible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Optional mode must not claim a pass when no requested table was checked."""

    monkeypatch.setattr(sys, "argv", ["db_explain_check.py", "--tables", "users"])
    engine, query_connection, _ = _make_analysis_engine()

    with (
        monkeypatch.context() as database_url,
        patch.object(db_explain_check, "create_async_engine", return_value=engine),
        patch.object(
            db_explain_check,
            "extract_queries_from_logs",
            return_value=["SELECT * FROM audit_entries WHERE id = 1"],
        ),
        patch.object(db_explain_check.logger, "info") as info,
        patch.object(db_explain_check.logger, "warning") as warning,
    ):
        database_url.setenv("DATABASE_URL", "postgresql+asyncpg://db/perf")
        await db_explain_check.main()

    logged = [recorded.args[0] for recorded in info.call_args_list]
    assert not any("PASSED" in str(message) for message in logged)
    assert any(
        "No eligible target queries" in str(recorded.args[0])
        and "optional mode" in str(recorded.args[0])
        for recorded in warning.call_args_list
    )
    engine.dispose.assert_awaited_once()
    query_connection.exec_driver_sql.assert_not_awaited()


def test_extract_queries_keeps_unique_non_empty_lines_and_skips_unreadable_logs(
    tmp_path: Path,
) -> None:
    (tmp_path / "queries_a.log").write_text(
        "SELECT * FROM users WHERE id = $1\n\nSELECT * FROM users WHERE id = $1\n",
        encoding="utf-8",
    )
    (tmp_path / "queries_unreadable.log").mkdir()

    with patch.object(db_explain_check.logger, "error") as error:
        queries = db_explain_check.extract_queries_from_logs(tmp_path)

    assert queries == ["SELECT * FROM users WHERE id = $1"]
    error.assert_called_once()


def test_find_sequential_scans_ignores_non_plans_and_recurses_into_children() -> None:
    assert db_explain_check.find_sequential_scans("not-a-plan", ["users"]) == []

    nested = {
        "Node Type": "Nested Loop",
        "Plans": [
            {"Node Type": "Index Scan", "Relation Name": "orders", "Total Cost": 1.0},
            {"Node Type": "Seq Scan", "Relation Name": "users", "Total Cost": 3.0},
        ],
    }

    assert db_explain_check.find_sequential_scans(nested, ["users"]) == [("users", 3.0)]


def test_usable_plan_node_rejects_costs_that_do_not_fit_a_float() -> None:
    oversized = {"Node Type": "Index Scan", "Total Cost": 10**400}

    assert db_explain_check._usable_plan_node(oversized) is False


@pytest.mark.asyncio
async def test_table_wide_write_without_where_is_not_planned() -> None:
    engine, query_connection, _ = _make_analysis_engine()

    violations, checked = await db_explain_check.run_explain_analysis(
        engine,
        ["DELETE FROM users"],
        ["users"],
        500.0,
        fail_on_analysis_error=True,
    )

    assert violations is False
    assert checked == 0
    query_connection.execute.assert_not_awaited()
    query_connection.exec_driver_sql.assert_not_awaited()


def test_script_entry_point_rejects_missing_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["db_explain_check.py"])

    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(db_explain_check.__file__, run_name="__main__")

    assert exit_info.value.code == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "error"),
    [
        ("database-unavailable", ConnectionError("connection refused")),
        ("explain-error", RuntimeError("EXPLAIN failed")),
        ("explain-timeout", TimeoutError("statement timeout")),
    ],
)
async def test_optional_main_does_not_report_pass_after_database_or_explain_failure(
    monkeypatch: pytest.MonkeyPatch, failure: str, error: Exception
) -> None:
    monkeypatch.setattr(sys, "argv", ["db_explain_check.py", "--tables", "users"])
    engine, _, _ = _make_analysis_engine(
        explain_error=error if failure != "database-unavailable" else None
    )
    if failure == "database-unavailable":
        engine.connect.return_value.__aenter__.side_effect = error

    with (
        monkeypatch.context() as database_url,
        patch.object(db_explain_check, "create_async_engine", return_value=engine),
        patch.object(
            db_explain_check,
            "extract_queries_from_logs",
            return_value=["SELECT * FROM users WHERE id = 1"],
        ),
        patch.object(db_explain_check.logger, "info") as info,
    ):
        database_url.setenv("DATABASE_URL", "postgresql+asyncpg://db/perf")
        await db_explain_check.main()

    logged_messages = [record.args[0] for record in info.call_args_list]
    assert not any("PASSED" in str(message) for message in logged_messages)
