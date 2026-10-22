import os
import re
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
import yaml
from alembic.config import Config
from testcontainers.community.postgres import PostgresContainer

from alembic import command

PROJECT_ROOT = Path(__file__).resolve().parents[2]

_RUN = os.getenv("RUN_INTEGRATION_TESTS") == "1"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _RUN, reason="Set RUN_INTEGRATION_TESTS=1 to run"),
]


def _pinned_postgres_image() -> str:
    """Read the test database's immutable image pin from the Compose source."""
    compose = yaml.safe_load(
        (PROJECT_ROOT / "docker-compose.test.yml").read_text(encoding="utf-8")
    )
    image = compose["services"]["postgres"]["image"]
    if (
        not isinstance(image, str)
        or re.fullmatch(r"pgvector/pgvector:pg17@sha256:[0-9a-f]{64}", image) is None
    ):
        raise ValueError("docker-compose.test.yml must pin pgvector/pg17 by SHA-256")
    return image


@pytest.fixture(scope="module")
def migration_postgres():
    """Provides a labelled, resource-bounded PostgreSQL migration container."""
    run_id = uuid4().hex
    image = _pinned_postgres_image()
    with PostgresContainer(
        image,
        name=f"ue-aud230-pg17-{run_id}",
        labels={
            "university-ecosystem.dev/test-owner": f"aud230-{run_id}",
            "university-ecosystem.dev/test-purpose": "tenant-migration-data-integrity",
        },
        mem_limit=1024**3,
        memswap_limit=1024**3,
        nano_cpus=2_000_000_000,
    ) as postgres:
        yield postgres


CORE_TENANT_TABLES = (
    "users",
    "groups",
    "schedule",
    "events",
    "chats",
    "messages",
    "news",
    "stories",
    "notifications",
)


def test_full_migration_cycle_with_data_integrity(migration_postgres):
    """
    Checks tenant-state compatibility across a historical revision edge and head.
    The isolated downgrade is not a supported production rollback.
    """
    orig_url = migration_postgres.get_connection_url()
    url_asyncpg = orig_url.replace("+psycopg2", "+asyncpg")
    url_psycopg = orig_url.replace("+psycopg2", "")

    orig_db_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url_asyncpg

    try:
        config = Config(str(PROJECT_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
        config.set_main_option("sqlalchemy.url", url_asyncpg)

        # Seed at the parent revision so the next migration encounters real data.
        command.upgrade(config, "202607240001")
        tenant_id = "11111111-2222-3333-4444-555555555555"
        tenant_user_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        with psycopg.connect(url_psycopg) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO tenants (id, name, slug)
                    VALUES (%s, 'AUD-230 tenant', 'aud-230-regression')
                    """,
                    (tenant_id,),
                )
                cur.execute(
                    "SELECT set_config('app.current_tenant', %s, true)",
                    (tenant_id,),
                )
                cur.execute(
                    """
                    INSERT INTO users (
                        id, email, hashed_password, role, is_active,
                        mfa_required, tenant_id
                    )
                    VALUES (
                        %s, 'aud230@university.invalid', 'synthetic-hash',
                        'student', true, false, %s
                    )
                    """,
                    (tenant_user_id, tenant_id),
                )

        command.upgrade(config, "202607280001")

        with psycopg.connect(url_psycopg) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT set_config('app.current_tenant', %s, true)",
                    (tenant_id,),
                )
                cur.execute(
                    """
                    SELECT table_name
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND column_name = 'tenant_id'
                      AND table_name = ANY(%s)
                    """,
                    (list(CORE_TENANT_TABLES),),
                )
                retained_columns = {row[0] for row in cur.fetchall()}
                assert retained_columns == set(CORE_TENANT_TABLES)

                cur.execute(
                    "SELECT tenant_id FROM users WHERE id = %s",
                    (tenant_user_id,),
                )
                tenant_assignment = cur.fetchone()
                assert tenant_assignment is not None
                assert str(tenant_assignment[0]) == tenant_id

                cur.execute(
                    """
                    SELECT count(*)
                    FROM pg_policies
                    WHERE schemaname = current_schema()
                      AND tablename = 'users'
                      AND policyname = 'tenant_isolation_policy'
                    """
                )
                assert cur.fetchone() == (1,)

        # Downgrading this revision must leave the tenant schema owned by its
        # parent revision, including the tenant assignment and foreign key.
        # Historical-only compatibility check on this isolated pre-barrier DB.
        # The 202608250001/2 boundary is retained in production; this downgrade
        # is not a supported production rollback and does not check grades or
        # vector_chunks retention. Recovery below the release boundary is from
        # a consistent backup/restore set.
        command.downgrade(config, "202607240001")
        with psycopg.connect(url_psycopg) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT set_config('app.current_tenant', %s, true)",
                    (tenant_id,),
                )
                cur.execute(
                    """
                    SELECT tenants.id, users.tenant_id
                    FROM tenants
                    JOIN users ON users.tenant_id = tenants.id
                    WHERE users.id = %s
                    """,
                    (tenant_user_id,),
                )
                tenant_assignment = cur.fetchone()
                assert tenant_assignment is not None
                assert tuple(str(value) for value in tenant_assignment) == (
                    tenant_id,
                    tenant_id,
                )

                cur.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conrelid = 'users'::regclass
                          AND confrelid = 'tenants'::regclass
                          AND contype = 'f'
                    )
                    """
                )
                assert cur.fetchone() == (True,)

        command.upgrade(config, "head")

        # Later migrations must continue to preserve the tenant assignment and
        # tenant row seeded at the 202607240001 boundary.
        with psycopg.connect(url_psycopg) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT set_config('app.current_tenant', %s, true)",
                    (tenant_id,),
                )
                cur.execute(
                    """
                    SELECT tenants.id, users.tenant_id
                    FROM tenants
                    JOIN users ON users.tenant_id = tenants.id
                    WHERE users.id = %s
                    """,
                    (tenant_user_id,),
                )
                preserved_assignment = cur.fetchone()
                assert preserved_assignment is not None
                assert tuple(str(value) for value in preserved_assignment) == (
                    tenant_id,
                    tenant_id,
                )

        # The real PostgreSQL catalog must also match migration-owned metadata.
        command.check(config)

        # Verify the later migrations and ordinary data integrity still work.
        with psycopg.connect(url_psycopg) as conn:
            with conn.cursor() as cur:
                user_id = "123e4567-e89b-12d3-a456-426614174000"
                cur.execute(
                    """
                    INSERT INTO users (id, email, hashed_password, role, is_active, mfa_required)
                    VALUES (%s, 'integrity@university.dev', 'hash123', 'student', true, false)
                    """,
                    (user_id,),
                )
                cur.execute(
                    """
                    INSERT INTO user_preferences (user_id, timezone, dnd_enabled)
                    VALUES (%s, 'UTC', false)
                    """,
                    (user_id,),
                )

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
