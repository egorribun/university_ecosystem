"""Database-free controls for the baseline proof's child-process boundary."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from tests.fixtures import owned_baseline_postgres as owned
from tests.integration import test_mvp_baseline_schema_equivalence as proof

initialize_database_for_tests = owned.initialize_database_for_tests
prepare_database = owned.prepare_database
clean_database = owned.clean_database
default_database_guard = owned.default_database_guard

pytest_plugins = ["pytester"]

_ROOT = Path(__file__).resolve().parents[1]
_PROOF = _ROOT / "tests/integration/test_mvp_baseline_schema_equivalence.py"


def test_child_environment_rejects_all_ambient_application_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = {
        "PATH": "/controlled/bin",
        "SystemRoot": "C:/Windows",
        "database_url": "unowned-target",
        "DATABASE_URL_FILE": "/unowned/database",
        "ENV_FILE_PATH": "/unowned/settings",
        "SECRET_KEY_FILE": "/unowned/key",
        "PYTHONPATH": "/unowned/imports",
        "pythonpath": "/unowned/alternate-imports",
        "PYTHONHOME": "/unowned/python",
        "LD_LIBRARY_PATH": "/unowned/libraries",
        "LD_PRELOAD": "/unowned/preload",
        "ENVIRONMENT": "production",
        "CI": "true",
        "GITHUB_ACTIONS": "true",
        "PGOPTIONS": "unowned-options",
        "MIGRATION_ROUNDTRIP_DATABASE_URL": "unowned-roundtrip",
    }
    monkeypatch.setattr(proof.os, "environ", environment)
    monkeypatch.setattr(proof.sys, "platform", "linux")
    monkeypatch.setattr(proof.sys, "base_prefix", "/trusted/python")

    result = proof._child_environment("owned-url")

    assert result["DATABASE_URL"] == "owned-url"
    assert result["ENV_FILE_PATH"] == ""
    assert result["ENVIRONMENT"] == "testing"
    assert result["PYTHONNOUSERSITE"] == "1"
    assert result["PYTHONUTF8"] == "1"
    assert result["LD_LIBRARY_PATH"] == str(Path("/trusted/python").resolve() / "lib")
    assert result["PATH"] == environment["PATH"]
    assert result["SystemRoot"] == environment["SystemRoot"]
    assert set(result) == {
        "PATH",
        "SystemRoot",
        "DATABASE_URL",
        "ENV_FILE_PATH",
        "ENVIRONMENT",
        "SECRET_KEY",
        "PYTHONNOUSERSITE",
        "PYTHONUTF8",
        "LD_LIBRARY_PATH",
    }
    assert environment["ENVIRONMENT"] == "production"


@pytest.mark.parametrize("platform", ["win32", "darwin"])
def test_other_platforms_do_not_inherit_linux_loader_authority(
    monkeypatch: pytest.MonkeyPatch, platform: str
) -> None:
    monkeypatch.setattr(proof.sys, "platform", platform)
    monkeypatch.setattr(proof.os, "environ", {"LD_LIBRARY_PATH": "/unowned"})
    assert "LD_LIBRARY_PATH" not in proof._child_environment("owned-url")


class Child:
    def __init__(self) -> None:
        self.returncode: int | None = None
        self.started = asyncio.Event()
        self.released = asyncio.Event()
        self.killed = False
        self.drained = False
        self.communication_cancelled = False
        self.reaped = False
        self.wait_calls = 0

    async def communicate(self) -> tuple[bytes, bytes]:
        self.started.set()
        try:
            await self.released.wait()
        except asyncio.CancelledError:
            self.communication_cancelled = True
            raise
        self.drained = True
        return b"output", b"diagnostic"

    async def wait(self) -> int:
        self.wait_calls += 1
        await self.released.wait()
        assert self.returncode is not None
        self.reaped = True
        return self.returncode

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9
        self.released.set()


def test_cancelled_child_is_killed_and_drained_before_cancellation_escapes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        child = Child()
        launch = AsyncMock(return_value=child)
        monkeypatch.setattr(proof.asyncio, "create_subprocess_exec", launch)
        task = asyncio.create_task(proof._run_fixed_argv(["fixed"], tmp_path))
        await asyncio.wait_for(child.started.wait(), timeout=5)
        task.cancel("controlled cancellation")
        with pytest.raises(asyncio.CancelledError) as raised:
            await asyncio.wait_for(task, timeout=5)
        assert raised.value.args == ("controlled cancellation",)
        assert child.killed
        assert child.drained
        assert child.reaped
        assert child.wait_calls == 1
        assert child.returncode == -9
        assert not child.communication_cancelled
        launch.assert_awaited_once_with(
            "fixed",
            cwd=tmp_path,
            env=None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    asyncio.run(scenario())


def test_timeout_keeps_communication_alive_until_child_is_killed_and_drained(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        child = Child()
        monkeypatch.setattr(
            proof.asyncio, "create_subprocess_exec", AsyncMock(return_value=child)
        )
        real_wait_for = asyncio.wait_for
        calls = 0
        original_timeout = TimeoutError("controlled deadline")

        async def deadline(awaitable, *, timeout):
            nonlocal calls
            calls += 1
            if calls == 1:
                await real_wait_for(child.started.wait(), timeout=5)
                awaitable.cancel()
                raise original_timeout
            assert timeout == proof._CHILD_REAP_SECONDS
            return await real_wait_for(awaitable, timeout=timeout)

        monkeypatch.setattr(proof.asyncio, "wait_for", deadline)
        with pytest.raises(TimeoutError) as raised:
            await real_wait_for(proof._run_fixed_argv(["fixed"], tmp_path), timeout=5)
        assert raised.value is original_timeout
        assert calls == 2
        assert child.killed
        assert child.drained
        assert child.reaped
        assert child.wait_calls == 1
        assert child.returncode == -9
        assert not child.communication_cancelled

    asyncio.run(scenario())


def test_completed_child_returns_its_actual_exit_status_and_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        child = Child()
        child.returncode = 7
        child.released.set()
        monkeypatch.setattr(
            proof.asyncio, "create_subprocess_exec", AsyncMock(return_value=child)
        )
        assert await proof._run_fixed_argv(["fixed"], tmp_path) == (
            7,
            b"output",
            b"diagnostic",
        )
        assert not child.killed
        assert child.drained

    asyncio.run(scenario())


def test_raw_pair_capture_precedes_processing_and_freezes_mutable_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = object()
    after = object()
    events: list[tuple[str, object]] = []
    rows = ["raw catalog row"]
    versions = ["raw version"]

    def dump(database):
        events.append(("dump", database))
        return "RAW SQL; 'two  spaces'"

    def probe(database):
        events.append(("catalog", database))
        return {"relations": rows}

    def version(database):
        events.append(("version", database))
        return versions

    def reject_processing(*_args):
        pytest.fail("raw capture must not normalize or split SQL")

    monkeypatch.setattr(proof, "_dump", dump)
    monkeypatch.setattr(proof, "_probe", probe)
    monkeypatch.setattr(proof, "_version", version)
    monkeypatch.setattr(proof, "_schema_statements", reject_processing)
    monkeypatch.setattr(proof, "_canonical", reject_processing)
    captures = proof._capture_pair(before, after)
    rows.append("later mutation")
    versions.append("later version")

    assert events == [
        ("dump", before),
        ("catalog", before),
        ("version", before),
        ("dump", after),
        ("catalog", after),
        ("version", after),
    ]
    for captured in captures:
        assert captured.dump == "RAW SQL; 'two  spaces'"
        assert captured.catalog == (("relations", ("raw catalog row",)),)
        assert captured.version == ("raw version",)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("SELECT 'two  spaces'", "SELECT 'two spaces'"),
        ('SELECT "two  spaces"', 'SELECT "two spaces"'),
        ("SELECT $body$two  spaces$body$", "SELECT $body$two spaces$body$"),
        ("SELECT $$line one\nline two$$", "SELECT $$line one line two$$"),
        ("SELECT 'one'\n 'two'", "SELECT 'one' 'two'"),
    ],
)
def test_schema_normalization_cannot_hide_quoted_changes(left: str, right: str) -> None:
    assert proof._schema_statements(left) != proof._schema_statements(right)


def test_schema_normalization_ignores_only_unquoted_layout() -> None:
    assert proof._schema_statements("CREATE TABLE\n public.t (id integer);") == (
        proof._schema_statements("CREATE   TABLE public.t (id integer);\n")
    )


def test_function_body_comment_and_setup_looking_lines_are_preserved() -> None:
    body = "CREATE FUNCTION f() RETURNS text AS $fn$\n-- retained body\nSET x = y;\nRETURN 'a;b';\n$fn$ LANGUAGE plpgsql"
    statements = proof._schema_statements(body + "; SELECT 1;")
    assert statements[body] == 1
    assert statements["SELECT 1"] == 1
    assert sum(statements.values()) == 2


def test_dump_headers_are_removed_only_outside_quoted_sql() -> None:
    sql = "-- dump header\n\\restrict nonce\nSET statement_timeout = 0;\nCREATE TABLE t (id integer);\n\\unrestrict nonce\n"
    assert proof._schema_statements(sql) == {"CREATE TABLE t (id integer)": 1}


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 'unterminated",
        'SELECT "unterminated',
        "SELECT $fn$unterminated",
        "/* unfinished",
        "\\connect other\n",
    ],
)
def test_malformed_or_unexpected_dump_tokens_fail_closed(sql: str) -> None:
    with pytest.raises(ValueError):
        proof._schema_statements(sql)


def test_quotes_and_nested_comments_do_not_create_spurious_statement_boundaries() -> (
    None
):
    sql = "SELECT \"identifier;with\"\"quote\", 'literal;with''quote'; /* outer /* inner ; */ comment */ SELECT 2;"
    assert proof._schema_statements(sql) == {
        "SELECT \"identifier;with\"\"quote\", 'literal;with''quote'": 1,
        "SELECT 2": 1,
    }


_EARLY_GUARD_PLUGIN = r"""
import json
import os
import sys
import docker
import pytest
import sqlalchemy as sa

