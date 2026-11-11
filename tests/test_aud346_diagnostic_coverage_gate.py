"""Strict helper/checker coverage contracts; all mutations stay in temp copies."""

from __future__ import annotations

import copy
import json
import re
import runpy
import sys
from pathlib import Path

import pytest
import yaml
from coverage.parser import PythonParser

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.quality import verify_aud346_diagnostic_coverage as gate


def complete_report() -> dict:
    files = {}
    total_lines = total_branches = 0
    for source in gate.SOURCES:
        parser = PythonParser(filename=str(ROOT / source))
        parser.parse_source()
        lines = sorted(parser.statements)
        counts = parser.exit_counts()
        branches = sorted([a, b] for a, b in parser.arcs() if counts.get(a, 0) > 1)
        summary = {
            "covered_lines": len(lines),
            "num_statements": len(lines),
            "missing_lines": 0,
            "excluded_lines": 0,
            "covered_branches": len(branches),
            "num_branches": len(branches),
            "missing_branches": 0,
            "num_partial_branches": 0,
        }
        files[source] = {
            "executed_lines": lines,
            "executed_branches": branches,
            "missing_lines": [],
            "missing_branches": [],
            "excluded_lines": [],
            "summary": summary,
        }
        total_lines += len(lines)
        total_branches += len(branches)
    totals = copy.deepcopy(summary)
    totals.update(
        covered_lines=total_lines,
        num_statements=total_lines,
        covered_branches=total_branches,
        num_branches=total_branches,
    )
    return {"meta": {"branch_coverage": True}, "files": files, "totals": totals}


def write_report(tmp_path: Path, value: object) -> Path:
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(value))
    return path


def test_current_canonical_sources_and_cli(tmp_path, monkeypatch, capsys):
    assert Path(gate.__file__).resolve() == ROOT / gate.SOURCES[1]
    from scripts.chaos import aud346_failure_diagnostics

    assert Path(aud346_failure_diagnostics.__file__).resolve() == ROOT / gate.SOURCES[0]
    path = write_report(tmp_path, complete_report())
    gate.verify(path)
    monkeypatch.setattr(sys, "argv", [gate.SOURCES[1], str(path)])
    runpy.run_path(str(ROOT / gate.SOURCES[1]), run_name="__main__")
    assert capsys.readouterr().out.count("100%") == 2


@pytest.mark.parametrize("value", [None, [], 0])
def test_non_object_root(tmp_path, value):
    with pytest.raises(ValueError, match="root"):
        gate.verify(write_report(tmp_path, value))


@pytest.mark.parametrize(
    "field,value",
    [
        ("meta", {}),
        ("files", None),
        ("files", {}),
        ("files", {"scripts/chaos/wrong.py": {}}),
        ("totals", None),
    ],
)
def test_document_negatives(tmp_path, field, value):
    report = complete_report()
    report[field] = value
    with pytest.raises(ValueError):
        gate.verify(write_report(tmp_path, report))


@pytest.mark.parametrize(
    "field,value",
    [
        ("missing_lines", [1]),
        ("missing_branches", [[1, 2]]),
        ("excluded_lines", [1]),
        ("executed_lines", []),
        ("executed_branches", []),
        ("summary", None),
    ],
)
def test_record_negatives(tmp_path, field, value):
    report = complete_report()
    report["files"][gate.SOURCES[0]][field] = value
    with pytest.raises(ValueError):
        gate.verify(write_report(tmp_path, report))


@pytest.mark.parametrize("field", ["executed_lines", "executed_branches"])
def test_noninteger_source_inventory(tmp_path, field):
    report = complete_report()
    values = report["files"][gate.SOURCES[0]][field]
    if field == "executed_lines":
        values[0] = float(values[0])
    else:
        values[0][0] = float(values[0][0])
    with pytest.raises(ValueError, match="inventory"):
        gate.verify(write_report(tmp_path, report))


def test_invalid_record(tmp_path):
    report = complete_report()
    report["files"][gate.SOURCES[0]] = []
    with pytest.raises(ValueError, match="record"):
        gate.verify(write_report(tmp_path, report))


@pytest.mark.parametrize("value", [False, "111", None, -1, 0, 999])
def test_invalid_exact_count(tmp_path, value):
    report = complete_report()
    report["files"][gate.SOURCES[0]]["summary"]["covered_lines"] = value
    with pytest.raises(ValueError):
        gate.verify(write_report(tmp_path, report))


def test_duplicate_json_key(tmp_path):
    path = tmp_path / "coverage.json"
    path.write_text('{"files":{},"files":{}}')
    with pytest.raises(ValueError, match="duplicate"):
        gate.verify(path)


@pytest.mark.parametrize("text", ["", "x = 1\n"])
def test_empty_denominator(tmp_path, monkeypatch, text):
    report = complete_report()
    root = tmp_path / "root"
    path = root / gate.SOURCES[0]
    path.parent.mkdir(parents=True)
    path.write_text(text)
    monkeypatch.setattr(gate, "ROOT", root)
    with pytest.raises(ValueError, match="denominator"):
        gate.verify(write_report(tmp_path, report))


