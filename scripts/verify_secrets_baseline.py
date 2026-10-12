#!/usr/bin/env python3
"""Fail-closed verification for a detect-secrets baseline.

The committed baseline is an allowlist of individual findings, not merely a
list of files.  A fresh scan must therefore be a subset of the baseline (old
entries are allowed to become stale when a secret is removed), while a pull
request must not add a new suppression relative to a trusted base baseline.

Usage::

    python scripts/verify_secrets_baseline.py BASELINE CURRENT_SCAN
    python scripts/verify_secrets_baseline.py BASELINE CURRENT_SCAN \
        --trusted-base-baseline TRUSTED_BASELINE \
        --trusted-base-source-sha BASE_SHA

Exit code 0 means no unsuppressed findings were detected.  Exit code 1 means
the current scan found a finding that is not in the committed baseline, or a
pull request added a suppression for a finding relative to its trusted base, or
the source delta added an inline secret-allowlist pragma. The source check
runs when --trusted-base-source-sha is supplied. Exit code 2 means an
artifact or trusted source delta is missing or malformed.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class BaselineArtifactError(ValueError):
    """Raised when a baseline or scan artifact cannot be trusted."""


class SourceDeltaError(ValueError):
    """Raised when a trusted source delta cannot be verified safely."""


_SOURCE_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_INLINE_SECRET_ALLOWLIST_PATTERN = re.compile(
    r"\bpragma\s*:\s*allowlist\s+secret\b", re.IGNORECASE
)
_DIFF_HUNK_PATTERN = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def _decode_git_quoted_path(value: str) -> str:
    """Decode Git's C-quoted pathname form without interpreting source text."""

    if not (value.startswith('"') and value.endswith('"')):
        return value

    escaped = value[1:-1]
    decoded = bytearray()
    simple_escapes = {
        '"': b'"',
        "\\": b"\\",
        "a": b"\a",
        "b": b"\b",
        "f": b"\f",
        "n": b"\n",
        "r": b"\r",
        "t": b"\t",
        "v": b"\v",
    }
    index = 0
    while index < len(escaped):
        character = escaped[index]
        if character != "\\":
            decoded.extend(character.encode("utf-8", errors="surrogateescape"))
            index += 1
            continue

        index += 1
        if index >= len(escaped):
            raise SourceDeltaError("malformed quoted Git pathname")
        escape = escaped[index]
        if escape in simple_escapes:
            decoded.extend(simple_escapes[escape])
            index += 1
            continue
        if escape not in "01234567":
            raise SourceDeltaError("unsupported quoted Git pathname escape")

        digits = escape
        index += 1
        while index < len(escaped) and len(digits) < 3 and escaped[index] in "01234567":
            digits += escaped[index]
            index += 1
        decoded.append(int(digits, 8))

    return decoded.decode("utf-8", errors="surrogateescape")


def _path_from_added_file_header(header: str) -> str | None:
    # Git uses a literal tab after a quoted pathname as its header delimiter;
    # tabs inside a quoted pathname are escaped and are therefore preserved.
    raw_path = header[4:].split("\t", 1)[0]
    if raw_path == "/dev/null":
        return None
    if raw_path.startswith('"'):
        path = _decode_git_quoted_path(raw_path)
    else:
        path = raw_path
    if not path.startswith("b/"):
        raise SourceDeltaError("unexpected Git diff path prefix")
    return path[2:]


def _find_added_inline_secret_pragmas(diff_text: str) -> list[tuple[str, int]]:
    """Return only safe path/line identities for newly added marker lines."""

    findings: list[tuple[str, int]] = []
    current_path: str | None = None
    new_line_number: int | None = None

    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            current_path = None
            new_line_number = None
            continue

        if new_line_number is None and line.startswith("+++ "):
            current_path = _path_from_added_file_header(line)
            continue

        hunk = _DIFF_HUNK_PATTERN.match(line)
        if line.startswith("@@"):
            if hunk is None:
                raise SourceDeltaError("unrecognized Git diff hunk header")
            new_line_number = int(hunk.group(1))
            continue

        if new_line_number is None:
            if line.startswith("+") and not line.startswith("+++ "):
                raise SourceDeltaError("Git diff addition has no hunk header")
            continue

        if line.startswith("+"):
            if current_path is None:
                raise SourceDeltaError("Git diff addition has no destination path")
            if _INLINE_SECRET_ALLOWLIST_PATTERN.search(line[1:]) is not None:
                findings.append((current_path, new_line_number))
            new_line_number += 1
        elif line.startswith("-"):
            continue
        elif line.startswith(" "):
            new_line_number += 1
        elif line.startswith("\\ No newline at end of file"):
            continue
        else:
            raise SourceDeltaError("unrecognized Git diff hunk format")

    return findings


