"""Fail-closed check for relative links in Markdown files.

Every relative inline, reference-style or HTML ``href``/``src`` link must reach
a tracked repository path. A ``#fragment`` pointing into a Markdown document
must name one of its headings (GitHub slug rules, Cyrillic included) or an
explicit HTML anchor. URL reachability belongs to the documentation host; this
check stays deterministic and offline.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from collections.abc import Iterator
from html import unescape
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

# Vendored agent skill catalogs mirror upstream content, not project docs.
VENDORED_PREFIXES = (".agents/skills/",)
ARCHIVE_PREFIX = "docs/audits/archive/"
# Dated evidence is never rewritten: only file targets are checked there, as a
# heading anchor may legitimately describe a report's past layout.
ANCHOR_EXEMPT_PREFIXES = ("docs/audits/", "docs/superpowers/plans/archive/")
REMOTE_PREFIXES = (
    "http://",
    "https://",
    "mailto:",
    "tel:",
    "data:",
    "file:",
    "ftp://",
    "vscode://",
)

FENCE_OPEN_RE = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})")
FENCE_CLOSE_RE = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})[ \t]*$")
CODE_SPAN_RE = re.compile(r"(?P<ticks>`+)(?:(?!(?P=ticks)).)+?(?P=ticks)", re.DOTALL)
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
INLINE_LINK_RE = re.compile(
    r"\[(?:[^\[\]]|\[[^\[\]]*\])*\]\(\s*(?:<(?P<angled>[^>\n]+)>|(?P<plain>[^\s()]+))"
)
REFERENCE_LINK_RE = re.compile(
    r"^ {0,3}\[[^\]]+\]:\s*(?:<(?P<angled>[^>\n]+)>|(?P<plain>\S+))",
    re.MULTILINE,
)
HTML_LINK_RE = re.compile(
    r"<(?:a|img|source)\b[^>]*?\b(?:href|src)\s*=\s*[\"'](?P<plain>[^\"']+)[\"']",
    re.IGNORECASE,
)
ATX_HEADING_RE = re.compile(r"^ {0,3}#{1,6}(?:[ \t]+(?P<text>.*?))?[ \t]*$")
ATX_CLOSING_RE = re.compile(r"(?:^|[ \t]+)#+[ \t]*$")
SETEXT_UNDERLINE_RE = re.compile(r"^ {0,3}(?:=+|-+)[ \t]*$")
NOT_SETEXT_TEXT_RE = re.compile(r"^\s*(?:[|*+>-]|<|\d+[.)]\s)")
HTML_ANCHOR_RE = re.compile(
    r"<[a-z][^>]*?\b(?:id|name)\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE
)
LINK_TEXT_RE = re.compile(r"!?\[((?:[^\[\]]|\[[^\[\]]*\])*)\]\([^)]*\)")
HTML_TAG_RE = re.compile(r"<[^>]+>")
UNDERSCORE_EMPHASIS_RE = re.compile(r"(?<!\w)_{1,2}(?=\S)(.+?)(?<=\S)_{1,2}(?!\w)")
LINE_SUFFIX_RE = re.compile(r":\d+(?:-\d+)?$")


def _git_lines(root: Path, *arguments: str) -> list[str] | None:
    git = shutil.which("git")
    if git is None:
        return None
    try:
        result = subprocess.run(  # noqa: S603 - executable resolved with shutil.which
            [git, "ls-files", "-z", *arguments],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return [name for name in result.stdout.split("\0") if name]


def tracked_markdown(root: Path) -> list[Path]:
    """Tracked Markdown documents, or every ``*.md`` file without Git."""
    names = _git_lines(root, "--", "*.md")
    if names is None:
        return sorted(root.rglob("*.md"))
    return [root / name for name in names]


def tracked_targets(root: Path) -> set[str] | None:
    """Tracked files and their parent directories, or ``None`` without Git."""
    names = _git_lines(root)
    if names is None:
        return None
    targets: set[str] = set()
    for name in names:
        path = PurePosixPath(name)
        targets.add(path.as_posix())
        targets.update(parent.as_posix() for parent in path.parents)
    return targets


def _prose_lines(content: str) -> Iterator[tuple[int, str]]:
    """Yield ``(line number, line)`` for every line outside fenced code."""
    fence: str | None = None
    for number, line in enumerate(content.splitlines(), start=1):
        if fence is None:
            opening = FENCE_OPEN_RE.match(line)
            if opening:
                fence = opening.group("fence")
                continue
            yield number, line
            continue
        closing = FENCE_CLOSE_RE.match(line)
        if closing and closing.group("fence").startswith(fence):
            fence = None


def _blank(match: re.Match[str]) -> str:
    return re.sub(r"[^\n]", " ", match.group(0))


def _mask_code(content: str) -> str:
    """Blank code fences, code spans and comments, preserving line numbers."""
    lines = [""] * (content.count("\n") + 1)
    for number, line in _prose_lines(content):
        lines[number - 1] = line
    prose = HTML_COMMENT_RE.sub(_blank, "\n".join(lines))
    return CODE_SPAN_RE.sub(_blank, prose)


def github_slug(heading: str) -> str:
    """Reproduce GitHub's anchor slug for the rendered text of a heading."""
    text = LINK_TEXT_RE.sub(r"\1", heading).replace("`", "")
    text = UNDERSCORE_EMPHASIS_RE.sub(r"\1", HTML_TAG_RE.sub("", text))
    text = re.sub(r"[^\w\- ]", "", unescape(text).strip().lower())
    return text.replace(" ", "-")


