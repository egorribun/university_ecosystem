"""Fail closed on osv-scanner SARIF for the Go modules (AUD-483).

Every reported result must be an exact, unexpired owner disposition from
GHSA_EXCEPTIONS: same advisory alias, same manifest, same module name and same
version. Any other result, including a stdlib result, fails. A scanner exit
status other than 0 or 1, or a malformed SARIF document, also fails. This is a
module-level inventory gate; reachability is decided by the govulncheck gates.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from scripts.quality.verify_dependency_review_scope import GHSA_EXCEPTIONS

MAX_SARIF_BYTES = 32 * 1024 * 1024
MESSAGE = re.compile(
    r"^Package '(?P<name>[^@']+)@(?P<version>[^']+)' is vulnerable to "
    r"'(?P<id>[^']+)'(?: \(also known as '(?P<alias>GHSA-[a-z0-9-]+)'\))?\.?$"
)


class OsvResultError(ValueError):
    """The scanner output does not establish an exact disposition for a result."""


def _today() -> date:
    return datetime.now(UTC).date()


def _exceptions_by_key() -> dict[tuple[str, str, str, str], dict[str, Any]]:
    keyed: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for record in GHSA_EXCEPTIONS:
        key = (
            str(record["ghsa"]),
            str(record["manifest"]),
            str(record["name"]),
            str(record["version"]),
        )
        keyed[key] = record
    return keyed


def _manifest(uri: str) -> str:
    marker = "services/"
    index = uri.find(marker)
    if index < 0:
        raise OsvResultError("result location is outside services/")
    return uri[index:]


def validate(report: dict[str, Any], scanner_status: int, today: date) -> list[str]:
    """Return the accepted dispositions as diagnostic lines, or raise."""
    if scanner_status not in (0, 1):
        raise OsvResultError(f"scanner failed operationally (exit {scanner_status})")
    if report.get("version") != "2.1.0":
        raise OsvResultError("SARIF version is not 2.1.0")
    runs = report.get("runs")
    if not isinstance(runs, list) or not runs:
        raise OsvResultError("SARIF has no runs")

    exceptions = _exceptions_by_key()
    accepted: list[str] = []
    findings = 0
    for run in runs:
        for result in run.get("results") or []:
            findings += 1
            message = str((result.get("message") or {}).get("text", ""))
            match = MESSAGE.match(message)
            if match is None:
                raise OsvResultError("unparsable finding message")
            locations = result.get("locations") or []
            if len(locations) != 1:
                raise OsvResultError("finding must have exactly one location")
            uri = str(locations[0]["physicalLocation"]["artifactLocation"]["uri"])
            manifest = _manifest(uri)
            alias = match.group("alias")
            if alias is None:
                raise OsvResultError(f"finding {match.group('id')} has no GHSA alias")
            key = (alias, manifest, match.group("name"), match.group("version"))
            record = exceptions.get(key)
            if record is None:
                raise OsvResultError(
                    f"unexcepted finding {alias} in {match.group('name')} "
                    f"{match.group('version')} at {manifest}"
                )
            if today > record["expires"]:
                raise OsvResultError(f"disposition for {alias} expired")
            accepted.append(f"{alias} {manifest}")
    if scanner_status == 0 and findings:
        raise OsvResultError("scanner exited 0 but reported findings")
    if scanner_status == 1 and not findings:
        raise OsvResultError("scanner exited 1 without a reportable finding")
    return sorted(set(accepted))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sarif", type=Path, required=True)
    parser.add_argument("--scanner-status", type=int, required=True)
    args = parser.parse_args()
    raw = args.sarif.read_bytes()
    if not raw or len(raw) > MAX_SARIF_BYTES:
        print("OSV Go result: empty or oversized SARIF", file=sys.stderr)
        return 1
    try:
        report = json.loads(raw.decode("utf-8"))
        accepted = validate(report, args.scanner_status, _today())
    except (OsvResultError, ValueError, KeyError, TypeError) as error:
        print(f"OSV Go result rejected: {error}", file=sys.stderr)
        return 1
    print(f"OSV Go result accepted {len(accepted)} exact disposition(s):")
    for line in accepted:
        print(f"  {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
