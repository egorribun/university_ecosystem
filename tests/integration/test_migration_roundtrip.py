"""Integration test for Alembic migration roundtrips.

Ensures that we can migrate all the way to `head`, downgrade by one revision (`-1`),
and migrate back to `head` successfully on a clean database schema.
"""

from __future__ import annotations

import os
from pathlib import Path

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
    """Provides an isolated PostgreSQL container with pgvector support for migration tests."""
    with PostgresContainer(
        "pgvector/pgvector:pg17@sha256:cf134a767f474095eeba57e0117be8e568e011a63f33fbf252f14c9b760f8e6f"
    ) as postgres:
        yield postgres


def test_migration_upgrade_downgrade_roundtrip(migration_postgres) -> None:
    """Verify upgrade head -> downgrade -1 -> upgrade head cycle runs without errors."""
    orig_url = migration_postgres.get_connection_url()
    url_asyncpg = orig_url.replace("+psycopg2", "+asyncpg")

    orig_db_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url_asyncpg

    try:
        # 1. Initialize Alembic Config pointing to testcontainer
        config = Config(str(PROJECT_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
        config.set_main_option("sqlalchemy.url", url_asyncpg)

        # 2. Upgrade all the way to head
        command.upgrade(config, "head")

        # 3. Downgrade by 1 revision
        command.downgrade(config, "-1")

        # 4. Upgrade back to head to complete the roundtrip
        command.upgrade(config, "head")

    finally:
        if orig_db_url is not None:
            os.environ["DATABASE_URL"] = orig_db_url
        else:
            del os.environ["DATABASE_URL"]
