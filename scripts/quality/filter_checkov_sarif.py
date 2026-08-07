"""Remove Checkov's inline-suppressed results before SARIF upload.

Checkov reports inline suppressions as ``warning`` entries in SARIF even when
its blocking summary says ``Failed checks: 0``. GitHub Code Scanning treats
those entries as open alerts. This filter removes only results whose SARIF
source snippet (or the corresponding source region) contains a matching
Checkov suppression marker; unsuppressed findings are left untouched.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse

SARIF_SUFFIXES = frozenset({".sarif", ".json"})


def _suppression_pattern(rule_id: str) -> re.Pattern[str]:
    escaped_rule_id = re.escape(rule_id)
    return re.compile(
        rf"(?:checkov\s*:\s*skip\s*=\s*{escaped_rule_id}(?:[:\s]|$)"
        rf"|checkov\.io/skip\d+\s*:\s*{escaped_rule_id}(?:=|\s|$))",
        re.IGNORECASE,
    )


def _relative_source_path(uri: object) -> Path | None:
    if not isinstance(uri, str) or not uri:
        return None

    parsed = urlparse(unquote(uri))
    raw_path = parsed.path
    path = PurePosixPath(raw_path.replace("\\", "/").lstrip("/"))
    if not path.parts or ".." in path.parts:
        return None
    return Path(*path.parts)


def _region_text(location: object, repository_root: Path) -> str:
    if not isinstance(location, dict):
        return ""
    physical = location.get("physicalLocation")
    if not isinstance(physical, dict):
        return ""
    region = physical.get("region")
    if not isinstance(region, dict):
        return ""

    region_texts: list[str] = []
    snippet = region.get("snippet")
    if isinstance(snippet, dict) and isinstance(snippet.get("text"), str):
        region_texts.append(snippet["text"])

    artifact = physical.get("artifactLocation")
    if not isinstance(artifact, dict):
        return "\n".join(region_texts)
    source_path = _relative_source_path(artifact.get("uri"))
    if source_path is None:
        return "\n".join(region_texts)

    source_file = (repository_root / source_path).resolve()
    root = repository_root.resolve()
    if not source_file.is_relative_to(root) or not source_file.is_file():
        return "\n".join(region_texts)

    try:
        source_lines = source_file.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return "\n".join(region_texts)

    start_line = region.get("startLine", 1)
    end_line = region.get("endLine", start_line)
    if not isinstance(start_line, int) or not isinstance(end_line, int):
        return "\n".join(region_texts)
    start_index = max(start_line - 1, 0)
    end_index = min(max(end_line, start_line), len(source_lines))
    region_texts.append("\n".join(source_lines[start_index:end_index]))
    return "\n".join(region_texts)


def _result_is_suppressed(result: object, repository_root: Path) -> bool:
    if not isinstance(result, dict):
        return False
    rule_id = result.get("ruleId")
    if not isinstance(rule_id, str) or not rule_id:
        return False

    pattern = _suppression_pattern(rule_id)
    locations = result.get("locations", ())
    if not isinstance(locations, list):
        return False
    return any(
        pattern.search(_region_text(location, repository_root))
        for location in locations
    )


def filter_suppressed_results(
    sarif_document: dict[str, object], repository_root: Path
) -> int:
    """Remove only source-backed, matching Checkov-suppressed SARIF results."""

    removed = 0
    runs = sarif_document.get("runs", ())
    if not isinstance(runs, list):
        return removed

    for run in runs:
        if not isinstance(run, dict):
            continue
        results = run.get("results", ())
        if not isinstance(results, list):
            continue
        kept_results = []
        for result in results:
            if _result_is_suppressed(result, repository_root):
                removed += 1
            else:
                kept_results.append(result)
        run["results"] = kept_results
    return removed


def _sarif_files(path: Path) -> Iterator[Path]:
    if path.is_file() and path.suffix.lower() in SARIF_SUFFIXES:
        yield path
    elif path.is_dir():
        yield from sorted(
            candidate
            for candidate in path.rglob("*")
            if candidate.is_file() and candidate.suffix.lower() in SARIF_SUFFIXES
        )


def _filter_file(path: Path, repository_root: Path) -> int:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"SARIF root must be an object: {path}")
    removed = filter_suppressed_results(document, repository_root)
    if removed:
        path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sarif_path", type=Path)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path.cwd(),
    )
    args = parser.parse_args()

    files = tuple(_sarif_files(args.sarif_path))
    if not files:
        print(f"No SARIF files found under {args.sarif_path}; nothing to filter.")
        return 0

    removed = sum(_filter_file(path, args.repository_root.resolve()) for path in files)
    print(f"Removed {removed} source-backed suppressed Checkov SARIF results.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
