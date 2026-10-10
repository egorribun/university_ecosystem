"""Keep the runtime dependency hygiene gate wired into CI."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import pytest
import yaml

from scripts import s3_cutover_preflight

ROOT = Path(__file__).resolve().parents[1]


def _project() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_ci_runs_deptry_on_the_application_package() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["backend-type-check"]["steps"]
    gate = next(
        step for step in steps if step.get("name") == "Check runtime dependency hygiene"
    )

    assert gate["run"] == "uv run deptry app"
    assert "continue-on-error" not in gate


def test_deptry_is_pinned_and_scoped_to_the_application() -> None:
    project = _project()
    config = project["tool"]["deptry"]

    assert "deptry==0.25.1" in project["dependency-groups"]["dev"]
    assert config["known_first_party"] == ["app"]
    # Security floors for transitive packages are constraints, not direct
    # dependencies that the application pretends to import.
    constraints = project["tool"]["uv"]["constraint-dependencies"]
    assert "urllib3>=2.8.0,<2.9" in constraints
    assert "h2>=4.4.1,<5" in constraints
    dependencies = project["project"]["dependencies"]
    assert not any(dep.startswith(("urllib3", "h2>")) for dep in dependencies)


def test_minio_runtime_exception_is_required_by_the_cutover_entrypoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project()
    assert any(dep.startswith("minio>=") for dep in project["project"]["dependencies"])
    assert "minio" in project["tool"]["deptry"]["per_rule_ignores"]["DEP002"]
    # The cutover runbook mounts this script into the production backend image.
    # A future client replacement must remove the exception with the SDK import.
    monkeypatch.setitem(sys.modules, "minio", None)
    with pytest.raises(ModuleNotFoundError, match="minio"):
        s3_cutover_preflight._client_from_environment("SOURCE", allow_http=False)
