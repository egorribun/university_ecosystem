import os
from pathlib import Path

import psycopg
import pytest
from alembic.config import Config
from testcontainers.postgres import PostgresContainer

from alembic import command

PROJECT_ROOT = Path(__file__).resolve().parents[2]

_RUN = bool(os.getenv("RUN_INTEGRATION_TESTS"))

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _RUN, reason="Set RUN_INTEGRATION_TESTS=1 to run"),
]


@pytest.fixture(scope="module")
def migration_postgres():
    """Provides an isolated PostgreSQL container for destructive migration tests."""
    # We use pgvector image because the schema relies on pgvector extension
    with PostgresContainer(
        "pgvector/pgvector:pg17@sha256:cf134a767f474095eeba57e0117be8e568e011a63f33fbf252f14c9b760f8e6f"
    ) as postgres:
        yield postgres


def test_full_migration_cycle_with_data_integrity(migration_postgres):
    """
    Tests that we can run all migrations to head, insert data,
    and the database remains in a consistent state.
    """
    orig_url = migration_postgres.get_connection_url()
    url_asyncpg = orig_url.replace("+psycopg2", "+asyncpg")
    url_psycopg = orig_url.replace("+psycopg2", "")

    import os

    orig_db_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url_asyncpg

    try:
        # Prepare Alembic config
        config = Config(str(PROJECT_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
        config.set_main_option("sqlalchemy.url", url_asyncpg)

        # 1. Upgrade to head
        command.upgrade(config, "head")

        # 2. Verify data integrity by inserting a complex record
        # that relies on multiple constraints and defaults defined in migrations.
        with psycopg.connect(url_psycopg) as conn:
            with conn.cursor() as cur:
                # Insert a user record
                user_id = "123e4567-e89b-12d3-a456-426614174000"
                cur.execute(
                    """
                    INSERT INTO users (id, email, hashed_password, role, is_active, mfa_required)
                    VALUES (%s, 'integrity@university.dev', 'hash123', 'student', true, false)
                """,
                    (user_id,),
                )

                # Insert into user_preferences (a table split out in later migrations)
                cur.execute(
                    """
                    INSERT INTO user_preferences (user_id, timezone, dnd_enabled)
                    VALUES (%s, 'UTC', false)
                """,
                    (user_id,),
                )

                conn.commit()

                # 3. Read it back to ensure constraints hold and data isn't corrupted
                cur.execute(
                    """
                    SELECT u.email, p.timezone 
                    FROM users u 
                    JOIN user_preferences p ON u.id = p.user_id 
                    WHERE u.id = %s
                """,
                    (user_id,),
                )
                result = cur.fetchone()

                assert result is not None
                assert result[0] == "integrity@university.dev"
                assert result[1] == "UTC"
    finally:
        if orig_db_url is not None:
            os.environ["DATABASE_URL"] = orig_db_url
        else:
            del os.environ["DATABASE_URL"]
