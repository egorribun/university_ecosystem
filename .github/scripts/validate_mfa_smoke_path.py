"""Resolve a reviewed MFA rotation smoke script from the deployed commit."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from shutil import which


def fail(message: str) -> None:
    print(f"::error::{message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    candidate = sys.argv[1] if len(sys.argv) == 2 else ""
    if not candidate.strip():
        fail("MFA_OVERLAP_SMOKE_SCRIPT is required for MFA key rotation.")

    workspace_raw = os.environ.get("GITHUB_WORKSPACE", "")
    if not workspace_raw:
        fail("GITHUB_WORKSPACE is required to validate the smoke script.")
    try:
        workspace = Path(workspace_raw).resolve(strict=True)
        allowed_root = (workspace / ".github" / "deployment-smoke").resolve(strict=True)
        raw_path = Path(candidate)
        candidate_path = raw_path if raw_path.is_absolute() else workspace / raw_path
        if candidate_path.is_symlink():
            fail("MFA_OVERLAP_SMOKE_SCRIPT must not be a symbolic link.")
        target = candidate_path.resolve(strict=True)
    except OSError:
        fail("MFA_OVERLAP_SMOKE_SCRIPT does not identify an existing file.")
    try:
        relative = target.relative_to(allowed_root)
    except ValueError:
        fail("MFA_OVERLAP_SMOKE_SCRIPT must stay under .github/deployment-smoke/.")
    if not relative.parts or not target.is_file():
        fail("MFA_OVERLAP_SMOKE_SCRIPT must identify a regular file.")

    git = which("git")
    if git is None:
        fail("git is required to validate the reviewed smoke script.")
    repository_relative = target.relative_to(workspace).as_posix()
    tracked = subprocess.run(  # noqa: S603 - fixed Git verification
        [git, "-C", str(workspace), "cat-file", "-e", f"HEAD:{repository_relative}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if tracked.returncode != 0:
        fail("MFA_OVERLAP_SMOKE_SCRIPT must be tracked in the deployed commit.")
    head_hash = subprocess.run(  # noqa: S603 - fixed Git verification
        [git, "-C", str(workspace), "rev-parse", f"HEAD:{repository_relative}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    worktree_hash = subprocess.run(  # noqa: S603 - fixed Git verification
        [git, "-C", str(workspace), "hash-object", str(target)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if not head_hash or head_hash != worktree_hash:
        fail("MFA_OVERLAP_SMOKE_SCRIPT differs from the reviewed deployed commit.")
    print(target)


if __name__ == "__main__":
    main()
