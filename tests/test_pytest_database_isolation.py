from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import closing
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_AUTO_DATABASE_URL_ENV = "UNIVERSITY_ECOSYSTEM_PYTEST_AUTO_DATABASE_URL"
_AUTO_DATABASE_DIR_ENV = "UNIVERSITY_ECOSYSTEM_PYTEST_AUTO_DATABASE_DIR"
_ALLOW_DATABASE_RESET_ENV = "UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET"
_DATABASE_MODE_ENV = "UNIVERSITY_ECOSYSTEM_PYTEST_DATABASE_MODE"
_EXTERNAL_DATABASE_URL_ENV = "UNIVERSITY_ECOSYSTEM_PYTEST_EXTERNAL_DATABASE_URL"
_REQUESTED_ENVIRONMENT_ENV = "UNIVERSITY_ECOSYSTEM_PYTEST_REQUESTED_ENVIRONMENT"
_REQUESTED_INTEGRATION_ENV = "UNIVERSITY_ECOSYSTEM_PYTEST_REQUESTED_INTEGRATION_TESTS"


def _database_url_from_fresh_pytest_process(
    *, environment_overrides: dict[str, str] | None = None
) -> subprocess.Popen[str]:
    environment = os.environ.copy()
    environment.pop("DATABASE_URL", None)
    environment.pop(_AUTO_DATABASE_URL_ENV, None)
    environment.pop(_AUTO_DATABASE_DIR_ENV, None)
    environment.pop(_ALLOW_DATABASE_RESET_ENV, None)
    environment.pop(_DATABASE_MODE_ENV, None)
    environment.pop(_EXTERNAL_DATABASE_URL_ENV, None)
    environment.pop(_REQUESTED_ENVIRONMENT_ENV, None)
    environment.pop(_REQUESTED_INTEGRATION_ENV, None)
    environment.pop("PYTEST_XDIST_WORKER", None)
    environment.pop("PYTEST_XDIST_WORKER_COUNT", None)
    environment.pop("PYTEST_XDIST_TESTRUNUID", None)
    environment.update(environment_overrides or {})
    return subprocess.Popen(  # noqa: S603 - fixed interpreter and inline probe
        [
            sys.executable,
            "-c",
            "import os; import tests.conftest; print(os.environ['DATABASE_URL'])",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_independent_pytest_processes_get_distinct_automatic_sqlite_databases() -> None:
    first = _database_url_from_fresh_pytest_process()
    second = _database_url_from_fresh_pytest_process()

    first_stdout, first_stderr = first.communicate(timeout=30)
    second_stdout, second_stderr = second.communicate(timeout=30)

    assert first.returncode == 0, first_stderr
    assert second.returncode == 0, second_stderr
    first_url = first_stdout.strip().splitlines()[-1]
    second_url = second_stdout.strip().splitlines()[-1]
    assert first_url.startswith("sqlite+aiosqlite:///")
    assert second_url.startswith("sqlite+aiosqlite:///")
    assert first_url != second_url
    first_path = Path(make_url(first_url).database or "")
    second_path = Path(make_url(second_url).database or "")
    assert first_path.is_absolute()
    assert second_path.is_absolute()
    assert not first_path.parent.exists()
    assert not second_path.parent.exists()


def test_explicit_database_url_is_not_replaced(tmp_path: Path) -> None:
    explicit_path = (tmp_path / "explicit.db").resolve()
    explicit_url = f"sqlite+aiosqlite:///{explicit_path.as_posix()}"

    process = _database_url_from_fresh_pytest_process(
        environment_overrides={"DATABASE_URL": explicit_url}
    )
    stdout, stderr = process.communicate(timeout=30)

    assert process.returncode == 0, stderr
    assert stdout.strip().splitlines()[-1] == explicit_url


def test_two_pytest_main_sessions_in_one_process_reuse_valid_owned_database() -> None:
    environment = os.environ.copy()
    for variable in (
        "DATABASE_URL",
        _AUTO_DATABASE_URL_ENV,
        _AUTO_DATABASE_DIR_ENV,
        _ALLOW_DATABASE_RESET_ENV,
        _DATABASE_MODE_ENV,
        _EXTERNAL_DATABASE_URL_ENV,
        _REQUESTED_ENVIRONMENT_ENV,
        _REQUESTED_INTEGRATION_ENV,
        "PYTEST_XDIST_WORKER",
        "PYTEST_XDIST_WORKER_COUNT",
        "PYTEST_XDIST_TESTRUNUID",
    ):
        environment.pop(variable, None)
    command = (
        "import pytest; "
        "args=['-q', 'tests/test_auth_repository.py::"
        "test_get_auth_repository_factory_returns_instance', '--tb=short']; "
        "first=pytest.main(args); second=pytest.main(args); "
        "raise SystemExit(first or second)"
    )

    process = subprocess.run(  # noqa: S603 - fixed interpreter and inline probe
        [sys.executable, "-c", command],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )

    assert process.returncode == 0, process.stdout + process.stderr


def test_explicit_sqlite_database_is_refused_without_reset_opt_in(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "university.db"
    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute("CREATE TABLE sentinel (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sentinel VALUES ('preserve-me')")
        connection.commit()
    explicit_url = f"sqlite+aiosqlite:///{database_path.resolve().as_posix()}"
    environment = os.environ.copy()
    for variable in (
        _AUTO_DATABASE_URL_ENV,
        _AUTO_DATABASE_DIR_ENV,
        _ALLOW_DATABASE_RESET_ENV,
        _DATABASE_MODE_ENV,
        _EXTERNAL_DATABASE_URL_ENV,
        _REQUESTED_ENVIRONMENT_ENV,
        _REQUESTED_INTEGRATION_ENV,
        "RUN_INTEGRATION_TESTS",
        "PYTEST_XDIST_WORKER",
        "PYTEST_XDIST_WORKER_COUNT",
        "PYTEST_XDIST_TESTRUNUID",
    ):
        environment.pop(variable, None)
    environment["DATABASE_URL"] = explicit_url
    environment.pop("ENVIRONMENT", None)

    process = subprocess.run(  # noqa: S603 - fixed interpreter and pytest target
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_auth_repository.py::test_get_auth_repository_factory_returns_instance",
            "--tb=short",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert process.returncode != 0
    assert (
        "explicit database reset is not authorized"
        in (process.stdout + process.stderr).lower()
    )
    with closing(sqlite3.connect(database_path)) as connection:
        assert connection.execute("SELECT value FROM sentinel").fetchone() == (
            "preserve-me",
        )


def test_environment_and_integration_selectors_do_not_authorize_database_reset(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "selector-test.db"
    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute("CREATE TABLE sentinel (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sentinel VALUES ('preserve-me')")
        connection.commit()
    environment = os.environ.copy()
    for variable in (
        _AUTO_DATABASE_URL_ENV,
        _AUTO_DATABASE_DIR_ENV,
        _ALLOW_DATABASE_RESET_ENV,
        _DATABASE_MODE_ENV,
        _EXTERNAL_DATABASE_URL_ENV,
        _REQUESTED_ENVIRONMENT_ENV,
        _REQUESTED_INTEGRATION_ENV,
        "PYTEST_XDIST_WORKER",
        "PYTEST_XDIST_WORKER_COUNT",
        "PYTEST_XDIST_TESTRUNUID",
    ):
        environment.pop(variable, None)
    environment["DATABASE_URL"] = (
        f"sqlite+aiosqlite:///{database_path.resolve().as_posix()}"
    )
    environment["ENVIRONMENT"] = "testing"
    environment["RUN_INTEGRATION_TESTS"] = "1"

    process = subprocess.run(  # noqa: S603 - fixed interpreter and pytest target
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_auth_repository.py::test_get_auth_repository_factory_returns_instance",
            "--tb=short",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert process.returncode != 0
    assert (
        "explicit database reset is not authorized"
        in (process.stdout + process.stderr).lower()
    )
    with closing(sqlite3.connect(database_path)) as connection:
        assert connection.execute("SELECT value FROM sentinel").fetchone() == (
            "preserve-me",
        )


def test_xdist_explicit_sqlite_preserves_location_driver_query_and_suffixes_stem(
    tmp_path: Path,
) -> None:
    database_path = (tmp_path / "custom-test.db").resolve()
    explicit_url = (
        f"sqlite+aiosqlite:///{database_path.as_posix()}?timeout=15&uri=false"
    )
    process = _database_url_from_fresh_pytest_process(
        environment_overrides={
            "DATABASE_URL": explicit_url,
            "PYTEST_XDIST_WORKER": "gw3",
            "ENVIRONMENT": "testing",
        }
    )
    stdout, stderr = process.communicate(timeout=30)

    assert process.returncode == 0, stderr
    result = make_url(stdout.strip().splitlines()[-1])
    expected_path = database_path.with_name("custom-test_gw3.db")
    assert result.drivername == "sqlite+aiosqlite"
    assert Path(result.database or "") == expected_path
    assert dict(result.query) == {"timeout": "15", "uri": "false"}


def test_testcontainers_postgres_failure_is_fail_closed() -> None:
    process = _database_url_from_fresh_pytest_process(
        environment_overrides={
            "USE_TESTCONTAINERS_POSTGRES": "1",
            "DOCKER_HOST": "tcp://127.0.0.1:1",
        }
    )
    stdout, stderr = process.communicate(timeout=30)

    assert process.returncode != 0
    assert "failed to start postgres testcontainer" in (stdout + stderr).lower()


def test_automatic_database_cleanup_requires_intact_ownership_sentinel() -> None:
    environment = os.environ.copy()
    for variable in (
        "DATABASE_URL",
        _AUTO_DATABASE_URL_ENV,
        _AUTO_DATABASE_DIR_ENV,
        _ALLOW_DATABASE_RESET_ENV,
    ):
        environment.pop(variable, None)
    command = (
        "import os; from pathlib import Path; import tests.conftest; "
        "directory=Path(os.environ['UNIVERSITY_ECOSYSTEM_PYTEST_AUTO_DATABASE_DIR']); "
        "sentinel=directory/'.pytest-owned'; "
        "assert sentinel.read_text(encoding='utf-8').startswith("
        "'university-ecosystem-pytest:'); "
        "sentinel.unlink(); (directory/'preserve.txt').write_text('safe'); "
        "print(directory, flush=True)"
    )

    process = subprocess.run(  # noqa: S603 - fixed interpreter and inline probe
        [sys.executable, "-c", command],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert process.returncode == 0, process.stdout + process.stderr
    database_dir = Path(process.stdout.strip().splitlines()[-1])
    try:
        assert (
            database_dir.parent
            == (
                Path(os.getenv("TEMP", database_dir.parent))
                / "university-ecosystem-pytest"
            ).resolve()
        )
        assert database_dir.name.startswith("pytest-")
        assert (database_dir / "preserve.txt").read_text(encoding="utf-8") == "safe"
    finally:
        shutil.rmtree(database_dir, ignore_errors=True)


def test_stale_scavenger_is_bounded_and_requires_valid_sentinel_age_and_dead_pid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tests.conftest as test_bootstrap

    root = (tmp_path / "university-ecosystem-pytest").resolve()
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(test_bootstrap, "_AUTO_DATABASE_ROOT", root)
    now = time.time()
    old = now - 7200

    def create_candidate(
        *, prefix: str, pid: int, stale: bool, valid_sentinel: bool
    ) -> Path:
        directory = Path(tempfile.mkdtemp(prefix=prefix, dir=root)).resolve()
        sentinel_prefix = (
            "university-ecosystem-pytest-basetemp"
            if prefix.startswith("basetemp-")
            else "university-ecosystem-pytest"
        )
        sentinel_value = f"{sentinel_prefix}:{pid}:{directory.name}\n"
        if not valid_sentinel:
            sentinel_value = "invalid\n"
        (directory / ".pytest-owned").write_text(sentinel_value, encoding="utf-8")
        (directory / "payload.txt").write_text("preserve", encoding="utf-8")
        timestamp = old if stale else now
        os.utime(directory, (timestamp, timestamp))
        return directory

    stale_dead = create_candidate(
        prefix="pytest-999999-", pid=999999, stale=True, valid_sentinel=True
    )
    recent_dead = create_candidate(
        prefix="pytest-999999-", pid=999999, stale=False, valid_sentinel=True
    )
    stale_invalid = create_candidate(
        prefix="pytest-999999-", pid=999999, stale=True, valid_sentinel=False
    )
    stale_live = create_candidate(
        prefix=f"basetemp-{os.getpid()}-",
        pid=os.getpid(),
        stale=True,
        valid_sentinel=True,
    )
    try:
        removed = test_bootstrap._scavenge_stale_owned_dirs(
            now=now, max_age_seconds=3600, limit=16
        )

        assert removed == 1
        assert not stale_dead.exists()
        assert recent_dead.exists()
        assert stale_invalid.exists()
        assert stale_live.exists()
    finally:
        for directory in (stale_dead, recent_dead, stale_invalid, stale_live):
            shutil.rmtree(directory, ignore_errors=True)


def test_opted_in_test_named_explicit_sqlite_preserves_unmanaged_tables(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "ci-test.db"
    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute("CREATE TABLE sentinel (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sentinel VALUES ('preserve-me')")
        connection.commit()
    environment = os.environ.copy()
    for variable in (
        _AUTO_DATABASE_URL_ENV,
        _AUTO_DATABASE_DIR_ENV,
        _DATABASE_MODE_ENV,
        _EXTERNAL_DATABASE_URL_ENV,
        _REQUESTED_ENVIRONMENT_ENV,
        _REQUESTED_INTEGRATION_ENV,
        "PYTEST_XDIST_WORKER",
        "PYTEST_XDIST_WORKER_COUNT",
        "PYTEST_XDIST_TESTRUNUID",
    ):
        environment.pop(variable, None)
    environment["DATABASE_URL"] = (
        f"sqlite+aiosqlite:///{database_path.resolve().as_posix()}"
    )
    environment[_ALLOW_DATABASE_RESET_ENV] = "1"

    process = subprocess.run(  # noqa: S603 - fixed interpreter and pytest target
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_auth_repository.py::test_get_auth_repository_factory_returns_instance",
            "--tb=short",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert process.returncode == 0, process.stdout + process.stderr
    with closing(sqlite3.connect(database_path)) as connection:
        assert connection.execute("SELECT value FROM sentinel").fetchone() == (
            "preserve-me",
        )


async def test_explicit_database_first_test_is_preclean_probe(
    db_session: AsyncSession,
) -> None:
    if os.environ.get("PYTEST_EXPLICIT_DATABASE_PRECLEAN_PROBE") != "1":
        pytest.skip("subprocess-only explicit database pre-clean probe")
    from app.models.schedule import Group

    count = await db_session.scalar(sa.select(sa.func.count()).select_from(Group))
    assert count == 0


def test_opted_in_explicit_database_is_clean_before_first_test_and_after(
    tmp_path: Path,
) -> None:
    from sqlalchemy import create_engine

    from app.models.schedule import Group

    database_path = tmp_path / "preclean-test.db"
    sync_engine = create_engine(f"sqlite:///{database_path.resolve().as_posix()}")
    try:
        Group.__table__.create(sync_engine)
        with sync_engine.begin() as connection:
            connection.execute(
                Group.__table__.insert().values(
                    id=uuid.uuid4(), name="seeded-before-pytest"
                )
            )
    finally:
        sync_engine.dispose()

    environment = os.environ.copy()
    for variable in (
        _AUTO_DATABASE_URL_ENV,
        _AUTO_DATABASE_DIR_ENV,
        _DATABASE_MODE_ENV,
        _EXTERNAL_DATABASE_URL_ENV,
        _REQUESTED_ENVIRONMENT_ENV,
        _REQUESTED_INTEGRATION_ENV,
        "PYTEST_XDIST_WORKER",
        "PYTEST_XDIST_WORKER_COUNT",
        "PYTEST_XDIST_TESTRUNUID",
    ):
        environment.pop(variable, None)
    environment["DATABASE_URL"] = (
        f"sqlite+aiosqlite:///{database_path.resolve().as_posix()}"
    )
    environment[_ALLOW_DATABASE_RESET_ENV] = "1"
    environment["PYTEST_EXPLICIT_DATABASE_PRECLEAN_PROBE"] = "1"

    process = subprocess.run(  # noqa: S603 - fixed interpreter and pytest target
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_pytest_database_isolation.py::test_explicit_database_first_test_is_preclean_probe",
            "--tb=short",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert process.returncode == 0, process.stdout + process.stderr
    with closing(sqlite3.connect(database_path)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM groups").fetchone() == (0,)


def test_test_named_explicit_postgres_still_requires_caller_opt_in() -> None:
    environment = os.environ.copy()
    for variable in (
        _AUTO_DATABASE_URL_ENV,
        _AUTO_DATABASE_DIR_ENV,
        _ALLOW_DATABASE_RESET_ENV,
        _DATABASE_MODE_ENV,
        _EXTERNAL_DATABASE_URL_ENV,
        _REQUESTED_ENVIRONMENT_ENV,
        _REQUESTED_INTEGRATION_ENV,
        "RUN_INTEGRATION_TESTS",
        "PYTEST_XDIST_WORKER",
        "PYTEST_XDIST_WORKER_COUNT",
        "PYTEST_XDIST_TESTRUNUID",
    ):
        environment.pop(variable, None)
    environment.pop("ENVIRONMENT", None)
    environment["DATABASE_URL"] = (
        "postgresql+asyncpg://test:test@127.0.0.1:1/test_external"  # pragma: allowlist secret
    )

    process = subprocess.run(  # noqa: S603 - fixed interpreter and pytest target
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_auth_repository.py::test_get_auth_repository_factory_returns_instance",
            "--tb=short",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        # Importing the full application/plugin graph on Windows can exceed 30
        # seconds on a contended CI worker before the fail-closed reset guard is
        # evaluated. Keep the probe bounded while matching neighboring
        # subprocess integration checks.
        timeout=60,
        check=False,
    )

    assert process.returncode != 0
    assert (
        "explicit database reset is not authorized"
        in (process.stdout + process.stderr).lower()
    )


def test_explicit_in_memory_sqlite_never_requires_destructive_reset_opt_in() -> None:
    environment = os.environ.copy()
    for variable in (
        _AUTO_DATABASE_URL_ENV,
        _AUTO_DATABASE_DIR_ENV,
        _ALLOW_DATABASE_RESET_ENV,
        _DATABASE_MODE_ENV,
        _EXTERNAL_DATABASE_URL_ENV,
        _REQUESTED_ENVIRONMENT_ENV,
        _REQUESTED_INTEGRATION_ENV,
        "RUN_INTEGRATION_TESTS",
        "PYTEST_XDIST_WORKER",
        "PYTEST_XDIST_WORKER_COUNT",
        "PYTEST_XDIST_TESTRUNUID",
    ):
        environment.pop(variable, None)
    environment.pop("ENVIRONMENT", None)
    environment["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

    process = subprocess.run(  # noqa: S603 - fixed interpreter and pytest target
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_auth_repository.py::test_get_auth_repository_factory_returns_instance",
            "--tb=short",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert process.returncode == 0, process.stdout + process.stderr


def test_postgres_xdist_database_name_is_unique_per_test_run() -> None:
    base_url = "postgresql+asyncpg://test:test@localhost:5432/test_suite"  # pragma: allowlist secret
    first = _database_url_from_fresh_pytest_process(
        environment_overrides={
            "DATABASE_URL": base_url,
            "PYTEST_XDIST_WORKER": "gw0",
            "PYTEST_XDIST_TESTRUNUID": "run-one",
            "ENVIRONMENT": "testing",
        }
    )
    second = _database_url_from_fresh_pytest_process(
        environment_overrides={
            "DATABASE_URL": base_url,
            "PYTEST_XDIST_WORKER": "gw0",
            "PYTEST_XDIST_TESTRUNUID": "run-two",
            "ENVIRONMENT": "testing",
        }
    )
    first_stdout, first_stderr = first.communicate(timeout=30)
    second_stdout, second_stderr = second.communicate(timeout=30)

    assert first.returncode == 0, first_stderr
    assert second.returncode == 0, second_stderr
    first_url = make_url(first_stdout.strip().splitlines()[-1])
    second_url = make_url(second_stdout.strip().splitlines()[-1])
    assert first_url.database != second_url.database
    assert (first_url.database or "").startswith("test_suite_gw0_")
    assert (second_url.database or "").startswith("test_suite_gw0_")
    assert len(first_url.database or "") <= 63
    assert len(second_url.database or "") <= 63


def test_tmp_path_subprocess_probe(tmp_path: Path) -> None:
    probe_id = os.environ.get("PYTEST_TMP_PATH_ISOLATION_PROBE_ID")
    barrier_value = os.environ.get("PYTEST_TMP_PATH_ISOLATION_BARRIER")
    if probe_id is None or barrier_value is None:
        pytest.skip("subprocess-only tmp_path isolation probe")
    assert probe_id is not None
    assert barrier_value is not None
    barrier = Path(barrier_value)
    marker = tmp_path / "owner.txt"
    marker.write_text(probe_id, encoding="utf-8")
    (barrier / f"ready-{probe_id}").write_text("ready", encoding="utf-8")
    deadline = time.monotonic() + 15
    while len(list(barrier.glob("ready-*"))) < 2:
        if time.monotonic() >= deadline:
            pytest.fail("concurrent tmp_path probe timed out at barrier")
        time.sleep(0.05)
    for _ in range(40):
        assert marker.read_text(encoding="utf-8") == probe_id
        time.sleep(0.05)


def test_independent_pytest_processes_get_distinct_tmp_path_roots() -> None:
    barrier = Path(tempfile.mkdtemp(prefix="pytest-basetemp-barrier-")).resolve()
    processes: list[subprocess.Popen[str]] = []
    try:
        for probe_id in ("first", "second"):
            environment = os.environ.copy()
            for variable in (
                "DATABASE_URL",
                _AUTO_DATABASE_URL_ENV,
                _AUTO_DATABASE_DIR_ENV,
                _DATABASE_MODE_ENV,
                _EXTERNAL_DATABASE_URL_ENV,
                _REQUESTED_ENVIRONMENT_ENV,
                _REQUESTED_INTEGRATION_ENV,
                "PYTEST_XDIST_WORKER",
                "PYTEST_XDIST_WORKER_COUNT",
                "PYTEST_XDIST_TESTRUNUID",
            ):
                environment.pop(variable, None)
            environment["PYTEST_TMP_PATH_ISOLATION_PROBE_ID"] = probe_id
            environment["PYTEST_TMP_PATH_ISOLATION_BARRIER"] = str(barrier)
            processes.append(
                subprocess.Popen(  # noqa: S603 - fixed interpreter/test target
                    [
                        sys.executable,
                        "-m",
                        "pytest",
                        "-q",
                        "tests/test_pytest_database_isolation.py::test_tmp_path_subprocess_probe",
                        "--tb=short",
                    ],
                    cwd=PROJECT_ROOT,
                    env=environment,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            )
        results = [process.communicate(timeout=60) for process in processes]
        for process, (stdout, stderr) in zip(processes, results, strict=True):
            assert process.returncode == 0, stdout + stderr
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
        shutil.rmtree(barrier, ignore_errors=True)
