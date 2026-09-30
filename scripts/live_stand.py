"""Owned live acceptance stand: a dedicated worktree running the full stack.

The stand runs from ``../ue-live`` (a detached git worktree of this
repository). Every run receives a unique Compose project recorded in an
ownership marker, so its volumes and networks are isolated from other stacks.
It adds Mailpit and locally generated VAPID keys through
``docker-compose.live.yml``.

Usage::

    python scripts/live_stand.py up [--ref HEAD]   # create/refresh the worktree and start
    python scripts/live_stand.py seed               # load demo users and content
    python scripts/live_stand.py status             # read-only status
    python scripts/live_stand.py stop               # stop containers; preserve data
    python scripts/live_stand.py teardown           # remove only this run's Compose data

``down`` remains a compatibility alias for ``stop``. ``teardown`` preserves
the worktree, ``.env*`` files, secrets and evidence; it removes volumes only
after validating the run ownership marker.
"""

from __future__ import annotations

import argparse
import base64
import errno
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKTREE_NAME = "ue-live"
WORKTREE = REPO_ROOT.parent / WORKTREE_NAME
OVERLAY = "docker-compose.live.yml"
COMPOSE_FILES = ("docker-compose.full.yml", OVERLAY)
MAILPIT_PORT = 18025
PUBLISHED_PORTS = (80, 443, MAILPIT_PORT)
PORT_BIND_HOSTS = {80: "", 443: "", MAILPIT_PORT: "127.0.0.1"}
VAPID_FILE = Path(".secrets") / "live-vapid.json"
STAND_FILE = Path(".secrets") / "live-stand.json"
PROJECT_PREFIX = "ue-live-"
PROJECT_PATTERN = re.compile(r"^ue-live-[0-9a-f]{16}$")
OWNER_SCHEMA_VERSION = 2
COMPOSE_INSPECTION_PLACEHOLDER = "live-stand-inspection-placeholder"
SEED_SCRIPTS = ("scripts/seed_demo_data.py", "scripts/seed_admin_data.py")
STAND_PATHS_TO_PROTECT = (
    Path(OVERLAY),
    Path(".env"),
    Path(".env.docker"),
    Path(".env.docker.workers"),
    Path(".secrets"),
    STAND_FILE,
    VAPID_FILE,
    Path(".secrets/jwt_rs256.pem"),
    Path(".secrets/jwt_rs256.pub.pem"),
    Path(".secrets/temporal_api_key"),
    Path(".secrets/s3-cutover-attestation.txt"),
)


class StandError(RuntimeError):
    """A precondition for operating the stand does not hold."""


