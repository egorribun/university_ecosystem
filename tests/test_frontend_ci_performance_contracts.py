from __future__ import annotations

from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"
FRONTEND_WORKFLOW_PATH = (
    REPOSITORY_ROOT / ".github" / "workflows" / "reusable-frontend-tests.yml"
)


def _load(path: Path) -> dict[str, object]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _step(job: dict[str, object], name: str) -> dict[str, object]:
    return next(
        step
        for step in job["steps"]  # type: ignore[index]
        if isinstance(step, dict) and step.get("name") == name
    )


def test_frontend_suite_is_not_serialized_behind_pre_commit() -> None:
    jobs = _load(CI_WORKFLOW_PATH)["jobs"]  # type: ignore[index]
    frontend = jobs["frontend-tests"]

    # Frontend tests reuse the single top-level WASM producer. They remain
    # independent of the slower pre-commit gate so unrelated static work can
    # still start as soon as the immutable artifact is ready.
    assert frontend["needs"] == ["e2e-wasm-build"]
    assert "pre-commit-check" not in frontend["needs"]
    assert frontend["permissions"] == {"contents": "read", "actions": "read"}
    assert frontend["with"] == {
        "node-version": "24",
        "run-lighthouse": True,
        "wasm-artifact-id": "${{ needs.e2e-wasm-build.outputs.artifact_id }}",
        "wasm-artifact-name": "${{ needs.e2e-wasm-build.outputs.artifact_name }}",
        "wasm-artifact-digest": "${{ needs.e2e-wasm-build.outputs.artifact_digest }}",
    }
    assert "frontend-tests" in jobs["ci-success"]["needs"]


def test_frontend_wasm_is_built_once_and_reused_by_all_consumers() -> None:
    workflow = _load(FRONTEND_WORKFLOW_PATH)
    jobs = workflow["jobs"]  # type: ignore[index]
    producer = jobs["wasm-build"]

    assert producer["name"] == "Build WASM modules"
    assert producer["timeout-minutes"] == 15
    assert producer["permissions"] == {"contents": "read", "actions": "read"}
    workflow_on = workflow.get("on", workflow.get(True))
    inputs = workflow_on["workflow_call"]["inputs"]  # type: ignore[index]
    expected_input_descriptions = {
        "wasm-artifact-id": "Optional same-run server-issued WASM artifact id",
        "wasm-artifact-name": "Optional same-run WASM artifact name",
        "wasm-artifact-digest": "Optional same-run WASM artifact archive digest",
    }
    for input_name, description in expected_input_descriptions.items():
        assert inputs[input_name] == {
            "description": description,
            "required": False,
            "type": "string",
            "default": "",
        }
    external_mode = (
        "${{ inputs.wasm-artifact-id != '' && inputs.wasm-artifact-name != '' "
        "&& inputs.wasm-artifact-digest != '' }}"
    )
    standalone_mode = (
        "${{ inputs.wasm-artifact-id == '' && inputs.wasm-artifact-name == '' "
        "&& inputs.wasm-artifact-digest == '' }}"
    )
    external_contract = _step(producer, "Validate shared WASM artifact input contract")
    assert "inputs.wasm-artifact-id != ''" in external_contract["if"]
    assert "all three inputs" in external_contract["run"]
    assert "WASM_ARTIFACT_ID" in external_contract["env"]
    external_download = _step(producer, "Download shared immutable WASM modules")
    assert external_download["if"] == external_mode
    assert external_download["with"] == {
        "artifact-ids": "${{ inputs.wasm-artifact-id }}",
        "path": "${{ inputs.working-directory }}",
    }
    external_verify = _step(
        producer, "Verify shared WASM artifact digest and provenance"
    )
    assert external_verify["if"] == external_mode
    assert "actions/artifacts/${ARTIFACT_ID}" in external_verify["run"]
    assert "WASM_PROVENANCE.json" in external_verify["run"]
    assert "WASM_INVENTORY.json" in external_verify["run"]
    assert "verify-wasm-artifacts.mjs" in external_verify["run"]
    for producer_step_name in (
        "Setup Rust toolchain",
        "Install wasm-pack",
        "Install pinned wasm-opt",
        "Build immutable WASM modules",
        "Upload immutable WASM modules",
    ):
        assert _step(producer, producer_step_name)["if"] == standalone_mode
    wasm_opt = _step(producer, "Install pinned wasm-opt")
    assert "binaryen-$binaryen_version-x86_64-linux.tar.gz" in wasm_opt["run"]
    assert (
        "3dc677006555b355ea2da5e82602065a161d5e83eaefd3f759afa00b96e83212"  # pragma: allowlist secret -- public Binaryen release checksum
        in wasm_opt["run"]
    )
    assert "GITHUB_PATH" in wasm_opt["run"]
    build = _step(producer, "Build immutable WASM modules")
    assert build["run"].count("wasm-pack build") == 2
    assert "wasm-pack build rust-crypto --target web --release" in build["run"]
    assert "wasm-pack build wasm-sanitizer --target web --release" in build["run"]
    assert "crypto_pid=$!" not in build["run"]
    assert "sanitizer_pid=$!" not in build["run"]
    assert "&" not in build["run"]
    assert "--remap-path-prefix=$HOME/.cargo=/usr/local/cargo" in build["run"]
    assert "--remap-path-prefix=$GITHUB_WORKSPACE=/work" in build["run"]
    assert "RUSTFLAGS:+$RUSTFLAGS " in build["run"]
    assert "node scripts/verify-wasm-artifacts.mjs" in build["run"]

    artifact_name = (
        "frontend-wasm-${{ github.run_id }}-${{ github.run_attempt }}-${{ github.sha }}"
    )
    upload = _step(producer, "Upload immutable WASM modules")
    assert upload["with"] == {
        "name": artifact_name,
        "path": (
            "${{ inputs.working-directory }}/rust-crypto/pkg\n"
            "${{ inputs.working-directory }}/wasm-sanitizer/pkg\n"
        ),
        "if-no-files-found": "error",
        "overwrite": False,
        "retention-days": 1,
        "compression-level": 0,
    }

    for job_name in ("unit-tests-shard", "lint", "build"):
        consumer = jobs[job_name]
        assert consumer["needs"] == "wasm-build"
        download = _step(consumer, "Download immutable WASM modules")
        assert download["with"] == {
            "name": artifact_name,
            "path": "${{ inputs.working-directory }}",
        }
        shared_download = _step(consumer, "Download shared immutable WASM modules")
        assert shared_download["with"] == {
            "artifact-ids": "${{ inputs.wasm-artifact-id }}",
            "path": "${{ inputs.working-directory }}",
        }
        install = _step(consumer, "Install dependencies")
        assert consumer["steps"].index(download) < consumer["steps"].index(install)

        consumer_text = "\n".join(
            str(step.get("run", "")) + str(step.get("uses", ""))
            for step in consumer["steps"]
            if isinstance(step, dict)
        )
        assert "wasm-pack build" not in consumer_text
        assert "taiki-e/install-action" not in consumer_text

    assert jobs["unit-tests-shard"]["strategy"]["matrix"]["shard"] == [1, 2, 3, 4]
    assert _step(jobs["build"], "Build app")["env"] == {"SKIP_WASM_BUILD": "1"}


