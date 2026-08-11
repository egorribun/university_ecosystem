"""Capture paired benchmarks in disposable, unprivileged Docker containers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

GO_IMAGE = (
    "docker.io/library/golang:1.26.5-bookworm@"
    "sha256:53eeac89074db483fdf0ab3be1df32bf6e47562263d2d0d6baa7f26acb4957dd"
)
DOCKER_BINARY = Path("/usr/bin/docker")
TIMEOUT_BINARY = Path("/usr/bin/timeout")
CONTAINER_USER = "10001:10001"
PAIR_COUNT = 12
MAX_OUTPUT_BYTES = 16 * 1024 * 1024
CONTAINER_MEMORY = "6g"
CONTAINER_CPUS = "2.0"
CONTAINER_PIDS_LIMIT = "512"
CACHE_VOLUME_SIZE = "2g"
RUST_TOOLCHAIN = "1.94.1"
CONTAINER_LOG_ARGUMENTS = (
    "--log-driver",
    "local",
    "--log-opt",
    "max-size=16m",
    "--log-opt",
    "max-file=1",
    "--log-opt",
    "compress=false",
)
# These paths exist only inside an isolated container's private tmpfs mounts.
CONTAINER_HOME = "/tmp/home"  # noqa: S108
CONTAINER_TMPFS = "/tmp:rw,exec,nosuid,nodev,size=4g,mode=1777"  # noqa: S108
CONTAINER_SMALL_TMPFS = "/tmp:rw,exec,nosuid,nodev,size=64m,mode=1777"  # noqa: S108
CONTAINER_RUN_TMPFS = "/run:rw,nosuid,nodev,size=64m,mode=1777"
_CAPTURE_READ_BYTES = 64 * 1024
_TERMINATE_WAIT_SECONDS = 30
CONTROL_PLANE_TIMEOUT_SECONDS = 30
_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_IMAGE_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_CONTAINER_NAME_RE = re.compile(r"^quality-benchmark-[0-9a-f]{32}$")
_VOLUME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_FORBIDDEN_ENV_PREFIXES = ("GITHUB_", "RUNNER_", "DOCKER_")


class CaptureError(RuntimeError):
    """Raised when isolated benchmark evidence cannot be safely collected."""


@dataclass(frozen=True)
class CaptureArguments:
    """Validated immutable inputs for one complete paired benchmark suite."""

    format_name: str
    base_worktree: Path
    candidate_worktree: Path
    artifact_root: Path
    runner_temp: Path
    base_revision: str
    candidate_revision: str
    rust_dockerfile: Path | None


def _validate_sha(value: str, label: str) -> str:
    if _SHA_RE.fullmatch(value) is None or value == "0" * 40:
        raise CaptureError(f"{label} must be a non-zero 40-hex commit SHA")
    return value


def _resolve_existing_directory(path: Path, label: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise CaptureError(f"Unable to resolve {label}: {exc}") from exc
    if not resolved.is_dir():
        raise CaptureError(f"{label} must be a directory: {resolved}")
    return resolved


def _validate_distinct_worktrees(base_worktree: Path, candidate_worktree: Path) -> None:
    """Reject accidental same-tree comparisons before a container is started."""

    if base_worktree == candidate_worktree:
        raise CaptureError("Base and candidate worktrees must be different directories")


def _resolve_worktree_head(worktree: Path, label: str) -> str:
    """Resolve one supplied worktree to the immutable commit Git will mount."""

    resolved_head = _run_checked(
        ("git", "-C", str(worktree), "rev-parse", "--verify", "HEAD^{commit}"),
        f"resolve {label} Git HEAD",
    ).stdout.strip()
    if _SHA_RE.fullmatch(resolved_head) is None or resolved_head == "0" * 40:
        raise CaptureError(f"Git returned an invalid {label} HEAD commit")
    return resolved_head.lower()


def _validate_worktree_revisions(
    *,
    base_worktree: Path,
    candidate_worktree: Path,
    base_revision: str,
    candidate_revision: str,
) -> None:
    """Bind declared provenance to both worktrees before capture can begin."""

    actual_base_revision = _resolve_worktree_head(base_worktree, "base worktree")
    actual_candidate_revision = _resolve_worktree_head(
        candidate_worktree, "candidate worktree"
    )
    if actual_base_revision != base_revision.lower():
        raise CaptureError("Git HEAD does not match declared base revision")
    if actual_candidate_revision != candidate_revision.lower():
        raise CaptureError("Git HEAD does not match declared candidate revision")


def _validate_image_content_id(value: str) -> str:
    """Accept only Docker's immutable content-addressed image identifier."""

    normalized = value.strip()
    if _IMAGE_ID_RE.fullmatch(normalized) is None:
        raise CaptureError(f"Docker returned an invalid image content ID: {value!r}")
    return normalized


