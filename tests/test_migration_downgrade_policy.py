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
BACKEND_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "reusable-backend-tests.yml"
BASELINE_BOUNDARY_REASON = (
    "The MVP baseline cannot be downgraded: reaching base or any earlier schema "
    "is not a supported recovery path. Restore a consistent backup set instead."
)


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


def test_repository_baseline_is_the_single_irreversible_boundary() -> None:
    policy = _load_policy_module()

    metadata = policy._parse_migration(MIGRATIONS_DIR / "202611020000_mvp_baseline.py")

    assert metadata.revision == "202611020000"
    assert metadata.parents == ()
    assert metadata.irreversible_reason == BASELINE_BOUNDARY_REASON


def test_retired_reviewed_preflight_name_is_not_a_reviewed_exception(
    tmp_path: Path,
) -> None:
    policy = _load_policy_module()
    _write_migration(
        tmp_path,
        revision="202609250001",
        down_revision=None,
        downgrade_body=(
            "if state.default_sql is None:\n"
            '        raise RuntimeError("missing required default")'
        ),
        policy=(
            'downgrade_policy = "guarded_preflight"\n'
            'downgrade_preflight_reason = "catalog preflight"'
        ),
    )

    with pytest.raises(policy.PolicyError, match="unreviewed guarded preflight"):
        policy._parse_migration(tmp_path / "202609250001.py")


def test_plan_requires_an_explicit_policy_for_guarded_preflight_raises(
    tmp_path: Path,
) -> None:
    policy = _load_policy_module()
    _write_migration(
        tmp_path,
        revision="undeclared",
        down_revision=None,
        downgrade_body=(
            "if state.default_sql is None:\n"
            '        raise RuntimeError("missing required default")'
        ),
    )

    with pytest.raises(
        policy.PolicyError, match="downgrade raises without an irreversible policy"
    ):
        policy.build_downgrade_plan(tmp_path)


@pytest.mark.parametrize(
    "downgrade_body",
    [
        'if True:\n        raise RuntimeError("always abort")',
        'if state_is_valid:\n        raise RuntimeError("unreviewed guard")',
        (
            "if state_is_valid:\n"
            '        raise RuntimeError("first branch")\n'
            "    else:\n"
            '        raise RuntimeError("second branch")'
        ),
        (
            'op.drop_table("users")\n'
            "    if missing_default:\n"
            '        raise RuntimeError("too late to guard")'
        ),
    ],
)
def test_plan_rejects_unconditional_or_late_guarded_raises(
    tmp_path: Path, downgrade_body: str
) -> None:
    policy = _load_policy_module()
    _write_migration(
        tmp_path,
        revision="unsafe",
        down_revision=None,
        policy=(
            'downgrade_policy = "guarded_preflight"\n'
            'downgrade_preflight_reason = "retain defaults unless catalog is complete"'
        ),
        downgrade_body=downgrade_body,
    )

    with pytest.raises(
        policy.PolicyError, match="downgrade raises without an irreversible policy"
    ):
        policy.build_downgrade_plan(tmp_path)


def test_plan_rejects_unconditional_abort_hidden_in_helper(tmp_path: Path) -> None:
    policy = _load_policy_module()
    _write_migration(
        tmp_path,
        revision="hidden_abort",
        down_revision=None,
        policy=(
            'downgrade_policy = "guarded_preflight"\n'
            'downgrade_preflight_reason = "retain defaults unless catalog is complete"\n'
            "\n"
            "def _abort() -> None:\n"
            '    raise RuntimeError("always abort")'
        ),
        downgrade_body=(
            "state = inspect_default()\n"
            "    if state.default_sql is None:\n"
            '        raise RuntimeError("missing required default")\n'
            "    _abort()"
        ),
    )

    with pytest.raises(
        policy.PolicyError, match="downgrade raises without an irreversible policy"
    ):
        policy.build_downgrade_plan(tmp_path)


def test_plan_rejects_schema_write_hidden_in_helper_before_preflight(
    tmp_path: Path,
) -> None:
    policy = _load_policy_module()
    _write_migration(
        tmp_path,
        revision="hidden_write",
        down_revision=None,
        policy=(
            'downgrade_policy = "guarded_preflight"\n'
            'downgrade_preflight_reason = "retain defaults unless catalog is complete"\n'
            "\n"
            "def _drop() -> None:\n"
            '    op.drop_table("users")'
        ),
        downgrade_body=(
            "_drop()\n"
            "    state = inspect_default()\n"
            "    if state.default_sql is None:\n"
            '        raise RuntimeError("missing required default")'
        ),
    )

    with pytest.raises(
        policy.PolicyError, match="downgrade raises without an irreversible policy"
    ):
        policy.build_downgrade_plan(tmp_path)


