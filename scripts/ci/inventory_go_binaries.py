"""Inventory the Go modules in Caddy and the file-processor health probe.

The command builds from an immutable Git commit, copies the final image binaries
from stopped containers, and reads their embedded Go build information without
executing either binary. It does not scan vulnerabilities, prove reachability,
or establish that a separately published image has the same contents. Builds are
supported on Windows only; POSIX lifecycle containment remains unverified. A
failed or interrupted Docker build can leave daemon-side work unresolved.

Example (Docker builds require an allocated resource slot):
    python scripts/ci/inventory_go_binaries.py --revision FULL_COMMIT_SHA \
        --work-dir /private/new-directory --output /private/inventory.json
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, BinaryIO

ROOT = Path(__file__).resolve().parents[2]
COMMIT = re.compile(r"[0-9a-f]{40}")
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")
CONTAINER_ID = re.compile(r"[0-9a-f]{64}")
_IS_WINDOWS = os.name == "nt"


class InventoryError(ValueError):
    """Evidence is incomplete or inconsistent; no inventory may be claimed."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


_LOADED_PRODUCER_SHA256 = _sha256(Path(__file__))


def _check_producer_identity() -> None:
    if _sha256(Path(__file__)) != _LOADED_PRODUCER_SHA256:
        raise InventoryError("Inventory producer source changed during execution")


def _module(fields: list[str]) -> dict[str, Any]:
    if len(fields) not in (2, 3) or not all(fields):
        raise InventoryError("Malformed Go module metadata")
    return {
        "path": fields[0],
        "version": fields[1],
        "sum": fields[2] if len(fields) == 3 else None,
        "replacement": None,
    }


def _setup_windows_job(name: str) -> int:
    """Create a named job whose handle is owned only by this producer."""
    import ctypes
    from ctypes import wintypes

    class BasicLimits(ctypes.Structure):
        _fields_ = [
            ("process_time", ctypes.c_longlong),
            ("job_time", ctypes.c_longlong),
            ("flags", wintypes.DWORD),
            ("minimum_working_set", ctypes.c_size_t),
            ("maximum_working_set", ctypes.c_size_t),
            ("active_process_limit", wintypes.DWORD),
            ("affinity", ctypes.c_size_t),
            ("priority_class", wintypes.DWORD),
            ("scheduling_class", wintypes.DWORD),
        ]

    class IoCounters(ctypes.Structure):
        _fields_ = [
            (name, ctypes.c_ulonglong)
            for name in (
                "read_operations",
                "write_operations",
                "other_operations",
                "read_bytes",
                "write_bytes",
                "other_bytes",
            )
        ]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("basic", BasicLimits),
            ("io", IoCounters),
            ("process_memory_limit", ctypes.c_size_t),
            ("job_memory_limit", ctypes.c_size_t),
            ("peak_process_memory", ctypes.c_size_t),
            ("peak_job_memory", ctypes.c_size_t),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    )
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    ctypes.set_last_error(0)
    job = kernel.CreateJobObjectW(None, name)
    if not job:
        raise OSError("Cannot create process job")
    if ctypes.get_last_error() == 183:
        _close_windows_job(job)
        raise OSError("Process job name already exists")
    limits = ExtendedLimits()
    limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel.SetInformationJobObject(
        job, 9, ctypes.byref(limits), ctypes.sizeof(limits)
    ):
        _close_windows_job(job)
        raise OSError("Cannot configure process job")
    return job


def _assign_windows_job(job: int, process: asyncio.subprocess.Process) -> None:
    import ctypes
    from ctypes import wintypes

    native = process._transport.get_extra_info("subprocess")
    if native is None or not hasattr(native, "_handle"):
        raise OSError("Cannot obtain supervisor process handle")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    if not kernel.AssignProcessToJobObject(job, int(native._handle)):
        raise OSError("Cannot assign supervisor to process job")


def _close_windows_job(job: int) -> None:
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    if not kernel.CloseHandle(job):
        raise OSError("Cannot close owned process job")


