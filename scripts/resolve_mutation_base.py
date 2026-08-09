#!/usr/bin/env python3
"""Resolve the immutable comparison base for the incremental mutation gate."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess  # nosec B404
from collections.abc import Sequence
from pathlib import Path

# Git invocations below use a fixed executable, validate every revision, and
# never invoke a shell.
_FULL_SHA = re.compile(r"^[0-9a-fA-F]{40}$")


def _git_executable() -> str:
    executable = shutil.which("git")
    if executable is None:
        raise RuntimeError("git executable is unavailable")
    return executable


def _git(repository: Path, *arguments: str) -> str:
    # The fixed git executable receives a list of non-shell-expanded arguments.
    result = subprocess.run(  # noqa: S603  # nosec B603
        [_git_executable(), "-C", str(repository), *arguments],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ValueError(f"git {' '.join(arguments[:2])} failed: {detail}")
    return result.stdout.strip()


def _resolve_commit_sha(repository: Path, value: str, *, label: str) -> str:
    if not _FULL_SHA.fullmatch(value):
        raise ValueError(f"{label} must be a full 40-character commit SHA")
    if _git(repository, "cat-file", "-t", value) != "commit":
        raise ValueError(f"{label} must identify a commit object")
    return _git(repository, "rev-parse", "--verify", value)


def _require_strict_ancestor(repository: Path, base: str) -> None:
    head = _git(repository, "rev-parse", "--verify", "HEAD^{commit}")
    if base == head:
        raise ValueError("manual mutation base must be a strict ancestor of HEAD")

    # The fixed git executable receives two verified commit revisions.
    result = subprocess.run(  # noqa: S603  # nosec B603
        [
            _git_executable(),
            "-C",
            str(repository),
            "merge-base",
            "--is-ancestor",
            base,
            head,
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode == 1:
        raise ValueError("manual mutation base must be an ancestor of HEAD")
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ValueError(f"git merge-base failed: {detail}")


def resolve_mutation_base(
    *,
    repository: Path,
    event_name: str,
    pr_base_sha: str,
    manual_base_sha: str,
) -> str:
    """Return a canonical comparison commit without weakening PR semantics."""

    if pr_base_sha:
        return _resolve_commit_sha(
            repository,
            pr_base_sha,
            label="pull-request mutation base",
        )

    if event_name == "workflow_dispatch":
        if not manual_base_sha:
            raise ValueError(
                "workflow_dispatch requires a full strict-ancestor manual mutation base"
            )
        base = _resolve_commit_sha(
            repository,
            manual_base_sha,
            label="manual mutation base",
        )
        _require_strict_ancestor(repository, base)
        return base

    if manual_base_sha:
        raise ValueError("manual mutation base is valid only for workflow_dispatch")

    return _git(repository, "rev-parse", "--verify", "origin/main^{commit}")


def _parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--pr-base-sha", default="")
    parser.add_argument("--manual-base-sha", default="")
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> None:
    args = _parse_args(arguments)
    print(
        resolve_mutation_base(
            repository=args.repository,
            event_name=args.event_name,
            pr_base_sha=args.pr_base_sha,
            manual_base_sha=args.manual_base_sha,
        )
    )


if __name__ == "__main__":
    main()
