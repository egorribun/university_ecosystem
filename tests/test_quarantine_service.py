from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.quarantine import QuarantineReservation, QuarantineStorageScope
from app.services.quarantine import (
    QuarantineInventoryIncomplete,
    QuarantineQuotaExceeded,
    QuarantineService,
    QuarantineStoreUnavailable,
    storage_scope_identifier,
)
from app.services.storage import (
    QuarantineObject,
    QuarantineStoragePage,
    S3Storage,
    StaticFSStorage,
)


@pytest.fixture
async def ledger_factory() -> Any:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(QuarantineStorageScope.__table__.create)
        await connection.run_sync(QuarantineReservation.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def _reservations(
    factory: async_sessionmaker[AsyncSession],
) -> list[QuarantineReservation]:
    async with factory() as session:
        return list((await session.scalars(select(QuarantineReservation))).all())


def _service(
    backend: StaticFSStorage,
    factory: async_sessionmaker[AsyncSession],
    *,
    quota_bytes: int = 1024,
    retention_days: int = 7,
    inventory_page_size: int = 100,
) -> QuarantineService:
    return QuarantineService(
        backend,
        session_factory=factory,
        quota_bytes=quota_bytes,
        retention_days=retention_days,
        inventory_page_size=inventory_page_size,
        explicit_scope_id="quarantine-service-test",
    )


@pytest.mark.asyncio
async def test_inventory_imports_existing_files_before_admitting_new_payloads(
    tmp_path: Path, ledger_factory: async_sessionmaker[AsyncSession]
) -> None:
    root = tmp_path / "quarantine"
    (root / "nested").mkdir(parents=True)
    (root / "legacy.bin").write_bytes(b"old")
    (root / "nested" / "second.bin").write_bytes(b"older")
    backend = StaticFSStorage(tmp_path)
    service = _service(backend, ledger_factory, inventory_page_size=1)

    assert await service.ensure_inventory_complete() is True
    before = await _reservations(ledger_factory)
    assert {(row.object_key, row.size_bytes, row.status) for row in before} == {
        ("quarantine/legacy.bin", 3, "stored"),
        ("quarantine/nested/second.bin", 5, "stored"),
    }
    async with ledger_factory() as session:
        scope = await session.get(QuarantineStorageScope, service.scope_id)
    assert scope is not None and scope.inventory_complete is True
    assert scope.inventory_cursor is None

    await service.store("quarantine/rejected/payload.bin", b"new payload")
    after = await _reservations(ledger_factory)
    assert len(after) == 3
    stored = next(row for row in after if row.object_key.endswith("payload.bin"))
    assert stored.status == "stored"
    assert stored.expires_at is not None
    assert stored.expires_at > stored.created_at


@pytest.mark.asyncio
async def test_reservation_is_committed_before_backend_write(
    tmp_path: Path, ledger_factory: async_sessionmaker[AsyncSession]
) -> None:
    observations: list[tuple[str, int]] = []

    class InspectingStorage(StaticFSStorage):
        async def save_file(
            self, relative_path: str, data: bytes, **kwargs: Any
        ) -> str:
            async with ledger_factory() as session:
                row = await session.scalar(
                    select(QuarantineReservation).where(
                        QuarantineReservation.object_key == relative_path
                    )
                )
                assert row is not None
                observations.append((row.status, row.size_bytes))
            return await super().save_file(relative_path, data, **kwargs)

    service = _service(InspectingStorage(tmp_path), ledger_factory)
    await service.store("quarantine/new.bin", b"payload")

    assert observations == [("pending", 7)]
    rows = await _reservations(ledger_factory)
    assert len(rows) == 1 and rows[0].status == "stored"


@pytest.mark.asyncio
async def test_quota_rejects_before_writing_and_counts_all_reservations(
    tmp_path: Path, ledger_factory: async_sessionmaker[AsyncSession]
) -> None:
    backend = StaticFSStorage(tmp_path)
    service = _service(backend, ledger_factory, quota_bytes=4)
    await service.store("quarantine/one.bin", b"1234")

    with pytest.raises(QuarantineQuotaExceeded):
        await service.store("quarantine/two.bin", b"x")

    assert (tmp_path / "quarantine" / "one.bin").read_bytes() == b"1234"
    assert not (tmp_path / "quarantine" / "two.bin").exists()
    assert [row.object_key for row in await _reservations(ledger_factory)] == [
        "quarantine/one.bin"
    ]


@pytest.mark.asyncio
async def test_delayed_put_remains_charged_after_absence_and_late_write(
    tmp_path: Path, ledger_factory: async_sessionmaker[AsyncSession]
) -> None:
    entered = asyncio.Event()
    finish_put = asyncio.Event()

    class DelayedPutStorage(StaticFSStorage):
        async def save_file(
            self, relative_path: str, data: bytes, **kwargs: Any
        ) -> str:
            entered.set()
            await finish_put.wait()
            await super().save_file(relative_path, data, **kwargs)
            raise TimeoutError("write reached storage but acknowledgement was lost")

    backend = DelayedPutStorage(tmp_path)
    service = _service(backend, ledger_factory, retention_days=1)
    store_task = asyncio.create_task(service.store("quarantine/late.bin", b"late"))
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)

        pending = await _reservations(ledger_factory)
        assert [(row.status, row.size_bytes) for row in pending] == [("pending", 4)]
        assert await service.sweep_once() == 0
        async with ledger_factory() as session:
            await session.execute(
                update(QuarantineReservation).values(
                    created_at=datetime.now(UTC) - timedelta(days=30)
                )
            )
            await session.commit()
        assert await service.sweep_once() == 0

        finish_put.set()
        with pytest.raises(QuarantineStoreUnavailable):
            await asyncio.wait_for(store_task, timeout=2)

        late_file = tmp_path / "quarantine" / "late.bin"
        assert late_file.read_bytes() == b"late"
        pending = await _reservations(ledger_factory)
        assert [(row.status, row.size_bytes) for row in pending] == [("pending", 4)]
        assert await service.sweep_once() == 0
    finally:
        finish_put.set()
        if not store_task.done():
            completed, _ = await asyncio.wait({store_task}, timeout=2)
            if not completed:
                store_task.cancel()
                completed, _ = await asyncio.wait({store_task}, timeout=2)
                if not completed:
                    pytest.fail(
                        "delayed quarantine PUT task did not stop after cancellation"
                    )
        if store_task.done() and not store_task.cancelled():
            error = store_task.exception()
            if error is not None and not isinstance(error, QuarantineStoreUnavailable):
                raise error