def _new_container_name() -> str:
    """Return an unguessable host-generated Docker name for forced cleanup."""

    return f"quality-benchmark-{uuid.uuid4().hex}"


def _new_volume_name() -> str:
    """Return an unguessable host-generated name for one bounded cache volume."""

    return f"quality-benchmark-cache-{uuid.uuid4().hex}"


def _validate_container_name(value: str) -> str:
    if _CONTAINER_NAME_RE.fullmatch(value) is None:
        raise CaptureError(f"Container name is invalid: {value!r}")
    return value


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def prepare_artifact_root(artifact_root: Path, runner_temp: Path) -> Path:
    """Create a fresh output root below trusted runner temp, never a checkout."""

    trusted_temp = _resolve_existing_directory(runner_temp, "runner temp")
    resolved_root = artifact_root.resolve(strict=False)
    if not _is_within(resolved_root, trusted_temp) or resolved_root == trusted_temp:
        raise CaptureError(
            "Artifact root must be a fresh directory under the trusted runner temp"
        )
    if resolved_root.exists():
        raise CaptureError(f"Artifact root must not already exist: {resolved_root}")
    try:
        resolved_root.mkdir(mode=0o700, parents=False)
        resolved_root.chmod(0o700)
    except OSError as exc:
        raise CaptureError(f"Unable to create artifact root: {exc}") from exc
    return resolved_root


def _validate_environment(environment: Mapping[str, str]) -> None:
    for key, value in environment.items():
        if not key or "=" in key or "\x00" in key or "\x00" in value:
            raise CaptureError(f"Invalid container environment variable: {key!r}")
        if key.startswith(_FORBIDDEN_ENV_PREFIXES):
            raise CaptureError(
                f"Host-controlled environment cannot enter container: {key}"
            )


def _bounded_docker_run_options(
    *,
    container_name: str,
    network: str,
    tmpfs_mounts: Sequence[str],
    remove: bool = False,
    cache_initialization: bool = False,
) -> list[str]:
    """Return the mandatory isolation/resource options for every Docker run.

    Cache initialization is the only root exception: it creates the private
    volume directory with the unprivileged benchmark UID/GID before any source
    code is mounted or executed. Every other run uses ``CONTAINER_USER``.
    """

    if network not in {"bridge", "none"}:
        raise CaptureError(f"Unsupported container network mode: {network}")
    _validate_container_name(container_name)
    command = [
        str(DOCKER_BINARY),
        "run",
        "--name",
        container_name,
    ]
    if remove:
        command.append("--rm")
    command.extend(
        (
            "--init",
            "--platform",
            "linux/amd64",
            "--network",
            network,
            "--read-only",
            *CONTAINER_LOG_ARGUMENTS,
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges=true",
            "--memory",
            CONTAINER_MEMORY,
            "--memory-swap",
            CONTAINER_MEMORY,
            "--cpus",
            CONTAINER_CPUS,
            "--pids-limit",
            CONTAINER_PIDS_LIMIT,
            "--user",
            "0:0" if cache_initialization else CONTAINER_USER,
        )
    )
    for tmpfs_mount in tmpfs_mounts:
        command.extend(("--tmpfs", tmpfs_mount))
    return command


def build_container_command(
    *,
    image: str,
    source_worktree: Path,
    cache_volume: str,
    container_name: str,
    workdir: str,
    network: str,
    environment: Mapping[str, str],
    program: Sequence[str],
) -> list[str]:
    """Build one explicit Docker invocation without host environment inheritance."""

    source = _resolve_existing_directory(source_worktree, "source worktree")
    if not image or any(character.isspace() for character in image):
        raise CaptureError("Container image reference is invalid")
    if _VOLUME_RE.fullmatch(cache_volume) is None:
        raise CaptureError(f"Container cache volume is invalid: {cache_volume!r}")
    # The mount root itself is a valid workdir for the Rust workspace; nested
    # paths remain constrained below that read-only source mount.
    if workdir != "/src" and not workdir.startswith("/src/"):
        raise CaptureError("Container workdir must stay below the read-only /src mount")
    if not program or any(not token or "\x00" in token for token in program):
        raise CaptureError("Container program is invalid")
    _validate_environment(environment)

    command = _bounded_docker_run_options(
        container_name=container_name,
        network=network,
        tmpfs_mounts=(CONTAINER_TMPFS, CONTAINER_RUN_TMPFS),
    )
    command.extend(
        (
            "--mount",
            f"type=bind,src={source},dst=/src,readonly",
            "--mount",
            f"type=volume,src={cache_volume},dst=/cache",
            "--workdir",
            workdir,
        )
    )
    for key in sorted(environment):
        command.extend(("--env", f"{key}={environment[key]}"))
    return [*command, image, *program]


