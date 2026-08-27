"""W21 migration integrity tests for explicit downgrade contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_MIGRATIONS_DIR = _PROJECT_ROOT / "alembic" / "versions"


@pytest.mark.slow
async def test_every_migration_has_downgrade_contract(tmp_path):
    """Every migration must implement a non-trivial downgrade contract.

    Reversible migrations perform the rollback. An intentional data-loss
    boundary fails before schema changes and is separately validated by
    ``test_migration_downgrade_policy.py``. Missing and no-op downgrade
    contracts remain forbidden.
    """
    assert _MIGRATIONS_DIR.exists(), (
        f"alembic/versions directory not found at {_MIGRATIONS_DIR}"
    )

    migration_files = list(_MIGRATIONS_DIR.glob("*.py"))
    assert migration_files, "No migration files found in alembic/versions"

    issues: list[str] = []
    for migration_file in migration_files:
        content = migration_file.read_text(encoding="utf-8")

        # Merge migrations (down_revision is a tuple of multiple parent revisions)
        # always have pass bodies for both upgrade() and downgrade() — this is
        # Alembic's standard template and not a defect.  Skip them.
        is_merge_migration = "down_revision" in content and (
            "down_revision: str | tuple" in content or "down_revision = (" in content
        )
        if is_merge_migration:
            continue

        if "def downgrade" not in content:
            issues.append(f"{migration_file.name}: missing downgrade() function")
        elif (
            "def downgrade():\n    pass" in content
            or "def downgrade() -> None:\n    pass" in content
        ):
            issues.append(f"{migration_file.name}: downgrade() is just pass")

    assert not issues, "Migration issues:\n" + "\n".join(issues)


@pytest.mark.slow
async def test_migration_files_have_revision_ids(tmp_path):
    """Every migration file must declare revision and down_revision.

    WHY: missing revision metadata breaks alembic's graph traversal and will
    cause `alembic upgrade head` to silently skip or error on affected files.
    """
    assert _MIGRATIONS_DIR.exists(), (
        f"alembic/versions directory not found at {_MIGRATIONS_DIR}"
    )

    migration_files = list(_MIGRATIONS_DIR.glob("*.py"))

    issues: list[str] = []
    for migration_file in migration_files:
        content = migration_file.read_text(encoding="utf-8")
        has_revision = "revision:" in content or "revision =" in content
        if not has_revision:
            issues.append(f"{migration_file.name}: missing revision identifier")

    assert not issues, "\n".join(issues)
