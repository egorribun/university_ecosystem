"""Ensure mutmut's isolated tree contains every repository-contract input."""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_ALSO_COPY = {
    "SECURITY.md",
    "security",
    "security/audit-allowlist.yaml",
    ".agents/hooks",
    ".agents/hooks/stop_quality_gate.py",
    ".secrets.baseline",
    ".husky",
    "start-docker.ps1",
    "alembic.ini",
    "charts/revocation-store",
    "frontend/openapi.json",
    "frontend/src/api",
    "frontend/src/api/generated",
    "frontend/src/hooks",
    "frontend/src/hooks/useChatWebSocket.ts",
    "frontend/src/tests/mocks",
    "frontend/src/tests/mocks/generated",
    "k8s/ingress.yaml",
    "k8s/secrets-example.yaml",
}


def test_mutmut_also_copy_covers_contract_inputs() -> None:
    """Contract tests must not fail collection inside mutmut's sandbox."""

    with (ROOT / "pyproject.toml").open("rb") as project_file:
        project = tomllib.load(project_file)

    configured = set(project["tool"]["mutmut"]["also_copy"])
    assert REQUIRED_ALSO_COPY <= configured

    missing = sorted(path for path in REQUIRED_ALSO_COPY if not (ROOT / path).exists())
    assert not missing, f"also_copy contract inputs are missing: {missing}"


def test_mutmut_also_copy_creates_file_parents_before_exact_files() -> None:
    """The mutmut copier requires a configured directory before ``copy2``."""

    with (ROOT / "pyproject.toml").open("rb") as project_file:
        project = tomllib.load(project_file)

    configured = list(project["tool"]["mutmut"]["also_copy"])
    # ``k8s/kyverno`` creates the shared ``k8s`` destination before the two
    # root-level manifests are copied; it is therefore the parent provider for
    # those files even though ``k8s`` itself is not an ``also_copy`` entry.
    parent_providers = {
        "security/audit-allowlist.yaml": "security",
        ".agents/hooks/stop_quality_gate.py": ".agents/hooks",
        "frontend/src/hooks/useChatWebSocket.ts": "frontend/src/hooks",
        "k8s/ingress.yaml": "k8s/kyverno",
        "k8s/secrets-example.yaml": "k8s/kyverno",
    }
    for file_path, parent in parent_providers.items():
        assert configured.index(parent) < configured.index(file_path), file_path
