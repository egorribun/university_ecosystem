"""Fail-closed command-line adapter for Lighthouse retry evidence selection.

The selector itself validates downloaded artifacts.  This adapter deliberately
does not accept a serialized retry-context argument: it derives the context
from the current trusted repository HEAD and explicitly named configuration
and policy inputs immediately before invoking the selector.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from scripts.quality.coverage_retry_context import (
    RetryContextError,
    build_consumer_retry_context,
)
from scripts.quality.select_lighthouse_artifacts import (
    LIGHTHOUSE_LOGICAL_ARTIFACT,
    LighthouseSelectionError,
    select_lighthouse_artifacts,
)


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--candidate-root", type=Path, action="append", required=True)
    parser.add_argument("--destination-root", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--workflow-ref", required=True)
    parser.add_argument("--workflow-sha", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--consumer-job", required=True)
    parser.add_argument("--config-input", type=Path, action="append", required=True)
    parser.add_argument("--policy-input", type=Path, action="append", required=True)
    return parser.parse_args(argv)


def _repository_path(repository_root: Path, value: Path) -> Path:
    """Resolve CLI artifact paths from the explicitly declared repository root."""

    if value.is_absolute():
        return value
    return repository_root / value


def _select(arguments: argparse.Namespace) -> dict[str, object]:
    context = build_consumer_retry_context(
        repository_root=arguments.repository_root,
        config_inputs=arguments.config_input,
        policy_inputs=arguments.policy_input,
        repository=arguments.repository,
        run_id=arguments.run_id,
        workflow_ref=arguments.workflow_ref,
        workflow_sha=arguments.workflow_sha,
        event=arguments.event,
    )
    result = select_lighthouse_artifacts(
        repository_root=arguments.repository_root,
        candidate_roots=tuple(
            _repository_path(arguments.repository_root, candidate)
            for candidate in arguments.candidate_root
        ),
        destination_root=_repository_path(
            arguments.repository_root, arguments.destination_root
        ),
        expected_sha=context["source_sha"],
        expected_repository=context["repository"],
        expected_run_id=context["run_id"],
        expected_run_attempt=arguments.run_attempt,
        expected_workflow_ref=context["workflow_ref"],
        expected_workflow_sha=context["workflow_sha"],
        expected_event=context["event"],
        expected_consumer_job=arguments.consumer_job,
        consumer_retry_context=context,
    )
    return {
        "artifact": LIGHTHOUSE_LOGICAL_ARTIFACT,
        "consumer_job": arguments.consumer_job,
        "physical_artifact": result.selection.physical_artifact,
        "producer_attempt": result.selection.producer_attempt,
        "receipt_path": str(result.receipt_path),
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Select verified Lighthouse evidence and emit a compact JSON summary."""

    arguments = _arguments(argv)
    try:
        payload = _select(arguments)
    except (LighthouseSelectionError, OSError, RetryContextError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
