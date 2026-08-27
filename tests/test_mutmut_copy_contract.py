"""Ensure mutmut's isolated tree contains every repository-contract input."""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_ALSO_COPY = {
    "SECURITY.md",
    "security",
    "security/audit-allowlist.yaml",
    "start-docker.ps1",
    "frontend/openapi.json",
}


def test_mutmut_also_copy_covers_contract_inputs() -> None:
    """Contract tests must not fail collection inside mutmut's sandbox."""

    with (ROOT / "pyproject.toml").open("rb") as project_file:
        project = tomllib.load(project_file)

    configured = set(project["tool"]["mutmut"]["also_copy"])
    assert REQUIRED_ALSO_COPY <= configured

    missing = sorted(path for path in REQUIRED_ALSO_COPY if not (ROOT / path).is_file())
    assert not missing, f"also_copy contract inputs are missing: {missing}"
