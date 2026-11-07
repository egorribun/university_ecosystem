#!/usr/bin/env python3
"""Fail-closed gate for Semgrep findings against exact reviewed dispositions (AUD-380).

A finding must match its rule id, repository path and complete start-line
digest. Multi-line matches also bind every line in the reported span; single-line
matches require an explicitly reviewed, wider source context. Range digests use
UTF-8 lines joined by LF, with no final line ending. Each disposition explicitly
declares companion source files and their byte-exact SHA-256 digests; the React
HTML sink rule requires at least one. The gate also refuses stale, expired,
ambiguous or malformed records and incomplete scanner evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DISPOSITIONS = REPOSITORY_ROOT / "quality" / "semgrep-dispositions.json"
DISPOSITION_FIELDS = frozenset(
    {
        "check_id",
        "path",
        "line_sha256",
        "reason",
        "owner",
        "approved",
        "expires",
        "companions",
    }
)
_SHA256_HEX = re.compile(r"[0-9a-f]{64}")
_REACT_HTML_SINK_CHECK_ID = (
    "typescript.react.security.audit.react-dangerouslysetinnerhtml."
    "react-dangerouslysetinnerhtml"
)
_REVIEWED_SEMGREP_IGNORE_PATTERNS = (
    "alembic/versions/",
    "tests/",
    "native/rust_ext/fuzz/",
    "**/*_test.go",
    "frontend/coverage-*/",
    "frontend/coverage/",
    "frontend/src/tests/mocks/generated/",
    "frontend/openapi.json",
    "frontend/src/routeTree.gen.ts",
    "app/static/quarantine/",
    "app/test-static/",
    ".agents/",
)

Key = tuple[str, str, str]


@dataclass(frozen=True)
class ReviewedContext:
    start_line: int
    end_line: int
    sha256: str


@dataclass(frozen=True)
class ReviewedCompanion:
    path: str
    sha256: str


@dataclass(frozen=True)
class Evidence:
    span_sha256: str | None = None
    context: ReviewedContext | None = None
    companions: tuple[ReviewedCompanion, ...] = ()


@dataclass(frozen=True)
class Finding:
    start_line: int
    end_line: int
    span_sha256: str
    source_lines: list[str]


class GateError(ValueError):
    """Raised when the gate cannot make a trustworthy decision."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise GateError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_json(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GateError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise GateError(f"JSON root must be an object: {path}")
    return loaded


def normalize_path(raw: object) -> str:
    """Return a canonical repository-relative POSIX path or fail closed."""

    if not isinstance(raw, str) or not raw.strip():
        raise GateError("path must be a non-empty string")
    text = raw.replace("\\", "/")
    if text.startswith("./"):
        text = text[2:]
    candidate = PurePosixPath(text)
    if (
        candidate.is_absolute()
        or PureWindowsPath(text).drive
        or ".." in candidate.parts
        or any(character in text for character in "*?\x00")
    ):
        raise GateError(f"path is not a canonical repository path: {raw!r}")
    return candidate.as_posix()


def _text_field(entry: dict[str, Any], field: str) -> str:
    value = entry.get(field)
    if not isinstance(value, str) or not value.strip():
        raise GateError(f"disposition field {field} must be a non-empty string")
    return value


def _date_field(entry: dict[str, Any], field: str) -> date:
    try:
        return date.fromisoformat(_text_field(entry, field))
    except ValueError as exc:
        raise GateError(f"disposition field {field} is not an ISO date") from exc


def _digest_field(entry: dict[str, Any], field: str) -> str:
    digest = _text_field(entry, field)
    if not _SHA256_HEX.fullmatch(digest):
        raise GateError(f"disposition {field} must be 64 lowercase hex digits")
    return digest


