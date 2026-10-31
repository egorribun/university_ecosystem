"""PostgreSQL proof for the read-only legacy-password release preflight.

The actual migration supplies the policy. Dedicated-role members may inventory
all active legacy rows; an unapproved reader must deny even an empty table.
All roles, grants and rows below belong only to the disposable test container.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from contextlib import closing
from uuid import UUID

import psycopg
import pytest
from psycopg import sql
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.community.postgres import PostgresContainer
from typer.testing import CliRunner

from app.cli import migrate_passwords
from app.core.db.listeners import register_tenant_listeners
from app.core.tenant import bypass_rls_ctx, tenant_id_ctx
from tests.test_aud277_360_450_tenant_rls_contract import capture_tenant_upgrade

_RUN = os.environ.get("RUN_INTEGRATION_TESTS") == "1"
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _RUN,
        reason="Set RUN_INTEGRATION_TESTS=1 to run PostgreSQL preflight tests",
    ),
]

_IMAGE = "pgvector/pgvector:pg17@sha256:ac08538c6f8b9904c33c8224c5e5706dbe760aca29db1d096972b4052c22a75d"
_READER = "legacy_preflight_reader"
_UNAPPROVED_READER = "legacy_preflight_unapproved_reader"
_TABLE = "users"
_DENIED_OUTPUT = "Legacy inventory authority could not be verified."
_TENANT_A = UUID("00000000-0000-4000-8000-000000000010")
_USER_IDS = (
    UUID("00000000-0000-4000-8000-000000000001"),
    UUID("00000000-0000-4000-8000-000000000002"),
    UUID("00000000-0000-4000-8000-000000000003"),
)


@pytest.fixture(scope="module", params=[False, True], ids=["empty", "seeded"])
def postgres_urls(
    request: pytest.FixtureRequest,
) -> Iterator[tuple[str, str, str, bool]]:
    """Create isolated empty/seeded cells with approved and unapproved readers."""

    with pytest.MonkeyPatch.context() as patch:
        _, tenant_sql, _ = capture_tenant_upgrade(patch, (_TABLE,))

    with PostgresContainer(_IMAGE) as postgres:
        admin_url = postgres.get_connection_url().replace("+psycopg2", "")
        parsed = make_url(admin_url)
        reader_password = UUID("00000000-0000-4000-8000-000000000099").hex
        seeded = bool(request.param)

        with closing(psycopg.connect(admin_url)) as connection:
            with connection.cursor() as cursor:
                for role in (_READER, _UNAPPROVED_READER):
                    cursor.execute(
                        sql.SQL(
                            "CREATE ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS "
                            "NOINHERIT PASSWORD {}"
                        ).format(sql.Identifier(role), sql.Literal(reader_password))
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
                for statement in tenant_sql:
                    cursor.execute(statement)
                for role in (_READER, _UNAPPROVED_READER):
                    cursor.execute(
                        sql.SQL("GRANT SELECT ON {} TO {}").format(
                            sql.Identifier(_TABLE), sql.Identifier(role)
                        )
                    )
                cursor.execute(
                    sql.SQL("GRANT ue_rls_bypass TO {}").format(sql.Identifier(_READER))
                )
                if seeded:
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
                                _TENANT_A,
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

        reader_urls = [
            parsed.set(
                drivername="postgresql+asyncpg",
                username=role,
                password=reader_password,
            ).render_as_string(hide_password=False)
            for role in (_READER, _UNAPPROVED_READER)
        ]
        yield admin_url, reader_urls[0], reader_urls[1], seeded

        with closing(psycopg.connect(admin_url)) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL("DROP TABLE IF EXISTS {}").format(sql.Identifier(_TABLE))
                )
                for role in (_READER, _UNAPPROVED_READER):
                    cursor.execute(
                        sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role))
                    )
            connection.commit()


def _sync_url(url: str) -> str:
    return make_url(url).set(drivername="postgresql").render_as_string(
        hide_password=False
    )


def _snapshot(admin_url: str) -> list[tuple[object, ...]]:
    with closing(psycopg.connect(admin_url)) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, email, hashed_password, is_active, tenant_id "
                "FROM users ORDER BY id"
            )
            return cursor.fetchall()


def _assert_reader_is_select_only(reader_url: str) -> None:
    with closing(psycopg.connect(_sync_url(reader_url))) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT rolsuper, rolbypassrls, rolinherit FROM pg_roles "
                "WHERE rolname = current_user"
            )
            assert cursor.fetchone() == (False, False, False)
            cursor.execute("SELECT row_security_active('public.users')")
            assert cursor.fetchone() == (True,)
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                cursor.execute(
                    "SELECT has_table_privilege(current_user, 'public.users', %s)",
                    (privilege,),
                )
                assert cursor.fetchone() == (privilege == "SELECT",)
            for statement in (
                "INSERT INTO users SELECT * FROM users WHERE false",
                "UPDATE users SET is_active = is_active WHERE false",
                "DELETE FROM users WHERE false",
            ):
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    cursor.execute(statement)
                connection.rollback()


def test_preflight_counts_active_bcrypt_rows_across_rls(
    postgres_urls: tuple[str, str, str, bool], monkeypatch: pytest.MonkeyPatch
) -> None:
    admin_url, reader_url, _unapproved_url, seeded = postgres_urls
    before = _snapshot(admin_url)
    _assert_reader_is_select_only(reader_url)
    engine: AsyncEngine = create_async_engine(reader_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    register_tenant_listeners()
    monkeypatch.setattr(migrate_passwords, "async_session", session_factory)
    expected = 3 if seeded else 0
    runner = CliRunner()

    try:
        assert asyncio.run(migrate_passwords._count_bcrypt_users()) == expected
        entries = asyncio.run(
            migrate_passwords._report_bcrypt_users(limit=2, show_ids=True)
        )
        assert entries == (
            [{"id": str(value)} for value in _USER_IDS[:2]] if seeded else []
        )

        report = runner.invoke(migrate_passwords.app, ["report"])
        assert report.exit_code == 0
        assert f"Legacy bcrypt accounts remaining: {expected}" in report.stdout
        assert all(str(value) not in report.stdout for value in _USER_IDS)
        assert "@example.test" not in report.stdout
        assert "$2" not in report.stdout

        sample = runner.invoke(
            migrate_passwords.app, ["report", "--show-ids", "--limit", "2"]
        )
        assert sample.exit_code == 0
        if seeded:
            assert all(str(value) in sample.stdout for value in _USER_IDS[:2])
        assert str(_USER_IDS[2]) not in sample.stdout
        assert "@example.test" not in sample.stdout
        assert "$2" not in sample.stdout

        assertion = runner.invoke(migrate_passwords.app, ["assert-none"])
        assert assertion.exit_code == (1 if seeded else 0)
        expected_message = (
            "Legacy bcrypt accounts remain: 3"
            if seeded
            else "No active legacy bcrypt accounts found."
        )
        assert assertion.stdout.strip() == expected_message
    finally:
        asyncio.run(engine.dispose())

    assert _snapshot(admin_url) == before


def test_global_inventory_denies_empty_and_hidden_rows_without_role_membership(
    postgres_urls: tuple[str, str, str, bool], monkeypatch: pytest.MonkeyPatch
) -> None:
    admin_url, _reader_url, unapproved_url, seeded = postgres_urls
    before = _snapshot(admin_url)
    _assert_reader_is_select_only(unapproved_url)
    with closing(psycopg.connect(_sync_url(unapproved_url))) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM users WHERE is_active IS true "
                "AND hashed_password LIKE '$2%'"
            )
            assert cursor.fetchone() == (0,)
            cursor.execute("SELECT set_config('app.bypass_rls', 'on', true)")
            cursor.execute(
                "SELECT set_config('app.current_tenant', %s, true)", (str(_TENANT_A),)
            )
            cursor.execute(
                "SELECT count(*) FROM users WHERE is_active IS true "
                "AND hashed_password LIKE '$2%'"
            )
            assert cursor.fetchone() == (1 if seeded else 0,)

    engine: AsyncEngine = create_async_engine(unapproved_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    register_tenant_listeners()
    monkeypatch.setattr(migrate_passwords, "async_session", session_factory)
    tenant_token = tenant_id_ctx.set("")
    bypass_token = bypass_rls_ctx.set(False)
    runner = CliRunner()

    try:
        for forge_context in (False, True):
            tenant_id_ctx.set(str(_TENANT_A) if forge_context else "")
            bypass_rls_ctx.set(forge_context)
            for arguments in (
                ["report"],
                ["assert-none"],
                ["report", "--show-ids", "--limit", "2"],
            ):
                result = runner.invoke(migrate_passwords.app, arguments)
                assert result.exit_code == 2
                assert result.stdout.strip() == _DENIED_OUTPUT
                assert result.stderr == ""
                assert bypass_rls_ctx.get() is forge_context
                assert tenant_id_ctx.get() == (str(_TENANT_A) if forge_context else "")
    finally:
        try:
            asyncio.run(engine.dispose())
        finally:
            bypass_rls_ctx.reset(bypass_token)
            tenant_id_ctx.reset(tenant_token)

    assert _snapshot(admin_url) == before
