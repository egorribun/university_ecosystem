#!/usr/bin/env python3
"""Build a deterministic, read-only timing ledger for one GitHub Actions run.

The analyzer deliberately treats the GitHub API payload as evidence rather than
as an instruction.  It never mutates a run, retries a job, or accepts a report
from another run.  A fixture can be supplied with ``--jobs-json`` for local
reproducibility; otherwise ``gh api --paginate`` is used to read the jobs for
the requested run. Exact critical-path analysis requires an attempt-bound DAG
sidecar supplied with ``--dag-json`` plus a detached provenance record obtained
from the same-run-artifact selector. API-only timing is available only through
the explicitly labelled ``--diagnostic-lower-bound`` mode.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import tempfile
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
ISO_RE = re.compile(r"Z$", re.ASCII)
SHA_RE = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_JOBS = 2048
MAX_STEPS_PER_JOB = 512
MAX_NEEDS_PER_JOB = 512
MAX_WORKFLOW_FILES = 256
MAX_ERROR_CHARS = 2000
MAX_TEXT_CHARS = 4096
MAX_FETCH_SECONDS = 120
_NON_TIMEOUT_CONCLUSIONS = frozenset(
    {
        "success",
        "failure",
        "neutral",
        "cancelled",
        "skipped",
        "action_required",
        "stale",
        "startup_failure",
    }
)
_TERMINAL_CONCLUSIONS = _NON_TIMEOUT_CONCLUSIONS | {"timed_out"}


class AnalysisError(ValueError):
    """Raised when run evidence is malformed or incomplete."""


def _parse_timestamp(value: object, field: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise AnalysisError(f"{field} must be an ISO-8601 timestamp or null")
    candidate = ISO_RE.sub("+00:00", value)
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as error:
        raise AnalysisError(f"{field} is not a valid ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise AnalysisError(f"{field} must include a timezone")
    return parsed.astimezone(UTC)


def _positive_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AnalysisError(f"{field} must be a positive integer")
    return value


def _text(value: object, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise AnalysisError(f"{field} must be a non-empty string")
    if len(value) > MAX_TEXT_CHARS:
        raise AnalysisError(f"{field} exceeds maximum length of {MAX_TEXT_CHARS}")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise AnalysisError(f"{field} contains a forbidden control character")
    return value


@dataclass(frozen=True)
class StepTiming:
    name: str
    started_at: datetime | None
    completed_at: datetime | None
    conclusion: str | None = None

    @property
    def seconds(self) -> float | None:
        if self.started_at is None or self.completed_at is None:
            return None
        return max(0.0, (self.completed_at - self.started_at).total_seconds())


@dataclass(frozen=True)
class JobTiming:
    job_id: int
    name: str
    status: str
    conclusion: str | None
    queued_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    needs: tuple[str, ...]
    steps: tuple[StepTiming, ...]
    core_failure: bool
    api_run_id: int | None = None
    api_run_attempt: int | None = None
    api_head_sha: str | None = None

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at is None or self.completed_at is None:
            return None
        return max(0.0, (self.completed_at - self.started_at).total_seconds())

    @property
    def queue_wait_seconds(self) -> float | None:
        if self.queued_at is None or self.started_at is None:
            return None
        return max(0.0, (self.started_at - self.queued_at).total_seconds())


@dataclass(frozen=True)
class DAGEvidence:
    """Validated, attempt-bound dependency and artifact metadata."""

    dependency_ids: dict[int, tuple[int, ...]]
    logical_ids: dict[int, str]
    core_failures: dict[int, bool]
    run_attempt: int
    source_head_sha: str
    tested_commit_sha: str
    workflow_path: str
    workflow_ref: str
    workflow_sha: str
    workflow_files_sha256: dict[str, str]
    dag_sha256: str
    artifact_id: int
    artifact_name: str
    artifact_digest: str
    producer_attempt: int


def _canonical_json(value: Mapping[str, object]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise AnalysisError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_non_finite_json_constant(value: str) -> object:
    raise AnalysisError(f"non-finite JSON constant {value!r} is not allowed")


def _parse_json_text(text: str, *, source: str) -> object:
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_non_finite_json_constant,
        )
    except AnalysisError:
        raise
    except (json.JSONDecodeError, RecursionError) as error:
        raise AnalysisError(f"{source} contains invalid JSON") from error


def _validate_sha(value: object, field: str, *, sha256_only: bool = False) -> str:
    text = _text(value, field)
    matcher = SHA256_RE if sha256_only else SHA_RE
    if not matcher.fullmatch(text):
        expected = (
            "a 64-character SHA-256 digest"
            if sha256_only
            else "a 40- or 64-character commit SHA"
        )
        raise AnalysisError(f"{field} must be {expected}")
    return text.lower()


def _validate_artifact_digest(value: object, field: str) -> str:
    """Normalize GitHub's ``sha256:<hex>`` artifact digest representation."""
    text = _text(value, field)
    if text.startswith("sha256:"):
        text = text.removeprefix("sha256:")
    return _validate_sha(text, field, sha256_only=True)