def _companions(
    entry: dict[str, Any], check_id: str, source: str
) -> tuple[ReviewedCompanion, ...]:
    raw = entry["companions"]
    if not isinstance(raw, list):
        raise GateError("disposition companions must be a list")
    if check_id == _REACT_HTML_SINK_CHECK_ID and not raw:
        raise GateError("React HTML sink requires companion evidence")
    seen: set[str] = set()
    companions = []
    for item in raw:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise GateError("each companion must contain exactly path and sha256")
        path = normalize_path(item["path"])
        if path != item["path"] or path == source:
            raise GateError(
                "companion path must be canonical and distinct from the finding"
            )
        if path in seen:
            raise GateError(f"duplicate companion path: {path}")
        seen.add(path)
        companions.append(ReviewedCompanion(path, _digest_field(item, "sha256")))
    return tuple(companions)


def _evidence(
    entry: dict[str, Any], companions: tuple[ReviewedCompanion, ...]
) -> Evidence:
    if "span_sha256" in entry:
        return Evidence(
            span_sha256=_digest_field(entry, "span_sha256"), companions=companions
        )
    raw = entry["context"]
    if not isinstance(raw, dict) or set(raw) != {"start_line", "end_line", "sha256"}:
        raise GateError(
            "disposition context must contain exactly start_line, end_line and sha256"
        )
    start, end = raw["start_line"], raw["end_line"]
    if (
        not isinstance(start, int)
        or isinstance(start, bool)
        or not isinstance(end, int)
        or isinstance(end, bool)
        or start < 1
        or end <= start
    ):
        raise GateError("disposition context must be a positive, multi-line range")
    return Evidence(
        context=ReviewedContext(start, end, _digest_field(raw, "sha256")),
        companions=companions,
    )


def load_dispositions(path: Path, today: date) -> dict[Key, Evidence]:
    """Load exact dispositions; refuse malformed, duplicate or expired entries."""

    loaded = _read_json(path)
    if set(loaded) != {"dispositions"} or not isinstance(loaded["dispositions"], list):
        raise GateError("dispositions file must contain exactly a dispositions list")
    keys: dict[Key, Evidence] = {}
    expired: list[str] = []
    for entry in loaded["dispositions"]:
        if not isinstance(entry, dict) or set(entry) not in (
            DISPOSITION_FIELDS | {"span_sha256"},
            DISPOSITION_FIELDS | {"context"},
        ):
            raise GateError("each disposition must contain exactly the required fields")
        check_id = _text_field(entry, "check_id")
        if check_id != check_id.strip() or any(c in check_id for c in "*?[]"):
            raise GateError("disposition must specify an exact check_id")
        repository_path = normalize_path(entry["path"])
        _text_field(entry, "reason")
        _text_field(entry, "owner")
        approved = _date_field(entry, "approved")
        expires = _date_field(entry, "expires")
        if approved > expires:
            raise GateError(f"disposition for {check_id} approved after it expires")
        if approved > today:
            raise GateError(f"disposition for {check_id} approval is in the future")
        digest = _digest_field(entry, "line_sha256")
        key: Key = (check_id, repository_path, digest)
        if key in keys:
            raise GateError(f"duplicate disposition: {check_id} {repository_path}")
        keys[key] = _evidence(entry, _companions(entry, check_id, repository_path))
        if today > expires:
            expired.append(f"{check_id} {repository_path}")
    if expired:
        raise GateError("expired dispositions: " + "; ".join(sorted(expired)))
    return keys


def _repository_path(root: Path, repository_path: str, subject: str) -> Path:
    source = root / repository_path
    try:
        resolved = source.resolve()
    except (OSError, RuntimeError) as exc:
        raise GateError(
            f"{subject} path cannot be resolved: {repository_path}"
        ) from exc
    if resolved == root:
        raise GateError(f"{subject} path must not be the repository root")
    if not resolved.is_relative_to(root):
        raise GateError(
            f"{subject} path resolves outside the repository: {repository_path}"
        )
    current = root
    for part in PurePosixPath(repository_path).parts:
        current = current / part
        if current.is_symlink() or current.is_junction():
            raise GateError(f"{subject} path contains a symlink: {repository_path}")
    return resolved


def _repository_file(root: Path, repository_path: str, subject: str) -> Path:
    source = _repository_path(root, repository_path, subject)
    if not source.is_file():
        raise GateError(f"{subject} path is not a repository file: {repository_path}")
    return source


