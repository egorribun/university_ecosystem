"""Fail-closed tests for the per-check Scorecard floor gate (AUD-381)."""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.quality import scorecard_floors_gate as gate

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = REPOSITORY_ROOT / "quality" / "scorecard-floors.json"
EXPECTED_COMMIT = "a" * 40

# Ratchet: every gated floor may rise but never fall below these values. They
# were measured from scorecard workflow run 41410082985 (see the policy file).
MINIMUM_GATED_FLOORS = {
    "Dangerous-Workflow": 10,
    "Token-Permissions": 10,
    "Pinned-Dependencies": 9,
    "Vulnerabilities": 0,
    "Binary-Artifacts": 8,
    "SAST": 9,
}
PUBLISHED_ONLY_CHECKS = {
    "Branch-Protection",
    "CII-Best-Practices",
    "Code-Review",
    "Contributors",
    "Packaging",
    "Signed-Releases",
}


def _policy(**overrides: Any) -> dict[str, Any]:
    policy: dict[str, Any] = {
        "schema_version": 1,
        "gated_checks": dict(MINIMUM_GATED_FLOORS),
        "published_only_checks": ["Code-Review"],
    }
    policy.update(overrides)
    return policy


def _result(checks: list[Any] | None = None, **overrides: Any) -> dict[str, Any]:
    if checks is None:
        checks = [
            {"name": "Dangerous-Workflow", "score": 10, "reason": "clean"},
            {"name": "Token-Permissions", "score": 10},
            {"name": "Pinned-Dependencies", "score": 9},
            {"name": "Vulnerabilities", "score": 0},
            {"name": "Binary-Artifacts", "score": 8},
            {"name": "SAST", "score": 9, "reason": "warn"},
            {"name": "Code-Review", "score": 0, "reason": "none"},
        ]
    result: dict[str, Any] = {
        "date": "2026-11-02T08:02:00Z",
        "repo": {"name": "github.com/example/project", "commit": EXPECTED_COMMIT},
        "checks": checks,
    }
    result.update(overrides)
    return result


def _write(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8", newline="\n")
    return path


def _text(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def test_committed_policy_retains_published_only_checks() -> None:
    _, published = gate.load_floors(POLICY_PATH)

    assert set(published) == PUBLISHED_ONLY_CHECKS


def test_committed_floors_never_decrease_below_the_pinned_minimum() -> None:
    floors, _ = gate.load_floors(POLICY_PATH)

    assert set(floors) == set(MINIMUM_GATED_FLOORS)
    for name, minimum in MINIMUM_GATED_FLOORS.items():
        assert floors[name] >= minimum, name


def test_committed_policy_records_its_source_run() -> None:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))

    assert policy["source"]["workflow_run_id"] == 41410082985
    assert policy["source"]["workflow"] == ".github/workflows/scorecard.yml"
    assert "head_sha" not in policy["source"]


def test_policy_gates_exactly_the_six_key_checks() -> None:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))

    assert set(policy["gated_checks"]) == set(MINIMUM_GATED_FLOORS)
    assert not set(policy["gated_checks"]) & set(policy["published_only_checks"])


def test_load_floors_returns_gated_and_published_checks(tmp_path: Path) -> None:
    floors, published = gate.load_floors(_write(tmp_path / "p.json", _policy()))

    assert floors == MINIMUM_GATED_FLOORS
    assert published == ["Code-Review"]


