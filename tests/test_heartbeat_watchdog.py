"""Contracts for the O9 heartbeat watchdog."""

from __future__ import annotations

import json
import multiprocessing
import os
import signal
import subprocess
import sys
import time
from io import BytesIO
from pathlib import Path

import pytest

from scripts.quality import heartbeat_watchdog as watchdog
from scripts.quality.heartbeat_watchdog import Monitor, Probe

PY = sys.executable


def _probe(
    events: int = 0, mtime: float | None = None, cpu: float | None = None
) -> Probe:
    return Probe(
        output_events=events, heartbeat_mtime=mtime, cpu_seconds=cpu, rss_bytes=None
    )


def _monitor(stall: float = 10.0, grace: float = 5.0) -> Monitor:
    return Monitor("stage", stall_seconds=stall, grace_seconds=grace, started_at=100.0)


# ---------------------------------------------------------------------------
# Monitor state machine
# ---------------------------------------------------------------------------


def test_silent_but_busy_process_is_not_stalled() -> None:
    monitor = _monitor()
    for step in range(10):
        # No output for 45 s, but the group keeps consuming CPU.
        assert monitor.observe(_probe(cpu=float(step)), now=100.0 + step * 5) == "wait"
    assert monitor.status == "running"


def test_stalls_exactly_after_the_silent_window() -> None:
    monitor = _monitor(stall=10.0)
    assert monitor.observe(_probe(cpu=1.0), now=100.0) == "wait"
    assert monitor.observe(_probe(cpu=1.0), now=109.999) == "wait"

    assert monitor.observe(_probe(cpu=1.0), now=110.0) == "term"
    assert monitor.status == "stalled"


def test_escalates_to_kill_only_after_the_grace_period() -> None:
    monitor = _monitor(stall=10.0, grace=5.0)
    monitor.observe(_probe(), now=100.0)
    assert monitor.observe(_probe(), now=110.0) == "term"

    assert monitor.observe(_probe(), now=114.999) == "wait"
    assert monitor.observe(_probe(), now=115.0) == "kill"


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (_probe(events=1), _probe(events=2)),
        (_probe(mtime=1.0), _probe(mtime=2.0)),
        (_probe(mtime=None), _probe(mtime=2.0)),
        (_probe(cpu=1.0), _probe(cpu=1.5)),
    ],
    ids=["output", "heartbeat", "heartbeat-appears", "cpu"],
)
def test_each_progress_signal_resets_the_silent_window(
    before: Probe, after: Probe
) -> None:
    monitor = _monitor(stall=10.0)
    monitor.observe(before, now=100.0)

    assert monitor.observe(after, now=109.0) == "wait"
    assert monitor.observe(after, now=118.9) == "wait"
    assert monitor.last_progress_at == 109.0


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (_probe(cpu=None), _probe(cpu=None)),
        (_probe(cpu=None), _probe(cpu=5.0)),
        (_probe(cpu=5.0), _probe(cpu=None)),
        (_probe(cpu=5.0), _probe(cpu=4.0)),
    ],
    ids=["unknown", "appears", "disappears", "decreases"],
)
def test_unknown_or_falling_cpu_is_not_progress(before: Probe, after: Probe) -> None:
    monitor = _monitor(stall=10.0)
    monitor.observe(before, now=100.0)

    assert monitor.observe(after, now=110.0) == "term"


def test_report_describes_the_current_state() -> None:
    monitor = _monitor()
    monitor.observe(Probe(3, 7.0, 1.25, 4096), now=102.0)

    report = monitor.report(104.5, pid=42, exit_code=None)

    assert report == {
        "stage": "stage",
        "status": "running",
        "pid": 42,
        "started_at": 100.0,
        "last_progress_at": 102.0,
        "silent_seconds": 2.5,
        "exit_code": None,
        "probe": {
            "output_events": 3,
            "heartbeat_mtime": 7.0,
            "cpu_seconds": 1.25,
            "rss_bytes": 4096,
        },
    }
    assert (
        Monitor("s", 1, 1, started_at=0.0).report(0.0, pid=1, exit_code=0)["probe"]
        is None
    )


# ---------------------------------------------------------------------------
# /proc resource counters
# ---------------------------------------------------------------------------


