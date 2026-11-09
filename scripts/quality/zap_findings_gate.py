"""Fail-closed gate for the ZAP DAST JSON report (AUD-381).

The pinned zaproxy/action-full-scan runs ``zap-full-scan.py -J report_json.json``
in the workspace. ZAP records each alert with a ``riskcode`` string: ``0``
informational, ``1`` low, ``2`` medium and ``3`` high. A missing, symlinked,
unreadable, oversized, unparsable or unexpectedly shaped report makes the scan
result unknown, so the gate fails.

Owner decision (2026-11-09): alerts of medium (riskcode 2) or high (riskcode 3)
fail the job, matching the Nuclei gate. Informational and low alerts are
reported only. The gate prints counts per risk and ZAP rule identifiers only;
it never prints URLs, parameters, evidence or any other report value.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, NoReturn

MAX_REPORT_BYTES = 128 * 1024 * 1024
BLOCKING_RISKCODE = 2
RISK_NAMES = {3: "high", 2: "medium", 1: "low", 0: "informational"}
_RISKCODES = {"0": 0, "1": 1, "2": 2, "3": 3}
_PLUGIN_ID = re.compile(r"[0-9]{1,10}")

_INVALID = "Could not validate ZAP JSON report; the scan result is unknown."
_MISSING = "ZAP produced no JSON report; the scan result is unknown."
_NOT_REGULAR = "ZAP JSON report is not a regular file; the scan result is unknown."
_OVERSIZED = "ZAP JSON report exceeds the size bound; the scan result is unknown."
_UNREADABLE = "Could not read ZAP JSON report; the scan result is unknown."


class ReportError(ValueError):
    """Raised when the ZAP JSON report is absent, unreadable or unrecognised."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReportError(_INVALID)
        result[key] = value
    return result


def _reject_nonfinite_constant(value: str) -> NoReturn:
    raise ReportError(_INVALID)


def _risk_of(alert: dict[str, Any]) -> int:
    riskcode = alert.get("riskcode")
    if not isinstance(riskcode, str) or riskcode not in _RISKCODES:
        raise ReportError(_INVALID)
    return _RISKCODES[riskcode]


def _rule_id_of(alert: dict[str, Any]) -> str:
    plugin_id = alert.get("pluginid")
    if not isinstance(plugin_id, str) or _PLUGIN_ID.fullmatch(plugin_id) is None:
        raise ReportError(_INVALID)
    return plugin_id


def parse_alerts(text: str) -> list[tuple[int, str]]:
    """Return ``(riskcode, rule id)`` for every alert of a valid ZAP JSON report.

    A report without a ``site`` list is rejected, while a valid report whose site
    list is empty (or whose sites hold no alerts) yields no alerts.
    """

    try:
        document = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite_constant,
        )
    except (json.JSONDecodeError, RecursionError) as error:
        raise ReportError(_INVALID) from error
    if not isinstance(document, dict):
        raise ReportError(_INVALID)
    sites = document.get("site")
    if not isinstance(sites, list):
        raise ReportError(_INVALID)

    alerts: list[tuple[int, str]] = []
    for site in sites:
        if not isinstance(site, dict):
            raise ReportError(_INVALID)
        site_alerts = site.get("alerts")
        if not isinstance(site_alerts, list):
            raise ReportError(_INVALID)
        for alert in site_alerts:
            if not isinstance(alert, dict):
                raise ReportError(_INVALID)
            alerts.append((_risk_of(alert), _rule_id_of(alert)))
    return alerts


def read_alerts(report_path: Path) -> list[tuple[int, str]]:
    """Read the report as one bounded regular file and parse its alerts."""

    if report_path.is_symlink():
        raise ReportError(_NOT_REGULAR)
    if not report_path.exists():
        raise ReportError(_MISSING)
    if not report_path.is_file():
        raise ReportError(_NOT_REGULAR)
    try:
        with report_path.open("rb") as handle:
            payload = handle.read(MAX_REPORT_BYTES + 1)
    except OSError as error:
        raise ReportError(_UNREADABLE) from error
    if len(payload) > MAX_REPORT_BYTES:
        raise ReportError(_OVERSIZED)
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ReportError(_INVALID) from error
    return parse_alerts(text)


def _write_summary(summary_path: Path | None, lines: list[str]) -> None:
    if summary_path is None:
        return
    with summary_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")


def run_gate(report_path: Path, summary_path: Path | None) -> int:
    """Validate the report, publish a summary, and return the exit status."""

    try:
        alerts = read_alerts(report_path)
    except ReportError as error:
        print(f"::error::{error}", file=sys.stderr)
        return 1

    counts = Counter(risk for risk, _ in alerts)
    blocking_rules = sorted(
        {rule for risk, rule in alerts if risk >= BLOCKING_RISKCODE}, key=int
    )
    blocking = sum(count for risk, count in counts.items() if risk >= BLOCKING_RISKCODE)
    summary = [
        "### ZAP DAST findings",
        "",
        "| Risk | Alerts | Blocks the job |",
        "| --- | ---: | --- |",
    ]
    for riskcode in (3, 2, 1, 0):
        summary.append(
            f"| {RISK_NAMES[riskcode]} | {counts[riskcode]} | "
            f"{'yes' if riskcode >= BLOCKING_RISKCODE else 'no'} |"
        )
    _write_summary(summary_path, summary)

    if blocking:
        print(
            f"::error::ZAP reported {blocking} medium or high alert(s); "
            f"rule ids: {', '.join(blocking_rules)}.",
            file=sys.stderr,
        )
        return 1
    print("ZAP reported no medium or high alerts.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("report", type=Path, help="ZAP JSON report (zap-full-scan -J)")
    parser.add_argument(
        "--summary-file",
        type=Path,
        default=None,
        help="Markdown job summary file to append to (for GITHUB_STEP_SUMMARY)",
    )
    arguments = parser.parse_args(argv)
    return run_gate(arguments.report, arguments.summary_file)


if __name__ == "__main__":
    raise SystemExit(main())