@pytest.mark.parametrize(
    "policy",
    [
        pytest.param(_policy(schema_version=2), id="unknown-schema"),
        pytest.param(_policy(schema_version=True), id="boolean-schema"),
        pytest.param(_policy(gated_checks={}), id="no-gated-checks"),
        pytest.param(_policy(gated_checks=None), id="gated-not-mapping"),
        pytest.param(
            _policy(gated_checks={**MINIMUM_GATED_FLOORS, "SAST": 11}),
            id="floor-above-ten",
        ),
        pytest.param(
            _policy(gated_checks={**MINIMUM_GATED_FLOORS, "SAST": -1}),
            id="not-applicable-floor",
        ),
        pytest.param(
            _policy(gated_checks={**MINIMUM_GATED_FLOORS, "SAST": 9.5}),
            id="fractional-floor",
        ),
        pytest.param(
            _policy(gated_checks={**MINIMUM_GATED_FLOORS, "SAST": True}),
            id="boolean-floor",
        ),
        pytest.param(_policy(published_only_checks="Code-Review"), id="not-a-list"),
        pytest.param(_policy(published_only_checks=[1]), id="non-string-published"),
        pytest.param(_policy(published_only_checks=[""]), id="empty-published-name"),
        pytest.param(
            _policy(published_only_checks=["Code-Review", "Code-Review"]),
            id="duplicate-published-name",
        ),
        pytest.param(
            _policy(published_only_checks=["SAST"]),
            id="check-both-gated-and-published",
        ),
    ],
)
def test_malformed_policy_fails_closed(tmp_path: Path, policy: dict[str, Any]) -> None:
    with pytest.raises(gate.GateError):
        gate.load_floors(_write(tmp_path / "p.json", policy))


def test_unreadable_policy_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(gate.GateError):
        gate.load_floors(_text(tmp_path / "p.json", "{"))


def test_missing_policy_file_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(gate.GateError):
        gate.load_floors(tmp_path / "absent.json")


@pytest.mark.parametrize("missing", MINIMUM_GATED_FLOORS)
def test_missing_key_check_from_policy_fails_closed(
    tmp_path: Path, missing: str
) -> None:
    floors = dict(MINIMUM_GATED_FLOORS)
    del floors[missing]

    with pytest.raises(gate.GateError):
        gate.load_floors(_write(tmp_path / "p.json", _policy(gated_checks=floors)))


@pytest.mark.parametrize(
    "name", [name for name, floor in MINIMUM_GATED_FLOORS.items() if floor > 0]
)
def test_policy_cannot_lower_initial_floor(tmp_path: Path, name: str) -> None:
    floors = dict(MINIMUM_GATED_FLOORS)
    floors[name] -= 1

    with pytest.raises(gate.GateError):
        gate.load_floors(_write(tmp_path / "p.json", _policy(gated_checks=floors)))


def test_duplicate_keys_in_policy_fail_closed(tmp_path: Path) -> None:
    text = json.dumps(_policy()).replace('"SAST": 9', '"SAST": 9, "SAST": 10')
    with pytest.raises(gate.GateError):
        gate.load_floors(_text(tmp_path / "p.json", text))


def test_load_scores_maps_every_check(tmp_path: Path) -> None:
    scores = gate.load_scores(_write(tmp_path / "r.json", _result()), EXPECTED_COMMIT)

    assert scores == {**MINIMUM_GATED_FLOORS, "Code-Review": 0}


@pytest.mark.parametrize(
    "result",
    [
        pytest.param(["not", "an", "object"], id="root-is-list"),
        pytest.param({"date": "x"}, id="missing-checks"),
        pytest.param({"checks": "SAST"}, id="checks-not-list"),
        pytest.param({"checks": ["SAST"]}, id="check-not-object"),
        pytest.param({"checks": [{"score": 9}]}, id="check-without-name"),
        pytest.param({"checks": [{"name": "", "score": 9}]}, id="empty-name"),
        pytest.param({"checks": [{"name": "SAST"}]}, id="check-without-score"),
        pytest.param({"checks": [{"name": "SAST", "score": "9"}]}, id="string-score"),
        pytest.param({"checks": [{"name": "SAST", "score": 11}]}, id="score-above-ten"),
        pytest.param({"checks": [{"name": "SAST", "score": -2}]}, id="score-below-na"),
        pytest.param({"checks": [{"name": "SAST", "score": True}]}, id="bool-score"),
        pytest.param(
            {"checks": [{"name": "SAST", "score": 9}, {"name": "SAST", "score": 1}]},
            id="duplicate-check",
        ),
    ],
)
def test_malformed_result_fails_closed(tmp_path: Path, result: Any) -> None:
    with pytest.raises(gate.GateError):
        if isinstance(result, dict):
            result = {"repo": {"commit": EXPECTED_COMMIT}, **result}
        gate.load_scores(_write(tmp_path / "r.json", result), EXPECTED_COMMIT)