events = []
original_profile = sys.getprofile()

def deny_connection(*args, **kwargs):
    events.append("connection")
    raise AssertionError("early default database connection sentinel")

def deny_container(*args, **kwargs):
    events.append("container")
    raise AssertionError("isolation probe must not start Docker")

sa.Engine.connect = deny_connection
docker.APIClient = deny_container

def profile(frame, event, arg):
    if event != "call":
        return
    name = frame.f_code.co_name
    if name not in {
        "init_database", "_require_safe_database_reset",
        "_clear_mapped_database_rows", "clean_database"
    }:
        return
    path = frame.f_code.co_filename.replace("\\", "/")
    if (
        path.endswith("/tests/fixtures/database/database.py")
        and name == "clean_database"
    ):
        if name not in events:
            events.append(name)
        return
    if (
        (path.endswith("/app/core/database.py") and name == "init_database")
        or (
            path.endswith("/tests/fixtures/database/database.py")
            and name in {"_require_safe_database_reset", "_clear_mapped_database_rows"}
        )
    ):
        events.append(name)
        raise AssertionError("early default database sentinel: " + name)

sys.setprofile(profile)

def pytest_collectstart(collector):
    if (
        isinstance(collector, pytest.Module)
        and collector.path.name == "test_mvp_baseline_schema_equivalence.py"
    ):
        missing = os.environ["OWNED_FIXTURE_REMOVE"]
        if missing:
            delattr(collector.obj, missing)

