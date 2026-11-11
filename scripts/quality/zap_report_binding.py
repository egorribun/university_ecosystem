"""Verify ZAP JSON/SARIF/evidence agreement, optionally enforcing its threshold.

Run verification before publishing, and enforce the threshold after uploads.
This validates report consistency, not scan execution or origin. The workflow
must separately establish current-run source and scan-completion provenance.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.quality.zap_findings_gate import (
    ReportError,
    _reject_duplicate_keys,
    _reject_nonfinite_constant,
    evaluate_alerts,
)
from scripts.quality.zap_sarif_producer import build_report, read_payload


def verify(source: Path, sarif: Path, outcome: str) -> list[tuple[int, str]]:
    """Return gate inputs from the same immutable bytes verified against SARIF."""
    if outcome != "success":
        raise ReportError("ZAP scan did not succeed")
    return verify_payload(read_payload(source), sarif)


def verify_payload(payload: bytes, sarif: Path) -> list[tuple[int, str]]:
    """Bind public output directly to verified bytes, never rereading raw JSON."""
    expected, evidence, alerts = build_report(payload)
    actual = json.loads(
        read_payload(sarif).decode("utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_nonfinite_constant,
    )
    # Exact projection comparison rejects omitted alerts, changed severity,
    # arbitrary scanner text, and even semantically equivalent changed raw bytes.
    # Compare serialized values so JSON false cannot compare equal to index 0.
    if json.dumps(actual, sort_keys=True) != json.dumps(expected, sort_keys=True):
        raise ReportError("ZAP JSON and SARIF disagree")
    if read_payload(sarif.with_name("zap-evidence.txt")) != evidence.encode("utf-8"):
        raise ReportError("ZAP evidence and SARIF disagree")
    return alerts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json-in", type=Path, required=True)
    parser.add_argument("--sarif-in", type=Path, required=True)
    parser.add_argument("--scan-outcome", required=True)
    parser.add_argument("--enforce-threshold", action="store_true")
    parser.add_argument("--summary-file", type=Path)
    args = parser.parse_args(argv)
    try:
        alerts = verify(args.json_in, args.sarif_in, args.scan_outcome)
        if args.enforce_threshold:
            return evaluate_alerts(alerts, args.summary_file)
    except (OSError, UnicodeError, ValueError, RecursionError):
        print("::error::Could not verify ZAP report agreement.", file=sys.stderr)
        return 1
    print("ZAP report agreement verified; finding threshold not evaluated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