def _validate_trusted_provenance(
    value: object,
    *,
    repository: str,
    run_id: int,
    run_attempt: int,
    source_head_sha: str,
    tested_commit_sha: str,
    workflow_path: str,
    workflow_ref: str,
    workflow_sha: str,
    workflow_files_sha256: Mapping[str, str],
    dag_sha256: str,
) -> tuple[int, str, str, int]:
    """Bind a DAG to a detached same-run artifact-selector record.

    The selector record is intentionally separate from the DAG JSON. A
    checksum on the DAG alone proves integrity only after the producer is
    trusted; requiring this independently selected artifact identity prevents
    a caller from changing provenance fields and recomputing ``dag_sha256``
    without detection. Cryptographic authenticity of the selector itself is
    owned by its GitHub API/attestation workflow and is not invented here.
    """
    if not isinstance(value, Mapping):
        raise AnalysisError(
            "strict analysis requires an authenticated provenance record"
        )
    allowed = {
        "selector",
        "repository",
        "run_id",
        "run_attempt",
        "source_head_sha",
        "tested_commit_sha",
        "workflow_path",
        "workflow_ref",
        "workflow_sha",
        "workflow_files_sha256",
        "artifact_id",
        "artifact_name",
        "artifact_digest",
        "producer_attempt",
        "dag_sha256",
    }
    unknown = sorted(str(key) for key in set(value) - allowed)
    if unknown:
        raise AnalysisError(
            "trusted provenance contains unknown fields: " + ", ".join(unknown)
        )
    if value.get("selector") != "select_same_run_artifact_cli":
        raise AnalysisError("trusted provenance selector is not approved")
    expected_scalars = {
        "repository": repository,
        "run_id": run_id,
        "run_attempt": run_attempt,
        "source_head_sha": source_head_sha,
        "tested_commit_sha": tested_commit_sha,
        "workflow_path": workflow_path,
        "workflow_ref": workflow_ref,
        "workflow_sha": workflow_sha,
        "dag_sha256": dag_sha256,
    }
    for field, expected in expected_scalars.items():
        actual = value.get(field)
        if type(actual) is not type(expected) or actual != expected:
            raise AnalysisError(f"trusted provenance {field} does not match DAG")
    trusted_workflow_hashes = value.get("workflow_files_sha256")
    if not isinstance(trusted_workflow_hashes, Mapping):
        raise AnalysisError("trusted provenance workflow_files_sha256 is malformed")
    if dict(trusted_workflow_hashes) != dict(workflow_files_sha256):
        raise AnalysisError(
            "trusted provenance workflow_files_sha256 does not match DAG"
        )
    artifact_id = _positive_integer(
        value.get("artifact_id"), "trusted provenance artifact_id"
    )
    artifact_name = _text(
        value.get("artifact_name"), "trusted provenance artifact_name"
    )
    artifact_digest = _validate_artifact_digest(
        value.get("artifact_digest"),
        "trusted provenance artifact_digest",
    )
    producer_attempt = _positive_integer(
        value.get("producer_attempt"), "trusted provenance producer_attempt"
    )
    if producer_attempt > run_attempt:
        raise AnalysisError("trusted provenance producer_attempt is from the future")
    return artifact_id, artifact_name, artifact_digest, producer_attempt


def _decode_jobs_payload(payload: object) -> list[Mapping[str, object]]:
    """Accept one API page, slurped API pages, or a fixture with ``jobs``.

    ``gh api --paginate --slurp`` emits a JSON array whose elements are the
    page objects returned by GitHub (each page has a ``jobs`` array).  The
    original implementation only flattened arrays, so a live paginated fetch
    treated each page envelope as a job and failed closed.  Keep the decoder
    strict while normalising both the single-page and slurped forms.
    """

    page_candidates: object
    if isinstance(payload, Mapping):
        page_candidates = [payload]
    elif isinstance(payload, list):
        page_candidates = payload
    else:
        raise AnalysisError(
            "jobs payload must be an array or an object containing jobs"
        )

    flattened: list[object] = []
    expected_total: int | None = None
    for index, page in enumerate(page_candidates):
        if isinstance(page, Mapping) and "jobs" in page:
            jobs = page["jobs"]
            if not isinstance(jobs, list):
                raise AnalysisError(f"jobs page {index} must contain an array")
            if "total_count" in page:
                total_count = page["total_count"]
                if (
                    isinstance(total_count, bool)
                    or not isinstance(total_count, int)
                    or total_count < 0
                    or total_count > MAX_JOBS
                ):
                    raise AnalysisError(f"jobs page {index} total_count is invalid")
                if expected_total is None:
                    expected_total = total_count
                elif total_count != expected_total:
                    raise AnalysisError("jobs pagination total_count changed")
                if len(flattened) + len(jobs) > expected_total:
                    raise AnalysisError("jobs pagination contains too many records")
            flattened.extend(jobs)
        elif isinstance(page, list):
            flattened.extend(page)
        elif isinstance(page, Mapping):
            # A plain list of job records is also a supported fixture shape;
            # preserve it without accepting arbitrary page envelopes.
            flattened.append(page)
        else:
            raise AnalysisError(f"jobs page {index} must be an object or array")
        if len(flattened) > MAX_JOBS:
            raise AnalysisError(f"jobs payload exceeds maximum of {MAX_JOBS} jobs")

    if expected_total is not None and len(flattened) != expected_total:
        raise AnalysisError(
            "jobs pagination is incomplete: expected "
            f"{expected_total} records, received {len(flattened)}"
        )

    records: list[Mapping[str, object]] = []
    for index, item in enumerate(flattened):
        if not isinstance(item, Mapping):
            raise AnalysisError(f"jobs[{index}] must be an object")
        records.append(item)
    return records


