"""PostgreSQL regressions for the 148642dd1207 shadow-key conversion."""

from __future__ import annotations

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
    """Provide an isolated PostgreSQL instance with the required extension."""

    with PostgresContainer(
        "pgvector/pgvector:pg17@sha256:cf134a767f474095eeba57e0117be8e568e011a63f33fbf252f14c9b760f8e6f"
    ) as postgres:
        yield postgres


def test_invalid_fk_value_aborts_shadow_conversion_without_data_loss(
    migration_postgres,
) -> None:
    """Reject an invalid child key before PostgreSQL can evaluate an unsafe cast."""

    original_url = migration_postgres.get_connection_url()
    alembic_url = original_url.replace("+psycopg2", "+psycopg")
    sync_url = original_url.replace("+psycopg2", "")
    original_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = alembic_url

    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", alembic_url)

    try:
        command.upgrade(config, "f7aa476e968a")
        with psycopg.connect(sync_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("INSERT INTO groups (id) VALUES (%s)", ("1",))
                cursor.execute(
                    "CREATE TABLE invalid_group_refs "
                    "(id serial PRIMARY KEY, group_id varchar(20))"
                )
                cursor.execute(
                    "INSERT INTO invalid_group_refs (group_id) VALUES (%s)",
                    ("oops",),
                )
                cursor.execute(
                    "ALTER TABLE invalid_group_refs "
                    "ADD CONSTRAINT invalid_group_refs_group_fk "
                    "FOREIGN KEY (group_id) REFERENCES groups(id) NOT VALID"
                )
            connection.commit()

        with pytest.raises(Exception) as exc_info:
            command.upgrade(config, "148642dd1207")
        assert "groups FK column" in str(exc_info.value)

        with psycopg.connect(sync_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT version_num FROM alembic_version")
                assert cursor.fetchone() == ("f7aa476e968a",)
                cursor.execute(
                    "SELECT data_type, character_maximum_length "
                    "FROM information_schema.columns "
                    "WHERE table_name = 'groups' AND column_name = 'id'"
                )
                assert cursor.fetchone() == ("character varying", 20)
                cursor.execute(
                    "SELECT data_type, character_maximum_length "
                    "FROM information_schema.columns "
                    "WHERE table_name = 'invalid_group_refs' "
                    "AND column_name = 'group_id'"
                )
                assert cursor.fetchone() == ("character varying", 20)
                cursor.execute(
                    "SELECT COUNT(*) FROM invalid_group_refs WHERE group_id = %s",
                    ("oops",),
                )
                assert cursor.fetchone() == (1,)
                cursor.execute(
                    "SELECT conname FROM pg_constraint "
                    "WHERE conname = 'invalid_group_refs_group_fk'"
                )
                assert cursor.fetchone() == ("invalid_group_refs_group_fk",)
    finally:
        if original_database_url is not None:
            os.environ["DATABASE_URL"] = original_database_url
        else:
            os.environ.pop("DATABASE_URL", None)
