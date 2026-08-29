"""Create and verify current-run coverage producer provenance.

The normalized quality manifest is the consumer-facing summary.  This module
closes the trust gap before normalization: every native report is accompanied
by a small, immutable sidecar that binds its bytes to the checked-out commit
and the GitHub Actions run that produced them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import NoReturn, cast

SCHEMA_VERSION = 2
SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
UTC_TIMESTAMP_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
TOP_LEVEL_FIELDS = frozenset(
    {
        "schema_version",
        "commit_sha",
        "collected_at",
        "producer",
        "tool_versions",
        "reports",
    }
)
PRODUCER_FIELDS = frozenset(
    {
        "identity_provider",
        "repository",
        "workflow_ref",
        "workflow_sha",
        "run_id",
        "run_attempt",
        "event",
        "job",
        "artifact",
    }
)
REPORT_FIELDS = frozenset({"component", "format", "path", "sha256", "byte_size"})
ATTEMPT_POLICIES = frozenset({"exact", "at-or-before"})
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


class ProvenanceError(ValueError):
    """Raised when coverage provenance is incomplete or inconsistent."""


@dataclass(frozen=True)
class MetadataSelection:
    """One validated metadata candidate and its producing retry attempt."""

    metadata_path: Path
    manifest: dict[str, object]
    producer_attempt: int


def _json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ProvenanceError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: Path) -> object:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_json_object,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProvenanceError(f"unable to read metadata {path}: {error}") from error


def _reject_json_constant(value: str) -> NoReturn:
    raise ProvenanceError(f"invalid JSON constant: {value}")


def _require_exact_fields(
    value: Mapping[str, object], expected: frozenset[str], field: str
) -> None:
    actual = frozenset(value)
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing:
        raise ProvenanceError(f"{field} missing fields: {', '.join(missing)}")
    if unexpected:
        raise ProvenanceError(f"{field} has unexpected fields: {', '.join(unexpected)}")


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProvenanceError(f"{field} must be a non-empty string")
    if "\x00" in value or "\r" in value or "\n" in value:
        raise ProvenanceError(f"{field} contains forbidden control characters")
    return value


def _require_sha(value: object, field: str) -> str:
    text = _require_text(value, field)
    if SHA_PATTERN.fullmatch(text) is None:
        raise ProvenanceError(f"{field} must be an exact lowercase 40-character SHA")
    return text


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field)
    if SHA256_PATTERN.fullmatch(text) is None:
        raise ProvenanceError(f"{field} must be lowercase SHA-256")
    return text


def _require_positive_decimal(value: object, field: str) -> str:
    text = _require_text(value, field)
    if not text.isdecimal() or int(text) < 1:
        raise ProvenanceError(f"{field} must be a positive decimal identifier")
    return text


def _validate_attempt_policy(value: str) -> str:
    if value not in ATTEMPT_POLICIES:
        raise ProvenanceError("producer attempt policy is invalid")
    return value


def _validate_retry_provenance(
    value: object,
    *,
    field: str,
    producer: Mapping[str, object],
    commit_sha: str,
) -> dict[str, str]:
    """Validate the complete identity required to reuse a prior retry artifact."""

    if not isinstance(value, Mapping):
        raise ProvenanceError(f"{field} must be an object")
    _require_exact_fields(value, RETRY_PROVENANCE_FIELDS, field)
    provenance = {
        "repository": _require_text(value["repository"], f"{field}.repository"),
        "run_id": _require_positive_decimal(value["run_id"], f"{field}.run_id"),
        "run_attempt": _require_positive_decimal(
            value["run_attempt"], f"{field}.run_attempt"
        ),
        "source_sha": _require_sha(value["source_sha"], f"{field}.source_sha"),
        "source_revision": _require_sha(
            value["source_revision"], f"{field}.source_revision"
        ),
        "workflow_ref": _require_text(value["workflow_ref"], f"{field}.workflow_ref"),
        "workflow_sha": _require_sha(value["workflow_sha"], f"{field}.workflow_sha"),
        "event": _require_text(value["event"], f"{field}.event"),
        "config_digest": _require_sha256(
            value["config_digest"], f"{field}.config_digest"
        ),
        "policy_digest": _require_sha256(
            value["policy_digest"], f"{field}.policy_digest"
        ),
        "artifact": _require_text(value["artifact"], f"{field}.artifact"),
    }
    if provenance["source_sha"] != commit_sha:
        raise ProvenanceError(f"{field}.source_sha does not bind commit_sha")
    if provenance["source_revision"] != commit_sha:
        raise ProvenanceError(f"{field}.source_revision does not bind commit_sha")
    for name in (
        "repository",
        "run_id",
        "run_attempt",
        "workflow_ref",
        "workflow_sha",
        "event",
        "artifact",
    ):
        if provenance[name] != producer[name]:
            raise ProvenanceError(f"{field}.{name} does not bind producer")
    return provenance


def _validate_consumer_retry_context(
    value: object,
    *,
    expected_sha: str,
    expected_repository: str,
    expected_run_id: str,
    expected_workflow_ref: str | None,
    expected_workflow_sha: str | None,
    expected_event: str | None,
    expected_artifact: str,
) -> dict[str, str]:
    """Validate immutable consumer context before candidate-specific binding."""

    if not isinstance(value, Mapping):
        raise ProvenanceError("consumer retry context must be an object")
    _require_exact_fields(
        value, CONSUMER_RETRY_CONTEXT_FIELDS, "consumer retry context"
    )
    if (
        expected_workflow_ref is None
        or expected_workflow_sha is None
        or expected_event is None
    ):
        raise ProvenanceError(
            "candidate selection requires workflow ref, workflow SHA, and event"
        )
    sha = _require_sha(expected_sha, "expected_sha")
    producer = {
        "repository": _require_text(expected_repository, "expected_repository"),
        "run_id": _require_positive_decimal(expected_run_id, "expected_run_id"),
        "run_attempt": "1",
        "workflow_ref": _require_text(expected_workflow_ref, "expected_workflow_ref"),
        "workflow_sha": _require_sha(expected_workflow_sha, "expected_workflow_sha"),
        "event": _require_text(expected_event, "expected_event"),
        "artifact": _require_text(expected_artifact, "expected_artifact"),
    }
    full_context = dict(value)
    full_context["run_attempt"] = "1"
    full_context["artifact"] = producer["artifact"]
    validated = _validate_retry_provenance(
        full_context,
        field="consumer retry context",
        producer=producer,
        commit_sha=sha,
    )
    return {name: validated[name] for name in sorted(CONSUMER_RETRY_CONTEXT_FIELDS)}


def _require_utc_timestamp(value: object, field: str) -> str:
    text = _require_text(value, field)
    if UTC_TIMESTAMP_PATTERN.fullmatch(text) is None:
        raise ProvenanceError(f"{field} must be a UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(f"{text[:-1]}+00:00")
    except ValueError as error:
        raise ProvenanceError(f"{field} must be a valid UTC timestamp") from error
    if parsed.tzinfo != UTC:
        raise ProvenanceError(f"{field} must be UTC")
    return text


def _git_head(repository_root: Path) -> str:
    git = shutil.which("git")
    if git is None:
        raise ProvenanceError("git is unavailable; current HEAD cannot be verified")
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
        raise ProvenanceError(
            f"unable to resolve current repository HEAD: {error}"
        ) from error
    return _require_sha(result.stdout.strip(), "repository HEAD")


def _repository_root(path: Path) -> Path:
    try:
        root = path.resolve(strict=True)
    except OSError as error:
        raise ProvenanceError(f"repository root is unavailable: {path}") from error
    if not root.is_dir():
        raise ProvenanceError(f"repository root is not a directory: {root}")
    return root


def _relative_path(value: str, field: str) -> PurePosixPath:
    text = _require_text(value, field)
    if "\\" in text or re.match(r"^[A-Za-z]:", text):
        raise ProvenanceError(f"{field} must be a safe repository-relative POSIX path")
    path = PurePosixPath(text)
    if (
        path.is_absolute()
        or text != path.as_posix()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ProvenanceError(f"{field} must be a safe repository-relative POSIX path")
    return path


def _is_link_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    isjunction = getattr(os.path, "isjunction", None)
    return bool(isjunction is not None and isjunction(path))


def _reject_linked_ancestors(root: Path, path: Path, field: str) -> None:
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise ProvenanceError(f"{field} must stay inside the repository") from error
    current = root
    for part in relative.parts:
        current /= part
        if current.exists() and _is_link_or_junction(current):
            raise ProvenanceError(f"{field} traverses a symlink or junction: {current}")


def _safe_report(root: Path, relative: str, field: str) -> Path:
    posix = _relative_path(relative, field)
    path = root.joinpath(*posix.parts)
    _reject_linked_ancestors(root, path, field)
    if not path.is_file():
        raise ProvenanceError(f"{field} does not identify a report file: {relative}")
    if _is_link_or_junction(path):
        raise ProvenanceError(f"{field} must not be a symlink or junction: {relative}")
    if path.stat().st_size <= 0:
        raise ProvenanceError(f"{field} must be a non-empty report: {relative}")
    return path


def _safe_path_argument(root: Path, path: Path, field: str) -> Path:
    candidate = path if path.is_absolute() else root / path
    candidate = Path(os.path.abspath(candidate))
    _reject_linked_ancestors(root, candidate, field)
    return candidate


def _safe_metadata_input(root: Path, path: Path) -> Path:
    candidate = _safe_path_argument(root, path, "metadata path")
    if not candidate.is_file() or candidate.stat().st_size <= 0:
        raise ProvenanceError(f"metadata path must be a non-empty file: {candidate}")
    if _is_link_or_junction(candidate):
        raise ProvenanceError(
            f"metadata path must not be a symlink or junction: {candidate}"
        )
    return candidate


def _safe_output(root: Path, path: Path) -> Path:
    candidate = _safe_path_argument(root, path, "output path")
    if candidate.exists() and _is_link_or_junction(candidate):
        raise ProvenanceError(
            f"output path must not be a symlink or junction: {candidate}"
        )
    candidate.parent.mkdir(parents=True, exist_ok=True)
    _reject_linked_ancestors(root, candidate, "output path")
    return candidate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_identity(
    *,
    expected_sha: str,
    identity_provider: str,
    repository: str,
    workflow_ref: str,
    workflow_sha: str,
    run_id: str,
    run_attempt: str,
    event: str,
    job: str,
    artifact: str,
    collected_at: str,
) -> tuple[str, dict[str, str], str]:
    sha = _require_sha(expected_sha, "expected_sha")
    if identity_provider != "github-actions":
        raise ProvenanceError("identity_provider must equal 'github-actions'")
    producer = {
        "identity_provider": identity_provider,
        "repository": _require_text(repository, "repository"),
        "workflow_ref": _require_text(workflow_ref, "workflow_ref"),
        "workflow_sha": _require_sha(workflow_sha, "workflow_sha"),
        "run_id": _require_positive_decimal(run_id, "run_id"),
        "run_attempt": _require_positive_decimal(run_attempt, "run_attempt"),
        "event": _require_text(event, "event"),
        "job": _require_text(job, "job"),
        "artifact": _require_text(artifact, "artifact"),
    }
    return sha, producer, _require_utc_timestamp(collected_at, "collected_at")


def _validate_tool_versions(tool_versions: Mapping[str, str]) -> dict[str, str]:
    if not tool_versions:
        raise ProvenanceError("tool_versions must contain exact producer versions")
    validated: dict[str, str] = {}
    for name, version in sorted(tool_versions.items()):
        tool_name = _require_text(name, "tool_versions name")
        tool_version = _require_text(version, f"tool_versions.{tool_name}")
        if tool_version.casefold() in {"latest", "unknown", "unavailable"}:
            raise ProvenanceError(f"tool_versions.{tool_name} is not an exact version")
        validated[tool_name] = tool_version
    return validated


def _atomic_write_json(root: Path, output_path: Path, payload: object) -> None:
    output = _safe_output(root, output_path)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{output.name}.",
            suffix=".tmp",
            dir=output.parent,
            delete=False,
        ) as stream:
            temporary_name = stream.name
            json.dump(payload, stream, indent=2, sort_keys=True, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, output)
        temporary_name = None
    finally:
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink()
            except FileNotFoundError:
                pass


def write_metadata(
    *,
    repository_root: Path,
    output_path: Path,
    reports: Sequence[tuple[str, str, str, str]],
    tool_versions: Mapping[str, str],
    expected_sha: str,
    identity_provider: str,
    repository: str,
    workflow_ref: str,
    workflow_sha: str,
    run_id: str,
    run_attempt: str,
    event: str,
    job: str,
    artifact: str,
    collected_at: str,
    retry_provenance: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Write one producer sidecar after validating its report bytes."""

    root = _repository_root(repository_root)
    sha, producer, timestamp = _validate_identity(
        expected_sha=expected_sha,
        identity_provider=identity_provider,
        repository=repository,
        workflow_ref=workflow_ref,
        workflow_sha=workflow_sha,
        run_id=run_id,
        run_attempt=run_attempt,
        event=event,
        job=job,
        artifact=artifact,
        collected_at=collected_at,
    )
    head = _git_head(root)
    if sha != head:
        raise ProvenanceError(
            f"expected_sha does not match current repository HEAD: {sha} != {head}"
        )
    if not reports:
        raise ProvenanceError("reports must contain at least one report")
    records: list[dict[str, object]] = []
    identities: set[tuple[str, str, str]] = set()
    for index, (component, report_format, source_path, canonical_path) in enumerate(
        reports
    ):
        report_component = _require_text(component, f"reports[{index}].component")
        report_kind = _require_text(report_format, f"reports[{index}].format")
        canonical = _relative_path(
            canonical_path, f"reports[{index}].canonical_path"
        ).as_posix()
        identity = (report_component, report_kind, canonical)
        if identity in identities:
            raise ProvenanceError("duplicate report identity: " + "/".join(identity))
        identities.add(identity)
        source = _safe_report(root, source_path, f"reports[{index}].source_path")
        records.append(
            {
                "component": report_component,
                "format": report_kind,
                "path": canonical,
                "sha256": _sha256(source),
                "byte_size": source.stat().st_size,
            }
        )
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "commit_sha": sha,
        "collected_at": timestamp,
        "producer": producer,
        "tool_versions": _validate_tool_versions(tool_versions),
        "reports": sorted(records, key=lambda item: cast(str, item["path"])),
    }
    if retry_provenance is not None:
        payload["retry_provenance"] = _validate_retry_provenance(
            retry_provenance,
            field="retry_provenance",
            producer=producer,
            commit_sha=sha,
        )
    _atomic_write_json(root, output_path, payload)
    return payload


