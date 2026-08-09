from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts import mutmut_incremental, run_mutmut_diff

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("script_name", "entrypoint"),
    (
        ("run_mutmut_diff.py", run_mutmut_diff.main),
        ("mutmut_incremental.py", mutmut_incremental.main),
    ),
)
def test_legacy_mutmut_entrypoints_fail_closed_and_name_supported_commands(
    script_name: str,
    entrypoint: object,
) -> None:
    assert callable(entrypoint)
    assert entrypoint() == 2

    result = subprocess.run(  # noqa: S603 - test invokes a fixed local script path.
        [sys.executable, str(ROOT / "scripts" / script_name)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=15,
        check=False,
    )

    assert result.returncode == 2
    assert "deprecated" in result.stderr.lower()
    assert "scripts/mutmut_ci_gate.py" in result.stderr
    assert "scripts/export_mutmut_shard_stats.py" in result.stderr
