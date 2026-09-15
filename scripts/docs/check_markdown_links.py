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
from pathlib import Path
from urllib.parse import unquote

INLINE_LINK_RE = re.compile(r"\[[^\]]*\]\((?:<(?P<angled>[^>]+)>|(?P<plain>[^\s)]+))")
REFERENCE_LINK_RE = re.compile(
    r"^\s*\[[^\]]+\]:\s*(?:<(?P<angled>[^>]+)>|(?P<plain>\S+))",
    re.MULTILINE,
)
REMOTE_PREFIXES = ("#", "http://", "https://", "mailto:", "tel:", "data:", "file:")
DEFAULT_EXCLUDES = (".agents/", ".opencode/", "docs/audits/archive/")


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


def find_missing(root: Path, documents: list[Path]) -> list[str]:
    missing: list[str] = []
    for document in documents:
        if not document.is_file():
            continue
        relative_name = document.relative_to(root).as_posix()
        if relative_name.startswith(DEFAULT_EXCLUDES):
            continue
        content = document.read_text(encoding="utf-8")
        matches = [
            *INLINE_LINK_RE.finditer(content),
            *REFERENCE_LINK_RE.finditer(content),
        ]
        for match in matches:
            target = match.group("angled") or match.group("plain") or ""
            candidate = _relative_target(document, target, root)
            if candidate is None or candidate.exists():
                continue
            line = content.count("\n", 0, match.start()) + 1
            missing.append(f"{relative_name}:{line} -> {target}")
    return missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
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
    missing = find_missing(root, documents)
    if missing:
        print("broken local Markdown links:", file=sys.stderr)
        print("\n".join(missing), file=sys.stderr)
        return 1
    print(f"checked {len(documents)} Markdown files; no broken local links")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
