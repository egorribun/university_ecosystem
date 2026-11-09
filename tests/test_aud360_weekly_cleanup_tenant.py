"""Do not infer orphanhood from RLS-filtered PostgreSQL users."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.tenant import bypass_rls_ctx, tenant_id_ctx
from app.management import weekly_cleanup as cleanup


def session(dialect="postgresql", witness=True):
    db = AsyncMock()
    db.get_bind = MagicMock(
        return_value=SimpleNamespace(dialect=SimpleNamespace(name=dialect))
    )
    result = MagicMock()
    result.scalar_one.return_value = witness
    result.scalars.return_value.fetchmany.return_value = []
    db.execute.return_value = result
    db.__aenter__.return_value = db
    return db


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ambient",
    [
        "",
        "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    ],
)
@pytest.mark.parametrize("bypass", [False, True])
async def test_canonical_postgres_fk_skips_orphan_delete_without_changing_scope(
    ambient, bypass
):
    db = session()
    tenant_token = tenant_id_ctx.set(ambient)
    bypass_token = bypass_rls_ctx.set(bypass)
    try:
        assert await cleanup._delete_orphaned_subscriptions(db) == 0
        assert tenant_id_ctx.get() == ambient
        assert bypass_rls_ctx.get() == bypass
    finally:
        bypass_rls_ctx.reset(bypass_token)
        tenant_id_ctx.reset(tenant_token)
    db.execute.assert_awaited_once()
    sql = str(db.execute.await_args.args[0]).lower()
    assert sql.lstrip().startswith("select")
    assert "delete from" not in sql
    assert "select users" not in sql
    for condition in (
        "pg_catalog.pg_constraint",
        "fk.conname = 'fk_push_subscriptions_user_id'",
        "fk.contype = 'f'",
        "not child.attisdropped and child.attnotnull",
        "not parent.attisdropped and parent.attnotnull",
        "child.atttypid = 'pg_catalog.uuid'::pg_catalog.regtype",
        "parent.atttypid = 'pg_catalog.uuid'::pg_catalog.regtype",
        "fk.conrelid = pg_catalog.to_regclass('push_subscriptions')",
        "fk.confrelid = pg_catalog.to_regclass('users')",
        "convalidated",
        "not fk.condeferrable",
        "not fk.condeferred",
        "confdeltype = 'c'",
        "conkey = array[child.attnum]",
        "confkey = array[parent.attnum]",
        "public.push_subscriptions",
        "public.users",
    ):
        assert condition in sql
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("witness", [False, None, 1, "true"])
async def test_missing_or_drifted_postgres_fk_fails_before_any_cleanup(
    monkeypatch, witness
):
    db = session(witness=witness)
    monkeypatch.setattr(cleanup, "async_session", lambda: db)
    stale = AsyncMock()
    monkeypatch.setattr(cleanup, "_delete_stale_subscriptions", stale)
    with pytest.raises(RuntimeError, match="foreign key"):
        await cleanup.run_weekly_cleanup()
    stale.assert_not_awaited()
    db.commit.assert_not_awaited()
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_postgres_catalog_error_does_not_fall_back_to_delete(monkeypatch):
    db = session()
    db.execute.side_effect = OperationalError(
        "catalog", {}, RuntimeError("unavailable")
    )
    monkeypatch.setattr(cleanup, "async_session", lambda: db)
    stale = AsyncMock()
    monkeypatch.setattr(cleanup, "_delete_stale_subscriptions", stale)
    with pytest.raises(OperationalError):
        await cleanup.run_weekly_cleanup()
    stale.assert_not_awaited()
    db.commit.assert_not_awaited()
    assert "delete from" not in str(db.execute.await_args.args[0]).lower()


@pytest.mark.asyncio
async def test_unsupported_dialect_fails_before_sql():
    db = session(dialect="unknown")
    with pytest.raises(RuntimeError, match="dialect"):
        await cleanup._delete_orphaned_subscriptions(db)
    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_sqlite_legacy_orphan_cleanup_preserves_valid_parent():
    from sqlalchemy import text

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    parent, valid, orphan = uuid4(), uuid4(), uuid4()
    try:
        async with engine.begin() as connection:
            # Explicit legacy fixture: no FK, no RLS. Never use this on a service.
            await connection.execute(text("CREATE TABLE users (id TEXT PRIMARY KEY)"))
            await connection.execute(
                text(
                    "CREATE TABLE push_subscriptions (id TEXT PRIMARY KEY, user_id TEXT NOT NULL)"
                )
            )
            await connection.execute(
                text("INSERT INTO users VALUES (:id)"), {"id": parent.hex}
            )
            await connection.execute(
                text("INSERT INTO push_subscriptions VALUES (:id, :owner)"),
                [
                    {"id": valid.hex, "owner": parent.hex},
                    {"id": orphan.hex, "owner": uuid4().hex},
                ],
            )
        async with async_sessionmaker(engine)() as db:
            assert await cleanup._delete_orphaned_subscriptions(db) == 1
            assert (
                await db.execute(text("SELECT id FROM push_subscriptions"))
            ).scalars().all() == [valid.hex]
            assert await cleanup._delete_orphaned_subscriptions(db) == 0
    finally:
        await engine.dispose()


def test_module_entrypoint_calls_cleanup_without_opening_database(monkeypatch):
    import runpy

    calls = []

    def run(coroutine):
        calls.append(coroutine.cr_code.co_name)
        coroutine.close()
        return {"subscriptions_removed": 0}

    monkeypatch.setattr(cleanup.asyncio, "run", run)
    runpy.run_path(cleanup.__file__, run_name="__main__")
    assert calls == ["run_weekly_cleanup"]


@pytest.mark.asyncio
async def test_supported_postgres_continues_stale_cleanup_and_reports_deleted_counts(
    monkeypatch,
):
    db = session()
    monkeypatch.setattr(cleanup, "async_session", lambda: db)
    stale = AsyncMock(return_value=2)
    monkeypatch.setattr(cleanup, "_delete_stale_subscriptions", stale)
    tenant_token = tenant_id_ctx.set("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
    bypass_token = bypass_rls_ctx.set(True)
    try:
        assert await cleanup.run_weekly_cleanup() == {
            "subscriptions_removed": 2,
            "subscriptions_orphaned": 0,
            "subscriptions_stale": 2,
        }
        stale.assert_awaited_once_with(db)
        assert tenant_id_ctx.get() == "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        assert bypass_rls_ctx.get() is True
        db.execute.assert_awaited_once()
        assert "delete from" not in str(db.execute.await_args.args[0]).lower()
    finally:
        bypass_rls_ctx.reset(bypass_token)
        tenant_id_ctx.reset(tenant_token)
