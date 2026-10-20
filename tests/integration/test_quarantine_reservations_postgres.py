from __future__ import annotations

import asyncio
import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import event, select, text, update
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import database
from app.models.quarantine import QuarantineReservation
from app.services.quarantine import (
    QuarantineQuotaExceeded,
    QuarantineService,
    QuarantineStoreUnavailable,
)
from app.services.storage import StaticFSStorage

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _postgres_factory() -> async_sessionmaker[AsyncSession]:
    if (
        database.engine.dialect.name != "postgresql"
        or database.engine.url.drivername != "postgresql+asyncpg"
    ):
        pytest.fail(
            "cross-worker quarantine quota proof requires PostgreSQL via asyncpg",
            pytrace=False,
        )
    return async_sessionmaker(database.engine, expire_on_commit=False)


async def _reservation_rows(
    factory: async_sessionmaker[AsyncSession],
) -> list[QuarantineReservation]:
    async with factory() as session:
        return list((await session.scalars(select(QuarantineReservation))).all())


async def test_independent_workers_cannot_overbook_one_storage_scope(
    tmp_path: Path,
) -> None:
    """Two sessions serialize at the shared scope row before byte admission."""
    session_factory = _postgres_factory()
    barrier = asyncio.Barrier(2)

    class SynchronizedService(QuarantineService):
        async def _reserve(self, key: str, size_bytes: int) -> Any:
            await asyncio.wait_for(barrier.wait(), timeout=5)
            return await super()._reserve(key, size_bytes)

    backend_one = StaticFSStorage(tmp_path)
    backend_two = StaticFSStorage(tmp_path)
    first = SynchronizedService(
        backend_one,
        session_factory=session_factory,
        quota_bytes=5,
        explicit_scope_id="aud241-shared-quota-race",
    )
    second = SynchronizedService(
        backend_two,
        session_factory=session_factory,
        quota_bytes=5,
        explicit_scope_id="aud241-shared-quota-race",
    )
    assert first.scope_id == second.scope_id
    assert await first.ensure_inventory_complete() is True
    assert await second.ensure_inventory_complete() is True

    outcomes = await asyncio.wait_for(
        asyncio.gather(
            first.store("quarantine/worker-one.bin", b"1234"),
            second.store("quarantine/worker-two.bin", b"5678"),
            return_exceptions=True,
        ),
        timeout=10,
    )

    successes = [outcome for outcome in outcomes if isinstance(outcome, str)]
    failures = [outcome for outcome in outcomes if isinstance(outcome, Exception)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], QuarantineQuotaExceeded)
    rows = await _reservation_rows(session_factory)
    assert len(rows) == 1
    assert rows[0].status == "stored"
    assert rows[0].size_bytes == 4
    assert len(list((tmp_path / "quarantine").glob("worker-*.bin"))) == 1


async def test_pending_reservation_survives_absence_observation_and_late_put(
    tmp_path: Path,
) -> None:
    """A lost PUT acknowledgement cannot free quota before a late remote write."""
    session_factory = _postgres_factory()
    entered_put = asyncio.Event()
    allow_late_put = asyncio.Event()

    class DelayedPutStorage(StaticFSStorage):
        async def save_file(
            self, relative_path: str, data: bytes, **kwargs: Any
        ) -> str:
            entered_put.set()
            await allow_late_put.wait()
            await super().save_file(relative_path, data, **kwargs)
            raise TimeoutError("synthetic lost acknowledgement")

    backend = DelayedPutStorage(tmp_path)
    service = QuarantineService(
        backend,
        session_factory=session_factory,
        quota_bytes=8,
        retention_days=1,
        explicit_scope_id="aud241-late-put",
    )
    assert await service.ensure_inventory_complete() is True
    write = asyncio.create_task(service.store("quarantine/late.bin", b"late"))
    try:
        await asyncio.wait_for(entered_put.wait(), timeout=5)

        rows = await _reservation_rows(session_factory)
        assert len(rows) == 1
        assert rows[0].status == "pending"
        assert rows[0].size_bytes == 4
        absent = await backend.list_quarantine_page(None, limit=10)
        assert absent.objects == ()
        assert await service.sweep_once() == 0
        async with session_factory() as session:
            await session.execute(
                update(QuarantineReservation).values(
                    created_at=datetime(2000, 1, 1, tzinfo=UTC)
                )
            )
            await session.commit()
        assert await service.sweep_once() == 0

        allow_late_put.set()
        with pytest.raises(QuarantineStoreUnavailable):
            await asyncio.wait_for(write, timeout=5)

        assert (tmp_path / "quarantine" / "late.bin").read_bytes() == b"late"
        rows = await _reservation_rows(session_factory)
        assert len(rows) == 1
        assert rows[0].status == "pending"
        assert rows[0].size_bytes == 4
        assert await service.sweep_once() == 0
    finally:
        allow_late_put.set()
        if not write.done():
            completed, _ = await asyncio.wait({write}, timeout=5)
            if not completed:
                write.cancel()
                completed, _ = await asyncio.wait({write}, timeout=5)
                if not completed:
                    pytest.fail(
                        "delayed quarantine PUT task did not stop after cancellation"
                    )
        if write.done() and not write.cancelled():
            error = write.exception()
            if error is not None and not isinstance(error, QuarantineStoreUnavailable):
                raise error