def _stat(pid: int, pgrp: int, utime: int, stime: int, rss: int) -> str:
    fields = ["S", "1", str(pgrp)] + ["0"] * 8 + [str(utime), str(stime)] + ["0"] * 8
    fields += [str(rss)]
    return f"{pid} (worker (x)) " + " ".join(fields)


def test_group_resources_sums_only_the_monitored_group(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        watchdog.os,
        "sysconf",
        lambda name: 100 if name == "SC_CLK_TCK" else 4096,
        raising=False,
    )
    for pid, pgrp, utime, stime, rss in [
        (10, 7, 150, 50, 3),
        (11, 7, 50, 0, 2),
        (12, 8, 999, 999, 999),
    ]:
        (tmp_path / str(pid)).mkdir()
        (tmp_path / str(pid) / "stat").write_text(
            _stat(pid, pgrp, utime, stime, rss), encoding="utf-8"
        )
    (tmp_path / "self").mkdir()
    (tmp_path / "13").mkdir()  # exited while listing: no stat file

    assert watchdog.group_resources(7, proc_root=tmp_path) == (2.5, 5 * 4096)


def test_group_resources_are_unknown_without_proc(tmp_path: Path) -> None:
    assert watchdog.group_resources(7, proc_root=tmp_path / "missing") == (None, None)


# ---------------------------------------------------------------------------
# Real processes
# ---------------------------------------------------------------------------


def _run(tmp_path: Path, code: str, **kwargs) -> tuple[int, dict[str, object]]:
    report = tmp_path / "heartbeat.json"
    options = {"stall_seconds": 30.0, "grace_seconds": 1.0, "poll_seconds": 0.05}
    options.update(kwargs)
    exit_code = watchdog.run(
        [PY, "-c", code], stage="probe", report_path=report, **options
    )
    return exit_code, json.loads(report.read_text(encoding="utf-8"))


def test_finished_command_keeps_its_exit_code(tmp_path: Path, capfd) -> None:
    exit_code, report = _run(tmp_path, "import sys; print('done'); sys.exit(3)")

    assert exit_code == 3
    assert report["status"] == "exited"
    assert report["exit_code"] == 3
    assert "done" in capfd.readouterr().out


def test_stalled_command_is_terminated_with_its_partial_report(tmp_path: Path) -> None:
    started = time.monotonic()
    exit_code, report = _run(
        tmp_path,
        # Bound by the watchdog's 0.5 s stall window; 60 s is the broken-run cap.
        "import time; print('started', flush=True); time.sleep(60)",
        stall_seconds=0.5,
    )

    assert exit_code == watchdog.STALLED_EXIT_CODE
    assert report["status"] == "stalled"
    assert report["stage"] == "probe"
    assert time.monotonic() - started < 20


def test_touching_the_heartbeat_file_keeps_a_silent_command_alive(
    tmp_path: Path,
) -> None:
    heartbeat = tmp_path / "beat"
    code = (
        "import pathlib, sys, time\n"
        f"beat = pathlib.Path({str(heartbeat)!r})\n"
        "for i in range(15):\n"
        # Bound: 15 heartbeats at 0.1 s, testing real file-mtime progress.
        "    beat.write_text(str(i)); time.sleep(0.1)\n"
    )

    exit_code, report = _run(
        tmp_path, code, stall_seconds=0.6, heartbeat_file=heartbeat
    )

    assert exit_code == 0
    assert report["status"] == "exited"