def find_new_inline_secret_pragmas(
    trusted_base_sha: str, *, repository_root: str | Path
) -> list[tuple[str, int]]:
    """Compare two immutable Git trees and find newly added suppression markers.

    The trusted base must be a full, nonzero commit SHA. Git diagnostics and
    source lines are never returned to the caller.
    """

    if (
        not isinstance(trusted_base_sha, str)
        or _SOURCE_SHA_PATTERN.fullmatch(trusted_base_sha) is None
        or trusted_base_sha == "0" * 40
    ):
        raise SourceDeltaError("trusted source base SHA is invalid")

    try:
        root = Path(repository_root).resolve(strict=True)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise SourceDeltaError("repository root is unavailable") from error

    git_executable = shutil.which("git")
    if git_executable is None:
        raise SourceDeltaError("Git source comparison could not run")
    try:
        git_executable = str(Path(git_executable).resolve(strict=True))
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise SourceDeltaError("Git source comparison could not run") from error

    def run_git(*arguments: str) -> str:
        try:
            # Git arguments are fixed except for the already-validated full source SHA.
            # The executable is absolute and shell interpretation is disabled.
            result = subprocess.run(  # noqa: S603
                [git_executable, *arguments],
                cwd=root,
                capture_output=True,
                check=False,
                encoding="utf-8",
                errors="surrogateescape",
                text=True,
                shell=False,
            )
        except (OSError, UnicodeError) as error:
            raise SourceDeltaError("Git source comparison could not run") from error
        if result.returncode != 0:
            raise SourceDeltaError("Git source comparison failed")
        return result.stdout

    run_git("cat-file", "-e", f"{trusted_base_sha}^{{commit}}")
    head_sha = run_git("rev-parse", "--verify", "HEAD^{commit}").strip()
    if _SOURCE_SHA_PATTERN.fullmatch(head_sha) is None:
        raise SourceDeltaError("current source commit is unavailable")

    diff_text = run_git(
        "diff",
        "--no-ext-diff",
        "--no-textconv",
        "--no-color",
        "--unified=0",
        "--no-renames",
        "--text",
        "--src-prefix=a/",
        "--dst-prefix=b/",
        trusted_base_sha,
        head_sha,
        "--",
    )
    return _find_added_inline_secret_pragmas(diff_text)


@dataclass(frozen=True, slots=True)
class FindingIdentity:
    """Stable, non-secret identity used when comparing detector findings."""

    path: str
    finding_type: str
    hashed_secret: str
    # Detector line numbers are useful diagnostics but are not stable identity:
    # inserting an unrelated line must not require a baseline rewrite.
    line_number: int = field(compare=False, hash=False)

    def sort_key(self) -> tuple[str, int, str, str]:
        """Return a deterministic ordering without exposing the digest."""

        return (self.path, self.line_number, self.finding_type, self.hashed_secret)

    def display(self) -> str:
        """Return a safe diagnostic label (never the secret or its digest)."""

        return f"{self.path}:{self.line_number} ({self.finding_type})"


def canonical_path(value: str) -> str:
    """Return the repository path spelling shared by Windows and POSIX jobs.

    This small helper intentionally lives in the executable verifier as well
    as ``scripts.secrets_baseline``: invoking this file directly puts the
    ``scripts`` directory (rather than the repository root) on ``sys.path``.
    Keeping the verifier standalone avoids a fragile import-time path hack.
    """

    return "/".join(part for part in value.replace("\\", "/").split("/") if part)


