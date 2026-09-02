#!/usr/bin/env python3
"""Build a deterministic, read-only timing ledger for one GitHub Actions run.

The analyzer deliberately treats the GitHub API payload as evidence rather than
as an instruction.  It never mutates a run, retries a job, or accepts a report
from another run.  A fixture can be supplied with ``--jobs-json`` for local
reproducibility; otherwise ``gh api --paginate`` is used to read the jobs for
the requested run.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
ISO_RE = re.compile(r"Z$", re.ASCII)


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
    if any(character in value for character in "\x00\r\n"):
        raise AnalysisError(f"{field} contains a forbidden control character")
    return value


@dataclass(frozen=True)
class StepTiming:
    name: str
    started_at: datetime
    completed_at: datetime

    @property
    def seconds(self) -> float:
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

    @property
    def duration_seconds(self) -> float:
        if self.started_at is None or self.completed_at is None:
            return 0.0
        return max(0.0, (self.completed_at - self.started_at).total_seconds())

    @property
    def queue_wait_seconds(self) -> float:
        if self.queued_at is None or self.started_at is None:
            return 0.0
        return max(0.0, (self.started_at - self.queued_at).total_seconds())


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
    for index, page in enumerate(page_candidates):
        if isinstance(page, Mapping) and "jobs" in page:
            jobs = page["jobs"]
            if not isinstance(jobs, list):
                raise AnalysisError(f"jobs page {index} must contain an array")
            flattened.extend(jobs)
        elif isinstance(page, list):
            flattened.extend(page)
        elif isinstance(page, Mapping):
            # A plain list of job records is also a supported fixture shape;
            # preserve it without accepting arbitrary page envelopes.
            flattened.append(page)
        else:
            raise AnalysisError(f"jobs page {index} must be an object or array")

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
    result: list[StepTiming] = []
    for index, value in enumerate(raw):
        if not isinstance(value, Mapping):
            raise AnalysisError(f"job {job_name!r} step {index} must be an object")
        name = _text(value.get("name"), f"job {job_name!r} step {index}.name")
        started = _parse_timestamp(
            value.get("started_at"), f"job {job_name!r} step {index}.started_at"
        )
        completed = _parse_timestamp(
            value.get("completed_at"), f"job {job_name!r} step {index}.completed_at"
        )
        if started is None or completed is None:
            continue
        if completed < started:
            raise AnalysisError(f"job {job_name!r} step {index} ends before it starts")
        result.append(StepTiming(name, started, completed))
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
        if started is not None and completed is not None and completed < started:
            # GitHub occasionally emits a one-second inverted pair for a
            # skipped or cancelled job that never received a runner (there
            # are no steps and therefore no elapsed work to measure). Treat
            # that API sentinel as a zero-duration guarded terminal job, but
            # keep malformed timestamps a hard error for every job that
            # could have executed.
            if conclusion in {"skipped", "cancelled"} and not record.get("steps"):
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
                steps=_parse_steps(record.get("steps"), name),
                core_failure=bool(record.get("core_failure", False)),
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


def _duration_buckets(job: JobTiming) -> tuple[float, float, float]:
    setup = [
        (step.started_at, step.completed_at)
        for step in job.steps
        if _step_bucket(step.name) == "setup"
    ]
    artifact = [
        (step.started_at, step.completed_at)
        for step in job.steps
        if _step_bucket(step.name) == "artifact"
    ]
    setup_seconds = _interval_union_seconds(setup)
    artifact_seconds = _interval_union_seconds(artifact)
    actual = max(0.0, job.duration_seconds - setup_seconds - artifact_seconds)
    return setup_seconds, actual, artifact_seconds


def _longest_dependency_path(
    jobs: Sequence[JobTiming],
) -> tuple[dict[int, float], dict[int, bool]]:
    by_name = {job.name: job for job in jobs}
    end_times: dict[int, float] = {}
    upstream_failure: dict[int, bool] = {}
    dependency_chain_failure: dict[int, bool] = {}
    visiting: set[str] = set()

    def visit(job: JobTiming) -> float:
        if job.job_id in end_times:
            return end_times[job.job_id]
        if job.name in visiting:
            raise AnalysisError(f"dependency cycle includes job {job.name!r}")
        visiting.add(job.name)
        predecessor_ends: list[float] = []
        dependency_failed = False
        for dependency_name in job.needs:
            predecessor = by_name.get(dependency_name)
            if predecessor is None:
                raise AnalysisError(
                    f"job {job.name!r} references missing dependency {dependency_name!r}"
                )
            predecessor_ends.append(visit(predecessor))
            dependency_failed = dependency_failed or (
                predecessor.conclusion not in {"success", "skipped"}
                or dependency_chain_failure.get(predecessor.job_id, False)
            )
        start = max(predecessor_ends, default=0.0)
        end = start + job.duration_seconds
        visiting.remove(job.name)
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


def analyze_jobs(
    jobs: Sequence[JobTiming], *, repository: str, run_id: int, concurrency_cap: int
) -> dict[str, object]:
    if not REPOSITORY_RE.fullmatch(repository):
        raise AnalysisError("repository must be an owner/name pair")
    _positive_integer(run_id, "run_id")
    _positive_integer(concurrency_cap, "concurrency_cap")
    if not jobs:
        raise AnalysisError("run contains no jobs")
    end_times, upstream_failure = _longest_dependency_path(jobs)
    peak, average_utilization, wall_seconds = _utilization(jobs, concurrency_cap)
    core_failures = [
        job.completed_at
        for job in jobs
        if job.core_failure and job.completed_at is not None
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
            and not job.core_failure
        )
        job_rows.append(
            {
                "id": job.job_id,
                "name": job.name,
                "status": job.status,
                "conclusion": job.conclusion,
                "needs": list(job.needs),
                "duration_seconds": round(job.duration_seconds, 3),
                "dependency_wait_seconds": round(
                    max(0.0, end_times[job.job_id] - job.duration_seconds), 3
                ),
                "github_queue_wait_seconds": round(job.queue_wait_seconds, 3),
                "setup_install_seconds": round(setup, 3),
                "actual_test_seconds": round(actual, 3),
                "artifact_seconds": round(artifact, 3),
                "critical_path_end_seconds": round(end_times[job.job_id], 3),
                "upstream_failure_blocked": upstream_failure[job.job_id],
                "continued_after_core_failure": continued,
                "steps": [
                    {
                        "name": step.name,
                        "seconds": round(step.seconds, 3),
                    }
                    for step in job.steps
                ],
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
        "concurrency_cap": concurrency_cap,
        "summary": {
            "job_count": len(jobs),
            "critical_path_seconds": round(critical_path, 3),
            "wall_clock_seconds": round(wall_seconds, 3),
            "peak_slot_utilization": peak,
            "average_slot_utilization": round(average_utilization, 6),
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
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AnalysisError(f"unable to read JSON {path}: {error}") from error


def _fetch_jobs(repository: str, run_id: int) -> object:
    endpoint = f"repos/{repository}/actions/runs/{run_id}/jobs?per_page=100"
    # ``repository`` is validated by the caller and the endpoint is passed as
    # one argv element, so no shell interpretation is possible.
    completed = subprocess.run(  # noqa: S603
        ["gh", "api", "--paginate", "--slurp", endpoint],  # noqa: S607
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode:
        message = completed.stderr.strip() or "gh api failed"
        raise AnalysisError(message)
    if not completed.stdout.strip():
        raise AnalysisError("gh api returned no jobs payload")
    try:
        # ``--slurp`` emits one JSON array containing all page envelopes.  Do
        # not wrap that array in another list: the decoder below deliberately
        # distinguishes a page envelope from a list of page envelopes.
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise AnalysisError("gh api returned invalid JSON") from error


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
    args = parser.parse_args(argv)
    try:
        payload = (
            _load_json(args.jobs_json)
            if args.jobs_json
            else _fetch_jobs(args.repository, args.run_id)
        )
        report = analyze_jobs(
            parse_jobs(payload),
            repository=args.repository,
            run_id=args.run_id,
            concurrency_cap=args.concurrency_cap,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (AnalysisError, OSError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