def _validate_document(document: object, *, field: str) -> dict[str, object]:
    if not isinstance(document, dict):
        raise ProvenanceError(f"{field} must be a JSON object")
    expected_fields = TOP_LEVEL_FIELDS
    if "retry_provenance" in document:
        expected_fields = TOP_LEVEL_FIELDS | frozenset({"retry_provenance"})
    _require_exact_fields(document, expected_fields, field)
    if document["schema_version"] != SCHEMA_VERSION:
        raise ProvenanceError(f"{field}.schema_version must equal {SCHEMA_VERSION}")
    _require_sha(document["commit_sha"], f"{field}.commit_sha")
    _require_utc_timestamp(document["collected_at"], f"{field}.collected_at")
    producer = document["producer"]
    if not isinstance(producer, dict):
        raise ProvenanceError(f"{field}.producer must be an object")
    _require_exact_fields(producer, PRODUCER_FIELDS, f"{field}.producer")
    if producer["identity_provider"] != "github-actions":
        raise ProvenanceError(
            f"{field}.producer.identity_provider must equal 'github-actions'"
        )
    for name in ("repository", "workflow_ref", "event", "job", "artifact"):
        _require_text(producer[name], f"{field}.producer.{name}")
    _require_sha(producer["workflow_sha"], f"{field}.producer.workflow_sha")
    _require_positive_decimal(producer["run_id"], f"{field}.producer.run_id")
    _require_positive_decimal(producer["run_attempt"], f"{field}.producer.run_attempt")
    if "retry_provenance" in document:
        _validate_retry_provenance(
            document["retry_provenance"],
            field=f"{field}.retry_provenance",
            producer=producer,
            commit_sha=cast(str, document["commit_sha"]),
        )
    tools = document["tool_versions"]
    if not isinstance(tools, dict) or not all(
        isinstance(name, str) and isinstance(version, str)
        for name, version in tools.items()
    ):
        raise ProvenanceError(f"{field}.tool_versions must be a string map")
    _validate_tool_versions(cast(dict[str, str], tools))
    reports = document["reports"]
    if not isinstance(reports, list):
        raise ProvenanceError(f"{field}.reports must be an array")
    if not reports:
        raise ProvenanceError(f"{field}.reports must contain at least one report")
    identities: set[tuple[str, str, str]] = set()
    for index, report in enumerate(reports):
        report_field = f"{field}.reports[{index}]"
        if not isinstance(report, dict):
            raise ProvenanceError(f"{report_field} must be an object")
        _require_exact_fields(report, REPORT_FIELDS, report_field)
        component = _require_text(report["component"], f"{report_field}.component")
        report_format = _require_text(report["format"], f"{report_field}.format")
        path = _relative_path(
            _require_text(report["path"], f"{report_field}.path"),
            f"{report_field}.path",
        ).as_posix()
        sha256 = _require_text(report["sha256"], f"{report_field}.sha256")
        if SHA256_PATTERN.fullmatch(sha256) is None:
            raise ProvenanceError(f"{report_field}.sha256 must be lowercase SHA-256")
        byte_size = report["byte_size"]
        if (
            isinstance(byte_size, bool)
            or not isinstance(byte_size, int)
            or byte_size < 1
        ):
            raise ProvenanceError(f"{report_field}.byte_size must be positive")
        identity = (component, report_format, path)
        if identity in identities:
            raise ProvenanceError("duplicate report identity: " + "/".join(identity))
        identities.add(identity)
    return document