def _repository_ignored_target(root: Path, repository_path: str) -> Path:
    """Validate a reviewed ignored target as a file or directory under root."""

    source = _repository_path(root, repository_path, "Semgrep skipped target")
    if not source.is_file() and not source.is_dir():
        raise GateError(
            "Semgrep skipped target path is not a regular repository file or "
            f"directory: {repository_path}"
        )
    return source


def _matches_reviewed_semgrep_ignore(repository_path: str) -> bool:
    """Return whether a normalized path matches the exact reviewed ignore set."""

    parts = PurePosixPath(repository_path).parts
    prefixes = tuple("/".join(parts[:index]) for index in range(1, len(parts) + 1))
    for pattern in _REVIEWED_SEMGREP_IGNORE_PATTERNS:
        if pattern == "**/*_test.go":
            if fnmatchcase(repository_path, pattern) or fnmatchcase(
                PurePosixPath(repository_path).name, "*_test.go"
            ):
                return True
        elif pattern.endswith("/"):
            directory_pattern = pattern[:-1]
            if "/" not in directory_pattern:
                if directory_pattern in parts:
                    return True
            elif any(fnmatchcase(prefix, directory_pattern) for prefix in prefixes):
                return True
        elif fnmatchcase(repository_path, pattern):
            return True
    return False


def _fixpoint_timeout_details(timeouts: list[Any]) -> str:
    """Expose bounded source coordinates, never scanner messages or source text."""
    details: list[dict[str, str | int]] = []
    for entry in timeouts[:8]:
        detail: dict[str, str | int] = {}
        if isinstance(entry, dict):
            rule_id = entry.get("rule_id")
            if isinstance(rule_id, str) and re.fullmatch(
                r"[A-Za-z0-9_.-]{1,200}", rule_id
            ):
                detail["rule_id"] = rule_id
            location = entry.get("location")
            if isinstance(location, dict):
                path = location.get("path")
                if isinstance(path, str) and re.fullmatch(
                    r"[A-Za-z0-9_./-]{1,240}", path
                ):
                    try:
                        detail["path"] = normalize_path(path)
                    except GateError:
                        pass
                start = location.get("start")
                line = start.get("line") if isinstance(start, dict) else None
                if type(line) is int and 0 < line <= 1_000_000_000:
                    detail["line"] = line
        details.append(detail)
    summary = {"details": details, "omitted": max(0, len(timeouts) - len(details))}
    return json.dumps(summary, ensure_ascii=True, separators=(",", ":"))


