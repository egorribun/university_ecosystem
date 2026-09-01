"""Run a fail-closed Python dependency audit through OSV's batch API.

``pip-audit`` 2.10.1 queries OSV once per dependency.  The per-package endpoint
is occasionally unavailable even while OSV's batch endpoint is healthy, which
turns an otherwise deterministic audit into an operational failure.  This
adapter keeps ``pip-audit``'s frozen requirement parsing and report shape, but
uses ``/v1/querybatch`` for the package/version inventory and fetches the full
vulnerability records by ID before emitting the same JSON fields consumed by
``check_dependency_audit_report.py``.

The adapter is deliberately fail-closed: an incomplete batch, malformed OSV
record, redirect, unsupported schema, or exhausted retry budget removes the
output report and exits with status 2.  Status 0 means a complete clean
inventory; status 1 means a complete inventory containing advisories (which the
existing allowlist validator must then approve).
"""

from __future__ import annotations

import argparse
import json
import time
import warnings
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import cast

import requests
from packaging.utils import canonicalize_name
from packaging.version import Version

with warnings.catch_warnings():
    # pip-audit 2.10.1 vendors pyparsing, which imports Python 3.14's deprecated
    # ``sre_constants`` module during import.  Keep this narrow suppression at
    # the third-party boundary; audit payloads and operational failures remain
    # fail-closed and no repository warnings are hidden.
    warnings.filterwarnings(
        "ignore",
        message=r"module 'sre_constants' is deprecated",
        category=DeprecationWarning,
    )
    from pip_audit._audit import Auditor  # type: ignore[import-untyped]
    from pip_audit._dependency_source import (  # type: ignore[import-untyped]
        RequirementSource,
    )
    from pip_audit._service import (  # type: ignore[import-untyped]
        Dependency,
        ResolvedDependency,
        ServiceError,
        SkippedDependency,
        VulnerabilityResult,
        VulnerabilityService,
    )

OSV_BATCH_URL = "https://api.osv.dev/v1/querybatch"
OSV_VULN_URL = "https://api.osv.dev/v1/vulns/"
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_ATTEMPTS = 4
DEFAULT_BATCH_SIZE = 100
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class OsvBatchError(ServiceError):  # type: ignore[misc]
    """Raised when OSV batch or vulnerability data is incomplete or invalid."""