# QUALITY-O9 @egorribun: process groups and orphan reaping are POSIX
# semantics; the Linux CI lane executes this contract.
@pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX-only")
def test_orphaned_children_are_reaped_after_the_command_exits(tmp_path: Path) -> None:
    pid_file = tmp_path / "orphan.pid"
    code = (
        "import subprocess, sys\n"
        # Bound: watchdog reaps this child after its parent exits; child caps at 60 s.
        f"child = subprocess.Popen([{PY!r}, '-c', 'import time; time.sleep(60)'])\n"
        f"open({str(pid_file)!r}, 'w').write(str(child.pid))\n"
    )

    exit_code, _ = _run(tmp_path, code)

    assert exit_code == 0
    orphan = int(pid_file.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.kill(orphan, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)  # Bound by the five-second orphan-reaping deadline.
    else:  # pragma: no cover - only reached when reaping regressed
        pytest.fail("orphaned child survived the watchdog")


def test_main_requires_a_command() -> None:
    with pytest.raises(SystemExit) as error:
        watchdog.main(
            ["--stage", "s", "--report", "r.json", "--stall-seconds", "1", "--"]
        )
    assert error.value.code == 2


def test_main_runs_the_command_after_the_separator(tmp_path: Path) -> None:
    report = tmp_path / "r.json"

    exit_code = watchdog.main(
        [
            "--stage",
            "cli",
            "--report",
            str(report),
            "--stall-seconds",
            "30",
            "--poll-seconds",
            "0.05",
            "--",
            PY,
            "-c",
            "pass",
        ]
    )

    assert exit_code == 0
    assert json.loads(report.read_text(encoding="utf-8"))["stage"] == "cli"


@pytest.mark.parametrize("option", ["stall-seconds", "grace-seconds", "poll-seconds"])
@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "-inf"])
def test_main_rejects_unsafe_timing_before_spawning(option, value, monkeypatch):
    def unexpected_spawn(*args, **kwargs):
        pytest.fail("invalid timing must be rejected before spawning")

    monkeypatch.setattr(watchdog.subprocess, "Popen", unexpected_spawn)
    with pytest.raises(SystemExit) as error:
        watchdog.main(
            [
                "--stage",
                "s",
                "--report",
                "r.json",
                "--stall-seconds",
                "1",
                f"--{option}={value}",
                "--",
                PY,
                "-c",
                "pass",
            ]
        )
    assert error.value.code == 2


@pytest.mark.parametrize("option", ["stall_seconds", "grace_seconds", "poll_seconds"])
@pytest.mark.parametrize(
    "value", [0.0, -1.0, float("nan"), float("inf"), float("-inf")]
)
def test_run_rejects_unsafe_timing_before_spawning(
    tmp_path, option, value, monkeypatch
):
    def unexpected_spawn(*args, **kwargs):
        pytest.fail("invalid timing must be rejected before spawning")

    monkeypatch.setattr(watchdog.subprocess, "Popen", unexpected_spawn)
    options = {"stall_seconds": 1.0, "grace_seconds": 1.0, "poll_seconds": 0.05}
    options[option] = value
    with pytest.raises(ValueError, match="finite and positive"):
        watchdog.run(
            [PY, "-c", "pass"], stage="s", report_path=tmp_path / "r.json", **options
        )


def _wait_for_owned_child(pid_file: Path) -> int:
    # QUALITY-O9 @egorribun: readiness wait is capped at five seconds; the
    # test-created child writes this file after installing its TERM handler.
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if pid_file.exists():
            ready_pid = pid_file.read_text(encoding="ascii").strip()
            if ready_pid:
                return int(ready_pid)
        time.sleep(0.01)  # Bound by the readiness deadline above.
    pytest.fail("test child did not become ready within five seconds")


def _term_ignoring_child(pid_file: Path) -> str:
    return (
        "import os, pathlib, signal, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        f"pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid()), encoding='ascii')\n"
        # QUALITY-O9 @egorribun: 60 seconds is a fallback cap; the watchdog
        # Bound: the test's finally block also terminates this owned group.
        "time.sleep(60)\n"
    )


