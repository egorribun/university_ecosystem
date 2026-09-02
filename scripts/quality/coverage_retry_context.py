"""Build and verify fail-closed retry contexts for CI quality evidence.

Coverage and Lighthouse jobs can reuse only evidence produced for the same
immutable source, workflow, and explicitly-declared configuration inputs.  The
helper deliberately owns no artifact download or report handling; it produces
the compact mappings consumed by provenance-aware selectors.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath, PureWindowsPath

_SHA_PATTERN = re.compile(r"[0-9a-f]{40}$")
_DIGEST_DOMAIN = b"university-ecosystem.retry-context.v1\x00"

RETRY_PROVENANCE_FIELDS = frozenset(
    {
        "repository",
        "run_id",
        "run_attempt",
        "source_sha",
        "source_revision",
        "workflow_ref",
        "workflow_sha",
        "event",
        "config_digest",
        "policy_digest",
        "artifact",
    }
)
CONSUMER_RETRY_CONTEXT_FIELDS = RETRY_PROVENANCE_FIELDS - frozenset(
    {"run_attempt", "artifact"}
)


class RetryContextError(ValueError):
    """Raised when retry context inputs or claims are unsafe or incomplete."""


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RetryContextError(f"{field} must be a non-empty string")
    if "\x00" in value or "\r" in value or "\n" in value:
        raise RetryContextError(f"{field} contains forbidden control characters")
    return value


def _require_sha(value: object, field: str) -> str:
    text = _require_text(value, field)
    if _SHA_PATTERN.fullmatch(text) is None:
        raise RetryContextError(f"{field} must be an exact lowercase 40-character SHA")
    return text


def _require_positive_decimal(value: object, field: str) -> str:
    text = _require_text(value, field)
    if not text.isdecimal() or int(text) < 1:
        raise RetryContextError(f"{field} must be a positive decimal identifier")
    return text


def _require_exact_fields(
    value: Mapping[object, object], expected: frozenset[str], field: str
) -> None:
    actual = frozenset(value)
    missing = sorted(expected - actual)
    unexpected = sorted(str(name) for name in actual - expected)
    if missing:
        raise RetryContextError(f"{field} missing fields: {', '.join(missing)}")
    if unexpected:
        raise RetryContextError(
            f"{field} has unexpected fields: {', '.join(unexpected)}"
        )


def _is_link_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    isjunction = getattr(os.path, "isjunction", None)
    return bool(isjunction is not None and isjunction(path))


def _normal_path_text(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def _trusted_repository_root(repository_root: Path) -> Path:
    lexical = Path(os.path.abspath(repository_root))
    if _is_link_or_junction(lexical):
        raise RetryContextError(
            f"repository root must not be a symlink or junction: {repository_root}"
        )
    try:
        resolved = lexical.resolve(strict=True)
    except OSError as error:
        raise RetryContextError(
            f"repository root is unavailable: {repository_root}"
        ) from error
    if _normal_path_text(lexical) != _normal_path_text(resolved):
        raise RetryContextError(
            f"repository root traverses a symlink or junction: {repository_root}"
        )
    if not resolved.is_dir():
        raise RetryContextError(f"repository root is not a directory: {resolved}")
    return resolved


def _safe_relative_path(value: object, field: str) -> str:
    if not isinstance(value, (str, Path)):
        raise RetryContextError(
            f"{field} must be a safe repository-relative POSIX path"
        )
    text = str(value)
    if not text or "\x00" in text or "\r" in text or "\n" in text:
        raise RetryContextError(
            f"{field} must be a safe repository-relative POSIX path"
        )
    portable = text.replace("\\", "/")
    path = PurePosixPath(portable)
    if (
        PureWindowsPath(text).drive
        or path.is_absolute()
        or portable != path.as_posix()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise RetryContextError(
            f"{field} must be a safe repository-relative POSIX path"
        )
    return path.as_posix()


def _validated_input_paths(value: object, field: str) -> tuple[str, ...]:
    if isinstance(value, (str, Path)) or not isinstance(value, Sequence):
        raise RetryContextError(f"{field} must be an explicit sequence of input paths")
    if not value:
        raise RetryContextError(f"{field} must contain at least one input path")
    paths: set[str] = set()
    for index, item in enumerate(value):
        relative = _safe_relative_path(item, f"{field}[{index}]")
        if relative in paths:
            raise RetryContextError(
                f"{field} contains a duplicate input path: {relative}"
            )
        paths.add(relative)
    return tuple(sorted(paths))


def _reject_linked_ancestors(root: Path, candidate: Path, field: str) -> None:
    try:
        relative = candidate.relative_to(root)
    except ValueError as error:
        raise RetryContextError(
            f"{field} escapes the trusted repository root"
        ) from error
    current = root
    for part in relative.parts:
        current /= part
        if _is_link_or_junction(current):
            raise RetryContextError(
                f"{field} traverses a symlink or junction: {current}"
            )


def _safe_regular_file(
    root: Path, relative: str, field: str
) -> tuple[Path, os.stat_result]:
    candidate = root.joinpath(*PurePosixPath(relative).parts)
    _reject_linked_ancestors(root, candidate, field)
    if _is_link_or_junction(candidate):
        raise RetryContextError(
            f"{field} must not be a symlink or junction: {relative}"
        )
    try:
        metadata = candidate.lstat()
    except OSError as error:
        raise RetryContextError(
            f"{field} does not identify an input file: {relative}"
        ) from error
    if not stat.S_ISREG(metadata.st_mode):
        raise RetryContextError(f"{field} must be a regular file: {relative}")
    if metadata.st_nlink != 1:
        raise RetryContextError(f"{field} must not be a hard link: {relative}")
    if metadata.st_size <= 0:
        raise RetryContextError(f"{field} must be a non-empty input: {relative}")
    return candidate, metadata


def _same_file_identity(before: os.stat_result, after: os.stat_result) -> bool:
    return (
        before.st_dev,
        before.st_ino,
        before.st_nlink,
        before.st_size,
        before.st_mtime_ns,
    ) == (
        after.st_dev,
        after.st_ino,
        after.st_nlink,
        after.st_size,
        after.st_mtime_ns,
    )


def _digest_input_files(repository_root: Path, input_paths: object, field: str) -> str:
    digest = hashlib.sha256()
    digest.update(_DIGEST_DOMAIN)
    encoded_field = field.encode("ascii")
    digest.update(len(encoded_field).to_bytes(8, "big"))
    digest.update(encoded_field)
    for relative in _validated_input_paths(input_paths, field):
        path, before = _safe_regular_file(repository_root, relative, field)
        encoded_path = relative.encode("utf-8")
        digest.update(len(encoded_path).to_bytes(8, "big"))
        digest.update(encoded_path)
        digest.update(before.st_size.to_bytes(8, "big"))
        try:
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as error:
            raise RetryContextError(f"{field} cannot be read: {relative}") from error
        _, after = _safe_regular_file(repository_root, relative, field)
        if not _same_file_identity(before, after):
            raise RetryContextError(
                f"{field} changed while its digest was calculated: {relative}"
            )
    return digest.hexdigest()


def _git_head(repository_root: Path) -> str:
    git = shutil.which("git")
    if git is None:
        raise RetryContextError("git is unavailable; current HEAD cannot be verified")
    try:
        result = subprocess.run(  # noqa: S603
            [git, "rev-parse", "HEAD"],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RetryContextError(
            f"unable to resolve current repository HEAD: {error}"
        ) from error
    return _require_sha(result.stdout.strip(), "repository HEAD")


def _identity(
    *,
    repository: str,
    run_id: str,
    workflow_ref: str,
    workflow_sha: str,
    event: str,
) -> dict[str, str]:
    return {
        "repository": _require_text(repository, "repository"),
        "run_id": _require_positive_decimal(run_id, "run_id"),
        "workflow_ref": _require_text(workflow_ref, "workflow_ref"),
        "workflow_sha": _require_sha(workflow_sha, "workflow_sha"),
        "event": _require_text(event, "event"),
    }


def _build_consumer_context(
    *,
    repository_root: Path,
    config_inputs: Sequence[str | Path],
    policy_inputs: Sequence[str | Path],
    repository: str,
    run_id: str,
    workflow_ref: str,
    workflow_sha: str,
    event: str,
) -> dict[str, str]:
    identity = _identity(
        repository=repository,
        run_id=run_id,
        workflow_ref=workflow_ref,
        workflow_sha=workflow_sha,
        event=event,
    )
    root = _trusted_repository_root(repository_root)
    head = _git_head(root)
    config_digest = _digest_input_files(root, config_inputs, "config_inputs")
    policy_digest = _digest_input_files(root, policy_inputs, "policy_inputs")
    if _git_head(root) != head:
        raise RetryContextError("repository HEAD changed while retry context was built")
    return {
        "repository": identity["repository"],
        "run_id": identity["run_id"],
        "source_sha": head,
        "source_revision": head,
        "workflow_ref": identity["workflow_ref"],
        "workflow_sha": identity["workflow_sha"],
        "event": identity["event"],
        "config_digest": config_digest,
        "policy_digest": policy_digest,
    }


def build_consumer_retry_context(
    *,
    repository_root: Path,
    config_inputs: Sequence[str | Path],
    policy_inputs: Sequence[str | Path],
    repository: str,
    run_id: str,
    workflow_ref: str,
    workflow_sha: str,
    event: str,
) -> dict[str, str]:
    """Build immutable retry fields shared by any current-run consumer."""

    return _build_consumer_context(
        repository_root=repository_root,
        config_inputs=config_inputs,
        policy_inputs=policy_inputs,
        repository=repository,
        run_id=run_id,
        workflow_ref=workflow_ref,
        workflow_sha=workflow_sha,
        event=event,
    )


def build_retry_provenance(
    *,
    repository_root: Path,
    config_inputs: Sequence[str | Path],
    policy_inputs: Sequence[str | Path],
    repository: str,
    run_id: str,
    run_attempt: str,
    workflow_ref: str,
    workflow_sha: str,
    event: str,
    artifact: str,
) -> dict[str, str]:
    """Build the full retry provenance sidecar fields for one producer artifact."""

    attempt = _require_positive_decimal(run_attempt, "run_attempt")
    artifact_name = _require_text(artifact, "artifact")
    context = _build_consumer_context(
        repository_root=repository_root,
        config_inputs=config_inputs,
        policy_inputs=policy_inputs,
        repository=repository,
        run_id=run_id,
        workflow_ref=workflow_ref,
        workflow_sha=workflow_sha,
        event=event,
    )
    return {
        "repository": context["repository"],
        "run_id": context["run_id"],
        "run_attempt": attempt,
        "source_sha": context["source_sha"],
        "source_revision": context["source_revision"],
        "workflow_ref": context["workflow_ref"],
        "workflow_sha": context["workflow_sha"],
        "event": context["event"],
        "config_digest": context["config_digest"],
        "policy_digest": context["policy_digest"],
        "artifact": artifact_name,
    }


def _validated_context(
    value: object, *, expected_fields: frozenset[str], field: str
) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise RetryContextError(f"{field} must be an object")
    _require_exact_fields(value, expected_fields, field)
    context = {
        "repository": _require_text(value["repository"], f"{field}.repository"),
        "run_id": _require_positive_decimal(value["run_id"], f"{field}.run_id"),
        "source_sha": _require_sha(value["source_sha"], f"{field}.source_sha"),
        "source_revision": _require_sha(
            value["source_revision"], f"{field}.source_revision"
        ),
        "workflow_ref": _require_text(value["workflow_ref"], f"{field}.workflow_ref"),
        "workflow_sha": _require_sha(value["workflow_sha"], f"{field}.workflow_sha"),
        "event": _require_text(value["event"], f"{field}.event"),
        "config_digest": _require_digest(
            value["config_digest"], f"{field}.config_digest"
        ),
        "policy_digest": _require_digest(
            value["policy_digest"], f"{field}.policy_digest"
        ),
    }
    if "run_attempt" in expected_fields:
        context["run_attempt"] = _require_positive_decimal(
            value["run_attempt"], f"{field}.run_attempt"
        )
    if "artifact" in expected_fields:
        context["artifact"] = _require_text(value["artifact"], f"{field}.artifact")
    return context


def _require_digest(value: object, field: str) -> str:
    text = _require_text(value, field)
    if re.fullmatch(r"[0-9a-f]{64}", text) is None:
        raise RetryContextError(f"{field} must be lowercase SHA-256")
    return text


def _assert_context_matches(
    actual: Mapping[str, str], expected: Mapping[str, str], field: str
) -> None:
    for name, expected_value in expected.items():
        if actual[name] != expected_value:
            raise RetryContextError(f"{field}.{name} mismatch")


def validate_consumer_retry_context(
    value: object,
    *,
    repository_root: Path,
    config_inputs: Sequence[str | Path],
    policy_inputs: Sequence[str | Path],
    repository: str,
    run_id: str,
    workflow_ref: str,
    workflow_sha: str,
    event: str,
) -> dict[str, str]:
    """Verify consumer retry fields against current source and declared inputs."""

    actual = _validated_context(
        value,
        expected_fields=CONSUMER_RETRY_CONTEXT_FIELDS,
        field="consumer retry context",
    )
    expected = _build_consumer_context(
        repository_root=repository_root,
        config_inputs=config_inputs,
        policy_inputs=policy_inputs,
        repository=repository,
        run_id=run_id,
        workflow_ref=workflow_ref,
        workflow_sha=workflow_sha,
        event=event,
    )
    _assert_context_matches(actual, expected, "consumer retry context")
    return actual


def validate_retry_provenance(
    value: object,
    *,
    repository_root: Path,
    config_inputs: Sequence[str | Path],
    policy_inputs: Sequence[str | Path],
    repository: str,
    run_id: str,
    run_attempt: str,
    workflow_ref: str,
    workflow_sha: str,
    event: str,
    artifact: str,
) -> dict[str, str]:
    """Verify one producer retry provenance mapping without trusting prior runs."""

    actual = _validated_context(
        value,
        expected_fields=RETRY_PROVENANCE_FIELDS,
        field="retry provenance",
    )
    expected = build_retry_provenance(
        repository_root=repository_root,
        config_inputs=config_inputs,
        policy_inputs=policy_inputs,
        repository=repository,
        run_id=run_id,
        run_attempt=run_attempt,
        workflow_ref=workflow_ref,
        workflow_sha=workflow_sha,
        event=event,
        artifact=artifact,
    )
    _assert_context_matches(actual, expected, "retry provenance")
    return actual