def test_unreadable_result_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(gate.GateError):
        gate.load_scores(_text(tmp_path / "r.json", "{not json"), EXPECTED_COMMIT)


def test_duplicate_keys_in_score_fail_closed(tmp_path: Path) -> None:
    text = '{"checks": [{"name": "SAST", "score": 1, "score": 10}]}'
    with pytest.raises(gate.GateError):
        gate.load_scores(_text(tmp_path / "r.json", text), EXPECTED_COMMIT)


@pytest.mark.parametrize(
    "repo",
    [None, {}, {"commit": "b" * 40}, {"commit": "a" * 39}, {"commit": True}],
)
def test_native_result_must_match_the_exact_event_commit(
    tmp_path: Path, repo: Any
) -> None:
    result = _write(tmp_path / "r.json", _result(repo=repo))
    with pytest.raises(gate.GateError):
        gate.load_scores(result, EXPECTED_COMMIT)


@pytest.mark.parametrize("expected", [None, "", "a" * 39, "z" * 40, "A" * 40])
def test_invalid_expected_commit_fails_closed(tmp_path: Path, expected: Any) -> None:
    result = _write(tmp_path / "r.json", _result())
    with pytest.raises(gate.GateError):
        gate.load_scores(result, expected)


def test_source_only_cli_verifies_native_json_commit(tmp_path: Path) -> None:
    result = _write(tmp_path / "r.json", _result())

    assert (
        gate.main(
            [
                str(POLICY_PATH),
                str(result),
                "--expected-commit",
                EXPECTED_COMMIT,
                "--validate-source-only",
            ]
        )
        == 0
    )


def test_source_only_cli_rejects_different_native_commit(tmp_path: Path) -> None:
    result = _write(tmp_path / "r.json", _result(repo={"commit": "b" * 40}))

    assert (
        gate.main(
            [
                str(POLICY_PATH),
                str(result),
                "--expected-commit",
                EXPECTED_COMMIT,
                "--validate-source-only",
            ]
        )
        == 1
    )


def test_scan_cli_requires_expected_commit(tmp_path: Path) -> None:
    result = _write(tmp_path / "r.json", _result())
    with pytest.raises(SystemExit):
        gate.main([str(POLICY_PATH), str(result)])


def test_source_only_cli_rejects_score_summary_option(tmp_path: Path) -> None:
    result = _write(tmp_path / "r.json", _result())
    with pytest.raises(SystemExit):
        gate.main(
            [
                str(POLICY_PATH),
                str(result),
                "--expected-commit",
                EXPECTED_COMMIT,
                "--validate-source-only",
                "--summary-file",
                str(tmp_path / "summary.md"),
            ]
        )


def test_ratchet_accepts_a_raised_floor(tmp_path: Path) -> None:
    previous = _write(tmp_path / "previous.json", _policy())
    raised = dict(MINIMUM_GATED_FLOORS)
    raised["SAST"] = 10
    current = _write(tmp_path / "current.json", _policy(gated_checks=raised))

    assert gate.run_ratchet(current, previous) == 0