@dataclass(frozen=True)
class StandOwner:
    """Validated identity of one dedicated Compose run."""

    repository: str
    worktree: str
    project_name: str


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate_vapid_keys() -> dict[str, str]:
    """Return a P-256 VAPID key pair in the Web Push base64url encoding."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    raw_private = private_key.private_numbers().private_value.to_bytes(32, "big")
    public_point = private_key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    return {"public": _b64url(public_point), "private": _b64url(raw_private)}


def _path_is_reparse_point(path: Path) -> bool:
    try:
        path_stat = path.lstat()
    except FileNotFoundError:
        return False
    except OSError as error:
        raise StandError(f"cannot inspect path safety: {path}") from error

    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    if (
        stat.S_ISLNK(path_stat.st_mode)
        or getattr(path_stat, "st_file_attributes", 0) & reparse_flag
    ):
        return True

    is_junction = getattr(path, "is_junction", None)
    try:
        return bool(is_junction and is_junction())
    except OSError as error:
        raise StandError(f"cannot inspect path safety: {path}") from error


def _assert_no_reparse_ancestors(path: Path) -> None:
    for candidate in (path, *path.parents):
        if _path_is_reparse_point(candidate):
            raise StandError(f"refusing to use a reparse point: {candidate}")


def _assert_worktree_paths_safe(worktree: Path, relative_paths: Sequence[Path]) -> None:
    root = Path(os.path.abspath(worktree))
    _assert_no_reparse_ancestors(root)
    for relative_path in relative_paths:
        if relative_path.is_absolute():
            raise StandError("stand safety paths must remain relative to the worktree")
        candidate = Path(os.path.abspath(root / relative_path))
        try:
            candidate.relative_to(root)
        except ValueError as error:
            raise StandError("stand safety path escapes the owned worktree") from error
        _assert_no_reparse_ancestors(candidate)


def _assert_stand_paths_safe(worktree: Path) -> None:
    _assert_worktree_paths_safe(worktree, STAND_PATHS_TO_PROTECT)


def load_or_create_vapid(worktree: Path) -> dict[str, str]:
    path = worktree / VAPID_FILE
    _assert_worktree_paths_safe(worktree, (VAPID_FILE,))
    if path.is_file():
        return load_vapid(worktree)
    keys = generate_vapid_keys()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as key_file:
            key_file.write(json.dumps(keys))
        if os.name != "nt":
            path.chmod(0o600)
    except FileExistsError:
        return load_vapid(worktree)
    return keys


def load_vapid(worktree: Path) -> dict[str, str]:
    """Read existing VAPID keys without creating or changing local files."""
    path = worktree / VAPID_FILE
    _assert_worktree_paths_safe(worktree, (VAPID_FILE,))
    if not path.is_file():
        raise StandError(
            f"missing or unsafe VAPID key file: {path}; run `live_stand.py up`"
        )
    try:
        keys = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StandError(f"cannot read VAPID key pair from {path}") from error
    if (
        not isinstance(keys, dict)
        or set(keys) != {"public", "private"}
        or not all(isinstance(value, str) and value for value in keys.values())
    ):
        raise StandError(f"{path} does not hold a VAPID key pair")
    return {"public": keys["public"], "private": keys["private"]}


def _git_common_directory() -> Path:
    """Resolve the repository's common Git metadata directory."""
    git_entry = REPO_ROOT / ".git"
    try:
        if git_entry.is_dir():
            git_directory = git_entry
        elif git_entry.is_file():
            git_file = git_entry.read_text(encoding="utf-8").strip()
            if not git_file.startswith("gitdir:"):
                raise StandError(f"invalid Git metadata pointer: {git_entry}")
            raw_git_directory = Path(git_file.partition(":")[2].strip())
            git_directory = (
                raw_git_directory
                if raw_git_directory.is_absolute()
                else REPO_ROOT / raw_git_directory
            )
            git_directory = git_directory.resolve(strict=True)
            common_directory_file = git_directory / "commondir"
            if common_directory_file.is_file():
                raw_common_directory = Path(
                    common_directory_file.read_text(encoding="utf-8").strip()
                )
                git_directory = (
                    raw_common_directory
                    if raw_common_directory.is_absolute()
                    else git_directory / raw_common_directory
                )
        else:
            raise StandError(f"Git metadata is missing: {git_entry}")
        result = git_directory.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise StandError("cannot resolve the common Git metadata directory") from error
    if not result.is_dir():
        raise StandError("the common Git metadata path is not a directory")
    return result


def _owner_signing_key(*, create: bool) -> bytes:
    """Read or create a local HMAC key under untracked Git metadata."""
    key_path = _git_common_directory() / "live-stand-owner.key"
    _assert_no_reparse_ancestors(key_path)
    if key_path.is_file():
        key = key_path.read_bytes()
    elif create:
        key = secrets.token_bytes(32)
        try:
            descriptor = os.open(
                key_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError:
            _assert_no_reparse_ancestors(key_path)
            if not key_path.is_file():
                raise StandError("unsafe live stand owner key file") from None
            key = key_path.read_bytes()
        else:
            with os.fdopen(descriptor, "wb") as key_file:
                key_file.write(key)
            if os.name != "nt":
                key_path.chmod(0o600)
    else:
        raise StandError("missing live stand owner key in Git metadata")
    if len(key) != 32:
        raise StandError("invalid live stand owner key in Git metadata")
    return key


def _owner_signature(payload: dict[str, object], key: bytes) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hmac.new(key, canonical.encode("utf-8"), hashlib.sha256).hexdigest()


@contextmanager
def stand_lifecycle_lock() -> Iterator[None]:
    """Serialize lifecycle and data operations for this stand worktree."""
    lock_path = WORKTREE.parent / f".{WORKTREE_NAME}.lifecycle.lock"
    _assert_no_reparse_ancestors(lock_path)
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as error:
        raise StandError(
            f"cannot open the live stand lifecycle lock: {lock_path}"
        ) from error

    with os.fdopen(descriptor, "r+b") as lock_file:
        if os.name == "nt":
            import msvcrt

            if os.fstat(lock_file.fileno()).st_size == 0:
                lock_file.write(b"\0")
                lock_file.flush()
            while True:
                try:
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as error:
                    if error.errno not in {errno.EACCES, errno.EDEADLK, errno.EAGAIN}:
                        raise StandError(
                            "cannot acquire the live stand lifecycle lock"
                        ) from error
                    time.sleep(0.05)
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)  # type: ignore[attr-defined]
        try:
            yield
        finally:
            if os.name == "nt":
                import msvcrt

                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]


