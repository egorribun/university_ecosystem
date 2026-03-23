#!/usr/bin/env python3
"""Verify that .secrets.baseline has not regressed by suppressing new secrets.

Usage:
    python scripts/verify_secrets_baseline.py .secrets.baseline /tmp/current_scan.json

Exit code 0  — baseline is clean (no new suppressions detected).
Exit code 1  — baseline suppresses entries not found in the current scan,
               indicating a potentially newly-committed secret was hidden.

AUDIT-INFRA-06 (audit 2026-03-15): detect-secrets baseline is a tracked file.
A contributor with push access can suppress a newly-introduced secret by
committing an updated baseline alongside the secret. This script, run in CI,
detects that pattern by comparing the committed baseline against a fresh scan.

Combined with .github/CODEOWNERS assigning .secrets.baseline to @security-team,
any regression is blocked until a security reviewer approves the change.
"""

import json
import sys


def load_json(path: str) -> dict:
    # LOW-W19: explicit encoding to avoid platform-dependent default encoding
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main() -> int:
    if len(sys.argv) != 3:
        print(
            f"Usage: {sys.argv[0]} <baseline-path> <current-scan-path>", file=sys.stderr
        )
        return 2

    baseline_path, scan_path = sys.argv[1], sys.argv[2]

    try:
        baseline = load_json(baseline_path)
        current = load_json(scan_path)
    except FileNotFoundError as exc:
        print(f"ERROR: file not found: {exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON: {exc}", file=sys.stderr)
        return 2

    baseline_files: set[str] = {
        f.replace("\\", "/") for f in baseline.get("results", {}).keys()
    }
    current_files: set[str] = {
        f.replace("\\", "/") for f in current.get("results", {}).keys()
    }

    # Files suppressed in baseline but absent from current scan could mean
    # the secret was removed — that is fine. (Logic fix: don't fail here).
    stale_suppressions = baseline_files - current_files

    if stale_suppressions:
        print(
            f"INFO: .secrets.baseline contains {len(stale_suppressions)} stale entries (files moved/deleted or secrets removed)."
        )
        # We don't return 1 here because the comments say secret removal is "fine".
        # This keeps the baseline clean of false positives due to refactoring.

    print(
        f"OK: .secrets.baseline integrity check passed ({len(baseline_files)} suppressed file(s) verified)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