def load_json(path: str | Path) -> Any:
    """Load JSON using an explicit encoding and fail closed on I/O errors."""

    try:
        with Path(path).open(encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError as error:
        raise BaselineArtifactError(f"file not found: {error}") from error
    except json.JSONDecodeError as error:
        raise BaselineArtifactError(f"invalid JSON: {error}") from error
    except UnicodeError as error:
        raise BaselineArtifactError(f"invalid UTF-8: {error}") from error
    except OSError as error:
        raise BaselineArtifactError(f"unable to read artifact: {error}") from error


def _canonical_result_path(raw_path: object, *, artifact: str) -> str:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise BaselineArtifactError(
            f"{artifact}: result paths must be non-empty strings"
        )

    # Inspect the separator-normalised spelling before dropping duplicate
    # separators so absolute POSIX and UNC paths cannot be reinterpreted as
    # repository-relative paths by canonicalisation.
    normalised_raw_path = raw_path.replace("\\", "/")
    if normalised_raw_path.startswith("/") or re.match(
        r"^[A-Za-z]:", normalised_raw_path
    ):
        raise BaselineArtifactError(
            f"{artifact}: result path must be a normalised repository-relative path"
        )

    path = canonical_path(raw_path)
    # Artifacts are repository-relative.  Reject absolute paths, drive-letter
    # paths, and traversal segments rather than silently normalising them.
    if (
        not path
        or path.startswith("/")
        or re.match(r"^[A-Za-z]:", path)
        or any(part in {".", ".."} for part in path.split("/"))
    ):
        raise BaselineArtifactError(
            f"{artifact}: result path must be a normalised repository-relative path"
        )
    return path


def _parse_finding(
    result_path: str,
    raw_finding: object,
    *,
    artifact: str,
    index: int,
) -> FindingIdentity:
    if not isinstance(raw_finding, dict):
        raise BaselineArtifactError(
            f"{artifact}: finding {result_path}[{index}] must be an object"
        )

    finding_type = raw_finding.get("type")
    if not isinstance(finding_type, str) or not finding_type.strip():
        raise BaselineArtifactError(
            f"{artifact}: finding {result_path}[{index}] has an invalid type"
        )

    hashed_secret = raw_finding.get("hashed_secret")
    if not isinstance(hashed_secret, str) or not hashed_secret.strip():
        raise BaselineArtifactError(
            f"{artifact}: finding {result_path}[{index}] has an invalid hashed_secret"
        )

    line_number = raw_finding.get("line_number")
    if (
        isinstance(line_number, bool)
        or not isinstance(line_number, int)
        or line_number < 1
    ):
        raise BaselineArtifactError(
            f"{artifact}: finding {result_path}[{index}] has an invalid line_number"
        )

    filename = raw_finding.get("filename")
    if filename is not None:
        canonical_filename = _canonical_result_path(filename, artifact=artifact)
        if canonical_filename != result_path:
            raise BaselineArtifactError(
                f"{artifact}: finding {result_path}[{index}] filename does not match its result path"
            )

    verified = raw_finding.get("is_verified")
    if verified is not None and not isinstance(verified, bool):
        raise BaselineArtifactError(
            f"{artifact}: finding {result_path}[{index}] has an invalid is_verified flag"
        )

    return FindingIdentity(result_path, finding_type, hashed_secret, line_number)


def extract_findings(document: object, *, artifact: str) -> set[FindingIdentity]:
    """Validate a detect-secrets document and return deduplicated identities."""

    if not isinstance(document, dict):
        raise BaselineArtifactError(
            f"{artifact}: top-level JSON value must be an object"
        )

    version = document.get("version")
    if not isinstance(version, str) or not version.strip():
        raise BaselineArtifactError(f"{artifact}: version must be a non-empty string")

    raw_results = document.get("results")
    if not isinstance(raw_results, dict):
        raise BaselineArtifactError(f"{artifact}: results must be an object")

    findings: set[FindingIdentity] = set()
    for raw_path, raw_findings in raw_results.items():
        result_path = _canonical_result_path(raw_path, artifact=artifact)
        if not isinstance(raw_findings, list):
            raise BaselineArtifactError(
                f"{artifact}: results for {result_path} must be a list"
            )
        for index, raw_finding in enumerate(raw_findings):
            findings.add(
                _parse_finding(
                    result_path,
                    raw_finding,
                    artifact=artifact,
                    index=index,
                )
            )
    return findings


def validate_baseline_triage(document: object) -> None:
    """Require an explicit false-positive decision for every baseline entry.

    A baseline entry is an allowlist record, not proof that a detector hit was
    reviewed.  ``detect-secrets audit`` records that decision in ``is_secret``;
    keeping the field explicit prevents an unknown finding from silently
    becoming a long-lived suppression.  A committed baseline may contain only
    findings confirmed to be non-secrets.  Real credentials must be removed or
    rotated instead of being labelled as acceptable repository content.
    """

    if not isinstance(document, dict):
        raise BaselineArtifactError("baseline: top-level JSON value must be an object")
    raw_results = document.get("results")
    if not isinstance(raw_results, dict):
        raise BaselineArtifactError("baseline: results must be an object")
    for raw_path, raw_findings in raw_results.items():
        result_path = _canonical_result_path(raw_path, artifact="baseline")
        if not isinstance(raw_findings, list):
            raise BaselineArtifactError(
                f"baseline: findings for {result_path} must be a list"
            )
        for index, raw_finding in enumerate(raw_findings):
            if not isinstance(raw_finding, dict):
                raise BaselineArtifactError(
                    f"baseline: finding {result_path}[{index}] must be an object"
                )
            decision = raw_finding.get("is_secret")
            if decision is not False:
                raise BaselineArtifactError(
                    f"baseline: finding {result_path}[{index}] requires explicit "
                    "is_secret=false triage"
                )


def _describe_findings(findings: set[FindingIdentity]) -> str:
    """Render bounded, deterministic diagnostics without secret material."""

    ordered = sorted(findings, key=FindingIdentity.sort_key)
    preview = ", ".join(finding.display() for finding in ordered[:20])
    if len(ordered) > 20:
        preview += f", ... (+{len(ordered) - 20} more)"
    return preview


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify a detect-secrets baseline against a fresh scan."
    )
    parser.add_argument("baseline_path", help="committed detect-secrets baseline")
    parser.add_argument("current_scan_path", help="fresh detect-secrets scan")
    parser.add_argument(
        "--trusted-base-baseline",
        "--base-baseline",
        dest="trusted_base_baseline",
        help="trusted target-branch baseline used to detect new PR suppressions",
    )
    parser.add_argument(
        "--trusted-base-source-sha",
        help="immutable trusted source commit used to detect new inline suppressions",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Verify baseline findings and return a shell-friendly status code."""

    try:
        arguments = _build_parser().parse_args(argv)
    except SystemExit as error:
        # Keep the function convenient for tests while retaining argparse's
        # normal CLI help/usage output and exit status.
        return int(error.code) if isinstance(error.code, int) else 2

    try:
        baseline_document = load_json(arguments.baseline_path)
        validate_baseline_triage(baseline_document)
        baseline_findings = extract_findings(baseline_document, artifact="baseline")
        current_findings = extract_findings(
            load_json(arguments.current_scan_path), artifact="current scan"
        )
        trusted_findings: set[FindingIdentity] | None = None
        if arguments.trusted_base_baseline is not None:
            trusted_findings = extract_findings(
                load_json(arguments.trusted_base_baseline), artifact="trusted base"
            )
    except BaselineArtifactError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    source_pragma_findings: list[tuple[str, int]] = []
    if arguments.trusted_base_source_sha is not None:
        try:
            source_pragma_findings = find_new_inline_secret_pragmas(
                arguments.trusted_base_source_sha,
                repository_root=Path(__file__).resolve().parents[1],
            )
        except SourceDeltaError:
            print(
                "ERROR: trusted source delta could not be verified.",
                file=sys.stderr,
            )
            return 2

    new_findings = current_findings - baseline_findings
    stale_suppressions = baseline_findings - current_findings
    # Only a newly added baseline entry that actually suppresses a finding in
    # this scan changes security semantics.  New stale entries remain harmless
    # and retain the existing removal/refactoring behaviour.
    new_trusted_suppressions: set[FindingIdentity] = set()
    if trusted_findings is not None:
        new_trusted_suppressions = (
            baseline_findings - trusted_findings
        ) & current_findings

    if stale_suppressions:
        print(
            "INFO: .secrets.baseline contains "
            f"{len(stale_suppressions)} stale finding(s) "
            "(removed files or secrets are allowed)."
        )

    if new_findings:
        print(
            "ERROR: current scan contains "
            f"{len(new_findings)} new finding(s) not present in the "
            "committed baseline: "
            f"{_describe_findings(new_findings)}",
            file=sys.stderr,
        )

    if new_trusted_suppressions:
        print(
            "ERROR: baseline introduces "
            f"{len(new_trusted_suppressions)} finding-level suppression(s) relative "
            "to the trusted base baseline: "
            f"{_describe_findings(new_trusted_suppressions)}",
            file=sys.stderr,
        )

    if source_pragma_findings:
        locations = ", ".join(
            f"{json.dumps(path, ensure_ascii=True)}:{line_number}"
            for path, line_number in source_pragma_findings[:20]
        )
        overflow = len(source_pragma_findings) - 20
        if overflow > 0:
            locations += f", ... (+{overflow} more)"
        print(
            "ERROR: source delta adds "
            f"{len(source_pragma_findings)} inline secret-allowlist pragma line(s): "
            f"{locations}",
            file=sys.stderr,
        )

    if new_findings or new_trusted_suppressions or source_pragma_findings:
        return 1

    baseline_paths = {finding.path for finding in baseline_findings}
    print(
        "OK: .secrets.baseline integrity check passed "
        f"({len(baseline_paths)} suppressed file(s), "
        f"{len(baseline_findings)} finding(s) verified)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