def test_plan_rejects_ddl_disguised_as_reviewed_lock_helper(tmp_path: Path) -> None:
    policy = _load_policy_module()
    _write_migration(
        tmp_path,
        revision="disguised_write",
        down_revision=None,
        policy=(
            'downgrade_policy = "guarded_preflight"\n'
            'downgrade_preflight_reason = "retain defaults unless catalog is complete"\n'
            "\n"
            "def _lock_targets() -> None:\n"
            '    op.execute(sa.text("DROP TABLE users"))'
        ),
        downgrade_body=(
            "_lock_targets()\n"
            "    state = inspect_default()\n"
            "    if state.default_sql is None:\n"
            '        raise RuntimeError("missing required default")'
        ),
    )

    with pytest.raises(
        policy.PolicyError, match="downgrade raises without an irreversible policy"
    ):
        policy.build_downgrade_plan(tmp_path)


def test_plan_rejects_dynamic_sql_disguised_as_reviewed_table_lock(
    tmp_path: Path,
) -> None:
    policy = _load_policy_module()
    _write_migration(
        tmp_path,
        revision="dynamic_lock",
        down_revision=None,
        policy=(
            'downgrade_policy = "guarded_preflight"\n'
            'downgrade_preflight_reason = "retain defaults unless catalog is complete"\n'
            "\n"
            "def _lock_targets() -> None:\n"
            '    qualified_schema = "users; DROP TABLE users; --"\n'
            '    qualified_table = "ignored"\n'
            "    op.execute(sa.text("
            'f"LOCK TABLE {qualified_schema}.{qualified_table} "'
            '"IN ACCESS EXCLUSIVE MODE"))'
        ),
        downgrade_body=(
            "_lock_targets()\n"
            "    state = inspect_default()\n"
            "    if state.default_sql is None:\n"
            '        raise RuntimeError("missing required default")'
        ),
    )

    with pytest.raises(
        policy.PolicyError, match="downgrade raises without an irreversible policy"
    ):
        policy.build_downgrade_plan(tmp_path)


@pytest.mark.parametrize(
    "downgrade_body",
    [
        (
            'bind.execute(sa.text("DROP TABLE users"))\n'
            "    state = inspect_default()\n"
            "    if state.default_sql is None:\n"
            '        raise RuntimeError("missing required default")'
        ),
        (
            "execute = op.execute\n"
            '    execute(sa.text("DROP TABLE users"))\n'
            "    state = inspect_default()\n"
            "    if state.default_sql is None:\n"
            '        raise RuntimeError("missing required default")'
        ),
        (
            "state = inspect_default()\n"
            "    try:\n"
            "        if state.default_sql is None:\n"
            '            raise RuntimeError("missing required default")\n'
            "    finally:\n"
            '        op.drop_table("users")'
        ),
        (
            "state = inspect_default()\n"
            "    if state.default_sql is None:\n"
            "        pass\n"
            "    else:\n"
            '        raise RuntimeError("wrong branch")'
        ),
        (
            "state = SimpleNamespace(default_sql=None)\n"
            "    if state.default_sql is None:\n"
            '        raise RuntimeError("fabricated state")'
        ),
    ],
)
def test_plan_rejects_unreviewed_guarded_preflight_shapes(
    tmp_path: Path, downgrade_body: str
) -> None:
    policy = _load_policy_module()
    _write_migration(
        tmp_path,
        revision="202609250001",
        down_revision=None,
        policy=(
            'downgrade_policy = "guarded_preflight"\n'
            'downgrade_preflight_reason = "retain defaults unless catalog is complete"'
        ),
        downgrade_body=downgrade_body,
    )
    (tmp_path / "202609250001.py").rename(
        tmp_path / "202609250001_phase_semantic_defaults.py"
    )

    with pytest.raises(policy.PolicyError, match="unreviewed guarded preflight"):
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

    assert sorted(path.name for path in MIGRATIONS_DIR.glob("*.py")) == [
        "202611020000_mvp_baseline.py"
    ]
    assert plan.head_revision == "202611020000"
    assert plan.safe_target == "202611020000"
    assert plan.boundary_revision == "202611020000"
    assert plan.boundary_parent == "base"
    assert plan.boundary_reason == BASELINE_BOUNDARY_REASON


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


