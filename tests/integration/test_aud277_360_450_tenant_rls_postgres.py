"""Opt-in PostgreSQL characterization of the historical tenant policies.

Run only against an explicitly designated disposable PostgreSQL database with a
non-superuser, non-BYPASSRLS role allowed to create temporary tables. All DDL
and data below use connection-local temporary tables and are rolled back. This
does not validate a deployed database, role, migration history, or application.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.db.listeners import set_pg_tenant_context
from app.core.tenant import bypass_rls_ctx, tenant_id_ctx
from tests.test_aud277_360_450_tenant_rls_contract import (
    capture_message_upgrade,
    capture_tenant_upgrade,
)

_URL = os.getenv("AUD_TENANT_RLS_DISPOSABLE_PG_URL", "")
_OPTED_IN = os.getenv("AUD_TENANT_RLS_DISPOSABLE") == "1"
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (_OPTED_IN and _URL.startswith("postgresql+asyncpg://")),
        reason="Set AUD_TENANT_RLS_DISPOSABLE=1 and a dedicated non-superuser AUD_TENANT_RLS_DISPOSABLE_PG_URL",
    ),
]

_TENANT_A = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
_TENANT_B = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
_USER_A = uuid.UUID("11111111-1111-4111-8111-111111111111")
_CHAT_A = uuid.UUID("22222222-2222-4222-8222-222222222222")
_CHAT_B = uuid.UUID("33333333-3333-4333-8333-333333333333")


@pytest_asyncio.fixture
async def isolated_rls_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncConnection]:
    with monkeypatch.context() as patch:
        message_sql = capture_message_upgrade(patch)
        _, tenant_sql, _ = capture_tenant_upgrade(patch, ("news", "messages"))

    engine = create_async_engine(_URL, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            transaction = await conn.begin()
            try:
                role = (
                    await conn.execute(
                        text(
                            "SELECT rolsuper, rolbypassrls FROM pg_roles "
                            "WHERE rolname = current_user"
                        )
                    )
                ).one()
                assert role.rolsuper is False and role.rolbypassrls is False

                # Temp relations shadow real names; only these are changed.
                await conn.execute(
                    text(
                        "CREATE TEMP TABLE news (id integer PRIMARY KEY, tenant_id uuid, body text) ON COMMIT DROP"
                    )
                )
                await conn.execute(
                    text(
                        "CREATE TEMP TABLE messages (id integer PRIMARY KEY, tenant_id uuid, chat_id uuid) ON COMMIT DROP"
                    )
                )
                await conn.execute(
                    text(
                        "CREATE TEMP TABLE chat_participants (chat_id uuid, user_id uuid) ON COMMIT DROP"
                    )
                )
                await conn.execute(text("SET LOCAL search_path = pg_temp, pg_catalog"))
                for row_id, tenant in ((1, _TENANT_A), (2, _TENANT_B), (3, None)):
                    await conn.execute(
                        text(
                            "INSERT INTO news (id, tenant_id, body) VALUES (:id, :tenant, 'fixture')"
                        ),
                        {"id": row_id, "tenant": tenant},
                    )
                await conn.execute(
                    text(
                        "INSERT INTO chat_participants (chat_id, user_id) VALUES (:chat, :user)"
                    ),
                    {"chat": _CHAT_A, "user": _USER_A},
                )
                for row_id, tenant, chat in (
                    (11, _TENANT_A, _CHAT_A),
                    (12, _TENANT_B, _CHAT_A),
                    (13, None, _CHAT_A),
                    (14, _TENANT_A, _CHAT_B),
                ):
                    await conn.execute(
                        text(
                            "INSERT INTO messages (id, tenant_id, chat_id) VALUES (:id, :tenant, :chat)"
                        ),
                        {"id": row_id, "tenant": tenant, "chat": chat},
                    )

                for statement in (*message_sql, *tenant_sql):
                    await conn.execute(text(statement))
                for table in ("news", "messages"):
                    active = await conn.scalar(
                        text("SELECT row_security_active(to_regclass(:relation))"),
                        {"relation": f"pg_temp.{table}"},
                    )
                    assert active is True
                yield conn
            finally:
                if transaction.is_active:
                    await transaction.rollback()
    finally:
        await engine.dispose()


async def _set_application_tenant(
    conn: AsyncConnection, tenant: uuid.UUID | None
) -> None:
    tenant_token = tenant_id_ctx.set(str(tenant) if tenant else "")
    bypass_token = bypass_rls_ctx.set(False)
    try:
        await conn.run_sync(
            lambda sync_conn: set_pg_tenant_context(None, None, sync_conn)
        )
    finally:
        bypass_rls_ctx.reset(bypass_token)
        tenant_id_ctx.reset(tenant_token)


async def _ids(conn: AsyncConnection, table: str) -> set[int]:
    statements = {
        "news": text("SELECT id FROM news ORDER BY id"),
        "messages": text("SELECT id FROM messages ORDER BY id"),
    }
    result = await conn.execute(statements[table])
    return set(result.scalars())


@pytest.mark.asyncio
async def test_aud277_360_450_postgres_policy_composition_null_writes_and_guc_bypass(
    isolated_rls_connection: AsyncConnection,
) -> None:
    conn = isolated_rls_connection
    await conn.execute(
        text("SELECT set_config('app.current_user_id', :user_id, true)"),
        {"user_id": str(_USER_A)},
    )
    await _set_application_tenant(conn, None)
    assert await _ids(conn, "news") == {3}

    await _set_application_tenant(conn, _TENANT_A)
    assert await _ids(conn, "news") == {1, 3}
    assert await _ids(conn, "messages") == {11, 13}
    with pytest.raises(DBAPIError):
        async with conn.begin_nested():
            await conn.execute(
                text(
                    "INSERT INTO news (id, tenant_id, body) VALUES (5, :other, 'foreign')"
                ),
                {"other": _TENANT_B},
            )
    with pytest.raises(DBAPIError):
        async with conn.begin_nested():
            await conn.execute(
                text("UPDATE news SET tenant_id = :other WHERE id = 1"),
                {"other": _TENANT_B},
            )

    # Like the mapped news INSERT, this write omits the nullable tenant column.
    await conn.execute(text("INSERT INTO news (id, body) VALUES (4, 'no tenant')"))
    await _set_application_tenant(conn, _TENANT_B)
    assert await _ids(conn, "news") == {2, 3, 4}

    # SQL access also permits changing the tenant identity GUC directly.
    await conn.execute(
        text("SELECT set_config('app.current_tenant', :tenant_id, true)"),
        {"tenant_id": str(_TENANT_A)},
    )
    assert await _ids(conn, "news") == {1, 3, 4}

    await _set_application_tenant(conn, _TENANT_A)
    # This role is subject to RLS, yet can set the custom bypass GUC itself.
    await conn.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
    assert await _ids(conn, "news") == {1, 2, 3, 4}
    # The message participant policy still applies: chat B remains invisible.
    assert await _ids(conn, "messages") == {11, 12, 13}
