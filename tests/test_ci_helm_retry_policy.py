"""Fail-closed tests for the bounded Helm dependency retry helper."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "ci" / "helm_dependency_build.py"


def _load_helper() -> ModuleType:
    spec = importlib.util.spec_from_file_location("helm_dependency_build", HELPER)
    if spec is None or spec.loader is None:
        raise AssertionError("unable to load Helm retry helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("failed to fetch chart: i/o timeout", True),
        ("context deadline exceeded while resolving registry", True),
        ("unexpected EOF from registry", True),
        ("received HTTP 503 Service Unavailable", True),
        ("429 Too Many Requests", True),
        ("401 Unauthorized", False),
        ("404 Not Found", False),
        ("chart metadata is invalid", False),
    ],
)
def test_helm_failure_classifier_is_narrow(output: str, expected: bool) -> None:
    helper = _load_helper()

    assert helper.is_transient_failure(output) is expected


def test_helm_helper_retries_transient_failure_and_keeps_first_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    helper = _load_helper()
    chart = tmp_path / "chart"
    chart.mkdir()
    outcomes = iter(
        [
            subprocess.CompletedProcess(
                ["helm"], 1, stdout="", stderr="first: i/o timeout\n"
            ),
            subprocess.CompletedProcess(["helm"], 0, stdout="ok\n", stderr=""),
        ]
    )
    monkeypatch.setattr(
        helper.subprocess, "run", lambda *args, **kwargs: next(outcomes)
    )
    monkeypatch.setenv("HELM_RETRY_SLEEP_BASE_SECONDS", "0")

    assert helper.main([str(chart)]) == 0
    output = capsys.readouterr().out
    assert "first: i/o timeout" in output
    assert "attempt 2" in output


def test_helm_helper_fails_fast_on_permanent_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    helper = _load_helper()
    chart = tmp_path / "chart"
    chart.mkdir()
    calls = 0

    def run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(
            ["helm"], 1, stdout="", stderr="401 Unauthorized\n"
        )

    monkeypatch.setattr(helper.subprocess, "run", run)
    monkeypatch.setenv("HELM_RETRY_SLEEP_BASE_SECONDS", "0")

    assert helper.main([str(chart)]) == 1
    assert calls == 1
    assert "non-transient" in capsys.readouterr().err


def test_helm_helper_requires_declared_archives_after_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    helper = _load_helper()
    chart = tmp_path / "chart"
    (chart / "charts").mkdir(parents=True)
    monkeypatch.setattr(
        helper.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            ["helm"], 0, stdout="ok\n", stderr=""
        ),
    )

    assert helper.main([str(chart), "redis-20.13.4.tgz"]) == 1


DIRECT_HELM_HELPER_WORKFLOWS = (
    ".github/workflows/ci.yml",
    ".github/workflows/deploy.yml",
    ".github/workflows/reusable-backend-tests.yml",
    ".github/workflows/reusable-security-audit.yml",
    ".github/workflows/reusable-full-backend-mutation.yml",
    ".github/workflows/reusable-helm-dependencies.yml",
)


def _workflow_job_block(source: str, job_name: str) -> str:
    lines = source.splitlines()
    header = f"  {job_name}:"
    starts = [index for index, line in enumerate(lines) if line == header]
    if len(starts) != 1:
        raise AssertionError("expected_one_helm_workflow_job")
    start = starts[0]
    end = next(
        (
            index
            for index in range(start + 1, len(lines))
            if lines[index].startswith("  ")
            and not lines[index].startswith("    ")
            and lines[index].endswith(":")
        ),
        len(lines),
    )
    return "\n".join(lines[start:end])


@pytest.mark.parametrize("workflow", DIRECT_HELM_HELPER_WORKFLOWS)
def test_helm_workflows_use_the_fail_closed_retry_helper(workflow: str) -> None:
    source = (ROOT / workflow).read_text(encoding="utf-8")

    assert "scripts/ci/helm_dependency_build.py" in source
    assert "helm dependency build" not in source


@pytest.mark.parametrize(
    ("workflow", "producer_job", "consumer_job"),
    [
        (
            ".github/workflows/nightly-full-gate.yml",
            "nightly-helm-dependencies",
            "mutation-tests-full",
        ),
        (
            ".github/workflows/manual-mutation-evidence.yml",
            "manual-full-helm-dependencies",
            "manual-full-backend-mutation",
        ),
    ],
)
def test_helm_workflow_callers_preserve_source_and_artifact_contract(
    workflow: str, producer_job: str, consumer_job: str
) -> None:
    source = (ROOT / workflow).read_text(encoding="utf-8")
    producer = _workflow_job_block(source, producer_job)
    consumer = _workflow_job_block(source, consumer_job)

    assert "uses: ./.github/workflows/reusable-helm-dependencies.yml" in producer
    assert "source_sha: ${{ github.sha }}" in producer
    assert producer_job in consumer
    expected_artifact = (
        "helm_artifact_name: ${{ needs." + producer_job + ".outputs.artifact_name }}"
    )
    assert expected_artifact in consumer

    reusable = (ROOT / ".github/workflows/reusable-helm-dependencies.yml").read_text(
        encoding="utf-8"
    )
    assert "source_sha != github_sha" in reusable
    assert 'artifact_prefix = "nightly-helm-dependencies-"' in reusable
    assert 'artifact_prefix = "manual-full-helm-dependencies-"' in reusable
    assert "value: ${{ jobs.produce.outputs.artifact_name }}" in reusable
