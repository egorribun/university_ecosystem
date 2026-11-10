"""Filesystem inventory must retain quota and retention coverage during cleanup."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import threading
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.quarantine import QuarantineReservation, QuarantineStorageScope
from app.services.quarantine import (
    QuarantineInventoryIncomplete,
    QuarantineQuotaExceeded,
    QuarantineService,
)
from app.services.storage import StaticFSStorage


def _cursor(payload: object) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")


def _seed_legacy_files(root: Path) -> None:
    root.mkdir()
    expired = (datetime.now(UTC) - timedelta(days=3)).timestamp()
    for index in range(201):
        file = root / f"{index:03}.bin"
        file.write_bytes(b"x")
        timestamp = expired - 100 if index == 0 else expired
        os.utime(file, (timestamp, timestamp))


@pytest.fixture
async def ledger_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(QuarantineStorageScope.__table__.create)
        await connection.run_sync(QuarantineReservation.__table__.create)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


async def _finish_inventory(service: QuarantineService) -> None:
    for _ in range(4):
        if await service.ensure_inventory_complete():
            return
    pytest.fail("201-file inventory did not finish within four bounded calls")


async def _ledger(
    factory: async_sessionmaker[AsyncSession], service: QuarantineService
) -> tuple[QuarantineStorageScope, list[QuarantineReservation]]:
    async with factory() as session:
        scope = await session.get(QuarantineStorageScope, service.scope_id)
        rows = list((await session.scalars(select(QuarantineReservation))).all())
    assert scope is not None
    return scope, rows


@pytest.mark.parametrize("cleanup_during_bootstrap", [True, False])
async def test_cleanup_keeps_all_surviving_files_charged_and_expirable(
    tmp_path: Path,
    ledger_factory: async_sessionmaker[AsyncSession],
    cleanup_during_bootstrap: bool,
) -> None:
    root = tmp_path / "quarantine"
    _seed_legacy_files(root)
    service = QuarantineService(
        StaticFSStorage(tmp_path),
        session_factory=ledger_factory,
        quota_bytes=200,
        retention_days=1,
        inventory_page_size=1,
    )
    if not cleanup_during_bootstrap:
        await _finish_inventory(service)

    assert await service.sweep_once(limit=1) == 1
    assert not (root / "000.bin").exists()
    if cleanup_during_bootstrap:
        scope, rows = await _ledger(ledger_factory, service)
        assert scope.inventory_complete is False
        assert len(rows) == 99

    await _finish_inventory(service)
    scope, rows = await _ledger(ledger_factory, service)
    assert scope.inventory_complete is True
    assert scope.inventory_cursor is None
    assert {row.object_key for row in rows} == {
        f"quarantine/{index:03}.bin" for index in range(1, 201)
    }
    assert sum(row.size_bytes for row in rows) == 200
    assert sum(file.stat().st_size for file in root.iterdir()) == 200
    with pytest.raises(QuarantineQuotaExceeded):
        await service.store("quarantine/new.bin", b"n")
    assert not (root / "new.bin").exists()

    assert await service.sweep_once(limit=1000) == 200
    assert await service.sweep_once(limit=1000) == 0
    assert list(root.iterdir()) == []


@pytest.mark.parametrize("nested", [False, True])
async def test_cursor_survives_prior_deletion_and_discovers_later_insertion(
    tmp_path: Path, nested: bool
) -> None:
    relative = "quarantine/nested" if nested else "quarantine"
    directory = tmp_path / relative
    directory.mkdir(parents=True)
    for name in ("a.bin", "b.bin", "c.bin"):
        (directory / name).write_bytes(b"x")
    storage = StaticFSStorage(tmp_path)
    first = await storage.list_quarantine_page(None, limit=1)
    assert [item.key for item in first.objects] == [f"{relative}/a.bin"]
    assert first.next_cursor is not None

    assert await storage.delete_quarantine_key(f"{relative}/a.bin")
    await storage.save_file(f"{relative}/bb.bin", b"new")
    cursor = first.next_cursor
    seen: list[str] = []
    while cursor is not None:
        page = await storage.list_quarantine_page(cursor, limit=1)
        assert len(page.objects) <= 1
        seen.extend(item.key for item in page.objects)
        cursor = page.next_cursor

    assert seen == [f"{relative}/{name}" for name in ("b.bin", "bb.bin", "c.bin")]


@pytest.mark.parametrize("nested", [False, True])
async def test_legacy_positional_cursor_restarts_after_prior_deletion(
    tmp_path: Path, nested: bool
) -> None:
    relative = "quarantine/nested" if nested else "quarantine"
    directory = tmp_path / relative
    directory.mkdir(parents=True)
    for name in ("a.bin", "b.bin", "c.bin"):
        (directory / name).write_bytes(b"x")
    frames = [["quarantine", 1], [relative, 1]] if nested else [[relative, 1]]
    legacy = _cursor({"version": 1, "stack": frames})
    storage = StaticFSStorage(tmp_path)
    assert await storage.delete_quarantine_key(f"{relative}/a.bin")

    page = await storage.list_quarantine_page(legacy, limit=10)

    assert [item.key for item in page.objects] == [
        f"{relative}/b.bin",
        f"{relative}/c.bin",
    ]
    assert page.next_cursor is None


async def test_inflight_page_handles_prior_deletion_and_later_insertion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "quarantine"
    directory.mkdir()
    for name in ("a.bin", "b.bin", "c.bin"):
        (directory / name).write_bytes(b"x")
    storage = StaticFSStorage(tmp_path)
    first = await storage.list_quarantine_page(None, limit=1)
    assert first.next_cursor is not None
    captured = threading.Event()
    resume = threading.Event()
    read_directory = storage._read_quarantine_directory

    def paused_directory_read(path: Path) -> list[tuple[str, str]]:
        entries = read_directory(path)
        if not captured.is_set():
            captured.set()
            if not resume.wait(timeout=5):
                raise TimeoutError("synthetic directory read was not resumed")
        return entries

    # Pause after a real directory snapshot, rather than inventing its entries.
    monkeypatch.setattr(storage, "_read_quarantine_directory", paused_directory_read)
    pending = asyncio.create_task(
        storage.list_quarantine_page(first.next_cursor, limit=1)
    )
    try:
        assert await asyncio.to_thread(captured.wait, 5)
        assert await storage.delete_quarantine_key("quarantine/a.bin")
        await storage.save_file("quarantine/bb.bin", b"new")
    finally:
        resume.set()
        second = await asyncio.wait_for(pending, timeout=5)

    assert [item.key for item in second.objects] == ["quarantine/b.bin"]
    assert second.next_cursor is not None
    remaining = await storage.list_quarantine_page(second.next_cursor, limit=10)
    assert [item.key for item in remaining.objects] == [
        "quarantine/bb.bin",
        "quarantine/c.bin",
    ]
    assert remaining.next_cursor is None


async def test_legacy_restart_preserves_existing_ledger_charges_and_status(
    tmp_path: Path, ledger_factory: async_sessionmaker[AsyncSession]
) -> None:
    _seed_legacy_files(tmp_path / "quarantine")
    service = QuarantineService(
        StaticFSStorage(tmp_path),
        session_factory=ledger_factory,
        inventory_page_size=1,
    )
    assert await service.ensure_inventory_complete() is False
    async with ledger_factory() as session:
        scope = await session.get(QuarantineStorageScope, service.scope_id)
        assert scope is not None
        scope.inventory_cursor = _cursor({"version": 1, "stack": [["quarantine", 100]]})
        row = await session.scalar(
            select(QuarantineReservation).where(
                QuarantineReservation.object_key == "quarantine/000.bin"
            )
        )
        assert row is not None
        row.status = "deleting"
        original = (row.id, row.created_at, row.expires_at)
        await session.commit()

    await _finish_inventory(service)

    scope, rows = await _ledger(ledger_factory, service)
    assert scope.inventory_complete is True
    assert len(rows) == 201
    assert sum(row.size_bytes for row in rows) == 201
    retained = next(row for row in rows if row.object_key == "quarantine/000.bin")
    assert (retained.id, retained.created_at, retained.expires_at) == original
    assert retained.status == "deleting"


@pytest.mark.parametrize("name", ["000-new.bin", "zzz-new.bin"])
async def test_managed_inserts_wait_for_inventory_and_are_charged(
    tmp_path: Path,
    ledger_factory: async_sessionmaker[AsyncSession],
    name: str,
) -> None:
    root = tmp_path / "quarantine"
    _seed_legacy_files(root)
    service = QuarantineService(
        StaticFSStorage(tmp_path),
        session_factory=ledger_factory,
        quota_bytes=202,
        inventory_page_size=1,
    )
    assert await service.ensure_inventory_complete() is False
    with pytest.raises(QuarantineInventoryIncomplete):
        await service.store(f"quarantine/{name}", b"n")
    assert not (root / name).exists()
    scope, _ = await _ledger(ledger_factory, service)
    assert scope.inventory_complete is False

    await service.store(f"quarantine/{name}", b"n")

    scope, rows = await _ledger(ledger_factory, service)
    assert scope.inventory_complete is True
    assert len(rows) == 202
    assert sum(row.size_bytes for row in rows) == 202
    assert sum(file.stat().st_size for file in root.iterdir()) == 202
    inserted = next(row for row in rows if row.object_key == f"quarantine/{name}")
    assert inserted.status == "stored"
    assert inserted.size_bytes == 1
    with pytest.raises(QuarantineQuotaExceeded):
        await service.store("quarantine/extra.bin", b"x")
    assert not (root / "extra.bin").exists()


@pytest.mark.parametrize("last_name", [1, True, "", "..", "/a", "a/b", "a\\b", "a\nb"])
async def test_keyset_cursor_rejects_invalid_entry_markers(
    tmp_path: Path, last_name: object
) -> None:
    encoded = _cursor({"version": 2, "stack": [["quarantine", last_name]]})
    with pytest.raises(ValueError):
        await StaticFSStorage(tmp_path).list_quarantine_page(encoded, limit=10)


async def test_keyset_cursor_can_resume_before_first_entry(tmp_path: Path) -> None:
    directory = tmp_path / "quarantine"
    directory.mkdir()
    (directory / "first.bin").write_bytes(b"x")
    encoded = _cursor({"version": 2, "stack": [["quarantine", None]]})

    page = await StaticFSStorage(tmp_path).list_quarantine_page(encoded, limit=10)

    assert [item.key for item in page.objects] == ["quarantine/first.bin"]
    assert page.next_cursor is None


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"version": 3, "stack": []},
        {"version": True, "stack": []},
        {"version": 2, "stack": "not-frames"},
        {"version": 2, "stack": ["not-a-frame"]},
        {"version": 2, "stack": [["quarantine"]]},
        {"version": 2, "stack": [[7, None]]},
    ],
)
async def test_cursor_rejects_unknown_versions_and_malformed_frames(
    tmp_path: Path, payload: object
) -> None:
    with pytest.raises(ValueError, match="Invalid quarantine inventory cursor"):
        await StaticFSStorage(tmp_path).list_quarantine_page(_cursor(payload), limit=10)


@pytest.mark.parametrize("nested", [False, True])
async def test_cursor_resumes_after_filename_with_leading_space(
    tmp_path: Path, nested: bool
) -> None:
    relative = "quarantine/nested" if nested else "quarantine"
    directory = tmp_path / relative
    directory.mkdir(parents=True)
    for name in (" a.bin", "b.bin"):
        (directory / name).write_bytes(b"x")
    storage = StaticFSStorage(tmp_path)

    first = await storage.list_quarantine_page(None, limit=1)
    assert [item.key for item in first.objects] == [f"{relative}/ a.bin"]
    assert first.next_cursor is not None
    second = await storage.list_quarantine_page(first.next_cursor, limit=10)

    assert [item.key for item in second.objects] == [f"{relative}/b.bin"]
    assert second.next_cursor is None