@pytest.mark.asyncio
async def test_cancelled_put_keeps_pending_charge(
    tmp_path: Path, ledger_factory: async_sessionmaker[AsyncSession]
) -> None:
    entered = asyncio.Event()
    never_finish = asyncio.Event()

    class CancellableStorage(StaticFSStorage):
        async def save_file(
            self, relative_path: str, data: bytes, **kwargs: Any
        ) -> str:
            entered.set()
            await never_finish.wait()
            return await super().save_file(relative_path, data, **kwargs)

    service = _service(CancellableStorage(tmp_path), ledger_factory)
    task = asyncio.create_task(service.store("quarantine/cancelled.bin", b"x"))
    await asyncio.wait_for(entered.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    rows = await _reservations(ledger_factory)
    assert [(row.status, row.size_bytes) for row in rows] == [("pending", 1)]
    assert await service.sweep_once() == 0
    assert (await _reservations(ledger_factory))[0].status == "pending"


@pytest.mark.asyncio
async def test_sweeper_retains_charge_until_verified_absence(
    tmp_path: Path, ledger_factory: async_sessionmaker[AsyncSession]
) -> None:
    class RetainFirstDeleteStorage(StaticFSStorage):
        retain = True

        async def delete_quarantine_key(self, key: str) -> bool:
            if self.retain:
                self.retain = False
                return False
            return await super().delete_quarantine_key(key)

    backend = RetainFirstDeleteStorage(tmp_path)
    service = _service(backend, ledger_factory, quota_bytes=3)
    await service.store("quarantine/expired.bin", b"old")
    async with ledger_factory() as session:
        await session.execute(
            update(QuarantineReservation).values(
                expires_at=datetime.now(UTC) - timedelta(seconds=1)
            )
        )
        await session.commit()

    assert await service.sweep_once() == 0
    rows = await _reservations(ledger_factory)
    assert len(rows) == 1 and rows[0].status == "deleting"
    with pytest.raises(QuarantineQuotaExceeded):
        await service.store("quarantine/replacement.bin", b"new")

    assert await service.sweep_once() == 1
    assert await _reservations(ledger_factory) == []
    assert await backend.exists("quarantine/expired.bin") is False


@pytest.mark.asyncio
async def test_incomplete_inventory_never_admits_a_write(
    tmp_path: Path,
    ledger_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class EndlessInventoryStorage(StaticFSStorage):
        page_number = 0
        writes = 0

        async def list_quarantine_page(
            self, cursor: str | None, *, limit: int
        ) -> QuarantineStoragePage:
            self.page_number += 1
            return QuarantineStoragePage((), f"cursor-{self.page_number}")

        async def save_file(
            self, relative_path: str, data: bytes, **kwargs: Any
        ) -> str:
            self.writes += 1
            return await super().save_file(relative_path, data, **kwargs)

    monkeypatch.setattr("app.services.quarantine._MAX_BOOTSTRAP_PAGES_PER_CALL", 2)
    backend = EndlessInventoryStorage(tmp_path)
    service = _service(backend, ledger_factory)

    assert await service.ensure_inventory_complete() is False
    with pytest.raises(QuarantineInventoryIncomplete):
        await service.store("quarantine/blocked.bin", b"x")
    with pytest.raises(QuarantineInventoryIncomplete):
        await service._reserve("quarantine/blocked.bin", 1)
    assert await service.sweep_once() == 0
    assert backend.writes == 0
    async with ledger_factory() as session:
        scope = await session.get(QuarantineStorageScope, service.scope_id)
    assert scope is not None and scope.inventory_complete is False


@pytest.mark.asyncio
async def test_unsafe_s3_inventory_blocks_admission_but_does_not_starve_known_cleanup(
    ledger_factory: async_sessionmaker[AsyncSession],
) -> None:
    from unittest.mock import AsyncMock

    from botocore.exceptions import ClientError

    client = AsyncMock()
    client.get_bucket_versioning.return_value = {}
    client.list_objects_v2.return_value = {
        "Contents": [{"Key": "quarantine/../outside.bin", "Size": 1}],
        "IsTruncated": False,
    }
    client.delete_object.return_value = {}
    client.head_object.side_effect = ClientError(
        {"Error": {"Code": "404"}}, "HeadObject"
    )
    backend = S3Storage(bucket="quarantine-test", client=client)
    service = QuarantineService(
        backend,
        session_factory=ledger_factory,
        explicit_scope_id="unsafe-inventory-test",
    )
    async with ledger_factory() as session, session.begin():
        session.add(QuarantineStorageScope(scope_id=service.scope_id))
        await session.flush()
        session.add(
            QuarantineReservation(
                scope_id=service.scope_id,
                object_key="quarantine/known-expired.bin",
                size_bytes=3,
                status="stored",
                expires_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )

    assert await service.sweep_once() == 1

    with pytest.raises(QuarantineInventoryIncomplete):
        await service.store("quarantine/new.bin", b"rejected")
    client.put_object.assert_not_awaited()
    client.delete_object.assert_awaited_once_with(
        Bucket="quarantine-test", Key="quarantine/known-expired.bin"
    )
    async with ledger_factory() as session:
        scope = await session.get(QuarantineStorageScope, service.scope_id)
    assert scope is not None and scope.inventory_complete is False
    assert await _reservations(ledger_factory) == []


def test_storage_scope_is_stable_and_configurable(tmp_path: Path) -> None:
    first = StaticFSStorage(tmp_path)
    same = StaticFSStorage(tmp_path / ".")
    different = StaticFSStorage(tmp_path / "other")

    assert storage_scope_identifier(first) == storage_scope_identifier(same)
    assert storage_scope_identifier(first) != storage_scope_identifier(different)
    assert storage_scope_identifier(first, "shared-store") == storage_scope_identifier(
        different, "shared-store"
    )


@pytest.mark.parametrize(
    "key",
    [
        "users/file.bin",
        "quarantine/../outside.bin",
        "quarantine//empty.bin",
        "quarantine\\escape.bin",
        " quarantine/file.bin",
        "quarantine/file.bin\x00",
        "quarantine/file.bin\x7f",
        None,
        17,
    ],
)
def test_store_rejects_keys_outside_unambiguous_quarantine_prefix(key: Any) -> None:
    with pytest.raises(ValueError, match="object key is invalid"):
        QuarantineService._validate_object_key(key)


@pytest.mark.parametrize("limit", [0, -1, 1001, True])
@pytest.mark.asyncio
async def test_sweep_rejects_unbounded_or_invalid_batch_sizes(
    tmp_path: Path,
    ledger_factory: async_sessionmaker[AsyncSession],
    limit: int,
) -> None:
    service = _service(StaticFSStorage(tmp_path), ledger_factory)

    with pytest.raises(ValueError, match="outside its bound"):
        await service.sweep_once(limit=limit)


class _NoopTransaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_args: Any) -> bool:
        return False


class _EmptySession:
    def __init__(self, dialect_name: str) -> None:
        self._dialect = SimpleNamespace(name=dialect_name)

    def get_bind(self) -> SimpleNamespace:
        return SimpleNamespace(dialect=self._dialect)

    def begin(self) -> _NoopTransaction:
        return _NoopTransaction()

    async def execute(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    async def scalar(self, *_args: Any, **_kwargs: Any) -> None:
        return None


class _SessionContext:
    def __init__(self, session: Any) -> None:
        self.session = session

    async def __aenter__(self) -> Any:
        return self.session

    async def __aexit__(self, *_args: Any) -> bool:
        return False


class _EmptySessionFactory:
    def __init__(self, dialect_name: str) -> None:
        self.dialect_name = dialect_name

    def __call__(self) -> _SessionContext:
        return _SessionContext(_EmptySession(self.dialect_name))


class _DialectProxy:
    def __init__(self, session: AsyncSession, dialect_name: str) -> None:
        self._session = session
        self._dialect = SimpleNamespace(name=dialect_name)

    def get_bind(self) -> SimpleNamespace:
        return SimpleNamespace(dialect=self._dialect)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._session, name)


class _DialectProxyContext:
    def __init__(self, session: AsyncSession, dialect_name: str) -> None:
        self._session = session
        self._dialect_name = dialect_name

    async def __aenter__(self) -> _DialectProxy:
        await self._session.__aenter__()
        return _DialectProxy(self._session, self._dialect_name)

    async def __aexit__(self, *args: Any) -> bool:
        return await self._session.__aexit__(*args)


class _DialectProxyFactory:
    def __init__(
        self, factory: async_sessionmaker[AsyncSession], dialect_name: str
    ) -> None:
        self.factory = factory
        self.dialect_name = dialect_name

    def __call__(self) -> _DialectProxyContext:
        return _DialectProxyContext(self.factory(), self.dialect_name)


@pytest.mark.asyncio
async def test_missing_scope_rows_fail_closed_for_each_ledger_operation(
    tmp_path: Path,
) -> None:
    service = QuarantineService(
        StaticFSStorage(tmp_path), session_factory=_EmptySessionFactory("sqlite")
    )

    with pytest.raises(RuntimeError, match="scope disappeared"):
        await service.ensure_inventory_complete()
    with pytest.raises(QuarantineInventoryIncomplete):
        await service._reserve("quarantine/missing.bin", 1)
    with pytest.raises(RuntimeError, match="reservation disappeared"):
        await service._mark_stored("synthetic-reservation")
    assert await service._release_verified_absence("synthetic-reservation") is False


@pytest.mark.asyncio
async def test_postgresql_upsert_branch_runs_with_the_postgresql_insert_shape(
    tmp_path: Path,
    ledger_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.services.quarantine.postgresql_insert", sqlite_insert)
    existing_object = tmp_path / "quarantine" / "preexisting.bin"
    existing_object.parent.mkdir(parents=True)
    existing_object.write_bytes(b"already managed")
    service = QuarantineService(
        StaticFSStorage(tmp_path),
        session_factory=_DialectProxyFactory(ledger_factory, "postgresql"),
        explicit_scope_id="postgres-dialect-proxy",
    )

    await service.store("quarantine/postgresql-path.bin", b"pg")

    async with ledger_factory() as session:
        stored_row = await session.scalar(
            select(QuarantineReservation).where(
                QuarantineReservation.object_key == "quarantine/postgresql-path.bin"
            )
        )
        imported_row = await session.scalar(
            select(QuarantineReservation).where(
                QuarantineReservation.object_key == "quarantine/preexisting.bin"
            )
        )
    assert stored_row is not None and stored_row.status == "stored"
    assert imported_row is not None
    assert imported_row.status == "stored" and imported_row.size_bytes == 15


@pytest.mark.asyncio
async def test_postgresql_inventory_empty_page_skips_existing_object_upsert(
    tmp_path: Path,
    ledger_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.services.quarantine.postgresql_insert", sqlite_insert)
    service = QuarantineService(
        StaticFSStorage(tmp_path),
        session_factory=_DialectProxyFactory(ledger_factory, "postgresql"),
        explicit_scope_id="postgres-empty-inventory",
    )

    assert await service.ensure_inventory_complete() is True

    async with ledger_factory() as session:
        imported_rows = await session.scalars(
            select(QuarantineReservation).where(
                QuarantineReservation.scope_id == service.scope_id
            )
        )
    assert imported_rows.all() == []


@pytest.mark.asyncio
async def test_unsupported_database_dialect_fails_before_inventory(
    tmp_path: Path,
) -> None:
    service = QuarantineService(
        StaticFSStorage(tmp_path), session_factory=_EmptySessionFactory("mysql")
    )

    with pytest.raises(RuntimeError, match="require PostgreSQL or SQLite"):
        await service.ensure_inventory_complete()


@pytest.mark.asyncio
async def test_inventory_rejects_oversized_and_repeated_cursors(
    tmp_path: Path,
    ledger_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class CursorStorage(StaticFSStorage):
        cursor = "long-cursor"

        async def list_quarantine_page(
            self, cursor: str | None, *, limit: int
        ) -> QuarantineStoragePage:
            del cursor, limit
            return QuarantineStoragePage((), self.cursor)

    monkeypatch.setattr("app.services.quarantine._MAX_CURSOR_LENGTH", 4)
    service = _service(CursorStorage(tmp_path), ledger_factory)
    with pytest.raises(RuntimeError, match="cursor exceeds"):
        await service.ensure_inventory_complete()

    monkeypatch.setattr("app.services.quarantine._MAX_CURSOR_LENGTH", 4096)
    stuck_service = _service(CursorStorage(tmp_path / "stuck"), ledger_factory)
    (tmp_path / "stuck" / "quarantine").mkdir(parents=True)

    class StuckCursorStorage(StaticFSStorage):
        async def list_quarantine_page(
            self, cursor: str | None, *, limit: int
        ) -> QuarantineStoragePage:
            del limit
            return QuarantineStoragePage((), "same" if cursor is None else cursor)

    stuck_service = _service(StuckCursorStorage(tmp_path / "stuck"), ledger_factory)
    with pytest.raises(RuntimeError, match="did not advance"):
        await stuck_service.ensure_inventory_complete()


@pytest.mark.asyncio
async def test_inventory_normalizes_missing_naive_and_future_timestamps(
    tmp_path: Path, ledger_factory: async_sessionmaker[AsyncSession]
) -> None:
    naive = datetime(2020, 1, 2, 3, 4, 5)
    future = datetime.now(UTC) + timedelta(days=1)

    class TimestampStorage(StaticFSStorage):
        async def list_quarantine_page(
            self, cursor: str | None, *, limit: int
        ) -> QuarantineStoragePage:
            del cursor, limit
            return QuarantineStoragePage(
                (
                    QuarantineObject("quarantine/missing-time.bin", 1, None),
                    QuarantineObject("quarantine/naive-time.bin", 1, naive),
                    QuarantineObject("quarantine/future-time.bin", 1, future),
                ),
                None,
            )

    service = _service(TimestampStorage(tmp_path), ledger_factory)
    before = datetime.now(UTC).replace(tzinfo=None)
    assert await service.ensure_inventory_complete() is True
    after = datetime.now(UTC).replace(tzinfo=None)
    rows = {row.object_key: row for row in await _reservations(ledger_factory)}

    assert set(rows) == {
        "quarantine/missing-time.bin",
        "quarantine/naive-time.bin",
        "quarantine/future-time.bin",
    }
    assert before <= rows["quarantine/missing-time.bin"].created_at <= after
    assert rows["quarantine/naive-time.bin"].created_at == naive
    assert before <= rows["quarantine/future-time.bin"].created_at <= after


@pytest.mark.asyncio
async def test_s3_versioning_is_checked_before_storage_or_import(
    ledger_factory: async_sessionmaker[AsyncSession],
) -> None:
    from unittest.mock import AsyncMock

    client = AsyncMock()
    client.get_bucket_versioning.return_value = {"Status": "Enabled"}
    backend = S3Storage(bucket="quarantine-test", client=client)
    service = QuarantineService(
        backend,
        session_factory=ledger_factory,
        explicit_scope_id="s3-versioned-test",
    )

    with pytest.raises(QuarantineStoreUnavailable):
        await service.store("quarantine/blocked.bin", b"secret")

    client.get_bucket_versioning.assert_awaited_once_with(Bucket="quarantine-test")
    client.list_objects_v2.assert_not_awaited()
    client.put_object.assert_not_awaited()


def test_storage_scope_identifies_s3_bucket_and_rejects_unknown_backend() -> None:
    from app.services.storage import StorageBackend

    first = S3Storage(
        bucket="quarantine-test", endpoint_url="https://MINIO.example:9000/"
    )
    same = S3Storage(
        bucket="quarantine-test", endpoint_url="https://minio.example:9000"
    )
    other = S3Storage(
        bucket="different-bucket", endpoint_url="https://minio.example:9000"
    )

    assert storage_scope_identifier(first) == storage_scope_identifier(same)
    assert storage_scope_identifier(first) != storage_scope_identifier(other)

    class UnsupportedStorage(StorageBackend):
        async def save_file(
            self, relative_path: str, data: bytes, **kwargs: Any
        ) -> str:
            del relative_path, data, kwargs
            raise NotImplementedError

        async def delete_file(self, file_url: str) -> None:
            del file_url
            raise NotImplementedError

        async def exists(self, file_url_or_path: str) -> bool:
            del file_url_or_path
            raise NotImplementedError

        async def read_file(
            self, file_url_or_path: str, *, max_bytes: int | None = None
        ) -> bytes:
            del file_url_or_path, max_bytes
            raise NotImplementedError

    with pytest.raises(TypeError, match="Unsupported quarantine storage backend"):
        storage_scope_identifier(UnsupportedStorage())


@pytest.mark.asyncio
async def test_service_uses_configured_defaults_when_overrides_are_omitted(
    tmp_path: Path,
    ledger_factory: async_sessionmaker[AsyncSession],
) -> None:
    from app.core.config import settings

    service = QuarantineService(
        StaticFSStorage(tmp_path), session_factory=ledger_factory
    )

    assert service.retention == timedelta(
        days=settings.storage_quarantine_retention_days
    )
    assert service.quota_bytes == settings.storage_quarantine_quota_bytes
    assert (
        service.inventory_page_size == settings.storage_quarantine_inventory_page_size
    )


class _ChangingDialectProxy(_DialectProxy):
    def __init__(self, session: AsyncSession, dialect_names: list[str]) -> None:
        self._session = session
        self._dialect_names = dialect_names
        self._bind_index = 0

    def get_bind(self) -> SimpleNamespace:
        name = self._dialect_names[min(self._bind_index, len(self._dialect_names) - 1)]
        self._bind_index += 1
        return SimpleNamespace(dialect=SimpleNamespace(name=name))


class _ChangingDialectProxyContext:
    def __init__(self, session: AsyncSession, dialect_names: list[str]) -> None:
        self._session = session
        self._dialect_names = dialect_names

    async def __aenter__(self) -> _ChangingDialectProxy:
        await self._session.__aenter__()
        return _ChangingDialectProxy(self._session, self._dialect_names)

    async def __aexit__(self, *args: Any) -> bool:
        return await self._session.__aexit__(*args)


class _ChangingDialectProxyFactory:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        dialect_names: list[str],
    ) -> None:
        self.factory = factory
        self.dialect_names = dialect_names

    def __call__(self) -> _ChangingDialectProxyContext:
        return _ChangingDialectProxyContext(self.factory(), self.dialect_names)


@pytest.mark.asyncio
async def test_inventory_refuses_dialect_change_before_import_commit(
    tmp_path: Path,
    ledger_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.services.quarantine.sqlite_insert", sqlite_insert)
    service = QuarantineService(
        StaticFSStorage(tmp_path),
        session_factory=_ChangingDialectProxyFactory(
            ledger_factory, ["sqlite", "mysql"]
        ),
        explicit_scope_id="dialect-change-test",
    )

    with pytest.raises(RuntimeError, match="require PostgreSQL or SQLite"):
        await service.ensure_inventory_complete()

    async with ledger_factory() as session:
        scope = await session.get(QuarantineStorageScope, service.scope_id)
    assert scope is None


@pytest.mark.asyncio
async def test_sweep_counts_only_the_worker_that_releases_the_reservation(
    tmp_path: Path,
    ledger_factory: async_sessionmaker[AsyncSession],
) -> None:
    class AlreadyReleasedStorage(StaticFSStorage):
        async def delete_quarantine_key(self, key: str) -> bool:
            async with ledger_factory() as session:
                async with session.begin():
                    row = await session.scalar(
                        select(QuarantineReservation).where(
                            QuarantineReservation.object_key == key
                        )
                    )
                    assert row is not None and row.status == "deleting"
                    await session.delete(row)
            await super().delete_quarantine_key(key)
            return True

    backend = AlreadyReleasedStorage(tmp_path)
    service = _service(backend, ledger_factory)
    await service.store("quarantine/already-released.bin", b"old")
    async with ledger_factory() as session:
        await session.execute(
            update(QuarantineReservation).values(
                expires_at=datetime.now(UTC) - timedelta(seconds=1)
            )
        )
        await session.commit()

    assert await service.sweep_once() == 0
    assert await _reservations(ledger_factory) == []