@pytest.mark.skipif(os.name != "posix", reason="owned process groups require POSIX")
@pytest.mark.parametrize("failure_point", ["probe", "report", "probe-and-final-report"])
def test_supervisor_failure_reaps_term_ignoring_child_and_preserves_error(
    tmp_path, monkeypatch, failure_point
):
    pid_file = tmp_path / "owned.pid"
    report = tmp_path / "heartbeat.json"
    original_spawn = subprocess.Popen
    original_write = watchdog._write
    original_signal_group = watchdog._signal_group
    children = []
    shutdown_signals = []
    expected = OSError(f"original {failure_point} failure")

    def owned_spawn(*args, **kwargs):
        child = original_spawn(*args, **kwargs)
        children.append(child)
        _wait_for_owned_child(pid_file)
        return child

    def fail_probe(*args, **kwargs):
        raise expected

    writes = 0

    def fail_first_write(path, payload):
        nonlocal writes
        writes += 1
        if writes == 1:
            raise expected
        original_write(path, payload)

    def fail_final_write(path, payload):
        raise OSError("secondary final report failure")

    def record_signal_group(child, *, force):
        shutdown_signals.append(force)
        original_signal_group(child, force=force)

    monkeypatch.setattr(watchdog.subprocess, "Popen", owned_spawn)
    monkeypatch.setattr(watchdog, "_signal_group", record_signal_group)
    if failure_point.startswith("probe"):
        monkeypatch.setattr(watchdog, "group_resources", fail_probe)
        if failure_point == "probe-and-final-report":
            monkeypatch.setattr(watchdog, "_write", fail_final_write)
    else:
        monkeypatch.setattr(watchdog, "_write", fail_first_write)
    previous_handlers = {
        sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)
    }
    started = time.monotonic()
    try:
        with pytest.raises(OSError) as error:
            watchdog.run(
                [PY, "-c", _term_ignoring_child(pid_file)],
                stage="failure",
                report_path=report,
                stall_seconds=30,
                grace_seconds=0.15,
                poll_seconds=0.01,
            )
        assert error.value is expected
        assert children[0].poll() == -signal.SIGKILL
        assert shutdown_signals[:2] == [False, True]
        assert time.monotonic() - started >= 0.15
        assert time.monotonic() - started < 5
        if failure_point != "probe-and-final-report":
            payload = json.loads(report.read_text(encoding="utf-8"))
            assert payload["status"] == "failed"
            assert payload["exit_code"] == -signal.SIGKILL
            assert payload["error"]["type"] == "OSError"
        assert {
            sig: signal.getsignal(sig) for sig in previous_handlers
        } == previous_handlers
    finally:
        # Only the Popen-created group from this test may be terminated.
        if children and children[0].poll() is None:
            os.killpg(children[0].pid, signal.SIGKILL)
            children[0].wait(timeout=5)


