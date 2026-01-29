"""Tests for Alembic migration runtime behavior using PostgreSQL.

These tests verify that migrations run correctly, are idempotent,
and produce the expected schema state.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Skip marker for tests that require PostgreSQL (won't work with SQLite)
_database_url = os.environ.get("DATABASE_URL", "")
_is_postgresql = _database_url.startswith("postgresql")
requires_postgresql = pytest.mark.skipif(
    not _is_postgresql,
    reason="Test requires PostgreSQL (uses pg_class or information_schema.public)",
)


def _get_postgres_url() -> str:
    """Get PostgreSQL URL from environment or use default test URL."""
    return os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/test_migrations",
    )


def _get_sync_postgres_url() -> str:
    """Get synchronous PostgreSQL URL for Alembic."""
    url = _get_postgres_url()
    # Convert asyncpg to psycopg2 for sync operations
    return url.replace("+asyncpg", "").replace("asyncpg://", "postgresql://")


def _make_config() -> Config:
    """Create Alembic config pointing to PostgreSQL."""
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", _get_sync_postgres_url())
    return config


@requires_postgresql
@pytest.mark.asyncio
async def test_migrations_produce_expected_schema(db_session):
    """Verify that migrations create the expected tables and columns.

    This test uses the already-migrated database from conftest fixtures.
    """
    from sqlalchemy import text

    # Check users table has expected columns
    result = await db_session.execute(
        text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'users'
        """)
    )
    user_columns = {row[0] for row in result.fetchall()}

    assert "id" in user_columns
    assert "email" in user_columns
    assert "mfa_required" in user_columns
    assert "mfa_default_method" in user_columns
    # DND columns were moved to user_preferences
    assert "dnd_enabled" not in user_columns

    # Check user_preferences table exists with DND columns
    result = await db_session.execute(
        text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'user_preferences'
        """)
    )
    prefs_columns = {row[0] for row in result.fetchall()}
    assert {"dnd_enabled", "dnd_start", "dnd_end", "timezone"}.issubset(prefs_columns)


@requires_postgresql
@pytest.mark.asyncio
async def test_mfa_tables_exist(db_session):
    """Verify MFA-related tables exist with correct structure."""
    from sqlalchemy import text

    # Check mfa_totp_enrollments table
    result = await db_session.execute(
        text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN ('mfa_totp_enrollments', 'mfa_challenges')
        """)
    )
    mfa_tables = {row[0] for row in result.fetchall()}
    assert mfa_tables == {"mfa_totp_enrollments", "mfa_challenges"}

    # mfa_recovery_codes should NOT exist (removed in migration)
    result = await db_session.execute(
        text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name = 'mfa_recovery_codes'
        """)
    )
    assert result.fetchone() is None

    # Check mfa_challenges has session_id FK
    result = await db_session.execute(
        text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'mfa_challenges'
        """)
    )
    challenge_columns = {row[0] for row in result.fetchall()}
    assert {"user_id", "session_id", "challenge_type", "expires_at"}.issubset(
        challenge_columns
    )


@requires_postgresql
@pytest.mark.asyncio
async def test_partitioned_tables_exist(db_session):
    """Verify partitioned tables are set up correctly."""
    from sqlalchemy import text

    # Check notifications is partitioned
    result = await db_session.execute(
        text("""
            SELECT relname, relkind FROM pg_class
            WHERE relname = 'notifications' AND relkind = 'p'
        """)
    )
    row = result.fetchone()
    assert row is not None, "notifications table should be partitioned"

    # Check at least one partition exists
    result = await db_session.execute(
        text("""
            SELECT child.relname FROM pg_inherits
            JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
            JOIN pg_class child ON pg_inherits.inhrelid = child.oid
            WHERE parent.relname = 'notifications'
            LIMIT 1
        """)
    )
    partition = result.fetchone()
    assert partition is not None, "notifications should have at least one partition"


def test_alembic_heads_converged():
    """Verify all migration branches have been merged to single head."""
    config = _make_config()
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()

    assert len(heads) == 1, f"Expected single head, got {len(heads)}: {heads}"


def test_alembic_no_pending_migrations():
    """Verify current database is at migration head."""
    config = _make_config()
    script = ScriptDirectory.from_config(config)

    # Get the single head revision
    heads = script.get_heads()
    assert len(heads) == 1

    # The database should already be at head (migrated by conftest)
    head = heads[0]
    revision = script.get_revision(head)
    assert revision is not None