def verify_metadata(
    *,
    repository_root: Path,
    metadata_paths: Sequence[Path],
    expected_sha: str,
    expected_repository: str,
    expected_run_id: str,
    expected_run_attempt: str,
    expected_job: str,
    expected_artifact: str,
    expected_workflow_ref: str | None = None,
    expected_workflow_sha: str | None = None,
    expected_event: str | None = None,
    producer_attempt_policy: str = "exact",
    expected_retry_provenance: Mapping[str, str] | None = None,
) -> list[dict[str, object]]:
    """Verify sidecars against current report bytes and the current run.

    Earlier producer attempts require the explicit ``at-or-before`` policy and
    a complete retry provenance identity.  The default remains exact attempt
    matching for all current callers.
    """

    root = _repository_root(repository_root)
    sha = _require_sha(expected_sha, "expected_sha")
    if _git_head(root) != sha:
        raise ProvenanceError("expected_sha does not match current repository HEAD")
    repository = _require_text(expected_repository, "expected_repository")
    run_id = _require_positive_decimal(expected_run_id, "expected_run_id")
    run_attempt = _require_positive_decimal(
        expected_run_attempt, "expected_run_attempt"
    )
    policy = _validate_attempt_policy(producer_attempt_policy)
    job = _require_text(expected_job, "expected_job")
    artifact = _require_text(expected_artifact, "expected_artifact")
    if not metadata_paths:
        raise ProvenanceError("metadata_paths must contain at least one sidecar")
    documents: list[dict[str, object]] = []
    for index, metadata_path in enumerate(metadata_paths):
        safe_path = _safe_metadata_input(root, metadata_path)
        document = _validate_document(_load_json(safe_path), field=f"metadata[{index}]")
        if document["commit_sha"] != sha:
            raise ProvenanceError(f"metadata[{index}].commit_sha mismatch")
        producer = cast(dict[str, object], document["producer"])
        expectations = {
            "repository": repository,
            "run_id": run_id,
            "job": job,
            "artifact": artifact,
        }
        if policy == "exact":
            expectations["run_attempt"] = run_attempt
        if expected_workflow_ref is not None:
            expectations["workflow_ref"] = _require_text(
                expected_workflow_ref, "expected_workflow_ref"
            )
        if expected_workflow_sha is not None:
            expectations["workflow_sha"] = _require_sha(
                expected_workflow_sha, "expected_workflow_sha"
            )
        if expected_event is not None:
            expectations["event"] = _require_text(expected_event, "expected_event")
        for name, expected in expectations.items():
            if producer[name] != expected:
                raise ProvenanceError(
                    f"metadata[{index}].producer.{name} mismatch: "
                    f"expected {expected!r}, got {producer[name]!r}"
                )
        producer_attempt = _require_positive_decimal(
            producer["run_attempt"], f"metadata[{index}].producer.run_attempt"
        )
        if policy == "at-or-before":
            if int(producer_attempt) > int(run_attempt):
                raise ProvenanceError(
                    f"metadata[{index}].producer.run_attempt is from the future"
                )
            if expected_retry_provenance is None:
                raise ProvenanceError("expected retry provenance is required")
            if "retry_provenance" not in document:
                raise ProvenanceError(f"metadata[{index}] retry provenance is required")
            actual_retry_provenance = _validate_retry_provenance(
                document["retry_provenance"],
                field=f"metadata[{index}].retry_provenance",
                producer=producer,
                commit_sha=sha,
            )
            expected_provenance = _validate_retry_provenance(
                expected_retry_provenance,
                field="expected retry provenance",
                producer=producer,
                commit_sha=sha,
            )
            for name, expected in expected_provenance.items():
                if actual_retry_provenance[name] != expected:
                    raise ProvenanceError(
                        f"metadata[{index}].retry_provenance.{name} mismatch: "
                        f"expected {expected!r}, got {actual_retry_provenance[name]!r}"
                    )
        reports = cast(list[dict[str, object]], document["reports"])
        for report_index, report in enumerate(reports):
            report_path = cast(str, report["path"])
            actual = _safe_report(
                root, report_path, f"metadata[{index}].reports[{report_index}].path"
            )
            if actual.stat().st_size != report["byte_size"]:
                raise ProvenanceError(
                    f"metadata[{index}].reports[{report_index}].byte_size mismatch"
                )
            if _sha256(actual) != report["sha256"]:
                raise ProvenanceError(
                    f"metadata[{index}].reports[{report_index}].sha256 mismatch"
                )
        documents.append(document)
    return documents


