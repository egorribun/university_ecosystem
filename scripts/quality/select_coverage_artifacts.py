"""Select and materialize provenance-bound coverage retry artifacts.

Each downloaded artifact is kept in its own candidate root.  The selector
accepts only a complete, exact set of logical slots, verifies every candidate
against the immutable current-run context through ``coverage_provenance``, and
materializes the chosen reports as one atomic directory replacement.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import tempfile
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, cast

from scripts.quality.coverage_provenance import (
    MetadataSelection,
    ProvenanceError,
    select_metadata_candidates,
)

_POSITIVE_DECIMAL = re.compile(r"[1-9][0-9]*$")
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")
_PORTABLE_LOGICAL_ARTIFACT = re.compile(r"[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?$")
_SHA256 = re.compile(r"[0-9a-f]{64}$")
_WINDOWS_DEVICE_ARTIFACT = re.compile(
    r"(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?$",
    re.IGNORECASE,
)
_RECEIPT_NAME = "selection-receipt.json"


class CoverageSelectionError(ValueError):
    """Raised when coverage retry candidates are unsafe or incomplete."""


@dataclass(frozen=True)
class CoverageReportSpec:
    """One report identity expected from a logical producer artifact."""

    component: str
    report_format: str
    path: str


@dataclass(frozen=True)
class CoverageArtifactSlot:
    """The immutable identity and exact report inventory of one producer."""

    logical_artifact: str
    producer_job: str
    metadata_path: str
    reports: tuple[CoverageReportSpec, ...]


@dataclass(frozen=True)
class CoverageArtifactSelection:
    """A selected physical artifact for one logical producer slot."""

    logical_artifact: str
    physical_artifact: str
    producer_attempt: int
    candidate_root: Path


@dataclass(frozen=True)
class CoverageSelectionResult:
    """The deterministic selections and the materialized receipt location."""

    selections: tuple[CoverageArtifactSelection, ...]
    receipt_path: Path


@dataclass(frozen=True)
class _Candidate:
    slot: CoverageArtifactSlot
    root: Path
    physical_artifact: str
    physical_attempt: int
    metadata: dict[str, object]
    metadata_bytes: bytes
    report_integrity: Mapping[str, tuple[str, int]]


@dataclass(frozen=True)
class _StagedCandidate:
    candidate: _Candidate
    stage_root: Path
    metadata_path: Path


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CoverageSelectionError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise CoverageSelectionError(f"invalid JSON constant: {value}")


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CoverageSelectionError(f"{field} must be a non-empty string")
    if "\x00" in value or "\r" in value or "\n" in value:
        raise CoverageSelectionError(f"{field} contains forbidden control characters")
    return value


def _safe_relative_path(value: object, field: str) -> str:
    text = _require_text(value, field)
    if "\\" in text or _WINDOWS_DRIVE.match(text):
        raise CoverageSelectionError(f"{field} must be a safe POSIX relative path")
    path = PurePosixPath(text)
    if (
        path.is_absolute()
        or text != path.as_posix()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise CoverageSelectionError(f"{field} must be a safe POSIX relative path")
    return path.as_posix()


def _is_link_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    isjunction = getattr(os.path, "isjunction", None)
    return bool(isjunction is not None and isjunction(path))


def _normal_path_text(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def _safe_candidate_root(path: Path) -> Path:
    lexical = Path(os.path.abspath(path))
    if _is_link_or_junction(lexical):
        raise CoverageSelectionError(
            f"candidate root must not be a symlink or junction: {path}"
        )
    try:
        resolved = lexical.resolve(strict=True)
    except OSError as error:
        raise CoverageSelectionError(
            f"candidate root is unavailable: {path}"
        ) from error
    if _normal_path_text(lexical) != _normal_path_text(resolved):
        raise CoverageSelectionError(
            f"candidate root traverses a symlink or junction: {path}"
        )
    if not resolved.is_dir():
        raise CoverageSelectionError(f"candidate root is not a directory: {resolved}")
    return resolved


def _safe_file(root: Path, relative: str, field: str) -> Path:
    candidate = root.joinpath(*PurePosixPath(relative).parts)
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise CoverageSelectionError(f"{field} escapes its candidate root") from error
    current = root
    for part in candidate.relative_to(root).parts:
        current /= part
        if current.exists() and _is_link_or_junction(current):
            raise CoverageSelectionError(
                f"{field} traverses a symlink or junction: {current}"
            )
    if not candidate.is_file() or _is_link_or_junction(candidate):
        raise CoverageSelectionError(f"{field} must be a regular file: {relative}")
    candidate_stat = candidate.stat()
    if candidate_stat.st_nlink != 1:
        raise CoverageSelectionError(f"{field} must not be a hard link: {relative}")
    if candidate_stat.st_size <= 0:
        raise CoverageSelectionError(f"{field} must be non-empty: {relative}")
    return candidate


def _validate_slots(
    slots: Sequence[CoverageArtifactSlot],
) -> tuple[CoverageArtifactSlot, ...]:
    if not slots:
        raise CoverageSelectionError("slots must contain at least one logical slot")
    validated: list[CoverageArtifactSlot] = []
    seen_artifacts: set[str] = set()
    for index, slot in enumerate(slots):
        artifact = _require_text(
            slot.logical_artifact, f"slots[{index}].logical_artifact"
        )
        if artifact in {".", ".."}:
            raise CoverageSelectionError(
                f"slots[{index}].logical_artifact is a reserved logical artifact"
            )
        if "/" in artifact or "\\" in artifact:
            raise CoverageSelectionError(
                f"slots[{index}].logical_artifact must not contain a path separator"
            )
        if _PORTABLE_LOGICAL_ARTIFACT.fullmatch(artifact) is None:
            raise CoverageSelectionError(
                f"slots[{index}].logical_artifact must be a portable safe slug"
            )
        if _WINDOWS_DEVICE_ARTIFACT.fullmatch(artifact) is not None:
            raise CoverageSelectionError(
                f"slots[{index}].logical_artifact must be a portable safe slug"
            )
        if artifact in seen_artifacts:
            raise CoverageSelectionError(f"duplicate logical slot: {artifact}")
        seen_artifacts.add(artifact)
        _require_text(slot.producer_job, f"slots[{index}].producer_job")
        metadata_path = _safe_relative_path(
            slot.metadata_path, f"slots[{index}].metadata_path"
        )
        if not slot.reports:
            raise CoverageSelectionError(f"slots[{index}].reports must not be empty")
        report_paths: set[str] = set()
        report_identities: set[tuple[str, str, str]] = set()
        reports: list[CoverageReportSpec] = []
        for report_index, report in enumerate(slot.reports):
            component = _require_text(
                report.component, f"slots[{index}].reports[{report_index}].component"
            )
            report_format = _require_text(
                report.report_format,
                f"slots[{index}].reports[{report_index}].report_format",
            )
            path = _safe_relative_path(
                report.path, f"slots[{index}].reports[{report_index}].path"
            )
            identity = (component, report_format, path)
            if identity in report_identities or path in report_paths:
                raise CoverageSelectionError(
                    f"slots[{index}].reports contains a duplicate report identity"
                )
            report_identities.add(identity)
            report_paths.add(path)
            reports.append(
                CoverageReportSpec(
                    component=component,
                    report_format=report_format,
                    path=path,
                )
            )
        if metadata_path in report_paths:
            raise CoverageSelectionError(
                f"slots[{index}].metadata_path must not overlap a report path"
            )
        validated.append(
            CoverageArtifactSlot(
                logical_artifact=artifact,
                producer_job=slot.producer_job,
                metadata_path=metadata_path,
                reports=tuple(sorted(reports, key=lambda item: item.path)),
            )
        )
    return tuple(sorted(validated, key=lambda item: item.logical_artifact))


def _physical_attempt(root: Path, slot: CoverageArtifactSlot) -> int:
    prefix = f"{slot.logical_artifact}-attempt-"
    if not root.name.startswith(prefix):
        raise CoverageSelectionError(
            f"candidate root name does not bind a known physical artifact: {root.name}"
        )
    attempt = root.name.removeprefix(prefix)
    if _POSITIVE_DECIMAL.fullmatch(attempt) is None:
        raise CoverageSelectionError(
            "candidate root name must end with a positive producer attempt: "
            f"{root.name}"
        )
    return int(attempt)


def _slot_for_root(
    root: Path, slots: Sequence[CoverageArtifactSlot]
) -> tuple[CoverageArtifactSlot, int]:
    matches: list[tuple[CoverageArtifactSlot, int]] = []
    for slot in slots:
        try:
            matches.append((slot, _physical_attempt(root, slot)))
        except CoverageSelectionError:
            continue
    if len(matches) != 1:
        raise CoverageSelectionError(
            "candidate root name must bind exactly one known logical artifact: "
            f"{root.name}"
        )
    return matches[0]


def _expected_files(slot: CoverageArtifactSlot) -> set[str]:
    return {slot.metadata_path, *(report.path for report in slot.reports)}


def _candidate_inventory(root: Path, slot: CoverageArtifactSlot) -> None:
    expected = _expected_files(slot)
    actual: set[str] = set()
    expected_directories: set[str] = set()
    for file_path in expected:
        parent = PurePosixPath(file_path).parent
        while parent != PurePosixPath("."):
            expected_directories.add(parent.as_posix())
            parent = parent.parent
    actual_directories: set[str] = set()
    try:
        descendants = sorted(root.rglob("*"), key=lambda item: item.as_posix())
    except OSError as error:
        raise CoverageSelectionError(
            f"unable to inspect candidate root: {root}"
        ) from error
    for descendant in descendants:
        if _is_link_or_junction(descendant):
            raise CoverageSelectionError(
                f"candidate root contains a symlink or junction: {descendant}"
            )
        if descendant.is_dir():
            actual_directories.add(
                _safe_relative_path(
                    descendant.relative_to(root).as_posix(), "candidate directory"
                )
            )
            continue
        if not descendant.is_file():
            raise CoverageSelectionError(
                f"candidate root contains a non-regular member: {descendant}"
            )
        relative = _safe_relative_path(
            descendant.relative_to(root).as_posix(), "candidate member"
        )
        actual.add(relative)
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing:
        raise CoverageSelectionError(
            "candidate root is missing expected members: " + ", ".join(missing)
        )
    if unexpected:
        raise CoverageSelectionError(
            "candidate root contains unexpected members: " + ", ".join(unexpected)
        )
    unexpected_directories = sorted(actual_directories - expected_directories)
    if unexpected_directories:
        raise CoverageSelectionError(
            "candidate root contains unexpected directories: "
            + ", ".join(unexpected_directories)
        )
    for path in sorted(expected):
        _safe_file(root, path, "candidate member")


def _load_candidate_metadata(path: Path) -> tuple[bytes, dict[str, object]]:
    try:
        raw = path.read_bytes()
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_json_object,
            parse_constant=_reject_json_constant,
        )
    except CoverageSelectionError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CoverageSelectionError(
            f"unable to read candidate metadata: {path}"
        ) from error
    if not isinstance(value, dict):
        raise CoverageSelectionError(
            f"candidate metadata must be a JSON object: {path}"
        )
    return raw, cast(dict[str, object], value)


def _validate_manifest_reports(
    metadata: Mapping[str, object], slot: CoverageArtifactSlot
) -> Mapping[str, tuple[str, int]]:
    raw_reports = metadata.get("reports")
    if not isinstance(raw_reports, list):
        raise CoverageSelectionError("candidate metadata reports must be an array")
    expected = {
        (specification.component, specification.report_format, specification.path)
        for specification in slot.reports
    }
    actual: set[tuple[str, str, str]] = set()
    report_integrity: dict[str, tuple[str, int]] = {}
    for index, report in enumerate(raw_reports):
        if not isinstance(report, Mapping):
            raise CoverageSelectionError(
                f"candidate metadata reports[{index}] must be an object"
            )
        try:
            component = _require_text(
                report["component"], f"candidate metadata reports[{index}].component"
            )
            report_format = _require_text(
                report["format"], f"candidate metadata reports[{index}].format"
            )
            path = _safe_relative_path(
                report["path"], f"candidate metadata reports[{index}].path"
            )
            sha256 = _require_text(
                report["sha256"], f"candidate metadata reports[{index}].sha256"
            )
            byte_size = report["byte_size"]
        except KeyError as error:
            raise CoverageSelectionError(
                f"candidate metadata reports[{index}] is incomplete"
            ) from error
        if _SHA256.fullmatch(sha256) is None:
            raise CoverageSelectionError(
                f"candidate metadata reports[{index}].sha256 must be lowercase SHA-256"
            )
        if (
            isinstance(byte_size, bool)
            or not isinstance(byte_size, int)
            or byte_size < 1
        ):
            raise CoverageSelectionError(
                f"candidate metadata reports[{index}].byte_size must be positive"
            )
        actual.add((component, report_format, path))
        report_integrity[path] = (sha256, byte_size)
    if len(actual) != len(raw_reports) or actual != expected:
        raise CoverageSelectionError(
            f"candidate metadata report inventory does not match slot {slot.logical_artifact}"
        )
    return report_integrity


def _candidate_from_root(
    root: Path, slot: CoverageArtifactSlot, attempt: int
) -> _Candidate:
    _candidate_inventory(root, slot)
    metadata_path = _safe_file(root, slot.metadata_path, "candidate metadata")
    raw, metadata = _load_candidate_metadata(metadata_path)
    report_integrity = _validate_manifest_reports(metadata, slot)
    return _Candidate(
        slot=slot,
        root=root,
        physical_artifact=root.name,
        physical_attempt=attempt,
        metadata=metadata,
        metadata_bytes=raw,
        report_integrity=report_integrity,
    )


def _validate_physical_attempt_binding(candidate: _Candidate) -> None:
    """Reject a forged artifact suffix before any retry candidate is selected.

    Full schema validation remains delegated to ``coverage_provenance`` below.
    This narrow early binding is deliberately tolerant of malformed producer
    metadata so that the shared validator retains its precise error, but a
    parseable attempt may never disagree with the immutable artifact name.
    """

    producer = candidate.metadata.get("producer")
    if not isinstance(producer, Mapping):
        return
    producer_attempt = producer.get("run_attempt")
    if not isinstance(producer_attempt, str) or not producer_attempt.isdecimal():
        return
    if int(producer_attempt) != candidate.physical_attempt:
        raise CoverageSelectionError(
            "producer attempt does not bind its physical artifact name"
        )


def _ensure_isolated_roots(roots: Sequence[Path]) -> None:
    for index, left in enumerate(roots):
        for right in roots[index + 1 :]:
            if right.is_relative_to(left) or left.is_relative_to(right):
                raise CoverageSelectionError(
                    "candidate roots must be isolated and must not nest: "
                    f"{left} / {right}"
                )


def _validation_root(repository_root: Path) -> Path:
    lexical = Path(os.path.abspath(repository_root))
    if _is_link_or_junction(lexical):
        raise CoverageSelectionError(
            f"repository root must not be a symlink or junction: {repository_root}"
        )
    try:
        root = lexical.resolve(strict=True)
    except OSError as error:
        raise CoverageSelectionError(
            f"repository root is unavailable: {repository_root}"
        ) from error
    if _normal_path_text(lexical) != _normal_path_text(root):
        raise CoverageSelectionError(
            f"repository root traverses a symlink or junction: {repository_root}"
        )
    if not root.is_dir():
        raise CoverageSelectionError(f"repository root is not a directory: {root}")
    return root


def _copy_regular_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target, follow_symlinks=False)
    with target.open("r+b") as stream:
        os.fsync(stream.fileno())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_materialized_report(
    *,
    stage_root: Path,
    relative_path: str,
    expected_sha256: str,
    expected_byte_size: int,
) -> None:
    materialized = _safe_file(stage_root, relative_path, "materialized report")
    if materialized.stat().st_size != expected_byte_size:
        raise CoverageSelectionError(
            f"materialized report byte_size mismatch: {relative_path}"
        )
    if _sha256(materialized) != expected_sha256:
        raise CoverageSelectionError(
            f"materialized report sha256 mismatch: {relative_path}"
        )


def _atomic_write_json(path: Path, payload: object) -> None:
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as stream:
            temporary_name = stream.name
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
        temporary_name = None
    finally:
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink()
            except FileNotFoundError:
                pass


def _project_metadata(metadata: dict[str, object], namespace: str) -> dict[str, object]:
    projected = copy.deepcopy(metadata)
    raw_reports = projected.get("reports")
    if not isinstance(raw_reports, list):
        raise CoverageSelectionError("candidate metadata reports must be an array")
    for index, report in enumerate(raw_reports):
        if not isinstance(report, dict):
            raise CoverageSelectionError(
                f"candidate metadata reports[{index}] must be an object"
            )
        report_path = _safe_relative_path(
            report.get("path"), f"candidate metadata reports[{index}].path"
        )
        report["path"] = f"{namespace}/{report_path}"
    return projected


def _stage_candidate(
    candidate: _Candidate,
    validation_root: Path,
    repository_root: Path,
    namespace: str,
) -> _StagedCandidate:
    stage_root = validation_root / namespace
    for path in sorted(_expected_files(candidate.slot)):
        source = _safe_file(candidate.root, path, "candidate member")
        target = stage_root.joinpath(*PurePosixPath(path).parts)
        _copy_regular_file(source, target)
    metadata_path = stage_root.joinpath(
        *PurePosixPath(candidate.slot.metadata_path).parts
    )
    projection_prefix = (
        f"{validation_root.relative_to(repository_root).as_posix()}/{namespace}"
    )
    _atomic_write_json(
        metadata_path,
        _project_metadata(candidate.metadata, projection_prefix),
    )
    return _StagedCandidate(
        candidate=candidate,
        stage_root=stage_root,
        metadata_path=metadata_path,
    )


def _safe_destination(repository_root: Path, destination_root: Path) -> Path:
    destination = Path(os.path.abspath(destination_root))
    try:
        relative = destination.relative_to(repository_root)
    except ValueError as error:
        raise CoverageSelectionError(
            "destination root must stay inside the trusted repository root"
        ) from error
    if not relative.parts or relative.parts[0] == ".git":
        raise CoverageSelectionError("destination root is unsafe")
    current = repository_root
    for part in relative.parts:
        current /= part
        if current.exists() and _is_link_or_junction(current):
            raise CoverageSelectionError(
                f"destination root traverses a symlink or junction: {current}"
            )
    if destination.exists() or _is_link_or_junction(destination):
        raise CoverageSelectionError(
            f"destination root must not already exist: {destination}"
        )
    return destination


def _retry_context_for_receipt(
    consumer_retry_context: Mapping[str, str],
) -> dict[str, str]:
    return {
        name: consumer_retry_context[name] for name in sorted(consumer_retry_context)
    }


def _receipt(
    *,
    expected_sha: str,
    expected_repository: str,
    expected_run_id: str,
    expected_run_attempt: str,
    expected_workflow_ref: str,
    expected_workflow_sha: str,
    expected_event: str,
    consumer_retry_context: Mapping[str, str],
    staged: Mapping[Path, _StagedCandidate],
    selections: Sequence[MetadataSelection],
) -> dict[str, object]:
    records: list[dict[str, object]] = []
    for selection in selections:
        candidate = staged[selection.metadata_path].candidate
        reports = cast(list[dict[str, object]], candidate.metadata["reports"])
        records.append(
            {
                "logical_artifact": candidate.slot.logical_artifact,
                "producer_job": candidate.slot.producer_job,
                "physical_artifact": candidate.physical_artifact,
                "producer_attempt": selection.producer_attempt,
                "metadata": {
                    "path": (
                        f"{candidate.slot.logical_artifact}/"
                        f"{candidate.slot.metadata_path}"
                    ),
                    "sha256": hashlib.sha256(candidate.metadata_bytes).hexdigest(),
                },
                "reports": [
                    {
                        "component": report["component"],
                        "format": report["format"],
                        "path": (f"{candidate.slot.logical_artifact}/{report['path']}"),
                        "sha256": report["sha256"],
                        "byte_size": report["byte_size"],
                    }
                    for report in sorted(
                        reports, key=lambda item: cast(str, item["path"])
                    )
                ],
            }
        )
    return {
        "schema_version": 1,
        "consumer": {
            "commit_sha": expected_sha,
            "repository": expected_repository,
            "run_id": expected_run_id,
            "run_attempt": expected_run_attempt,
            "workflow_ref": expected_workflow_ref,
            "workflow_sha": expected_workflow_sha,
            "event": expected_event,
            "retry_context": _retry_context_for_receipt(consumer_retry_context),
        },
        "selections": sorted(
            records, key=lambda item: cast(str, item["logical_artifact"])
        ),
    }


def _materialize_selection(
    *,
    destination: Path,
    staged: Mapping[Path, _StagedCandidate],
    selections: Sequence[MetadataSelection],
    receipt: dict[str, object],
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage_path = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
    )
    completed = False
    try:
        for selection in selections:
            staged_candidate = staged[selection.metadata_path]
            candidate = staged_candidate.candidate
            output_root = stage_path / candidate.slot.logical_artifact
            for report in candidate.slot.reports:
                source = staged_candidate.stage_root.joinpath(
                    *PurePosixPath(report.path).parts
                )
                output_relative = f"{candidate.slot.logical_artifact}/{report.path}"
                _copy_regular_file(
                    source, stage_path.joinpath(*PurePosixPath(output_relative).parts)
                )
                expected_sha256, expected_byte_size = candidate.report_integrity[
                    report.path
                ]
                _verify_materialized_report(
                    stage_root=stage_path,
                    relative_path=output_relative,
                    expected_sha256=expected_sha256,
                    expected_byte_size=expected_byte_size,
                )
            metadata_output = output_root.joinpath(
                *PurePosixPath(candidate.slot.metadata_path).parts
            )
            metadata_output.parent.mkdir(parents=True, exist_ok=True)
            metadata_output.write_bytes(candidate.metadata_bytes)
            with metadata_output.open("r+b") as stream:
                os.fsync(stream.fileno())
        _atomic_write_json(stage_path / _RECEIPT_NAME, receipt)
        os.replace(stage_path, destination)
        completed = True
    finally:
        if not completed:
            shutil.rmtree(stage_path, ignore_errors=True)


def select_coverage_artifacts(
    *,
    repository_root: Path,
    candidate_roots: Collection[Path],
    slots: Sequence[CoverageArtifactSlot],
    destination_root: Path,
    expected_sha: str,
    expected_repository: str,
    expected_run_id: str,
    expected_run_attempt: str,
    expected_workflow_ref: str,
    expected_workflow_sha: str,
    expected_event: str,
    consumer_retry_context: Mapping[str, str],
) -> CoverageSelectionResult:
    """Select complete retry evidence and atomically materialize it.

    Candidates must be isolated artifact roots named
    ``<logical-artifact>-attempt-<positive-integer>``.  Each root is an exact
    miniature of its declared metadata/report paths; this avoids relying on
    artifact extraction layout or wildcard flattening.
    """

    trusted_root = _validation_root(repository_root)
    validated_slots = _validate_slots(slots)
    if not candidate_roots:
        raise CoverageSelectionError("candidate roots must contain at least one root")
    normalized_roots = tuple(
        sorted((_safe_candidate_root(path) for path in candidate_roots), key=str)
    )
    if len(set(normalized_roots)) != len(normalized_roots):
        raise CoverageSelectionError("candidate roots contain a duplicate root")
    _ensure_isolated_roots(normalized_roots)
    candidate_groups: dict[str, list[_Candidate]] = {
        slot.logical_artifact: [] for slot in validated_slots
    }
    for root in normalized_roots:
        slot, physical_attempt = _slot_for_root(root, validated_slots)
        candidate = _candidate_from_root(root, slot, physical_attempt)
        _validate_physical_attempt_binding(candidate)
        candidate_groups[slot.logical_artifact].append(candidate)
    missing_slots = sorted(
        artifact for artifact, candidates in candidate_groups.items() if not candidates
    )
    if missing_slots:
        raise CoverageSelectionError(
            "missing logical slots: " + ", ".join(missing_slots)
        )
    destination = _safe_destination(trusted_root, destination_root)

    validation_directory = Path(
        tempfile.mkdtemp(prefix=".coverage-selection-validate.", dir=trusted_root)
    )
    try:
        staged_by_metadata: dict[Path, _StagedCandidate] = {}
        selected_metadata: list[MetadataSelection] = []
        for slot_index, slot in enumerate(validated_slots):
            candidates = sorted(
                candidate_groups[slot.logical_artifact],
                key=lambda item: (item.physical_attempt, str(item.root)),
            )
            metadata_paths: list[Path] = []
            for candidate_index, candidate in enumerate(candidates):
                namespace = (
                    f"candidate-{slot_index}-{candidate.physical_attempt}-"
                    f"{candidate_index}"
                )
                staged = _stage_candidate(
                    candidate,
                    validation_directory,
                    trusted_root,
                    namespace,
                )
                staged_by_metadata[staged.metadata_path.resolve()] = staged
                metadata_paths.append(staged.metadata_path)
            try:
                selection = select_metadata_candidates(
                    repository_root=trusted_root,
                    metadata_paths=metadata_paths,
                    expected_sha=expected_sha,
                    expected_repository=expected_repository,
                    expected_run_id=expected_run_id,
                    expected_run_attempt=expected_run_attempt,
                    expected_job=slot.producer_job,
                    expected_artifact=slot.logical_artifact,
                    expected_workflow_ref=expected_workflow_ref,
                    expected_workflow_sha=expected_workflow_sha,
                    expected_event=expected_event,
                    consumer_retry_context=consumer_retry_context,
                )
            except ProvenanceError as error:
                raise CoverageSelectionError(str(error)) from error
            selected_stage = staged_by_metadata.get(selection.metadata_path)
            if selected_stage is None:
                raise CoverageSelectionError(
                    "selected metadata is outside validation root"
                )
            selected_metadata.append(selection)
        selected_metadata.sort(
            key=lambda selection: staged_by_metadata[
                selection.metadata_path
            ].candidate.slot.logical_artifact
        )
        receipt = _receipt(
            expected_sha=expected_sha,
            expected_repository=expected_repository,
            expected_run_id=expected_run_id,
            expected_run_attempt=expected_run_attempt,
            expected_workflow_ref=expected_workflow_ref,
            expected_workflow_sha=expected_workflow_sha,
            expected_event=expected_event,
            consumer_retry_context=consumer_retry_context,
            staged=staged_by_metadata,
            selections=selected_metadata,
        )
        _materialize_selection(
            destination=destination,
            staged=staged_by_metadata,
            selections=selected_metadata,
            receipt=receipt,
        )
        return CoverageSelectionResult(
            selections=tuple(
                CoverageArtifactSelection(
                    logical_artifact=staged_by_metadata[
                        selection.metadata_path
                    ].candidate.slot.logical_artifact,
                    physical_artifact=staged_by_metadata[
                        selection.metadata_path
                    ].candidate.physical_artifact,
                    producer_attempt=selection.producer_attempt,
                    candidate_root=staged_by_metadata[
                        selection.metadata_path
                    ].candidate.root,
                )
                for selection in selected_metadata
            ),
            receipt_path=destination / _RECEIPT_NAME,
        )
    finally:
        shutil.rmtree(validation_directory, ignore_errors=True)
