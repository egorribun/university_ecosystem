"""Fail-closed check for relative links in Markdown files.

This intentionally validates file targets only. URL reachability and fragment
semantics belong to the documentation host; a local check must stay
deterministic and offline-friendly.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

INLINE_LINK_RE = re.compile(r"\[[^\]]*\]\((?:<(?P<angled>[^>]+)>|(?P<plain>[^\s)]+))")
REFERENCE_LINK_RE = re.compile(
    r"^\s*\[[^\]]+\]:\s*(?:<(?P<angled>[^>]+)>|(?P<plain>\S+))",
    re.MULTILINE,
)
FENCED_CODE_RE = re.compile(r"(?ms)^ {0,3}```.*?^ {0,3}```")
INLINE_CODE_RE = re.compile(r"`+[^`\n]*`+")
REMOTE_PREFIXES = ("#", "http://", "https://", "mailto:", "tel:", "data:", "file:")


def _mask_code(content: str) -> str:
    """Replace code spans/fences with spaces while preserving offsets and lines."""

    masked = list(content)
    for pattern in (FENCED_CODE_RE, INLINE_CODE_RE):
        for match in pattern.finditer(content):
            for index in range(match.start(), match.end()):
                if masked[index] != "\n":
                    masked[index] = " "
    return "".join(masked)


def _tracked_markdown(root: Path) -> list[Path]:
    git = shutil.which("git")
    if git is None:
        return sorted(root.rglob("*.md"))
    try:
        result = subprocess.run(  # noqa: S603 - executable resolved with shutil.which
            [git, "ls-files", "--", "*.md"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return sorted(root.rglob("*.md"))
    return [root / line for line in result.stdout.splitlines() if line]


def tracked_targets(root: Path) -> set[str] | None:
    """Tracked files and their parent directories, or ``None`` without Git."""
    git = shutil.which("git")
    if git is None:
        return None
    try:
        result = subprocess.run(  # noqa: S603 - executable resolved with shutil.which
            [git, "ls-files"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    targets: set[str] = set()
    for line in result.stdout.splitlines():
        path = PurePosixPath(line)
        targets.add(path.as_posix())
        targets.update(parent.as_posix() for parent in path.parents)
    return targets


def _relative_target(document: Path, target: str, root: Path) -> Path | None:
    target = unquote(target.split("#", maxsplit=1)[0])
    target = re.sub(r":\d+(?:-\d+)?$", "", target)
    if not target or target.startswith(REMOTE_PREFIXES):
        return None
    return (
        (root / target.lstrip("/"))
        if target.startswith("/")
        else document.parent / target
    )


def _resolves(candidate: Path, root: Path, tracked: set[str] | None) -> bool:
    if tracked is None:
        return candidate.exists()
    # An untracked local file exists on disk yet is absent from every checkout.
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root.resolve()):
        return False
    return resolved.relative_to(root.resolve()).as_posix() in tracked


def find_missing(
    root: Path,
    documents: list[Path],
    *,
    include_archives: bool = False,
    tracked: set[str] | None = None,
) -> list[str]:
    missing: list[str] = []
    for document in documents:
        if not document.is_file():
            continue
        relative_name = document.relative_to(root).as_posix()
        if relative_name.startswith((".agents/", ".opencode/")):
            continue
        if not include_archives and relative_name.startswith("docs/audits/archive/"):
            continue
        content = document.read_text(encoding="utf-8")
        scan_content = _mask_code(content)
        matches = [
            *INLINE_LINK_RE.finditer(scan_content),
            *REFERENCE_LINK_RE.finditer(scan_content),
        ]
        for match in matches:
            target = match.group("angled") or match.group("plain") or ""
            candidate = _relative_target(document, target, root)
            if candidate is None or _resolves(candidate, root, tracked):
                continue
            line = content.count("\n", 0, match.start()) + 1
            missing.append(f"{relative_name}:{line} -> {target}")
    return missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--include-archives",
        action="store_true",
        help="include immutable historical audit files in the check",
    )
    parser.add_argument(
        "paths", nargs="*", help="Markdown files or directories to check"
    )
    args = parser.parse_args()
    root = args.root.resolve()
    if args.paths:
        documents = []
        for value in args.paths:
            path = (root / value).resolve()
            documents.extend(sorted(path.rglob("*.md")) if path.is_dir() else [path])
    else:
        documents = _tracked_markdown(root)
    missing = find_missing(
        root,
        documents,
        include_archives=args.include_archives,
        tracked=tracked_targets(root),
    )
    if missing:
        print("broken local Markdown links:", file=sys.stderr)
        print("\n".join(missing), file=sys.stderr)
        return 1
    print(f"checked {len(documents)} Markdown files; no broken local links")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