def _parse_steps(raw: object, job_name: str) -> tuple[StepTiming, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise AnalysisError(f"job {job_name!r} steps must be an array")
    if len(raw) > MAX_STEPS_PER_JOB:
        raise AnalysisError(
            f"job {job_name!r} steps exceed maximum of {MAX_STEPS_PER_JOB}"
        )
    result: list[StepTiming] = []
    for index, value in enumerate(raw):
        if not isinstance(value, Mapping):
            raise AnalysisError(f"job {job_name!r} step {index} must be an object")
        name = _text(value.get("name"), f"job {job_name!r} step {index}.name")
        step_conclusion_value = value.get("conclusion")
        step_conclusion = (
            None
            if step_conclusion_value is None
            else _text(
                step_conclusion_value,
                f"job {job_name!r} step {index}.conclusion",
            )
        )
        started = _parse_timestamp(
            value.get("started_at"), f"job {job_name!r} step {index}.started_at"
        )
        completed = _parse_timestamp(
            value.get("completed_at"), f"job {job_name!r} step {index}.completed_at"
        )
        if started is not None and completed is not None and completed < started:
            raise AnalysisError(f"job {job_name!r} step {index} ends before it starts")
        result.append(StepTiming(name, started, completed, step_conclusion))
    return tuple(result)


def _parse_needs(value: object, job_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values: Sequence[object] = (value,)
    elif isinstance(value, list):
        values = value
    else:
        raise AnalysisError(f"job {job_name!r}.needs must be a string or array")
    if len(values) > MAX_NEEDS_PER_JOB:
        raise AnalysisError(
            f"job {job_name!r}.needs exceeds maximum of {MAX_NEEDS_PER_JOB}"
        )
    result = tuple(
        sorted(
            {
                _text(item, f"job {job_name!r}.needs[{index}]")
                for index, item in enumerate(values)
            }
        )
    )
    return result


def parse_jobs(payload: object) -> tuple[JobTiming, ...]:
    """Parse and validate jobs, rejecting duplicate IDs and impossible times."""
    records = _decode_jobs_payload(payload)
    jobs: list[JobTiming] = []
    seen: set[int] = set()
    for index, record in enumerate(records):
        job_id = _positive_integer(record.get("id"), f"jobs[{index}].id")
        if job_id in seen:
            raise AnalysisError(f"duplicate job id {job_id}")
        seen.add(job_id)
        name = _text(record.get("name"), f"jobs[{index}].name")
        status = _text(record.get("status", "completed"), f"job {name!r}.status")
        conclusion_value = record.get("conclusion")
        conclusion = (
            None
            if conclusion_value is None
            else _text(conclusion_value, f"job {name!r}.conclusion")
        )
        # GitHub's Jobs API does not currently populate ``queued_at`` for live
        # jobs.  ``created_at`` is the authoritative queued/created timestamp
        # in that payload shape; prefer an explicit queued_at when available,
        # but fall back only when it is absent or explicitly null.  A malformed
        # value in either field remains a hard error rather than silently
        # reporting zero queue wait.
        queued_field = "queued_at"
        queued_value = record.get("queued_at")
        if queued_value is None and "created_at" in record:
            queued_field = "created_at"
            queued_value = record.get("created_at")
        queued = _parse_timestamp(queued_value, f"job {name!r}.{queued_field}")
        started = _parse_timestamp(record.get("started_at"), f"job {name!r}.started_at")
        completed = _parse_timestamp(
            record.get("completed_at"), f"job {name!r}.completed_at"
        )
        steps = _parse_steps(record.get("steps"), name)
        core_failure_value = record.get("core_failure", False)
        if not isinstance(core_failure_value, bool):
            raise AnalysisError(f"job {name!r}.core_failure must be boolean")
        if queued is not None and started is not None and queued > started:
            raise AnalysisError(f"job {name!r} {queued_field} is after it starts")
        if started is not None and completed is not None and completed < started:
            # GitHub occasionally emits a one-second inverted pair for a
            # skipped or cancelled job that never received a runner (there
            # are no steps and therefore no elapsed work to measure). Treat
            # that API sentinel as a zero-duration guarded terminal job, but
            # keep malformed timestamps a hard error for every job that
            # could have executed.
            if (
                conclusion in {"skipped", "cancelled"}
                and not steps
                and started - completed <= timedelta(seconds=1)
            ):
                completed = started
            else:
                raise AnalysisError(f"job {name!r} ends before it starts")
        jobs.append(
            JobTiming(
                job_id=job_id,
                name=name,
                status=status,
                conclusion=conclusion,
                queued_at=queued,
                started_at=started,
                completed_at=completed,
                needs=_parse_needs(record.get("needs"), name),
                steps=steps,
                core_failure=core_failure_value,
                api_run_id=(
                    None
                    if record.get("run_id") is None
                    else _positive_integer(record.get("run_id"), f"job {name!r}.run_id")
                ),
                api_run_attempt=(
                    None
                    if record.get("run_attempt") is None
                    else _positive_integer(
                        record.get("run_attempt"), f"job {name!r}.run_attempt"
                    )
                ),
                api_head_sha=(
                    None
                    if record.get("head_sha") is None
                    else _validate_sha(record.get("head_sha"), f"job {name!r}.head_sha")
                ),
            )
        )
    return tuple(
        sorted(
            jobs,
            key=lambda job: (
                job.started_at or datetime.max.replace(tzinfo=UTC),
                job.job_id,
            ),
        )
    )


def _validate_dag_sidecar(
    dag: object,
    jobs: Sequence[JobTiming],
    *,
    repository: str,
    run_id: int,
    trusted_provenance: object | None,
) -> DAGEvidence:
    """Validate a normalized, immutable DAG envelope for exact analysis."""
    if not isinstance(dag, Mapping):
        raise AnalysisError("strict analysis requires a DAG sidecar object")
    if type(dag.get("schema_version")) is not int or dag.get("schema_version") != 1:
        raise AnalysisError("DAG sidecar schema_version must be 1")
    if dag.get("repository") != repository:
        raise AnalysisError("DAG sidecar repository does not match run repository")
    if type(dag.get("run_id")) is not int or dag.get("run_id") != run_id:
        raise AnalysisError("DAG sidecar run_id does not match requested run_id")
    sidecar_run_attempt = _positive_integer(
        dag.get("run_attempt"), "DAG sidecar run_attempt"
    )
    sidecar_source_sha = _validate_sha(
        dag.get("source_head_sha"), "DAG sidecar source_head_sha"
    )
    sidecar_tested_sha = _validate_sha(
        dag.get("tested_commit_sha"), "DAG sidecar tested_commit_sha"
    )
    workflow_path = _text(dag.get("workflow_path"), "DAG sidecar workflow_path")
    workflow_ref = _text(dag.get("workflow_ref"), "DAG sidecar workflow_ref")
    workflow_sha = _validate_sha(dag.get("workflow_sha"), "DAG sidecar workflow_sha")

    workflow_hashes = dag.get("workflow_files_sha256")
    if not isinstance(workflow_hashes, Mapping) or not workflow_hashes:
        raise AnalysisError(
            "DAG sidecar workflow_files_sha256 must be a non-empty object"
        )
    if len(workflow_hashes) > MAX_WORKFLOW_FILES:
        raise AnalysisError(
            "DAG sidecar workflow_files_sha256 exceeds "
            f"maximum of {MAX_WORKFLOW_FILES} files"
        )
    normalized_workflow_hashes: dict[str, str] = {}
    for path, digest in workflow_hashes.items():
        path_text = _text(path, "DAG sidecar workflow file path")
        normalized_workflow_hashes[path_text] = _validate_sha(
            digest,
            f"DAG sidecar workflow_files_sha256[{path!r}]",
            sha256_only=True,
        )

    supplied_digest = _validate_sha(
        dag.get("dag_sha256"), "DAG sidecar dag_sha256", sha256_only=True
    )
    canonical = dict(dag)
    canonical.pop("dag_sha256", None)
    try:
        expected_digest = hashlib.sha256(
            _canonical_json(canonical).encode("utf-8")
        ).hexdigest()
    except (TypeError, ValueError, RecursionError) as error:
        raise AnalysisError("DAG sidecar contains non-canonical JSON values") from error
    if supplied_digest != expected_digest:
        raise AnalysisError("DAG sidecar dag_sha256 does not match its contents")

    nonterminal = [job.job_id for job in jobs if job.status != "completed"]
    if nonterminal:
        raise AnalysisError(
            "strict analysis requires terminal jobs; nonterminal job IDs: "
            + ", ".join(str(job_id) for job_id in nonterminal)
        )
    invalid_conclusions = [
        job.job_id for job in jobs if job.conclusion not in _TERMINAL_CONCLUSIONS
    ]
    if invalid_conclusions:
        raise AnalysisError(
            "strict analysis requires terminal conclusions; invalid job IDs: "
            + ", ".join(str(job_id) for job_id in invalid_conclusions)
        )
    incomplete_timing = [
        job.job_id
        for job in jobs
        if not (job.started_at is not None and job.completed_at is not None)
        and not (
            job.started_at is None
            and job.completed_at is None
            and not job.steps
            and job.conclusion in {"skipped", "cancelled"}
        )
    ]
    if incomplete_timing:
        raise AnalysisError(
            "strict analysis requires complete job timing; incomplete job IDs: "
            + ", ".join(str(job_id) for job_id in incomplete_timing)
        )
    incomplete_steps = [
        job.job_id
        for job in jobs
        if any(
            step.started_at is None or step.completed_at is None for step in job.steps
        )
    ]
    if incomplete_steps:
        raise AnalysisError(
            "strict analysis requires complete step timing; incomplete job IDs: "
            + ", ".join(str(job_id) for job_id in incomplete_steps)
        )
    outside_steps = [
        job.job_id
        for job in jobs
        if job.started_at is not None
        and job.completed_at is not None
        and any(
            step.started_at is not None
            and step.completed_at is not None
            and (
                step.started_at < job.started_at or step.completed_at > job.completed_at
            )
            for step in job.steps
        )
    ]
    if outside_steps:
        raise AnalysisError(
            "strict analysis requires step timing within job bounds; job IDs: "
            + ", ".join(str(job_id) for job_id in outside_steps)
        )

    nodes = dag.get("nodes")
    if not isinstance(nodes, list) or len(nodes) != len(jobs):
        raise AnalysisError("DAG sidecar nodes must contain exactly one node per job")
    jobs_by_id = {job.job_id: job for job in jobs}
    for job in jobs:
        if (
            job.api_run_id is None
            or job.api_run_attempt is None
            or job.api_head_sha is None
        ):
            raise AnalysisError(
                f"strict analysis requires API identity fields for job {job.job_id}"
            )
        if job.api_run_id is not None and job.api_run_id != run_id:
            raise AnalysisError(
                f"job {job.job_id} run_id does not match requested run_id"
            )
        if (
            job.api_run_attempt is not None
            and job.api_run_attempt != sidecar_run_attempt
        ):
            raise AnalysisError(
                f"job {job.job_id} run_attempt does not match DAG sidecar"
            )
        if job.api_head_sha is not None and job.api_head_sha != sidecar_source_sha:
            raise AnalysisError(
                f"job {job.job_id} head_sha does not match DAG sidecar source_head_sha"
            )
    dependency_ids: dict[int, tuple[int, ...]] = {}
    logical_ids: dict[int, str] = {}
    logical_id_values: set[str] = set()
    core_failures: dict[int, bool] = {}
    for index, node in enumerate(nodes):
        if not isinstance(node, Mapping):
            raise AnalysisError(f"DAG sidecar nodes[{index}] must be an object")
        job_id = _positive_integer(
            node.get("job_id"), f"DAG sidecar nodes[{index}].job_id"
        )
        if job_id in dependency_ids:
            raise AnalysisError(f"duplicate DAG sidecar job_id {job_id}")
        if job_id not in jobs_by_id:
            raise AnalysisError(f"DAG sidecar references unknown job id {job_id}")
        logical_id = _text(
            node.get("logical_id"), f"DAG sidecar nodes[{index}].logical_id"
        )
        if logical_id in logical_id_values:
            raise AnalysisError(f"duplicate DAG sidecar logical_id {logical_id!r}")
        for field in ("phase", "core_role", "skip_classification"):
            _text(node.get(field), f"DAG sidecar nodes[{index}].{field}")
        core_failure = node.get("core_failure")
        if not isinstance(core_failure, bool):
            raise AnalysisError(
                f"DAG sidecar nodes[{index}].core_failure must be boolean"
            )
        raw_needs = node.get("needs")
        if not isinstance(raw_needs, list):
            raise AnalysisError(f"DAG sidecar nodes[{index}].needs must be an array")
        if len(raw_needs) > MAX_NEEDS_PER_JOB:
            raise AnalysisError(
                f"DAG sidecar nodes[{index}].needs exceeds "
                f"maximum of {MAX_NEEDS_PER_JOB}"
            )
        needs = tuple(
            _positive_integer(value, f"DAG sidecar nodes[{index}].needs[{need_index}]")
            for need_index, value in enumerate(raw_needs)
        )
        if len(set(needs)) != len(needs):
            raise AnalysisError(f"DAG sidecar nodes[{index}].needs contains duplicates")
        dependency_ids[job_id] = needs
        logical_ids[job_id] = logical_id
        logical_id_values.add(logical_id)
        core_failures[job_id] = core_failure
    if set(dependency_ids) != set(jobs_by_id):
        raise AnalysisError("DAG sidecar job IDs do not match the jobs payload")
    for job_id, needs in dependency_ids.items():
        for dependency_id in needs:
            if dependency_id not in jobs_by_id:
                raise AnalysisError(
                    f"DAG sidecar job {job_id} references unknown dependency id {dependency_id}"
                )
    artifact_id, artifact_name, artifact_digest, producer_attempt = (
        _validate_trusted_provenance(
            trusted_provenance,
            repository=repository,
            run_id=run_id,
            run_attempt=sidecar_run_attempt,
            source_head_sha=sidecar_source_sha,
            tested_commit_sha=sidecar_tested_sha,
            workflow_path=workflow_path,
            workflow_ref=workflow_ref,
            workflow_sha=workflow_sha,
            workflow_files_sha256=normalized_workflow_hashes,
            dag_sha256=supplied_digest,
        )
    )
    return DAGEvidence(
        dependency_ids=dependency_ids,
        logical_ids=logical_ids,
        core_failures=core_failures,
        run_attempt=sidecar_run_attempt,
        source_head_sha=sidecar_source_sha,
        tested_commit_sha=sidecar_tested_sha,
        workflow_path=workflow_path,
        workflow_ref=workflow_ref,
        workflow_sha=workflow_sha,
        workflow_files_sha256=normalized_workflow_hashes,
        dag_sha256=supplied_digest,
        artifact_id=artifact_id,
        artifact_name=artifact_name,
        artifact_digest=artifact_digest,
        producer_attempt=producer_attempt,
    )


def _interval_union_seconds(intervals: Iterable[tuple[datetime, datetime]]) -> float:
    ordered = sorted((start, end) for start, end in intervals if end >= start)
    if not ordered:
        return 0.0
    total = 0.0
    current_start, current_end = ordered[0]
    for start, end in ordered[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
            continue
        total += (current_end - current_start).total_seconds()
        current_start, current_end = start, end
    return total + (current_end - current_start).total_seconds()


def _step_bucket(name: str) -> str | None:
    lowered = name.casefold()
    if any(
        token in lowered
        for token in ("upload artifact", "download artifact", "artifact", "cache")
    ):
        return "artifact"
    if any(
        token in lowered
        for token in (
            "checkout",
            "setup ",
            "install",
            "npm ci",
            "uv sync",
            "uv pip",
            "pip install",
            "cargo fetch",
            "go mod download",
            "restore dependencies",
            "login to",
        )
    ):
        return "setup"
    return None


def _duration_buckets(
    job: JobTiming,
) -> tuple[float | None, float | None, float | None]:
    if job.duration_seconds is None:
        return None, None, None
    if not any(
        step.started_at is not None and step.completed_at is not None
        for step in job.steps
    ):
        return None, None, None
    setup = [
        (step.started_at, step.completed_at)
        for step in job.steps
        if (
            _step_bucket(step.name) == "setup"
            and step.started_at is not None
            and step.completed_at is not None
        )
    ]
    artifact = [
        (step.started_at, step.completed_at)
        for step in job.steps
        if (
            _step_bucket(step.name) == "artifact"
            and step.started_at is not None
            and step.completed_at is not None
        )
    ]
    setup_seconds = _interval_union_seconds(setup)
    artifact_seconds = _interval_union_seconds(artifact)
    actual = max(0.0, job.duration_seconds - setup_seconds - artifact_seconds)
    return setup_seconds, actual, artifact_seconds


def _longest_dependency_path(
    jobs: Sequence[JobTiming],
    dependency_ids: Mapping[int, tuple[int, ...]] | None = None,
) -> tuple[dict[int, float], dict[int, bool]]:
    by_name = {job.name: job for job in jobs}
    by_id = {job.job_id: job for job in jobs}
    end_times: dict[int, float] = {}
    upstream_failure: dict[int, bool] = {}
    dependency_chain_failure: dict[int, bool] = {}
    visiting: set[int] = set()

    def visit(job: JobTiming) -> float:
        if job.job_id in end_times:
            return end_times[job.job_id]
        if job.job_id in visiting:
            raise AnalysisError(f"dependency cycle includes job {job.name!r}")
        visiting.add(job.job_id)
        predecessor_ends: list[float] = []
        dependency_failed = False
        if dependency_ids is None:
            predecessors = [
                by_name.get(dependency_name) for dependency_name in job.needs
            ]
            missing_names = [
                dependency_name
                for dependency_name, predecessor in zip(
                    job.needs, predecessors, strict=True
                )
                if predecessor is None
            ]
            if missing_names:
                raise AnalysisError(
                    f"job {job.name!r} references missing dependency {missing_names[0]!r}"
                )
        else:
            predecessors = [
                by_id.get(dependency_id) for dependency_id in dependency_ids[job.job_id]
            ]
            missing_ids = [
                dependency_id
                for dependency_id, predecessor in zip(
                    dependency_ids[job.job_id], predecessors, strict=True
                )
                if predecessor is None
            ]
            if missing_ids:
                raise AnalysisError(
                    f"job {job.name!r} references missing dependency id {missing_ids[0]}"
                )
        for predecessor in predecessors:
            if predecessor is None:
                raise AnalysisError(f"job {job.name!r} has an unknown dependency")
            predecessor_ends.append(visit(predecessor))
            dependency_failed = dependency_failed or (
                predecessor.conclusion not in {"success", "skipped"}
                or dependency_chain_failure.get(predecessor.job_id, False)
            )
        start = max(predecessor_ends, default=0.0)
        end = start + (job.duration_seconds or 0.0)
        visiting.remove(job.job_id)
        end_times[job.job_id] = end
        # A dependency failure is only a *blocked* job when the job never ran.
        # Jobs using ``always()`` may legitimately execute after a failed need;
        # retaining that distinction prevents false queue/starvation diagnoses.
        dependency_chain_failure[job.job_id] = dependency_failed
        upstream_failure[job.job_id] = dependency_failed and job.conclusion in {
            "skipped",
            "cancelled",
        }
        return end

    for job in jobs:
        visit(job)
    return end_times, upstream_failure


def _utilization(jobs: Sequence[JobTiming], cap: int) -> tuple[float, float, float]:
    intervals = [
        (job.started_at, job.completed_at)
        for job in jobs
        if job.started_at is not None and job.completed_at is not None
    ]
    valid = [
        (start, end)
        for start, end in intervals
        if start is not None and end is not None
    ]
    if not valid:
        return 0.0, 0.0, 0.0
    first = min(start for start, _ in valid)
    last = max(end for _, end in valid)
    wall = max(0.0, (last - first).total_seconds())
    events: list[tuple[datetime, int]] = []
    for start, end in valid:
        events.append((start, 1))
        events.append((end, -1))
    events.sort(key=lambda item: (item[0], item[1]))
    active = 0
    area = 0.0
    peak = 0
    previous = first
    for timestamp, delta in events:
        area += active * max(0.0, (timestamp - previous).total_seconds())
        active += delta
        peak = max(peak, active)
        previous = timestamp
    return peak, (area / wall / cap if wall and cap else 0.0), wall


def _nearest_rank(values: Sequence[float], percentile: float) -> float | None:
    """Return a deterministic percentile without interpolation surprises.

    A nearest-rank percentile is stable for small job cohorts and keeps the
    ledger explainable: p95 is always one observed duration rather than a
    synthetic value between two jobs.  The caller supplies a validated
    percentile in the closed interval (0, 1].
    """
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, min(len(ordered), math.ceil(len(ordered) * percentile)))
    return ordered[rank - 1]


def _timing_distribution(values: Sequence[float]) -> dict[str, object]:
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "total_seconds": round(sum(ordered), 3),
        "p50_seconds": (
            None if (p50 := _nearest_rank(ordered, 0.50)) is None else round(p50, 3)
        ),
        "p95_seconds": (
            None if (p95 := _nearest_rank(ordered, 0.95)) is None else round(p95, 3)
        ),
        "max_seconds": None if not ordered else round(ordered[-1], 3),
    }


def _timing_ledger(jobs: Sequence[JobTiming]) -> dict[str, dict[str, object]]:
    """Aggregate measured queue/setup/test/artifact durations.

    Incomplete jobs are omitted from aggregate distributions.  Treating a
    queued or cancelled job with no runner timestamps as a zero-second sample
    would under-report queue and setup pressure, so only observed intervals
    contribute to p50/p95 and totals.
    """
    values: dict[str, list[float]] = {
        "queue": [],
        "setup": [],
        "test": [],
        "artifact": [],
    }
    for job in jobs:
        if job.started_at is None or job.completed_at is None:
            continue
        if (
            job.queued_at is not None
            and (queue_wait := job.queue_wait_seconds) is not None
        ):
            values["queue"].append(queue_wait)
        setup, actual, artifact = _duration_buckets(job)
        if setup is not None and actual is not None and artifact is not None:
            values["setup"].append(setup)
            values["test"].append(actual)
            values["artifact"].append(artifact)
    return {name: _timing_distribution(samples) for name, samples in values.items()}


def _retry_classification(job: JobTiming) -> str:
    """Classify only the workflow-attempt signal exposed by GitHub's API.

    The Jobs API does not expose an independent per-job retry counter.  A
    ``run_attempt`` greater than one proves a workflow rerun, but cannot prove
    which individual job was retried; the wording intentionally preserves
    that distinction.
    """
    if job.api_run_attempt is None:
        return "unknown"
    if job.api_run_attempt == 1:
        return "initial_workflow_attempt"
    return "workflow_rerun"


def _retry_summary(jobs: Sequence[JobTiming]) -> dict[str, object]:
    attempts = sorted(
        {job.api_run_attempt for job in jobs if job.api_run_attempt is not None}
    )
    complete = len(attempts) == 1 and len(
        [job for job in jobs if job.api_run_attempt is not None]
    ) == len(jobs)
    if not complete:
        state = "unknown"
    elif attempts[0] == 1:
        state = "initial_workflow_attempt"
    else:
        state = "workflow_rerun"
    return {"state": state, "run_attempts": attempts}


def _timeout_classification(job: JobTiming) -> str:
    """Classify timeout evidence without inferring it from duration alone."""
    if job.conclusion == "timed_out" or any(
        step.conclusion == "timed_out" for step in job.steps
    ):
        return "timed_out"
    if job.conclusion == "cancelled":
        return "cancelled"
    if job.status != "completed" or job.conclusion is None:
        return "unknown"
    if job.conclusion in _NON_TIMEOUT_CONCLUSIONS:
        return "not_timed_out"
    return "unknown"


def _timeout_summary(jobs: Sequence[JobTiming]) -> dict[str, object]:
    classifications = {job.job_id: _timeout_classification(job) for job in jobs}
    counts = {
        state: sum(value == state for value in classifications.values())
        for state in ("cancelled", "not_timed_out", "timed_out", "unknown")
    }
    return {
        "counts": counts,
        "timed_out_job_ids": sorted(
            job_id for job_id, state in classifications.items() if state == "timed_out"
        ),
        "cancelled_job_ids": sorted(
            job_id for job_id, state in classifications.items() if state == "cancelled"
        ),
    }


def _rounded_seconds(value: float | None) -> float | None:
    return None if value is None else round(value, 3)


def _step_rows(job: JobTiming) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for step in job.steps:
        row: dict[str, object] = {
            "name": step.name,
            "seconds": _rounded_seconds(step.seconds),
        }
        if step.conclusion is not None:
            row["conclusion"] = step.conclusion
        rows.append(row)
    return rows


def _validate_job_run_ids(jobs: Sequence[JobTiming], run_id: int) -> None:
    mismatched = sorted(
        job.job_id
        for job in jobs
        if job.api_run_id is not None and job.api_run_id != run_id
    )
    if mismatched:
        raise AnalysisError(
            f"job {mismatched[0]} run_id does not match requested run_id"
            + (" (and additional jobs)" if len(mismatched) > 1 else "")
        )


def _validate_diagnostic_identity(jobs: Sequence[JobTiming]) -> None:
    attempts = {job.api_run_attempt for job in jobs if job.api_run_attempt is not None}
    if len(attempts) > 1:
        raise AnalysisError(
            "diagnostic analysis cannot mix run_attempt values: "
            + ", ".join(str(value) for value in sorted(attempts))
        )
    source_heads = {job.api_head_sha for job in jobs if job.api_head_sha is not None}
    if len(source_heads) > 1:
        raise AnalysisError("diagnostic analysis cannot mix source head SHAs")


def _diagnostic_provenance(
    jobs: Sequence[JobTiming], *, repository: str, run_id: int
) -> dict[str, object]:
    attempts = sorted(
        {job.api_run_attempt for job in jobs if job.api_run_attempt is not None}
    )
    source_heads = sorted(
        {job.api_head_sha for job in jobs if job.api_head_sha is not None}
    )
    return {
        "evidence_scope": "diagnostic-only",
        "repository": repository,
        "run_id": run_id,
        "run_attempt": attempts[0] if len(attempts) == 1 else None,
        "run_attempts": attempts,
        "source_head_sha": source_heads[0] if len(source_heads) == 1 else None,
        "source_head_shas": source_heads,
        "tested_commit_sha": None,
        "workflow_path": None,
        "workflow_ref": None,
        "workflow_sha": None,
        "workflow_files_sha256": None,
        "dag_sha256": None,
        "identity_complete": bool(
            jobs
            and all(
                job.api_run_id is not None
                and job.api_run_attempt is not None
                and job.api_head_sha is not None
                for job in jobs
            )
        ),
    }


def _strict_provenance(
    dag: DAGEvidence, *, repository: str, run_id: int
) -> dict[str, object]:
    return {
        "evidence_scope": "strict",
        "repository": repository,
        "run_id": run_id,
        "run_attempt": dag.run_attempt,
        "source_head_sha": dag.source_head_sha,
        "tested_commit_sha": dag.tested_commit_sha,
        "workflow_path": dag.workflow_path,
        "workflow_ref": dag.workflow_ref,
        "workflow_sha": dag.workflow_sha,
        "workflow_files_sha256": dag.workflow_files_sha256,
        "dag_sha256": dag.dag_sha256,
        "authentication": "same-run-artifact-selector",
        "artifact_id": dag.artifact_id,
        "artifact_name": dag.artifact_name,
        "artifact_digest": dag.artifact_digest,
        "producer_attempt": dag.producer_attempt,
    }


def _diagnostic_lower_bound_report(
    jobs: Sequence[JobTiming], *, repository: str, run_id: int, concurrency_cap: int
) -> dict[str, object]:
    """Report observable timing without inventing dependencies or core roles."""
    peak, average_utilization, wall_seconds = _utilization(jobs, concurrency_cap)
    setup_signatures: Counter[str] = Counter()
    job_rows: list[dict[str, object]] = []
    for job in jobs:
        setup, actual, artifact = _duration_buckets(job)
        for step in job.steps:
            if _step_bucket(step.name) in {"setup", "artifact"}:
                setup_signatures[step.name.casefold()] += 1
        queue_wait: float | None = None
        if job.status != "queued":
            queue_wait = _rounded_seconds(job.queue_wait_seconds)
        job_rows.append(
            {
                "id": job.job_id,
                "name": job.name,
                "status": job.status,
                "conclusion": job.conclusion,
                "needs": "unknown",
                "duration_seconds": _rounded_seconds(job.duration_seconds),
                "dependency_wait_seconds": None,
                "github_queue_wait_seconds": queue_wait,
                "setup_install_seconds": _rounded_seconds(setup),
                "actual_test_seconds": _rounded_seconds(actual),
                "artifact_seconds": _rounded_seconds(artifact),
                "retry_classification": _retry_classification(job),
                "timeout_classification": _timeout_classification(job),
                "critical_path_end_seconds": None,
                "upstream_failure_blocked": "unknown",
                "continued_after_core_failure": "unknown",
                "steps": _step_rows(job),
            }
        )
    duplicate_setup = [
        {"step": name, "count": count}
        for name, count in sorted(setup_signatures.items())
        if count > 1
    ]
    return {
        "schema_version": 1,
        "repository": repository,
        "run_id": run_id,
        "provenance": _diagnostic_provenance(
            jobs, repository=repository, run_id=run_id
        ),
        "concurrency_cap": concurrency_cap,
        "analysis_mode": "diagnostic-lower-bound",
        "summary": {
            "job_count": len(jobs),
            "analysis_mode": "diagnostic-lower-bound",
            "critical_path_kind": "lower-bound",
            "critical_path_lower_bound_seconds": round(wall_seconds, 3),
            "wall_clock_seconds": round(wall_seconds, 3),
            "peak_slot_utilization": peak,
            "peak_concurrency": peak,
            "average_slot_utilization": round(average_utilization, 6),
            "timing_seconds": _timing_ledger(jobs),
            "retry_classification": _retry_summary(jobs),
            "timeout_classification": _timeout_summary(jobs),
            "duplicate_setup_download_work": duplicate_setup,
            "upstream_failure_blocked_jobs": "unknown",
            "jobs_continued_after_core_failure": "unknown",
        },
        "jobs": job_rows,
    }


def analyze_jobs(
    jobs: Sequence[JobTiming],
    *,
    repository: str,
    run_id: int,
    concurrency_cap: int,
    dag: object | None = None,
    diagnostic_lower_bound: bool = False,
    trusted_provenance: object | None = None,
) -> dict[str, object]:
    if not REPOSITORY_RE.fullmatch(repository):
        raise AnalysisError("repository must be an owner/name pair")
    _positive_integer(run_id, "run_id")
    _positive_integer(concurrency_cap, "concurrency_cap")
    if not jobs:
        raise AnalysisError("run contains no jobs")
    _validate_job_run_ids(jobs, run_id)
    if diagnostic_lower_bound and dag is not None:
        raise AnalysisError("DAG sidecar cannot be combined with diagnostic mode")
    if diagnostic_lower_bound and trusted_provenance is not None:
        raise AnalysisError(
            "trusted provenance cannot be combined with diagnostic mode"
        )
    if dag is None:
        if not diagnostic_lower_bound:
            raise AnalysisError(
                "strict analysis requires a DAG sidecar; use diagnostic-lower-bound mode for API-only jobs"
            )
        _validate_diagnostic_identity(jobs)
        return _diagnostic_lower_bound_report(
            jobs,
            repository=repository,
            run_id=run_id,
            concurrency_cap=concurrency_cap,
        )
    dag_evidence = _validate_dag_sidecar(
        dag,
        jobs,
        repository=repository,
        run_id=run_id,
        trusted_provenance=trusted_provenance,
    )
    end_times, upstream_failure = _longest_dependency_path(
        jobs, dag_evidence.dependency_ids
    )
    peak, average_utilization, wall_seconds = _utilization(jobs, concurrency_cap)
    core_failures = [
        job.completed_at
        for job in jobs
        if dag_evidence.core_failures[job.job_id] and job.completed_at is not None
    ]
    earliest_core_failure = min(core_failures) if core_failures else None
    setup_signatures: Counter[str] = Counter()
    job_rows: list[dict[str, object]] = []
    for job in jobs:
        setup, actual, artifact = _duration_buckets(job)
        for step in job.steps:
            if _step_bucket(step.name) in {"setup", "artifact"}:
                setup_signatures[step.name.casefold()] += 1
        continued = bool(
            earliest_core_failure
            and job.started_at
            and job.started_at > earliest_core_failure
            and not dag_evidence.core_failures[job.job_id]
        )
        job_rows.append(
            {
                "id": job.job_id,
                "name": job.name,
                "status": job.status,
                "conclusion": job.conclusion,
                "needs": [
                    dag_evidence.logical_ids[dependency_id]
                    for dependency_id in dag_evidence.dependency_ids[job.job_id]
                ],
                "duration_seconds": _rounded_seconds(job.duration_seconds),
                "dependency_wait_seconds": round(
                    max(0.0, end_times[job.job_id] - (job.duration_seconds or 0.0)),
                    3,
                ),
                "github_queue_wait_seconds": _rounded_seconds(job.queue_wait_seconds),
                "setup_install_seconds": _rounded_seconds(setup),
                "actual_test_seconds": _rounded_seconds(actual),
                "artifact_seconds": _rounded_seconds(artifact),
                "retry_classification": _retry_classification(job),
                "timeout_classification": _timeout_classification(job),
                "critical_path_end_seconds": round(end_times[job.job_id], 3),
                "upstream_failure_blocked": upstream_failure[job.job_id],
                "continued_after_core_failure": continued,
                "steps": _step_rows(job),
            }
        )
    duplicate_setup = [
        {"step": name, "count": count}
        for name, count in sorted(setup_signatures.items())
        if count > 1
    ]
    critical_path = max(end_times.values(), default=0.0)
    return {
        "schema_version": 1,
        "repository": repository,
        "run_id": run_id,
        "provenance": _strict_provenance(
            dag_evidence, repository=repository, run_id=run_id
        ),
        "concurrency_cap": concurrency_cap,
        "analysis_mode": "strict",
        "summary": {
            "job_count": len(jobs),
            "analysis_mode": "strict",
            "critical_path_kind": "exact",
            "critical_path_seconds": round(critical_path, 3),
            "wall_clock_seconds": round(wall_seconds, 3),
            "peak_slot_utilization": peak,
            "peak_concurrency": peak,
            "average_slot_utilization": round(average_utilization, 6),
            "timing_seconds": _timing_ledger(jobs),
            "retry_classification": _retry_summary(jobs),
            "timeout_classification": _timeout_summary(jobs),
            "duplicate_setup_download_work": duplicate_setup,
            "upstream_failure_blocked_jobs": [
                row["id"] for row in job_rows if row["upstream_failure_blocked"]
            ],
            "jobs_continued_after_core_failure": [
                row["id"] for row in job_rows if row["continued_after_core_failure"]
            ],
        },
        "jobs": job_rows,
    }


def _load_json(path: Path) -> object:
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_JSON_BYTES + 1)
        if len(raw) > MAX_JSON_BYTES:
            raise AnalysisError(
                f"JSON file {path} exceeds maximum size of {MAX_JSON_BYTES} bytes"
            )
        text = raw.decode("utf-8")
        return _parse_json_text(text, source=f"JSON file {path}")
    except AnalysisError:
        raise
    except (OSError, UnicodeError) as error:
        raise AnalysisError(f"unable to read JSON {path}: {error}") from error


