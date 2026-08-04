from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_checker():
    path = ROOT / "scripts" / "check_mutation_score.py"
    spec = importlib.util.spec_from_file_location("check_mutation_score", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parser_counts_complete_mutmut_status_stream() -> None:
    checker = _load_checker()
    output = "\n".join(
        (
            "    app.one__mutmut_1: killed",
            "    app.two__mutmut_1: survived",
            "    app.three__mutmut_1: no tests",
            "    app.four__mutmut_1: timed out",
            "    app.five__mutmut_1: suspicious",
            "    app.six__mutmut_1: not checked",
        )
    )

    summary = checker._parse_mutmut_output(output)

    assert summary.killed == 1
    assert summary.survived == 1
    assert summary.no_tests == 1
    assert summary.not_checked == 1
    assert summary.timeout == 1
    assert summary.suspicious == 1
    assert summary.score == 50.0


def test_runner_requests_all_statuses(monkeypatch) -> None:
    checker = _load_checker()
    calls: list[list[str]] = []

    class Completed:
        returncode = 0
        stdout = "status output"
        stderr = ""

    monkeypatch.setattr(
        shutil, "which", lambda name: "uv.exe" if name == "uv" else None
    )
    monkeypatch.setattr(
        checker.subprocess,
        "run",
        lambda command, **_kwargs: calls.append(command) or Completed(),
    )

    assert checker._run_mutmut() == "status output"
    assert calls == [["uv.exe", "run", "mutmut", "results", "--all"]]
