from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "quality" / "migration_downgrade_policy.py"
MIGRATIONS_DIR = ROOT / "alembic" / "versions"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"


def _load_policy_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "migration_downgrade_policy", SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_migration(
    directory: Path,
    *,
    revision: str,
    down_revision: str | None,
    downgrade_body: str = "pass",
    policy: str = "",
) -> None:
    parent = "None" if down_revision is None else repr(down_revision)
    (directory / f"{revision}.py").write_text(
        "\n".join(
            [
                f"revision: str = {revision!r}",
                f"down_revision: str | None = {parent}",
                policy,
                "",
                "def upgrade() -> None:",
                "    pass",
                "",
                "def downgrade() -> None:",
                f"    {downgrade_body}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_plan_stops_at_latest_declared_irreversible_boundary(tmp_path: Path) -> None:
    policy = _load_policy_module()
    _write_migration(tmp_path, revision="base1", down_revision=None)
    _write_migration(
        tmp_path,
        revision="barrier2",
        down_revision="base1",
        policy=(
            'downgrade_policy: str = "irreversible"\n'
            'downgrade_reason: str = "destroyed legacy credentials"'
        ),
        downgrade_body="raise RuntimeError(downgrade_reason)",
    )
    _write_migration(tmp_path, revision="head3", down_revision="barrier2")

    plan = policy.build_downgrade_plan(tmp_path)

    assert plan.head_revision == "head3"
    assert plan.safe_target == "barrier2"
    assert plan.boundary_revision == "barrier2"
    assert plan.boundary_parent == "base1"
    assert plan.boundary_reason == "destroyed legacy credentials"


@pytest.mark.parametrize(
    ("policy_declaration", "downgrade_body", "error"),
    [
        ("", 'raise RuntimeError("undeclared")', "without an irreversible policy"),
        (
            'downgrade_policy = "irreversible"\ndowngrade_reason = "declared reason"',
            'raise RuntimeError("different reason")',
            "does not raise the declared reason",
        ),
        (
            'downgrade_policy = "irreversible"\ndowngrade_reason = "declared reason"',
            "pass",
            "must fail before changing schema",
        ),
    ],
)
def test_plan_rejects_ambiguous_or_unsafe_irreversible_contracts(
    tmp_path: Path,
    policy_declaration: str,
    downgrade_body: str,
    error: str,
) -> None:
    policy = _load_policy_module()
    _write_migration(
        tmp_path,
        revision="barrier",
        down_revision=None,
        policy=policy_declaration,
        downgrade_body=downgrade_body,
    )

    with pytest.raises(policy.PolicyError, match=error):
        policy.build_downgrade_plan(tmp_path)


def test_plan_rejects_multiple_heads_instead_of_guessing_a_downgrade_path(
    tmp_path: Path,
) -> None:
    policy = _load_policy_module()
    _write_migration(tmp_path, revision="base", down_revision=None)
    _write_migration(tmp_path, revision="left", down_revision="base")
    _write_migration(tmp_path, revision="right", down_revision="base")

    with pytest.raises(policy.PolicyError, match="exactly one migration head"):
        policy.build_downgrade_plan(tmp_path)


def test_runtime_barrier_accepts_only_the_exact_declared_failure(
    tmp_path: Path,
) -> None:
    policy = _load_policy_module()
    _write_migration(
        tmp_path,
        revision="barrier",
        down_revision=None,
        policy=(
            'downgrade_policy = "irreversible"\n'
            'downgrade_reason = "credential material was shredded"'
        ),
        downgrade_body="raise RuntimeError(downgrade_reason)",
    )
    plan = policy.build_downgrade_plan(tmp_path)

    def expected_failure(_target: str) -> None:
        raise RuntimeError("credential material was shredded")

    policy.assert_declared_boundary(plan, expected_failure)

    def unexpected_failure(_target: str) -> None:
        raise RuntimeError("database connection failed")

    with pytest.raises(policy.PolicyError, match="unexpected error"):
        policy.assert_declared_boundary(plan, unexpected_failure)

    with pytest.raises(policy.PolicyError, match="allowed the downgrade"):
        policy.assert_declared_boundary(plan, lambda _target: None)

    incomplete = policy.DowngradePlan("head", "barrier", "barrier", None, None)
    with pytest.raises(policy.PolicyError, match="incomplete"):
        policy.assert_declared_boundary(incomplete, lambda _target: None)


def test_repository_migrations_have_a_valid_fail_closed_downgrade_plan() -> None:
    policy = _load_policy_module()

    plan = policy.build_downgrade_plan(MIGRATIONS_DIR)

    assert plan.safe_target == "202608250002"
    assert plan.boundary_parent == "202608250001"


def test_all_postgres_gates_exercise_safe_range_and_declared_boundary() -> None:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    jobs: dict[str, Any] = workflow["jobs"]

    for job_name in (
        "alembic-migrations",
        "db-migration-gate",
        "db-migration-integrity",
    ):
        steps = jobs[job_name]["steps"]
        combined = "\n".join(str(step.get("run", "")) for step in steps)
        assert "migration_downgrade_policy.py plan" in combined
        assert "migration_downgrade_policy.py assert-boundary" in combined
        assert "alembic downgrade base" not in combined
        assert 'downgrade "$SAFE_DOWNGRADE_TARGET"' in combined
