"""Record runner memory telemetry around the DAST ZAP scan (AUD-381).

Telemetry only: this module never changes scan coverage, rules, thresholds or
pass/fail semantics. It records host memory and, when identifiable, sampled
numeric cgroup memory counters for the owned container. It never records
command lines, environment values, targets or report contents.

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
import asyncio
import json
import os
import re
import shutil
import stat
import sys
import time
from collections import defaultdict
from collections.abc import Mapping
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROC_ROOT = Path("/proc")
TOP_PROCESS_COUNT = 5
MEMINFO_KEYS = ("MemAvailable", "MemTotal", "SwapFree")
CONTAINER_SAMPLE_EVERY = 3
DOCKER_SOCKET = "/var/run/docker.sock"
DOCKER_TIMEOUT_SECONDS = 1.0
_MAX_CONTEXT_BYTES = 8192
_MAX_COUNTER_BYTES = 65536
_IDENTITY_PATTERNS = {
    "source_sha": r"[0-9a-f]{40}",
    "run_id": r"[1-9][0-9]*",
    "run_attempt": r"[1-9][0-9]*",
    "image": r"ghcr\.io/zaproxy/zaproxy@sha256:[0-9a-f]{64}",
    "rules_sha256": r"[0-9a-f]{64}",
    "hook_sha256": r"[0-9a-f]{64}",
}


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate context key")
        result[key] = value
    return result


def _context_nonce(payload: bytes, env: Mapping[str, str]) -> str | None:
    """Extract only a validated nonce from the current run's private context."""
    try:
        value = json.loads(payload, object_pairs_hook=_unique_pairs)
        if not isinstance(value, dict) or set(value) != {
            "schema_version",
            "identity",
            "run_nonce",
            "started_ns",
        }:
            return None
        identity = value["identity"]
        if not isinstance(identity, dict) or set(identity) != set(_IDENTITY_PATTERNS):
            return None
        if any(
            type(identity[key]) is not str
            or re.fullmatch(pattern, identity[key]) is None
            for key, pattern in _IDENTITY_PATTERNS.items()
        ):
            return None
        if any(
            identity[key] != env.get(variable)
            for key, variable in (
                ("source_sha", "GITHUB_SHA"),
                ("run_id", "GITHUB_RUN_ID"),
                ("run_attempt", "GITHUB_RUN_ATTEMPT"),
            )
        ):
            return None
        nonce = value["run_nonce"]
        if (
            type(value["schema_version"]) is not int
            or value["schema_version"] != 1
            or type(value["started_ns"]) is not int
            or value["started_ns"] <= 0
            or type(nonce) is not str
            or re.fullmatch(r"[0-9a-f]{32}", nonce) is None
        ):
            return None
        return nonce
    except (ValueError, UnicodeError, TypeError):
        return None


def _read_private_context(temp_root: Path) -> bytes | None:
    """Read a bounded owner-only regular file without following symlinks."""
    if os.name != "posix" or not temp_root.is_absolute() or ".." in temp_root.parts:
        return None
    try:
        if temp_root.resolve(strict=True) != temp_root:
            return None
        with ExitStack() as stack:
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            root = os.open(temp_root, flags)
            stack.callback(os.close, root)
            work = os.open("zap-private", flags, dir_fd=root)
            stack.callback(os.close, work)
            info = os.fstat(work)
            if info.st_uid != os.getuid() or info.st_mode & 0o077:
                return None
            descriptor = os.open(
                "context.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=work
            )
            stack.callback(os.close, descriptor)
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_mode & 0o077
                or info.st_nlink != 1
                or not 0 < info.st_size <= _MAX_CONTEXT_BYTES
            ):
                return None
            payload = os.read(descriptor, _MAX_CONTEXT_BYTES + 1)
            return payload if len(payload) <= _MAX_CONTEXT_BYTES else None
    except OSError:
        return None


async def _inspect_owned_container(docker: str, name: str) -> tuple[str, int] | None:
    """Run one fixed local-only Docker inspection with bounded output and time."""
    process = None
    try:
        async with asyncio.timeout(DOCKER_TIMEOUT_SECONDS):
            process = await asyncio.create_subprocess_exec(
                docker,
                "--host",
                f"unix://{DOCKER_SOCKET}",
                "inspect",
                "--type",
                "container",
                "--format",
                "{{.Id}} {{.State.Pid}} {{.State.Running}}",
                name,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env={"DOCKER_CONFIG": "/dev/null"},
            )
            if process.stdout is None:
                return None
            payload = b""
            while len(payload) <= 256:
                part = await process.stdout.read(257 - len(payload))
                if not part:
                    break
                payload += part
            if len(payload) > 256 or await process.wait() != 0:
                return None
        match = re.fullmatch(rb"([0-9a-f]{64}) ([1-9][0-9]{0,9}) true\s*", payload)
        if match is None:
            return None
        return match.group(1).decode("ascii"), int(match.group(2))
    except (OSError, TimeoutError):
        return None
    finally:
        if process is not None and process.returncode is None:
            try:
                process.kill()
                await asyncio.wait_for(process.wait(), timeout=0.2)
            except (OSError, TimeoutError):
                pass


def _read_bounded(path: Path, limit: int = _MAX_COUNTER_BYTES) -> bytes | None:
    try:
        with path.open("rb") as handle:
            value = handle.read(limit + 1)
        return value if len(value) <= limit else None
    except OSError:
        return None


def _counter(value: bytes | None) -> int | None:
    if value is None or re.fullmatch(rb"[0-9]{1,20}\s*", value) is None:
        return None
    number = int(value)
    return number if number <= 2**64 - 1 else None