def _wait_for_windows_job(name: str) -> None:
    """Do not start the target until its supervisor belongs to the producer's job."""
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenJobObjectW.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR)
    kernel.OpenJobObjectW.restype = wintypes.HANDLE
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.IsProcessInJob.argtypes = (
        wintypes.HANDLE,
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.BOOL),
    )
    kernel.IsProcessInJob.restype = wintypes.BOOL
    job = kernel.OpenJobObjectW(0x0004, False, name)  # JOB_OBJECT_QUERY
    if not job:
        raise OSError("Cannot open owned process job")
    try:
        deadline = time.monotonic() + 10
        while True:
            member = wintypes.BOOL()
            if not kernel.IsProcessInJob(
                kernel.GetCurrentProcess(), job, ctypes.byref(member)
            ):
                raise OSError("Cannot verify process job membership")
            if member.value:
                break
            if time.monotonic() >= deadline:
                raise OSError("Supervisor was not assigned to process job")
            time.sleep(0.01)
    finally:
        # The producer must own the last handle before the target starts.
        _close_windows_job(job)


def _supervise(job_name: str, command: list[str]) -> int:
    if _IS_WINDOWS:
        _wait_for_windows_job(job_name)

    async def execute() -> int:
        process = await asyncio.create_subprocess_exec(*command)
        return await process.wait()

    return asyncio.run(execute())


def parse_build_info(output: str) -> dict[str, Any]:
    """Parse `go version -m` records, including original and replacement IDs."""
    lines = output.splitlines()
    if not lines:
        raise InventoryError("Go build information is missing")
    _, separator, version = lines[0].rpartition(": ")
    if not separator or not re.fullmatch(r"go[0-9][^\s]*", version):
        raise InventoryError("Go build information header is missing")

    path: str | None = None
    main: dict[str, Any] | None = None
    dependencies: list[dict[str, Any]] = []
    last_module: dict[str, Any] | None = None
    platform: dict[str, str | None] = {"goos": None, "goarch": None}
    for line in lines[1:]:
        fields = line.split()
        if not fields:
            continue
        kind, values = fields[0], fields[1:]
        if kind == "path" and len(values) == 1 and path is None:
            path = values[0]
            last_module = None
        elif kind == "mod" and main is None:
            main = _module(values)
            last_module = main
        elif kind == "dep":
            dependency = _module(values)
            if any(item["path"] == dependency["path"] for item in dependencies):
                raise InventoryError("Duplicate Go module metadata")
            dependencies.append(dependency)
            last_module = dependency
        elif kind == "=>" and last_module is not None:
            replacement = _module(values)
            replacement.pop("replacement")
            last_module["replacement"] = replacement
            last_module = None
        elif kind == "build" and values:
            key, separator, value = values[0].partition("=")
            if separator and key in ("GOOS", "GOARCH"):
                platform_key = key.lower()
                if not value or platform[platform_key] is not None:
                    raise InventoryError("Invalid Go platform metadata")
                platform[platform_key] = value
            last_module = None
        else:
            raise InventoryError("Unrecognized or malformed Go build metadata")
    if path is None or main is None:
        raise InventoryError("Go build path or main module is missing")
    return {
        "go_version": version,
        "path": path,
        "main": main,
        "dependencies": dependencies,
        "platform": platform,
    }


