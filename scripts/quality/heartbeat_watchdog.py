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
import math
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


def _positive_seconds(value: str | float) -> float:
    seconds = float(value)
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("timing values must be finite and positive")
    return seconds


def _group_running(process: subprocess.Popen[bytes]) -> bool:
    # Reap the direct child before checking the group: its zombie must not
    # keep an otherwise-empty group alive throughout the shutdown grace.
    direct_running = process.poll() is None
    if os.name != "posix":
        return direct_running
    try:
        os.killpg(process.pid, 0)
    except ProcessLookupError:
        return False
    return True


def _shutdown_group(
    process: subprocess.Popen[bytes], *, grace_seconds: float, poll_seconds: float
) -> None:
    """Allow graceful shutdown, then bound the lifetime of the owned group."""
    _signal_group(process, force=False)
    # Cleanup uses the real monotonic clock, independent of an injected
    # monitor clock or failed resource probe.
    deadline = time.monotonic() + grace_seconds
    while _group_running(process):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _signal_group(process, force=True)
            break
        time.sleep(min(poll_seconds, remaining))
    process.wait(timeout=grace_seconds)


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
    stall_seconds = _positive_seconds(stall_seconds)
    grace_seconds = _positive_seconds(grace_seconds)
    poll_seconds = _positive_seconds(poll_seconds)
    monitor = Monitor(stage, stall_seconds, grace_seconds, started_at=clock())
    process: subprocess.Popen[bytes] | None = None
    pumps: list[threading.Thread] = []
    cancellation_signal: int | None = None
    previous_handlers: dict[int, int | Callable[..., object] | None] = {}
    failure: BaseException | None = None
    secondary_errors: list[dict[str, str]] = []

    def record_failure(exc: BaseException, phase: str) -> None:
        nonlocal failure
        if failure is None and cancellation_signal is None:
            failure = exc
            monitor.status = "failed"
            return
        if monitor.status == "running" and cancellation_signal is not None:
            monitor.status = "cancelled"
        message = f"Watchdog {phase} also failed: {type(exc).__name__}"
        if failure is not None:
            failure.add_note(message)
        secondary_errors.append({"phase": phase, "type": type(exc).__name__})
        try:
            # Diagnostic text must not disclose exception messages, which can
            # contain paths, credentials, or application data.
            sys.stderr.write(message + "\n")
            sys.stderr.flush()
        except BaseException as diagnostic_error:  # RZ-22-01-JUSTIFIED: failed diagnostics cannot replace the first failure/cancellation.
            secondary_errors.append(
                {"phase": "diagnostic", "type": type(diagnostic_error).__name__}
            )
            if failure is not None:
                failure.add_note(
                    f"Watchdog diagnostic also failed: {type(diagnostic_error).__name__}"
                )

    def cancel(signum: int, _frame: object) -> None:
        nonlocal cancellation_signal
        # A later signal must not replace the first cancellation reason or
        # interrupt bounded TERM-to-KILL cleanup.
        if cancellation_signal is None:
            cancellation_signal = signum

    try:
        try:
            if threading.current_thread() is threading.main_thread():
                for sig in (signal.SIGTERM, signal.SIGINT):
                    previous_handlers[sig] = signal.getsignal(sig)
                    signal.signal(sig, cancel)
            process = subprocess.Popen(  # noqa: S603 - argv comes from the CI step, no shell.
                list(command),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=os.name == "posix",
            )
            counter = _OutputCounter()
            for source, sink in (
                (process.stdout, sys.stdout.buffer),
                (process.stderr, sys.stderr.buffer),
            ):
                pump = threading.Thread(
                    target=counter.pump, args=(source, sink), daemon=True
                )
                pump.start()
                pumps.append(pump)

            while process.poll() is None:
                if cancellation_signal is not None:
                    monitor.status = "cancelled"
                    break
                now = clock()
                mtime = None
                if heartbeat_file is not None and heartbeat_file.exists():
                    mtime = heartbeat_file.stat().st_mtime
                cpu, rss = group_resources(process.pid)
                action = monitor.observe(Probe(counter.events, mtime, cpu, rss), now)
                _write(
                    report_path, monitor.report(now, pid=process.pid, exit_code=None)
                )
                if action != "wait":
                    break
                time.sleep(poll_seconds)
        except BaseException as exc:  # RZ-22-01-JUSTIFIED: preserve original failure after owned process cleanup.
            record_failure(exc, "monitor")
        finally:
            if process is not None:
                try:
                    if monitor.status in {"failed", "cancelled", "stalled"}:
                        _shutdown_group(
                            process,
                            grace_seconds=grace_seconds,
                            poll_seconds=poll_seconds,
                        )
                    else:
                        # Anything still in the group outlived its finished parent.
                        _signal_group(process, force=True)
                    for pump in pumps:
                        pump.join(timeout=poll_seconds)
                except BaseException as exc:  # RZ-22-01-JUSTIFIED: cleanup failures must not replace the first failure.
                    record_failure(exc, "cleanup")

        if process is not None:
            if monitor.status == "running":
                monitor.status = (
                    "cancelled" if cancellation_signal is not None else "exited"
                )
            try:
                report = monitor.report(
                    clock(), pid=process.pid, exit_code=process.returncode
                )
                if failure is not None:
                    report["error"] = {"type": type(failure).__name__}
                if cancellation_signal is not None:
                    report["cancellation_signal"] = cancellation_signal
                if secondary_errors:
                    report["secondary_errors"] = list(secondary_errors)
                _write(report_path, report)
            except BaseException as exc:  # RZ-22-01-JUSTIFIED: retain primary exception when final reporting also fails.
                record_failure(exc, "final report")
    finally:
        # Keep cancellation handlers active through the final report attempt.
        # Restoration is last and cannot mask the first failure/cancellation.
        for original_signal, handler in previous_handlers.items():
            try:
                signal.signal(original_signal, handler)
            except BaseException as exc:  # RZ-22-01-JUSTIFIED: restoration cannot replace a primary failure/cancellation or prevent other handlers being restored.
                record_failure(exc, "signal restoration")

    if failure is not None:
        raise failure
    if cancellation_signal is not None:
        return 128 + cancellation_signal
    if monitor.status == "stalled":
        return STALLED_EXIT_CODE
    if process is None or process.returncode is None:
        raise RuntimeError("Watchdog child did not reach a terminal state")
    return process.returncode


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--stall-seconds", required=True, type=_positive_seconds)
    parser.add_argument("--grace-seconds", default=30.0, type=_positive_seconds)
    parser.add_argument("--poll-seconds", default=5.0, type=_positive_seconds)
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
