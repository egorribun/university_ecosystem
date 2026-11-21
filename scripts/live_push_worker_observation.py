"""Project a bounded owned-worker log tail into closed Push outcome counts.

The tail is run-level, may be rotated or truncated, and has no test-attempt
correlation. Counts are saturated marginals, not unique sends or delivery proof.
Each count saturates at nine; nine means at least nine. ``http_none`` means no
numeric status was recorded, not that no provider request occurred.
The separate success summary distinguishes HTTP 201 from other 2xx responses
only for rows classified as sent; it is not proof of browser delivery.
The separate 410 prefixes are candidate correlation hints from the bounded tail;
they do not establish browser identity, timing, or notification attribution.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import NoReturn

from scripts import live_stand

MAX_BYTES = 262_144
MAX_LINE_BYTES = 8_192
MAX_LINES = 256
READ_TIMEOUT_SECONDS = 5.0
CAPTURE_TIMEOUT_SECONDS = 25.0
_COUNT_LIMIT = 9
_STATUSES = ("sent", "gone", "error")
_STAGES = (
    "endpoint_url_validation",
    "endpoint_host_validation",
    "dns_resolution",
    "resolved_address_validation",
    "pinned_session_creation",
    "webpush_request",
    "none",
)
_HTTP_CLASSES = ("1xx", "2xx", "3xx", "4xx", "5xx", "none")
_CONTAINER_ID = re.compile(r"[0-9a-f]{64}\Z")
_SOURCE_SHA = re.compile(r"[0-9a-f]{40}\Z")
_MASKED_ENDPOINT = re.compile(r"(?:https?://[A-Za-z0-9.\-\[\]:]+/…|…)#([0-9a-f]{10})\Z")
_FINGERPRINT = re.compile(r"[0-9a-f]{10}\Z")
_410_PREFIX_LIMIT = 16


@dataclass(frozen=True, slots=True)
class WorkerSummary:
    statuses: tuple[int, ...]
    stages: tuple[int, ...]
    http_classes: tuple[int, ...]
    success_http: tuple[int, int] = (0, 0)
    gone_410_prefixes: tuple[str, ...] = ()
    gone_410_seen: bool = False
    gone_410_incomplete: bool = False
    gone_410_truncated: bool = False


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _reject_constant(_value: str) -> NoReturn:
    raise ValueError


def _finite_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError
    return result


def project_worker_logs(stdout: bytes, stderr: bytes) -> WorkerSummary | None:
    """Discard all fields except fixed enums; malformed bounded samples fail closed."""
    if (
        type(stdout) is not bytes
        or type(stderr) is not bytes
        or len(stdout) + len(stderr) > MAX_BYTES
        or any(stream and not stream.endswith(b"\n") for stream in (stdout, stderr))
    ):
        return None
    lines = [
        line.removesuffix(b"\r")
        for stream in (stdout, stderr)
        for line in stream.split(b"\n")[:-1]
    ]
    if len(lines) > MAX_LINES:
        return None
    status_counts = [0] * len(_STATUSES)
    stage_counts = [0] * len(_STAGES)
    http_counts = [0] * len(_HTTP_CLASSES)
    success_http = [0, 0]
    gone_410_prefixes: list[str] = []
    gone_410_seen = False
    gone_410_incomplete = False
    gone_410_truncated = False
    for line in lines:
        if len(line) > MAX_LINE_BYTES:
            return None
        try:
            text = line.decode("utf-8")
            if text and not text.isprintable():
                return None
            if not text.lstrip().startswith(("{", "[")):
                continue
            row = json.loads(
                text,
                object_pairs_hook=_unique_pairs,
                parse_constant=_reject_constant,
                parse_float=_finite_float,
            )
        except (UnicodeError, ValueError, RecursionError):
            return None
        if type(row) is not dict:
            return None
        if (
            row.get("logger") != "app.services.webpush"
            or row.get("message") != "webpush.send"
        ):
            continue
        extra = row.get("extra")
        if type(extra) is not dict:
            return None
        if "event" not in extra:
            continue
        if extra["event"] != "send":
            return None
        status = extra.get("status")
        if type(status) is not str or status not in _STATUSES:
            return None
        if "error_stage" not in extra:
            stage = "none"
        else:
            stage = extra["error_stage"]
            if type(stage) is not str or stage not in _STAGES[:-1]:
                return None
        code = None
        if "status_code" not in extra:
            http_class = "none"
        else:
            code = extra["status_code"]
            if type(code) is not int or not 100 <= code <= 599:
                return None
            http_class = f"{code // 100}xx"
        if status == "gone" and code == 410:
            gone_410_seen = True
            endpoint = extra.get("endpoint")
            masked = (
                _MASKED_ENDPOINT.fullmatch(endpoint) if type(endpoint) is str else None
            )
            if stage != "webpush_request" or masked is None:
                gone_410_incomplete = True
            else:
                prefix = masked.group(1)
                if prefix not in gone_410_prefixes:
                    if len(gone_410_prefixes) == _410_PREFIX_LIMIT:
                        gone_410_truncated = True
                    else:
                        gone_410_prefixes.append(prefix)
        if status == "sent" and code is not None and 200 <= code <= 299:
            success_index = 0 if code == 201 else 1
            success_http[success_index] = min(
                _COUNT_LIMIT, success_http[success_index] + 1
            )
        for counts, index in (
            (status_counts, _STATUSES.index(status)),
            (stage_counts, _STAGES.index(stage)),
            (http_counts, _HTTP_CLASSES.index(http_class)),
        ):
            counts[index] = min(_COUNT_LIMIT, counts[index] + 1)
    return WorkerSummary(
        tuple(status_counts),
        tuple(stage_counts),
        tuple(http_counts),
        (success_http[0], success_http[1]),
        tuple(gone_410_prefixes),
        gone_410_seen,
        gone_410_incomplete,
        gone_410_truncated,
    )


def render_summary(summary: WorkerSummary) -> str:
    if type(summary) is not WorkerSummary or any(
        type(values) is not tuple
        or len(values) != expected
        or any(
            type(value) is not int or not 0 <= value <= _COUNT_LIMIT for value in values
        )
        for values, expected in (
            (summary.statuses, len(_STATUSES)),
            (summary.stages, len(_STAGES)),
            (summary.http_classes, len(_HTTP_CLASSES)),
            (summary.success_http, 2),
        )
    ):
        raise ValueError
    fields = zip(
        (
            "sent",
            "gone",
            "error",
            "stage_url",
            "stage_host",
            "stage_dns",
            "stage_address",
            "stage_session",
            "stage_request",
            "stage_none",
            "http_1xx",
            "http_2xx",
            "http_3xx",
            "http_4xx",
            "http_5xx",
            "http_none",
        ),
        (*summary.statuses, *summary.stages, *summary.http_classes),
        strict=True,
    )
    return "live E2E worker push sample=tail " + " ".join(
        f"{name}={value}" for name, value in fields
    )


def render_success_summary(summary: WorkerSummary) -> str:
    """Render only successful-provider response classes, not delivery proof."""
    render_summary(summary)  # Reuse the same closed, bounded validation.
    count_201, count_other_2xx = summary.success_http
    return (
        "live E2E worker push success_http sample=tail "
        f"sent_http_201={count_201} sent_http_other_2xx={count_other_2xx}"
    )


def render_410_prefixes(summary: WorkerSummary) -> list[str]:
    """Output only validated prefixes, never the masked URL or other log data."""
    render_summary(summary)
    prefixes = summary.gone_410_prefixes
    flags = (
        summary.gone_410_seen,
        summary.gone_410_incomplete,
        summary.gone_410_truncated,
    )
    if (
        type(prefixes) is not tuple
        or len(prefixes) > _410_PREFIX_LIMIT
        or any(
            type(value) is not str or not _FINGERPRINT.fullmatch(value)
            for value in prefixes
        )
        or len(set(prefixes)) != len(prefixes)
        or any(type(flag) is not bool for flag in flags)
        or (
            not summary.gone_410_seen
            and (prefixes or summary.gone_410_incomplete or summary.gone_410_truncated)
        )
    ):
        raise ValueError
    if not summary.gone_410_seen:
        return []
    result = [
        "live E2E worker push 410 sample=tail "
        f"incomplete={str(summary.gone_410_incomplete).lower()} "
        f"truncated={str(summary.gone_410_truncated).lower()}"
    ]
    result.extend(
        "live E2E worker push 410 sample=tail endpoint_sha256=" + value
        for value in prefixes
    )
    return result


def _snapshot(
    owner: live_stand.StandOwner,
    context: live_stand._LiveDockerReadContext,
    deadline: float,
) -> tuple[live_stand.ComposeResourceEvidence, tuple[str, str]]:
    live_stand._assert_core_owner_unchanged(
        owner, deadline=deadline, docker_context=context
    )
    evidence = live_stand._verify_stand_owner_compose_resources(
        live_stand.WORKTREE, owner, deadline=deadline, docker_context=context
    )
    records = live_stand._live_core_caddy_container_inventory(
        owner, evidence, deadline=deadline, docker_context=context
    )
    workers = [
        (identifier, record)
        for identifier, record in records.items()
        if record.service == "outbox-worker"
    ]
    if len(workers) != 1:
        raise ValueError
    identifier, worker = workers[0]
    if (
        not _CONTAINER_ID.fullmatch(identifier)
        or not _CONTAINER_ID.fullmatch(worker.identity)
        or worker.running is not True
        or worker.status != "running"
    ):
        raise ValueError
    live_stand._assert_core_owner_unchanged(
        owner, deadline=deadline, docker_context=context
    )
    return evidence, (identifier, worker.identity)


def collect_worker_sample(state_dir: str, source_sha: str) -> WorkerSummary:
    """Read only the sole verified worker, with owner and container pinned twice."""
    if not state_dir or not _SOURCE_SHA.fullmatch(source_sha):
        raise ValueError
    live_stand._configure_state_mode(
        argparse.Namespace(command="e2e", in_place=True, state_dir=state_dir)
    )
    with live_stand.stand_lifecycle_lock():
        owner = live_stand.load_stand_owner(live_stand.WORKTREE)
        if owner.stack != live_stand.LIVE_STACK_CORE or owner.source_sha != source_sha:
            raise ValueError
        if live_stand._assert_in_place_source_current(owner) != source_sha:
            raise ValueError
        deadline = time.monotonic() + CAPTURE_TIMEOUT_SECONDS
        context = live_stand._new_live_docker_read_context()
        evidence, pin = _snapshot(owner, context, deadline)
        result = live_stand._run_live_bounded_read(
            ["docker", "logs", "--tail", str(MAX_LINES), pin[0]],
            context=context,
            deadline=deadline,
            maximum_bytes=MAX_BYTES,
            command_timeout_seconds=READ_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            raise ValueError
        summary = project_worker_logs(result.stdout, result.stderr)
        if summary is None:
            raise ValueError
        after_evidence, after_pin = _snapshot(owner, context, deadline)
        if after_evidence != evidence or after_pin != pin:
            raise ValueError
        if live_stand._assert_in_place_source_current(owner) != source_sha:
            raise ValueError
        live_stand._assert_live_docker_read_context(context)
        live_stand._live_probe_remaining(deadline)
        return summary


def main() -> int:
    try:
        summary = collect_worker_sample(
            os.environ.get("LIVE_STATE_DIR", ""),
            os.environ.get("LIVE_OBSERVATION_SOURCE_SHA", ""),
        )
        output = render_summary(summary)
        success_output = render_success_summary(summary)
        gone_outputs = render_410_prefixes(summary)
    except Exception:
        output = "live E2E worker push sample=unavailable"
        success_output = None
        gone_outputs = []
    try:
        print(output, flush=True)
        if success_output is not None:
            print(success_output, flush=True)
        for line in gone_outputs:
            print(line, flush=True)
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