def _process_start_time(payload: bytes | None, pid: int) -> int | None:
    if payload is None or not payload.startswith(f"{pid} (".encode()):
        return None
    fields = payload.rpartition(b") ")[2].split()
    return _counter(fields[19]) if len(fields) > 19 else None


def _container_cgroup_sample(
    proc_root: Path, cgroup_root: Path, pid: int, container_id: str
) -> dict[str, Any]:
    """Read numeric cgroup-v2 counters only for the inspected container's PID."""
    unavailable = {"status": "unavailable"}
    process = proc_root / str(pid)
    initial_start = _process_start_time(_read_bounded(process / "stat"), pid)
    membership = _read_bounded(process / "cgroup")
    if initial_start is None or membership is None:
        return unavailable
    lines = [line[3:] for line in membership.splitlines() if line.startswith(b"0::")]
    if not lines:
        return {"status": "unsupported"}
    if len(lines) != 1:
        return unavailable
    try:
        path = lines[0].decode("ascii")
        parts = path.split("/")[1:]
        if (
            not path.startswith("/")
            or not parts
            or any(re.fullmatch(r"[A-Za-z0-9_.:-]+", part) is None for part in parts)
            or any(part in {".", ".."} for part in parts)
            or parts[-1] not in {container_id, f"docker-{container_id}.scope"}
        ):
            return unavailable
        group = cgroup_root.joinpath(*parts)
        if group.resolve(strict=True) != group.absolute():
            return unavailable
        procs = _read_bounded(group / "cgroup.procs")
        if procs is None or str(pid).encode() not in procs.splitlines():
            return unavailable
        current = _counter(_read_bounded(group / "memory.current"))
        peak = _counter(_read_bounded(group / "memory.peak"))
        limit_raw = _read_bounded(group / "memory.max")
        limit = _counter(limit_raw)
        limit_state = (
            "value"
            if limit is not None
            else "unlimited"
            if limit_raw is not None and limit_raw.strip() == b"max"
            else "unavailable"
        )
        events: dict[bytes, int | None] = {}
        events_raw = _read_bounded(group / "memory.events")
        for line in (events_raw or b"").splitlines():
            fields = line.split()
            if len(fields) == 2 and fields[0] in {b"oom", b"oom_kill"}:
                key = fields[0]
                events[key] = _counter(fields[1]) if key not in events else None
        if (
            _process_start_time(_read_bounded(process / "stat"), pid) != initial_start
            or _read_bounded(process / "cgroup") != membership
            or str(pid).encode()
            not in (_read_bounded(group / "cgroup.procs") or b"").splitlines()
        ):
            return unavailable
        if (
            current is None
            and peak is None
            and limit_state == "unavailable"
            and events.get(b"oom") is None
            and events.get(b"oom_kill") is None
        ):
            return unavailable
        return {
            "status": "sampled",
            "current_bytes": current,
            "peak_bytes": peak,
            "limit_bytes": limit,
            "limit_state": limit_state,
            "oom_events": events.get(b"oom"),
            "oom_kill_events": events.get(b"oom_kill"),
        }
    except (OSError, UnicodeError, ValueError):
        return unavailable


class _ContainerObserver:
    def __init__(self, env: Mapping[str, str]) -> None:
        self.env = env
        self.nonce: str | None = None
        self.container_id: str | None = None

    def observe(self) -> dict[str, Any]:
        """Observe one owned container or return a fixed unavailable state."""
        try:
            temp = self.env.get("RUNNER_TEMP")
            payload = _read_private_context(Path(temp)) if temp else None
            nonce = _context_nonce(payload, self.env) if payload is not None else None
            if nonce is None or (self.nonce is not None and nonce != self.nonce):
                return {"status": "unavailable"}
            self.nonce = nonce
            docker = shutil.which("docker")
            if (
                docker is None
                or not Path(docker).is_absolute()
                or not Path(DOCKER_SOCKET).is_socket()
            ):
                return {"status": "unavailable"}
            result = asyncio.run(_inspect_owned_container(docker, f"zap-{nonce}"))
            if result is None:
                return {"status": "unavailable"}
            container_id, pid = result
            if self.container_id is not None and container_id != self.container_id:
                return {"status": "unavailable"}
            self.container_id = container_id
            return _container_cgroup_sample(
                PROC_ROOT, Path("/sys/fs/cgroup"), pid, container_id
            )
        except Exception:
            # Observation failures must not affect the DAST job or disclose details.
            return {"status": "unavailable"}


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
    observer = _ContainerObserver(os.environ)
    sample_index = 0
    with output.open("a", encoding="utf-8") as handle:
        while not stop_file.exists() and time.monotonic() < deadline:
            try:
                record = take_sample()
            except OSError as error:
                record = {
                    "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
                    "error": type(error).__name__,
                }
            if "error" not in record and sample_index % CONTAINER_SAMPLE_EVERY == 0:
                record["container_memory"] = observer.observe()
            sample_index += 1
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

    observations = [
        record["container_memory"]
        for record in records
        if isinstance(record.get("container_memory"), dict)
    ]
    if observations:
        sampled = [item for item in observations if item.get("status") == "sampled"]
        lines.append(f"Container cgroup: {len(sampled)} sampled observation(s)")
        for key, label, suffix in (
            ("current_bytes", "current", " bytes"),
            ("peak_bytes", "peak", " bytes"),
            ("oom_events", "oom", ""),
            ("oom_kill_events", "oom_kill", ""),
        ):
            values = [item[key] for item in sampled if type(item.get(key)) is int]
            value = f"{max(values)}{suffix}" if values else "unavailable"
            lines.append(f"  maximum observed {label}: {value}")
        lines.append("  Sampling does not cover events after the last observation.")
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
