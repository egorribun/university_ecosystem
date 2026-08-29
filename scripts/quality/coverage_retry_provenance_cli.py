"""Emit fail-closed producer retry provenance for a repository-owned CI step.

The output is deliberately line-delimited ``KEY=VALUE`` data rather than a
shell fragment.  A workflow must read it into a Bash array and pass every
member as a separately quoted ``--retry-provenance`` argument to
``coverage_provenance.py write``.  This keeps provenance derivation in trusted
repository code while preventing a workflow input from becoming executable
shell syntax.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from scripts.quality.coverage_retry_context import (
    RETRY_PROVENANCE_FIELDS,
    RetryContextError,
    build_retry_provenance,
)


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--config-input", type=Path, action="append", required=True)
    parser.add_argument("--policy-input", type=Path, action="append", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--workflow-ref", required=True)
    parser.add_argument("--workflow-sha", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--artifact", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Build current-run provenance and emit one non-executable member per line."""

    arguments = _arguments(argv)
    try:
        provenance = build_retry_provenance(
            repository_root=arguments.repository_root,
            config_inputs=arguments.config_input,
            policy_inputs=arguments.policy_input,
            repository=arguments.repository,
            run_id=arguments.run_id,
            run_attempt=arguments.run_attempt,
            workflow_ref=arguments.workflow_ref,
            workflow_sha=arguments.workflow_sha,
            event=arguments.event,
            artifact=arguments.artifact,
        )
    except (OSError, RetryContextError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    for field in sorted(RETRY_PROVENANCE_FIELDS):
        print(f"{field}={provenance[field]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