def pytest_collection_modifyitems(items):
    assert len(items) == 1
    assert items[0].nodeid.endswith(
        "tests/integration/test_mvp_baseline_schema_equivalence.py"
        "::test_proof_owned_fixture_never_uses_default_database"
    )

def pytest_runtest_call(item):
    from app.core.config import settings
    from app.core.config.base import _ENV_FILE

    assert settings.database_url == "sqlite+aiosqlite:///:memory:"
    assert settings.database_read_replica_url is None
    assert _ENV_FILE is None

def pytest_sessionfinish(session, exitstatus):
    sys.setprofile(original_profile)
    print("\nOWNED_ISOLATION_EVENTS=" + json.dumps(events))
"""


@pytest.mark.parametrize(
    "missing, expected, hostile_aliases",
    [
        ("", None, False),
        ("", None, True),
        ("initialize_database_for_tests", "init_database", False),
        ("prepare_database", "_require_safe_database_reset", False),
        ("clean_database", "blocked default database: lazy access", False),
    ],
)
def test_proof_real_autouse_graph_isolated_before_conftest_import(
    pytester: pytest.Pytester,
    missing: str,
    expected: str | None,
    hostile_aliases: bool,
) -> None:
    pytester.makepyfile(owned_early_guard=_EARLY_GUARD_PLUGIN)
    # Pytester's supported launcher copies os.environ. Limit our overrides to
    # this synchronous child invocation and restore them before checking results.
    parent_fingerprint = hashlib.sha256(
        json.dumps(dict(os.environ), sort_keys=True).encode()
    ).digest()
    try:
        with pytest.MonkeyPatch.context() as child_environment:
            if hostile_aliases:
                for key, value in {
                    "PYTEST_ADDOPTS": "--collect-only",
                    "PYTEST_PLUGINS": "unowned_probe_plugin_must_not_load",
                    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                    "PYTEST_CURRENT_TEST": "unrelated-parent-case (call)",
                    "PYTEST_XDIST_WORKER": "gw_unowned",
                    "PYTEST_XDIST_WORKER_COUNT": "99",
                    "PYTEST_XDIST_TESTRUNUID": "unrelated-parent-run",
                    "PYTEST_XDIST_AUTO_NUM_WORKERS": "99",
                    "PYTEST_SHARD_MANIFEST": str(
                        pytester.path / "parent-manifest.json"
                    ),
                    "UNIVERSITY_ECOSYSTEM_DB_PERF_CAPTURE_REQUIRED": "1",
                }.items():
                    child_environment.setenv(key, value)
                for key in ("database_url", "DaTaBaSe_ReAd_RePlIcA_Url"):
                    child_environment.setenv(key, "not-a-database-url")
                for key in (
                    "DATABASE_URL_FILE",
                    "DaTaBaSe_Url_FiLe",
                    "DaTaBaSe_ReAd_RePlIcA_Url_FiLe",
                    "eNv_FiLe_PaTh",
                    "EnV_ExAmPlE_PaTh",
                ):
                    child_environment.setenv(
                        key, str(pytester.path / "absent-operator-input")
                    )

            # Plain DB inputs are case-insensitive. Isolate aliases only in
            # this child; production's exact-case FILE policy is unchanged.
            controlled = {
                "database_url",
                "database_url_file",
                "database_read_replica_url",
                "database_read_replica_url_file",
                "env_file_path",
                "env_example_path",
                "pytest_addopts",
                "pytest_plugins",
                "pytest_disable_plugin_autoload",
                "pytest_current_test",
                "pytest_xdist_worker",
                "pytest_xdist_worker_count",
                "pytest_xdist_testrunuid",
                "pytest_xdist_auto_num_workers",
                "pytest_shard_manifest",
                "university_ecosystem_db_perf_capture_required",
                "university_ecosystem_pytest_allow_testcontainers_fallback",
                "university_ecosystem_pytest_auto_database_url",
                "university_ecosystem_pytest_auto_database_dir",
                "university_ecosystem_pytest_database_mode",
                "university_ecosystem_pytest_external_database_url",
            }
            for key in tuple(os.environ):
                if key.casefold() in controlled:
                    child_environment.delenv(key)

            child_environment.setenv(
                "PYTHONPATH", os.pathsep.join((str(pytester.path), str(_ROOT)))
            )
            child_environment.setenv("RUN_INTEGRATION_TESTS", "1")
            child_environment.setenv("USE_TESTCONTAINERS_POSTGRES", "0")
            child_environment.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
            child_environment.setenv("ENV_FILE_PATH", "")
            child_environment.setenv("OWNED_FIXTURE_REMOVE", missing)
            child_environment.setenv("PYTEST_ADDOPTS", "")
            pytester.plugins.append("owned_early_guard")
            # Pytester's timeout bounds the wait, then kills the subprocess.
            # Its reap wait is unbounded; the host job remains outermost.
            result = pytester.runpytest_subprocess(
                f"{_PROOF}::test_proof_owned_fixture_never_uses_default_database",
                "-c",
                str(_ROOT / "pyproject.toml"),
                "--rootdir",
                str(_ROOT),
                "-o",
                "addopts=",
                "-p",
                "no:cacheprovider",
                "-q",
                "-s",
                timeout=60,
            )
    finally:
        current_fingerprint = hashlib.sha256(
            json.dumps(dict(os.environ), sort_keys=True).encode()
        ).digest()
        restored = current_fingerprint == parent_fingerprint
        assert restored, "Child isolation changed the parent environment"
    output = result.stdout.str()
    lines = [
        line
        for line in output.splitlines()
        if line.startswith("OWNED_ISOLATION_EVENTS=")
    ]
    assert len(lines) == 1
    events = json.loads(lines[0].split("=", 1)[1])
    assert "connection" not in events
    assert "container" not in events
    assert result.parseoutcomes().get("skipped", 0) == 0
    if expected is None:
        assert result.ret == pytest.ExitCode.OK
        result.assert_outcomes(passed=1)
        assert events == []
    else:
        assert result.ret == pytest.ExitCode.TESTS_FAILED
        assert result.parseoutcomes().get("errors", 0) >= 1
        assert expected in output
        assert events == (
            ["clean_database"] if missing == "clean_database" else [expected]
        )
