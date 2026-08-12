#!/usr/bin/env python3
"""Fail-closed compatibility entrypoint for the retired mutmut diff helper."""

from __future__ import annotations

import sys


def main() -> int:
    """Explain the supported mutation gates without silently skipping quality work."""
    print(
        "ERROR: scripts/run_mutmut_diff.py is deprecated and intentionally does "
        "not run a mutation gate. Use the CI-supported "
        "scripts/export_mutmut_shard_stats.py with an exact shard or --all, then "
        "scripts/mutmut_ci_gate.py (or scripts/check_mutation_score.py).",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