@pytest.mark.skipif(os.name != "posix", reason="owned process groups require POSIX")
@pytest.mark.parametrize("cancel_signal", [signal.SIGTERM, signal.SIGINT])
@pytest.mark.parametrize(
    "signal_during_final_report", [False, True], ids=["single-signal", "second-signal"]
)
def test_cli_cancellation_escalates_and_records_original_signal(
    tmp_path, cancel_signal, signal_during_final_report
):
    pid_file = tmp_path / "owned.pid"
    report = tmp_path / "heartbeat.json"
    second_signal = (
        (signal.SIGINT if cancel_signal == signal.SIGTERM else signal.SIGTERM)
        if signal_during_final_report
        else None
    )
    supervisor = multiprocessing.get_context("spawn").Process(
        target=_invoke_watchdog_cli,
        args=(
            [
                "--stage",
                "cancel",
                "--report",
                str(report),
                "--stall-seconds",
                "30",
                "--grace-seconds",
                "0.15",
                "--poll-seconds",
                "0.01",
                "--",
                PY,
                "-c",
                _term_ignoring_child(pid_file),
            ],
            second_signal,
        ),
    )
    supervisor.start()
    child_pid = None
    try:
        child_pid = _wait_for_owned_child(pid_file)
        os.kill(supervisor.pid, cancel_signal)
        # QUALITY-O9 @egorribun: five-second cap catches unbounded shutdown;
        # the configured cleanup grace is only 0.15 seconds.
        supervisor.join(timeout=5)
        assert supervisor.exitcode == 128 + cancel_signal
        payload = json.loads(report.read_text(encoding="utf-8"))
        assert payload["status"] == "cancelled"
        assert payload["cancellation_signal"] == cancel_signal
        assert payload["exit_code"] == -signal.SIGKILL
        with pytest.raises(ProcessLookupError):
            os.kill(child_pid, 0)
    finally:
        if supervisor.is_alive():
            supervisor.kill()
            supervisor.join(timeout=5)
        if child_pid is not None:
            try:
                # This PID identifies only the ready child created above.
                os.killpg(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def _invoke_watchdog_cli(args: list[str], second_signal: int | None = None) -> None:
    if second_signal is not None:
        original_write = watchdog._write

        def signal_inside_final_report(path, payload):
            if payload["status"] == "cancelled":
                # Signal only this test-owned supervisor, never the pytest parent.
                os.kill(os.getpid(), second_signal)
            original_write(path, payload)

        watchdog._write = signal_inside_final_report
    raise SystemExit(watchdog.main(args))


@pytest.mark.parametrize("cancel_signal", [signal.SIGTERM, signal.SIGINT])
@pytest.mark.parametrize("failure_point", ["report", "clock", "cleanup", "restore"])
def test_cancellation_keeps_its_exit_code_after_secondary_failure(
    tmp_path, monkeypatch, capfd, cancel_signal, failure_point
):
    handlers = {sig: signal.SIG_DFL for sig in (signal.SIGTERM, signal.SIGINT)}
    previous_handlers = dict(handlers)
    cleanup_completed = []
    exceptions = {
        "report": OSError("sensitive secondary report text"),
        "clock": LookupError("sensitive secondary clock text"),
        "cleanup": RuntimeError("sensitive secondary cleanup text"),
        "restore": OSError("sensitive secondary restoration text"),
    }

    def register_handler(sig, handler):
        if (
            failure_point == "restore"
            and handler == signal.SIG_DFL
            and sig == signal.SIGTERM
        ):
            raise exceptions["restore"]
        previous = handlers[sig]
        handlers[sig] = handler
        return previous

    class OwnedChild:
        pid = 42
        stdout = BytesIO()
        stderr = BytesIO()
        returncode = None

        def poll(self):
            handlers[cancel_signal](cancel_signal, None)
            return self.returncode

    child = OwnedChild()

    def cleanup(process, **kwargs):
        assert process is child
        child.returncode = -9
        cleanup_completed.append(True)
        if failure_point == "cleanup":
            raise exceptions["cleanup"]

    original_write = watchdog._write

    def write_report(path, payload):
        if failure_point == "report":
            raise exceptions["report"]
        original_write(path, payload)

    clock_calls = 0

    def clock():
        nonlocal clock_calls
        clock_calls += 1
        if failure_point == "clock" and clock_calls > 1:
            raise exceptions["clock"]
        return 100.0

    monkeypatch.setattr(watchdog.signal, "signal", register_handler)
    monkeypatch.setattr(watchdog.signal, "getsignal", handlers.__getitem__)
    monkeypatch.setattr(watchdog.subprocess, "Popen", lambda *args, **kwargs: child)
    monkeypatch.setattr(watchdog, "_shutdown_group", cleanup)
    monkeypatch.setattr(watchdog, "_write", write_report)
    exit_code = watchdog.run(
        [PY, "-c", "pass"],
        stage="cancel",
        report_path=tmp_path / "r.json",
        stall_seconds=30,
        grace_seconds=1,
        poll_seconds=0.01,
        clock=clock,
    )

    assert exit_code == 128 + cancel_signal
    assert cleanup_completed == [True]
    diagnostic = capfd.readouterr().err
    assert type(exceptions[failure_point]).__name__ in diagnostic
    assert "sensitive secondary" not in diagnostic
    if failure_point != "restore":
        assert handlers == previous_handlers
    else:
        # A failed TERM restoration must not prevent attempting INT restoration.
        assert handlers[signal.SIGINT] == signal.SIG_DFL


def test_primary_probe_exception_survives_signal_restoration_failure(
    tmp_path, monkeypatch
):
    handlers = {sig: signal.SIG_DFL for sig in (signal.SIGTERM, signal.SIGINT)}
    primary = LookupError("original probe failure")

    class OwnedChild:
        pid = 42
        stdout = BytesIO()
        stderr = BytesIO()
        returncode = None

        def poll(self):
            return self.returncode

    child = OwnedChild()

    def cleanup(process, **kwargs):
        child.returncode = -9

    def register_handler(sig, handler):
        if handler == signal.SIG_DFL and sig == signal.SIGTERM:
            raise OSError("secondary restoration failure")
        previous = handlers[sig]
        handlers[sig] = handler
        return previous

    def fail_probe(*args, **kwargs):
        raise primary

    monkeypatch.setattr(watchdog.signal, "signal", register_handler)
    monkeypatch.setattr(watchdog.signal, "getsignal", handlers.__getitem__)
    monkeypatch.setattr(watchdog.subprocess, "Popen", lambda *args, **kwargs: child)
    monkeypatch.setattr(watchdog, "_shutdown_group", cleanup)
    monkeypatch.setattr(watchdog, "group_resources", fail_probe)
    with pytest.raises(LookupError) as error:
        watchdog.run(
            [PY, "-c", "pass"],
            stage="failure",
            report_path=tmp_path / "r.json",
            stall_seconds=30,
            grace_seconds=1,
            poll_seconds=0.01,
        )
    assert error.value is primary
    assert any("restoration" in note for note in primary.__notes__)
    assert handlers[signal.SIGINT] == signal.SIG_DFL
