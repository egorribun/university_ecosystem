"""Keep generated Pact artifacts separate from checked-in contract snapshots."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def pact_output_dir(
    pytestconfig: pytest.Config, tmp_path_factory: pytest.TempPathFactory
) -> Path:
    """Merge module pacts only within this run's fresh artifact directory.

    Ordinary runs, including xdist workers, use their own temporary directory.
    CI explicitly publishes with PACT_OUTPUT_DIR and ``-n 0``. Requiring a new
    destination prevents stale interactions and concurrent publishers from
    silently contaminating the provider artifact.
    """
    destination = os.environ.get("PACT_OUTPUT_DIR")
    if not destination:
        return tmp_path_factory.mktemp("pacts")
    if hasattr(pytestconfig, "workerinput"):
        raise pytest.UsageError("PACT_OUTPUT_DIR requires serial pytest (-n 0)")
    output = Path(destination).resolve()
    try:
        output.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise pytest.UsageError("PACT_OUTPUT_DIR must not already exist") from exc
    return output