def _validate_project_name(project_name: str) -> None:
    if not PROJECT_PATTERN.fullmatch(project_name):
        raise StandError(f"refusing unexpected Compose project name {project_name!r}")


def _expected_worktree(worktree: Path) -> Path:
    _assert_no_reparse_ancestors(worktree)
    try:
        candidate = worktree.resolve(strict=False)
        expected = WORKTREE.resolve(strict=False)
    except (OSError, RuntimeError) as error:
        raise StandError("cannot resolve the live stand worktree path") from error
    if worktree.is_symlink() or candidate != expected:
        raise StandError(f"refusing unexpected worktree path {worktree}")
    return candidate


def create_stand_owner(worktree: Path) -> StandOwner:
    """Create a unique ownership marker for a newly prepared worktree."""
    expected_worktree = _expected_worktree(worktree)
    if not expected_worktree.is_dir():
        raise StandError(f"stand worktree does not exist: {worktree}")
    _assert_worktree_paths_safe(worktree, (Path(".secrets"), STAND_FILE))
    secrets_dir = worktree / ".secrets"
    secrets_dir.mkdir(parents=True, exist_ok=True)
    marker = worktree / STAND_FILE
    if marker.is_symlink() or marker.exists():
        raise StandError(f"ownership metadata already exists or is unsafe: {marker}")
    try:
        repository = str(REPO_ROOT.resolve(strict=True))
    except (OSError, RuntimeError) as error:
        raise StandError(
            "cannot resolve the repository path for the live stand"
        ) from error
    owner = StandOwner(
        repository=repository,
        worktree=str(expected_worktree),
        project_name=f"{PROJECT_PREFIX}{secrets.token_hex(8)}",
    )
    _validate_project_name(owner.project_name)
    payload = {
        "version": OWNER_SCHEMA_VERSION,
        "repository": owner.repository,
        "worktree": owner.worktree,
        "project_name": owner.project_name,
    }
    marker_data = {
        **payload,
        "signature": _owner_signature(payload, _owner_signing_key(create=True)),
    }
    try:
        with marker.open("x", encoding="utf-8") as marker_file:
            marker_file.write(json.dumps(marker_data, indent=2) + "\n")
        if os.name != "nt":
            marker.chmod(0o600)
    except FileExistsError as error:
        raise StandError(f"ownership metadata already exists: {marker}") from error
    return owner


def load_stand_owner(worktree: Path) -> StandOwner:
    """Load and validate an existing stand marker without mutating it."""
    expected_worktree = _expected_worktree(worktree)
    _assert_worktree_paths_safe(worktree, (Path(".secrets"), STAND_FILE))
    marker = worktree / STAND_FILE
    if marker.is_symlink() or not marker.is_file():
        raise StandError(
            f"missing or unsafe ownership metadata: {marker}; run `live_stand.py up`"
        )
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StandError(f"cannot read ownership metadata: {marker}") from error
    if (
        not isinstance(data, dict)
        or set(data)
        != {"version", "repository", "worktree", "project_name", "signature"}
        or not isinstance(data.get("version"), int)
        or isinstance(data.get("version"), bool)
        or data.get("version") != OWNER_SCHEMA_VERSION
        or not all(
            isinstance(data.get(key), str)
            for key in ("repository", "worktree", "project_name")
        )
    ):
        raise StandError(f"invalid ownership metadata: {marker}")
    try:
        marker_repository = Path(data["repository"]).resolve(strict=False)
        expected_repository = REPO_ROOT.resolve(strict=True)
        marker_worktree = Path(data["worktree"]).resolve(strict=False)
    except (OSError, RuntimeError) as error:
        raise StandError(f"invalid paths in ownership metadata: {marker}") from error
    if marker_worktree != expected_worktree:
        raise StandError("ownership metadata belongs to another worktree")
    if marker_repository != expected_repository:
        raise StandError("ownership metadata belongs to another repository")
    project_name = data["project_name"]
    _validate_project_name(project_name)
    payload = {
        "version": data["version"],
        "repository": data["repository"],
        "worktree": data["worktree"],
        "project_name": project_name,
    }
    signature = data["signature"]
    if not isinstance(signature, str) or not hmac.compare_digest(
        signature, _owner_signature(payload, _owner_signing_key(create=False))
    ):
        raise StandError("ownership metadata signature is invalid")
    return StandOwner(
        repository=str(marker_repository),
        worktree=str(marker_worktree),
        project_name=project_name,
    )