def _safe_error_excerpt(value: object) -> str:
    raw = "" if value is None else str(value)
    sanitized = "".join(
        character if character in "\t " or ord(character) >= 0x20 else "?"
        for character in raw
    ).strip()
    return sanitized[:MAX_ERROR_CHARS]


def _fetch_jobs(repository: str, run_id: int) -> object:
    if not REPOSITORY_RE.fullmatch(repository):
        raise AnalysisError("repository must be an owner/name pair")
    _positive_integer(run_id, "run_id")
    endpoint = f"repos/{repository}/actions/runs/{run_id}/jobs?per_page=100"
    # ``repository`` is validated by the caller and the endpoint is passed as
    # one argv element, so no shell interpretation is possible.
    try:
        with (
            tempfile.TemporaryFile(mode="w+b") as stdout_file,
            tempfile.TemporaryFile(mode="w+b") as stderr_file,
        ):
            try:
                completed = subprocess.run(  # noqa: S603
                    ["gh", "api", "--paginate", "--slurp", endpoint],  # noqa: S607
                    stdin=subprocess.DEVNULL,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    check=False,
                    timeout=MAX_FETCH_SECONDS,
                )
            except subprocess.TimeoutExpired as error:
                raise AnalysisError("gh api jobs request timed out") from error
            stdout_file.seek(0)
            stdout = stdout_file.read(MAX_JSON_BYTES + 1)
            stderr_file.seek(0)
            stderr = stderr_file.read(MAX_ERROR_CHARS + 1)
    except AnalysisError:
        raise
    except OSError as error:
        raise AnalysisError("unable to execute gh api") from error
    if completed.returncode:
        message = (
            _safe_error_excerpt(stderr.decode("utf-8", errors="replace"))
            or "gh api failed"
        )
        raise AnalysisError(message)
    if len(stdout) > MAX_JSON_BYTES:
        raise AnalysisError(
            f"gh api jobs payload exceeds maximum size of {MAX_JSON_BYTES} bytes"
        )
    try:
        stdout_text = stdout.decode("utf-8")
    except UnicodeDecodeError as error:
        raise AnalysisError("gh api returned invalid UTF-8") from error
    if not stdout_text.strip():
        raise AnalysisError("gh api returned no jobs payload")
    # ``--slurp`` emits one JSON array containing all page envelopes.  Do
    # not wrap that array in another list: the decoder below deliberately
    # distinguishes a page envelope from a list of page envelopes.
    return _parse_json_text(stdout_text, source="gh api jobs payload")


