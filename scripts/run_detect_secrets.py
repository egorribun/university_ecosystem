#!/usr/bin/env python3
"""Run one cross-platform detect-secrets scan and normalize its baseline."""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

if __package__:
    from scripts.secrets_baseline import (
        _baseline_lock,
        _canonicalize_baseline_file_unlocked,
        _replace_if_unchanged,
        canonicalize_document,
    )
    from scripts.verify_secrets_baseline import (
        BaselineArtifactError,
        FindingIdentity,
        canonical_path,
        extract_findings,
        load_owner_authored_candidate_false_positive_dispositions,
        load_trusted_base_false_positive_dispositions,
        validate_baseline_triage,
    )
else:
    from secrets_baseline import (
        _baseline_lock,
        _canonicalize_baseline_file_unlocked,
        _replace_if_unchanged,
        canonicalize_document,
    )
    from verify_secrets_baseline import (
        BaselineArtifactError,
        FindingIdentity,
        canonical_path,
        extract_findings,
        load_owner_authored_candidate_false_positive_dispositions,
        load_trusted_base_false_positive_dispositions,
        validate_baseline_triage,
    )

_VALUE_OPTIONS = frozenset(
    {
        "-C",
        "-c",
        "--baseline",
        "-p",
        "--plugin",
        "--base64-limit",
        "--hex-limit",
        "--disable-plugin",
        "--exclude-lines",
        "--exclude-files",
        "--exclude-secrets",
        "-f",
        "--filter",
        "--disable-filter",
    }
)
_PATH_VALUE_OPTIONS = frozenset(
    {"-C", "--baseline", "-p", "--plugin", "-f", "--filter"}
)
_DISPOSITION_POLICY_PATH = "quality/security-false-positive-dispositions.json"
_BASELINE_FILE_FILTER = "detect_secrets.filters.common.is_baseline_file"
_OWNER_DISPOSITION_OPT_IN = "UE_DETECT_SECRETS_OWNER_AUTHORED_DISPOSITION_UPDATE"
_FULL_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")


def normalize_detect_secrets_arguments(arguments: list[str]) -> list[str]:
    """Normalize only filenames and path-valued options, never regex values."""
    normalized: list[str] = []
    value_for: str | None = None
    for argument in arguments:
        if value_for is not None:
            normalized.append(
                argument.replace("\\", "/")
                if value_for in _PATH_VALUE_OPTIONS
                else argument
            )
            value_for = None
            continue
        if argument.startswith("-"):
            if argument.startswith("-C") and len(argument) > 2:
                prefix = "-C=" if argument.startswith("-C=") else "-C"
                value = argument[len(prefix) :].replace("\\", "/")
                normalized.append(f"{prefix}{value}")
                continue
            option, separator, value = argument.partition("=")
            if separator:
                normalized_value = (
                    value.replace("\\", "/") if option in _PATH_VALUE_OPTIONS else value
                )
                normalized.append(f"{option}={normalized_value}")
            else:
                normalized.append(argument)
                if option in _VALUE_OPTIONS:
                    value_for = option
            continue
        normalized.append(argument.replace("\\", "/"))
    return normalized


def _detect_context_values(arguments: list[str]) -> tuple[str | None, str | None]:
    custom_root: str | None = None
    baseline: str | None = None
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--":
            break
        if argument in {"-C", "--baseline"}:
            if index + 1 < len(arguments):
                value = arguments[index + 1]
                if argument == "-C":
                    custom_root = value
                else:
                    baseline = value
            index += 2
            continue
        if argument.startswith("-C="):
            custom_root = argument[3:]
        elif argument.startswith("-C") and len(argument) > 2:
            custom_root = argument[2:]
        elif argument.startswith("--baseline="):
            baseline = argument.partition("=")[2]
        elif argument in _VALUE_OPTIONS:
            index += 2
            continue
        index += 1
    return custom_root, baseline


def _runner_arguments(arguments: list[str]) -> list[str]:
    """Remove wrapper-only custom-root options before invoking detect-secrets."""
    runner_arguments: list[str] = []
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--":
            runner_arguments.extend(arguments[index:])
            break
        if argument == "-C":
            index += 2
            continue
        if argument.startswith("-C") and len(argument) > 2:
            index += 1
            continue
        runner_arguments.append(argument)
        index += 1
    return runner_arguments


def _effective_root(arguments: list[str], invocation_root: Path) -> Path:
    custom_root, _baseline = _detect_context_values(arguments)
    if not custom_root:
        return invocation_root.resolve()
    root = Path(custom_root)
    if not root.is_absolute():
        root = invocation_root / root
    return root.resolve()