def _run_checked(
    command: Sequence[str], description: str
) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(  # noqa: S603 - all command tokens are constructed locally.
            list(command),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=CONTROL_PLANE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise CaptureError(
            f"{description} did not complete within {CONTROL_PLANE_TIMEOUT_SECONDS} seconds"
        ) from exc
    except OSError as exc:
        raise CaptureError(f"Unable to {description}: {exc}") from exc
    if completed.returncode != 0:
        raise CaptureError(
            f"{description} failed with exit status {completed.returncode}"
        )
    return completed


def _copy_limited_stream(source: BinaryIO, destination: BinaryIO) -> bool:
    """Copy output until its byte cap; return whether the cap was exceeded."""

    written = 0
    while block := source.read(_CAPTURE_READ_BYTES):
        remaining = MAX_OUTPUT_BYTES - written
        if remaining <= 0:
            return True
        destination.write(block[:remaining])
        written += min(len(block), remaining)
        if len(block) > remaining:
            return True
    return False


def _terminate_capture_process(process: subprocess.Popen[bytes]) -> None:
    """Terminate the timeout wrapper and its Docker child after unsafe output."""

    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                return
        else:  # pragma: no cover - isolated capture runs only on Linux CI.
            process.terminate()
        process.wait(timeout=_TERMINATE_WAIT_SECONDS)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                return
        else:  # pragma: no cover - isolated capture runs only on Linux CI.
            process.kill()
        process.wait()


def _timeout_command(command: Sequence[str], *, timeout_seconds: int) -> list[str]:
    """Wrap a capture with TERM and a mandatory subsequent KILL deadline."""

    if timeout_seconds <= 0:
        raise CaptureError("Capture timeout must be positive")
    return [
        str(TIMEOUT_BINARY),
        "--foreground",
        "--kill-after=30s",
        f"{timeout_seconds}s",
        *command,
    ]


def _force_remove_container(container_name: str) -> None:
    """Remove a daemon-owned container even if its Docker client was killed."""

    name = _validate_container_name(container_name)
    removed = _run_container_cleanup_command(
        [str(DOCKER_BINARY), "container", "rm", "--force", name],
        action="force-removing",
        container_name=name,
    )
    if removed.returncode == 0:
        return
    exists = _run_container_cleanup_command(
        [str(DOCKER_BINARY), "container", "inspect", name],
        action="verifying cleanup of",
        container_name=name,
    )
    if exists.returncode == 0:
        raise CaptureError(f"Unable to force-remove isolated container {name}")
    no_such_container = "No such" in (removed.stderr + exists.stderr)
    if not no_such_container:
        raise CaptureError(f"Unable to verify cleanup of isolated container {name}")


def _run_container_cleanup_command(
    command: Sequence[str], *, action: str, container_name: str
) -> subprocess.CompletedProcess[str]:
    """Run bounded daemon cleanup without allowing raw client failures to escape."""

    try:
        return subprocess.run(  # noqa: S603 - command tokens are locally constructed.
            list(command),
            check=False,
            capture_output=True,
            text=True,
            timeout=_TERMINATE_WAIT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise CaptureError(
            "Docker container cleanup timed out while "
            f"{action} isolated container {container_name}"
        ) from exc
    except OSError as exc:
        raise CaptureError(
            "Docker container cleanup could not start while "
            f"{action} isolated container {container_name}: {exc}"
        ) from exc


def _safe_capture(
    command: Sequence[str],
    output_path: Path,
    *,
    description: str,
    timeout_seconds: int,
    container_name: str | None = None,
) -> None:
    """Capture untrusted container output without exposing GitHub command syntax."""

    marker = uuid.uuid4().hex
    print(f"::stop-commands::{marker}", flush=True)
    return_code: int | None = None
    output_exceeded = False
    process: subprocess.Popen[bytes] | None = None
    if container_name is not None:
        _validate_container_name(container_name)
    try:
        with output_path.open("xb") as output:
            process = subprocess.Popen(  # noqa: S603 - command is a fixed Docker argv list.
                _timeout_command(command, timeout_seconds=timeout_seconds),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            stream = process.stdout
            if stream is None:
                _terminate_capture_process(process)
                raise CaptureError(f"Unable to capture {description} output stream")
            try:
                output_exceeded = _copy_limited_stream(stream, output)
            except (
                BaseException
            ):  # RZ-22-01-JUSTIFIED: terminate untrusted capture before re-raise.
                _terminate_capture_process(process)
                raise
            finally:
                stream.close()
            if output_exceeded:
                _terminate_capture_process(process)
            else:
                return_code = process.wait()
    finally:
        try:
            if process is not None and process.poll() is None:
                _terminate_capture_process(process)
            if container_name is not None:
                _force_remove_container(container_name)
        finally:
            print(f"::{marker}::", flush=True)

    if output_exceeded:
        raise CaptureError(
            f"{description} output exceeds the {MAX_OUTPUT_BYTES}-byte safety limit"
        )
    if return_code != 0:
        raise CaptureError(f"{description} failed with exit status {return_code}")


def _create_private_volume(image: str, artifact_root: Path, side: str) -> str:
    volume = _new_volume_name()
    completed = _run_checked(
        (
            str(DOCKER_BINARY),
            "volume",
            "create",
            "--driver",
            "local",
            "--opt",
            "type=tmpfs",
            "--opt",
            "device=tmpfs",
            "--opt",
            f"o=size={CACHE_VOLUME_SIZE},uid=10001,gid=10001,mode=0700",
            volume,
        ),
        f"create {side} cache volume",
    )
    created_volume = completed.stdout.strip()
    if created_volume != volume or _VOLUME_RE.fullmatch(created_volume) is None:
        raise CaptureError(
            f"Docker returned an unsafe cache volume name: {created_volume!r}"
        )

    container_name = _new_container_name()
    initialize = _bounded_docker_run_options(
        container_name=container_name,
        network="none",
        tmpfs_mounts=(CONTAINER_SMALL_TMPFS,),
        cache_initialization=True,
    )
    initialize.extend(
        (
            "--mount",
            f"type=volume,src={volume},dst=/cache",
            image,
            "sh",
            "-ec",
            "install -d -m 0700 -o 10001 -g 10001 /cache",
        )
    )
    try:
        _safe_capture(
            initialize,
            artifact_root / f"initialize-{side}-cache.log",
            description=f"initialize {side} cache volume",
            timeout_seconds=60,
            container_name=container_name,
        )
    except (
        BaseException
    ):  # RZ-22-01-JUSTIFIED: remove the private cache volume before re-raise.
        _remove_volume(volume)
        raise
    return volume


def _remove_volume(volume: str) -> None:
    _best_effort_docker_cleanup([str(DOCKER_BINARY), "volume", "rm", "--force", volume])


def _best_effort_docker_cleanup(command: Sequence[str]) -> None:
    """Bound disposable-object cleanup without obscuring the primary outcome."""

    try:
        subprocess.run(  # noqa: S603 - cleanup tokens are locally constructed.
            list(command),
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=CONTROL_PLANE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return


def _container_tool_output(
    image: str,
    program: Sequence[str],
    *,
    environment: Mapping[str, str],
) -> str:
    _validate_environment(environment)
    container_name = _new_container_name()
    command = _bounded_docker_run_options(
        container_name=container_name,
        network="none",
        tmpfs_mounts=(CONTAINER_SMALL_TMPFS,),
        remove=True,
    )
    for key in sorted(environment):
        command.extend(("--env", f"{key}={environment[key]}"))
    command.extend((image, *program))
    with tempfile.TemporaryDirectory(prefix="quality-toolchain-") as temporary_dir:
        output_path = Path(temporary_dir) / "toolchain-output.txt"
        _safe_capture(
            command,
            output_path,
            description="query isolated toolchain",
            timeout_seconds=CONTROL_PLANE_TIMEOUT_SECONDS,
            container_name=container_name,
        )
        try:
            return output_path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError as exc:
            raise CaptureError(
                f"Unable to read isolated toolchain output: {exc}"
            ) from exc


def _image_content_id(image: str) -> str:
    """Resolve the immutable local image identifier after trusted setup."""

    output = _run_checked(
        (str(DOCKER_BINARY), "image", "inspect", "--format", "{{.Id}}", image),
        "inspect isolated benchmark image",
    ).stdout
    return _validate_image_content_id(output)


def _docker_server_version() -> str:
    """Record the daemon version that enforced the capture boundary."""

    version = _run_checked(
        (str(DOCKER_BINARY), "version", "--format", "{{.Server.Version}}"),
        "query Docker server version",
    ).stdout.strip()
    if not version:
        raise CaptureError("Docker returned an empty server version")
    return version


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise CaptureError(f"Unable to hash trusted file {path}: {exc}") from exc
    return digest.hexdigest()


def _build_rust_image(
    *,
    dockerfile: Path,
    base_worktree: Path,
    runner_temp: Path,
    artifact_root: Path,
    base_revision: str,
) -> str:
    try:
        resolved_dockerfile = dockerfile.resolve(strict=True)
    except OSError as exc:
        raise CaptureError(f"Unable to resolve trusted Rust Dockerfile: {exc}") from exc
    if not resolved_dockerfile.is_file() or not _is_within(
        resolved_dockerfile, base_worktree
    ):
        raise CaptureError("Rust Dockerfile must be a file inside the base worktree")

    image = f"quality-performance-rust:{base_revision[:12].lower()}"
    with tempfile.TemporaryDirectory(
        dir=runner_temp, prefix="quality-performance-rust-"
    ) as context_directory:
        context = Path(context_directory)
        copied_dockerfile = context / "Dockerfile"
        try:
            shutil.copyfile(resolved_dockerfile, copied_dockerfile)
        except OSError as exc:
            raise CaptureError(
                f"Unable to copy trusted Rust Dockerfile: {exc}"
            ) from exc
        try:
            _safe_capture(
                (
                    str(DOCKER_BINARY),
                    "build",
                    "--pull",
                    "--file",
                    str(copied_dockerfile),
                    "--tag",
                    image,
                    str(context),
                ),
                artifact_root / "build-rust-image.log",
                description="build trusted Rust benchmark image",
                timeout_seconds=900,
            )
        except CaptureError:
            _remove_image(image)
            raise
    return image


def _remove_image(image: str) -> None:
    _best_effort_docker_cleanup([str(DOCKER_BINARY), "image", "rm", "--force", image])


def _go_environment(*, offline: bool) -> dict[str, str]:
    environment = {
        "GOCACHE": "/cache/go-build",
        "GOMODCACHE": "/cache/go-mod",
        "GOPATH": "/cache/go-path",
        "GOTOOLCHAIN": "local",
        "HOME": CONTAINER_HOME,
    }
    if offline:
        environment.update(
            {
                "GOFLAGS": "-mod=readonly -buildvcs=false",
                "GOPROXY": "off",
                "GOSUMDB": "off",
            }
        )
    return environment


def _go_prefetch_environment() -> dict[str, str]:
    """Fetch Go modules without mutating the read-only workspace checkout."""

    environment = _go_environment(offline=False)
    environment.update(
        {
            "GOWORK": "off",
            "GOFLAGS": "-mod=readonly -buildvcs=false",
        }
    )
    return environment


def _rust_environment(*, offline: bool) -> dict[str, str]:
    environment = {
        "CARGO_HOME": "/cache/cargo",
        "CARGO_TARGET_DIR": "/cache/cargo-target",
        "HOME": CONTAINER_HOME,
        "LD_LIBRARY_PATH": "/usr/local/lib",
        "RUSTUP_TOOLCHAIN": RUST_TOOLCHAIN,
    }
    if offline:
        environment["CARGO_NET_OFFLINE"] = "true"
    return environment


def _go_program() -> tuple[str, ...]:
    return (
        "go",
        "test",
        "-mod=readonly",
        "-buildvcs=false",
        "-bench=.",
        "-run=^$",
        "-benchmem",
        "-count=1",
        "-benchtime=1s",
        "./...",
    )


def _rust_prefetch_program() -> tuple[str, ...]:
    """Fetch dependencies for the nested extension manifest from /src."""

    return (
        "cargo",
        "fetch",
        "--locked",
        "--manifest-path",
        "native/rust_ext/Cargo.toml",
    )


def _rust_program(*, warm: bool) -> tuple[str, ...]:
    program = (
        "cargo",
        "bench",
        "--locked",
        "--offline",
        "--manifest-path",
        "native/rust_ext/Cargo.toml",
        "--bench",
        "conflict_bench",
        "--no-default-features",
    )
    if warm:
        return (*program, "--no-run")
    return (*program, "--", "--output-format", "bencher")


def _capture_pair(
    *,
    image: str,
    source_worktree: Path,
    cache_volume: str,
    workdir: str,
    environment: Mapping[str, str],
    program: Sequence[str],
    output_path: Path,
    description: str,
) -> None:
    container_name = _new_container_name()
    _safe_capture(
        build_container_command(
            image=image,
            source_worktree=source_worktree,
            cache_volume=cache_volume,
            container_name=container_name,
            workdir=workdir,
            network="none",
            environment=environment,
            program=program,
        ),
        output_path,
        description=description,
        timeout_seconds=300,
        container_name=container_name,
    )


def _prefetch(
    *,
    image: str,
    source_worktree: Path,
    cache_volume: str,
    workdir: str,
    environment: Mapping[str, str],
    program: Sequence[str],
    output_path: Path,
    description: str,
) -> None:
    container_name = _new_container_name()
    _safe_capture(
        build_container_command(
            image=image,
            source_worktree=source_worktree,
            cache_volume=cache_volume,
            container_name=container_name,
            workdir=workdir,
            network="bridge",
            environment=environment,
            program=program,
        ),
        output_path,
        description=description,
        timeout_seconds=600,
        container_name=container_name,
    )


def _write_toolchain(
    *,
    artifact_root: Path,
    format_name: str,
    image: str,
    base_revision: str,
    rust_dockerfile: Path | None,
) -> None:
    tool_name = "go" if format_name == "go" else "rustc"
    version_program = (
        ("go", "version")
        if format_name == "go"
        else ("rustc", "--version", "--verbose")
    )
    version_environment = {
        "HOME": CONTAINER_HOME,
        "GOTOOLCHAIN": "local",
    }
    if format_name == "rust":
        version_environment = {
            "HOME": CONTAINER_HOME,
            "RUSTUP_TOOLCHAIN": RUST_TOOLCHAIN,
        }
    payload: dict[str, object] = {
        tool_name: _container_tool_output(
            image, version_program, environment=version_environment
        ),
        "docker_server_version": _docker_server_version(),
        "uname": os.uname().sysname
        + " "
        + os.uname().release
        + " "
        + os.uname().machine,
        "image": {
            "content_id": _image_content_id(image),
            "reference": image,
        },
        "isolation": {
            "cache": "per-side-private-docker-volume",
            "network_during_measurement": "none",
            "runtime": "docker",
            "source_mount": "read-only",
            "user": CONTAINER_USER,
        },
    }
    if rust_dockerfile is not None:
        payload["trusted_dockerfile_sha256"] = _file_sha256(rust_dockerfile)
        payload["trusted_dockerfile_base_revision"] = base_revision
    (artifact_root / "toolchain.json").write_text(
        json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8"
    )


def capture(arguments: CaptureArguments) -> None:
    """Collect one full twelve-pair suite without mounting host evidence to code."""

    if not DOCKER_BINARY.is_file() or not TIMEOUT_BINARY.is_file():
        raise CaptureError(
            "Required Docker isolation tools are unavailable on this runner"
        )
    base_revision = _validate_sha(arguments.base_revision, "base revision")
    candidate_revision = _validate_sha(
        arguments.candidate_revision, "candidate revision"
    )
    if base_revision.lower() == candidate_revision.lower():
        raise CaptureError("Base and candidate revisions must differ")

    base_worktree = _resolve_existing_directory(
        arguments.base_worktree, "base worktree"
    )
    candidate_worktree = _resolve_existing_directory(
        arguments.candidate_worktree, "candidate worktree"
    )
    _validate_distinct_worktrees(base_worktree, candidate_worktree)
    _validate_worktree_revisions(
        base_worktree=base_worktree,
        candidate_worktree=candidate_worktree,
        base_revision=base_revision,
        candidate_revision=candidate_revision,
    )
    runner_temp = _resolve_existing_directory(arguments.runner_temp, "runner temp")
    artifact_root = prepare_artifact_root(arguments.artifact_root, runner_temp)
    (artifact_root / "base").mkdir()
    (artifact_root / "candidate").mkdir()

    image: str | None = None
    base_volume: str | None = None
    candidate_volume: str | None = None
    try:
        if arguments.format_name == "go":
            image = GO_IMAGE
            workdir = "/src/services/ws-hub"
            prefetch_program = ("sh", "-ec", "go mod download && go mod verify")
            prefetch_environment = _go_prefetch_environment()
            measurement_environment = _go_environment(offline=True)
            warm_program = _go_program()
            measurement_program = _go_program()
        else:
            if arguments.rust_dockerfile is None:
                raise CaptureError("Rust capture requires a trusted Rust Dockerfile")
            image = _build_rust_image(
                dockerfile=arguments.rust_dockerfile,
                base_worktree=base_worktree,
                runner_temp=runner_temp,
                artifact_root=artifact_root,
                base_revision=base_revision,
            )
            workdir = "/src"
            prefetch_program = _rust_prefetch_program()
            prefetch_environment = _rust_environment(offline=False)
            measurement_environment = _rust_environment(offline=True)
            warm_program = _rust_program(warm=True)
            measurement_program = _rust_program(warm=False)

        base_volume = _create_private_volume(image, artifact_root, "base")
        candidate_volume = _create_private_volume(image, artifact_root, "candidate")
        for side, worktree, volume in (
            ("base", base_worktree, base_volume),
            ("candidate", candidate_worktree, candidate_volume),
        ):
            _prefetch(
                image=image,
                source_worktree=worktree,
                cache_volume=volume,
                workdir=workdir,
                environment=prefetch_environment,
                program=prefetch_program,
                output_path=artifact_root / f"prefetch-{side}.log",
                description=f"prefetch {side} benchmark dependencies",
            )
            _capture_pair(
                image=image,
                source_worktree=worktree,
                cache_volume=volume,
                workdir=workdir,
                environment=measurement_environment,
                program=warm_program,
                output_path=artifact_root / f"warm-{side}.log",
                description=f"warm {side} benchmark build",
            )

        _write_toolchain(
            artifact_root=artifact_root,
            format_name=arguments.format_name,
            image=image,
            base_revision=base_revision,
            rust_dockerfile=arguments.rust_dockerfile,
        )
        for pair in range(1, PAIR_COUNT + 1):
            ordered_sides = (
                (
                    ("base", base_worktree, base_volume),
                    ("candidate", candidate_worktree, candidate_volume),
                )
                if pair % 2
                else (
                    ("candidate", candidate_worktree, candidate_volume),
                    ("base", base_worktree, base_volume),
                )
            )
            for side, worktree, volume in ordered_sides:
                _capture_pair(
                    image=image,
                    source_worktree=worktree,
                    cache_volume=volume,
                    workdir=workdir,
                    environment=measurement_environment,
                    program=measurement_program,
                    output_path=artifact_root / side / f"pair-{pair:02d}.txt",
                    description=f"capture {side} benchmark pair {pair:02d}",
                )
    finally:
        if base_volume is not None:
            _remove_volume(base_volume)
        if candidate_volume is not None:
            _remove_volume(candidate_volume)
        if arguments.format_name == "rust" and image is not None:
            _remove_image(image)


def _parse_arguments(argv: Sequence[str] | None = None) -> CaptureArguments:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("go", "rust"), required=True)
    parser.add_argument("--base-worktree", type=Path, required=True)
    parser.add_argument("--candidate-worktree", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--runner-temp", type=Path, required=True)
    parser.add_argument("--base-revision", required=True)
    parser.add_argument("--candidate-revision", required=True)
    parser.add_argument("--rust-dockerfile", type=Path)
    parsed = parser.parse_args(argv)
    if parsed.format == "rust" and parsed.rust_dockerfile is None:
        parser.error("--rust-dockerfile is required for --format rust")
    if parsed.format == "go" and parsed.rust_dockerfile is not None:
        parser.error("--rust-dockerfile is only valid for --format rust")
    return CaptureArguments(
        format_name=parsed.format,
        base_worktree=parsed.base_worktree,
        candidate_worktree=parsed.candidate_worktree,
        artifact_root=parsed.artifact_root,
        runner_temp=parsed.runner_temp,
        base_revision=parsed.base_revision,
        candidate_revision=parsed.candidate_revision,
        rust_dockerfile=parsed.rust_dockerfile,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Capture evidence and return a fail-closed CI status."""

    try:
        arguments = _parse_arguments(argv)
        capture(arguments)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    except CaptureError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (OSError, subprocess.SubprocessError) as exc:
        print(
            f"error: unable to capture isolated benchmark evidence: {exc}",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