def stand_environment(keys: dict[str, str], project_name: str) -> dict[str, str]:
    _validate_project_name(project_name)
    env = os.environ.copy()
    env["COMPOSE_PROJECT_NAME"] = project_name
    env["LIVE_VAPID_PUBLIC_KEY"] = keys["public"]
    env["LIVE_VAPID_PRIVATE_KEY"] = keys["private"]
    env["LIVE_MAILPIT_PORT"] = str(MAILPIT_PORT)
    return env


def compose_control_environment(project_name: str) -> dict[str, str]:
    """Build a secret-free environment for read/stop/remove Compose commands."""
    _validate_project_name(project_name)
    env = os.environ.copy()
    env["COMPOSE_PROJECT_NAME"] = project_name
    # Compose interpolates these required live-overlay fields while loading
    # the project, even for `ps`, `stop`, or `down`. These commands never
    # recreate containers, so a fixed non-secret placeholder is sufficient.
    env["LIVE_VAPID_PUBLIC_KEY"] = COMPOSE_INSPECTION_PLACEHOLDER
    env["LIVE_VAPID_PRIVATE_KEY"] = COMPOSE_INSPECTION_PLACEHOLDER
    env["LIVE_MAILPIT_PORT"] = str(MAILPIT_PORT)
    return env


def compose_command(*args: str, project_name: str) -> list[str]:
    _validate_project_name(project_name)
    command = ["docker", "compose", "-p", project_name, "--env-file", ".env.docker"]
    for compose_file in COMPOSE_FILES:
        command += ["-f", compose_file]
    return [*command, *args]


def port_is_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, port))
        except OSError:
            return False
        return True


def require_free_ports(ports: Sequence[int] = PUBLISHED_PORTS) -> None:
    busy = [
        port
        for port in ports
        if not port_is_free(port, host=PORT_BIND_HOSTS.get(port, "127.0.0.1"))
    ]
    if busy:
        raise StandError(
            f"ports {busy} are in use; stop the local stack "
            "(.\\start-docker.ps1 -Down) before starting the stand"
        )


def _run(
    command: Sequence[str], *, cwd: Path, env: dict[str, str] | None = None
) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)  # noqa: S603 - fixed argv


