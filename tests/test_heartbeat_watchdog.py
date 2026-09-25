"""Contracts for the O9 heartbeat watchdog."""

from __future__ import annotations

import json
import os
import sys
import time
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
        time.sleep(0.05)
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