def test_reusable_postgres_gate_checks_refusal_without_masking_failures() -> None:
    workflow = yaml.safe_load(BACKEND_WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["integration-tests"]["steps"]
    planners = [
        step for step in steps if step.get("id") == "integration-migration-policy"
    ]
    gates = [
        step
        for step in steps
        if step.get("name") == "Test migration downgrade safety (MOD-03)"
    ]
    assert len(planners) == len(gates) == 1
    planner, gate = planners[0], gates[0]
    assert steps.index(planner) < steps.index(gate)
    for step in (planner, gate):
        assert step["shell"] == "bash"
        assert step["run"].startswith("set -euo pipefail\n")
        assert not step.get("continue-on-error", False)
        assert "|| true" not in step["run"]
    assert 'migration_downgrade_policy.py plan >> "$GITHUB_OUTPUT"' in planner["run"]
    assert gate["env"]["SAFE_DOWNGRADE_TARGET"] == (
        "${{ steps.integration-migration-policy.outputs.safe_target }}"
    )

    run = gate["run"]
    commands = [
        'uv run --frozen --no-sync alembic downgrade "$SAFE_DOWNGRADE_TARGET"',
        'before_boundary="$(uv run --frozen --no-sync alembic current)"',
        'test -n "$before_boundary"',
        "uv run --frozen --no-sync python "
        "scripts/quality/migration_downgrade_policy.py assert-boundary",
        'after_boundary="$(uv run --frozen --no-sync alembic current)"',
        'if [[ "$before_boundary" != "$after_boundary" ]]; then',
        'echo "Declared boundary probe changed the applied migration revision" >&2',
        "exit 1",
    ]
    positions = [run.index(command) for command in commands]
    assert positions == sorted(positions)
    assert run.count("uv run --frozen --no-sync alembic upgrade head") == 2
    assert run.rindex("alembic upgrade head") > positions[-1]
    assert "alembic downgrade -1" not in run
    assert "alembic downgrade base" not in run
    assert "Migration round-trip succeeded" not in run
    assert (
        "Supported migration range and declared refusal verified; "
        "protected boundary was not crossed"
    ) in run


def test_postgres_migration_gates_pin_python_before_uv() -> None:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    jobs: dict[str, Any] = workflow["jobs"]

    for job_name in (
        "alembic-migrations",
        "db-migration-gate",
        "db-migration-integrity",
    ):
        steps = jobs[job_name]["steps"]
        python_steps = [
            (index, step)
            for index, step in enumerate(steps)
            if str(step.get("uses", "")).startswith("actions/setup-python@")
        ]
        uv_steps = [
            index
            for index, step in enumerate(steps)
            if str(step.get("uses", "")).startswith("astral-sh/setup-uv@")
        ]
        assert len(python_steps) == len(uv_steps) == 1, job_name
        python_index, python_step = python_steps[0]
        assert python_step["uses"] == (
            "actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0"
        ), job_name
        assert python_step["with"]["python-version"] == "3.14", job_name
        assert python_index < uv_steps[0], job_name

    for job_name in ("db-migration-gate", "db-migration-integrity"):
        assert jobs[job_name]["env"]["UV_PYTHON"] == "3.14", job_name


def _mvp_rollback_adr_section() -> str:
    path = ROOT / "docs" / "adr" / "ADR-036-sqlalchemy-dual-default-migration-policy.md"
    source = path.read_text(encoding="utf-8")
    heading = "## MVP Release Rollback Boundary (Owner Decision, 2026-10-12)"
    assert source.count(heading) == 1
    section = source.split(heading, 1)[1].split("\n## ", 1)[0]
    assert section.strip()
    return section


def test_baseline_adr_matches_current_plan_without_rewriting_historical_scope() -> None:
    """ADR-051 governs the fresh baseline; ADR-036 remains a historical record."""
    policy = _load_policy_module()
    plan = policy.build_downgrade_plan(MIGRATIONS_DIR)
    baseline_adr = (
        ROOT / "docs" / "adr" / "ADR-051-mvp-migration-baseline-squash.md"
    ).read_text(encoding="utf-8")
    normalized = " ".join(baseline_adr.split())

    assert f"one baseline revision, `{plan.head_revision}`" in normalized
    assert "`down_revision = None`" in normalized
    assert '`downgrade_policy = "irreversible"`' in normalized
    assert "Its `downgrade()` raises before it changes any schema." in normalized
    assert "There is no upgrade path from a pre-squash database." in normalized
    assert "a downgrade to base is refused." in normalized
    assert plan.safe_target == plan.head_revision == plan.boundary_revision
    assert plan.boundary_parent == "base"
    assert plan.boundary_reason == BASELINE_BOUNDARY_REASON
    assert (
        "The rollback-boundary section of ADR-036 and the Tier 0 exception text of "
        "ADR-047 need their own amendments through their ADR processes."
    ) in normalized

    historical = " ".join(_mvp_rollback_adr_section().split())
    assert (
        "The newest irreversible revision is 202610250001, "
        "whose parent is 202610200001."
    ) in historical
    assert (
        "A verified refusal is not a successful rollback across the boundary."
    ) in historical
    assert (
        "The original owner decision does not make later data-loss barriers reversible."
    ) in historical


def test_adr_rollback_scope_maps_eight_unsupported_historical_findings() -> None:
    """A scope record alone is not a repair, a ledger increment or restore evidence."""
    section = _mvp_rollback_adr_section()
    rows = [
        tuple(cell.strip() for cell in line.strip().strip("|").split("|"))
        for line in section.splitlines()
        if line.startswith("| AUD-")
    ]
    expected_operations = [
        ("AUD-268", "202607020001"),
        ("AUD-273", "202607230001"),
        ("AUD-276", "202503150001"),
        ("AUD-324", "202607280001"),
        ("AUD-325", "202605070001"),
        ("AUD-326", "Downgrade to base"),
        ("AUD-349", "148642dd1207"),
        ("AUD-435", "Relative downgrade at 7ad848733a4b"),
    ]
    assert all(len(row) == 3 for row in rows)
    assert [row[:2] for row in rows] == expected_operations
    expected_limits = {
        "AUD-268": "drops monthly and default partitions, including their rows",
        "AUD-273": "older message RLS migration remains applied",
        "AUD-276": "invalid token can become NULL",
        "AUD-324": "still drops grades and vector_chunks",
        "AUD-325": "deletes failed_login_attempts rows whose user_id is NULL",
        "AUD-326": "reaching base is not a supported recovery path",
        "AUD-349": "without retaining their data",
        "AUD-435": "no repair of historical relative-target resolution is claimed",
    }
    for finding, _operation, limitation in rows:
        assert expected_limits[finding] in limitation, finding

    normalized = " ".join(section.split())
    for boundary in (
        "without claiming that their historical downgrade implementations were "
        "repaired.",
        "This scope record alone does not add findings to the accepted audit ledger.",
        "Migration-local barriers protect only paths that execute them.",
        "A database already below a barrier, an explicit offline revision range "
        "or a direct historical migration call is not made safe by a later barrier.",
        "a database still at 202607280001 is not safe to downgrade.",
        "Choosing an older explicit target or a relative target does not "
        "authorize an otherwise unsupported operation.",
        "release acceptance still requires a verified, paired database and S3 restore.",
        "It is not evidence for production rollback support and does not "
        "certify retention of grades or vector_chunks.",
        "Any change to the supported rollback range requires a new owner decision",
    ):
        assert boundary in normalized, boundary


def test_baseline_is_the_only_rollback_barrier_in_the_squashed_graph() -> None:
    """Prove the single-revision graph without migration imports, SQL or DB connections."""
    policy = _load_policy_module()
    plan = policy.build_downgrade_plan(MIGRATIONS_DIR)
    metadata = [
        policy._parse_migration(path) for path in sorted(MIGRATIONS_DIR.glob("*.py"))
    ]

    assert [migration.revision for migration in metadata] == ["202611020000"]
    baseline = metadata[0]
    assert baseline.parents == ()
    assert baseline.irreversible_reason == BASELINE_BOUNDARY_REASON
    assert plan.head_revision == plan.boundary_revision == baseline.revision
    assert plan.boundary_parent == "base"
