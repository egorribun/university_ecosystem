"""Retry-safe artifact transport for the primary CI mutmut chain.

Generic provenance owns identity, retry-context, and byte integrity.  This
adapter owns the mutmut-only contract: eight static stats slots, exact isolated
artifact layout, and a receipt bound into the central universe artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, cast

from scripts.mutmut_universe_artifact import (
    ArtifactSelection,
    ArtifactValidationError,
    create_artifact_manifest,
    select_artifact_manifest_candidates,
    validate_artifact_manifest,
)
from scripts.quality.coverage_provenance import (
    MetadataSelection,
    ProvenanceError,
    select_metadata_candidates,
    write_metadata,
)

STATS_ARTIFACT = "mutmut-stats"
UNIVERSE_ARTIFACT = "mutmut-universe"
STATS_SIDECAR_NAME = "mutmut-stats-artifact.json"
STATS_SELECTION_NAME = "mutmut-stats-selection.json"
UNIVERSE_SELECTION_NAME = "mutmut-universe-selection.json"
STATS_SOURCE_PATH = "mutants/mutmut-stats.json"
STATS_PATH = "mutmut-stats.json"
STATS_CANDIDATE_DIRECTORY = "mutmut-stats-candidates"
EXPECTED_STATS_SHARDS = frozenset(range(8))

_STATS_JOB = "mutation-tests-stats"
_STATS_COMPONENT = "mutmut"
_STATS_FORMAT = "mutmut-stats-json"
_EVIDENCE_VERSION = 1
_SHA256 = re.compile(r"[0-9a-f]{64}")
_POSITIVE = re.compile(r"[1-9][0-9]*")
_PHYSICAL = re.compile(r"mutmut-stats-shard-([0-7])-attempt-([1-9][0-9]*)")
_RETRY_FIELDS = frozenset(
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
_CONSUMER_FIELDS = _RETRY_FIELDS - {"run_attempt", "artifact"}
_DEFAULT_CONFIG_INPUTS = (
    "pyproject.toml",
    "uv.lock",
    "scripts/mutmut_stats_shard.py",
    "scripts/merge_mutmut_stats.py",
    "scripts/plan_mutmut_shards.py",
    "scripts/mutmut_shard_matrix.py",
    "scripts/mutmut_universe_artifact.py",
    "scripts/mutmut_retry_artifacts.py",
)
_DEFAULT_POLICY_INPUTS = ("quality/quality-contract.json", ".github/workflows/ci.yml")


class RetryArtifactError(ValueError):
    """Evidence is malformed, unsafe, or not retry-compatible."""


@dataclass(frozen=True)
class StatsArtifactSelection:
    logical_shard: int
    physical_artifact: str
    producer_attempt: int
    candidate_root: Path
    stats_sha256: str
    sidecar_sha256: str


@dataclass(frozen=True)
class _Candidate:
    shard: int
    physical: str
    attempt: int
    root: Path
    metadata: Path


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise RetryArtifactError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _constant(value: str) -> NoReturn:
    raise RetryArtifactError(f"invalid JSON constant: {value}")


def _json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_object,
            parse_constant=_constant,
        )
    except RetryArtifactError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RetryArtifactError(f"{label} is invalid: {path}") from error
    if not isinstance(value, dict):
        raise RetryArtifactError(f"{label} must be a JSON object")
    return value


def _linked(path: Path) -> bool:
    junction = getattr(os.path, "isjunction", None)
    return path.is_symlink() or bool(junction is not None and junction(path))


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(os.path.normpath(str(left))) == os.path.normcase(
        os.path.normpath(str(right))
    )


def _root(path: Path, label: str) -> Path:
    requested = Path(os.path.abspath(path))
    if _linked(requested):
        raise RetryArtifactError(f"{label} must not be a symlink or junction")
    try:
        result = requested.resolve(strict=True)
    except OSError as error:
        raise RetryArtifactError(f"{label} is unavailable: {path}") from error
    if not _same_path(requested, result):
        raise RetryArtifactError(f"{label} traverses a symlink or junction")
    if not result.is_dir():
        raise RetryArtifactError(f"{label} is not a directory: {path}")
    return result


def _relative(value: Path | str, label: str) -> str:
    raw = str(value).replace("\\", "/")
    path = PurePosixPath(raw)
    if (
        not path.parts
        or path.is_absolute()
        or re.match(r"^[A-Za-z]:/", raw)
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise RetryArtifactError(f"{label} must be a safe repository-relative path")
    return path.as_posix()


def _path(root: Path, value: Path | str, label: str) -> Path:
    requested = Path(value)
    target = Path(
        os.path.abspath(requested if requested.is_absolute() else root / requested)
    )
    try:
        relative = target.relative_to(root)
    except ValueError as error:
        raise RetryArtifactError(f"{label} must stay inside its root") from error
    normalized = _relative(relative, label)
    target = root.joinpath(*PurePosixPath(normalized).parts)
    try:
        resolved = target.resolve(strict=False)
    except OSError as error:
        raise RetryArtifactError(f"{label} is unavailable") from error
    if not _same_path(target, resolved):
        raise RetryArtifactError(f"{label} traverses a symlink or junction")
    current = root
    for part in PurePosixPath(normalized).parts:
        current /= part
        if current.exists() and _linked(current):
            raise RetryArtifactError(f"{label} traverses a symlink or junction")
    return target


def _file(root: Path, value: Path | str, label: str) -> Path:
    target = _path(root, value, label)
    if _linked(target) or not target.is_file() or target.stat().st_size < 1:
        raise RetryArtifactError(f"{label} is missing or unsafe: {value}")
    return target


def _new_file(root: Path, value: Path | str, label: str) -> Path:
    target = _path(root, value, label)
    if target.exists() or _linked(target):
        raise RetryArtifactError(f"{label} already exists: {value}")
    target.parent.mkdir(parents=True, exist_ok=True)
    _path(root, value, label)
    return target


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise RetryArtifactError(f"unable to hash {path}") from error
    return digest.hexdigest()


def _attempt(value: object, label: str) -> int:
    if isinstance(value, bool) or _POSITIVE.fullmatch(str(value)) is None:
        raise RetryArtifactError(f"{label} must be a positive decimal integer")
    return int(str(value))


def _logical(shard: int) -> str:
    if isinstance(shard, bool) or shard not in EXPECTED_STATS_SHARDS:
        raise RetryArtifactError("logical shard must be one of the eight stats slots")
    return f"mutmut-stats-shard-{shard}"


def _physical(shard: int, attempt: object) -> str:
    return f"{_logical(shard)}-attempt-{_attempt(attempt, 'run attempt')}"


def _context(
    raw: Mapping[str, str],
    *,
    commit_sha: str,
    run_id: str,
    run_attempt: str,
    workflow: str,
    artifact: str,
    label: str,
) -> dict[str, str]:
    if frozenset(raw) != _RETRY_FIELDS:
        raise RetryArtifactError(f"{label} must contain complete retry provenance")
    context: dict[str, str] = {}
    for field in _RETRY_FIELDS:
        value = raw[field]
        if (
            not isinstance(value, str)
            or not value
            or any(char in value for char in "\x00\r\n")
        ):
            raise RetryArtifactError(f"{label}.{field} must be a non-empty string")
        context[field] = value
    expected = {
        "run_id": run_id,
        "run_attempt": run_attempt,
        "source_sha": commit_sha,
        "source_revision": commit_sha,
        "artifact": artifact,
    }
    if any(context[field] != value for field, value in expected.items()):
        raise RetryArtifactError(f"{label} does not bind its mutmut producer")
    workflow_path, separator, revision = context["workflow_ref"].partition("@")
    if not separator or not revision or not workflow_path.endswith(f"/{workflow}"):
        raise RetryArtifactError(f"{label}.workflow_ref does not bind the workflow")
    return context


def _consumer_context(context: Mapping[str, str]) -> dict[str, str]:
    return {field: context[field] for field in sorted(_CONSUMER_FIELDS)}


def _digest(root: Path, inputs: Sequence[Path | str], label: str) -> str:
    if not inputs:
        raise RetryArtifactError(f"{label} inputs must not be empty")
    names = [_relative(item, f"{label} input") for item in inputs]
    if len(names) != len(set(names)):
        raise RetryArtifactError(f"{label} inputs contain a duplicate")
    digest = hashlib.sha256()
    for name in sorted(names):
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(_sha(_file(root, name, f"{label} input"))))
    return digest.hexdigest()


def build_retry_provenance(
    *,
    root: Path,
    repository: str,
    run_id: str,
    run_attempt: str,
    source_sha: str,
    source_revision: str,
    workflow_ref: str,
    workflow_sha: str,
    event: str,
    artifact: str,
    config_inputs: Sequence[Path | str],
    policy_inputs: Sequence[Path | str],
) -> dict[str, str]:
    """Digest the checked-out policy and config that permit retry reuse."""

    repository_root = _root(root, "retry provenance root")
    return {
        "repository": repository,
        "run_id": run_id,
        "run_attempt": run_attempt,
        "source_sha": source_sha,
        "source_revision": source_revision,
        "workflow_ref": workflow_ref,
        "workflow_sha": workflow_sha,
        "event": event,
        "config_digest": _digest(repository_root, config_inputs, "configuration"),
        "policy_digest": _digest(repository_root, policy_inputs, "policy"),
        "artifact": artifact,
    }


def create_stats_sidecar(
    *,
    root: Path,
    output: Path,
    stats_path: Path,
    logical_shard: int,
    commit_sha: str,
    run_id: str,
    run_attempt: str,
    workflow: str,
    retry_provenance: Mapping[str, str],
    candidate_parent: Path = Path(STATS_CANDIDATE_DIRECTORY),
) -> dict[str, object]:
    """Bind one logical mutmut stats shard to generic provenance metadata."""

    repository_root = _root(root, "stats sidecar root")
    artifact = _logical(logical_shard)
    context = _context(
        retry_provenance,
        commit_sha=commit_sha,
        run_id=run_id,
        run_attempt=run_attempt,
        workflow=workflow,
        artifact=artifact,
        label="stats retry provenance",
    )
    if (
        _relative(
            _path(repository_root, output, "stats sidecar output").relative_to(
                repository_root
            ),
            "stats sidecar output",
        )
        != STATS_SIDECAR_NAME
    ):
        raise RetryArtifactError(f"stats sidecar output must be {STATS_SIDECAR_NAME}")
    if (
        _relative(
            _path(repository_root, stats_path, "stats source").relative_to(
                repository_root
            ),
            "stats source",
        )
        != STATS_SOURCE_PATH
    ):
        raise RetryArtifactError(f"stats source must be {STATS_SOURCE_PATH}")
    parent = _relative(candidate_parent, "stats candidate parent")
    canonical = f"{parent}/{_physical(logical_shard, run_attempt)}/{STATS_PATH}"
    try:
        return write_metadata(
            repository_root=repository_root,
            output_path=Path(STATS_SIDECAR_NAME),
            reports=((_STATS_COMPONENT, _STATS_FORMAT, STATS_SOURCE_PATH, canonical),),
            tool_versions={"mutmut": "3.7.0"},
            expected_sha=commit_sha,
            identity_provider="github-actions",
            repository=context["repository"],
            workflow_ref=context["workflow_ref"],
            workflow_sha=context["workflow_sha"],
            run_id=context["run_id"],
            run_attempt=context["run_attempt"],
            event=context["event"],
            job=_STATS_JOB,
            artifact=artifact,
            collected_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            retry_provenance=context,
        )
    except ProvenanceError as error:
        raise RetryArtifactError(str(error)) from error


def _candidate(repository_root: Path, value: Path) -> _Candidate:
    root = _path(repository_root, value, "stats candidate root")
    if _linked(root) or not root.is_dir():
        raise RetryArtifactError(f"stats candidate root is unavailable: {value}")
    try:
        members = list(root.iterdir())
    except OSError as error:
        raise RetryArtifactError(
            f"unable to enumerate stats candidate: {value}"
        ) from error
    if {member.name for member in members} != {STATS_PATH, STATS_SIDECAR_NAME} or any(
        _linked(member) or not member.is_file() or member.stat().st_size < 1
        for member in members
    ):
        raise RetryArtifactError("stats candidate inventory is not exact and isolated")
    match = _PHYSICAL.fullmatch(root.name)
    if match is None:
        raise RetryArtifactError(f"unexpected mutmut stats artifact name: {root.name}")
    shard, attempt = int(match.group(1)), int(match.group(2))
    metadata = _file(root, STATS_SIDECAR_NAME, "stats sidecar")
    payload = _json(metadata, "stats sidecar")
    reports = payload.get("reports")
    expected_path = f"{_relative(root.relative_to(repository_root), 'stats candidate root')}/{STATS_PATH}"
    if (
        not isinstance(reports, list)
        or len(reports) != 1
        or not isinstance(reports[0], Mapping)
        or reports[0].get("component") != _STATS_COMPONENT
        or reports[0].get("format") != _STATS_FORMAT
        or reports[0].get("path") != expected_path
        or not isinstance(payload.get("producer"), Mapping)
        or payload["producer"].get("artifact") != _logical(shard)
    ):
        raise RetryArtifactError("stats sidecar does not bind this logical candidate")
    return _Candidate(shard, root.name, attempt, root, metadata)


def _fresh_directory(root: Path, value: Path, label: str) -> Path:
    target = _path(root, value, label)
    if target.exists() or _linked(target):
        raise RetryArtifactError(f"{label} must not already exist")
    target.mkdir(parents=True)
    return target


def _copy(
    source_root: Path, destination_root: Path, source: str, destination: str, label: str
) -> None:
    # Inventory members may legitimately be zero-byte regular files (Python
    # package markers such as ``tests/__init__.py`` are emitted by mutmut).
    # Keep the strict path/link checks from ``_path`` while not conflating an
    # empty file with a missing or unsafe artifact.  Metadata/receipt inputs
    # continue to use ``_file`` and therefore remain non-empty by contract.
    input_path = _path(source_root, source, label)
    if _linked(input_path) or not input_path.is_file():
        raise RetryArtifactError(f"{label} is missing or unsafe: {source}")
    output_path = _new_file(destination_root, destination, label)
    try:
        with (
            input_path.open("rb") as input_stream,
            output_path.open("xb") as output_stream,
        ):
            shutil.copyfileobj(input_stream, output_stream)
    except OSError as error:
        raise RetryArtifactError(f"unable to copy {label}") from error


def _receipt(
    output_root: Path,
    context: Mapping[str, str],
    selected: Mapping[int, StatsArtifactSelection],
) -> None:
    payload = {
        "schema_version": _EVIDENCE_VERSION,
        "artifact": STATS_ARTIFACT,
        "consumer": dict(context),
        "selected": [
            {
                "logical_shard": shard,
                "physical_artifact": selected[shard].physical_artifact,
                "producer_attempt": selected[shard].producer_attempt,
                "stats_sha256": selected[shard].stats_sha256,
                "sidecar_sha256": selected[shard].sidecar_sha256,
            }
            for shard in sorted(selected)
        ],
    }
    try:
        _new_file(
            output_root, STATS_SELECTION_NAME, "stats selection evidence"
        ).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    except OSError as error:
        raise RetryArtifactError("unable to write stats selection evidence") from error


def _validate_receipt(root: Path, path: Path, context: Mapping[str, str]) -> None:
    payload = _json(
        _file(root, path, "stats selection evidence"), "stats selection evidence"
    )
    if (
        set(payload) != {"schema_version", "artifact", "consumer", "selected"}
        or payload["schema_version"] != _EVIDENCE_VERSION
        or payload["artifact"] != STATS_ARTIFACT
        or payload["consumer"] != dict(context)
        or not isinstance(payload["selected"], list)
        or len(payload["selected"]) != len(EXPECTED_STATS_SHARDS)
    ):
        raise RetryArtifactError("stats selection evidence is invalid")
    consumer_attempt = _attempt(
        context["run_attempt"], "stats selection consumer attempt"
    )
    for shard, item in enumerate(payload["selected"]):
        if not isinstance(item, Mapping) or set(item) != {
            "logical_shard",
            "physical_artifact",
            "producer_attempt",
            "stats_sha256",
            "sidecar_sha256",
        }:
            raise RetryArtifactError("stats selection evidence entry is invalid")
        attempt = _attempt(item["producer_attempt"], "stats selection producer attempt")
        if (
            item["logical_shard"] != shard
            or attempt > consumer_attempt
            or item["physical_artifact"] != _physical(shard, attempt)
            or not isinstance(item["stats_sha256"], str)
            or _SHA256.fullmatch(item["stats_sha256"]) is None
            or not isinstance(item["sidecar_sha256"], str)
            or _SHA256.fullmatch(item["sidecar_sha256"]) is None
        ):
            raise RetryArtifactError("stats selection evidence entry is invalid")


def select_stats_candidates(
    *,
    root: Path,
    candidate_roots: Collection[Path],
    output_root: Path,
    commit_sha: str,
    run_id: str,
    run_attempt: str,
    workflow: str,
    consumer_retry_context: Mapping[str, str],
) -> dict[int, StatsArtifactSelection]:
    """Choose one highest valid producer <= consumer attempt for each slot."""

    repository_root = _root(root, "stats repository root")
    context = _context(
        consumer_retry_context,
        commit_sha=commit_sha,
        run_id=run_id,
        run_attempt=run_attempt,
        workflow=workflow,
        artifact=STATS_ARTIFACT,
        label="stats consumer retry context",
    )
    if not candidate_roots:
        raise RetryArtifactError("stats candidate roots must not be empty")
    grouped: dict[int, list[_Candidate]] = {
        shard: [] for shard in EXPECTED_STATS_SHARDS
    }
    seen: set[Path] = set()
    for value in candidate_roots:
        candidate = _candidate(repository_root, value)
        if candidate.root in seen:
            raise RetryArtifactError("duplicate stats candidate root")
        seen.add(candidate.root)
        grouped[candidate.shard].append(candidate)
    if missing := [str(shard) for shard, items in sorted(grouped.items()) if not items]:
        raise RetryArtifactError(
            "stats candidates are incomplete: missing " + ", ".join(missing)
        )

    selected: dict[int, StatsArtifactSelection] = {}
    for shard, candidates in sorted(grouped.items()):
        by_metadata = {
            candidate.metadata.resolve(strict=True): candidate
            for candidate in candidates
        }
        try:
            chosen: MetadataSelection = select_metadata_candidates(
                repository_root=repository_root,
                metadata_paths=[candidate.metadata for candidate in candidates],
                expected_sha=commit_sha,
                expected_repository=context["repository"],
                expected_run_id=run_id,
                expected_run_attempt=run_attempt,
                expected_job=_STATS_JOB,
                expected_artifact=_logical(shard),
                expected_workflow_ref=context["workflow_ref"],
                expected_workflow_sha=context["workflow_sha"],
                expected_event=context["event"],
                consumer_retry_context=_consumer_context(context),
            )
        except ProvenanceError as error:
            raise RetryArtifactError(str(error)) from error
        chosen_candidate = by_metadata.get(chosen.metadata_path.resolve(strict=True))
        reports = chosen.manifest.get("reports")
        if (
            chosen_candidate is None
            or not isinstance(reports, list)
            or not isinstance(reports[0], Mapping)
        ):
            raise RetryArtifactError(
                "generic provenance selector returned an invalid candidate"
            )
        stats_sha256 = reports[0].get("sha256")
        if not isinstance(stats_sha256, str):
            raise RetryArtifactError("selected stats metadata has no SHA-256")
        if chosen_candidate.attempt != chosen.producer_attempt:
            raise RetryArtifactError(
                "stats physical artifact attempt does not bind its provenance"
            )
        selected[shard] = StatsArtifactSelection(
            shard,
            chosen_candidate.physical,
            chosen.producer_attempt,
            chosen_candidate.root,
            stats_sha256,
            _sha(chosen_candidate.metadata),
        )
    output = _fresh_directory(repository_root, output_root, "stats selection output")
    for shard, selection in selected.items():
        _copy(
            selection.candidate_root,
            output,
            STATS_PATH,
            f"shard-{shard:02d}/{STATS_PATH}",
            "selected mutmut stats",
        )
    _receipt(output, context, selected)
    return selected


def create_universe_artifact(
    *,
    root: Path,
    output: Path,
    mode: str,
    commit_sha: str,
    run_id: str,
    run_attempt: str,
    workflow: str,
    retry_provenance: Mapping[str, str],
) -> dict[str, Any]:
    """Bind a central universe to a valid fixed-slot stats receipt."""

    if mode not in {"mutmut", "empty"}:
        raise RetryArtifactError(f"unsupported universe artifact mode: {mode!r}")
    repository_root = _root(root, "universe artifact root")
    context = _context(
        retry_provenance,
        commit_sha=commit_sha,
        run_id=run_id,
        run_attempt=run_attempt,
        workflow=workflow,
        artifact=UNIVERSE_ARTIFACT,
        label="universe retry provenance",
    )
    includes: Sequence[Path | str] = ()
    required: Sequence[Path | str] = ()
    if mode == "mutmut":
        _validate_receipt(
            repository_root,
            Path("mutants") / STATS_SELECTION_NAME,
            {**context, "artifact": STATS_ARTIFACT},
        )
        includes = ("mutants",)
        required = (
            "mutants/mutmut-universe.json",
            "mutants/mutmut-stats.json",
            "mutants/mutmut-incremental-plan/plan-manifest.json",
            f"mutants/{STATS_SELECTION_NAME}",
        )
    try:
        return create_artifact_manifest(
            root=repository_root,
            output=output,
            commit_sha=commit_sha,
            run_id=run_id,
            run_attempt=run_attempt,
            workflow=workflow,
            includes=includes,
            mode=mode,
            required_files=required,
            retry_provenance=context,
        )
    except ArtifactValidationError as error:
        raise RetryArtifactError(str(error)) from error


def _copy_universe(
    candidate: Path, destination: Path, manifest: Mapping[str, Any]
) -> None:
    files = manifest.get("files")
    if not isinstance(files, Mapping):
        raise RetryArtifactError("selected universe manifest files are invalid")
    for relative in sorted(files):
        if not isinstance(relative, str):
            raise RetryArtifactError("selected universe manifest has an invalid path")
        _copy(candidate, destination, relative, relative, "selected universe output")
    _copy(
        candidate,
        destination,
        "mutmut-universe-artifact.json",
        "mutmut-universe-artifact.json",
        "selected universe manifest",
    )


def select_universe_candidate(
    *,
    candidate_roots: Collection[Path],
    output_root: Path,
    selection_evidence: Path,
    commit_sha: str,
    run_id: str,
    run_attempt: str,
    workflow: str,
    expected_mode: str,
    consumer_retry_context: Mapping[str, str],
) -> ArtifactSelection:
    """Materialize and revalidate the highest complete compatible universe."""

    destination = _root(output_root, "universe selection output")
    context = _context(
        consumer_retry_context,
        commit_sha=commit_sha,
        run_id=run_id,
        run_attempt=run_attempt,
        workflow=workflow,
        artifact=UNIVERSE_ARTIFACT,
        label="universe consumer retry context",
    )
    try:
        selection = select_artifact_manifest_candidates(
            candidate_roots=candidate_roots,
            commit_sha=commit_sha,
            run_id=run_id,
            run_attempt=run_attempt,
            workflow=workflow,
            expected_artifact=UNIVERSE_ARTIFACT,
            consumer_retry_context=_consumer_context(context),
            expected_mode=expected_mode,
        )
    except ArtifactValidationError as error:
        raise RetryArtifactError(str(error)) from error
    if selection.candidate_root is None:
        raise RetryArtifactError("universe selector returned no candidate root")
    selected_context = {**context, "run_attempt": str(selection.producer_attempt)}
    if expected_mode == "mutmut":
        _validate_receipt(
            selection.candidate_root,
            Path("mutants") / STATS_SELECTION_NAME,
            {**selected_context, "artifact": STATS_ARTIFACT},
        )
    _copy_universe(selection.candidate_root, destination, selection.manifest)
    try:
        copied = validate_artifact_manifest(
            root=destination,
            manifest_path=Path("mutmut-universe-artifact.json"),
            commit_sha=commit_sha,
            run_id=run_id,
            run_attempt=run_attempt,
            workflow=workflow,
            expected_mode=expected_mode,
            producer_attempt_policy="at-or-before",
            expected_retry_provenance=selected_context,
        )
    except ArtifactValidationError as error:
        raise RetryArtifactError(str(error)) from error
    payload = {
        "schema_version": _EVIDENCE_VERSION,
        "artifact": UNIVERSE_ARTIFACT,
        "consumer": context,
        "producer_attempt": selection.producer_attempt,
        "manifest_sha256": _sha(destination / "mutmut-universe-artifact.json"),
    }
    try:
        _new_file(
            destination, selection_evidence, "universe selection evidence"
        ).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    except OSError as error:
        raise RetryArtifactError(
            "unable to write universe selection evidence"
        ) from error
    return ArtifactSelection(
        copied, selection.producer_attempt, selection.candidate_root
    )


def _identity_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--workflow", required=True)


def _retry_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repository", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--workflow-ref", required=True)
    parser.add_argument("--workflow-sha", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--config-input", type=Path, action="append", default=[])
    parser.add_argument("--policy-input", type=Path, action="append", default=[])


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("create-stats", "select-stats", "create-universe", "select-universe"):
        child = commands.add_parser(name)
        _identity_arguments(child)
        _retry_arguments(child)
        if name == "create-stats":
            child.add_argument("--logical-shard", type=int, required=True)
            child.add_argument("--stats", type=Path, default=Path(STATS_SOURCE_PATH))
            child.add_argument(
                "--manifest", type=Path, default=Path(STATS_SIDECAR_NAME)
            )
        elif name == "select-stats":
            child.add_argument(
                "--candidate-root", type=Path, action="append", required=True
            )
            child.add_argument("--output-root", type=Path, required=True)
        elif name == "create-universe":
            child.add_argument("--mode", choices=("mutmut", "empty"), required=True)
            child.add_argument(
                "--manifest", type=Path, default=Path("mutmut-universe-artifact.json")
            )
        else:
            child.add_argument(
                "--candidate-root", type=Path, action="append", required=True
            )
            child.add_argument("--output-root", type=Path, default=Path("."))
            child.add_argument(
                "--selection-evidence", type=Path, default=Path(UNIVERSE_SELECTION_NAME)
            )
            child.add_argument(
                "--expected-mode", choices=("mutmut", "empty"), required=True
            )
    return parser.parse_args()


def _from_arguments(args: argparse.Namespace, artifact: str) -> dict[str, str]:
    return build_retry_provenance(
        root=args.root,
        repository=args.repository,
        run_id=args.run_id,
        run_attempt=args.run_attempt,
        source_sha=args.commit_sha,
        source_revision=args.source_revision,
        workflow_ref=args.workflow_ref,
        workflow_sha=args.workflow_sha,
        event=args.event,
        artifact=artifact,
        config_inputs=args.config_input or _DEFAULT_CONFIG_INPUTS,
        policy_inputs=args.policy_input or _DEFAULT_POLICY_INPUTS,
    )


def main() -> int:
    args = _arguments()
    try:
        if args.command == "create-stats":
            artifact = _logical(args.logical_shard)
            payload = create_stats_sidecar(
                root=args.root,
                output=args.manifest,
                stats_path=args.stats,
                logical_shard=args.logical_shard,
                commit_sha=args.commit_sha,
                run_id=args.run_id,
                run_attempt=args.run_attempt,
                workflow=args.workflow,
                retry_provenance=_from_arguments(args, artifact),
            )
            reports = cast(list[dict[str, object]], payload["reports"])
            result: dict[str, object] = {
                "artifact": artifact,
                "logical_shard": args.logical_shard,
                "stats_sha256": reports[0]["sha256"],
            }
        elif args.command == "select-stats":
            selected = select_stats_candidates(
                root=args.root,
                candidate_roots=args.candidate_root,
                output_root=args.output_root,
                commit_sha=args.commit_sha,
                run_id=args.run_id,
                run_attempt=args.run_attempt,
                workflow=args.workflow,
                consumer_retry_context=_from_arguments(args, STATS_ARTIFACT),
            )
            result = {
                "artifact": STATS_ARTIFACT,
                "selected": [
                    {
                        "logical_shard": shard,
                        "physical_artifact": selection.physical_artifact,
                        "producer_attempt": selection.producer_attempt,
                    }
                    for shard, selection in sorted(selected.items())
                ],
            }
        elif args.command == "create-universe":
            payload = create_universe_artifact(
                root=args.root,
                output=args.manifest,
                mode=args.mode,
                commit_sha=args.commit_sha,
                run_id=args.run_id,
                run_attempt=args.run_attempt,
                workflow=args.workflow,
                retry_provenance=_from_arguments(args, UNIVERSE_ARTIFACT),
            )
            result = {"artifact": UNIVERSE_ARTIFACT, "mode": payload["mode"]}
        else:
            selection = select_universe_candidate(
                candidate_roots=args.candidate_root,
                output_root=args.output_root,
                selection_evidence=args.selection_evidence,
                commit_sha=args.commit_sha,
                run_id=args.run_id,
                run_attempt=args.run_attempt,
                workflow=args.workflow,
                expected_mode=args.expected_mode,
                consumer_retry_context=_from_arguments(args, UNIVERSE_ARTIFACT),
            )
            result = {
                "artifact": UNIVERSE_ARTIFACT,
                "mode": selection.manifest["mode"],
                "selected_producer_attempt": selection.producer_attempt,
            }
    except (
        ArtifactValidationError,
        OSError,
        ProvenanceError,
        RetryArtifactError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
