"""Owned live acceptance stand: a dedicated worktree running the full stack.

The stand runs from ``../ue-live`` (a detached git worktree of this
repository), so its Compose project, volumes, networks, ``.env*`` files and
secrets are separate from the developer's own stack.  It adds Mailpit and
locally generated VAPID keys through ``docker-compose.live.yml``.

Usage::

    python scripts/live_stand.py up [--ref HEAD]   # create/refresh the worktree and start
    python scripts/live_stand.py seed               # load demo users and content
    python scripts/live_stand.py status
    python scripts/live_stand.py down               # remove the stand's containers,
                                                    # volumes and worktree

``down`` only ever removes the ``ue-live`` Compose project and the
``../ue-live`` worktree.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import socket
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT = "ue-live"
WORKTREE = REPO_ROOT.parent / PROJECT
OVERLAY = "docker-compose.live.yml"
COMPOSE_FILES = ("docker-compose.full.yml", OVERLAY)
PUBLISHED_PORTS = (80, 443)
MAILPIT_PORT = 18025
VAPID_FILE = Path(".secrets") / "live-vapid.json"
SEED_SCRIPTS = ("scripts/seed_demo_data.py", "scripts/seed_admin_data.py")


class StandError(RuntimeError):
    """A precondition for operating the stand does not hold."""


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


def load_or_create_vapid(worktree: Path) -> dict[str, str]:
    path = worktree / VAPID_FILE
    if path.is_file():
        keys = json.loads(path.read_text(encoding="utf-8"))
        if set(keys) != {"public", "private"}:
            raise StandError(f"{path} does not hold a VAPID key pair")
        return {"public": str(keys["public"]), "private": str(keys["private"])}
    keys = generate_vapid_keys()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(keys), encoding="utf-8")
    return keys


def stand_environment(keys: dict[str, str]) -> dict[str, str]:
    env = os.environ.copy()
    env["COMPOSE_PROJECT_NAME"] = PROJECT
    env["LIVE_VAPID_PUBLIC_KEY"] = keys["public"]
    env["LIVE_VAPID_PRIVATE_KEY"] = keys["private"]
    env["LIVE_MAILPIT_PORT"] = str(MAILPIT_PORT)
    return env


def compose_command(*args: str) -> list[str]:
    command = ["docker", "compose", "-p", PROJECT, "--env-file", ".env.docker"]
    for compose_file in COMPOSE_FILES:
        command += ["-f", compose_file]
    return [*command, *args]


def port_is_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        return probe.connect_ex((host, port)) != 0


def require_free_ports(ports: Sequence[int] = PUBLISHED_PORTS) -> None:
    busy = [port for port in ports if not port_is_free(port)]
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


def ensure_worktree(ref: str) -> str:
    sha = _git("rev-parse", "--verify", f"{ref}^{{commit}}")
    if WORKTREE.exists():
        if _git("-C", str(WORKTREE), "status", "--porcelain", "--untracked-files=no"):
            raise StandError(f"{WORKTREE} has tracked changes; refusing to switch it")
        _git("-C", str(WORKTREE), "checkout", "--detach", sha)
    else:
        _git("worktree", "add", "--detach", str(WORKTREE), sha)
    return sha


def _require_worktree() -> None:
    if not (WORKTREE / OVERLAY).is_file():
        raise StandError(f"no stand at {WORKTREE}; run `live_stand.py up` first")


def up(ref: str) -> None:
    if (WORKTREE / OVERLAY).is_file():
        # Stop the stand's own containers (volumes stay) so its ports are free
        # and the launcher's storage guard does not see a running SeaweedFS
        # container and refuse the restart as a silent MinIO rollback.
        env = stand_environment(load_or_create_vapid(WORKTREE))
        _run(compose_command("down", "--remove-orphans"), cwd=WORKTREE, env=env)
    require_free_ports()
    sha = ensure_worktree(ref)
    env = stand_environment(load_or_create_vapid(WORKTREE))
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
    print(f"stand {PROJECT} is up at https://localhost for {sha}")
    print(f"Mailpit API/UI: http://127.0.0.1:{MAILPIT_PORT}")


def seed() -> None:
    _require_worktree()
    env = stand_environment(load_or_create_vapid(WORKTREE))
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
            ),
            cwd=WORKTREE,
            env=env,
        )


def status() -> None:
    _require_worktree()
    env = stand_environment(load_or_create_vapid(WORKTREE))
    _run(compose_command("ps"), cwd=WORKTREE, env=env)


def down() -> None:
    if WORKTREE.name != PROJECT or WORKTREE.parent != REPO_ROOT.parent:
        raise StandError(f"refusing to remove unexpected path {WORKTREE}")
    if (WORKTREE / OVERLAY).is_file():
        env = stand_environment(load_or_create_vapid(WORKTREE))
        _run(
            compose_command("down", "--volumes", "--remove-orphans"),
            cwd=WORKTREE,
            env=env,
        )
    if WORKTREE.exists():
        _git("worktree", "remove", "--force", str(WORKTREE))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    commands = parser.add_subparsers(dest="command", required=True)
    up_parser = commands.add_parser("up")
    up_parser.add_argument("--ref", default="HEAD")
    commands.add_parser("seed")
    commands.add_parser("status")
    commands.add_parser("down")
    args = parser.parse_args(argv)
    try:
        if args.command == "up":
            up(args.ref)
        elif args.command == "seed":
            seed()
        elif args.command == "status":
            status()
        else:
            down()
    except StandError as error:
        print(f"live_stand: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
