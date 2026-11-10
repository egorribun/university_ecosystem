"""A wall-clock Semgrep fixpoint timeout is confirmed by a complete re-analysis."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = REPOSITORY_ROOT / "scripts" / "quality" / "run_semgrep_gate.py"
SPEC = importlib.util.spec_from_file_location("fixpoint_runner", RUNNER_PATH)
assert SPEC is not None and SPEC.loader is not None
gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gate
SPEC.loader.exec_module(gate)

IMAGE = "semgrep/semgrep:1.179.0@sha256:" + "d" * 64
SLOW = "scripts/slow.py"
OTHER = "scripts/other.py"


def _timeout(path: str = SLOW) -> dict[str, Any]:
    return {
        "message": "Fixpoint timeout while performing taint analysis at x [rules: 1, first: y]",
        "location": {"path": path},
    }


def _finding(line: int, path: str = SLOW) -> dict[str, Any]:
    return {
        "check_id": "out.rule",
        "path": path,
        "start": {"line": line, "col": 1},
        "end": {"line": line, "col": 2},
    }


def _report(
    *,
    scanned: tuple[str, ...] = (SLOW, OTHER),
    timeouts: list[Any] | None = None,
    results: list[Any] | None = None,
) -> dict[str, Any]:
    return {
        "results": results or [],
        "errors": [],
        "skipped_rules": [],
        "paths": {"scanned": list(scanned), "skipped": []},
        "time": {"fixpoint_timeouts": timeouts or []},
    }


def _sarif(*lines: int) -> dict[str, Any]:
    return {
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Semgrep OSS",
                        "semanticVersion": "1.179.0",
                        "rules": [{"id": "out.rule"}],
                    }
                },
                "results": [
                    {
                        "ruleId": "out.rule",
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": SLOW},
                                    "region": {"startLine": line},
                                }
                            }
                        ],
                    }
                    for line in lines
                ],
            }
        ],
    }


@pytest.fixture
def context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    monkeypatch.setattr(gate, "_persist_reports", lambda *_args: None)
    monkeypatch.setattr(gate, "_verify_source_snapshot", lambda *_args: None)
    monkeypatch.setattr(gate, "_verify_index_unchanged", lambda **_kwargs: None)
    monkeypatch.setattr(gate, "_tree_file_hashes", lambda *_a, **_k: {"f": "hash"})
    output = tmp_path / "out"
    output.mkdir()
    return SimpleNamespace(
        image=IMAGE,
        repository_root=tmp_path,
        run_command=None,
        scan_output_directory=output,
        scan_root=tmp_path,
        snapshot_manifest=[],
        index_entries=[],
        manifest_directory=output,
        manifest_sha256="",
        overlay_root=tmp_path,
        overlay_target_hashes={"f": "hash"},
        report_directory=None,
        results_path=output / "semgrep.json",
        sarif_path=output / "semgrep.sarif",
    )


def _install_scan(
    monkeypatch: pytest.MonkeyPatch, report: dict[str, Any], sarif: dict[str, Any]
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def fake_scan(**kwargs: Any) -> int:
        calls.append(kwargs)
        output = kwargs["output_directory"]
        prefix = kwargs["report_prefix"]
        (output / f"{prefix}.json").write_text(json.dumps(report), encoding="utf-8")
        (output / f"{prefix}.sarif").write_text(json.dumps(sarif), encoding="utf-8")
        return 1 if report["results"] else 0

    monkeypatch.setattr(gate, "_docker_scan", fake_scan)
    return calls


def _write_primary(context: SimpleNamespace, report: dict[str, Any]) -> None:
    context.results_path.write_text(json.dumps(report), encoding="utf-8")
    context.sarif_path.write_text(json.dumps(_sarif(1)), encoding="utf-8")


def test_no_timeout_runs_no_second_scan(
    context: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_primary(context, _report())
    calls = _install_scan(monkeypatch, _report(), _sarif())

    preserved = gate._run_fixpoint_confirmation(
        context, primary_reports_preserved=False
    )

    assert preserved is False
    assert calls == []


def test_confirmation_rescans_only_timed_out_files_and_keeps_all_findings(
    context: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    timeouts = [_timeout(), _timeout()]
    _write_primary(context, _report(timeouts=timeouts, results=[_finding(1)]))
    calls = _install_scan(
        monkeypatch,
        _report(scanned=(SLOW,), results=[_finding(1), _finding(9)]),
        _sarif(1, 9),
    )

    assert gate._run_fixpoint_confirmation(context, primary_reports_preserved=False)

    assert len(calls) == 1
    assert calls[0]["target_paths"] == (SLOW,)
    assert calls[0]["jobs"] == 1
    assert calls[0]["explicit_file_targets"] is True
    merged = json.loads(context.results_path.read_text(encoding="utf-8"))
    assert [item["start"]["line"] for item in merged["results"]] == [1, 9]
    assert merged["time"]["fixpoint_timeouts"] == []
    evidence = merged["supplemental_scan_evidence"][-1]
    assert evidence["mode"] == "fixpoint-timeout-confirmation"
    assert evidence["targets"] == [SLOW]
    assert evidence["confirmed_fixpoint_timeouts"] == timeouts
    assert merged["paths"]["scanned"] == [SLOW, OTHER]
    sarif = json.loads(context.sarif_path.read_text(encoding="utf-8"))
    regions = [
        item["locations"][0]["physicalLocation"]["region"]["startLine"]
        for item in sarif["runs"][0]["results"]
    ]
    assert regions == [1, 9]
    assert (context.scan_output_directory / "semgrep-primary.json").is_file()


@pytest.mark.parametrize(
    ("confirmation", "message"),
    [
        (
            _report(scanned=(SLOW,), timeouts=[_timeout()]),
            "fixpoint confirmation supplemental scan has missing or timed-out analysis",
        ),
        (
            {**_report(scanned=(SLOW,)), "errors": [{"message": "partial"}]},
            "fixpoint confirmation supplemental scan reported diagnostics",
        ),
        (
            _report(scanned=(OTHER,)),
            "fixpoint confirmation supplemental scan did not scan the exact target set",
        ),
    ],
)
def test_incomplete_confirmation_stays_fatal_and_leaves_the_report_alone(
    context: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    confirmation: dict[str, Any],
    message: str,
) -> None:
    primary = _report(timeouts=[_timeout()])
    _write_primary(context, primary)
    _install_scan(monkeypatch, confirmation, _sarif())

    with pytest.raises(gate.SemgrepGateError, match=message):
        gate._run_fixpoint_confirmation(context, primary_reports_preserved=False)

    assert json.loads(context.results_path.read_text(encoding="utf-8")) == primary


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        ({"message": "no location"}, "names no target"),
        (_timeout("scripts/never_scanned.py"), "names an unscanned target"),
    ],
)
def test_unattributable_timeout_cannot_be_confirmed(
    entry: dict[str, Any], message: str
) -> None:
    with pytest.raises(gate.SemgrepGateError, match=message):
        gate._fixpoint_timeout_targets(_report(timeouts=[entry]))


def test_timeouts_across_too_many_files_are_not_confirmed() -> None:
    paths = tuple(
        f"scripts/f{index}.py"
        for index in range(gate.FIXPOINT_CONFIRMATION_MAX_TARGETS + 1)
    )
    report = _report(scanned=paths, timeouts=[_timeout(path) for path in paths])

    with pytest.raises(gate.SemgrepGateError, match="exceed the confirmation bound"):
        gate._fixpoint_timeout_targets(report)


def test_docker_confirmation_scan_uses_one_job_and_exact_files(tmp_path: Path) -> None:
    root = tmp_path / "root"
    target = root / SLOW
    target.parent.mkdir(parents=True)
    target.write_text("x = 1\n", encoding="utf-8")
    output = tmp_path / "out"
    output.mkdir()
    commands: list[list[str]] = []
    container_names: list[str] = []

    def runner(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if command[:2] == ["docker", "run"]:
            cid = Path(command[command.index("--cidfile") + 1])
            cid.write_text("b" * 64, encoding="utf-8")
            container_names.append(command[command.index("--name") + 1])
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[:2] == ["docker", "inspect"]:
            name = "/" + container_names[-1]
            return subprocess.CompletedProcess(command, 0, f"{'b' * 64} {name}\n", "")
        return subprocess.CompletedProcess(command, 0, "", "")

    status = gate._docker_scan(
        scan_root=root,
        output_directory=output,
        image=IMAGE,
        command_runner=runner,
        scan_id="semgrep-fixpoint-confirmation",
        report_prefix="semgrep-fixpoint-confirmation",
        target_paths=(SLOW,),
        explicit_file_targets=True,
        jobs=1,
    )

    assert status == 0
    scan = next(command for command in commands if command[:2] == ["docker", "run"])
    assert scan[scan.index("--timeout") + 1] == "10"
    assert "--timeout-threshold" not in scan
    assert scan[scan.index("--jobs") + 1] == "1"
    assert scan[-1] == SLOW
    assert "--scan-unknown-extensions" not in scan
    assert "--disable-nosem" in scan


@pytest.mark.parametrize(
    "targets", [(".",), ("../outside.py",), ("scripts/missing.py",)]
)
def test_docker_confirmation_scan_rejects_non_file_targets(
    tmp_path: Path, targets: tuple[str, ...]
) -> None:
    def runner(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        pytest.fail(f"no process may start for rejected targets: {command[0]}")

    with pytest.raises(gate.SemgrepGateError, match="explicit-target scan"):
        gate._docker_scan(
            scan_root=tmp_path,
            output_directory=tmp_path,
            image=IMAGE,
            command_runner=runner,
            target_paths=targets,
            explicit_file_targets=True,
        )


def test_run_gate_confirms_after_all_supplements_before_dispositions() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")
    body = source[source.index("def run_gate(") :]
    order = [
        body.index("_run_inline_javascript_supplement("),
        body.index("_run_fixpoint_confirmation("),
        body.index("_evaluate_merged_dispositions("),
    ]
    assert order == sorted(order)


def test_rules_git_commands_cannot_touch_the_repository_exported_to_hooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A hook in a linked worktree inherits GIT_DIR; `git init` must ignore it."""
    decoy = tmp_path / "decoy"
    subprocess.run(  # noqa: S603  # Fixed git command on a temporary repository.
        ["git", "init", "--quiet", str(decoy)],  # noqa: S607  # git comes from PATH.
        check=True,
    )
    decoy_config = decoy / ".git" / "config"
    before = decoy_config.read_bytes()
    monkeypatch.setenv("GIT_DIR", str(decoy / ".git"))
    monkeypatch.setenv("GIT_INDEX_FILE", str(decoy / ".git" / "index"))
    rules = tmp_path / "rules"
    rules.mkdir()

    gate._run_git(["git", "init", "--quiet"], cwd=rules, command_runner=subprocess.run)
    gate._run_git(
        ["git", "remote", "add", "origin", gate.RULES_URL],
        cwd=rules,
        command_runner=subprocess.run,
    )

    assert decoy_config.read_bytes() == before
    assert gate.RULES_URL in (rules / ".git" / "config").read_text(encoding="utf-8")
