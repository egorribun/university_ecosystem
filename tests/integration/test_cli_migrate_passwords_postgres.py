"""PostgreSQL proof for the read-only legacy-password release preflight.

The committed MVP baseline supplies the actual users schema and policy. Dedicated-role members may inventory
all active legacy rows; an unapproved reader must deny even an empty table.
All roles, grants and rows below belong only to the disposable test container.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from contextlib import closing
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from typer.testing import CliRunner

from app.cli import migrate_passwords
from app.core.db.listeners import register_tenant_listeners
from app.core.tenant import bypass_rls_ctx, tenant_id_ctx
from tests.fixtures import owned_baseline_postgres as owned

initialize_database_for_tests = owned.initialize_database_for_tests
prepare_database = owned.prepare_database
clean_database = owned.clean_database
default_database_guard = owned.default_database_guard

_RUN = os.environ.get("RUN_INTEGRATION_TESTS") == "1"
pytestmark = [
    pytest.mark.integration,
    pytest.mark.timeout(300, method="signal", func_only=False),
    pytest.mark.skipif(
        not _RUN,
        reason="Set RUN_INTEGRATION_TESTS=1 to run PostgreSQL preflight tests",
    ),
]

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

    request.getfixturevalue("default_database_guard")
    assert request.config.getoption("timeout_disable_debugger_detection", False), (
        "Password preflight tests require --timeout-disable-debugger-detection"
    )
    with (
        owned.owned_postgres_server() as server,
        owned.committed_baseline(server) as baseline,
    ):
        parsed = baseline.url
        admin_url = parsed.set(drivername="postgresql").render_as_string(
            hide_password=False
        )
        reader_password = uuid4().hex + uuid4().hex
        seeded = bool(request.param)
        with closing(psycopg.connect(admin_url, connect_timeout=5)) as connection:
            with connection.cursor() as cursor:
                for role in (_READER, _UNAPPROVED_READER):
                    cursor.execute(
                        sql.SQL(
                            "CREATE ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS "
                            "NOINHERIT PASSWORD {}"
                        ).format(sql.Identifier(role), sql.Literal(reader_password))
                    )
                    cursor.execute(
                        sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(
                            sql.Identifier(role)
                        )
                    )
                    cursor.execute(
                        sql.SQL("GRANT SELECT ON public.users TO {}").format(
                            sql.Identifier(role)
                        )
                    )
                cursor.execute(
                    sql.SQL("GRANT ue_rls_bypass TO {}").format(sql.Identifier(_READER))
                )
                if seeded:
                    for suffix in range(10, 14):
                        tenant = UUID(f"00000000-0000-4000-8000-{suffix:012d}")
                        cursor.execute(
                            "INSERT INTO tenants (id, name, slug) VALUES (%s, %s, %s)",
                            (tenant, f"Preflight {suffix}", f"preflight-{suffix}"),
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
                query={},
            ).render_as_string(hide_password=False)
            for role in (_READER, _UNAPPROVED_READER)
        ]
        yield admin_url, reader_urls[0], reader_urls[1], seeded


def _sync_url(url: str) -> str:
    return (
        make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)
    )


def _snapshot(admin_url: str) -> list[tuple[object, ...]]:
    with closing(psycopg.connect(admin_url, connect_timeout=5)) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, email, hashed_password, is_active, tenant_id "
                "FROM users ORDER BY id"
            )
            return cursor.fetchall()


def _assert_reader_is_select_only(reader_url: str) -> None:
    with closing(
        psycopg.connect(_sync_url(reader_url), connect_timeout=5)
    ) as connection:
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
    engine: AsyncEngine = create_async_engine(
        reader_url,
        poolclass=NullPool,
        connect_args={
            "timeout": 5,
            "command_timeout": 65,
            "server_settings": {
                "lock_timeout": "10s",
                "statement_timeout": "60s",
                "idle_in_transaction_session_timeout": "60s",
            },
        },
    )
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
    with closing(
        psycopg.connect(_sync_url(unapproved_url), connect_timeout=5)
    ) as connection:
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

    engine: AsyncEngine = create_async_engine(
        unapproved_url,
        poolclass=NullPool,
        connect_args={
            "timeout": 5,
            "command_timeout": 65,
            "server_settings": {
                "lock_timeout": "10s",
                "statement_timeout": "60s",
                "idle_in_transaction_session_timeout": "60s",
            },
        },
    )
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
