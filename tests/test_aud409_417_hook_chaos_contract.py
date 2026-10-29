"""Behavioral regression for the stop gate's limited success claim."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parents[1] / ".agents" / "hooks"
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

stop_gate = importlib.import_module("stop_quality_gate")


def test_stop_success_reports_only_configured_checks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Do not describe successful lint/type/vet checks as a full test run."""
    monkeypatch.setattr(stop_gate, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(stop_gate, "check_gate_state_errors", lambda: (True, ""))
    for name in (
        "check_python_subsystem",
        "check_frontend_subsystem",
        "check_services_subsystem",
    ):
        monkeypatch.setattr(stop_gate, name, lambda _root: (True, ""))

    assert stop_gate.evaluate_stop({}) == {
        "decision": "allow",
        "reason": (
            "All configured stop checks passed (Python Ruff, frontend TypeScript, "
            "and Go vet for every workspace module)."
        ),
    }
