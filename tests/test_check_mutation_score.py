from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _checker_path() -> Path:
    """Locate the checker both in a normal checkout and mutmut isolation."""
    candidates = [
        Path.cwd() / "scripts" / "check_mutation_score.py",
        ROOT / "scripts" / "check_mutation_score.py",
    ]
    candidates.extend(
        parent / "scripts" / "check_mutation_score.py"
        for parent in Path(__file__).resolve().parents
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise AssertionError("scripts/check_mutation_score.py is not available")


def _load_checker():
    path = _checker_path()
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


def test_parser_accepts_mutmut_cicd_stats_json() -> None:
    checker = _load_checker()
    summary = checker._parse_cicd_stats(
        json.dumps(
            {
                "killed": 17,
                "survived": 3,
                "total": 24,
                "no_tests": 2,
                "skipped": 1,
                "suspicious": 1,
                "timeout": 0,
                "check_was_interrupted_by_user": 0,
                "segfault": 0,
                "caught_by_type_check": 0,
            }
        )
    )

    assert summary.killed == 17
    assert summary.survived == 3
    assert summary.no_tests == 2
    assert summary.suspicious == 1
    assert summary.not_checked == 0
    assert summary.score == 17 / 20 * 100