def select_metadata(
    *,
    repository_root: Path,
    metadata_paths: Sequence[Path],
    expected_sha: str,
    expected_repository: str,
    expected_run_id: str,
    expected_run_attempt: str,
    expected_job: str,
    expected_artifact: str,
    expected_workflow_ref: str | None = None,
    expected_workflow_sha: str | None = None,
    expected_event: str | None = None,
    producer_attempt_policy: str = "exact",
    expected_retry_provenance: Mapping[str, str] | None = None,
) -> list[MetadataSelection]:
    """Return validated sidecars with their selected producer attempts."""

    documents = verify_metadata(
        repository_root=repository_root,
        metadata_paths=metadata_paths,
        expected_sha=expected_sha,
        expected_repository=expected_repository,
        expected_run_id=expected_run_id,
        expected_run_attempt=expected_run_attempt,
        expected_job=expected_job,
        expected_artifact=expected_artifact,
        expected_workflow_ref=expected_workflow_ref,
        expected_workflow_sha=expected_workflow_sha,
        expected_event=expected_event,
        producer_attempt_policy=producer_attempt_policy,
        expected_retry_provenance=expected_retry_provenance,
    )
    root = _repository_root(repository_root)
    selections: list[MetadataSelection] = []
    for path, document in zip(metadata_paths, documents, strict=True):
        producer = cast(dict[str, object], document["producer"])
        selections.append(
            MetadataSelection(
                metadata_path=_safe_metadata_input(root, path),
                manifest=document,
                producer_attempt=int(cast(str, producer["run_attempt"])),
            )
        )
    return selections


