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

    assert "needs" not in frontend
    assert "frontend-tests" in jobs["ci-success"]["needs"]


def test_frontend_wasm_is_built_once_and_reused_by_all_consumers() -> None:
    workflow = _load(FRONTEND_WORKFLOW_PATH)
    jobs = workflow["jobs"]  # type: ignore[index]
    producer = jobs["wasm-build"]

    assert producer["name"] == "Build WASM modules"
    assert producer["timeout-minutes"] == 15
    build = _step(producer, "Build immutable WASM modules")
    assert build["run"].count("wasm-pack build") == 2
    assert "wasm-pack build rust-crypto --target web --release" in build["run"]
    assert "wasm-pack build wasm-sanitizer --target web --release" in build["run"]
    assert "crypto_pid=$!" in build["run"]
    assert "sanitizer_pid=$!" in build["run"]
    assert 'wait "$crypto_pid" || crypto_status=$?' in build["run"]
    assert 'wait "$sanitizer_pid" || sanitizer_status=$?' in build["run"]
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


def test_frontend_wasm_target_is_installed_once_before_parallel_builds() -> None:
    workflow = _load(FRONTEND_WORKFLOW_PATH)
    producer = workflow["jobs"]["wasm-build"]  # type: ignore[index]
    build_run = _step(producer, "Build immutable WASM modules")["run"]

    target_install = "rustup target add wasm32-unknown-unknown"
    target_verify = (
        'rustup target list --installed | grep -Fxq "wasm32-unknown-unknown"'
    )
    first_parallel_build = "wasm-pack build rust-crypto --target web --release &"

    assert build_run.count(target_install) == 1
    assert build_run.count(target_verify) == 1
    assert build_run.index(target_install) < build_run.index(first_parallel_build)
    assert build_run.index(target_verify) < build_run.index(first_parallel_build)


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
        "run_gate deadcode npm run lint:deadcode &",
        "run_gate depcheck npm run lint:depcheck &",
    ):
        assert run.count(invocation) == 1
    assert run.count("run_gate ") == 6
    assert "wait" in run
    assert 'exit "$failed"' in run