def _run(
    command: list[str],
    *,
    cwd: Path | None = None,
    stdin: BinaryIO | None = None,
    stdout: BinaryIO | None = None,
    timeout: int = 60,
    discard_stdout: bool = False,
) -> subprocess.CompletedProcess[str]:
    async def execute() -> subprocess.CompletedProcess[str]:
        job_name = f"aud482-{uuid.uuid4().hex}" if _IS_WINDOWS else ""
        job = _setup_windows_job(job_name) if _IS_WINDOWS else None
        launch = (
            [
                sys.executable,
                str(Path(__file__)),
                "--aud482-supervise",
                job_name,
                *command,
            ]
            if _IS_WINDOWS
            else command
        )
        assigned = False
        try:
            process = await asyncio.create_subprocess_exec(
                *launch,
                cwd=cwd,
                start_new_session=not _IS_WINDOWS,
                stdin=stdin if stdin is not None else asyncio.subprocess.DEVNULL,
                stdout=(
                    stdout
                    if stdout is not None
                    else asyncio.subprocess.DEVNULL
                    if discard_stdout
                    else asyncio.subprocess.PIPE
                ),
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                if job is not None:
                    _assign_windows_job(job, process)
                    assigned = True
                data, _ = await asyncio.wait_for(process.communicate(), timeout)
            except BaseException:
                if job is not None:
                    _close_windows_job(job)
                    job = None
                if not assigned and process.returncode is None and _IS_WINDOWS:
                    process.kill()
                elif not _IS_WINDOWS and process.returncode is None:
                    os.killpg(process.pid, signal.SIGKILL)
                await process.communicate()
                raise
            if process.returncode != 0:
                raise InventoryError(f"{command[0]} {command[1]} failed")
            return subprocess.CompletedProcess(
                command, process.returncode, (data or b"").decode("utf-8"), ""
            )
        finally:
            if job is not None:
                _close_windows_job(job)

    try:
        return asyncio.run(execute())
    except (OSError, TimeoutError) as exc:
        raise InventoryError(f"{command[0]} {command[1]} failed") from exc


def inspect_binary(binary: Path) -> dict[str, Any]:
    """Read embedded metadata and reject a binary that changed during inspection."""
    try:
        _require_regular_binary(binary)
        before = _sha256(binary)
        result = _run(["go", "version", "-m", str(binary)])
        _require_regular_binary(binary)
        after = _sha256(binary)
    except OSError as exc:
        raise InventoryError("Cannot read Go binary") from exc
    if before != after:
        raise InventoryError("Go binary changed during metadata inspection")
    return {"sha256": before, **parse_build_info(result.stdout)}


def _require_regular_binary(binary: Path) -> None:
    metadata = binary.lstat()
    attributes = getattr(metadata, "st_file_attributes", 0)
    reparse_point = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    if not stat.S_ISREG(metadata.st_mode) or attributes & reparse_point:
        raise InventoryError("Extracted binary must be a regular file, not a link")


def _verify_container(
    repo: Path, container: str, image: str, name: str, owner: str
) -> None:
    fields = (
        '{{.Id}}|{{.Image}}|{{.Name}}|{{index .Config.Labels "org.ue.aud482.owner"}}'
    )
    result = _run(["docker", "inspect", "--format", fields, container], cwd=repo)
    if result.stdout.strip() != f"{container}|{image}|/{name}|{owner}":
        raise InventoryError("Container ownership could not be verified")


def _build_artifact(
    repo: Path,
    revision: str,
    work_dir: Path,
    name: str,
    source: str,
    dockerfile: str,
    runtime_path: str,
) -> dict[str, Any]:
    context = work_dir / f"{name}.context.tar"
    iidfile = work_dir / f"{name}.iid"
    binary = work_dir / f"{name}.binary"
    with context.open("xb") as stream:
        _run(
            [
                "git",
                "-c",
                "core.autocrlf=false",
                "-c",
                "core.eol=lf",
                "archive",
                "--format=tar",
                source,
            ],
            cwd=repo,
            stdout=stream,
        )
    context_hash = _sha256(context)
    build_label = f"org.ue.aud482.build={uuid.uuid4().hex}"
    build_receipt = work_dir / f"{name}.build-intent.json"
    with build_receipt.open("x", encoding="utf-8") as stream:
        json.dump(
            {
                "source_revision": revision,
                "context_sha256": context_hash,
                "dockerfile": dockerfile,
                "build_label": build_label,
            },
            stream,
            indent=2,
        )
        stream.write("\n")
    try:
        with context.open("rb") as stream:
            _run(
                [
                    "docker",
                    "build",
                    "--resource",
                    "cpu-quota=200000",
                    "--label",
                    f"org.opencontainers.image.revision={revision}",
                    "--label",
                    build_label,
                    "--iidfile",
                    str(iidfile),
                    "-f",
                    dockerfile,
                    "-",
                ],
                cwd=repo,
                stdin=stream,
                timeout=1800,
                discard_stdout=True,
            )
    except InventoryError as exc:
        raise InventoryError(
            f"Docker daemon build state unresolved; inspect {build_receipt}"
        ) from exc
    if _sha256(context) != context_hash:
        raise InventoryError("Build context changed during Docker build")
    image_id = iidfile.read_text(encoding="utf-8").strip()
    if not IMAGE_ID.fullmatch(image_id):
        raise InventoryError("Docker did not return an immutable image config ID")
    owner = uuid.uuid4().hex
    container_name = f"aud482-{name}-{owner}"
    label = f"org.ue.aud482.owner={owner}"
    receipt = work_dir / f"{name}.container-intent.json"
    with receipt.open("x", encoding="utf-8") as stream:
        json.dump(
            {
                "name": container_name,
                "ownership_label": label,
                "image_config_id": image_id,
                "source_revision": revision,
                "runtime_path": runtime_path,
            },
            stream,
            indent=2,
        )
        stream.write("\n")
    existing = _run(
        ["docker", "ps", "--all", "--filter", f"name=^/{container_name}$", "--quiet"],
        cwd=repo,
    ).stdout.strip()
    if existing:
        raise InventoryError("Reserved container name already exists")
    try:
        container = _run(
            ["docker", "create", "--name", container_name, "--label", label, image_id],
            cwd=repo,
        ).stdout.strip()
    except InventoryError as exc:
        raise InventoryError(
            f"Container creation outcome uncertain; inspect {receipt}"
        ) from exc
    if not CONTAINER_ID.fullmatch(container):
        raise InventoryError(f"Container creation outcome uncertain; inspect {receipt}")
    _verify_container(repo, container, image_id, container_name, owner)
    try:
        _run(["docker", "cp", f"{container}:{runtime_path}", str(binary)], cwd=repo)
    finally:
        _verify_container(repo, container, image_id, container_name, owner)
        _run(["docker", "rm", container], cwd=repo)
    metadata = inspect_binary(binary)
    if not metadata["dependencies"]:
        raise InventoryError("Final Go binary has no linked module metadata")
    return {
        "context_sha256": context_hash,
        "dockerfile": dockerfile,
        "build_label": build_label,
        "image_config_id": image_id,
        "runtime_path": runtime_path,
        "binary": metadata,
    }


def build_inventory(repo: Path, revision: str, work_dir: Path) -> dict[str, Any]:
    """Build both images from immutable archives and inventory their final binaries."""
    if not _IS_WINDOWS:
        raise InventoryError("POSIX build lifecycle has not been verified")
    _check_producer_identity()
    if not COMMIT.fullmatch(revision):
        raise InventoryError("A full 40-character commit SHA is required")
    commit = _run(["git", "rev-parse", "--verify", f"{revision}^{{commit}}"], cwd=repo)
    if commit.stdout.strip() != revision:
        raise InventoryError("Revision does not resolve to the requested commit")
    tree = _run(["git", "rev-parse", f"{revision}^{{tree}}"], cwd=repo).stdout.strip()
    if not COMMIT.fullmatch(tree):
        raise InventoryError("Git tree identity is invalid")
    artifacts = {
        "caddy": _build_artifact(
            repo,
            revision,
            work_dir,
            "caddy",
            f"{revision}:services/caddy",
            "Dockerfile",
            "/usr/bin/caddy",
        ),
        "probe": _build_artifact(
            repo,
            revision,
            work_dir,
            "probe",
            revision,
            "services/file-processor/Dockerfile",
            "/usr/local/bin/grpc_health_probe",
        ),
    }
    _check_producer_identity()
    return {
        "schema": "aud482-go-binary-inventory-v1",
        "source": {
            "revision": revision,
            "tree": tree,
            "context": "git archive; uncommitted changes are excluded",
        },
        "producer_sha256": _LOADED_PRODUCER_SHA256,
        "artifacts": artifacts,
        "limitations": [
            "Local builds are not proof of a separately published or CI image.",
            "Go module metadata is not a vulnerability or reachability assessment.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True, help="full Git commit SHA")
    parser.add_argument(
        "--work-dir", type=Path, required=True, help="new private directory"
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="new JSON report path"
    )
    args = parser.parse_args()
    try:
        if not COMMIT.fullmatch(args.revision):
            raise InventoryError("A full 40-character commit SHA is required")
        if args.output.exists() or args.output.is_symlink():
            raise InventoryError("Output path already exists")
        if not args.output.parent.is_dir():
            raise InventoryError("Output parent directory does not exist")
        args.work_dir.mkdir(parents=True, exist_ok=False)
        report = build_inventory(ROOT, args.revision, args.work_dir)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
            stream.write("\n")
    except (InventoryError, OSError) as exc:
        parser.exit(1, f"inventory failed: {exc}\n")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--aud482-supervise":
        raise SystemExit(_supervise(sys.argv[2], sys.argv[3:]))
    raise SystemExit(main())
