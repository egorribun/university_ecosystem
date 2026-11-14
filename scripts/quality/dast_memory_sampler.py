"""Record runner memory telemetry around the DAST ZAP scan (AUD-381).

Telemetry only: this module never changes scan coverage, rules, thresholds or
pass/fail semantics. It reads Linux ``/proc`` and writes JSON lines containing
process names, PIDs and resident sizes. It never records command lines,
environment values, targets or report contents.

Subcommands:

``sample``
    Append one JSON record every ``--interval-seconds`` until ``--stop-file``
    exists or ``--max-seconds`` elapses.

``summarize``
    Print the minimum MemAvailable, the peak VmRSS per process name, and the
    ``oom_kill`` counter delta between the first and last samples.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROC_ROOT = Path("/proc")
TOP_PROCESS_COUNT = 5
MEMINFO_KEYS = ("MemAvailable", "MemTotal", "SwapFree")


def parse_meminfo(text: str) -> dict[str, int]:
    """Return the selected /proc/meminfo values in kB."""

    values: dict[str, int] = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        if key not in MEMINFO_KEYS:
            continue
        fields = rest.split()
        if not fields or not fields[0].isdigit():
            continue
        values[key] = int(fields[0])
    return values


def parse_process_status(text: str) -> dict[str, Any] | None:
    """Return name and VmRSS (kB) from /proc/<pid>/status, or None.

    Kernel threads and exiting processes have no VmRSS line and are skipped.
    """

    name: str | None = None
    rss_kb: int | None = None
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        if key == "Name":
            name = rest.strip() or None
        elif key == "VmRSS":
            fields = rest.split()
            if fields and fields[0].isdigit():
                rss_kb = int(fields[0])
    if name is None or rss_kb is None:
        return None
    return {"name": name, "rss_kb": rss_kb}


def parse_oom_kill(text: str) -> int | None:
    """Return the oom_kill counter from /proc/vmstat text, or None."""

    for line in text.splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[0] == "oom_kill" and fields[1].isdigit():
            return int(fields[1])
    return None


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def top_processes(proc_root: Path = PROC_ROOT) -> list[dict[str, Any]]:
    """Return the largest processes by VmRSS, without command lines."""

    processes: list[dict[str, Any]] = []
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        text = _read(entry / "status")
        if text is None:
            continue
        parsed = parse_process_status(text)
        if parsed is None:
            continue
        processes.append({**parsed, "pid": int(entry.name)})
    processes.sort(key=lambda item: (-item["rss_kb"], item["pid"]))
    return processes[:TOP_PROCESS_COUNT]


def take_sample(proc_root: Path = PROC_ROOT) -> dict[str, Any]:
    """Collect one telemetry record from the host kernel interfaces."""

    meminfo = parse_meminfo(_read(proc_root / "meminfo") or "")
    vmstat = _read(proc_root / "vmstat")
    return {
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "mem_available_kb": meminfo.get("MemAvailable"),
        "mem_total_kb": meminfo.get("MemTotal"),
        "swap_free_kb": meminfo.get("SwapFree"),
        "oom_kill": parse_oom_kill(vmstat) if vmstat is not None else None,
        "top_processes": top_processes(proc_root),
    }


def sample(
    output: Path,
    stop_file: Path,
    interval_seconds: float,
    max_seconds: float,
) -> int:
    """Append samples until the stop file exists or the time budget elapses."""

    if interval_seconds <= 0 or max_seconds <= 0:
        print("interval and max duration must be positive", file=sys.stderr)
        return 2
    output.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + max_seconds
    with output.open("a", encoding="utf-8") as handle:
        while not stop_file.exists() and time.monotonic() < deadline:
            try:
                record = take_sample()
            except OSError as error:
                record = {
                    "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
                    "error": type(error).__name__,
                }
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            time.sleep(interval_seconds)
    return 0


def _load_records(path: Path) -> tuple[list[dict[str, Any]], bool]:
    records: list[dict[str, Any]] = []
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            # A killed sampler can leave its final write incomplete. Preserve
            # prior samples, but never silently skip corruption in complete lines.
            if index == len(lines) - 1 and not line.endswith("\n"):
                return records, True
            raise
        if isinstance(record, dict) and "error" not in record:
            records.append(record)
    return records, False


def summarize_records(records: list[dict[str, Any]]) -> str:
    """Render a plain-text summary of parsed telemetry records."""

    lines = [f"DAST runner memory telemetry: {len(records)} samples"]
    if not records:
        lines.append("No usable samples were recorded.")
        return "\n".join(lines) + "\n"

    available = [
        (record["mem_available_kb"], record["timestamp"])
        for record in records
        if isinstance(record.get("mem_available_kb"), int)
    ]
    if available:
        minimum, when = min(available)
        lines.append(f"Minimum MemAvailable: {minimum} kB at {when}")
    else:
        lines.append("Minimum MemAvailable: unavailable")

    peaks: dict[str, int] = defaultdict(int)
    for record in records:
        for process in record.get("top_processes", []):
            peaks[process["name"]] = max(peaks[process["name"]], process["rss_kb"])
    lines.append("Peak VmRSS per process (kB, top-5 samples):")
    for name, peak in sorted(peaks.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"  {name}: {peak}")

    counters = [
        record["oom_kill"]
        for record in records
        if isinstance(record.get("oom_kill"), int)
    ]
    if counters:
        lines.append(f"oom_kill delta (last - first): {counters[-1] - counters[0]}")
    else:
        lines.append("oom_kill delta: unavailable")
    return "\n".join(lines) + "\n"


def summarize(path: Path) -> str:
    records, incomplete = _load_records(path)
    summary = summarize_records(records)
    if incomplete:
        summary += "Ignored incomplete trailing sample.\n"
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)

    sample_parser = commands.add_parser("sample", help="append telemetry samples")
    sample_parser.add_argument("--output", type=Path, required=True)
    sample_parser.add_argument("--stop-file", type=Path, required=True)
    sample_parser.add_argument("--interval-seconds", type=float, default=5.0)
    sample_parser.add_argument("--max-seconds", type=float, default=7200.0)

    summarize_parser = commands.add_parser("summarize", help="print a summary")
    summarize_parser.add_argument("input", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "sample":
        return sample(
            args.output,
            args.stop_file,
            args.interval_seconds,
            args.max_seconds,
        )
    sys.stdout.write(summarize(args.input))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