def load_findings(
    path: Path, repository_root: Path | None = None
) -> list[dict[str, Any]]:
    """Return results only with complete, diagnostic-free scan evidence."""

    loaded = _read_json(path)
    results = loaded.get("results")
    errors = loaded.get("errors")
    if not isinstance(results, list) or not isinstance(errors, list):
        raise GateError("Semgrep JSON must contain list results and errors")
    # Warnings include skipped and partially parsed files and can accompany an
    # otherwise successful Semgrep exit code, so they also invalidate evidence.
    if errors:
        raise GateError(
            f"Semgrep reported {len(errors)} diagnostic(s); results are not authoritative"
        )
    skipped_rules = loaded.get("skipped_rules")
    if not isinstance(skipped_rules, list):
        raise GateError("Semgrep JSON must contain a skipped rules list")
    if skipped_rules:
        raise GateError(
            f"Semgrep skipped {len(skipped_rules)} rule(s); results are not authoritative"
        )
    timing = loaded.get("time")
    fixpoint_timeouts = (
        timing.get("fixpoint_timeouts") if isinstance(timing, dict) else None
    )
    if not isinstance(fixpoint_timeouts, list):
        raise GateError("Semgrep JSON must contain a fixpoint timeout list")
    if fixpoint_timeouts:
        raise GateError(
            f"Semgrep reported {len(fixpoint_timeouts)} fixpoint timeout(s); "
            "results are not authoritative; "
            + _fixpoint_timeout_details(fixpoint_timeouts)
        )
    paths = loaded.get("paths")
    scanned = paths.get("scanned") if isinstance(paths, dict) else None
    skipped = paths.get("skipped") if isinstance(paths, dict) else None
    if (
        not isinstance(scanned, list)
        or not scanned
        or any(not isinstance(path, str) or not path for path in scanned)
    ):
        raise GateError("Semgrep JSON must contain non-empty scanned targets")
    if not isinstance(skipped, list):
        raise GateError("Semgrep JSON must contain a skipped targets list")
    normalized_scanned = [normalize_path(target) for target in scanned]
    if "." in normalized_scanned:
        raise GateError("Semgrep scanned target must be a repository file path")
    scanned_paths = set(normalized_scanned)
    if len(scanned_paths) != len(normalized_scanned):
        raise GateError("Semgrep reported duplicate scanned targets")
    if any(path.split("/", 1)[0].startswith(".pytest_tmp_") for path in scanned_paths):
        raise GateError("Semgrep scanned a root pytest temporary target")
    root = repository_root.resolve() if repository_root is not None else None
    scanned_target_paths: set[Path] = set()
    scanned_target_ancestors: set[Path] = set()
    if root is not None:
        for scanned_path in sorted(scanned_paths):
            scanned_target = _repository_file(
                root, scanned_path, "Semgrep scanned target"
            )
            if scanned_target in scanned_target_paths:
                raise GateError("Semgrep reported duplicate scanned targets")
            scanned_target_paths.add(scanned_target)
            parent = scanned_target.parent
            while parent != root:
                if not parent.is_relative_to(root):
                    raise GateError(
                        f"Semgrep scanned target ancestry escapes the repository: {scanned_path}"
                    )
                scanned_target_ancestors.add(parent)
                parent = parent.parent
    skipped_paths: set[str] = set()
    skipped_target_paths: set[Path] = set()
    for entry in skipped:
        if not isinstance(entry, dict) or not {"path", "reason"} <= set(entry):
            raise GateError("each Semgrep skipped target must contain path and reason")
        if set(entry) - {"path", "reason", "details"}:
            raise GateError("Semgrep skipped target contains unsupported metadata")
        skipped_path = normalize_path(entry["path"])
        reason = entry["reason"]
        if not isinstance(reason, str) or not reason:
            raise GateError("Semgrep skipped target reason must be a non-empty string")
        details = entry.get("details")
        if "details" in entry and not isinstance(details, str):
            raise GateError("Semgrep skipped target details must be a string")
        if skipped_path in skipped_paths:
            raise GateError("Semgrep reported duplicate skipped targets")
        skipped_paths.add(skipped_path)
        if skipped_path in scanned_paths:
            raise GateError("Semgrep target is both scanned and skipped")
        if reason != "semgrepignore_patterns_match":
            raise GateError(
                f"Semgrep skipped target {skipped_path} for unapproved reason: {reason}"
            )
        if not _matches_reviewed_semgrep_ignore(skipped_path):
            raise GateError(
                f"Semgrep ignore skip is outside the reviewed policy: {skipped_path}"
            )
        if root is None:
            raise GateError(
                "repository root is required to validate Semgrep skipped targets"
            )
        ignored_target = _repository_ignored_target(root, skipped_path)
        if ignored_target in skipped_target_paths:
            raise GateError("Semgrep reported duplicate skipped targets")
        skipped_target_paths.add(ignored_target)
        if ignored_target in scanned_target_paths:
            raise GateError("Semgrep target is both scanned and skipped")
        if ignored_target.is_dir() and ignored_target in scanned_target_ancestors:
            raise GateError(
                "Semgrep scanned a target beneath a skipped ignore directory: "
                f"{skipped_path}"
            )
    for result in results:
        if not isinstance(result, dict):
            raise GateError("each Semgrep result must be an object")
        if normalize_path(result.get("path")) not in scanned_paths:
            raise GateError("Semgrep finding is not in the scanned targets")
    return results


