"""Bound native-lock contention scenarios independently of their event loop."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable

_SCENARIO_DEADLINE_SECONDS = 5
_RUN_SCENARIO = """
import sys


def _phase(value):
    try:
        print("CIRCUIT_CHILD_PHASE=" + value, file=sys.stderr, flush=True)
    except Exception:
        return


_phase("child_started")
import importlib
import pytest

scenario = getattr(importlib.import_module(sys.argv[1]), sys.argv[2])
_phase("imports_ready")
with pytest.MonkeyPatch.context() as monkeypatch:
    if sys.argv[3] == "monkeypatch":
        scenario(monkeypatch)
    else:
        scenario()
    _phase("scenario_returned")
_phase("cleanup_returned")
"""


def assert_circuit_scenario_completes(
    scenario: Callable[..., None], *, with_monkeypatch: bool = False
) -> None:
    """Run the identical body before inline coverage can encounter a native stall.

    An asyncio deadline cannot fire when a native lock blocks its event loop.
    This parent observes the whole scenario, including cancellation and cleanup.
    ``subprocess.run`` kills and waits for only its owned child on expiry. The
    scenario starts no other processes; any worker threads die with that child.
    Its normal runtime is well below the five-second responsiveness deadline.
    """
    try:
        completed = subprocess.run(  # noqa: S603 - current interpreter and repository-owned scenario, without a shell
            [
                sys.executable,
                "-c",
                _RUN_SCENARIO,
                scenario.__module__,
                scenario.__name__,
                "monkeypatch" if with_monkeypatch else "none",
            ],
            capture_output=True,
            text=True,
            timeout=_SCENARIO_DEADLINE_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise AssertionError(
            f"Circuit contention scenario {scenario.__name__} did not finish "
            f"within {_SCENARIO_DEADLINE_SECONDS}s across child startup, imports, "
            f"scenario and shutdown. Owned child was killed and reaped. "
            f"stdout={error.stdout!r}; stderr={error.stderr!r}"
        ) from error
    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    assert completed.returncode == 0, (
        f"Circuit contention scenario {scenario.__name__} exited "
        f"{completed.returncode}.\n"
        f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )
