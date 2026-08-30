"""Contract tests for retry-safe Lighthouse producer evidence."""

from __future__ import annotations

from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = (
    REPOSITORY_ROOT / ".github" / "workflows" / "reusable-frontend-tests.yml"
)


def _workflow() -> dict[str, object]:
    payload = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _step(job: dict[str, object], name: str) -> dict[str, object]:
    steps = job["steps"]
    assert isinstance(steps, list)
    for step in steps:
        if isinstance(step, dict) and step.get("name") == name:
            return step
    raise AssertionError(f"missing workflow step: {name}")


def test_lighthouse_producer_publishes_fixed_retry_artifact_contract() -> None:
    """The producer must publish one exact 30-LHR artifact per run attempt."""

    workflow = _workflow()
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    shards = jobs["lighthouse-shards"]
    lighthouse = jobs["lighthouse"]
    assert isinstance(shards, dict)
    assert isinstance(lighthouse, dict)

    assert lighthouse["needs"] == "lighthouse-shards"
    assert (
        lighthouse["if"] == "${{ always() && !cancelled() && inputs.run-lighthouse }}"
    )
    assert lighthouse["timeout-minutes"] == 10

    shard_upload = _step(shards, "Upload Lighthouse shard reports")
    assert shard_upload["if"] == "always()"
    shard_upload_with = shard_upload["with"]
    assert isinstance(shard_upload_with, dict)
    assert shard_upload_with["name"] == (
        "lighthouse-reports-${{ github.run_id }}-${{ github.run_attempt }}-${{ matrix.shard }}"
    )
    assert shard_upload_with["path"] == "${{ inputs.working-directory }}/.lighthouseci"
    assert shard_upload_with["if-no-files-found"] == "error"

    download = _step(lighthouse, "Download Lighthouse shard reports")
    download_with = download["with"]
    assert isinstance(download_with, dict)
    assert download_with == {
        "pattern": "lighthouse-reports-${{ github.run_id }}-${{ github.run_attempt }}-*",
        "path": "${{ inputs.working-directory }}/.lighthouseci-shards",
        "merge-multiple": False,
    }

    assemble = _step(lighthouse, "Assemble canonical Lighthouse evidence")
    assemble_run = str(assemble["run"])
    assemble_env = assemble["env"]
    assert isinstance(assemble_env, dict)
    assert (
        assemble_env["SHARDS_ROOT"]
        == "${{ inputs.working-directory }}/.lighthouseci-shards"
    )
    assert "producer_root=artifacts/lighthouse/producer" in assemble_run
    assert 'shards_root="$SHARDS_ROOT"' in assemble_run
    assert "shards_root=frontend/.lighthouseci-shards" not in assemble_run
    assert "expected_shards=(core content realtime fallback)" in assemble_run
    assert "expected_counts=(9 9 9 3)" in assemble_run
    assert 'prefix="lighthouse-reports-${RUN_ID}-${RUN_ATTEMPT}"' in assemble_run
    assert "Lighthouse evidence path must not traverse a symlink" in assemble_run
    assert 'find "$shard_dir" -type l -print -quit' in assemble_run
    assert (
        "Lighthouse shard download contains an unexpected artifact member"
        in assemble_run
    )
    assert (
        "find \"$shard_dir\" -type f -name 'lhr-*.json' -print0 | sort -z"
        in assemble_run
    )
    assert 'printf -v report_name "lhr-%02d.json" "$index"' in assemble_run
    assert 'target="$producer_root/lhr/$shard/$report_name"' in assemble_run
    assert "Expected exactly 30 Lighthouse LHR JSON reports" in assemble_run

    provenance = _step(lighthouse, "Write Lighthouse evidence provenance")
    provenance_run = str(provenance["run"])
    provenance_env = provenance["env"]
    assert isinstance(provenance_env, dict)
    assert provenance_env["PHYSICAL_ARTIFACT_NAME"] == (
        "lighthouse-reports-attempt-${{ github.run_attempt }}"
    )
    assert provenance_env["LOGICAL_ARTIFACT_NAME"] == "lighthouse-reports"
    assert provenance_env["EXPECTED_SHA"] == "${{ github.sha }}"
    assert provenance_env["WORKFLOW_REPOSITORY"] == "${{ github.repository }}"
    assert provenance_env["WORKFLOW_REF"] == "${{ github.workflow_ref }}"
    assert provenance_env["WORKFLOW_SHA"] == "${{ github.workflow_sha }}"
    assert provenance_env["RUN_ID"] == "${{ github.run_id }}"
    assert provenance_env["RUN_ATTEMPT"] == "${{ github.run_attempt }}"
    assert provenance_env["WORKFLOW_EVENT"] == "${{ github.event_name }}"
    assert "coverage_provenance.py write" in provenance_run
    assert 'cd "$GITHUB_WORKSPACE"' in provenance_run
    assert 'workspace_root="$(pwd -P)"' in provenance_run
    assert (
        'github_workspace_root="$(realpath -- "$GITHUB_WORKSPACE")"' in provenance_run
    )
    assert 'provenance_dir="$producer_root/provenance"' in provenance_run
    assert 'mkdir -p -- "$provenance_dir"' in provenance_run
    assert 'test ! -L "$provenance_dir"' in provenance_run
    assert (
        'provenance_output="$provenance_dir/lighthouse-reports.json"' in provenance_run
    )
    assert '--output "$provenance_output"' in provenance_run
    assert (
        '"lighthouse-$shard|lighthouse-lhr-json|$source|lhr/$shard/$report_name"'
        in provenance_run
    )
    assert "python3 -m scripts.quality.coverage_retry_provenance_cli" in provenance_run
    assert 'retry_output="$(mktemp)"' in provenance_run
    assert 'retry_error="$(mktemp)"' in provenance_run
    assert 'write_output="$(mktemp)"' in provenance_run
    assert 'write_error="$(mktemp)"' in provenance_run
    assert (
        'trap \'rm -f "$retry_output" "$retry_error" "$write_output" "$write_error"\' EXIT'
        in provenance_run
    )
    assert (
        "python3 -m scripts.quality.coverage_retry_provenance_cli \\" in provenance_run
    )
    assert ' >"$retry_output" 2>"$retry_error"' in provenance_run
    assert 'cat "$retry_error" >&2' in provenance_run
    assert 'mapfile -t retry_values < "$retry_output"' in provenance_run
    assert "retry CLI returned" in provenance_run
    assert (
        "--config-input .github/workflows/reusable-frontend-tests.yml" in provenance_run
    )
    assert "--config-input .lighthouserc.js" in provenance_run
    assert "--config-input frontend/scripts/run-lhci.mjs" in provenance_run
    assert "--policy-input quality/quality-contract.json" in provenance_run
    assert (
        "--policy-input scripts/quality/select_lighthouse_artifacts_cli.py"
        in provenance_run
    )
    assert 'retry_args+=(--retry-provenance "$value")' in provenance_run
    assert '"${retry_args[@]}"' in provenance_run
    assert "--retry-provenance" in provenance_run
    assert "lighthouse-reports" in provenance_run
    assert '--job "$GITHUB_JOB"' in provenance_run
    assert '--artifact "$LOGICAL_ARTIFACT_NAME"' in provenance_run
    assert "write_status=0" in provenance_run
    assert ' >"$write_output" 2>"$write_error" || write_status=$?' in provenance_run
    assert "Lighthouse evidence provenance writer failed with exit" in provenance_run
    assert 'cat "$write_error" >&2' in provenance_run
    assert 'cat "$write_output" >&2' in provenance_run
    assert (
        'if [[ ! -f "$provenance_output" || -L "$provenance_output" || ! -s "$provenance_output" ]]; then'
        in provenance_run
    )
    assert "pwd -P" in provenance_run
    assert "stat --printf=" in provenance_run
    assert "writer stderr:" in provenance_run
    assert "writer stdout:" in provenance_run
    assert 'test -s "$provenance_output"' in provenance_run

    upload = _step(lighthouse, "Upload Lighthouse retry evidence")
    upload_with = upload["with"]
    assert isinstance(upload_with, dict)
    assert upload_with == {
        "name": "lighthouse-reports-attempt-${{ github.run_attempt }}",
        "path": "artifacts/lighthouse/producer",
        "include-hidden-files": True,
        "if-no-files-found": "error",
        "overwrite": False,
    }

    steps = lighthouse["steps"]
    assert isinstance(steps, list)
    assert (
        steps.index(download)
        < steps.index(assemble)
        < steps.index(provenance)
        < steps.index(upload)
    )


def test_lighthouse_retry_producer_uses_checked_out_trusted_workflow_scripts() -> None:
    """The final producer needs the current checkout to write bound provenance."""

    workflow = _workflow()
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    lighthouse = jobs["lighthouse"]
    assert isinstance(lighthouse, dict)
    steps = lighthouse["steps"]
    assert isinstance(steps, list)

    checkout = next(
        step
        for step in steps
        if isinstance(step, dict)
        and str(step.get("uses", "")).startswith("actions/checkout@")
    )
    checkout_with = checkout["with"]
    assert isinstance(checkout_with, dict)
    assert checkout_with["persist-credentials"] is False
    assert checkout_with["ref"] == "${{ github.sha }}"

    setup_python = next(
        step
        for step in steps
        if isinstance(step, dict) and step.get("name") == "Set up Python"
    )
    setup_python_with = setup_python["with"]
    assert isinstance(setup_python_with, dict)
    assert setup_python_with["python-version"] == "3.14"