def validate_semgrep_ignore_policy(repository_root: Path) -> None:
    """Require the exact reviewed ignore patterns used to select scan targets."""

    root = repository_root.resolve()
    ignore_file = root / ".semgrepignore"
    if ignore_file.is_symlink() or ignore_file.is_junction():
        raise GateError("Semgrep ignore policy must not be a symlink")
    try:
        resolved = ignore_file.resolve()
        if not resolved.is_relative_to(root):
            raise GateError("Semgrep ignore policy resolves outside the repository")
        contents = ignore_file.read_text(encoding="utf-8")
    except (OSError, RuntimeError, UnicodeDecodeError) as exc:
        raise GateError(f"cannot read Semgrep ignore policy: {exc}") from exc
    patterns = tuple(
        line.strip()
        for line in contents.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    if patterns != _REVIEWED_SEMGREP_IGNORE_PATTERNS:
        raise GateError(
            "Semgrep ignore policy differs from the reviewed exact pattern set"
        )


def _line_digest(lines: list[str], line_number: int) -> str:
    if line_number < 1 or line_number > len(lines):
        raise GateError(f"finding line {line_number} is outside its file")
    return hashlib.sha256(lines[line_number - 1].encode("utf-8")).hexdigest()


def _range_digest(lines: list[str], start: int, end: int) -> str:
    if end < start or end > len(lines):
        raise GateError(f"source range {start}-{end} is outside its file")
    return hashlib.sha256("\n".join(lines[start - 1 : end]).encode("utf-8")).hexdigest()


def finding_keys(
    results: Sequence[dict[str, Any]],
    repository_root: Path,
    read_lines: Callable[[Path], list[str]],
    check_id_prefix: str = "",
) -> dict[Key, Finding]:
    """Compute the exact (check_id, path, line digest) key of every finding.

    A non-empty ``check_id_prefix`` is a fixed prefix that Semgrep adds from the
    configuration location. Every check id must carry it and it is removed, so
    dispositions key on the stable rule id rather than the mount path.
    """

    cache: dict[str, list[str]] = {}
    keys: dict[Key, Finding] = {}
    root = repository_root.resolve()
    for result in results:
        check_id = result.get("check_id")
        if not isinstance(check_id, str) or not check_id:
            raise GateError("finding check_id must be a non-empty string")
        if check_id_prefix:
            if not check_id.startswith(check_id_prefix):
                raise GateError(f"finding check_id lacks the fixed prefix: {check_id}")
            check_id = check_id[len(check_id_prefix) :]
            if not check_id:
                raise GateError("finding check_id is empty after prefix removal")
        repository_path = normalize_path(result.get("path"))
        start = result.get("start")
        line_number = start.get("line") if isinstance(start, dict) else None
        if not isinstance(line_number, int) or isinstance(line_number, bool):
            raise GateError(f"finding {check_id} {repository_path} has no start line")
        end = result.get("end")
        end_line = end.get("line") if isinstance(end, dict) else None
        if not isinstance(end_line, int) or isinstance(end_line, bool):
            raise GateError(f"finding {check_id} {repository_path} has no end line")
        if repository_path not in cache:
            source = _repository_file(root, repository_path, "finding")
            cache[repository_path] = read_lines(source)
        key: Key = (
            check_id,
            repository_path,
            _line_digest(cache[repository_path], line_number),
        )
        if key in keys:
            raise GateError(f"ambiguous finding identity: {check_id} {repository_path}")
        keys[key] = Finding(
            line_number,
            end_line,
            _range_digest(cache[repository_path], line_number, end_line),
            cache[repository_path],
        )
    return keys


def _read_source_lines(path: Path) -> list[str]:
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise GateError(f"cannot read finding source {path}: {exc}") from exc
    return content.removesuffix("\n").split("\n") if content else []


def _companion_digest(
    root: Path, companion: ReviewedCompanion
) -> tuple[str, tuple[int, int]]:
    path = root
    for part in PurePosixPath(companion.path).parts:
        path = path / part
        if path.is_symlink() or path.is_junction():
            raise GateError(f"companion path contains a symlink: {companion.path}")
    try:
        if not path.resolve().is_relative_to(root):
            raise GateError(
                f"companion resolves outside the repository: {companion.path}"
            )
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        flags |= getattr(os, "O_NONBLOCK", 0)
        with os.fdopen(os.open(path, flags), "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise GateError(
                    f"cannot read companion as a regular file: {companion.path}"
                )
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
            after = os.fstat(stream.fileno())
            if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ):
                raise GateError(f"companion changed while being read: {companion.path}")
    except OSError as exc:
        raise GateError(f"cannot read companion {companion.path}: {exc}") from exc
    return digest, (before.st_dev, before.st_ino)