def select_metadata_candidates(
    *,
    repository_root: Path,
    metadata_paths: Collection[Path],
    expected_sha: str,
    expected_repository: str,
    expected_run_id: str,
    expected_run_attempt: str,
    expected_job: str,
    expected_artifact: str,
    expected_workflow_ref: str | None = None,
    expected_workflow_sha: str | None = None,
    expected_event: str | None = None,
    consumer_retry_context: Mapping[str, str],
) -> MetadataSelection:
    """Choose the highest valid producer attempt from metadata candidates.

    Every candidate is validated against the same immutable consumer context.
    Invalid, foreign, future, and duplicate attempts reject the entire
    candidate set rather than being silently ignored.
    """

    root = _repository_root(repository_root)
    sha = _require_sha(expected_sha, "expected_sha")
    run_attempt = _require_positive_decimal(
        expected_run_attempt, "expected_run_attempt"
    )
    context = _validate_consumer_retry_context(
        consumer_retry_context,
        expected_sha=sha,
        expected_repository=expected_repository,
        expected_run_id=expected_run_id,
        expected_workflow_ref=expected_workflow_ref,
        expected_workflow_sha=expected_workflow_sha,
        expected_event=expected_event,
        expected_artifact=expected_artifact,
    )
    if not metadata_paths:
        raise ProvenanceError("metadata_paths must contain at least one candidate")

    seen_paths: set[Path] = set()
    selections: dict[int, MetadataSelection] = {}
    for index, metadata_path in enumerate(metadata_paths):
        safe_path = _safe_metadata_input(root, metadata_path)
        if safe_path in seen_paths:
            raise ProvenanceError(f"duplicate metadata candidate: {safe_path}")
        seen_paths.add(safe_path)
        document = _validate_document(
            _load_json(safe_path), field=f"metadata candidate[{index}]"
        )
        producer = cast(dict[str, object], document["producer"])
        producer_attempt = _require_positive_decimal(
            producer["run_attempt"],
            f"metadata candidate[{index}].producer.run_attempt",
        )
        expected_retry_provenance = {
            **context,
            "run_attempt": producer_attempt,
            "artifact": _require_text(expected_artifact, "expected_artifact"),
        }
        candidate = select_metadata(
            repository_root=root,
            metadata_paths=[safe_path],
            expected_sha=sha,
            expected_repository=expected_repository,
            expected_run_id=expected_run_id,
            expected_run_attempt=run_attempt,
            expected_job=expected_job,
            expected_artifact=expected_artifact,
            expected_workflow_ref=expected_workflow_ref,
            expected_workflow_sha=expected_workflow_sha,
            expected_event=expected_event,
            producer_attempt_policy="at-or-before",
            expected_retry_provenance=expected_retry_provenance,
        )[0]
        if candidate.producer_attempt in selections:
            raise ProvenanceError(
                "duplicate producer attempt in metadata candidates: "
                f"{candidate.producer_attempt}"
            )
        selections[candidate.producer_attempt] = candidate
    return selections[max(selections)]


