"""Bounded, owned Core-only transport observations; never export raw logs."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

_SERVICES = ("caddy", "gateway")
_CATEGORIES = ("eof", "timeout", "refused", "reset", "dns", "other")
_MAX_BYTES = 65_536
_PREFIX = "live E2E transport diagnostic"
_TIMESTAMP = re.compile(rb"^\d{4}-\d\d-\d\dT[0-9:.]+Z ")
_STARTED = re.compile(r"\d{4}-\d\d-\d\dT[0-9:.]+Z")


def summarize(service: str, data: bytes) -> dict[str, int]:
    """Closed aggregate only. Absence is not proof of absence or correlation."""
    if service not in _SERVICES or type(data) is not bytes or len(data) > _MAX_BYTES:
        raise ValueError("invalid diagnostic input")
    counts = dict.fromkeys(_CATEGORIES, 0)
    for line in data.splitlines(keepends=True):
        if not line.endswith(b"\n") or len(line) > 8192:
            continue
        prefix = _TIMESTAMP.match(line)
        if prefix is None:
            continue
        try:
            record = json.loads(line[prefix.end() :])
        except (ValueError, UnicodeError):
            continue
        if type(record) is not dict:
            continue
        if service == "gateway":
            if (
                record.get("service") != "gateway"
                or record.get("msg") != "Proxy error"
                or record.get("path") != "/api/v1/auth/login"
            ):
                continue
            error = record.get("err")
        else:
            request = record.get("request")
            if (
                record.get("logger") != "http.log.error"
                or type(request) is not dict
                or request.get("method") != "POST"
                or request.get("uri") != "/api/v1/auth/login"
                or record.get("status") != 502
            ):
                continue
            error = record.get("msg")
        if type(error) is not str or len(error) > 4096:
            continue
        lowered = error.lower()
        category = "other"
        for needle, candidate in (
            ("eof", "eof"),
            ("timeout", "timeout"),
            ("deadline exceeded", "timeout"),
            ("connection refused", "refused"),
            ("connection reset", "reset"),
            ("no such host", "dns"),
        ):
            if needle in lowered:
                category = candidate
                break
        counts[category] = min(512, counts[category] + 1)
    return counts


@dataclass(frozen=True)
class Capture:
    context: Any
    pins: tuple[tuple[str, str, str, str, int], ...]
    since: int


def _pins(live: Any, owner: Any, context: Any, deadline: float) -> tuple:
    live._assert_core_owner_unchanged(owner, deadline=deadline, docker_context=context)
    evidence = live._verify_stand_owner_compose_resources(
        live.WORKTREE, owner, deadline=deadline, docker_context=context
    )
    inventory = live._live_core_caddy_container_inventory(
        owner, evidence, deadline=deadline, docker_context=context
    )
    pins = []
    for service in _SERVICES:
        selected = [
            (identifier, record)
            for identifier, record in inventory.items()
            if record.service == service
        ]
        if len(selected) != 1:
            raise ValueError("ambiguous owned service")
        identifier, record = selected[0]
        if not record.running or record.status != "running":
            raise ValueError("owned service not running")
        result = live._run_live_bounded_read(
            [
                "docker",
                "inspect",
                "--format",
                "[{{json .State.StartedAt}},{{json .RestartCount}}]",
                identifier,
            ],
            context=context,
            deadline=deadline,
            maximum_bytes=1024,
            command_timeout_seconds=3,
        )
        if result.returncode != 0 or result.stderr:
            raise ValueError("identity read failed")
        boot = json.loads(result.stdout)
        if (
            type(boot) is not list
            or len(boot) != 2
            or type(boot[0]) is not str
            or _STARTED.fullmatch(boot[0]) is None
            or type(boot[1]) is not int
            or not 0 <= boot[1] <= 1_000_000
        ):
            raise ValueError("identity read invalid")
        pins.append((service, identifier, record.identity, boot[0], boot[1]))
    live._assert_core_owner_unchanged(owner, deadline=deadline, docker_context=context)
    return tuple(pins)


def prepare(live: Any, owner: Any) -> Capture | None:
    """Diagnostic admission failures never change the acceptance outcome."""
    if owner.stack != live.LIVE_STACK_CORE:
        return None
    try:
        context = live._new_live_docker_read_context()
        pins = _pins(live, owner, context, time.monotonic() + 15)
        return Capture(context, pins, time.time_ns() // 1_000_000)
    except Exception:
        return None


def emit_failure(live: Any, owner: Any, capture: Capture | None) -> None:
    """Read only pinned containers, reverify afterwards, emit finite aggregates."""
    try:
        if capture is None:
            print(f"{_PREFIX} state=unavailable", flush=True)
            return
        until = time.time_ns() // 1_000_000
        if not 0 <= until - capture.since <= 3_600_000:
            raise ValueError("invalid capture window")
        deadline = time.monotonic() + 20
        if _pins(live, owner, capture.context, deadline) != capture.pins:
            raise ValueError("service identity changed")
        summaries = []
        for service, identifier, _, _, _ in capture.pins:
            result = live._run_live_bounded_read(
                [
                    "docker",
                    "logs",
                    "--timestamps",
                    "--tail",
                    "512",
                    "--since",
                    live._caddy_probe_timestamp_argument(capture.since),
                    "--until",
                    live._caddy_probe_timestamp_argument(until),
                    identifier,
                ],
                context=capture.context,
                deadline=deadline,
                maximum_bytes=_MAX_BYTES,
                command_timeout_seconds=5,
            )
            if result.returncode != 0:
                raise ValueError("log read failed")
            # Docker separates container stdout/stderr. Parse each independently;
            # never join an unterminated record to the other stream.
            first = summarize(service, result.stdout)
            second = summarize(service, result.stderr)
            summaries.append(
                (
                    service,
                    {key: min(512, first[key] + second[key]) for key in _CATEGORIES},
                )
            )
        if _pins(live, owner, capture.context, deadline) != capture.pins:
            raise ValueError("service identity changed")
        for service, counts in summaries:
            fields = " ".join(f"{key}={counts[key]}" for key in _CATEGORIES)
            print(
                f"{_PREFIX} state=observed service={service} "
                f"scope=bounded-unmatched {fields}",
                flush=True,
            )
    except Exception:
        # No exception messages, raw bytes, paths, identifiers or headers escape.
        try:
            print(f"{_PREFIX} state=unavailable", flush=True)
        except Exception:
            pass


def run(live: Any, owner: Any, arguments: dict[str, Any]) -> None:
    """Preserve the original invocation and failure; diagnostics never retry it."""
    capture = prepare(live, owner) if owner.stack == live.LIVE_STACK_CORE else None
    try:
        live._run_live_playwright(**arguments)
    except Exception:
        if owner.stack == live.LIVE_STACK_CORE:
            emit_failure(live, owner, capture)
        raise
