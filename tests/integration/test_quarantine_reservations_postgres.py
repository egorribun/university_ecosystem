from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import event, select, update
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.quarantine import QuarantineReservation
from app.services.quarantine import (
    QuarantineQuotaExceeded,
    QuarantineService,
    QuarantineStoreUnavailable,
)
from app.services.storage import StaticFSStorage
from tests.fixtures import owned_baseline_postgres as owned

initialize_database_for_tests = owned.initialize_database_for_tests
prepare_database = owned.prepare_database
clean_database = owned.clean_database
default_database_guard = owned.default_database_guard
owned_baseline_server = owned.owned_baseline_server

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.timeout(300, method="signal", func_only=False),
]


@pytest_asyncio.fixture
async def quarantine_baseline(
    request: pytest.FixtureRequest,
) -> AsyncIterator[tuple[AsyncEngine, Any]]:
    assert os.getenv("RUN_INTEGRATION_TESTS") == "1", "Requires integration opt-in"
    assert request.config.getoption("timeout_disable_debugger_detection", False), (
        "Quarantine tests require --timeout-disable-debugger-detection"
    )
    server = request.getfixturevalue("owned_baseline_server")
    with owned.committed_baseline(server) as baseline:
        engine = create_async_engine(
            baseline.url.set(drivername="postgresql+asyncpg", query={}),
            poolclass=sa.pool.NullPool,
            hide_parameters=True,
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
        try:
            yield engine, baseline.migration
        finally:
            await engine.dispose()


def _postgres_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    assert engine.dialect.name == "postgresql"
    assert engine.url.drivername == "postgresql+asyncpg"
    return async_sessionmaker(engine, expire_on_commit=False)


async def _reservation_rows(
    factory: async_sessionmaker[AsyncSession],
) -> list[QuarantineReservation]:
    async with factory() as session:
        return list((await session.scalars(select(QuarantineReservation))).all())


async def test_independent_workers_cannot_overbook_one_storage_scope(
    tmp_path: Path,
    quarantine_baseline: tuple[AsyncEngine, Any],
) -> None:
    """Two sessions serialize at the shared scope row before byte admission."""
    session_factory = _postgres_factory(quarantine_baseline[0])
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
    quarantine_baseline: tuple[AsyncEngine, Any],
) -> None:
    """A lost PUT acknowledgement cannot free quota before a late remote write."""
    session_factory = _postgres_factory(quarantine_baseline[0])
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


async def test_quarantine_ledger_baseline_has_complete_irreversible_schema(
    quarantine_baseline: tuple[AsyncEngine, Any],
) -> None:
    """Inspect the actual baseline and prove downgrade emits no DDL."""
    engine, migration = quarantine_baseline
    schema = "public"
    async with engine.connect() as connection:
        transaction = await connection.begin()
        try:

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
                    "quarantine_reservations",
                    schema=schema,
                    postgresql_ignore_search_path=True,
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