def _contract_reports(contract_path: Path) -> set[tuple[str, str, str]]:
    contract = _load_json(contract_path)
    if not isinstance(contract, dict):
        raise ProvenanceError("quality contract must be a JSON object")
    declarations = contract.get("coverage_reports")
    if not isinstance(declarations, list) or not declarations:
        raise ProvenanceError("quality contract coverage_reports must be non-empty")
    expected: set[tuple[str, str, str]] = set()
    for index, declaration in enumerate(declarations):
        if not isinstance(declaration, dict):
            raise ProvenanceError(f"coverage_reports[{index}] must be an object")
        try:
            component = _require_text(
                declaration["component"], f"coverage_reports[{index}].component"
            )
            report_format = _require_text(
                declaration["format"], f"coverage_reports[{index}].format"
            )
            path = _relative_path(
                _require_text(declaration["path"], f"coverage_reports[{index}].path"),
                f"coverage_reports[{index}].path",
            ).as_posix()
        except KeyError as error:
            raise ProvenanceError(
                f"coverage_reports[{index}] is missing {error.args[0]}"
            ) from error
        identity = (component, report_format, path)
        if identity in expected:
            raise ProvenanceError(
                "quality contract contains duplicate report: " + "/".join(identity)
            )
        expected.add(identity)
    return expected