def test_noncanonical_source(tmp_path, monkeypatch):
    report = complete_report()
    root = tmp_path / "root"
    path = root / gate.SOURCES[0]
    path.parent.mkdir(parents=True)
    path.symlink_to(ROOT / gate.SOURCES[0])
    monkeypatch.setattr(gate, "ROOT", root)
    with pytest.raises(ValueError, match="canonical"):
        gate.verify(write_report(tmp_path, report))


COVERAGE_STEP = "Verify AUD-346 diagnostic helper coverage"
NEGATIVE_MARKER = "# Exercise the configured gate against isolated negative controls."


def assert_blocking_graph(workflow: dict) -> None:
    jobs = workflow["jobs"]
    prerequisite = jobs["aud346-diagnostic-coverage"]
    contract = jobs["contract-tests"]
    finalizer = jobs["ci-success"]
    assert prerequisite.get("needs", []) == []
    assert "if" not in prerequisite
    assert "continue-on-error" not in prerequisite
    assert prerequisite["timeout-minutes"] == 5
    assert contract["name"] == "Contract Tests"
    assert contract["timeout-minutes"] == 10
    assert contract["needs"] == ["aud346-diagnostic-coverage"]
    # No explicit job condition may override GitHub's default success() on
    # completed dependencies. Failed/cancelled/skipped prerequisites cannot
    # dispatch this job; unfinished dependencies cannot make it successful.
    assert "if" not in contract
    assert "continue-on-error" not in contract
    assert all(step["name"] != COVERAGE_STEP for step in contract["steps"])
    assert finalizer["if"] == "${{ always() }}"
    assert "contract-tests" in finalizer["needs"]
    check = next(s for s in finalizer["steps"] if s["name"] == "Check all jobs passed")
    assert "'contract-tests|${{ needs.contract-tests.result }}'" in check["run"]


def test_blocking_graph_has_default_success_dependency_and_strict_finalizer():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    assert_blocking_graph(workflow)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_need",
        "conditional_bypass",
        "continue_on_error",
        "conditional_prerequisite",
        "optional_prerequisite",
        "old_budget",
        "new_budget",
        "finalizer_skip",
        "missing_finalizer_need",
        "missing_result_check",
    ],
)
def test_blocking_graph_rejects_weakened_wiring(mutation):
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    jobs = workflow["jobs"]
    if mutation == "missing_need":
        jobs["contract-tests"]["needs"] = []
    elif mutation == "conditional_bypass":
        jobs["contract-tests"]["if"] = "${{ always() }}"
    elif mutation == "continue_on_error":
        jobs["contract-tests"]["continue-on-error"] = True
    elif mutation == "conditional_prerequisite":
        jobs["aud346-diagnostic-coverage"]["if"] = "${{ false }}"
    elif mutation == "optional_prerequisite":
        jobs["aud346-diagnostic-coverage"]["continue-on-error"] = True
    elif mutation == "old_budget":
        jobs["contract-tests"]["timeout-minutes"] = 11
    elif mutation == "new_budget":
        jobs["aud346-diagnostic-coverage"]["timeout-minutes"] = 2
    elif mutation == "finalizer_skip":
        jobs["ci-success"]["if"] = "${{ success() }}"
    elif mutation == "missing_finalizer_need":
        jobs["ci-success"]["needs"].remove("contract-tests")
    else:
        step = next(
            s
            for s in jobs["ci-success"]["steps"]
            if s["name"] == "Check all jobs passed"
        )
        step["run"] = step["run"].replace(
            "'contract-tests|${{ needs.contract-tests.result }}'", ""
        )
    with pytest.raises(AssertionError):
        assert_blocking_graph(workflow)


