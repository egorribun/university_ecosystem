"""Workflow wiring for the owner-activated historical148 admission (2026-10-31).

The unchanged 148642dd1207 revision is rendered and scanned by a separate input step
that records its raw exits and JSON. The evidence step then asks the finite
admission module for the exact inventory and fails the job unless every warning
matches. Changed migrations keep the unchanged fatal raw gate in the lint loop.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / ".github/workflows/ci.yml"
POLICY = ROOT / "quality/historical148-squawk-policy.json"
INPUT_ID = "migration-squawk-148-ordinary"
INPUT_NAME = "Historical 148642dd1207 ordinary Squawk admission input"
LINT_INVOCATION = '"$squawk_binary_path" "${squawk_args[@]}" "$sql_file"'
ADMISSION_MODULE = "uv run python -m scripts.quality.historical148_squawk_admission"


def _job() -> dict[str, Any]:
    workflow = yaml.safe_load(CI.read_text(encoding="utf-8"))
    job: dict[str, Any] = workflow["jobs"]["alembic-migrations"]
    return job


def _step_by_id(job: dict[str, Any], step_id: str) -> dict[str, Any]:
    matches: list[dict[str, Any]] = [
        step for step in job["steps"] if step.get("id") == step_id
    ]
    assert len(matches) == 1
    return matches[0]


def _step_by_name(job: dict[str, Any], name: str) -> dict[str, Any]:
    matches: list[dict[str, Any]] = [
        step for step in job["steps"] if step.get("name") == name
    ]
    assert len(matches) == 1
    return matches[0]


def _index(job: dict[str, Any], step: dict[str, Any]) -> int:
    position: int = job["steps"].index(step)
    return position


def _input_step(job: dict[str, Any]) -> dict[str, Any]:
    return _step_by_id(job, INPUT_ID)


def _lint_step(job: dict[str, Any]) -> dict[str, Any]:
    return _step_by_id(job, "migration-squawk")


def _evidence_step(job: dict[str, Any]) -> dict[str, Any]:
    return _step_by_name(job, "Collect bounded 148642dd1207 DDL evidence")


def _recorded_rules() -> list[str]:
    arguments: list[str] = json.loads(POLICY.read_bytes())["scanner"]["args"]
    assert arguments[::2] == ["--exclude"] * (len(arguments) // 2)
    rules: list[str] = arguments[1::2]
    return rules


def _admission_block(run: str) -> str:
    start = run.index(ADMISSION_MODULE)
    end = run.index('> "$admission_log"', start)
    return run[start : run.index("\n", end)]


def test_unchanged_revision_input_runs_before_the_lint_loop_without_bypass() -> None:
    job = _job()
    step = _input_step(job)
    assert step["name"] == INPUT_NAME
    assert _index(job, step) == _index(job, _lint_step(job)) - 1
    assert "if" not in step
    assert "continue-on-error" not in step
    assert "|| true" not in step["run"]


def test_input_step_records_the_raw_exit_without_failing_the_job() -> None:
    run = _input_step(_job())["run"]
    assert '"$squawk_binary_path" "${squawk_args[@]}" "$sql_file" || raw_exit=$?' in run
    assert "raw_exit=0" in run
    assert "aud148_ordinary_exit=%s" in run


def test_input_step_scans_the_same_sql_with_json_and_keeps_the_verified_binary() -> (
    None
):
    run = _input_step(_job())["run"]
    assert (
        '--reporter json "$sql_file" > "$json_file" 2> "$stderr_file" || json_exit=$?'
        in run
    )
    assert run.count("/usr/bin/sha256sum --check --strict") >= 3
    assert run.index("render_live_alembic_sql") < run.index("|| raw_exit=$?")
    assert run.index("|| raw_exit=$?") < run.index("--reporter json")


def test_input_step_publishes_every_ordinary_admission_field() -> None:
    run = _input_step(_job())["run"]
    for key in (
        "aud148_ordinary_sql",
        "aud148_ordinary_sha256",
        "aud148_ordinary_identity",
        "aud148_ordinary_exit",
        "aud148_ordinary_json",
        "aud148_ordinary_json_exit",
        "aud148_ordinary_stderr",
    ):
        assert f"printf '{key}=" in run, key


def test_lint_loop_raw_gate_stays_fatal_for_changed_migrations() -> None:
    run = _lint_step(_job())["run"]
    assert run.rstrip().endswith(LINT_INVOCATION + '\ndone <<< "$changed_files"')
    assert run.count(LINT_INVOCATION) == 1
    assert "|| true" not in run


def test_evidence_step_reads_only_the_admitted_ordinary_outputs() -> None:
    env = _evidence_step(_job())["env"]
    for variable, output in (
        ("AUD148_ORDINARY_SQL", "aud148_ordinary_sql"),
        ("AUD148_ORDINARY_SHA256", "aud148_ordinary_sha256"),
        ("AUD148_ORDINARY_IDENTITY", "aud148_ordinary_identity"),
        ("AUD148_RAW_ORDINARY_EXIT", "aud148_ordinary_exit"),
        ("AUD148_ORDINARY_JSON", "aud148_ordinary_json"),
        ("AUD148_ORDINARY_JSON_EXIT", "aud148_ordinary_json_exit"),
        ("AUD148_ORDINARY_STDERR", "aud148_ordinary_stderr"),
    ):
        assert env[variable] == f"${{{{ steps.{INPUT_ID}.outputs.{output} }}}}", (
            variable
        )


def test_admission_runs_the_recorded_scanner_identity_and_arguments() -> None:
    run = _evidence_step(_job())["run"]
    assert ADMISSION_MODULE in run
    assert "--policy quality/historical148-squawk-policy.json" in run
    assert '--scanner-sha256 "$expected_sha256"' in run
    assert '--scanner-version "$AUD148_SQUAWK_VERSION"' in run
    assert re.findall(r"--exclude (\S+)", _admission_block(run)) == _recorded_rules()


def test_admission_takes_the_migration_git_object_from_git_hash_object() -> None:
    run = _evidence_step(_job())["run"]
    migration_path = json.loads(POLICY.read_bytes())["migration"]["path"]
    assert f'admission_migration="{migration_path}"' in run
    assert (
        'admission_migration_blob="$(git hash-object -- "$admission_migration" '
        '2>/dev/null)" || admission_migration_blob=""'
    ) in run
    assert '--migration-blob "$admission_migration_blob"' in _admission_block(run)


def test_admission_binds_both_scenarios_and_raw_failures() -> None:
    block = _admission_block(_evidence_step(_job())["run"])
    for argument in (
        '--migration-blob "$admission_migration_blob"',
        '--ordinary-sql "$AUD148_ORDINARY_SQL"',
        '--ordinary-raw-exit "$AUD148_RAW_ORDINARY_EXIT"',
        '--ordinary-json "$AUD148_ORDINARY_JSON"',
        '--ordinary-json-exit "$AUD148_ORDINARY_JSON_EXIT"',
        '--ordinary-stderr "$AUD148_ORDINARY_STDERR"',
        '--expanded-sql "$sql_file"',
        '--expanded-raw-exit "$lint_status"',
        '--expanded-json "$expanded_json"',
        '--expanded-json-exit "$expanded_json_exit"',
        '--expanded-stderr "$expanded_stderr"',
    ):
        assert argument in block, argument


def test_job_fails_closed_on_the_admission_and_keeps_the_capture_gate() -> None:
    run = _evidence_step(_job())["run"]
    assert run.rstrip().endswith('exit "$admission_status"')
    assert 'if [[ "$capture_status" -ne 0 ]]; then' in run
    assert 'exit "$capture_status"' in run
    # The old final line `exit "$lint_status"` must not survive as the job decision.
    assert not run.rstrip().endswith('exit "$lint_status"')
    assert "AUD148_HISTORICAL_ADMISSION_EXIT=$admission_status" in run


def test_evidence_step_keeps_the_original_gate_condition_and_order() -> None:
    job = _job()
    evidence = _evidence_step(job)
    assert _index(job, evidence) == _index(job, _lint_step(job)) + 1
    assert "steps.migration-squawk.outcome == 'failure'" in evidence["if"]
    assert "continue-on-error" not in evidence


def test_the_workflow_introduces_no_new_suppression() -> None:
    job = _job()
    for step in (_input_step(job), _evidence_step(job)):
        assert "continue-on-error" not in step
        assert "|| true" not in step["run"]
    assert "continue-on-error" not in job
