#!/usr/bin/env python3
"""Normalize AUD-346 failure observations; never publish raw input or errors.

The shell owns bounded, read-only probes. This helper performs no network calls
and writes only closed-schema JSON to stdout, retained by the existing job log.
A target/fault snapshot is not proof of restoration or UID-bound fault deletion.
A live port-forward supervisor is not proof of a healthy forwarding child.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import re
import stat
import sys
from pathlib import Path

MAX_BYTES = 65536
SCHEMA = "university-ecosystem/aud346-failure-diagnostic/v1"


def _document(raw: bytes) -> dict:
    if len(raw) > MAX_BYTES:
        return {}
    try:
        value = json.loads(raw)
    except (ValueError, RecursionError):
        return {}
    return value if isinstance(value, dict) else {}


def _boolean(value: object) -> bool | None:
    return value if type(value) is bool else None


def target_snapshot(raw: bytes) -> dict:
    """Accept one fixed fixture target in the run-owned cluster, not other pods."""
    unavailable = {"observation": "unavailable"}
    items = _document(raw).get("items")
    if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
        return unavailable
    pod = items[0]
    metadata, status = pod.get("metadata"), pod.get("status")
    if not isinstance(metadata, dict) or not isinstance(status, dict):
        return unavailable
    name, labels = metadata.get("name"), metadata.get("labels")
    if (
        metadata.get("namespace") != "aud346"
        or not isinstance(name, str)
        or re.fullmatch(r"aud346-chaos-target-[a-z0-9]{1,16}-[a-z0-9]{1,8}", name)
        is None
        or not isinstance(labels, dict)
        or labels.get("app.kubernetes.io/name") != "aud346-chaos-target"
    ):
        return unavailable
    conditions = status.get("conditions")
    ready = (
        [
            item.get("status")
            for item in conditions
            if isinstance(item, dict) and item.get("type") == "Ready"
        ]
        if isinstance(conditions, list)
        else []
    )
    containers = status.get("containerStatuses")
    matches = (
        [
            item
            for item in containers
            if isinstance(item, dict) and item.get("name") == "http"
        ]
        if isinstance(containers, list)
        else []
    )
    container = matches[0] if len(matches) == 1 else {}
    state = container.get("state")
    states = list(state) if isinstance(state, dict) else []
    count = container.get("restartCount")
    phase = status.get("phase")
    return {
        "observation": "matched",
        "phase": phase
        if phase in ("Pending", "Running", "Succeeded", "Failed", "Unknown")
        else "unknown",
        "ready": {"True": True, "False": False}.get(ready[0])
        if len(ready) == 1 and isinstance(ready[0], str)
        else None,
        "container_ready": _boolean(container.get("ready")),
        "container_state": states[0]
        if len(states) == 1
        and states[0] in ("running", "waiting", "terminated")
        and isinstance(state[states[0]], dict)
        else "unknown",
        "restart_count": count
        if type(count) is int and 0 <= count <= 1000000
        else None,
    }


def fault_snapshot(raw: bytes) -> dict:
    """Absence is only a fresh snapshot; do not assert UID deletion/restoration."""
    if not raw:
        return {"observation": "absent_at_snapshot"}
    document = _document(raw)
    metadata = document.get("metadata")
    if (
        document.get("kind") == "PodChaos"
        and isinstance(metadata, dict)
        and metadata.get("namespace") == "aud346"
        and metadata.get("name") == "aud346-live-pod-failure"
    ):
        return {"observation": "present_at_snapshot"}
    return {"observation": "unavailable"}


def _private_log_tail(directory: Path) -> tuple[bytes, bool]:
    """Open relative to a private directory descriptor; reject links/special files."""
    if directory.resolve(strict=True) != directory.absolute():
        raise ValueError("noncanonical directory")
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(directory_fd)
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("nonprivate directory")
        descriptor = os.open(
            "port-forward.log",
            os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW,
            dir_fd=directory_fd,
        )
        try:
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_mode & 0o077
                or info.st_nlink != 1
            ):
                raise ValueError("nonprivate regular file")
            truncated = info.st_size > MAX_BYTES
            os.lseek(descriptor, max(0, info.st_size - MAX_BYTES), os.SEEK_SET)
            data = os.read(descriptor, MAX_BYTES)
            if truncated:
                # Do not count a partial first line as a complete restart marker.
                data = data.partition(b"\n")[2]
            return data, truncated
        finally:
            os.close(descriptor)
    finally:
        os.close(directory_fd)


def transport_snapshot(directory: Path, supervisor: str) -> dict:
    result = {
        "supervisor": supervisor
        if supervisor in ("alive", "not_running", "not_started")
        else "unknown",
        "log": "unavailable",
        "tail_truncated": None,
        "restarts_in_tail": None,
        "connection_refused_in_tail": None,
        "lost_connection_in_tail": None,
        "forwarding_in_tail": None,
    }
    try:
        data, truncated = _private_log_tail(directory)
    except (OSError, ValueError, RuntimeError):
        return result
    lower = data.lower()
    result.update(
        log="read",
        tail_truncated=truncated,
        restarts_in_tail=data.splitlines().count(b"port-forward exited; restarting"),
        connection_refused_in_tail=b"connection refused" in lower,
        lost_connection_in_tail=b"lost connection to pod" in lower,
        forwarding_in_tail=b"forwarding from" in lower,
    )
    return result


def _binding(name: str, pattern: str) -> str | None:
    value = os.environ.get(name, "")
    return value if re.fullmatch(pattern, value) else None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("transport", "target", "fault"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--exit-status", type=int, required=True)
    parser.add_argument(
        "--phase", choices=("proof", "post_proof_health"), required=True
    )
    parser.add_argument(
        "--input-status", choices=("ok", "unavailable"), default="unavailable"
    )
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--supervisor", default="unknown")
    args = parser.parse_args(argv)
    if (
        not re.fullmatch(r"[0-9a-f]{12}", args.run_id)
        or not 1 <= args.exit_status <= 255
    ):
        raise ValueError("invalid binding")
    if args.kind == "transport":
        observation = (
            transport_snapshot(args.directory, args.supervisor)
            if args.directory is not None
            else {"log": "unavailable"}
        )
    elif args.input_status != "ok":
        observation = {"observation": "unavailable"}
    else:
        encoded = sys.stdin.buffer.read(4 * ((MAX_BYTES + 2) // 3) + 1)
        try:
            raw = base64.b64decode(encoded, validate=True)
        except binascii.Error:
            raw = b"invalid"
        observation = (
            target_snapshot(raw) if args.kind == "target" else fault_snapshot(raw)
        )
    record = {
        "schema": SCHEMA,
        "kind": args.kind,
        "run_id": args.run_id,
        # Environment claims are named explicitly, not checkout attestations.
        "github_sha": _binding("GITHUB_SHA", r"[0-9a-f]{40}"),
        "github_run_id": _binding("GITHUB_RUN_ID", r"[1-9][0-9]{0,19}"),
        "github_run_attempt": _binding("GITHUB_RUN_ATTEMPT", r"[1-9][0-9]{0,5}"),
        "harness_exit_status": args.exit_status,
        "failure_phase": args.phase,
        "observation": observation,
    }
    print(
        "AUD346_FAILURE_DIAGNOSTIC "
        + json.dumps(record, sort_keys=True, separators=(",", ":"))
    )


if __name__ == "__main__":
    main()
