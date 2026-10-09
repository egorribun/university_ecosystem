"""Parsed contracts for the canonical Chaos app-lane runtime and safety gates."""

import shlex
from pathlib import Path

import yaml

WORKFLOW = (
    Path(__file__).resolve().parents[1] / ".github/workflows/nightly-full-gate.yml"
)
SETUP_PYTHON = "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97"


def _job() -> dict[str, object]:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return document["jobs"]["chaos-tests"]


def test_chaos_job_is_main_only_and_fail_closed() -> None:
    job = _job()
    assert job["if"] == "${{ github.ref == 'refs/heads/main' }}"
    assert job["runs-on"] == "ubuntu-24.04"
    assert job["timeout-minutes"] == 30
    assert job["permissions"] == {"contents": "read"}
    assert "continue-on-error" not in job
    assert all("continue-on-error" not in step for step in job["steps"])


def test_chaos_installs_pinned_python_before_dependency_sync() -> None:
    steps = _job()["steps"]
    setup = [
        step
        for step in steps
        if step.get("uses", "").startswith("actions/setup-python@")
    ]
    assert len(setup) == 1
    assert setup[0]["uses"] == SETUP_PYTHON
    assert setup[0]["with"]["python-version"] == "3.14"
    assert "if" not in setup[0]
    assert "continue-on-error" not in setup[0]
    sync = next(step for step in steps if step.get("name") == "Install dependencies")
    assert sync["run"] == "uv sync --frozen --group dev"
    assert steps.index(setup[0]) < steps.index(sync)


def test_chaos_uses_pinned_minio_and_toxiproxy_services() -> None:
    job = _job()
    services = job["services"]
    assert set(services) == {"minio", "toxiproxy"}

    minio = services["minio"]
    assert "@sha256:" in minio["image"]
    assert minio["command"] == "mini -dir=/data -s3.port=9000"
    assert minio["ports"] == ["9000:9000"]

    toxiproxy = services["toxiproxy"]
    assert "@sha256:" in toxiproxy["image"]
    assert toxiproxy["ports"] == ["8474:8474", "9003:9003"]


def test_chaos_configures_proxy_before_fail_closed_tests_and_keeps_reset_safety() -> (
    None
):
    job = _job()
    assert job["env"]["DATABASE_URL"] == "sqlite+aiosqlite:///./test_chaos.db"
    assert job["env"]["UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET"] == "1"
    steps = job["steps"]
    configure = next(
        step for step in steps if step.get("name") == "Configure ToxiProxy proxies"
    )
    assert "for _attempt in {1..30}" in configure["run"]
    assert "curl --fail --silent http://localhost:9000/status" in configure["run"]
    assert "--request POST http://localhost:8474/proxies" in configure["run"]

    tests = next(step for step in steps if step.get("name") == "Run chaos tests")
    assert shlex.split(tests["run"]) == [
        "uv",
        "run",
        "pytest",
        "tests/chaos/",
        "-v",
        "-m",
        "chaos",
        "--tb=short",
    ]
    assert steps.index(configure) < steps.index(tests)
    assert tests["env"]["UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET"] == "1"
    assert tests["env"]["MINIO_PROXY_ENDPOINT"] == "http://localhost:9003"
    assert tests["env"]["MINIO_DIRECT_ENDPOINT"] == "localhost:9000"
    assert tests["env"]["STORAGE_S3_ENDPOINT_URL"] == "http://localhost:9003"
    assert "if" not in tests
    assert "continue-on-error" not in tests