def _mapping(value: object, *, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise OsvBatchError(f"{label} must be a JSON object")
    return cast(dict[str, object], value)


def _list(value: object, *, label: str) -> list[object]:
    if not isinstance(value, list):
        raise OsvBatchError(f"{label} must be a JSON array")
    return cast(list[object], value)


def _string(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OsvBatchError(f"{label} must be a non-empty string")
    return value.strip()


def _retry_delay(attempt: int) -> float:
    """Return a bounded deterministic backoff for the next attempt."""
    return float(2 ** (attempt - 1))


class OsvBatchService(VulnerabilityService):  # type: ignore[misc]
    """Vulnerability service backed by deterministic OSV batch requests."""

    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        attempts: int = DEFAULT_ATTEMPTS,
        batch_size: int = DEFAULT_BATCH_SIZE,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if attempts <= 0:
            raise ValueError("attempts must be positive")
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        self._session = session or requests.Session()
        self._session.max_redirects = 5
        self._timeout = timeout
        self._attempts = attempts
        self._batch_size = batch_size
        self._sleep = sleep

    def query(self, spec: Dependency) -> tuple[Dependency, list[VulnerabilityResult]]:
        """Reject single-package queries so callers cannot reintroduce N+1 calls."""
        raise OsvBatchError("OSV batch service only supports query_all")

    def query_all(
        self, specs: Iterator[Dependency]
    ) -> Iterator[tuple[Dependency, list[VulnerabilityResult]]]:
        ordered_specs = list(specs)
        resolved_specs: list[ResolvedDependency] = []
        for spec in ordered_specs:
            if isinstance(spec, SkippedDependency):
                continue
            if not isinstance(spec, ResolvedDependency):
                raise OsvBatchError(f"unsupported dependency record: {spec!r}")
            resolved_specs.append(spec)

        findings = self._query_batches(resolved_specs)
        for spec in ordered_specs:
            if isinstance(spec, SkippedDependency):
                yield spec, []
            else:
                key = self._dependency_key(cast(ResolvedDependency, spec))
                yield spec, findings[key]

    @staticmethod
    def _dependency_key(spec: ResolvedDependency) -> tuple[str, str]:
        return canonicalize_name(spec.name), str(spec.version)

    def _query_batches(
        self, specs: list[ResolvedDependency]
    ) -> dict[tuple[str, str], list[VulnerabilityResult]]:
        keys = [self._dependency_key(spec) for spec in specs]
        if len(keys) != len(set(keys)):
            raise OsvBatchError(
                "requirements contain duplicate package/version records"
            )

        references: dict[tuple[str, str], list[str]] = {}
        for start in range(0, len(specs), self._batch_size):
            batch = specs[start : start + self._batch_size]
            payload: dict[str, object] = {
                "queries": [
                    {
                        "package": {
                            "name": canonicalize_name(spec.name),
                            "ecosystem": "PyPI",
                        },
                        "version": str(spec.version),
                    }
                    for spec in batch
                ]
            }
            response = self._request_json(OSV_BATCH_URL, payload)
            raw_results = _list(response.get("results"), label="OSV querybatch.results")
            if len(raw_results) != len(batch):
                raise OsvBatchError(
                    "OSV querybatch returned a result count different from the request"
                )
            for spec, raw_result in zip(batch, raw_results, strict=True):
                result = _mapping(raw_result, label="OSV querybatch result")
                raw_vulns = result.get("vulns", [])
                vuln_refs = _list(raw_vulns, label="OSV querybatch result.vulns")
                ids: list[str] = []
                for index, raw_ref in enumerate(vuln_refs):
                    ref = _mapping(
                        raw_ref, label=f"OSV querybatch result.vulns[{index}]"
                    )
                    identifier = _string(ref.get("id"), label="OSV vulnerability id")
                    if identifier not in ids:
                        ids.append(identifier)
                references[self._dependency_key(spec)] = sorted(ids)

        detail_cache: dict[str, VulnerabilityResult | None] = {}
        findings: dict[tuple[str, str], list[VulnerabilityResult]] = {}
        for spec in specs:
            key = self._dependency_key(spec)
            package_name = canonicalize_name(spec.name)
            parsed: list[VulnerabilityResult] = []
            for identifier in references[key]:
                if identifier not in detail_cache:
                    detail_cache[identifier] = self._parse_vulnerability(
                        identifier,
                        self._request_json(
                            f"{OSV_VULN_URL}{identifier}", None, method="GET"
                        ),
                        package_name,
                    )
                detail = detail_cache[identifier]
                if detail is not None:
                    parsed.append(detail)
            findings[key] = parsed
        return findings

    def _request_json(
        self,
        url: str,
        payload: dict[str, object] | None,
        *,
        method: str = "POST",
    ) -> dict[str, object]:
        headers = {"Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        for attempt in range(1, self._attempts + 1):
            try:
                if method == "GET":
                    response = self._session.get(
                        url,
                        headers=headers,
                        timeout=self._timeout,
                        allow_redirects=False,
                    )
                elif method == "POST":
                    response = self._session.post(
                        url,
                        json=payload,
                        headers=headers,
                        timeout=self._timeout,
                        allow_redirects=False,
                    )
                else:
                    raise OsvBatchError(f"unsupported OSV HTTP method: {method}")
            except requests.RequestException as exc:
                if attempt == self._attempts:
                    raise OsvBatchError(
                        f"OSV request failed after {self._attempts} attempts: {exc}"
                    ) from exc
                self._sleep(_retry_delay(attempt))
                continue

            if response.status_code in RETRYABLE_STATUS_CODES:
                if attempt == self._attempts:
                    raise OsvBatchError(
                        f"OSV request returned HTTP {response.status_code} after "
                        f"{self._attempts} attempts"
                    )
                self._sleep(_retry_delay(attempt))
                continue
            if response.status_code >= 300:
                raise OsvBatchError(f"OSV request returned HTTP {response.status_code}")
            try:
                parsed = response.json()
            except (ValueError, requests.RequestException) as exc:
                raise OsvBatchError("OSV response is not valid JSON") from exc
            return _mapping(parsed, label="OSV response")

        raise AssertionError("retry loop must return or raise")

    @staticmethod
    def _parse_vulnerability(
        identifier: str, payload: dict[str, object], package_name: str
    ) -> VulnerabilityResult | None:
        payload_id = _string(payload.get("id"), label="OSV vulnerability.id")
        if payload_id != identifier:
            raise OsvBatchError(
                f"OSV vulnerability id mismatch: requested {identifier!r}, got {payload_id!r}"
            )
        if payload.get("withdrawn") is not None:
            return None

        schema = _string(
            payload.get("schema_version", "1.0.0"), label="OSV schema_version"
        )
        try:
            if Version(schema).major != 1:
                raise OsvBatchError(f"unsupported OSV schema version: {schema}")
        except ValueError as exc:
            raise OsvBatchError(f"invalid OSV schema version: {schema}") from exc

        affected = _list(payload.get("affected"), label="OSV vulnerability.affected")
        matched = False
        fix_versions: set[Version] = set()
        for affected_index, raw_affected in enumerate(affected):
            entry = _mapping(raw_affected, label=f"OSV affected[{affected_index}]")
            package = _mapping(
                entry.get("package"), label=f"OSV affected[{affected_index}].package"
            )
            ecosystem = _string(
                package.get("ecosystem"),
                label=f"OSV affected[{affected_index}].package.ecosystem",
            )
            name = _string(
                package.get("name"),
                label=f"OSV affected[{affected_index}].package.name",
            )
            if ecosystem != "PyPI" or canonicalize_name(name) != package_name:
                continue
            matched = True
            ranges = _list(
                entry.get("ranges", []), label=f"OSV affected[{affected_index}].ranges"
            )
            for range_index, raw_range in enumerate(ranges):
                range_entry = _mapping(
                    raw_range,
                    label=f"OSV affected[{affected_index}].ranges[{range_index}]",
                )
                if range_entry.get("type") != "ECOSYSTEM":
                    continue
                events = _list(
                    range_entry.get("events", []),
                    label=f"OSV affected[{affected_index}].ranges[{range_index}].events",
                )
                for event_index, raw_event in enumerate(events):
                    event = _mapping(
                        raw_event,
                        label=(
                            f"OSV affected[{affected_index}].ranges[{range_index}]"
                            f".events[{event_index}]"
                        ),
                    )
                    fixed = event.get("fixed")
                    if fixed is not None:
                        fixed_text = _string(fixed, label="OSV fixed version")
                        try:
                            fix_versions.add(Version(fixed_text))
                        except ValueError as exc:
                            raise OsvBatchError(
                                f"invalid OSV fixed version: {fixed_text}"
                            ) from exc
        if not matched:
            raise OsvBatchError(
                f"OSV vulnerability {identifier} does not affect queried package {package_name}"
            )

        raw_aliases = payload.get("aliases", [])
        aliases = [
            _string(alias, label=f"OSV vulnerability.aliases[{index}]")
            for index, alias in enumerate(_list(raw_aliases, label="OSV aliases"))
        ]
        summary = payload.get("summary")
        description = summary if summary is not None else payload.get("details", "N/A")
        description_text = _string(description, label="OSV vulnerability.description")
        published = payload.get("published")
        published_text = (
            None if published is None else _string(published, label="OSV published")
        )
        return VulnerabilityResult.create(
            ids=[identifier, *aliases],
            description=description_text.replace("\n", " "),
            fix_versions=sorted(fix_versions),
            published=VulnerabilityService._parse_rfc3339(published_text),
        )


def _report(
    results: list[tuple[Dependency, list[VulnerabilityResult]]],
) -> tuple[dict[str, object], bool]:
    dependencies: list[dict[str, object]] = []
    has_findings = False
    for dependency, vulnerabilities in results:
        if isinstance(dependency, SkippedDependency):
            dependencies.append(
                {
                    "name": dependency.canonical_name,
                    "skip_reason": dependency.skip_reason,
                }
            )
            continue
        resolved = cast(ResolvedDependency, dependency)
        rendered: list[dict[str, object]] = []
        for vulnerability in sorted(vulnerabilities, key=lambda item: str(item.id)):
            has_findings = True
            rendered.append(
                {
                    "id": str(vulnerability.id),
                    "aliases": sorted(str(alias) for alias in vulnerability.aliases),
                    "fix_versions": [
                        str(version) for version in vulnerability.fix_versions
                    ],
                }
            )
        dependencies.append(
            {
                "name": resolved.canonical_name,
                "version": str(resolved.version),
                "vulns": rendered,
            }
        )
    return {"dependencies": dependencies, "fixes": []}, has_findings


def _write_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requirement", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--attempts", type=int, default=DEFAULT_ATTEMPTS)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.output.unlink(missing_ok=True)
    try:
        source = RequirementSource(
            [args.requirement], no_deps=True, disable_pip=True, skip_editable=False
        )
        service = OsvBatchService(
            timeout=args.timeout, attempts=args.attempts, batch_size=args.batch_size
        )
        results = list(Auditor(service).audit(source))
        payload, has_findings = _report(results)
        _write_atomic(args.output, payload)
        return 1 if has_findings else 0
    except Exception as exc:
        args.output.unlink(missing_ok=True)
        print(f"::error::OSV batch audit failed: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
