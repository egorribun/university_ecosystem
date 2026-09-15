"""PostgreSQL proof for the read-only legacy-password release preflight.

The CLI must count every active legacy credential, including rows hidden from a
normal tenant-scoped session.  This test uses a non-superuser reader against a
disposable PostgreSQL container so the RLS bypass is exercised by a real
connection rather than a mocked session.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import closing
from uuid import UUID

import psycopg
import pytest
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from app.cli import migrate_passwords
from app.core.db.listeners import register_tenant_listeners

_RUN = os.environ.get("RUN_INTEGRATION_TESTS") == "1"
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _RUN,
        reason="Set RUN_INTEGRATION_TESTS=1 to run PostgreSQL preflight tests",
    ),
]

_IMAGE = "pgvector/pgvector:pg17@sha256:cf134a767f474095eeba57e0117be8e568e011a63f33fbf252f14c9b760f8e6f"
_READER = "legacy_preflight_reader"
_TABLE = "users"
_USER_IDS = (
    UUID("00000000-0000-4000-8000-000000000001"),
    UUID("00000000-0000-4000-8000-000000000002"),
    UUID("00000000-0000-4000-8000-000000000003"),
)


@pytest.fixture(scope="module")
def postgres_urls() -> Iterator[tuple[str, str]]:
    """Create an isolated database and return admin/reader URLs."""

    with PostgresContainer(_IMAGE) as postgres:
        admin_url = postgres.get_connection_url().replace("+psycopg2", "")
        parsed = make_url(admin_url)
        reader_password = UUID("00000000-0000-4000-8000-000000000099").hex

        with closing(psycopg.connect(admin_url)) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL(
                        "CREATE ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD {}"
                    ).format(sql.Identifier(_READER), sql.Literal(reader_password))
                )
                cursor.execute(
                    sql.SQL(
                        "CREATE TABLE {} ("
                        "id uuid PRIMARY KEY, "
                        "email text NOT NULL, "
                        "hashed_password text NOT NULL, "
                        "is_active boolean NOT NULL, "
                        "tenant_id uuid"
                        ")"
                    ).format(sql.Identifier(_TABLE))
                )
                cursor.execute(
                    sql.SQL("ALTER TABLE {} ENABLE ROW LEVEL SECURITY").format(
                        sql.Identifier(_TABLE)
                    )
                )
                cursor.execute(
                    sql.SQL("ALTER TABLE {} FORCE ROW LEVEL SECURITY").format(
                        sql.Identifier(_TABLE)
                    )
                )
                cursor.execute(
                    sql.SQL(
                        "CREATE POLICY {} ON {} FOR SELECT TO PUBLIC USING ("
                        "current_setting('app.bypass_rls', true) = 'on' "
                        "OR tenant_id IS NULL)"
                    ).format(
                        sql.Identifier(f"{_TABLE}_tenant_policy"),
                        sql.Identifier(_TABLE),
                    )
                )
                cursor.execute(
                    sql.SQL("GRANT SELECT ON {} TO {}").format(
                        sql.Identifier(_TABLE), sql.Identifier(_READER)
                    )
                )
                cursor.executemany(
                    sql.SQL(
                        "INSERT INTO {} "
                        "(id, email, hashed_password, is_active, tenant_id) "
                        "VALUES (%s, %s, %s, %s, %s)"
                    ).format(sql.Identifier(_TABLE)),
                    [
                        (
                            _USER_IDS[0],
                            "legacy-one@example.test",
                            "$2a$12$legacy-a",
                            True,
                            None,
                        ),
                        (
                            _USER_IDS[1],
                            "legacy-two@example.test",
                            "$2b$12$legacy-b",
                            True,
                            UUID("00000000-0000-4000-8000-000000000010"),
                        ),
                        (
                            _USER_IDS[2],
                            "legacy-three@example.test",
                            "$2y$12$legacy-c",
                            True,
                            UUID("00000000-0000-4000-8000-000000000011"),
                        ),
                        (
                            UUID("00000000-0000-4000-8000-000000000004"),
                            "inactive@example.test",
                            "$2b$12$inactive",
                            False,
                            UUID("00000000-0000-4000-8000-000000000012"),
                        ),
                        (
                            UUID("00000000-0000-4000-8000-000000000005"),
                            "argon@example.test",
                            "$argon2id$v=19$m=32768,t=3,p=4$argon",
                            True,
                            UUID("00000000-0000-4000-8000-000000000013"),
                        ),
                    ],
                )
            connection.commit()

        reader_url = parsed.set(
            drivername="postgresql+asyncpg",
            username=_READER,
            password=reader_password,
        ).render_as_string(hide_password=False)
        yield admin_url, reader_url

        with closing(psycopg.connect(admin_url)) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL("DROP TABLE IF EXISTS {}").format(sql.Identifier(_TABLE))
                )
                cursor.execute(
                    sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(_READER))
                )
            connection.commit()


@pytest.mark.asyncio
async def test_preflight_counts_active_bcrypt_rows_across_rls(
    postgres_urls: tuple[str, str], monkeypatch: pytest.MonkeyPatch
):
    """Count and sampling use SQL predicates and the scoped RLS bypass."""

    _admin_url, reader_url = postgres_urls
    engine: AsyncEngine = create_async_engine(reader_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    register_tenant_listeners()

    async def plain_count() -> int:
        async with session_factory() as session:
            result = await session.execute(
                text(
                    "SELECT count(*) FROM users "
                    "WHERE is_active IS true AND hashed_password LIKE '$2%'"
                )
            )
            return int(result.scalar_one())

    monkeypatch.setattr(migrate_passwords, "async_session", session_factory)

    try:
        # A normal tenant-scoped reader sees only the NULL-tenant row.
        assert await plain_count() == 1
        assert await migrate_passwords._count_bcrypt_users() == 3

        entries = await migrate_passwords._report_bcrypt_users(limit=2, show_ids=True)
        assert entries == [
            {"id": str(_USER_IDS[0])},
            {"id": str(_USER_IDS[1])},
        ]
        assert all("@" not in entry["id"] for entry in entries)
    finally:
        await engine.dispose()
