"""Select the base or cryptographically pinned Go capture helper for CI."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

CANONICAL_REPOSITORY = "egorribun/university_ecosystem"
ACTIVATION_PULL_REQUEST = "1306"
ACTIVATION_HEAD_REF = "egorribun"
ACTIVATION_BASE_REF = "main"
CAPTURE_HELPER_PATH = "scripts/quality/capture_isolated_benchmarks.py"
MAX_CAPTURE_HELPER_BYTES = 256 * 1024

# Public immutable provenance for the reviewed checkpoint containing the helper.
PINNED_HELPER_COMMIT = "03f8e81085972dd5131c7bfbfc310972c7f37642"  # pragma: allowlist secret -- public helper commit
PINNED_HELPER_PARENT = "6a1d1a78a5a78e793b0df32fc6dea1f192b0732f"  # pragma: allowlist secret -- public helper parent
PINNED_HELPER_TREE = "07b9670798c398df862d2065eb8e8393d68e2e4d"  # pragma: allowlist secret -- public helper tree
PINNED_HELPER_BLOB = "25c4d92f64edbb1025672be81d88b7c04321d137"  # pragma: allowlist secret -- public helper blob
PINNED_HELPER_SHA256 = "b0e5442aece556c2d78bb4f4210ee24ff8f797dc1fde878ddf92cd3f61b85e17"  # pragma: allowlist secret -- public helper SHA-256
PINNED_HELPER_SIZE = "52338"

_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_POSITIVE_DECIMAL_RE = re.compile(r"^[1-9][0-9]{0,8}$")


class ActivationError(ValueError):
    """Raised when helper selection cannot be proven safe."""


@dataclass(frozen=True)
class HelperSelection:
    origin: str
    commit: str
    parent: str
    tree: str
    path: str
    blob: str
    sha256: str
    size_bytes: int
    executable_path: Path


def _git(repo: Path, *args: str) -> bytes:
    completed = subprocess.run(  # noqa: S603 - fixed git executable and argv, no shell.
        ("git", "-C", str(repo), *args),
        check=False,
        capture_output=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise ActivationError("git_object_validation_failed")
    return completed.stdout


def _resolve_commit(repo: Path, revision: str) -> str:
    if _SHA1_RE.fullmatch(revision) is None:
        raise ActivationError("commit_reference_invalid")
    value = (
        _git(repo, "rev-parse", "--verify", f"{revision}^{{commit}}")
        .decode("ascii", errors="strict")
        .strip()
    )
    if _SHA1_RE.fullmatch(value) is None:
        raise ActivationError("commit_id_invalid")
    return value


def _resolve_tree(repo: Path, revision: str) -> str:
    value = (
        _git(repo, "rev-parse", "--verify", f"{revision}^{{tree}}")
        .decode("ascii", errors="strict")
        .strip()
    )
    if _SHA1_RE.fullmatch(value) is None:
        raise ActivationError("tree_id_invalid")
    return value


def _resolve_parent(repo: Path, revision: str) -> str:
    fields = (
        _git(repo, "rev-list", "--parents", "-n", "1", revision)
        .decode("ascii", errors="strict")
        .split()
    )
    if len(fields) != 2 or _SHA1_RE.fullmatch(fields[1]) is None:
        raise ActivationError("helper_commit_parent_invalid")
    return fields[1]


def _resolve_base_parent(repo: Path, revision: str) -> str:
    fields = (
        _git(repo, "rev-list", "--parents", "-n", "1", revision)
        .decode("ascii", errors="strict")
        .split()
    )
    if not fields or any(_SHA1_RE.fullmatch(value) is None for value in fields):
        raise ActivationError("base_commit_parent_record_invalid")
    if len(fields) == 1:
        return "none"
    return fields[1]


def _resolve_regular_blob(repo: Path, revision: str, path: str) -> str:
    raw = _git(repo, "ls-tree", "-z", revision, "--", path)
    rows = raw.split(b"\0")
    if len(rows) != 2 or rows[1] or not rows[0]:
        raise ActivationError("helper_tree_entry_invalid")
    metadata, separator, recorded_path = rows[0].partition(b"\t")
    fields = metadata.split()
    if (
        not separator
        or recorded_path.decode("utf-8", errors="strict") != path
        or len(fields) != 3
        or fields[0] != b"100644"
        or fields[1] != b"blob"
    ):
        raise ActivationError("helper_tree_entry_not_regular_file")
    blob = fields[2].decode("ascii", errors="strict")
    if _SHA1_RE.fullmatch(blob) is None:
        raise ActivationError("helper_blob_id_invalid")
    return blob


def _read_pinned_blob(repo: Path, blob: str, expected_size: int) -> bytes:
    size_text = (
        _git(repo, "cat-file", "-s", blob).decode("ascii", errors="strict").strip()
    )
    if not size_text.isdecimal() or int(size_text) != expected_size:
        raise ActivationError("helper_blob_size_mismatch")
    if expected_size <= 0 or expected_size > MAX_CAPTURE_HELPER_BYTES:
        raise ActivationError("helper_blob_size_out_of_bounds")
    payload = _git(repo, "cat-file", "blob", blob)
    if len(payload) != expected_size:
        raise ActivationError("helper_blob_size_mismatch")
    return payload


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _is_reparse_point(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    if callable(is_junction) and is_junction():
        return True
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except (OSError, RuntimeError, ValueError):
        return True
    return bool(attributes & 0x400)


def _cleanup_helper_dir(helper_dir: Path, trusted_temp: Path) -> None:
    """Remove only a direct, still-resolved ordinary child of runner temp."""
    try:
        if _is_reparse_point(trusted_temp):
            return
        trusted_root = trusted_temp.resolve(strict=True)
        if not trusted_root.is_dir() or _is_reparse_point(helper_dir):
            return
        resolved_dir = helper_dir.resolve(strict=True)
        if (
            resolved_dir == trusted_root
            or resolved_dir.parent != trusted_root
            or _is_reparse_point(resolved_dir)
        ):
            return
        # Re-resolve and reject reparse points immediately before recursion.
        final_target = helper_dir.resolve(strict=True)
        if (
            final_target != resolved_dir
            or final_target.parent != trusted_root
            or _is_reparse_point(helper_dir)
            or _is_reparse_point(final_target)
        ):
            return
        shutil.rmtree(final_target)
    except (OSError, RuntimeError, ValueError):
        return


def _eligible_context(
    context: Mapping[str, str], source_head_sha: str, candidate_sha: str
) -> bool:
    """Limit activation to the reviewed PR and canonical main transition."""
    event = context.get("event_name", "")
    repository = context.get("repository", "")
    if repository != CANONICAL_REPOSITORY:
        return False

    if event == "push":
        push_ref = context.get("push_ref", "")
        if push_ref != "refs/heads/main":
            return False
        if context.get("push_base_ref") != "main":
            raise ActivationError("approved_main_push_context_mismatch")
        if source_head_sha != candidate_sha:
            raise ActivationError("main_push_source_candidate_mismatch")
        return True

    pull_request = context.get("pull_request_number", "")
    if event != "pull_request":
        return False
    if not pull_request.isdecimal() or pull_request.startswith("0"):
        raise ActivationError("pull_request_identity_invalid")
    if pull_request != ACTIVATION_PULL_REQUEST:
        return False
    if (
        context.get("head_repository") != CANONICAL_REPOSITORY
        or context.get("head_ref") != ACTIVATION_HEAD_REF
        or context.get("base_ref") != ACTIVATION_BASE_REF
    ):
        raise ActivationError("approved_pull_request_context_mismatch")
    return True


def _commit_object_present(repo: Path, revision: str) -> bool:
    result = subprocess.run(  # noqa: S603 - fixed git executable and validated SHA argv.
        (
            "git",
            "-C",
            str(repo),
            "rev-parse",
            "--verify",
            "--quiet",
            f"{revision}^{{commit}}",
        ),
        check=False,
        capture_output=True,
        timeout=30,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise ActivationError("helper_history_validation_failed")


def _is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    result = subprocess.run(  # noqa: S603 - fixed git executable and validated SHA argv.
        ("git", "-C", str(repo), "merge-base", "--is-ancestor", ancestor, descendant),
        check=False,
        capture_output=True,
        timeout=30,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise ActivationError("helper_history_validation_failed")


def _first_main_transition_uses_candidate(
    repo: Path, base_sha: str, candidate_sha: str
) -> bool:
    """Select the candidate helper only on the first main push containing it."""
    pinned_commit, *_ = _validate_pins()
    if not _commit_object_present(repo, pinned_commit):
        return False
    pinned = _resolve_commit(repo, pinned_commit)
    base = _resolve_commit(repo, base_sha)
    candidate = _resolve_commit(repo, candidate_sha)
    candidate_contains_pin = _is_ancestor(repo, pinned, candidate)
    base_contains_pin = _is_ancestor(repo, pinned, base)
    if base_contains_pin and not candidate_contains_pin:
        raise ActivationError("main_push_removed_reviewed_helper_history")
    return candidate_contains_pin and not base_contains_pin


def _validate_pins() -> tuple[str, str, str, str, str, int]:
    pins = (
        PINNED_HELPER_COMMIT,
        PINNED_HELPER_PARENT,
        PINNED_HELPER_TREE,
        PINNED_HELPER_BLOB,
        PINNED_HELPER_SHA256,
        PINNED_HELPER_SIZE,
    )
    if any(value.startswith("UNBOUND_") for value in pins):
        raise ActivationError("reviewed_helper_pin_unbound")
    commit, parent, tree, blob, sha256, size_text = pins
    if any(_SHA1_RE.fullmatch(value) is None for value in (commit, parent, tree, blob)):
        raise ActivationError("reviewed_helper_pin_invalid")
    if _SHA256_RE.fullmatch(sha256) is None:
        raise ActivationError("reviewed_helper_pin_invalid")
    if _POSITIVE_DECIMAL_RE.fullmatch(size_text) is None:
        raise ActivationError("reviewed_helper_pin_invalid")
    size_bytes = int(size_text)
    if size_bytes > MAX_CAPTURE_HELPER_BYTES:
        raise ActivationError("reviewed_helper_pin_invalid")
    return commit, parent, tree, blob, sha256, size_bytes


def _base_selection(
    repo: Path, base_worktree: Path, base_sha: str, helper: Path
) -> HelperSelection:
    commit = _resolve_commit(repo, base_sha)
    helper_path = helper.resolve(strict=True)
    base_root = base_worktree.resolve(strict=True)
    if (
        helper.is_symlink()
        or not _is_within(helper_path, base_root)
        or not helper_path.is_file()
    ):
        raise ActivationError("base_capture_helper_path_invalid")
    blob = _resolve_regular_blob(repo, commit, CAPTURE_HELPER_PATH)
    payload = _read_pinned_blob(repo, blob, helper_path.stat().st_size)
    if helper_path.read_bytes() != payload:
        raise ActivationError("base_capture_helper_content_mismatch")
    return HelperSelection(
        origin="immutable-base",
        commit=commit,
        parent=_resolve_base_parent(repo, commit),
        tree=_resolve_tree(repo, commit),
        path=CAPTURE_HELPER_PATH,
        blob=blob,
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
        executable_path=helper_path,
    )


def _candidate_selection(
    repo: Path,
    source_head_sha: str,
    candidate_sha: str,
    runner_temp: Path,
) -> HelperSelection:
    commit, parent, tree, blob, expected_sha, expected_size = _validate_pins()
    if _resolve_commit(repo, commit) != commit:
        raise ActivationError("helper_commit_pin_mismatch")
    if _resolve_parent(repo, commit) != parent:
        raise ActivationError("helper_parent_pin_mismatch")
    if _resolve_tree(repo, commit) != tree:
        raise ActivationError("helper_tree_pin_mismatch")
    if _resolve_regular_blob(repo, commit, CAPTURE_HELPER_PATH) != blob:
        raise ActivationError("helper_blob_pin_mismatch")
    for revision in (source_head_sha, candidate_sha):
        resolved = _resolve_commit(repo, revision)
        result = subprocess.run(  # noqa: S603 - fixed git executable and validated SHA argv.
            ("git", "-C", str(repo), "merge-base", "--is-ancestor", commit, resolved),
            check=False,
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise ActivationError("reviewed_helper_not_in_tested_history")
    payload = _read_pinned_blob(repo, blob, expected_size)
    actual_sha = hashlib.sha256(payload).hexdigest()
    if actual_sha != expected_sha:
        raise ActivationError("helper_content_sha256_mismatch")

    trusted_temp = runner_temp.resolve(strict=True)
    if _is_reparse_point(runner_temp) or not trusted_temp.is_dir():
        raise ActivationError("runner_temp_invalid")
    helper_dir = Path(
        tempfile.mkdtemp(prefix="quality-pinned-capture-", dir=trusted_temp)
    )
    try:
        resolved_dir = helper_dir.resolve(strict=True)
        if not _is_within(resolved_dir, trusted_temp) or resolved_dir == trusted_temp:
            raise ActivationError("helper_copy_path_invalid")
        helper_copy = resolved_dir / "capture_isolated_benchmarks.py"
        with helper_copy.open("xb") as handle:
            handle.write(payload)
        helper_copy.chmod(0o444)
        if helper_copy.is_symlink() or helper_copy.read_bytes() != payload:
            raise ActivationError("helper_copy_verification_failed")
        return HelperSelection(
            origin="reviewed-immutable-candidate",
            commit=commit,
            parent=parent,
            tree=tree,
            path=CAPTURE_HELPER_PATH,
            blob=blob,
            sha256=actual_sha,
            size_bytes=len(payload),
            executable_path=helper_copy,
        )
    except Exception:
        _cleanup_helper_dir(helper_dir, trusted_temp)
        raise


def select_capture_helper(
    *,
    context: Mapping[str, str],
    repo: Path,
    base_worktree: Path,
    base_sha: str,
    source_head_sha: str,
    candidate_sha: str,
    base_helper: Path,
    runner_temp: Path,
) -> HelperSelection:
    """Select the pinned helper only for an approved immutable source context."""
    if not _eligible_context(context, source_head_sha, candidate_sha):
        return _base_selection(repo, base_worktree, base_sha, base_helper)
    if context.get(
        "event_name"
    ) == "push" and not _first_main_transition_uses_candidate(
        repo, base_sha, candidate_sha
    ):
        return _base_selection(repo, base_worktree, base_sha, base_helper)
    return _candidate_selection(repo, source_head_sha, candidate_sha, runner_temp)


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ActivationError("required_workflow_context_missing")
    return value


def main() -> int:
    try:
        context = {
            "event_name": _required("EVENT_NAME"),
            "repository": _required("REPOSITORY_NAME"),
            "pull_request_number": os.environ.get("PR_NUMBER", ""),
            "head_repository": os.environ.get("PR_HEAD_REPOSITORY", ""),
            "head_ref": os.environ.get("PR_HEAD_REF", ""),
            "base_ref": os.environ.get("PR_BASE_REF", ""),
            "push_ref": os.environ.get("PUSH_REF", ""),
            "push_base_ref": os.environ.get("PUSH_BASE_REF", ""),
        }
        selection = select_capture_helper(
            context=context,
            repo=Path(_required("GITHUB_WORKSPACE")),
            base_worktree=Path(_required("BASE_WORKTREE")),
            base_sha=_required("BASE_SHA"),
            source_head_sha=_required("SOURCE_HEAD_SHA"),
            candidate_sha=_required("CANDIDATE_SHA"),
            base_helper=Path(_required("BASE_CAPTURE_HELPER")),
            runner_temp=Path(_required("RUNNER_TEMP")),
        )
        output_path = Path(_required("GITHUB_OUTPUT"))
        output_path_resolved = output_path.resolve(strict=True)
        if output_path.is_symlink() or not output_path_resolved.is_file():
            raise ActivationError("workflow_output_path_invalid")
        rows = {
            "capture_helper_path": str(selection.executable_path),
            "capture_helper_origin": selection.origin,
            "capture_helper_commit": selection.commit,
            "capture_helper_parent": selection.parent,
            "capture_helper_tree": selection.tree,
            "capture_helper_source_path": selection.path,
            "capture_helper_blob": selection.blob,
            "capture_helper_sha256": selection.sha256,
            "capture_helper_size_bytes": str(selection.size_bytes),
        }
        with output_path.open("a", encoding="utf-8", newline="\n") as output:
            for key, value in rows.items():
                if "\n" in value or "\r" in value:
                    raise ActivationError("workflow_output_value_invalid")
                output.write(f"{key}={value}\n")
        print(selection.executable_path)
        return 0
    except (ActivationError, OSError, subprocess.SubprocessError, UnicodeError):
        print("Capture helper selection failed closed.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