def test_frontend_wasm_target_is_installed_once_before_sequential_builds() -> None:
    workflow = _load(FRONTEND_WORKFLOW_PATH)
    producer = workflow["jobs"]["wasm-build"]  # type: ignore[index]
    build_run = _step(producer, "Build immutable WASM modules")["run"]

    target_install = "rustup target add wasm32-unknown-unknown"
    target_verify = (
        'rustup target list --installed | grep -Fxq "wasm32-unknown-unknown"'
    )
    first_build = "wasm-pack build rust-crypto --target web --release"
    second_build = "wasm-pack build wasm-sanitizer --target web --release"

    assert build_run.count(target_install) == 1
    assert build_run.count(target_verify) == 1
    assert build_run.index(target_install) < build_run.index(first_build)
    assert build_run.index(target_verify) < build_run.index(first_build)
    assert build_run.index(first_build) < build_run.index(second_build)
    assert "&" not in build_run


def test_frontend_wasm_build_pins_the_artifact_toolchain() -> None:
    """Generated bytes must be reproducible across hosted runner image updates."""
    workflow = _load(FRONTEND_WORKFLOW_PATH)
    producer = workflow["jobs"]["wasm-build"]  # type: ignore[index]
    setup = _step(producer, "Setup Rust toolchain")

    assert setup["uses"] == (
        "dtolnay/rust-toolchain@6c977a6ca4077a0ceb28ffbe03f59d46e9ac8772"
    )
    assert setup["with"] == {
        "toolchain": "1.97.1",
        "targets": "wasm32-unknown-unknown",
    }
    build_run = _step(producer, "Build immutable WASM modules")["run"]
    assert "rustc --version" in build_run


def test_frontend_wasm_build_uses_pinned_binaryen_before_system_wasm_opt() -> None:
    workflow = _load(FRONTEND_WORKFLOW_PATH)
    producer = workflow["jobs"]["wasm-build"]  # type: ignore[index]
    install = _step(producer, "Install pinned wasm-opt")
    run = install["run"]
    assert "version_117" in run
    assert "sha256sum --check --strict" in run
    assert "GITHUB_PATH" in run


def test_frontend_wasm_build_remaps_host_paths_and_preserves_existing_flags() -> None:
    workflow = _load(FRONTEND_WORKFLOW_PATH)
    producer = workflow["jobs"]["wasm-build"]  # type: ignore[index]
    build_run = _step(producer, "Build immutable WASM modules")["run"]
    assert 'export RUSTFLAGS="${RUSTFLAGS:+$RUSTFLAGS }' in build_run
    assert "--remap-path-prefix=$HOME/.cargo=/usr/local/cargo" in build_run
    assert "--remap-path-prefix=$GITHUB_WORKSPACE=/work" in build_run


def test_frontend_typecheck_runs_once_in_a_required_static_gate() -> None:
    jobs = _load(FRONTEND_WORKFLOW_PATH)["jobs"]  # type: ignore[index]
    typecheck_steps = [
        (job_name, step)
        for job_name, job in jobs.items()
        for step in job.get("steps", [])
        if isinstance(step, dict) and "npm run typecheck" in str(step.get("run", ""))
    ]

    assert [job_name for job_name, _ in typecheck_steps] == ["lint"]
    static_gate = typecheck_steps[0][1]
    assert static_gate["name"] == "Run frontend static gates in parallel"
    run = static_gate["run"]
    for invocation in (
        "run_gate typecheck npm run typecheck &",
        "run_gate eslint npm run lint &",
        "run_gate formatting npm run format:check &",
        "run_gate i18n npm run i18n:check &",
        "run_gate message_contract python ../scripts/generate_message_contract.py --check &",
        "run_gate deadcode npm run lint:deadcode &",
        "run_gate depcheck npm run lint:depcheck &",
    ):
        assert run.count(invocation) == 1
    assert run.count("run_gate ") == 7
    assert "wait" in run
    assert 'exit "$failed"' in run
