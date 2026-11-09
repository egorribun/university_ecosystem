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
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from scripts.quality.verify_dependency_review_scope import GHSA_EXCEPTIONS

MAX_SARIF_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class _ParsedMessage:
    name: str
    version: str
    identifiers: tuple[str, ...]


def _parse_advisory_id(value: str, start: int) -> tuple[str, int] | None:
    """Read one exact scanner advisory token with a single forward pass."""
    if value.startswith("CVE-", start):
        prefix_end = start + len("CVE-")
    elif value.startswith("GO-", start):
        prefix_end = start + len("GO-")
    elif value.startswith("GHSA-", start):
        cursor = start + len("GHSA-")
        for group in range(3):
            group_end = cursor + 4
            if group_end > len(value) or any(
                not ("a" <= char <= "z" or "0" <= char <= "9")
                for char in value[cursor:group_end]
            ):
                return None
            cursor = group_end
            if group < 2:
                if cursor >= len(value) or value[cursor] != "-":
                    return None
                cursor += 1
        return value[start:cursor], cursor
    else:
        return None

    year_end = prefix_end + 4
    if year_end >= len(value) or any(
        not ("0" <= char <= "9") for char in value[prefix_end:year_end]
    ):
        return None
    if value[year_end] != "-":
        return None
    digits_start = year_end + 1
    cursor = digits_start
    while cursor < len(value) and "0" <= value[cursor] <= "9":
        cursor += 1
    if cursor - digits_start < 4:
        return None
    return value[start:cursor], cursor


def _parse_message(message: str) -> _ParsedMessage | None:
    """Parse the scanner's exact package/advisory message grammar linearly."""
    prefix = "Package '"
    if not message.startswith(prefix):
        return None

    name_start = len(prefix)
    separator = message.find("@", name_start)
    if separator <= name_start:
        return None
    name = message[name_start:separator]
    if any(char == "'" or char.isspace() for char in name):
        return None

    version_start = separator + 1
    cursor = version_start
    while (
        cursor < len(message)
        and message[cursor] != "'"
        and not message[cursor].isspace()
    ):
        cursor += 1
    if cursor == version_start or not message.startswith(
        "' is vulnerable to '", cursor
    ):
        return None
    version = message[version_start:cursor]
    cursor += len("' is vulnerable to '")

    primary = _parse_advisory_id(message, cursor)
    if primary is None:
        return None
    identifier, cursor = primary
    if cursor >= len(message) or message[cursor] != "'":
        return None
    cursor += 1
    identifiers = [identifier]

    alias_prefix = " (also known as '"
    if message.startswith(alias_prefix, cursor):
        cursor += len(alias_prefix)
        while True:
            alias = _parse_advisory_id(message, cursor)
            if alias is None:
                return None
            alias_id, cursor = alias
            identifiers.append(alias_id)
            if message.startswith("', '", cursor):
                cursor += len("', '")
                continue
            if message.startswith("')", cursor):
                cursor += len("')")
                break
            return None

    if cursor < len(message) and message[cursor] == ".":
        cursor += 1
    if cursor != len(message):
        return None
    return _ParsedMessage(name, version, tuple(identifiers))


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
    parts = uri.split("/")
    if "services" not in parts:
        raise OsvResultError("result location is outside services/")
    return "/".join(parts[parts.index("services") :])


def _ghsa_alias(
    run: dict[str, Any], result: dict[str, Any], message: _ParsedMessage
) -> str:
    # v2.6.0 emits all aliases, not only GHSA, and repeats the complete alias
    # group in the referenced rule's deprecatedIds. Never select the first
    # approved alias from an ambiguous group or from unmatched message text.
    ids = message.identifiers
    if len(set(ids)) != len(ids):
        raise OsvResultError("duplicate advisory identifier")
    ghsas = [identifier for identifier in ids if identifier.startswith("GHSA-")]
    if not ghsas:
        raise OsvResultError(f"finding {ids[0]} has no GHSA alias")
    if len(ghsas) != 1:
        raise OsvResultError("finding has ambiguous GHSA aliases")
    tool = run.get("tool")
    driver = tool.get("driver") if isinstance(tool, dict) else None
    rules = driver.get("rules") if isinstance(driver, dict) else None
    if not isinstance(rules, list) or not all(isinstance(rule, dict) for rule in rules):
        raise OsvResultError("finding has no valid SARIF rules")
    matched = [
        (index, rule) for index, rule in enumerate(rules) if rule.get("id") == ids[0]
    ]
    if result.get("ruleId") != ids[0] or len(matched) != 1:
        raise OsvResultError("finding does not identify one matching SARIF rule")
    index, rule = matched[0]
    if "ruleIndex" in result and (
        type(result["ruleIndex"]) is not int or result["ruleIndex"] != index
    ):
        raise OsvResultError("finding ruleIndex disagrees with ruleId")
    if rule.get("deprecatedIds") != list(ids):
        raise OsvResultError("finding aliases disagree with SARIF rule")
    return ghsas[0]


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
            parsed_message = _parse_message(message)
            if parsed_message is None:
                raise OsvResultError("unparsable finding message")
            locations = result.get("locations") or []
            if len(locations) != 1:
                raise OsvResultError("finding must have exactly one location")
            uri = str(locations[0]["physicalLocation"]["artifactLocation"]["uri"])
            manifest = _manifest(uri)
            alias = _ghsa_alias(run, result, parsed_message)
            key = (alias, manifest, parsed_message.name, parsed_message.version)
            record = exceptions.get(key)
            if record is None:
                raise OsvResultError(
                    f"unexcepted finding {alias} in {parsed_message.name} "
                    f"{parsed_message.version} at {manifest}"
                )
            if today >= record["expires"]:
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
