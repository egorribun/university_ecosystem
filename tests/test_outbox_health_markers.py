from __future__ import annotations

import asyncio
import importlib
import os
import shlex
import shutil
import sys
import time
from pathlib import Path
from typing import Literal

import pytest

from app.workers import outbox


def _write_stale_pid_one_markers(runtime_dir: Path) -> tuple[Path, Path]:
    runtime_dir.mkdir(parents=True, exist_ok=True)
    pid_path = runtime_dir / "worker.pid"
    heartbeat_path = runtime_dir / "worker.heartbeat"
    pid_path.write_text("1", encoding="ascii")
    heartbeat_path.write_text(str(time.time_ns()), encoding="ascii")
    os.utime(heartbeat_path, None)
    return pid_path, heartbeat_path


def test_clear_runtime_markers_removes_only_owned_files_and_allows_missing(
    tmp_path: Path,
) -> None:
    runtime_dir = tmp_path / "runtime"
    pid_path, heartbeat_path = _write_stale_pid_one_markers(runtime_dir)
    unrelated = runtime_dir / "unrelated"
    unrelated.write_text("keep", encoding="ascii")

    returned_paths = outbox._clear_runtime_markers(runtime_dir)

    assert returned_paths == (pid_path, heartbeat_path)
    assert not pid_path.exists()
    assert not heartbeat_path.exists()
    assert unrelated.read_text(encoding="ascii") == "keep"
    assert outbox._clear_runtime_markers(runtime_dir) == (pid_path, heartbeat_path)


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked_stage", ["database", "nats"])
async def test_main_clears_fresh_stale_pid_one_markers_before_database_or_nats(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    blocked_stage: Literal["database", "nats"],
) -> None:
    runtime_dir = tmp_path / "runtime"
    pid_path, heartbeat_path = _write_stale_pid_one_markers(runtime_dir)
    unrelated = runtime_dir / "unrelated"
    unrelated.write_text("keep", encoding="ascii")
    assert time.time() - heartbeat_path.stat().st_mtime < 30
    monkeypatch.setenv("OUTBOX_WORKER_RUNTIME_DIR", str(runtime_dir))

    database = importlib.import_module("app.core.database")
    events = importlib.import_module("app.core.events")
    nats_module = importlib.import_module("app.core.nats_broker")
    handlers = importlib.import_module("app.services.event_handlers")
    blocked = asyncio.Event()

    def assert_markers_cleared(stage: str) -> None:
        assert not pid_path.exists(), f"stale PID marker remains at {stage}"
        assert not heartbeat_path.exists(), f"stale heartbeat remains at {stage}"
        assert unrelated.read_text(encoding="ascii") == "keep"

    async def block_at_database(*, max_attempts: int) -> None:
        assert max_attempts == 10
        assert_markers_cleared("database wait")
        blocked.set()
        await asyncio.Event().wait()

    async def block_at_nats() -> None:
        assert_markers_cleared("NATS connect")
        blocked.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(
        database, "init_database", lambda: assert_markers_cleared("database init")
    )
    monkeypatch.setattr(
        database,
        "wait_db",
        block_at_database if blocked_stage == "database" else _async_noop,
    )
    monkeypatch.setattr(events, "register_event_listeners", _async_noop)
    monkeypatch.setattr(handlers, "configure_event_handlers", lambda: None)
    monkeypatch.setattr(
        nats_module.broker,
        "connect",
        block_at_nats if blocked_stage == "nats" else _async_noop,
    )

    task = asyncio.create_task(outbox.main())
    try:
        await asyncio.wait_for(blocked.wait(), timeout=2)
        assert_markers_cleared(blocked_stage)
        assert not task.done()
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


async def _async_noop(*args: object, **kwargs: object) -> None:
    del args, kwargs


@pytest.mark.asyncio
async def test_main_fails_closed_before_database_when_marker_removal_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "worker.pid").mkdir()
    (runtime_dir / "worker.heartbeat").write_text("stale", encoding="ascii")
    monkeypatch.setenv("OUTBOX_WORKER_RUNTIME_DIR", str(runtime_dir))

    database = importlib.import_module("app.core.database")
    initialized = False

    def observe_database_init() -> None:
        nonlocal initialized
        initialized = True

    monkeypatch.setattr(database, "init_database", observe_database_init)

    with pytest.raises(OSError):
        await outbox.main()

    assert initialized is False
    assert (runtime_dir / "worker.heartbeat").exists()