def merge_metadata(
    *,
    repository_root: Path,
    contract_path: Path,
    metadata_paths: Sequence[Path],
    output_path: Path,
    tool_versions: Mapping[str, str],
    producer_expectations: Mapping[Path, tuple[str, str]],
    expected_sha: str,
    identity_provider: str,
    repository: str,
    workflow_ref: str,
    workflow_sha: str,
    run_id: str,
    run_attempt: str,
    event: str,
    job: str,
    artifact: str,
    collected_at: str,
) -> dict[str, object]:
    """Merge sidecars only when they exactly cover the canonical registry."""

    root = _repository_root(repository_root)
    sha, producer, timestamp = _validate_identity(
        expected_sha=expected_sha,
        identity_provider=identity_provider,
        repository=repository,
        workflow_ref=workflow_ref,
        workflow_sha=workflow_sha,
        run_id=run_id,
        run_attempt=run_attempt,
        event=event,
        job=job,
        artifact=artifact,
        collected_at=collected_at,
    )
    contract = _safe_metadata_input(root, contract_path)
    safe_metadata_paths = [_safe_metadata_input(root, path) for path in metadata_paths]
    safe_expectations: dict[Path, tuple[str, str]] = {}
    for expectation_path, (
        expected_job,
        expected_artifact,
    ) in producer_expectations.items():
        safe_path = _safe_metadata_input(root, expectation_path)
        if safe_path in safe_expectations:
            raise ProvenanceError(f"duplicate producer expectation: {safe_path}")
        safe_expectations[safe_path] = (
            _require_text(expected_job, "producer expectation job"),
            _require_text(expected_artifact, "producer expectation artifact"),
        )
    if set(safe_metadata_paths) != set(safe_expectations):
        raise ProvenanceError("producer expectations must exactly match metadata paths")
    documents: list[dict[str, object]] = []
    for metadata_path in safe_metadata_paths:
        expected_job, expected_artifact = safe_expectations[metadata_path]
        documents.extend(
            verify_metadata(
                repository_root=root,
                metadata_paths=[metadata_path],
                expected_sha=sha,
                expected_repository=repository,
                expected_run_id=run_id,
                expected_run_attempt=run_attempt,
                expected_job=expected_job,
                expected_artifact=expected_artifact,
                expected_workflow_ref=workflow_ref,
                expected_workflow_sha=workflow_sha,
                expected_event=event,
            )
        )
    expected_reports = _contract_reports(contract)
    reports: list[dict[str, object]] = []
    actual_reports: set[tuple[str, str, str]] = set()
    merged_tools = _validate_tool_versions(tool_versions)
    for document in documents:
        document_tools = cast(dict[str, str], document["tool_versions"])
        for name, version in document_tools.items():
            existing = merged_tools.get(name)
            if existing is not None and existing != version:
                raise ProvenanceError(
                    f"conflicting exact tool version for {name}: {existing!r} != {version!r}"
                )
            merged_tools[name] = version
        for report in cast(list[dict[str, object]], document["reports"]):
            identity = (
                cast(str, report["component"]),
                cast(str, report["format"]),
                cast(str, report["path"]),
            )
            if identity in actual_reports:
                raise ProvenanceError(
                    "duplicate report identity: " + "/".join(identity)
                )
            actual_reports.add(identity)
            reports.append(report)
    missing = sorted(expected_reports - actual_reports)
    unexpected = sorted(actual_reports - expected_reports)
    if missing or unexpected or len(reports) != len(expected_reports):
        details: list[str] = []
        if missing:
            details.append("missing=" + ", ".join("/".join(item) for item in missing))
        if unexpected:
            details.append(
                "unexpected=" + ", ".join("/".join(item) for item in unexpected)
            )
        details.append(f"count={len(reports)} expected={len(expected_reports)}")
        raise ProvenanceError(
            "canonical report registry mismatch: " + "; ".join(details)
        )
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "commit_sha": sha,
        "collected_at": timestamp,
        "producer": producer,
        "tool_versions": dict(sorted(merged_tools.items())),
        "reports": sorted(reports, key=lambda item: cast(str, item["path"])),
    }
    _atomic_write_json(root, output_path, payload)
    return payload


