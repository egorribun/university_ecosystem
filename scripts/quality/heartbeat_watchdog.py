"""Heartbeat watchdog for long CI stages (organizational task O9).

Runs a command in its own process group and records a JSON heartbeat while it
runs. Progress is any of: new output on stdout/stderr, a touched heartbeat
file, or growing CPU time of the process group. A stage is *stalled* only when
none of them advanced for ``--stall-seconds``, so a long but busy compilation
is not mistaken for a hang. A stalled stage receives SIGTERM, then SIGKILL
after ``--grace-seconds``; the watchdog exits 124 and keeps every partial
report. Children left behind by a finished command are reaped as orphans.

Resource counters (RSS, CPU) come from ``/proc`` and are reported as ``null``
where that is unavailable, never as zero.

Usage::

    python scripts/quality/heartbeat_watchdog.py --stage stryker-shard-3 \\
        --report artifacts/quality/heartbeat.json --stall-seconds 900 -- \\
        npm run test:mutation
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

STALLED_EXIT_CODE = 124


@dataclass(frozen=True)
class Probe:
    """One observation of the monitored process group."""

    output_events: int
    heartbeat_mtime: float | None
    cpu_seconds: float | None
    rss_bytes: int | None


@dataclass
class Monitor:
    """Pure stall detection; the clock and probes are injected by the runner."""

    stage: str
    stall_seconds: float
    grace_seconds: float
    started_at: float
    last_progress_at: float = field(init=False)
    last_probe: Probe | None = None
    status: str = "running"
    terminated_at: float | None = None

    def __post_init__(self) -> None:
        self.last_progress_at = self.started_at

    def observe(self, probe: Probe, now: float) -> str:
        """Record ``probe`` and return the action: ``wait``, ``term`` or ``kill``."""

        previous = self.last_probe
        self.last_probe = probe
        if previous is None or _advanced(previous, probe):
            self.last_progress_at = now
        if self.status == "running":
            if now - self.last_progress_at >= self.stall_seconds:
                self.status = "stalled"
                self.terminated_at = now
                return "term"
            return "wait"
        if self.terminated_at is not None and (
            now - self.terminated_at >= self.grace_seconds
        ):
            return "kill"
        return "wait"

    def report(
        self, now: float, *, pid: int, exit_code: int | None
    ) -> dict[str, object]:
        probe = self.last_probe
        return {
            "stage": self.stage,
            "status": self.status,
            "pid": pid,
            "started_at": self.started_at,
            "last_progress_at": self.last_progress_at,
            "silent_seconds": round(now - self.last_progress_at, 3),
            "exit_code": exit_code,
            "probe": None if probe is None else asdict(probe),
        }


def _advanced(previous: Probe, current: Probe) -> bool:
    if current.output_events != previous.output_events:
        return True
    if current.heartbeat_mtime != previous.heartbeat_mtime:
        return True
    return (
        current.cpu_seconds is not None
        and previous.cpu_seconds is not None
        and current.cpu_seconds > previous.cpu_seconds
    )


def group_resources(
    pgid: int, proc_root: Path = Path("/proc")
) -> tuple[float | None, int | None]:
    """Sum CPU seconds and RSS of every process in ``pgid`` (Linux ``/proc``)."""

    if not proc_root.is_dir():
        return None, None
    ticks = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
    page = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096
    cpu_ticks = 0
    rss_pages = 0
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / "stat").read_text(encoding="utf-8")
        except OSError:
            continue  # The process exited while it was being read.
        fields = stat.rsplit(")", 1)[1].split()
        # After the command name: state=0, ppid=1, pgrp=2, utime=11, stime=12, rss=21.
        if int(fields[2]) != pgid:
            continue
        cpu_ticks += int(fields[11]) + int(fields[12])
        rss_pages += int(fields[21])
    return cpu_ticks / ticks, rss_pages * page


class _OutputCounter:
    """Forwards a stream line by line and counts lines as progress events."""

    def __init__(self) -> None:
        self.events = 0
        self._lock = threading.Lock()

    def pump(self, source: object, sink: object) -> None:
        for line in iter(source.readline, b""):  # type: ignore[attr-defined]
            sink.write(line)  # type: ignore[attr-defined]
            sink.flush()  # type: ignore[attr-defined]
            with self._lock:
                self.events += 1


def _signal_group(process: subprocess.Popen[bytes], *, force: bool) -> None:
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL if force else signal.SIGTERM)
        except ProcessLookupError:
            pass
    elif force:
        process.kill()
    else:
        process.terminate()


def _write(report_path: Path, report: dict[str, object]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = report_path.with_suffix(report_path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
    temporary.replace(report_path)


def run(
    command: Sequence[str],
    *,
    stage: str,
    report_path: Path,
    stall_seconds: float,
    grace_seconds: float,
    poll_seconds: float,
    heartbeat_file: Path | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> int:
    process = subprocess.Popen(  # noqa: S603 - argv comes from the CI step, no shell.
        list(command),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=os.name == "posix",
    )
    counter = _OutputCounter()
    pumps = [
        threading.Thread(
            target=counter.pump, args=(process.stdout, sys.stdout.buffer), daemon=True
        ),
        threading.Thread(
            target=counter.pump, args=(process.stderr, sys.stderr.buffer), daemon=True
        ),
    ]
    for pump in pumps:
        pump.start()
    monitor = Monitor(stage, stall_seconds, grace_seconds, started_at=clock())

    def probe() -> Probe:
        mtime = None
        if heartbeat_file is not None and heartbeat_file.exists():
            mtime = heartbeat_file.stat().st_mtime
        cpu, rss = group_resources(process.pid)
        return Probe(counter.events, mtime, cpu, rss)

    while process.poll() is None:
        now = clock()
        action = monitor.observe(probe(), now)
        _write(report_path, monitor.report(now, pid=process.pid, exit_code=None))
        if action != "wait":
            _signal_group(process, force=action == "kill")
        time.sleep(poll_seconds)
    exit_code = process.returncode
    # Anything still in the group outlived its parent: reap it.
    _signal_group(process, force=True)
    for pump in pumps:
        pump.join(timeout=poll_seconds)
    now = clock()
    if monitor.status == "running":
        monitor.status = "exited"
    _write(report_path, monitor.report(now, pid=process.pid, exit_code=exit_code))
    return STALLED_EXIT_CODE if monitor.status == "stalled" else exit_code


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--stall-seconds", required=True, type=float)
    parser.add_argument("--grace-seconds", default=30.0, type=float)
    parser.add_argument("--poll-seconds", default=5.0, type=float)
    parser.add_argument("--heartbeat-file", type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command is required after --")
    return run(
        command,
        stage=args.stage,
        report_path=args.report,
        stall_seconds=args.stall_seconds,
        grace_seconds=args.grace_seconds,
        poll_seconds=args.poll_seconds,
        heartbeat_file=args.heartbeat_file,
    )


if __name__ == "__main__":
    raise SystemExit(main())
