"""Select complete, provenance-bound Lighthouse retry evidence.

The Lighthouse producer publishes one immutable logical artifact named
``lighthouse-reports`` per workflow attempt.  Each physical candidate must be
downloaded into its own directory named ``lighthouse-reports-attempt-<N>`` and
must contain exactly this layout::

    provenance/lighthouse-reports.json
    lhr/core/lhr-00.json .. lhr/core/lhr-08.json
    lhr/content/lhr-00.json .. lhr/content/lhr-08.json
    lhr/realtime/lhr-00.json .. lhr/realtime/lhr-08.json
    lhr/fallback/lhr-00.json .. lhr/fallback/lhr-02.json

The sidecar uses the shared provenance schema.  This module intentionally
delegates isolation, symlink/junction rejection, byte hashing, retry identity
validation, deterministic candidate selection, and atomic output replacement
to ``select_coverage_artifacts``.  Keeping one hardened implementation for
all artifact families prevents Lighthouse retries from drifting into a weaker
trust boundary.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any

from scripts.quality.select_coverage_artifacts import (
    CoverageArtifactSelection,
    CoverageArtifactSlot,
    CoverageReportSpec,
    CoverageSelectionError,
    select_coverage_artifacts,
)

LIGHTHOUSE_LOGICAL_ARTIFACT = "lighthouse-reports"
LIGHTHOUSE_PRODUCER_JOB = "lighthouse"
LIGHTHOUSE_METADATA_PATH = "provenance/lighthouse-reports.json"
LIGHTHOUSE_LHR_FORMAT = "lighthouse-lhr-json"
LIGHTHOUSE_SHARD_REPORT_COUNTS = MappingProxyType(
    {
        "core": 9,
        "content": 9,
        "realtime": 9,
        "fallback": 3,
    }
)


class LighthouseSelectionError(ValueError):
    """Raised when Lighthouse retry evidence cannot be trusted."""


@dataclass(frozen=True)
class LighthouseArtifactSelection:
    """The one selected physical Lighthouse artifact."""

    logical_artifact: str
    physical_artifact: str
    producer_attempt: int
    candidate_root: Path


@dataclass(frozen=True)
class LighthouseSelectionResult:
    """The selected evidence, its reports root, and immutable receipt."""

    selection: LighthouseArtifactSelection
    reports_root: Path
    receipt_path: Path


def expected_lighthouse_report_specs() -> tuple[CoverageReportSpec, ...]:
    """Return the canonical 30-report Lighthouse matrix inventory."""

    reports = [
        CoverageReportSpec(
            component=f"lighthouse-{shard}",
            report_format=LIGHTHOUSE_LHR_FORMAT,
            path=f"lhr/{shard}/lhr-{index:02d}.json",
        )
        for shard, count in LIGHTHOUSE_SHARD_REPORT_COUNTS.items()
        for index in range(count)
    ]
    return tuple(sorted(reports, key=lambda report: report.path))


def lighthouse_artifact_slot() -> CoverageArtifactSlot:
    """Build the fixed producer slot consumed by the retry selector."""

    return CoverageArtifactSlot(
        logical_artifact=LIGHTHOUSE_LOGICAL_ARTIFACT,
        producer_job=LIGHTHOUSE_PRODUCER_JOB,
        metadata_path=LIGHTHOUSE_METADATA_PATH,
        reports=expected_lighthouse_report_specs(),
    )


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in pairs:
        if key in payload:
            raise LighthouseSelectionError(
                f"duplicate JSON key in Lighthouse LHR: {key}"
            )
        payload[key] = value
    return payload


def _reject_json_constant(value: str) -> None:
    raise LighthouseSelectionError(f"invalid JSON constant in Lighthouse LHR: {value}")


def _is_link_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    isjunction = getattr(os.path, "isjunction", None)
    return bool(isjunction is not None and isjunction(path))


def _normal_path_text(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def _safe_repository_root(repository_root: Path) -> Path:
    lexical = Path(os.path.abspath(repository_root))
    if _is_link_or_junction(lexical):
        raise LighthouseSelectionError(
            f"repository root must not be a symlink or junction: {repository_root}"
        )
    try:
        resolved = lexical.resolve(strict=True)
    except OSError as error:
        raise LighthouseSelectionError(
            f"repository root is unavailable: {repository_root}"
        ) from error
    if _normal_path_text(lexical) != _normal_path_text(resolved):
        raise LighthouseSelectionError(
            f"repository root traverses a symlink or junction: {repository_root}"
        )
    if not resolved.is_dir():
        raise LighthouseSelectionError(
            f"repository root is not a directory: {resolved}"
        )
    return resolved


def _safe_destination(repository_root: Path, destination_root: Path) -> Path:
    destination = Path(os.path.abspath(destination_root))
    try:
        relative = destination.relative_to(repository_root)
    except ValueError as error:
        raise LighthouseSelectionError(
            "destination root must stay inside the trusted repository root"
        ) from error
    if not relative.parts or relative.parts[0] == ".git":
        raise LighthouseSelectionError("destination root is unsafe")
    current = repository_root
    for index, part in enumerate(relative.parts):
        current /= part
        is_destination = index == len(relative.parts) - 1
        if current.exists():
            if _is_link_or_junction(current):
                raise LighthouseSelectionError(
                    f"destination root traverses a symlink or junction: {current}"
                )
            if not is_destination and not current.is_dir():
                raise LighthouseSelectionError(
                    f"destination parent is not a directory: {current}"
                )
        elif not is_destination:
            current.mkdir()
    if destination.exists() or _is_link_or_junction(destination):
        raise LighthouseSelectionError(
            f"destination root must not already exist: {destination}"
        )
    return destination


def _validate_lhr(path: Path) -> None:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_json_object,
            parse_constant=_reject_json_constant,
        )
    except LighthouseSelectionError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise LighthouseSelectionError(
            f"unable to parse Lighthouse LHR JSON: {path}"
        ) from error
    if not isinstance(payload, dict):
        raise LighthouseSelectionError(f"Lighthouse LHR must be a JSON object: {path}")
    final_url = payload.get("finalUrl")
    if not isinstance(final_url, str) or not final_url.strip():
        raise LighthouseSelectionError(
            f"Lighthouse LHR finalUrl must be a non-empty string: {path}"
        )


def _validate_materialized_lhrs(reports_root: Path) -> None:
    if not reports_root.is_dir() or _is_link_or_junction(reports_root):
        raise LighthouseSelectionError(
            f"selected Lighthouse reports root is unavailable: {reports_root}"
        )
    for specification in expected_lighthouse_report_specs():
        report = reports_root.joinpath(*PurePosixPath(specification.path).parts)
        if not report.is_file() or _is_link_or_junction(report):
            raise LighthouseSelectionError(
                f"selected Lighthouse LHR is unavailable: {specification.path}"
            )
        _validate_lhr(report)


def _selection_from_coverage(
    selection: CoverageArtifactSelection,
) -> LighthouseArtifactSelection:
    if selection.logical_artifact != LIGHTHOUSE_LOGICAL_ARTIFACT:
        raise LighthouseSelectionError(
            "coverage selector returned an unexpected Lighthouse logical artifact"
        )
    return LighthouseArtifactSelection(
        logical_artifact=selection.logical_artifact,
        physical_artifact=selection.physical_artifact,
        producer_attempt=selection.producer_attempt,
        candidate_root=selection.candidate_root,
    )


def select_lighthouse_artifacts(
    *,
    repository_root: Path,
    candidate_roots: Collection[Path],
    destination_root: Path,
    expected_sha: str,
    expected_repository: str,
    expected_run_id: str,
    expected_run_attempt: str,
    expected_workflow_ref: str,
    expected_workflow_sha: str,
    expected_event: str,
    expected_consumer_job: str,
    consumer_retry_context: Mapping[str, str],
) -> LighthouseSelectionResult:
    """Select the highest valid Lighthouse retry and atomically materialize it.

    A candidate from a foreign run, a later attempt, an incomplete matrix, or
    a duplicate/tampered sidecar makes the entire selection fail.  The output
    is the shared atomic selection directory containing a provenance receipt
    and the fixed ``lighthouse-reports`` report subtree.
    """

    trusted_root = _safe_repository_root(repository_root)
    destination = _safe_destination(trusted_root, destination_root)
    with tempfile.TemporaryDirectory(
        prefix=".lighthouse-selection-validate.", dir=trusted_root
    ) as temporary_root:
        private_destination = Path(temporary_root) / "selected"
        try:
            selection = select_coverage_artifacts(
                repository_root=trusted_root,
                candidate_roots=candidate_roots,
                slots=(lighthouse_artifact_slot(),),
                destination_root=private_destination,
                expected_sha=expected_sha,
                expected_repository=expected_repository,
                expected_run_id=expected_run_id,
                expected_run_attempt=expected_run_attempt,
                expected_workflow_ref=expected_workflow_ref,
                expected_workflow_sha=expected_workflow_sha,
                expected_event=expected_event,
                expected_consumer_job=expected_consumer_job,
                consumer_retry_context=consumer_retry_context,
            )
        except CoverageSelectionError as error:
            raise LighthouseSelectionError(str(error)) from error
        if len(selection.selections) != 1:
            raise LighthouseSelectionError(
                "coverage selector must return exactly one Lighthouse artifact"
            )
        selected = _selection_from_coverage(selection.selections[0])
        reports_root = selection.receipt_path.parent / LIGHTHOUSE_LOGICAL_ARTIFACT
        _validate_materialized_lhrs(reports_root)
        os.replace(private_destination, destination)
    return LighthouseSelectionResult(
        selection=selected,
        reports_root=destination / LIGHTHOUSE_LOGICAL_ARTIFACT,
        receipt_path=destination / "selection-receipt.json",
    )
