"""Exercise a reversible migration roundtrip and the declared downgrade boundary."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from testcontainers.community.postgres import PostgresContainer

from alembic import command
from scripts.quality import migration_downgrade_policy

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


def test_migration_supported_roundtrip_and_irreversible_boundary(
    migration_postgres,
) -> None:
    """Round-trip a reversible migration and verify the PostgreSQL boundary."""
    url_sync = migration_postgres.get_connection_url(driver="psycopg")
    url_asyncpg = migration_postgres.get_connection_url(driver="asyncpg")

    orig_db_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url_asyncpg

    try:
        # Initialize Alembic Config pointing to the isolated testcontainer.
        config = Config(str(PROJECT_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
        config.set_main_option("sqlalchemy.url", url_asyncpg)
        plan = migration_downgrade_policy.build_downgrade_plan(
            PROJECT_ROOT / "alembic" / "versions"
        )
        assert plan.boundary_revision is not None
        assert plan.boundary_parent is not None
        assert plan.safe_target == plan.boundary_revision

        # Round-trip the schema-changing groups demo-key revision. It is before
        # the latest boundary and its parent, so this never crosses a barrier.
        command.upgrade(config, "202609300002")
        command.downgrade(config, "202609300001")
        command.upgrade(config, "202609300002")

        # Follow the policy's safe path through the boundary to the current head.
        command.upgrade(config, plan.boundary_parent)
        command.upgrade(config, "head")
        command.downgrade(config, plan.safe_target)
        command.upgrade(config, "head")
        migration_downgrade_policy.assert_declared_boundary(
            plan, lambda target: command.downgrade(config, target)
        )

        # Confirm the refusal leaves the database at its prior head and
        # retains the irreversible migration's wall-clock schema.
        inspection_engine = sa.create_engine(url_sync)
        try:
            with inspection_engine.connect() as connection:
                assert (
                    MigrationContext.configure(connection).get_current_revision()
                    == plan.head_revision
                )
                dnd_types = connection.execute(
                    sa.text(
                        """
                        SELECT column_name, data_type
                          FROM information_schema.columns
                         WHERE table_schema = current_schema()
                           AND table_name = 'user_preferences'
                           AND column_name IN ('dnd_start', 'dnd_end')
                        """
                    )
                ).mappings()
                assert {row["column_name"]: row["data_type"] for row in dnd_types} == {
                    "dnd_start": "time without time zone",
                    "dnd_end": "time without time zone",
                }
        finally:
            inspection_engine.dispose()

    finally:
        if orig_db_url is not None:
            os.environ["DATABASE_URL"] = orig_db_url
        else:
            del os.environ["DATABASE_URL"]