def _parse_tool(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("tool version must use NAME=VERSION")
    name, version = value.split("=", 1)
    try:
        return (
            _require_text(name, "tool name"),
            _require_text(version, f"tool version {name}"),
        )
    except ProvenanceError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def _parse_report(value: str) -> tuple[str, str, str, str]:
    parts = value.split("|")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError(
            "report must use COMPONENT|FORMAT|SOURCE_PATH|CANONICAL_PATH"
        )
    try:
        component, report_format, source_path, canonical_path = (
            _require_text(part, "report field") for part in parts
        )
    except ProvenanceError as error:
        raise argparse.ArgumentTypeError(str(error)) from error
    return component, report_format, source_path, canonical_path


def _parse_producer_expectation(value: str) -> tuple[Path, str, str]:
    parts = value.split("|")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError(
            "producer expectation must use METADATA_PATH|JOB|ARTIFACT"
        )
    try:
        metadata_path, job, artifact = (
            _require_text(part, "producer expectation field") for part in parts
        )
    except ProvenanceError as error:
        raise argparse.ArgumentTypeError(str(error)) from error
    return Path(metadata_path), job, artifact


def _tool_map(values: Sequence[tuple[str, str]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name, version in values:
        if name in result:
            raise ProvenanceError(f"duplicate tool version entry: {name}")
        result[name] = version
    return result


def _producer_expectation_map(
    values: Sequence[tuple[Path, str, str]],
) -> dict[Path, tuple[str, str]]:
    result: dict[Path, tuple[str, str]] = {}
    for path, job, artifact in values:
        if path in result:
            raise ProvenanceError(f"duplicate producer expectation entry: {path}")
        result[path] = (job, artifact)
    return result


def _parse_retry_provenance(value: str) -> tuple[str, str]:
    key, separator, item = value.partition("=")
    if not separator or not key or not item:
        raise argparse.ArgumentTypeError("retry provenance must use KEY=VALUE")
    return key, item


def _retry_provenance_map(
    values: Sequence[tuple[str, str]], *, field: str
) -> dict[str, str] | None:
    if not values:
        return None
    result: dict[str, str] = {}
    for key, value in values:
        if key in result:
            raise ProvenanceError(f"{field} contains duplicate field: {key}")
        result[key] = value
    return result


def _add_identity_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--identity-provider", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--workflow-ref", required=True)
    parser.add_argument("--workflow-sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--job", required=True)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--collected-at", required=True)


def _add_verify_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--metadata", action="append", type=Path, required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--expected-repository", required=True)
    parser.add_argument("--expected-run-id", required=True)
    parser.add_argument("--expected-run-attempt", required=True)
    parser.add_argument("--expected-job", required=True)
    parser.add_argument("--expected-artifact", required=True)
    parser.add_argument("--expected-workflow-ref")
    parser.add_argument("--expected-workflow-sha")
    parser.add_argument("--expected-event")
    parser.add_argument(
        "--producer-attempt-policy",
        choices=sorted(ATTEMPT_POLICIES),
        default="exact",
    )
    parser.add_argument(
        "--expected-retry-provenance",
        action="append",
        type=_parse_retry_provenance,
        default=[],
    )


def _parse_arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write or verify current-run coverage provenance sidecars."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    write_parser = subparsers.add_parser("write")
    write_parser.add_argument("--repository-root", type=Path, required=True)
    write_parser.add_argument("--output", type=Path, required=True)
    write_parser.add_argument(
        "--report", action="append", type=_parse_report, required=True
    )
    write_parser.add_argument(
        "--tool-version", action="append", type=_parse_tool, required=True
    )
    write_parser.add_argument(
        "--retry-provenance",
        action="append",
        type=_parse_retry_provenance,
        default=[],
    )
    _add_identity_arguments(write_parser)

    verify_parser = subparsers.add_parser("verify")
    _add_verify_arguments(verify_parser)

    select_parser = subparsers.add_parser("select")
    _add_verify_arguments(select_parser)

    merge_parser = subparsers.add_parser("merge")
    merge_parser.add_argument("--repository-root", type=Path, required=True)
    merge_parser.add_argument("--contract", type=Path, required=True)
    merge_parser.add_argument("--metadata", action="append", type=Path, required=True)
    merge_parser.add_argument("--output", type=Path, required=True)
    merge_parser.add_argument(
        "--tool-version", action="append", type=_parse_tool, required=True
    )
    merge_parser.add_argument(
        "--producer-expectation",
        action="append",
        type=_parse_producer_expectation,
        required=True,
    )
    _add_identity_arguments(merge_parser)
    return parser.parse_args(argv)


def _identity_kwargs(arguments: argparse.Namespace) -> dict[str, str]:
    return {
        "expected_sha": arguments.expected_sha,
        "identity_provider": arguments.identity_provider,
        "repository": arguments.repository,
        "workflow_ref": arguments.workflow_ref,
        "workflow_sha": arguments.workflow_sha,
        "run_id": arguments.run_id,
        "run_attempt": arguments.run_attempt,
        "event": arguments.event,
        "job": arguments.job,
        "artifact": arguments.artifact,
        "collected_at": arguments.collected_at,
    }


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parse_arguments(argv)
    try:
        if arguments.command == "write":
            write_metadata(
                repository_root=arguments.repository_root,
                output_path=arguments.output,
                reports=arguments.report,
                tool_versions=_tool_map(arguments.tool_version),
                retry_provenance=_retry_provenance_map(
                    arguments.retry_provenance,
                    field="retry provenance",
                ),
                **_identity_kwargs(arguments),
            )
        elif arguments.command == "verify":
            verify_metadata(
                repository_root=arguments.repository_root,
                metadata_paths=arguments.metadata,
                expected_sha=arguments.expected_sha,
                expected_repository=arguments.expected_repository,
                expected_run_id=arguments.expected_run_id,
                expected_run_attempt=arguments.expected_run_attempt,
                expected_job=arguments.expected_job,
                expected_artifact=arguments.expected_artifact,
                expected_workflow_ref=arguments.expected_workflow_ref,
                expected_workflow_sha=arguments.expected_workflow_sha,
                expected_event=arguments.expected_event,
                producer_attempt_policy=arguments.producer_attempt_policy,
                expected_retry_provenance=_retry_provenance_map(
                    arguments.expected_retry_provenance,
                    field="expected retry provenance",
                ),
            )
        elif arguments.command == "select":
            selections = select_metadata(
                repository_root=arguments.repository_root,
                metadata_paths=arguments.metadata,
                expected_sha=arguments.expected_sha,
                expected_repository=arguments.expected_repository,
                expected_run_id=arguments.expected_run_id,
                expected_run_attempt=arguments.expected_run_attempt,
                expected_job=arguments.expected_job,
                expected_artifact=arguments.expected_artifact,
                expected_workflow_ref=arguments.expected_workflow_ref,
                expected_workflow_sha=arguments.expected_workflow_sha,
                expected_event=arguments.expected_event,
                producer_attempt_policy=arguments.producer_attempt_policy,
                expected_retry_provenance=_retry_provenance_map(
                    arguments.expected_retry_provenance,
                    field="expected retry provenance",
                ),
            )
            print(
                json.dumps(
                    {
                        "selected_producer_attempts": [
                            selection.producer_attempt for selection in selections
                        ]
                    },
                    sort_keys=True,
                )
            )
        else:
            merge_metadata(
                repository_root=arguments.repository_root,
                contract_path=arguments.contract,
                metadata_paths=arguments.metadata,
                output_path=arguments.output,
                tool_versions=_tool_map(arguments.tool_version),
                producer_expectations=_producer_expectation_map(
                    arguments.producer_expectation
                ),
                **_identity_kwargs(arguments),
            )
    except ProvenanceError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
