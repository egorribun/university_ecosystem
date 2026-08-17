"""Security contracts for the database EXPLAIN performance gate."""

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