@pytest.mark.asyncio
async def test_main_publishes_fresh_markers_after_nats_and_clears_them_on_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_dir = tmp_path / "runtime"
    monkeypatch.setenv("OUTBOX_WORKER_RUNTIME_DIR", str(runtime_dir))
    pid_path = runtime_dir / "worker.pid"
    heartbeat_path = runtime_dir / "worker.heartbeat"
    database = importlib.import_module("app.core.database")
    events = importlib.import_module("app.core.events")
    nats_module = importlib.import_module("app.core.nats_broker")
    handlers = importlib.import_module("app.services.event_handlers")
    calls: list[str] = []

    monkeypatch.setattr(database, "init_database", lambda: calls.append("database"))
    monkeypatch.setattr(database, "wait_db", _async_noop)
    monkeypatch.setattr(events, "register_event_listeners", _async_noop)
    monkeypatch.setattr(handlers, "configure_event_handlers", lambda: None)

    async def connect() -> None:
        calls.append("nats-connect")

    async def close() -> None:
        calls.append("nats-close")

    monkeypatch.setattr(nats_module.broker, "connect", connect)
    monkeypatch.setattr(nats_module.broker, "close", close)

    async def idle_listener(self: outbox.OutboxWorker) -> None:
        await asyncio.Event().wait()

    async def no_pending_events(self: outbox.OutboxWorker) -> int:
        return 0

    monkeypatch.setattr(outbox.OutboxWorker, "_listen_loop", idle_listener)
    monkeypatch.setattr(outbox.OutboxWorker, "process_batch", no_pending_events)

    async def stop_after_heartbeat(stop_event: asyncio.Event) -> None:
        deadline = asyncio.get_running_loop().time() + 2
        while not heartbeat_path.exists():
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError("worker heartbeat was not written")
            await asyncio.sleep(0.001)
        assert pid_path.read_text(encoding="ascii") == str(os.getpid())
        calls.append("fresh-markers")
        stop_event.set()

    monkeypatch.setattr(outbox, "_wait_for_signals", stop_after_heartbeat)

    await asyncio.wait_for(outbox.main(), timeout=3)

    assert calls == ["database", "nats-connect", "fresh-markers", "nats-close"]
    assert not pid_path.exists()
    assert not heartbeat_path.exists()


def _startup_prelude_from_chart() -> str:
    chart_path = (
        Path(__file__).resolve().parents[1]
        / "charts"
        / "university-ecosystem"
        / "templates"
        / "outbox-worker-deployment.yaml"
    )
    lines = chart_path.read_text(encoding="utf-8").splitlines()
    command = '          command: ["/bin/sh", "-ec"]'
    assert lines.count(command) == 1
    start = lines.index(command)
    assert lines[start + 1 : start + 3] == ["          args:", "            - |"]

    body: list[str] = []
    for line in lines[start + 3 :]:
        if not line.startswith("              "):
            break
        body.append(line[14:])

    assert body == [
        "rm -f -- /tmp/worker.pid /tmp/worker.heartbeat",
        "exec python -m app.workers.outbox",
    ]
    return "\n".join(body) + "\n"


def _posix_shell() -> str:
    if os.name == "nt":
        # Prefer usr/bin so sibling POSIX utilities such as rm are available.
        for candidate in (
            Path("C:/Program Files/Git/usr/bin/sh.exe"),
            Path("C:/Program Files/Git/bin/sh.exe"),
        ):
            if candidate.is_file():
                return str(candidate)
    executable = shutil.which("sh")
    if executable:
        return executable
    raise AssertionError("a POSIX sh executable is required for the startup contract")


async def _communicate_bounded(
    process: asyncio.subprocess.Process, timeout: float
) -> tuple[bytes, bytes]:
    try:
        return await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError:
        process.kill()
        await process.communicate()
        raise AssertionError(
            "startup shell subprocess exceeded its test deadline"
        ) from None