def test_ratchet_rejects_reduction_after_a_floor_was_raised(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    raised = dict(MINIMUM_GATED_FLOORS)
    raised["SAST"] = 10
    previous = _write(tmp_path / "previous.json", _policy(gated_checks=raised))
    current = _write(tmp_path / "current.json", _policy())

    assert gate.run_ratchet(current, previous) == 1
    assert "SAST" in capsys.readouterr().err


def test_ratchet_fails_closed_when_previous_policy_is_missing(tmp_path: Path) -> None:
    current = _write(tmp_path / "current.json", _policy())

    assert gate.run_ratchet(current, tmp_path / "missing.json") == 1


def test_ratchet_cli_checks_previous_policy_without_scan_result(tmp_path: Path) -> None:
    previous = _write(tmp_path / "previous.json", _policy())
    current = _write(tmp_path / "current.json", _policy())

    assert gate.main([str(current), "--previous-floors", str(previous)]) == 0


def test_ratchet_cli_rejects_combining_previous_policy_with_scan_result(
    tmp_path: Path,
) -> None:
    current = _write(tmp_path / "current.json", _policy())
    result = _write(tmp_path / "result.json", _result())

    with pytest.raises(SystemExit):
        gate.main([str(current), str(result), "--previous-floors", str(current)])


def test_ratchet_cli_rejects_scan_summary_option(tmp_path: Path) -> None:
    current = _write(tmp_path / "current.json", _policy())

    with pytest.raises(SystemExit):
        gate.main(
            [
                str(current),
                "--previous-floors",
                str(current),
                "--summary-file",
                str(tmp_path / "summary"),
            ]
        )


def test_scorecard_retains_and_publishes_partial_reports_after_failure() -> None:
    workflow = yaml.safe_load(
        (REPOSITORY_ROOT / ".github/workflows/scorecard.yml").read_text(
            encoding="utf-8"
        )
    )
    steps = workflow["jobs"]["analysis"]["steps"]
    by_name = {step["name"]: step for step in steps}
    trusted = by_name["Verify trusted main source"]
    sarif = by_name["Run OpenSSF Scorecard (SARIF for Code Scanning)"]
    normalize = by_name["Normalize Scorecard result ownership"]
    publish = by_name["Upload SARIF results to GitHub Security tab"]
    provenance = by_name["Verify Scorecard report source"]
    gate_step = by_name["Gate Scorecard key-check floors"]
    upload = by_name["Upload Scorecard reports"]

    assert trusted["id"] == "trusted_source"
    assert "always()" in sarif["if"]
    assert "steps.trusted_source.outcome == 'success'" in sarif["if"]
    assert "always()" in normalize["if"]
    assert 'if [[ -f "$report" ]]' in normalize["run"]
    assert "always()" in publish["if"]
    assert "steps.scorecard-sarif.outcome == 'success'" in publish["if"]
    assert "steps.report_source.outcome == 'success'" in publish["if"]
    assert steps.index(sarif) < steps.index(provenance) < steps.index(publish)
    assert provenance["env"]["EVENT_SHA"] == "${{ github.sha }}"
    assert (
        provenance["env"]["SCORECARD_RESULT_OUTCOME"]
        == "${{ steps.scorecard-json.outcome }}"
    )
    assert "--validate-source-only" in provenance["run"]
    assert '--expected-commit "$EVENT_SHA"' in provenance["run"]
    assert gate_step["env"]["EVENT_SHA"] == "${{ github.sha }}"
    assert '--expected-commit "$EVENT_SHA"' in gate_step["run"]
    assert "id-token" not in workflow["jobs"]["analysis"]["permissions"]
    assert upload["if"] == "${{ always() }}"
    assert set(upload["with"]["path"].split()) == {
        "scorecard-results.json",
        "scorecard-results.sarif",
    }
    assert upload["with"]["retention-days"] == 90


def test_meeting_every_floor_passes_and_publishes_all_checks() -> None:
    failures, summary = gate.evaluate(
        {"SAST": 9},
        ["Code-Review"],
        {"SAST": 9, "Code-Review": 0},
    )

    assert failures == []
    assert "| SAST | 9 | 9 | gated |" in summary
    assert "| Code-Review | 0 | - | published only |" in summary


def test_score_below_floor_fails_naming_the_check() -> None:
    failures, _ = gate.evaluate(
        {"Pinned-Dependencies": 9}, [], {"Pinned-Dependencies": 8}
    )

    assert failures == ["Pinned-Dependencies scored 8, below its floor of 9"]


def test_aggregate_score_cannot_hide_a_failing_key_check() -> None:
    """A high score elsewhere must not satisfy a gated check below its floor."""

    scores = {"Dangerous-Workflow": 0, "SAST": 10}
    failures, _ = gate.evaluate({"Dangerous-Workflow": 10, "SAST": 9}, [], scores)

    assert failures == ["Dangerous-Workflow scored 0, below its floor of 10"]


def test_missing_gated_check_fails_closed() -> None:
    failures, summary = gate.evaluate({"SAST": 9}, [], {})

    assert failures == ["SAST has no applicable score; the gate is unknown"]
    assert "| SAST | n/a | 9 | gated |" in summary


def test_not_applicable_gated_check_fails_closed() -> None:
    failures, _ = gate.evaluate({"SAST": 9}, [], {"SAST": -1})

    assert failures == ["SAST has no applicable score; the gate is unknown"]


def test_published_only_check_below_threshold_never_fails() -> None:
    failures, summary = gate.evaluate({}, ["Code-Review"], {"Code-Review": 0})

    assert failures == []
    assert "| Code-Review | 0 | - | published only |" in summary


def test_published_only_check_absent_from_result_is_shown_not_failed() -> None:
    failures, summary = gate.evaluate({}, ["Packaging"], {})

    assert failures == []
    assert "| Packaging | n/a | - | published only |" in summary


def test_run_gate_passes_and_writes_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    policy = _write(tmp_path / "p.json", _policy())
    result = _write(tmp_path / "r.json", _result())
    summary = tmp_path / "summary.md"

    code = gate.run_gate(policy, result, summary, EXPECTED_COMMIT)

    assert code == 0
    assert "Scorecard gated checks meet their recorded floors." in (
        capsys.readouterr().out
    )
    assert "### OpenSSF Scorecard floors" in summary.read_text(encoding="utf-8")


def test_run_gate_fails_on_a_floor_breach(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    policy = _write(tmp_path / "p.json", _policy())
    result = _write(
        tmp_path / "r.json",
        _result(
            [
                {"name": "Dangerous-Workflow", "score": 10},
                {"name": "SAST", "score": 4},
            ]
        ),
    )

    code = gate.run_gate(policy, result, None, EXPECTED_COMMIT)

    assert code == 1
    assert "::error::Scorecard SAST scored 4, below its floor of 9." in (
        capsys.readouterr().err
    )


def test_run_gate_fails_closed_on_unusable_evidence(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    policy = _write(tmp_path / "p.json", _policy())
    result = _text(tmp_path / "r.json", "not json")

    code = gate.run_gate(policy, result, None, EXPECTED_COMMIT)

    assert code == 1
    assert "the scan result is unknown." in capsys.readouterr().err


def test_main_runs_the_gate_on_the_given_paths(tmp_path: Path) -> None:
    policy = _write(tmp_path / "p.json", _policy())
    result = _write(tmp_path / "r.json", _result())

    assert (
        gate.main([str(policy), str(result), "--expected-commit", EXPECTED_COMMIT]) == 0
    )


def test_main_requires_both_paths() -> None:
    with pytest.raises(SystemExit):
        gate.main([])


def test_script_entry_point_exits_with_the_gate_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Running the file as a script reaches the same exit status as main()."""

    policy = _write(tmp_path / "p.json", _policy())
    result = _write(tmp_path / "r.json", _result())
    script = Path(gate.__file__).resolve()
    monkeypatch.setattr(
        sys,
        "argv",
        [str(script), str(policy), str(result), "--expected-commit", EXPECTED_COMMIT],
    )
    with pytest.raises(SystemExit) as raised:
        runpy.run_path(str(script), run_name="__main__")

    assert raised.value.code == 0
