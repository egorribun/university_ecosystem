"""Fail closed on the pinned govulncheck JSON stream for the isolated Caddy build.

JSON mode exits zero even for vulnerabilities. The caller must supply the actual
scanner exit status: a partial stream is never evidence of completed analysis.
This is a source-symbol gate, not proof of production runtime reachability.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from scripts.quality.verify_dependency_review_scope import GHSA_EXCEPTIONS

CADDY_MODULE = "github.com/university-ecosystem/caddy"
CADDY_MANIFEST = "services/caddy/go.mod"
MAX_REPORT_BYTES = 32 * 1024 * 1024
MAX_GRAPH_BYTES = 4 * 1024 * 1024


class ReportError(ValueError):
    """The report does not establish an accepted completed Caddy scan."""


def _nonfinite(_value: str) -> None:
    raise ReportError("Non-finite JSON constant")


def _diagnostic(finding: dict[str, Any]) -> str:
    """Emit bounded identifiers only, never source positions or raw scanner text."""

    def safe(value: Any) -> str:
        if isinstance(value, str) and re.fullmatch(
            r"[A-Za-z0-9_./+*()\[\]-]{0,160}", value
        ):
            return value
        return "<invalid>"

    trace = finding["trace"]
    return json.dumps(
        {
            "osv": safe(finding["osv"]),
            "fixed_version": safe(finding.get("fixed_version", "")),
            "trace_frames": len(trace),
            "trace": [
                {
                    key: safe(frame.get(key, ""))
                    for key in ("module", "version", "package", "function")
                }
                for frame in trace[:8]
            ],
        },
        sort_keys=True,
    )


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReportError("Duplicate JSON key")
        result[key] = value
    return result


def _messages(text: str) -> list[dict[str, Any]]:
    if not text.strip() or len(text.encode("utf-8")) > MAX_REPORT_BYTES:
        raise ReportError("Empty or oversized report")
    decoder = json.JSONDecoder(object_pairs_hook=_object, parse_constant=_nonfinite)
    result = []
    offset = 0
    while offset < len(text):
        if text[offset].isspace():
            offset += 1
            continue
        try:
            record, offset = decoder.raw_decode(text, offset)
        except json.JSONDecodeError as exc:
            raise ReportError("Malformed JSON stream") from exc
        if not isinstance(record, dict) or len(record) != 1:
            raise ReportError("Each message must have exactly one kind")
        kind, payload = next(iter(record.items()))
        if kind not in {"config", "SBOM", "osv", "finding", "progress"}:
            raise ReportError("Unknown report message")
        if not isinstance(payload, dict):
            raise ReportError("Message payload must be an object")
        result.append(record)
    return result


def _expected_modules(graph: str) -> dict[str, str]:
    """Read the successfully generated, production-tagged Go package graph."""
    if not graph.strip() or len(graph.encode("utf-8")) > MAX_GRAPH_BYTES:
        raise ReportError("Empty or oversized Caddy module graph")
    modules: dict[str, str] = {}
    for line in graph.splitlines():
        fields = line.split()
        if not fields:
            continue
        if len(fields) not in (1, 2):
            raise ReportError("Malformed Caddy module graph")
        path, version = fields[0], fields[1] if len(fields) == 2 else ""
        if (path == CADDY_MODULE) != (version == "") or path == "stdlib":
            raise ReportError("Malformed Caddy module graph")
        if path in modules and modules[path] != version:
            raise ReportError("Conflicting Caddy module versions")
        modules[path] = version
    if (
        not {
            CADDY_MODULE,
            "github.com/caddyserver/caddy/v2",
            "github.com/mholt/caddy-ratelimit",
        }
        <= modules.keys()
    ):
        raise ReportError("Incomplete Caddy module graph")
    # Go's dependency list omits standard-library packages' module metadata.
    modules["stdlib"] = "v1.26.10"
    return modules


def validate_report(
    text: str, scanner_status: int, *, graph: str, today: date | None = None
) -> dict[str, int]:
    """Validate source identity, completion status and bounded reachable findings."""
    if type(scanner_status) is not int or scanner_status != 0:
        raise ReportError("govulncheck did not complete successfully")
    records = _messages(text)
    if "config" not in records[0]:
        raise ReportError("Configuration must be first")
    configs = [r["config"] for r in records if "config" in r]
    sboms = [r["SBOM"] for r in records if "SBOM" in r]
    if len(configs) != 1 or len(sboms) != 1:
        raise ReportError("Exactly one configuration and SBOM are required")
    expected = {
        "protocol_version": "v1.0.0",
        "scanner_name": "govulncheck",
        "scanner_version": "v1.8.0",
        "scan_level": "symbol",
        "scan_mode": "source",
        "go_version": "go1.26.10",
        "db": "https://vuln.go.dev",
    }
    if any(configs[0].get(key) != value for key, value in expected.items()):
        raise ReportError("Unexpected scanner configuration")
    sbom = sboms[0]
    modules = sbom.get("modules")
    if (
        sbom.get("roots") != [CADDY_MODULE]
        or sbom.get("go_version") != expected["go_version"]
        or not isinstance(modules, list)
        or not all(
            isinstance(m, dict)
            and isinstance(m.get("path"), str)
            and isinstance(m.get("version", ""), str)
            for m in modules
        )
        or sum(m["path"] == CADDY_MODULE for m in modules) != 1
    ):
        raise ReportError("Report does not describe the Caddy source root")
    scanned_modules = {m["path"]: m.get("version", "") for m in modules}
    if len(scanned_modules) != len(modules) or scanned_modules != _expected_modules(
        graph
    ):
        raise ReportError("Scanned modules do not match the Caddy build graph")

    advisories: dict[str, dict[str, Any]] = {}
    advisory_payloads: dict[str, str] = {}
    for record in records:
        if "osv" not in record:
            continue
        osv = record["osv"]
        identifier = osv.get("id")
        aliases = osv.get("aliases", [])
        if not isinstance(identifier, str) or not re.fullmatch(
            r"GO-[0-9]{4}-[0-9]{1,12}", identifier
        ):
            raise ReportError("Malformed advisory identifier")
        if not isinstance(aliases, list) or not all(
            isinstance(alias, str) and alias for alias in aliases
        ):
            raise ReportError(f"Malformed advisory aliases: {identifier}")
        # v1.8.0 emitOSVs emits per-module records without deduplication. A
        # multi-module advisory can repeat; never merge or overwrite conflicts.
        canonical = json.dumps(
            osv, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        if (
            identifier in advisory_payloads
            and advisory_payloads[identifier] != canonical
        ):
            raise ReportError(f"Conflicting advisory: {identifier}")
        advisories[identifier] = osv
        advisory_payloads[identifier] = canonical

    as_of = today if today is not None else datetime.now(UTC).date()
    reachable = 0
    accepted = 0
    for record in records:
        if "finding" not in record:
            continue
        finding = record["finding"]
        identifier = finding.get("osv")
        trace = finding.get("trace")
        if (
            not isinstance(identifier, str)
            or identifier not in advisories
            or not isinstance(trace, list)
            or not trace
        ):
            raise ReportError("Finding lacks an advisory or trace")
        for frame in trace:
            if (
                not isinstance(frame, dict)
                or not isinstance(frame.get("module"), str)
                or not frame["module"]
                or any(
                    not isinstance(frame.get(key, ""), str)
                    for key in ("function", "package", "version")
                )
            ):
                raise ReportError("Malformed finding frame")
        first = trace[0]
        if not first.get("function"):
            if len(trace) != 1:
                raise ReportError("Lower-level findings must have one frame")
            continue
        if not first.get("package"):
            raise ReportError("Symbol finding lacks its package")
        if scanned_modules.get(first["module"]) != first.get("version", ""):
            raise ReportError("Finding does not match the scanned module graph")
        reachable += 1
        aliases = {
            alias
            for alias in advisories[identifier].get("aliases", [])
            if alias.startswith("GHSA-")
        }
        approved = {
            entry["ghsa"]
            for entry in GHSA_EXCEPTIONS
            if entry["manifest"] == CADDY_MANIFEST
            and entry["ecosystem"] == "gomod"
            and entry["owner"] == "egorribun"
            and entry["name"] == first["module"]
            and "v" + entry["version"] == first.get("version")
            and as_of < entry["expires"]
        }
        if not aliases or not aliases <= approved:
            raise ReportError("Unaccepted reachable advisory: " + _diagnostic(finding))
        accepted += 1
    return {"reachable": reachable, "accepted": accepted}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--scanner-status", type=int, required=True)
    args = parser.parse_args()
    try:
        if args.report.stat().st_size > MAX_REPORT_BYTES:
            raise ReportError("Oversized report")
        if args.graph.stat().st_size > MAX_GRAPH_BYTES:
            raise ReportError("Oversized Caddy module graph")
        result = validate_report(
            args.report.read_text(encoding="utf-8"),
            args.scanner_status,
            graph=args.graph.read_text(encoding="utf-8"),
        )
    except (OSError, UnicodeError, ReportError) as exc:
        print(f"Caddy vulnerability gate failed: {exc}")
        return 1
    print(json.dumps({"caddy_source_scan": "accepted", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
