"""Convert private ZAP JSON into a minimal, privacy-safe SARIF report.

This is a converter, not scan-completion or coverage evidence. Call it only
with the outcome of the actual scan step, then validate provenance separately.
Only numeric ZAP rule identifiers and risk levels leave the private report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any

from scripts.quality.zap_findings_gate import (
    MAX_REPORT_BYTES,
    ReportError,
    parse_alerts,
)

_ERROR = "Could not produce privacy-safe ZAP SARIF."
_LEVELS = {0: "note", 1: "note", 2: "warning", 3: "error"}
_SCORES = {0: "0.0", 1: "2.0", 2: "5.0", 3: "8.0"}


def read_payload(source: Path) -> bytes:
    """Read a bounded regular file through a non-following descriptor."""
    descriptor = os.open(source, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ReportError(_ERROR)
        payload = handle.read(MAX_REPORT_BYTES + 1)
    if len(payload) > MAX_REPORT_BYTES:
        raise ReportError(_ERROR)
    return payload


def build_report(payload: bytes) -> tuple[dict[str, Any], str, list[tuple[int, str]]]:
    """Derive all public values and gate inputs from exactly these report bytes."""
    text = payload.decode("utf-8")
    # Shared parser rejects duplicate keys, nonfinite values and invalid alerts.
    alerts = parse_alerts(text)
    document = json.loads(text)
    version = document.get("@version")
    if (
        not isinstance(version, str)
        or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) is None
        or not document["site"]
    ):
        raise ReportError(_ERROR)
    # A ZAP plugin may legitimately emit alerts at different risks (e.g. CSP).
    # Split rule descriptors so each GitHub security-severity remains accurate.
    identities = sorted(set(alerts), key=lambda item: (int(item[1]), item[0], item[1]))
    rules = [
        {
            "id": f"{plugin_id}-risk-{risk}",
            "shortDescription": {"text": f"ZAP rule {plugin_id}; risk level {risk}"},
            "properties": {
                "tags": ["security"],
                "security-severity": _SCORES[risk],
                "zapPluginId": plugin_id,
                "zapRiskCode": risk,
            },
        }
        for risk, plugin_id in identities
    ]
    indices = {identity: index for index, identity in enumerate(identities)}
    evidence_lines = [
        f"{rule['id']}: dynamic finding; application source location unavailable."
        for rule in rules
    ]
    evidence_text = "\n".join(evidence_lines) + ("\n" if evidence_lines else "")
    results = [
        {
            "ruleId": f"{plugin_id}-risk-{risk}",
            "ruleIndex": indices[(risk, plugin_id)],
            "level": _LEVELS[risk],
            "message": {
                "text": f"ZAP rule {plugin_id}; risk level {risk}. Location identifies generated evidence, not application source."
            },
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {
                            "uri": "zap-evidence.txt",
                            "uriBaseId": "ZAP_OUTPUT",
                            "index": 0,
                        },
                        "region": {
                            "startLine": indices[(risk, plugin_id)] + 1,
                            "snippet": {
                                "text": evidence_lines[indices[(risk, plugin_id)]]
                            },
                        },
                    }
                }
            ],
        }
        for risk, plugin_id in alerts
    ]
    sarif: dict[str, Any] = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "OWASP ZAP",
                        "semanticVersion": version,
                        "rules": rules,
                    }
                },
                "results": results,
                "originalUriBaseIds": {
                    # SARIF 2.1.0 section 3.14.14 explicitly permits omitting
                    # the absolute URI for privacy and deterministic output.
                    "ZAP_OUTPUT": {
                        "description": {
                            "text": "Directory containing the generated sanitized ZAP evidence. Absolute filesystem location withheld."
                        },
                    },
                },
                "artifacts": [
                    {
                        "location": {
                            "uri": "zap-evidence.txt",
                            "uriBaseId": "ZAP_OUTPUT",
                        },
                        "roles": ["resultFile"],
                        "mimeType": "text/plain",
                        "contents": {"text": evidence_text},
                    }
                ],
                "properties": {
                    "sourceReportSha256": hashlib.sha256(payload).hexdigest()
                },
            }
        ],
    }
    return sarif, evidence_text, alerts


def produce(source: Path, destination: Path, outcome: str) -> None:
    """Create a fresh SARIF file without publishing raw scanner-controlled text."""
    if outcome != "success":
        raise ReportError(_ERROR)
    produce_payload(read_payload(source), destination)


def produce_payload(payload: bytes, destination: Path) -> None:
    """Produce from an immutable verified snapshot without reopening its source."""
    sarif, evidence_text, _ = build_report(payload)
    encoded = (json.dumps(sarif, indent=2, sort_keys=True) + "\n").encode("utf-8")
    evidence_path = destination.with_name("zap-evidence.txt")
    # Create both outputs exclusively. Failed publication leaves neither new
    # artifact behind and never modifies a pre-existing file or symlink.
    created: list[Path] = []
    try:
        for path, data in (
            (evidence_path, evidence_text.encode("utf-8")),
            (destination, encoded),
        ):
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created.append(path)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
    except OSError:
        for path in created:
            path.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json-in", type=Path, required=True)
    parser.add_argument("--sarif-out", type=Path, required=True)
    parser.add_argument("--scan-outcome", required=True)
    args = parser.parse_args(argv)
    try:
        produce(args.json_in, args.sarif_out, args.scan_outcome)
    except (OSError, UnicodeError, ValueError, RecursionError):
        print(f"::error::{_ERROR}", file=sys.stderr)
        return 1
    print("Privacy-safe ZAP SARIF produced; scan coverage is not asserted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