def _baseline_path(
    arguments: list[str], invocation_root: Path | None = None
) -> Path | None:
    invocation = (invocation_root or Path.cwd()).resolve()
    _custom_root, baseline_value = _detect_context_values(arguments)
    if not baseline_value:
        return None
    baseline = Path(baseline_value)
    if not baseline.is_absolute():
        baseline = _effective_root(arguments, invocation) / baseline
    return baseline.resolve()


def _git_executable() -> str:
    executable = shutil.which("git")
    if executable is None:
        raise BaselineArtifactError("local disposition lookup could not run")
    try:
        return str(Path(executable).resolve(strict=True))
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise BaselineArtifactError("local disposition lookup could not run") from error


def _git(root: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(  # noqa: S603
            [_git_executable(), *arguments],
            cwd=root,
            capture_output=True,
            check=False,
            shell=False,
        )
    except (OSError, UnicodeError) as error:
        raise BaselineArtifactError("local disposition lookup could not run") from error


def _candidate_policy_is_staged_and_clean(root: Path) -> None:
    staged = _git(
        root,
        "diff",
        "--cached",
        "--quiet",
        "HEAD",
        "--",
        _DISPOSITION_POLICY_PATH,
    )
    if staged.returncode == 0:
        raise BaselineArtifactError("owner candidate disposition policy is not staged")
    if staged.returncode != 1:
        raise BaselineArtifactError("owner candidate disposition staging check failed")

    worktree = _git(root, "diff", "--quiet", "--", _DISPOSITION_POLICY_PATH)
    if worktree.returncode != 0:
        raise BaselineArtifactError(
            "owner candidate disposition policy is not index-matched"
        )


def _repository_root(root: Path) -> Path | None:
    result = _git(root, "rev-parse", "--show-toplevel")
    if result.returncode != 0:
        return None
    try:
        return Path(result.stdout.decode("utf-8").strip()).resolve(strict=True)
    except (OSError, RuntimeError, UnicodeError, ValueError) as error:
        raise BaselineArtifactError("local repository root is invalid") from error


def _load_local_dispositions(root: Path) -> set[FindingIdentity]:
    """Load HEAD policy by default; candidate policy requires explicit local opt-in."""
    repository = _repository_root(root)
    opt_in = os.environ.get(_OWNER_DISPOSITION_OPT_IN)
    policy_root = repository or root
    policy_file = policy_root.joinpath(*_DISPOSITION_POLICY_PATH.split("/"))
    if opt_in == "1":
        if repository is None:
            raise BaselineArtifactError(
                "owner candidate policy requires a Git repository"
            )
        _candidate_policy_is_staged_and_clean(repository)
        return load_owner_authored_candidate_false_positive_dispositions(
            repository_root=repository
        )
    if opt_in is not None:
        raise BaselineArtifactError("owner candidate disposition opt-in is invalid")

    if repository is None:
        # Hermetic wrapper tests and non-repository callers without a policy
        # keep the ordinary scanner path; a present candidate is never trusted.
        if policy_file.exists():
            raise BaselineArtifactError(
                "trusted local disposition source is unavailable"
            )
        return set()
    result = _git(repository, "rev-parse", "--verify", "HEAD^{commit}")
    if result.returncode != 0:
        raise BaselineArtifactError("trusted local disposition source is unavailable")
    try:
        head_sha = result.stdout.decode("ascii").strip()
    except UnicodeError as error:
        raise BaselineArtifactError(
            "trusted local disposition source is invalid"
        ) from error
    if _FULL_COMMIT_SHA.fullmatch(head_sha) is None or head_sha == "0" * 40:
        raise BaselineArtifactError("trusted local disposition source is invalid")
    return load_trusted_base_false_positive_dispositions(
        head_sha, repository_root=repository
    )


def _replace_baseline_argument(arguments: list[str], baseline: Path) -> list[str]:
    """Point every active baseline option at the temporary overlay."""
    result: list[str] = []
    index = 0
    replaced = False
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--":
            result.extend(arguments[index:])
            break
        if argument == "--baseline":
            result.extend((argument, str(baseline)))
            index += 2
            replaced = True
            continue
        if argument.startswith("--baseline="):
            result.append(f"--baseline={baseline}")
            replaced = True
        else:
            result.append(argument)
        index += 1
    if not replaced:
        raise BaselineArtifactError("baseline overlay cannot replace the scanner input")
    return result


def _identity_keys(findings: set[FindingIdentity]) -> set[tuple[str, str, str]]:
    return {
        (finding.path, finding.finding_type, finding.hashed_secret)
        for finding in findings
    }


def _overlay_document(
    baseline_content: bytes, dispositions: set[FindingIdentity]
) -> tuple[dict[str, Any], set[FindingIdentity]]:
    try:
        document: Any = json.loads(baseline_content.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise BaselineArtifactError("baseline overlay source is invalid") from error
    validate_baseline_triage(document)
    original_findings = extract_findings(document, artifact="baseline")
    if not isinstance(document, dict) or not isinstance(document.get("results"), dict):
        raise BaselineArtifactError("baseline overlay source is invalid")

    results = document["results"]
    existing = _identity_keys(original_findings)
    for finding in sorted(dispositions, key=FindingIdentity.sort_key):
        if (finding.path, finding.finding_type, finding.hashed_secret) in existing:
            continue
        entry: dict[str, object] = {
            "type": finding.finding_type,
            "filename": finding.path,
            "hashed_secret": finding.hashed_secret,
            "is_secret": False,
            "is_verified": False,
            "line_number": 1,
        }
        entries = results.setdefault(finding.path, [])
        if not isinstance(entries, list):
            raise BaselineArtifactError("baseline overlay results are invalid")
        entries.append(entry)
    return canonicalize_document(document), original_findings


def _baseline_filter_entries(document: Any) -> list[dict[str, Any]]:
    """Return the single self-baseline filter record, if the baseline has one."""
    if not isinstance(document, dict):
        raise BaselineArtifactError("baseline filter metadata is invalid")
    if "filters_used" not in document:
        return []
    filters = document["filters_used"]
    if not isinstance(filters, list):
        raise BaselineArtifactError("baseline filter metadata is invalid")
    entries = [
        item
        for item in filters
        if isinstance(item, dict) and item.get("path") == _BASELINE_FILE_FILTER
    ]
    if len(entries) > 1 or (
        entries and not isinstance(entries[0].get("filename"), str)
    ):
        raise BaselineArtifactError("baseline self-filter metadata is invalid")
    return entries


def _set_baseline_filter_filename(document: Any, filename: str) -> bool:
    """Set only the self-baseline filter path; leave every other filter untouched."""
    if not isinstance(filename, str) or not filename:
        raise BaselineArtifactError("baseline self-filter filename is invalid")
    entries = _baseline_filter_entries(document)
    if not entries:
        return False
    entries[0]["filename"] = filename
    return True


def _canonical_baseline_filter_filename(
    baseline: Path, effective_root: Path, raw_argument: str
) -> str:
    """Use a root-relative path inside the scan root, otherwise the caller spelling."""
    resolved_baseline = baseline.resolve()
    resolved_root = effective_root.resolve()
    try:
        return resolved_baseline.relative_to(resolved_root).as_posix()
    except ValueError:
        return raw_argument


def _meaningful_baseline_document(document: dict[str, Any]) -> dict[str, Any]:
    """Normalize a baseline for update comparison, ignoring scan timestamps."""
    meaningful = canonicalize_document(document)
    meaningful.pop("generated_at", None)
    return meaningful


def _commit_original_baseline_updates(
    baseline: Path,
    expected_content: bytes,
    updated_content: bytes,
    original_findings: set[FindingIdentity],
    dispositions: set[FindingIdentity],
    canonical_filter_filename: str,
) -> bool:
    try:
        document: Any = json.loads(updated_content.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise BaselineArtifactError("updated temporary baseline is invalid") from error
    try:
        original_document: Any = json.loads(expected_content.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise BaselineArtifactError("baseline update source is invalid") from error
    validate_baseline_triage(original_document)
    if not isinstance(original_document, dict):
        raise BaselineArtifactError("baseline update source is invalid")
    original_meaningful = _meaningful_baseline_document(original_document)
    validate_baseline_triage(document)
    updated_findings = extract_findings(document, artifact="temporary baseline")
    allowed = original_findings | dispositions
    if not updated_findings <= allowed:
        raise BaselineArtifactError("temporary baseline contains an unreviewed finding")
    if not isinstance(document, dict) or not isinstance(document.get("results"), dict):
        raise BaselineArtifactError("updated temporary baseline is invalid")

    original_keys = _identity_keys(original_findings)
    filtered_results: dict[str, list[dict[str, Any]]] = {}
    for raw_path, raw_findings in document["results"].items():
        path = canonical_path(raw_path)
        retained = [
            finding
            for finding in raw_findings
            if (
                path,
                finding.get("type"),
                finding.get("hashed_secret"),
            )
            in original_keys
        ]
        if retained:
            filtered_results[path] = retained
    document["results"] = filtered_results
    if "filters_used" in original_document:
        document["filters_used"] = original_document["filters_used"]
        _set_baseline_filter_filename(document, canonical_filter_filename)
    else:
        document.pop("filters_used", None)
    if original_meaningful == _meaningful_baseline_document(document):
        try:
            current_content = baseline.read_bytes()
        except OSError as error:
            raise BaselineArtifactError(
                "baseline cannot be verified after scanner update"
            ) from error
        if current_content != expected_content:
            raise BaselineArtifactError("baseline changed during scanner update")
        return False
    rendered = (json.dumps(document, indent=2) + "\n").encode("utf-8")

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{baseline.name}.", suffix=".tmp", dir=baseline.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(rendered)
        os.chmod(temporary_path, stat.S_IMODE(baseline.stat().st_mode))
        if not _replace_if_unchanged(baseline, temporary_path, expected_content):
            raise BaselineArtifactError("baseline changed during scanner update")
    finally:
        temporary_path.unlink(missing_ok=True)
    return True


def _run_with_disposition_overlay(
    runner_arguments: list[str],
    runner: Callable[[list[str]], int],
    *,
    baseline: Path,
    effective_root: Path,
) -> int:
    dispositions = _load_local_dispositions(effective_root)
    if not dispositions:
        return runner(runner_arguments)
    original_content = baseline.read_bytes()
    overlay, original_findings = _overlay_document(original_content, dispositions)
    try:
        original_document: Any = json.loads(original_content.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise BaselineArtifactError("baseline overlay source is invalid") from error
    _custom_root, raw_baseline_argument = _detect_context_values(runner_arguments)
    if raw_baseline_argument is None:
        raise BaselineArtifactError(
            "baseline overlay cannot resolve its source argument"
        )
    canonical_filter_filename = _canonical_baseline_filter_filename(
        baseline, effective_root, raw_baseline_argument
    )
    original_filter_entries = _baseline_filter_entries(original_document)
    repair_stale_filter = bool(original_filter_entries) and (
        original_filter_entries[0]["filename"] != canonical_filter_filename
    )

    with tempfile.TemporaryDirectory(
        prefix="detect-secrets-dispositions-"
    ) as temp_root:
        overlay_path = Path(temp_root) / baseline.name
        _set_baseline_filter_filename(overlay, str(overlay_path))
        overlay_path.write_text(json.dumps(overlay, indent=2) + "\n", encoding="utf-8")
        overlay_arguments = _replace_baseline_argument(runner_arguments, overlay_path)
        result = runner(overlay_arguments)
        if result == 3 or (result == 0 and repair_stale_filter):
            canonical_changed = _commit_original_baseline_updates(
                baseline,
                original_content,
                overlay_path.read_bytes(),
                original_findings,
                dispositions,
                canonical_filter_filename,
            )
            if not canonical_changed:
                return 0
            if result == 0:
                return 3
        return result


@contextmanager
def _working_directory(path: Path) -> Iterator[None]:
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def run_detect_secrets_hook(
    arguments: list[str], runner: Callable[[list[str]], int]
) -> int:
    """Serialize the hook's complete baseline read/modify/write transaction."""
    normalized = normalize_detect_secrets_arguments(arguments)
    invocation_root = Path.cwd().resolve()
    effective_root = _effective_root(normalized, invocation_root)
    baseline = _baseline_path(normalized, invocation_root)
    runner_arguments = _runner_arguments(normalized)
    if baseline is None or not baseline.is_file():
        with _working_directory(effective_root):
            return runner(runner_arguments)
    with _baseline_lock(baseline):
        with _working_directory(effective_root):
            try:
                return _run_with_disposition_overlay(
                    runner_arguments,
                    runner,
                    baseline=baseline,
                    effective_root=effective_root,
                )
            finally:
                _canonicalize_baseline_file_unlocked(baseline)


def main(arguments: list[str] | None = None) -> int:
    # Call the hook API in-process so normalized positional filenames are
    # preserved without another platform-dependent command-line roundtrip.
    from detect_secrets.pre_commit_hook import main as detect_secrets_main

    try:
        return run_detect_secrets_hook(
            list(arguments or sys.argv[1:]), detect_secrets_main
        )
    except BaselineArtifactError:
        sys.stderr.write("detect-secrets policy or baseline validation failed\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
