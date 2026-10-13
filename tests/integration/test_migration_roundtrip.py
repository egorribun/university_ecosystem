"""Exercise a reversible migration roundtrip and the declared downgrade boundary."""

from __future__ import annotations

import os
from ipaddress import ip_address
from pathlib import Path
from uuid import uuid4

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


class _LoopbackMigrationPostgres:
    def __init__(self, connection_url: str) -> None:
        parsed = sa.engine.make_url(connection_url)
        try:
            loopback = ip_address(parsed.host or "").is_loopback
        except ValueError:
            loopback = False
        if (
            parsed.drivername != "postgresql+asyncpg"
            or not loopback
            or parsed.username != "test"
            or parsed.database is None
            or len(parsed.database) != 25
            or not parsed.database.startswith("test_")
            or any(
                character not in "0123456789abcdef" for character in parsed.database[5:]
            )
            or not parsed.password
            or parsed.port is None
            or not 1 <= parsed.port <= 65535
            or parsed.port == 5432
            or bool(parsed.query)
        ):
            raise ValueError(
                "MIGRATION_ROUNDTRIP_DATABASE_URL must target the owned loopback PG17 test database."
            )
        self._url = parsed

    def get_connection_url(self, *, driver: str) -> str:
        if driver not in {"asyncpg", "psycopg"}:
            raise ValueError("Unsupported migration test database driver.")
        return self._url.set(drivername=f"postgresql+{driver}").render_as_string(
            hide_password=False
        )


@pytest.fixture(scope="module")
def migration_postgres():
    """Provides isolated PostgreSQL, reusing the bounded operator when requested."""
    operator_url = os.environ.get("MIGRATION_ROUNDTRIP_DATABASE_URL")
    if operator_url:
        yield _LoopbackMigrationPostgres(operator_url)
        return

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
        inspection_engine = sa.create_engine(url_sync)
        sentinel_id = uuid4()
        sentinel_url = f"https://example.invalid/migration-roundtrip/{sentinel_id}"
        try:
            # Commit a marker before the probe so transaction rollback must retain it.
            with inspection_engine.begin() as connection:
                connection.execute(
                    sa.text(
                        """
                        INSERT INTO news_media_assets (id, storage_url)
                        VALUES (:id, :storage_url)
                        """
                    ).bindparams(sa.bindparam("id", type_=sa.Uuid())),
                    {"id": sentinel_id, "storage_url": sentinel_url},
                )

            boundary_connection = inspection_engine.connect()
            boundary_transaction = None
            try:
                boundary_transaction = boundary_connection.begin()
                config.attributes["connection"] = boundary_connection
                try:
                    migration_downgrade_policy.assert_declared_boundary(
                        plan, lambda target: command.downgrade(config, target)
                    )

                    # 002 is a no-op downgrade, but Alembic still stamps 001 before
                    # the irreversible 001 downgrade raises. Prove that this partial
                    # stamp and the protected data/schema are visible inside the
                    # outer transaction before rolling the diagnostic back.
                    assert (
                        MigrationContext.configure(
                            boundary_connection
                        ).get_current_revision()
                        == plan.safe_target
                    )
                    assert (
                        boundary_connection.execute(
                            sa.text(
                                "SELECT storage_url FROM news_media_assets WHERE id = :id"
                            ).bindparams(sa.bindparam("id", type_=sa.Uuid())),
                            {"id": sentinel_id},
                        ).scalar_one()
                        == sentinel_url
                    )
                    dnd_types = boundary_connection.execute(
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
                    assert {
                        row["column_name"]: row["data_type"] for row in dnd_types
                    } == {
                        "dnd_start": "time without time zone",
                        "dnd_end": "time without time zone",
                    }
                finally:
                    config.attributes.pop("connection", None)
                    if boundary_transaction.is_active:
                        boundary_transaction.rollback()
            finally:
                boundary_connection.close()

            # The head revision, data marker, and irreversible schema
            # survive the failed probe after its external transaction is rolled back.
            with inspection_engine.connect() as connection:
                assert (
                    MigrationContext.configure(connection).get_current_revision()
                    == plan.head_revision
                )
                assert (
                    connection.execute(
                        sa.text(
                            "SELECT storage_url FROM news_media_assets WHERE id = :id"
                        ).bindparams(sa.bindparam("id", type_=sa.Uuid())),
                        {"id": sentinel_id},
                    ).scalar_one()
                    == sentinel_url
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
            config.attributes.pop("connection", None)
            inspection_engine.dispose()

    finally:
        if orig_db_url is not None:
            os.environ["DATABASE_URL"] = orig_db_url
        else:
            del os.environ["DATABASE_URL"]
