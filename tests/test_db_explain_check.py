"""Security contracts for the database EXPLAIN performance gate."""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
    with pytest.raises(ValueError, match="single explainable"):
        db_explain_check.normalize_explainable_query(query)


@pytest.mark.asyncio
async def test_run_explain_analysis_binds_calibration_and_executes_one_statement() -> (
    None
):
    calibration_connection = MagicMock()
    calibration_connection.execute = AsyncMock()
    calibration_context = MagicMock()
    calibration_context.__aenter__ = AsyncMock(return_value=calibration_connection)
    calibration_context.__aexit__ = AsyncMock(return_value=False)

    plan_result = MagicMock()
    plan_result.scalar.return_value = [
        {"Plan": {"Node Type": "Index Scan", "Total Cost": 1.0}}
    ]
    query_connection = MagicMock()
    query_connection.execute = AsyncMock()
    query_connection.exec_driver_sql = AsyncMock(return_value=plan_result)
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
    engine.begin.return_value = calibration_context
    engine.connect.return_value = query_context

    with patch.object(db_explain_check.logger, "warning") as warning:
        violations, checked = await db_explain_check.run_explain_analysis(
            engine,
            ["SELECT * FROM users WHERE id = $1", "SELECT 1; DROP TABLE users"],
            ["users"],
            500.0,
        )

    assert violations is False
    assert checked == 1
    assert calibration_connection.execute.await_count == 2
    for call in calibration_connection.execute.await_args_list:
        assert call.args[1] == {"table_names": ["users"]}
    query_connection.exec_driver_sql.assert_awaited_once_with(
        "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT * FROM users WHERE id = NULL"
    )
    transaction.rollback.assert_awaited_once()
    warning.assert_called_once()


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
) -> tuple[MagicMock, MagicMock, MagicMock]:
    calibration_connection = MagicMock()
    calibration_connection.execute = AsyncMock()
    calibration_context = MagicMock()
    if calibration_error is None:
        calibration_context.__aenter__ = AsyncMock(return_value=calibration_connection)
    else:
        calibration_context.__aenter__ = AsyncMock(side_effect=calibration_error)
    calibration_context.__aexit__ = AsyncMock(return_value=False)

    plan_result = MagicMock()
    plan_result.scalar.return_value = (
        plan
        if plan is not None
        else [{"Plan": {"Node Type": "Index Scan", "Total Cost": 1.0}}]
    )
    query_connection = MagicMock()
    query_connection.execute = AsyncMock()
    if explain_error is None:
        query_connection.exec_driver_sql = AsyncMock(return_value=plan_result)
    else:
        query_connection.exec_driver_sql = AsyncMock(side_effect=explain_error)

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
    engine.begin.return_value = calibration_context
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
async def test_strict_main_returns_success_for_usable_index_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://db/perf")
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
            return_value=["SELECT * FROM users WHERE id = 1"],
        ),
    ):
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