async def _shell_path(path: Path, shell: str) -> str:
    value = path.resolve().as_posix()
    if os.name == "nt":
        cygpath = Path(shell).parent / "cygpath.exe"
        if not cygpath.is_file():
            located = shutil.which("cygpath")
            assert located is not None, "Git Bash cygpath is required on Windows"
            cygpath = Path(located)
        process = await asyncio.create_subprocess_exec(
            str(cygpath),
            "-u",
            str(path.resolve()),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await _communicate_bounded(process, timeout=5)
        assert process.returncode == 0, (
            "cygpath could not convert the private test path"
        )
        value = stdout.decode("utf-8").strip()
        assert value.startswith("/"), "cygpath must return an absolute POSIX path"
    return shlex.quote(value)


async def _run_startup_script(
    tmp_path: Path, runtime_dir: Path, package_init: str
) -> tuple[int, Path, str]:
    shell = _posix_shell()
    script = _startup_prelude_from_chart()
    pid_path = runtime_dir / "worker.pid"
    heartbeat_path = runtime_dir / "worker.heartbeat"
    pid_literal, heartbeat_literal = shlex.split(script.splitlines()[0])[-2:]
    script = script.replace(pid_literal, await _shell_path(pid_path, shell))
    script = script.replace(heartbeat_literal, await _shell_path(heartbeat_path, shell))

    workdir = tmp_path / "python-import"
    package = workdir / "app"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(package_init, encoding="utf-8")
    observation = tmp_path / "python-import-observation"
    env = os.environ.copy()
    path_entries = [str(Path(sys.executable).resolve().parent)]
    if os.name == "nt":
        path_entries.append(str(Path(shell).resolve().parent))
    path_entries.append(env.get("PATH", ""))
    env["PATH"] = os.pathsep.join(path_entries)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["OUTBOX_TEST_MARKER_DIR"] = str(runtime_dir)
    env["OUTBOX_TEST_IMPORT_OBSERVATION"] = str(observation)
    process = await asyncio.create_subprocess_exec(
        shell,
        "-ec",
        script,
        cwd=workdir,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await _communicate_bounded(process, timeout=10)
    if process.returncode is None:
        raise AssertionError("startup shell did not report an exit code")
    output = (stdout + stderr).decode("utf-8", errors="replace")
    return process.returncode, observation, output


@pytest.mark.asyncio
async def test_deployment_clears_stale_markers_before_python_import_failure(
    tmp_path: Path,
) -> None:
    runtime_dir = tmp_path / "private-runtime"
    runtime_dir.mkdir()
    pid_path, heartbeat_path = _write_stale_pid_one_markers(runtime_dir)
    unrelated = runtime_dir / "unrelated"
    unrelated.write_text("keep", encoding="ascii")
    package_init = """\
import os
from pathlib import Path

runtime = Path(os.environ["OUTBOX_TEST_MARKER_DIR"])
observation = Path(os.environ["OUTBOX_TEST_IMPORT_OBSERVATION"])
cleared = not (runtime / "worker.pid").exists() and not (runtime / "worker.heartbeat").exists()
observation.write_text("cleared" if cleared else "stale", encoding="ascii")
raise ImportError("intentional synthetic worker import failure")
"""
    returncode, observation, output = await _run_startup_script(
        tmp_path, runtime_dir, package_init
    )

    assert returncode != 0, output
    assert observation.read_text(encoding="ascii") == "cleared"
    assert not pid_path.exists()
    assert not heartbeat_path.exists()
    assert unrelated.read_text(encoding="ascii") == "keep"


@pytest.mark.asyncio
async def test_deployment_does_not_exec_python_when_marker_removal_fails(
    tmp_path: Path,
) -> None:
    runtime_dir = tmp_path / "private-runtime"
    runtime_dir.mkdir()
    (runtime_dir / "worker.pid").mkdir()
    (runtime_dir / "worker.heartbeat").write_text("stale", encoding="ascii")
    unrelated = runtime_dir / "unrelated"
    unrelated.write_text("keep", encoding="ascii")
    package_init = """\
import os
from pathlib import Path

Path(os.environ["OUTBOX_TEST_IMPORT_OBSERVATION"]).write_text(
    "python-exec-reached", encoding="ascii"
)
"""
    returncode, observation, output = await _run_startup_script(
        tmp_path, runtime_dir, package_init
    )

    assert returncode != 0, output
    assert not observation.exists()
    assert (runtime_dir / "worker.pid").is_dir()
    assert unrelated.read_text(encoding="ascii") == "keep"