@pytest.mark.parametrize(
    "contract_result",
    [
        "success",
        "failure",
        "cancelled",
        "skipped",
        "",
        "queued",
        "in_progress",
        "unknown",
    ],
)
def test_actual_ci_success_gate_requires_successful_contract_job(contract_result):
    import os
    import subprocess

    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    assert_blocking_graph(workflow)
    finalizer = workflow["jobs"]["ci-success"]
    step = next(s for s in finalizer["steps"] if s["name"] == "Check all jobs passed")
    # Execute the actual aggregate shell, substituting only the runner's
    # expression context. No second status evaluator or scheduler is invented.
    values = {name: "success" for name in finalizer["needs"]}
    values.update({"contract-tests": contract_result, "codecov-upload": "skipped"})
    context = {f"needs.{name}.result": result for name, result in values.items()}
    context.update(
        {
            "github.event_name": "pull_request",
            "github.ref": "refs/pull/1380/merge",
            "github.base_ref": "main",
        }
    )

    def substitute(text):
        return re.sub(
            r"\$\{\{\s*([^{}]+?)\s*\}\}", lambda match: context[match[1].strip()], text
        )

    script = substitute(step["run"])
    assert "${{" not in script
    environment = {
        **os.environ,
        **{key: substitute(value) for key, value in step["env"].items()},
    }
    result = subprocess.run(
        ["/bin/bash", "-s"],
        input=script,
        env=environment,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    if contract_result == "success":
        assert result.returncode == 0, result.stdout + result.stderr
        assert "All required CI checks passed." in result.stdout
    else:
        assert result.returncode != 0, result.stdout + result.stderr
        assert "Required CI job 'contract-tests'" in result.stdout
        assert "All required CI checks passed." not in result.stdout


def coverage_step() -> dict:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    assert_blocking_graph(workflow)
    job = workflow["jobs"]["aud346-diagnostic-coverage"]
    assert job["name"] == "AUD-346 Diagnostic Coverage"
    assert job["timeout-minutes"] == 5
    steps = job["steps"]
    step = next(item for item in steps if item["name"] == COVERAGE_STEP)
    assert (
        steps.index(step)
        == next(
            i for i, item in enumerate(steps) if item["name"] == "Install dependencies"
        )
        + 1
    )
    assert step["timeout-minutes"] == 2
    assert "if" not in step and "continue-on-error" not in step
    return step


def test_workflow_keeps_exact_supplemental_gate():
    run = coverage_step()["run"]
    assert run.startswith("set -euo pipefail\n")
    assert (
        "--source=scripts.chaos.aud346_failure_diagnostics,scripts.quality.verify_aud346_diagnostic_coverage"
        in run
    )
    assert 'export COVERAGE_FILE="$coverage_root/.coverage"' in run
    assert "-p pytest_asyncio.plugin" in run
    assert "tests/test_aud346_failure_diagnostics.py" in run
    assert "tests/test_aud346_diagnostic_coverage_gate.py" in run
    assert (
        'python scripts/quality/verify_aud346_diagnostic_coverage.py "$coverage_root/coverage.json"'
        in run
    )
    assert run.count(NEGATIVE_MARKER) == 1
    assert "::test_configured_gate_negatives" in run.split(NEGATIVE_MARKER)[1]
    assert "continue-on-error" not in run
    assert "||" not in run and "set +e" not in run
    assert "--fail-under=100" in run
    assert "--append" not in run and "coverage combine" not in run


@pytest.mark.parametrize(
    "mode", ["positive", "zero_data", "wrong_source", "uncovered_branch"]
)
def test_configured_gate_negatives(tmp_path, mode):
    import os
    import shutil
    import subprocess

    sandbox = tmp_path / "repo"
    sources = (
        *gate.SOURCES,
        "scripts/chaos/aud346_live_kind_proof.sh",
        "tests/test_aud346_failure_diagnostics.py",
        "tests/test_aud346_diagnostic_coverage_gate.py",
        ".github/workflows/ci.yml",
        "pyproject.toml",
    )
    for source in sources:
        target = sandbox / source
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / source, target)
    if mode == "uncovered_branch":
        helper = sandbox / gate.SOURCES[0]
        with helper.open("a") as stream:
            stream.write(
                "\n\ndef uncovered_gate_branch(value):\n    if value:\n        return 1\n    return 0\n"
            )
    # Run the actual checked-in workflow commands, not a second gate implementation.
    # Only the uv launcher is replaced: dependencies are already installed in this
    # interpreter, and these offline tests must never sync/install or use a network.
    binary = tmp_path / "bin"
    binary.mkdir()
    launcher = binary / "uv"
    launcher.write_text(
        f"#!{sys.executable}\nimport os, sys\n"
        "assert sys.argv[1:5] == ['run', '--frozen', '--no-sync', 'python']\n"
        "os.execv(sys.executable, [sys.executable, *sys.argv[5:]])\n"
    )
    launcher.chmod(0o700)
    run = coverage_step()["run"].split(NEGATIVE_MARKER)[0]
    selector = "--source=scripts.chaos.aud346_failure_diagnostics,scripts.quality.verify_aud346_diagnostic_coverage"
    if mode == "zero_data":
        run = run.replace(selector, "--source=aud346_nonexistent_source")
    elif mode == "wrong_source":
        run = run.replace(selector, "--source=scripts.chaos.aud346_failure_diagnostics")
    temporary = tmp_path / "runner"
    temporary.mkdir()
    environment = {
        **os.environ,
        "PATH": f"{binary}:{os.environ['PATH']}",
        "RUNNER_TEMP": str(temporary),
    }
    result = subprocess.run(
        ["/bin/bash", "-s"],
        input=run,
        cwd=sandbox,
        env=environment,
        capture_output=True,
        text=True,
        timeout=40,
    )
    output = result.stdout + result.stderr
    assert " passed" in output, output
    assert " failed" not in result.stdout, output
    if mode == "positive":
        assert result.returncode == 0, output
        assert "AUD346 strict coverage:" in output
    else:
        assert result.returncode != 0, output
        if mode == "zero_data":
            assert "No data to report" in output
        elif mode == "wrong_source":
            assert "exact canonical sources" in output
        else:
            assert "Coverage failure" in output
            reports = list(temporary.glob("aud346-coverage.*/coverage.json"))
            assert len(reports) == 1
            report = json.loads(reports[0].read_text())
            helper = report["files"][gate.SOURCES[0]]
            assert helper["missing_branches"]
            assert (
                helper["summary"]["covered_branches"]
                < helper["summary"]["num_branches"]
            )