def _write_atomic_text(path: Path, text: str) -> None:
    """Write evidence via a flushed temporary file and atomic replacement."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except (OSError, UnicodeError):
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        raise


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--concurrency-cap", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--jobs-json",
        type=Path,
        help="read an offline fixture instead of invoking gh api",
    )
    parser.add_argument(
        "--dag-json",
        type=Path,
        help="read the required attempt-bound normalized DAG sidecar",
    )
    parser.add_argument(
        "--trusted-provenance-json",
        type=Path,
        help="read the detached provenance record from the same-run artifact selector",
    )
    parser.add_argument(
        "--diagnostic-lower-bound",
        action="store_true",
        help="report API-only timing as a lower bound without dependency claims",
    )
    args = parser.parse_args(argv)
    try:
        if not REPOSITORY_RE.fullmatch(args.repository):
            raise AnalysisError("repository must be an owner/name pair")
        _positive_integer(args.run_id, "run_id")
        _positive_integer(args.concurrency_cap, "concurrency_cap")
        payload = (
            _load_json(args.jobs_json)
            if args.jobs_json
            else _fetch_jobs(args.repository, args.run_id)
        )
        dag = _load_json(args.dag_json) if args.dag_json else None
        trusted_provenance = (
            _load_json(args.trusted_provenance_json)
            if args.trusted_provenance_json
            else None
        )
        report = analyze_jobs(
            parse_jobs(payload),
            repository=args.repository,
            run_id=args.run_id,
            concurrency_cap=args.concurrency_cap,
            dag=dag,
            diagnostic_lower_bound=args.diagnostic_lower_bound,
            trusted_provenance=trusted_provenance,
        )
        report["report_sha256"] = hashlib.sha256(
            _canonical_json(report).encode("utf-8")
        ).hexdigest()
        _write_atomic_text(
            args.output,
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
    except (AnalysisError, OSError, UnicodeError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