def heading_anchors(content: str) -> set[str]:
    """Anchors GitHub renders for a document: heading slugs and HTML ids."""
    lines = dict(_prose_lines(content))
    if content.startswith("---\n"):
        # YAML front matter renders as a table, never as a setext heading.
        closing_line = content.count("\n", 0, content.find("\n---", 4)) + 2
        for number in range(1, closing_line + 1):
            lines.pop(number, None)
    anchors: set[str] = set()
    seen: dict[str, int] = {}
    for number, line in sorted(lines.items()):
        atx = ATX_HEADING_RE.match(line)
        if atx:
            heading = ATX_CLOSING_RE.sub("", atx.group("text") or "")
        elif (
            line.strip()
            and SETEXT_UNDERLINE_RE.match(lines.get(number + 1, "x"))
            and not lines.get(number - 1, "").strip()
            and not NOT_SETEXT_TEXT_RE.match(line)
        ):
            heading = line.strip()
        else:
            continue
        slug = github_slug(heading)
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        anchors.add(slug if count == 0 else f"{slug}-{count}")
    anchors.update(HTML_ANCHOR_RE.findall(_mask_code(content)))
    return anchors


def _links(content: str) -> Iterator[tuple[int, str]]:
    scan_content = _mask_code(content)
    for pattern in (INLINE_LINK_RE, REFERENCE_LINK_RE, HTML_LINK_RE):
        for match in pattern.finditer(scan_content):
            groups = match.groupdict()
            target = (groups.get("angled") or groups.get("plain") or "").strip()
            if target:
                yield scan_content.count("\n", 0, match.start()) + 1, target


def _target_path(document: Path, target: str, root: Path) -> Path | None:
    """Resolve a link's file part, or ``None`` for remote and same-page links."""
    if target.lower().startswith(REMOTE_PREFIXES):
        return None
    path_text = unquote(target.split("#", maxsplit=1)[0].split("?", maxsplit=1)[0])
    path_text = LINE_SUFFIX_RE.sub("", path_text)
    if not path_text:
        return document
    return (
        (root / path_text.lstrip("/"))
        if path_text.startswith("/")
        else document.parent / path_text
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
    """Return ``document:line -> target`` for every unresolved relative link."""
    missing: list[str] = []
    anchors: dict[Path, set[str]] = {}
    for document in documents:
        if not document.is_file():
            continue
        relative_name = document.relative_to(root).as_posix()
        if relative_name.startswith(VENDORED_PREFIXES):
            continue
        if not include_archives and relative_name.startswith(ARCHIVE_PREFIX):
            continue
        content = document.read_text(encoding="utf-8")
        for line, target in _links(content):
            candidate = _target_path(document, target, root)
            if candidate is None:
                continue
            if not _resolves(candidate, root, tracked):
                missing.append(f"{relative_name}:{line} -> {target}")
                continue
            fragment = unquote(target.partition("#")[2])
            if (
                not fragment
                or candidate.suffix.lower() != ".md"
                or not candidate.is_file()
                or relative_name.startswith(ANCHOR_EXEMPT_PREFIXES)
            ):
                continue
            key = candidate.resolve()
            if key not in anchors:
                anchors[key] = heading_anchors(candidate.read_text(encoding="utf-8"))
            if fragment not in anchors[key]:
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
        documents = tracked_markdown(root)
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