def _load_ledger_migration() -> Any:
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "202610200001_add_quarantine_storage_ledger.py"
    )
    spec = importlib.util.spec_from_file_location(
        "aud241_quarantine_ledger_postgres_acceptance", migration_path
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


async def test_quarantine_ledger_migration_creates_complete_irreversible_schema() -> (
    None
):
    """Exercise real PostgreSQL DDL and prove refusal leaves it untouched."""
    _postgres_factory()  # Validate the same live asyncpg engine used by both cases.
    engine = database.engine
    assert engine is not None
    migration = _load_ledger_migration()
    schema = f"aud241_migration_{uuid4().hex}"

    async with engine.connect() as connection:
        transaction = await connection.begin()
        try:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            await connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            assert await connection.scalar(text("SELECT current_schema()")) == schema

            def upgrade(sync_connection: Connection) -> None:
                with Operations.context(MigrationContext.configure(sync_connection)):
                    migration.upgrade()

            await connection.run_sync(upgrade)

            def assert_schema(sync_connection: Connection) -> None:
                inspector = sa.inspect(sync_connection)
                assert inspector.has_table("quarantine_storage_scopes", schema=schema)
                assert inspector.has_table("quarantine_reservations", schema=schema)

                scopes = {
                    column["name"]: column
                    for column in inspector.get_columns(
                        "quarantine_storage_scopes", schema=schema
                    )
                }
                assert set(scopes) == {
                    "scope_id",
                    "inventory_complete",
                    "inventory_cursor",
                    "created_at",
                }
                assert scopes["scope_id"]["nullable"] is False
                assert scopes["scope_id"]["type"].length == 64
                assert scopes["inventory_complete"]["nullable"] is False
                assert scopes["inventory_cursor"]["nullable"] is True

                reservations = {
                    column["name"]: column
                    for column in inspector.get_columns(
                        "quarantine_reservations", schema=schema
                    )
                }
                assert set(reservations) == {
                    "id",
                    "scope_id",
                    "object_key",
                    "size_bytes",
                    "status",
                    "created_at",
                    "expires_at",
                }
                assert reservations["id"]["nullable"] is False
                assert reservations["scope_id"]["nullable"] is False
                assert reservations["scope_id"]["type"].length == 64
                assert reservations["object_key"]["nullable"] is False
                assert reservations["object_key"]["type"].length == 2048
                assert reservations["size_bytes"]["nullable"] is False
                assert reservations["status"]["nullable"] is False
                assert reservations["status"]["type"].length == 16
                assert reservations["expires_at"]["nullable"] is True

                assert inspector.get_pk_constraint(
                    "quarantine_storage_scopes", schema=schema
                )["constrained_columns"] == ["scope_id"]
                assert inspector.get_pk_constraint(
                    "quarantine_reservations", schema=schema
                )["constrained_columns"] == ["id"]
                assert {
                    (item["name"], tuple(item["column_names"]))
                    for item in inspector.get_unique_constraints(
                        "quarantine_reservations", schema=schema
                    )
                } == {
                    (
                        "uq_quarantine_reservation_object",
                        ("scope_id", "object_key"),
                    )
                }
                foreign_keys = inspector.get_foreign_keys(
                    "quarantine_reservations", schema=schema
                )
                assert len(foreign_keys) == 1
                assert foreign_keys[0]["constrained_columns"] == ["scope_id"]
                assert foreign_keys[0]["referred_schema"] == schema
                assert foreign_keys[0]["referred_table"] == "quarantine_storage_scopes"
                assert foreign_keys[0]["referred_columns"] == ["scope_id"]

                checks = {
                    item["name"]: item["sqltext"]
                    for item in inspector.get_check_constraints(
                        "quarantine_reservations", schema=schema
                    )
                }
                assert set(checks) == {
                    "ck_quarantine_reservation_size",
                    "ck_quarantine_reservation_status",
                }
                assert "size_bytes >= 0" in checks["ck_quarantine_reservation_size"]
                status_check = checks["ck_quarantine_reservation_status"]
                assert all(
                    status in status_check
                    for status in ("pending", "stored", "deleting")
                )
                indexes = {
                    item["name"]: item
                    for item in inspector.get_indexes(
                        "quarantine_reservations", schema=schema
                    )
                }
                assert "ix_quarantine_reservations_expiry" in indexes
                assert indexes["ix_quarantine_reservations_expiry"]["column_names"] == [
                    "scope_id",
                    "status",
                    "expires_at",
                ]

            await connection.run_sync(assert_schema)

            def assert_downgrade_refuses_ddl(sync_connection: Connection) -> None:
                statements: list[str] = []

                def record_statement(
                    _connection: Connection,
                    _cursor: Any,
                    statement: str,
                    _parameters: Any,
                    _context: Any,
                    _executemany: bool,
                ) -> None:
                    statements.append(statement)

                event.listen(sync_connection, "before_cursor_execute", record_statement)
                try:
                    with Operations.context(
                        MigrationContext.configure(sync_connection)
                    ):
                        with pytest.raises(RuntimeError) as error:
                            migration.downgrade()
                    assert str(error.value) == migration.downgrade_reason
                    assert statements == []
                finally:
                    event.remove(
                        sync_connection, "before_cursor_execute", record_statement
                    )

            await connection.run_sync(assert_downgrade_refuses_ddl)
        finally:
            if transaction.is_active:
                await transaction.rollback()

    async with engine.connect() as verification:
        schema_exists = await verification.scalar(
            text("SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = :schema)"),
            {"schema": schema},
        )
    assert schema_exists is False