def _git(*args: str) -> str:
    completed = subprocess.run(  # noqa: S603 - fixed git argv
        ["git", *args],  # noqa: S607 - git resolved from PATH like every repo script
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def resolve_stand_ref(ref: str) -> str:
    """Resolve the selected commit and reject refs without the live overlay."""
    try:
        sha = _git("rev-parse", "--verify", f"{ref}^{{commit}}")
        _git("cat-file", "-e", f"{sha}:{OVERLAY}")
    except subprocess.CalledProcessError as error:
        raise StandError(
            f"selected ref {ref!r} is invalid or does not contain {OVERLAY}"
        ) from error
    return sha


def ensure_worktree(ref: str) -> str:
    _assert_no_reparse_ancestors(WORKTREE)
    sha = resolve_stand_ref(ref)
    if WORKTREE.exists():
        _assert_worktree_clean(WORKTREE)
        _git("-C", str(WORKTREE), "checkout", "--detach", sha)
    else:
        _git("worktree", "add", "--detach", str(WORKTREE), sha)
    return sha


def _assert_worktree_clean(worktree: Path) -> None:
    changes = _git("-C", str(worktree), "status", "--porcelain", "--untracked-files=no")
    if changes:
        raise StandError(f"{worktree} has tracked changes; refusing to switch it")


def _require_worktree() -> None:
    _assert_stand_paths_safe(WORKTREE)
    if not (WORKTREE / OVERLAY).is_file():
        raise StandError(f"no stand at {WORKTREE}; run `live_stand.py up` first")
    load_stand_owner(WORKTREE)


def _up_locked(ref: str) -> None:
    _assert_stand_paths_safe(WORKTREE)
    resolved_sha = resolve_stand_ref(ref)
    if WORKTREE.exists():
        if not (WORKTREE / OVERLAY).is_file():
            raise StandError(
                f"path exists but is not an owned live stand worktree: {WORKTREE}"
            )
        owner = load_stand_owner(WORKTREE)
        _assert_worktree_clean(WORKTREE)
        # Stop the stand's own containers (volumes stay) so its ports are free
        # for the port check and the launcher's restart.
        env = stand_environment(load_vapid(WORKTREE), owner.project_name)
        _run(
            compose_command("stop", project_name=owner.project_name),
            cwd=WORKTREE,
            env=env,
        )
        require_free_ports()
    else:
        require_free_ports()
    sha = ensure_worktree(resolved_sha)
    _assert_stand_paths_safe(WORKTREE)
    if not (WORKTREE / STAND_FILE).is_file():
        owner = create_stand_owner(WORKTREE)
        load_or_create_vapid(WORKTREE)
    else:
        owner = load_stand_owner(WORKTREE)
    env = stand_environment(load_vapid(WORKTREE), owner.project_name)
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if powershell is None:
        raise StandError("PowerShell is required to run start-docker.ps1")
    _run(
        [
            powershell,
            "-NoProfile",
            "-File",
            "start-docker.ps1",
            "-Build",
            "-ExtraCompose",
            OVERLAY,
        ],
        cwd=WORKTREE,
        env=env,
    )
    print(f"stand {owner.project_name} is up at https://localhost for {sha}")
    print(f"Mailpit API/UI: http://127.0.0.1:{MAILPIT_PORT}")


def up(ref: str) -> None:
    with stand_lifecycle_lock():
        _up_locked(ref)


def _seed_locked() -> None:
    _require_worktree()
    owner = load_stand_owner(WORKTREE)
    env = stand_environment(load_vapid(WORKTREE), owner.project_name)
    scripts_mount = f"{WORKTREE / 'scripts'}:/app/scripts:ro"
    for script in SEED_SCRIPTS:
        _run(
            compose_command(
                "run",
                "--rm",
                "--no-deps",
                "-v",
                scripts_mount,
                "backend",
                "python",
                script,
                project_name=owner.project_name,
            ),
            cwd=WORKTREE,
            env=env,
        )


def seed() -> None:
    with stand_lifecycle_lock():
        _seed_locked()


def status() -> None:
    _require_worktree()
    owner = load_stand_owner(WORKTREE)
    env = compose_control_environment(owner.project_name)
    _run(compose_command("ps", project_name=owner.project_name), cwd=WORKTREE, env=env)


def _stop_locked() -> None:
    """Stop only this owned stand's containers, preserving all data."""
    _require_worktree()
    owner = load_stand_owner(WORKTREE)
    env = compose_control_environment(owner.project_name)
    _run(
        compose_command("stop", project_name=owner.project_name), cwd=WORKTREE, env=env
    )


def stop() -> None:
    with stand_lifecycle_lock():
        _stop_locked()


def _teardown_locked() -> None:
    """Remove only the owned Compose project and volumes; keep local files."""
    _require_worktree()
    owner = load_stand_owner(WORKTREE)
    env = compose_control_environment(owner.project_name)
    _run(
        compose_command(
            "down", "--volumes", "--remove-orphans", project_name=owner.project_name
        ),
        cwd=WORKTREE,
        env=env,
    )


def teardown() -> None:
    with stand_lifecycle_lock():
        _teardown_locked()


def down() -> None:
    """Compatibility alias for the data-preserving stop command."""
    stop()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    commands = parser.add_subparsers(dest="command", required=True)
    up_parser = commands.add_parser("up")
    up_parser.add_argument("--ref", default="HEAD")
    commands.add_parser("seed")
    commands.add_parser("status")
    commands.add_parser("stop")
    commands.add_parser("down")
    commands.add_parser("teardown")
    args = parser.parse_args(argv)
    try:
        if args.command == "up":
            up(args.ref)
        elif args.command == "seed":
            seed()
        elif args.command == "status":
            status()
        elif args.command in {"stop", "down"}:
            stop()
        elif args.command == "teardown":
            teardown()
        else:
            raise AssertionError(f"unexpected command {args.command}")
    except StandError as error:
        print(f"live_stand: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
