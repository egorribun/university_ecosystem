"""Regression checks for incomplete DB-performance query-log ingestion."""

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts import db_explain_check

pytest_plugins = ["pytester"]


@pytest.mark.parametrize("strict", [False, True], ids=["optional", "strict"])
@pytest.mark.parametrize("failure", ["decode", "unreadable"])
async def test_cli_does_not_pass_when_one_log_cannot_be_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    strict: bool,
    failure: str,
) -> None:
    (tmp_path / "queries_good.log").write_text(
        "SELECT * FROM users WHERE id = 1\n", encoding="utf-8"
    )
    bad_log = tmp_path / "queries_bad.log"
    if failure == "decode":
        bad_log.write_bytes(b"SELECT * FROM users WHERE id = 2\n\xff")
    else:
        bad_log.mkdir()

    argv = ["db_explain_check.py", "--tables", "users", "--log-dir", str(tmp_path)]
    if strict:
        argv.append("--fail-on-seq-scan")
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    engine = MagicMock()
    engine.dispose = AsyncMock()
    analysis = AsyncMock(return_value=(False, 1))
    monkeypatch.setattr(db_explain_check, "create_async_engine", lambda _: engine)
    monkeypatch.setattr(db_explain_check, "run_explain_analysis", analysis)

    exit_code = 0
    try:
        await db_explain_check.main()
    except SystemExit as error:
        exit_code = error.code

    assert exit_code == (1 if strict else 0)
    assert "Failed to read query log file" in caplog.text
    assert "DB Performance Gate PASSED" not in caplog.text
    analysis.assert_not_awaited()
    engine.dispose.assert_awaited_once()


@pytest.mark.parametrize("strict", [False, True], ids=["optional", "strict"])
async def test_cli_analyzes_complete_query_logs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    strict: bool,
) -> None:
    query = "SELECT * FROM users WHERE id = 1"
    (tmp_path / "queries_good.log").write_text(query + "\n", encoding="utf-8")
    argv = ["db_explain_check.py", "--tables", "users", "--log-dir", str(tmp_path)]
    if strict:
        argv.append("--fail-on-seq-scan")
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    engine = MagicMock()
    engine.dispose = AsyncMock()
    analysis = AsyncMock(return_value=(False, 1))
    monkeypatch.setattr(db_explain_check, "create_async_engine", lambda _: engine)
    monkeypatch.setattr(db_explain_check, "run_explain_analysis", analysis)

    await db_explain_check.main()

    analysis.assert_awaited_once_with(
        engine, [query], ["users"], 500.0, fail_on_analysis_error=True
    )
    assert "DB Performance Gate PASSED" in caplog.text
    engine.dispose.assert_awaited_once()


def test_strict_cli_process_fails_for_partial_query_logs(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    (pytester.path / "queries_good.log").write_text(
        "SELECT * FROM users WHERE id = 1\n", encoding="utf-8"
    )
    (pytester.path / "queries_bad.log").write_bytes(b"\xff")
    project_root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv(
        "PYTHONPATH", str(project_root) + os.pathsep + os.environ.get("PYTHONPATH", "")
    )
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("AUD_DBPERF_LOG_DIR", str(pytester.path))

    result = pytester.runpython_c(
        """
import asyncio
import os
import sys
from scripts import db_explain_check as gate

class Engine:
    async def dispose(self):
        pass

async def successful_analysis(*args, **kwargs):
    return False, 1

gate.create_async_engine = lambda _: Engine()
gate.run_explain_analysis = successful_analysis
sys.argv = ['db_explain_check.py', '--fail-on-seq-scan', '--tables', 'users',
            '--log-dir', os.environ['AUD_DBPERF_LOG_DIR']]
asyncio.run(gate.main())
"""
    )

    assert result.ret == 1
    assert "DB Performance Gate FAILED" in result.stderr.str()
    assert "DB Performance Gate PASSED" not in result.stderr.str()
