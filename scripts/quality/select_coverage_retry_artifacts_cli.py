"""Fail-closed CLI adapter for selecting complete coverage retry evidence.

The artifact layout is never accepted from a downloaded candidate or inline
workflow data.  It comes from the repository-owned
``quality/coverage-retry-layout.json`` file and must exactly cover the report
inventory declared by ``quality/quality-contract.json``.  Both files are bound
into the immutable consumer retry context before the generic selector sees any
candidate artifact.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path, PureWindowsPath
from typing import Any, NoReturn

# A direct file invocation places ``scripts/quality`` rather than the
# repository root on ``sys.path``.  Prepend the resolved source repository
# only for that invocation mode; package imports and ``python -m`` keep their
# normal import semantics.
if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.quality.coverage_retry_context import (
    RetryContextError,
    build_consumer_retry_context,
    validate_consumer_retry_context,
)
from scripts.quality.select_coverage_artifacts import (
    CoverageArtifactSlot,
    CoverageReportSpec,
    CoverageSelectionError,
    select_coverage_artifacts,
)

COVERAGE_RETRY_LAYOUT_PATH = Path("quality/coverage-retry-layout.json")
QUALITY_CONTRACT_PATH = Path("quality/quality-contract.json")
_LAYOUT_SCHEMA_VERSION = 1
_LAYOUT_FIELDS = frozenset({"schema_version", "slots"})
_SLOT_FIELDS = frozenset(
    {"logical_artifact", "producer_job", "metadata_path", "reports"}
)
_REPORT_FIELDS = frozenset({"component", "format", "path"})


class CoverageRetryLayoutError(ValueError):
    """Raised when the repository-owned retry layout is unsafe or stale."""


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise CoverageRetryLayoutError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _reject_json_constant(value: str) -> NoReturn:
    raise CoverageRetryLayoutError(f"invalid JSON constant: {value}")


def _read_json(path: Path, field: str) -> object:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_json_object,
            parse_constant=_reject_json_constant,
        )
    except CoverageRetryLayoutError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CoverageRetryLayoutError(f"unable to parse {field}: {path}") from error


def _require_object(value: object, field: str) -> Mapping[object, object]:
    if not isinstance(value, Mapping):
        raise CoverageRetryLayoutError(f"{field} must be an object")
    return value


def _require_exact_fields(
    value: Mapping[object, object], expected: frozenset[str], field: str
) -> None:
    actual = frozenset(value)
    missing = sorted(expected - actual)
    unexpected = sorted(str(name) for name in actual - expected)
    if missing:
        raise CoverageRetryLayoutError(f"{field} missing fields: {', '.join(missing)}")
    if unexpected:
        raise CoverageRetryLayoutError(
            f"{field} has unexpected fields: {', '.join(unexpected)}"
        )


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CoverageRetryLayoutError(f"{field} must be a non-empty string")
    if "\x00" in value or "\r" in value or "\n" in value:
        raise CoverageRetryLayoutError(f"{field} contains forbidden control characters")
    return value


def _parse_reports(value: object, field: str) -> tuple[CoverageReportSpec, ...]:
    if not isinstance(value, list) or not value:
        raise CoverageRetryLayoutError(f"{field} must be a non-empty array")
    reports: list[CoverageReportSpec] = []
    for index, raw_report in enumerate(value):
        report = _require_object(raw_report, f"{field}[{index}]")
        _require_exact_fields(report, _REPORT_FIELDS, f"{field}[{index}]")
        reports.append(
            CoverageReportSpec(
                component=_require_text(
                    report["component"], f"{field}[{index}].component"
                ),
                report_format=_require_text(
                    report["format"], f"{field}[{index}].format"
                ),
                path=_require_text(report["path"], f"{field}[{index}].path"),
            )
        )
    return tuple(reports)


def _report_identities(
    reports: Sequence[CoverageReportSpec], field: str
) -> set[tuple[str, str, str]]:
    identities = {
        (report.component, report.report_format, report.path) for report in reports
    }
    if len(identities) != len(reports):
        raise CoverageRetryLayoutError(f"{field} contains duplicate report identities")
    return identities


def _parse_contract_reports(repository_root: Path) -> set[tuple[str, str, str]]:
    contract = _require_object(
        _read_json(repository_root / QUALITY_CONTRACT_PATH, "quality contract"),
        "quality contract",
    )
    try:
        reports = _parse_reports(
            contract["coverage_reports"], "quality contract coverage_reports"
        )
    except KeyError as error:
        raise CoverageRetryLayoutError(
            "quality contract missing fields: coverage_reports"
        ) from error
    return _report_identities(reports, "quality contract coverage_reports")


def load_coverage_retry_layout(
    repository_root: Path,
) -> tuple[CoverageArtifactSlot, ...]:
    """Parse the fixed retry layout and bind its reports to the quality contract.

    The CLI calls this only after ``coverage_retry_context`` validated the
    layout and contract as trusted regular policy inputs.  It returns plain
    selector slots, leaving candidate provenance and filesystem isolation to
    the generic selector.
    """

    layout = _require_object(
        _read_json(
            repository_root / COVERAGE_RETRY_LAYOUT_PATH, "coverage retry layout"
        ),
        "coverage retry layout",
    )
    _require_exact_fields(layout, _LAYOUT_FIELDS, "coverage retry layout")
    schema_version = layout["schema_version"]
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version != _LAYOUT_SCHEMA_VERSION
    ):
        raise CoverageRetryLayoutError(
            f"coverage retry layout.schema_version must equal {_LAYOUT_SCHEMA_VERSION}"
        )
    raw_slots = layout["slots"]
    if not isinstance(raw_slots, list) or not raw_slots:
        raise CoverageRetryLayoutError(
            "coverage retry layout.slots must contain at least one slot"
        )
    slots: list[CoverageArtifactSlot] = []
    for index, raw_slot in enumerate(raw_slots):
        slot = _require_object(raw_slot, f"coverage retry layout.slots[{index}]")
        _require_exact_fields(
            slot, _SLOT_FIELDS, f"coverage retry layout.slots[{index}]"
        )
        slots.append(
            CoverageArtifactSlot(
                logical_artifact=_require_text(
                    slot["logical_artifact"],
                    f"coverage retry layout.slots[{index}].logical_artifact",
                ),
                producer_job=_require_text(
                    slot["producer_job"],
                    f"coverage retry layout.slots[{index}].producer_job",
                ),
                metadata_path=_require_text(
                    slot["metadata_path"],
                    f"coverage retry layout.slots[{index}].metadata_path",
                ),
                reports=_parse_reports(
                    slot["reports"], f"coverage retry layout.slots[{index}].reports"
                ),
            )
        )
    layout_reports = _report_identities(
        tuple(report for slot in slots for report in slot.reports),
        "coverage retry layout reports",
    )
    if layout_reports != _parse_contract_reports(repository_root):
        raise CoverageRetryLayoutError(
            "coverage retry layout report inventory does not exactly match quality contract"
        )
    return tuple(slots)


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--candidate-root", type=Path, action="append", required=True)
    parser.add_argument("--destination-root", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--workflow-ref", required=True)
    parser.add_argument("--workflow-sha", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--consumer-job", required=True)
    parser.add_argument("--config-input", type=Path, action="append", required=True)
    return parser.parse_args(argv)


def _repository_path(repository_root: Path, value: Path) -> Path:
    """Resolve a repository-relative artifact root without allowing escapes."""

    if ".." in value.parts:
        raise CoverageRetryLayoutError(
            "artifact roots must not contain parent traversal"
        )
    if value.is_absolute() or value.drive or PureWindowsPath(str(value)).drive:
        raise CoverageRetryLayoutError(
            "artifact roots must be repository-relative, not absolute"
        )
    lexical_repository_root = Path(os.path.abspath(repository_root))
    _reject_linked_components(lexical_repository_root, value)
    resolved_repository_root = lexical_repository_root.resolve()
    resolved_value = (lexical_repository_root / value).resolve()
    try:
        resolved_value.relative_to(resolved_repository_root)
    except ValueError as error:
        raise CoverageRetryLayoutError(
            "artifact roots must resolve inside the repository root"
        ) from error
    _reject_linked_components(lexical_repository_root, value)
    return resolved_value


def _is_link_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    isjunction = getattr(os.path, "isjunction", None)
    return bool(isjunction is not None and isjunction(path))


def _reject_linked_components(repository_root: Path, value: Path) -> None:
    """Reject a lexical artifact path that traverses a link before resolving it."""

    if _is_link_or_junction(repository_root):
        raise CoverageRetryLayoutError(
            "artifact roots must not traverse a symlink or junction"
        )
    current = repository_root
    for part in value.parts:
        current /= part
        if _is_link_or_junction(current):
            raise CoverageRetryLayoutError(
                "artifact roots must not traverse a symlink or junction"
            )


def _build_context(arguments: argparse.Namespace) -> dict[str, str]:
    return build_consumer_retry_context(
        repository_root=arguments.repository_root,
        config_inputs=arguments.config_input,
        policy_inputs=(QUALITY_CONTRACT_PATH, COVERAGE_RETRY_LAYOUT_PATH),
        repository=arguments.repository,
        run_id=arguments.run_id,
        workflow_ref=arguments.workflow_ref,
        workflow_sha=arguments.workflow_sha,
        event=arguments.event,
    )


def _validate_context(arguments: argparse.Namespace, context: dict[str, str]) -> None:
    validate_consumer_retry_context(
        context,
        repository_root=arguments.repository_root,
        config_inputs=arguments.config_input,
        policy_inputs=(QUALITY_CONTRACT_PATH, COVERAGE_RETRY_LAYOUT_PATH),
        repository=arguments.repository,
        run_id=arguments.run_id,
        workflow_ref=arguments.workflow_ref,
        workflow_sha=arguments.workflow_sha,
        event=arguments.event,
    )


def _select(arguments: argparse.Namespace) -> dict[str, object]:
    context = _build_context(arguments)
    slots = load_coverage_retry_layout(arguments.repository_root)
    # Detect a policy/source change between parsing the trusted layout and
    # handing its slots to the generic candidate selector.
    _validate_context(arguments, context)
    result = select_coverage_artifacts(
        repository_root=arguments.repository_root,
        candidate_roots=tuple(
            _repository_path(arguments.repository_root, candidate)
            for candidate in arguments.candidate_root
        ),
        slots=slots,
        destination_root=_repository_path(
            arguments.repository_root, arguments.destination_root
        ),
        expected_sha=context["source_sha"],
        expected_repository=context["repository"],
        expected_run_id=context["run_id"],
        expected_run_attempt=arguments.run_attempt,
        expected_workflow_ref=context["workflow_ref"],
        expected_workflow_sha=context["workflow_sha"],
        expected_event=context["event"],
        expected_consumer_job=arguments.consumer_job,
        consumer_retry_context=context,
    )
    return {
        "consumer_job": arguments.consumer_job,
        "layout": COVERAGE_RETRY_LAYOUT_PATH.as_posix(),
        "receipt_path": str(result.receipt_path),
        "selections": [
            {
                "logical_artifact": selection.logical_artifact,
                "physical_artifact": selection.physical_artifact,
                "producer_attempt": selection.producer_attempt,
            }
            for selection in result.selections
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Select validated coverage retry evidence and print its receipt summary."""

    arguments = _arguments(argv)
    try:
        summary = _select(arguments)
    except (
        CoverageRetryLayoutError,
        CoverageSelectionError,
        OSError,
        RetryContextError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
