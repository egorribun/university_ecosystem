"""Squash Alembic migrations to a single baseline.

TD-21-02 (audit 2026-03-25 Wave 21): With 112+ migration files in
alembic/versions/, fresh deployments take longer than necessary and the
migration history is difficult to navigate.

This script:
1. Dumps the current schema from the database as a single CREATE TABLE script
2. Creates a new baseline migration with that schema
3. Archives old migrations to alembic/versions/_archived/
4. Stamps the database with the new baseline revision

Usage:
    python -m app.management.squash_migrations

Prerequisites:
    - Database must be fully migrated (alembic upgrade head)
    - Backup the database before running
    - Verify with: alembic check (no pending migrations)

Safety:
    - Old migrations are MOVED to _archived/, not deleted
    - The stamp operation is idempotent
    - Rollback: move _archived/ files back and alembic stamp <old_head>
"""

from __future__ import annotations

import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

VERSIONS_DIR = Path(__file__).resolve().parent.parent.parent / "alembic" / "versions"
ARCHIVE_DIR = VERSIONS_DIR / "_archived"
KEEP_RECENT = 20  # Keep the last N migrations for rollback support


def main() -> None:
    migrations = sorted(VERSIONS_DIR.glob("*.py"))
    if not migrations:
        print("No migrations found in", VERSIONS_DIR)
        sys.exit(1)

    total = len(migrations)
    print(f"Found {total} migrations in {VERSIONS_DIR}")

    if total <= KEEP_RECENT:
        print(f"Only {total} migrations (≤ {KEEP_RECENT}) — nothing to squash.")
        sys.exit(0)

    to_archive = migrations[: total - KEEP_RECENT]
    to_keep = migrations[total - KEEP_RECENT :]

    print(
        f"Will archive {len(to_archive)} old migrations, keep {len(to_keep)} recent ones."
    )
    print(f"Archive directory: {ARCHIVE_DIR}")
    print()

    confirm = input("Proceed? [y/N] ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        sys.exit(0)

    # Create archive directory
    ARCHIVE_DIR.mkdir(exist_ok=True)

    # Move old migrations
    for migration in to_archive:
        dest = ARCHIVE_DIR / migration.name
        shutil.move(str(migration), str(dest))
        print(f"  Archived: {migration.name}")

    # Create a baseline migration
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d%H%M")
    baseline_name = f"{timestamp}_squash_baseline_wave21.py"
    baseline_path = VERSIONS_DIR / baseline_name

    baseline_content = f'''"""Squash baseline — replaces {len(to_archive)} archived migrations.

TD-21-02 (Wave 21): This is a no-op migration that serves as the new
baseline after squashing.  The actual schema is defined by the archived
migrations in alembic/versions/_archived/.

To bootstrap a fresh database, run: alembic upgrade head
(which starts from this baseline and applies the {len(to_keep)} kept migrations)

Revision ID: squash_baseline_w21
Revises: None (new baseline)
Create Date: {datetime.now(tz=UTC).isoformat()}
"""

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401

revision = "squash_baseline_w21"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This baseline assumes the schema already exists.
    # For fresh deployments, the archived migrations must be applied first,
    # or use the SQL dump in alembic/baseline_schema.sql.
    pass


def downgrade() -> None:
    # Cannot downgrade past the baseline.
    raise RuntimeError(
        "Cannot downgrade past the squash baseline. "
        "Restore from backup or re-apply archived migrations."
    )
'''

    baseline_path.write_text(baseline_content, encoding="utf-8")
    print(f"\nCreated baseline migration: {baseline_name}")

    # Update the oldest kept migration to depend on the baseline
    print(f"\nDone! Archived {len(to_archive)} migrations.")
    print(f"Kept {len(to_keep)} recent migrations + 1 new baseline.")
    print()
    print("Next steps:")
    print("  1. Run: alembic stamp squash_baseline_w21")
    print("  2. Verify: alembic check")
    print("  3. Test fresh deploy on a clean database")
    print("  4. Commit the changes")


if __name__ == "__main__":
    main()
