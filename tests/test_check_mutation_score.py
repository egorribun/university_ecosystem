from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

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
            "    app.seven__mutmut_1: skipped",
            "    app.eight__mutmut_1: check was interrupted by user",
            "    app.nine__mutmut_1: segfault",
            "    app.ten__mutmut_1: caught by type check",
        )
    )

    summary = checker._parse_mutmut_output(output)

    assert summary.killed == 1
    assert summary.survived == 1
    assert summary.no_tests == 1
    assert summary.not_checked == 1
    assert summary.timeout == 1
    assert summary.suspicious == 1
    assert summary.skipped == 1
    assert summary.interrupted == 1
    assert summary.segfault == 1
    assert summary.caught_by_type_check == 1
    assert summary.total_meaningful == 3
    assert summary.score == 2 / 3 * 100


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
    assert summary.skipped == 1
    assert summary.interrupted == 0
    assert summary.segfault == 0
    assert summary.caught_by_type_check == 0
    assert summary.not_checked == 0
    assert summary.score == 17 / 20 * 100


def test_default_score_gate_requires_all_viable_mutants_to_be_killed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = _load_checker()
    monkeypatch.setattr(
        checker,
        "_load_cicd_stats",
        lambda: checker.MutationSummary(
            killed=99,
            survived=1,
            timeout=0,
            suspicious=0,
            no_tests=0,
            not_checked=0,
        ),
    )

    with pytest.raises(SystemExit) as error:
        checker.main([])

    assert error.value.code == 1


def test_default_score_gate_accepts_all_killed_viable_mutants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = _load_checker()
    monkeypatch.setattr(
        checker,
        "_load_cicd_stats",
        lambda: checker.MutationSummary(
            killed=100,
            survived=0,
            timeout=0,
            suspicious=0,
            no_tests=0,
            not_checked=0,
        ),
    )

    assert checker.main([]) is None


@pytest.mark.parametrize(
    "status",
    (
        "timeout",
        "suspicious",
        "no_tests",
        "not_checked",
        "skipped",
        "interrupted",
        "segfault",
    ),
)
def test_default_score_gate_fails_closed_on_unresolved_mutation_status(
    monkeypatch: pytest.MonkeyPatch,
    status: str,
) -> None:
    checker = _load_checker()
    values = {
        "killed": 1,
        "survived": 0,
        "timeout": 0,
        "suspicious": 0,
        "no_tests": 0,
        "not_checked": 0,
        "skipped": 0,
        "interrupted": 0,
        "segfault": 0,
        "caught_by_type_check": 0,
    }
    values[status] = 1
    monkeypatch.setattr(
        checker,
        "_load_cicd_stats",
        lambda: checker.MutationSummary(**values),
    )

    with pytest.raises(SystemExit) as error:
        checker.main([])

    assert error.value.code == 1


def test_default_score_gate_accepts_type_check_kill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = _load_checker()
    monkeypatch.setattr(
        checker,
        "_load_cicd_stats",
        lambda: checker.MutationSummary(
            killed=0,
            survived=0,
            timeout=0,
            suspicious=0,
            no_tests=0,
            not_checked=0,
            caught_by_type_check=1,
        ),
    )

    assert checker.main([]) is None


def test_default_score_gate_rejects_an_empty_mutation_universe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = _load_checker()
    monkeypatch.setattr(
        checker,
        "_load_cicd_stats",
        lambda: checker.MutationSummary(
            killed=0,
            survived=0,
            timeout=0,
            suspicious=0,
            no_tests=0,
            not_checked=0,
        ),
    )

    with pytest.raises(SystemExit) as error:
        checker.main([])

    assert error.value.code == 1


def test_unclassified_exported_mutant_is_not_checked_and_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = _load_checker()
    summary = checker._parse_cicd_stats(
        {
            "killed": 1,
            "survived": 0,
            "total": 2,
            "no_tests": 0,
            "skipped": 0,
            "suspicious": 0,
            "timeout": 0,
            "check_was_interrupted_by_user": 0,
            "segfault": 0,
            "caught_by_type_check": 0,
        }
    )
    assert summary.not_checked == 1
    monkeypatch.setattr(checker, "_load_cicd_stats", lambda: summary)

    with pytest.raises(SystemExit) as error:
        checker.main([])

    assert error.value.code == 1
