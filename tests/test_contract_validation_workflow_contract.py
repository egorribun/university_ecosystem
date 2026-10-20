"""Exercise the OpenAPI gate's event baseline in real, shallow Git checkouts."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from shutil import which
from typing import Any

import pytest
import yaml

from scripts.quality import check_prometheus_alert_rules as alert_contract

WORKFLOW = (
    Path(__file__).resolve().parents[1] / ".github/workflows/contract-validation.yml"
)
SNAPSHOT = Path("tests/contracts/snapshots/api_openapi_v1.json")


def _job() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["openapi-diff"]


def _spectral_job() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["spectral-lint"]


def test_spectral_openapi_generation_uses_test_only_environment() -> None:
    job = _spectral_job()
    assert job["env"] == {
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "ENVIRONMENT": "testing",
        "SECRET_KEY": "",
    }
    steps = job["steps"]
    configure = next(
        step
        for step in steps
        if step.get("name") == "Configure ephemeral application secret"
    )
    generate = next(
        step
        for step in steps
        if step.get("name") == "Generate OpenAPI spec from FastAPI app"
    )
    assert steps.index(configure) < steps.index(generate)
    assert configure["shell"] == "bash"
    assert 'secret="$(openssl rand -hex 32)"' in configure["run"]
    assert 'echo "::add-mask::$secret"' in configure["run"]
    assert "SECRET_KEY=%s" in configure["run"]
    assert "$GITHUB_ENV" in configure["run"]


def _baseline_step() -> dict[str, Any]:
    steps = [step for step in _job()["steps"] if step.get("id") == "openapi_baseline"]
    assert len(steps) == 1, "The gate must extract the immutable event baseline"
    return steps[0]


def _git(repository: Path, *args: str) -> str:
    git = which("git")
    assert git is not None, "Git is required for the real baseline regression"
    return subprocess.run(  # noqa: S603 -- resolved Git, fixture-owned arguments
        [git, *args],
        cwd=repository,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def _schema(*paths: str) -> dict[str, Any]:
    return {
        "openapi": "3.0.3",
        "info": {"title": "Baseline regression", "version": "1.0.0"},
        "paths": {
            path: {"get": {"responses": {"200": {"description": "OK"}}}}
            for path in paths
        },
    }


def _checkout(
    tmp_path: Path, baseline: str | None, candidate: dict[str, Any]
) -> tuple[Path, str, str]:
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "--initial-branch=main")
    _git(origin, "config", "user.name", "Baseline test")
    _git(origin, "config", "user.email", "baseline@example.invalid")
    (origin / "README").write_text("fixture\n", encoding="utf-8")
    snapshot = origin / SNAPSHOT
    snapshot.parent.mkdir(parents=True)
    if baseline is not None:
        snapshot.write_text(baseline, encoding="utf-8")
    _git(origin, "add", ".")
    _git(origin, "commit", "-m", "baseline")
    base_sha = _git(origin, "rev-parse", "HEAD")
    snapshot.write_text(json.dumps(candidate), encoding="utf-8")
    _git(origin, "add", ".")
    _git(origin, "commit", "--allow-empty", "-m", "candidate snapshot update")
    candidate_sha = _git(origin, "rev-parse", "HEAD")
    checkout = tmp_path / "checkout"
    _git(tmp_path, "clone", "--depth=1", origin.as_uri(), str(checkout))
    assert _git(checkout, "rev-list", "--count", "HEAD") == "1"
    return checkout, base_sha, candidate_sha


def _extract(
    checkout: Path,
    tmp_path: Path,
    event: str,
    pr_base: str,
    push_before: str,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    runner_temp = tmp_path / "runner temp"
    runner_temp.mkdir()
    output = runner_temp / "step-output"
    env = {
        **os.environ,
        "EVENT_NAME": event,
        "PR_BASE_SHA": pr_base,
        "PUSH_BEFORE_SHA": push_before,
        "RUNNER_TEMP": str(runner_temp),
        "GITHUB_OUTPUT": str(output),
    }
    bash = which("bash")
    assert bash is not None, "Bash is required to exercise the workflow step"
    result = subprocess.run(  # noqa: S603 -- resolved Bash, checked-in workflow script
        [
            bash,
            "--noprofile",
            "--norc",
            "-eo",
            "pipefail",
            "-c",
            _baseline_step()["run"],
        ],
        cwd=checkout,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return result, output


@pytest.mark.parametrize("event", ["pull_request", "push"])
def test_candidate_snapshot_update_cannot_hide_removed_endpoint(
    tmp_path: Path, event: str
) -> None:
    baseline = _schema("/retained", "/removed")
    candidate = _schema("/retained")
    checkout, base_sha, candidate_sha = _checkout(
        tmp_path, json.dumps(baseline), candidate
    )
    result, output = _extract(
        checkout,
        tmp_path,
        event,
        base_sha if event == "pull_request" else candidate_sha,
        base_sha if event == "push" else candidate_sha,
    )

    assert result.returncode == 0, result.stderr
    baseline_path = Path(
        output.read_text(encoding="utf-8").strip().removeprefix("path=")
    )
    extracted = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert extracted == baseline
    assert json.loads((checkout / SNAPSHOT).read_text(encoding="utf-8")) == candidate
    assert set(extracted["paths"]) - set(candidate["paths"]) == {"/removed"}
    assert _git(checkout, "rev-parse", "HEAD") == candidate_sha


@pytest.mark.parametrize("event", ["pull_request", "push"])
def test_additive_candidate_preserves_the_old_comparison_surface(
    tmp_path: Path, event: str
) -> None:
    baseline = _schema("/retained")
    candidate = _schema("/retained", "/added")
    checkout, base_sha, _ = _checkout(tmp_path, json.dumps(baseline), candidate)
    result, output = _extract(checkout, tmp_path, event, base_sha, base_sha)

    assert result.returncode == 0, result.stderr
    baseline_path = Path(
        output.read_text(encoding="utf-8").strip().removeprefix("path=")
    )
    extracted = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert extracted == baseline
    assert set(extracted["paths"]) <= set(candidate["paths"])


@pytest.mark.parametrize("event", ["pull_request", "push"])
@pytest.mark.parametrize(
    "invalid_sha",
    ["", "0" * 40, "f" * 40, "main", "a" * 39, "g" * 40, "$(touch injected)"],
)
def test_invalid_event_baseline_fails_without_using_candidate_snapshot(
    tmp_path: Path, event: str, invalid_sha: str
) -> None:
    candidate = _schema("/retained")
    checkout, base_sha, _ = _checkout(tmp_path, json.dumps(candidate), candidate)
    result, output = _extract(
        checkout,
        tmp_path,
        event,
        invalid_sha if event == "pull_request" else base_sha,
        invalid_sha if event == "push" else base_sha,
    )

    assert result.returncode != 0
    assert not output.exists(), "A failed extraction must not publish a baseline"
    assert not (checkout / "injected").exists()


@pytest.mark.parametrize("baseline", [None, ""])
def test_missing_or_empty_base_snapshot_fails_closed(
    tmp_path: Path, baseline: str | None
) -> None:
    checkout, base_sha, _ = _checkout(tmp_path, baseline, _schema("/retained"))
    result, output = _extract(checkout, tmp_path, "pull_request", base_sha, base_sha)

    assert result.returncode != 0
    assert not output.exists()


def test_unsupported_event_fails_closed(tmp_path: Path) -> None:
    candidate = _schema("/retained")
    checkout, base_sha, _ = _checkout(tmp_path, json.dumps(candidate), candidate)
    result, output = _extract(
        checkout, tmp_path, "workflow_dispatch", base_sha, base_sha
    )

    assert result.returncode != 0
    assert not output.exists()


def test_comparison_uses_extracted_event_snapshot_and_existing_err_policy() -> None:
    job = _job()
    steps = job["steps"]
    extraction = _baseline_step()
    comparison = steps[steps.index(extraction) + 1]

    assert job["name"] == "OpenAPI Backward Compatibility Check"
    assert job["permissions"] == {"contents": "read"}
    assert extraction["env"] == {
        "EVENT_NAME": "${{ github.event_name }}",
        "PR_BASE_SHA": "${{ github.event.pull_request.base.sha }}",
        "PUSH_BEFORE_SHA": "${{ github.event.before }}",
    }
    assert "${{" not in extraction["run"]
    assert steps.index(extraction) > next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "Generate current PR OpenAPI spec"
    )
    assert comparison["env"] == {
        "BASELINE_OPENAPI": "${{ steps.openapi_baseline.outputs.path }}"
    }
    assert '"$BASELINE_OPENAPI"' in comparison["run"]
    assert "pr-openapi.json" in comparison["run"]
    assert "--fail-on ERR" in comparison["run"]
    assert "tests/contracts/snapshots" not in comparison["run"]
    assert any(
        step.get("run") == "npm install --global @oasdiff-js/oasdiff-js@1.0.0"
        for step in steps
    )


def test_prometheus_generator_preserves_actual_rule_groups() -> None:
    source = WORKFLOW.parents[2] / "k8s/monitoring/prometheus-rules.yaml"
    manifest = yaml.safe_load(source.read_text(encoding="utf-8"))

    assert alert_contract.rules() == {"groups": manifest["spec"]["groups"]}


def _existing_prometheus_image() -> str:
    source = WORKFLOW.parents[2] / "docker-compose.observability.yml"
    node = yaml.compose(
        source.read_text(encoding="utf-8"),
        Loader=yaml.SafeLoader,
    )
    for name in ("services", "prometheus", "image"):
        assert isinstance(node, yaml.MappingNode)
        assert node.tag == "tag:yaml.org,2002:map"
        matches = [
            value
            for key, value in node.value
            if isinstance(key, yaml.ScalarNode)
            and key.tag == "tag:yaml.org,2002:str"
            and key.value == name
        ]
        assert len(matches) == 1
        node = matches[0]

    assert isinstance(node, yaml.ScalarNode)
    assert node.tag == "tag:yaml.org,2002:str"
    return node.value


def test_prometheus_generator_uses_the_existing_compose_image() -> None:
    assert alert_contract.image() == _existing_prometheus_image()


@pytest.mark.parametrize(
    "reference",
    [
        "prom/prometheus:latest",
        "prom/prometheus:v3.15.0",
        "untrusted/prometheus:v3.15.0@sha256:" + "a" * 64,
        "prom/prometheus:v3.15.0@sha256:" + "a" * 63,
    ],
)
def test_prometheus_generator_image_cli_rejects_unpinned_or_wrong_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    reference: str,
) -> None:
    (tmp_path / "docker-compose.observability.yml").write_text(
        yaml.safe_dump({"services": {"prometheus": {"image": reference}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(alert_contract, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["alert-contract", "image"])

    with pytest.raises(ValueError, match="immutable official Prometheus image"):
        alert_contract.main()

    assert capsys.readouterr().out == ""


def test_prometheus_generator_has_six_actual_metric_boundary_cases() -> None:
    generated = alert_contract.fixture()
    assert generated["rule_files"] == ["rules.json"]
    assert generated["evaluation_interval"] == "30s"
    tests = generated["tests"]
    assert isinstance(tests, list)
    assert len(tests) == 6
    by_name = {case["name"]: case for case in tests}
    assert len(by_name) == 6

    expected = {
        "OutboxStagnant": (
            {"outbox_pending_events_total": 101},
            {"outbox_pending_events_total": 100},
            "4m30s",
            "5m",
        ),
        "DatabasePoolSaturation": (
            {"db_pool_checkedout": 9, "db_pool_size": 10},
            {"db_pool_checkedout": 8, "db_pool_size": 10},
            "4m30s",
            "5m",
        ),
        "DatabasePoolExhausted": (
            {"db_pool_checkedout": 10, "db_pool_size": 10},
            {"db_pool_checkedout": 9, "db_pool_size": 10},
            "30s",
            "1m",
        ),
    }
    assert set(by_name) == {
        f"{alert}-{level}" for alert in expected for level in ("high", "low")
    }

    for alert, (high, low, pending_time, firing_time) in expected.items():
        for level, series in (("high", high), ("low", low)):
            case = by_name[f"{alert}-{level}"]
            assert case["interval"] == "30s"
            assert case["input_series"] == [
                {"series": name, "values": f"{value}+0x12"}
                for name, value in series.items()
            ]
            checks = case["promql_expr_test"]
            if level == "high":
                expected_checks = [
                    (pending_time, "pending", 1),
                    (pending_time, "firing", 0),
                    (firing_time, "pending", 0),
                    (firing_time, "firing", 1),
                ]
            else:
                expected_checks = [
                    ("6m", "pending", 0),
                    ("6m", "firing", 0),
                ]

            assert len(checks) == len(expected_checks)
            for check, (time, state, value) in zip(
                checks, expected_checks, strict=True
            ):
                assert check == {
                    "expr": (
                        f'count(ALERTS{{alertname="{alert}",'
                        f'alertstate="{state}"}}) or vector(0)'
                    ),
                    "eval_time": time,
                    "exp_samples": [{"labels": "{}", "value": value}],
                }


def test_prometheus_image_cli_ignores_unrelated_compose_tags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    reference = _existing_prometheus_image()
    (tmp_path / "docker-compose.observability.yml").write_text(
        "services:\n"
        "  unrelated:\n"
        "    ports: !override []\n"
        "  prometheus:\n"
        f"    image: {reference}\n"
        "    ports: !override []\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(alert_contract, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["alert-contract", "image"])

    alert_contract.main()

    assert capsys.readouterr().out == f"{reference}\n"


@pytest.mark.parametrize(
    "document",
    [
        "services: {}\nservices: {}\n",
        "services:\n  prometheus: {}\n  prometheus: {}\n",
        "services:\n  prometheus:\n    image: $IMAGE\n    image: $IMAGE\n",
        "{}\n",
        "services: {}\n",
        "services:\n  prometheus: {}\n",
        "services: !override {}\n",
        "services:\n  prometheus: !override {}\n",
        "services:\n  prometheus:\n    image: !override $IMAGE\n",
        "services:\n  prometheus:\n    image: 123\n",
        "services:\n  prometheus:\n    image: {}\n",
        "services:\n  prometheus:\n    image: $IMAGE\n    123: ignored\n",
    ],
)
def test_prometheus_image_cli_rejects_ambiguous_or_nonstring_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    document: str,
) -> None:
    reference = _existing_prometheus_image()
    (tmp_path / "docker-compose.observability.yml").write_text(
        document.replace("$IMAGE", reference),
        encoding="utf-8",
    )
    monkeypatch.setattr(alert_contract, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["alert-contract", "image"])

    with pytest.raises(ValueError, match="immutable official Prometheus image"):
        alert_contract.main()

    assert capsys.readouterr().out == ""