def _companion_problems(
    repository_root: Path, source: str, companions: tuple[ReviewedCompanion, ...]
) -> list[str]:
    if not companions:
        return []
    root = repository_root.resolve()
    try:
        source_stat = (root / source).stat()
    except OSError as exc:
        raise GateError(f"cannot read finding source {source}: {exc}") from exc
    seen = {(source_stat.st_dev, source_stat.st_ino)}
    problems = []
    for companion in companions:
        digest, identity = _companion_digest(root, companion)
        if identity in seen:
            raise GateError(f"duplicate companion file: {companion.path}")
        seen.add(identity)
        if digest != companion.sha256:
            problems.append(f"Semgrep companion evidence changed: {companion.path}")
    return problems


def evaluate(
    results_path: Path,
    dispositions_path: Path,
    repository_root: Path,
    today: date,
    read_lines: Callable[[Path], list[str]] = _read_source_lines,
    check_id_prefix: str = "",
) -> list[str]:
    """Return human-readable problems; an empty list means the gate passes."""

    validate_semgrep_ignore_policy(repository_root)
    dispositions = load_dispositions(dispositions_path, today)
    findings = finding_keys(
        load_findings(results_path, repository_root),
        repository_root,
        read_lines,
        check_id_prefix,
    )
    problems = []
    for key in sorted(findings.keys() - dispositions.keys()):
        check_id, path, digest = key
        finding = findings[key]
        problem = (
            f"unreviewed Semgrep finding: {check_id} {path} (line sha256 {digest})"
        )
        if finding.end_line > finding.start_line:
            problem += (
                f" reported span {finding.start_line}-{finding.end_line}"
                f" sha256 {finding.span_sha256}"
            )
        problems.append(problem)
    problems.extend(
        f"stale disposition matches no finding: {check_id} {path}"
        for check_id, path, _digest in sorted(dispositions.keys() - findings.keys())
    )
    for key in sorted(findings.keys() & dispositions.keys()):
        finding = findings[key]
        evidence = dispositions[key]
        if finding.end_line > finding.start_line:
            valid = evidence.span_sha256 == finding.span_sha256
        elif evidence.context is None:
            valid = False
        else:
            context = evidence.context
            valid = (
                context.start_line <= finding.start_line <= context.end_line
                and _range_digest(
                    finding.source_lines, context.start_line, context.end_line
                )
                == context.sha256
            )
        if not valid:
            problems.append(f"Semgrep evidence changed or missing: {key[0]} {key[1]}")
        problems.extend(
            _companion_problems(repository_root, key[1], evidence.companions)
        )
    return problems


def _today_utc() -> date:
    """Use one timezone-independent date for expiry checks in CI and locally."""

    return datetime.now(UTC).date()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("results", type=Path, help="Semgrep --json-output file")
    parser.add_argument("--dispositions", type=Path, default=DEFAULT_DISPOSITIONS)
    parser.add_argument("--repository-root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument(
        "--strip-check-prefix",
        default="",
        help="fixed prefix Semgrep adds from the config location; required on every finding",
    )
    args = parser.parse_args(argv)
    try:
        problems = evaluate(
            args.results,
            args.dispositions,
            args.repository_root,
            _today_utc(),
            check_id_prefix=args.strip_check_prefix,
        )
    except GateError as exc:
        print(f"::error::Semgrep dispositions gate: {exc}")
        return 1
    if problems:
        for problem in problems:
            print(f"::error::Semgrep dispositions gate: {problem}")
        return 1
    print(
        "Semgrep dispositions gate: every finding matches an exact unexpired disposition."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
