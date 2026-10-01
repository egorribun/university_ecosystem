from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from scripts import backup_db


class FakeBody:
    def __init__(self, content: bytes) -> None:
        self.content = content

    async def read(self, size: int = -1) -> bytes:
        if size < 0:
            content, self.content = self.content, b""
            return content
        content, self.content = self.content[:size], self.content[size:]
        return content

    async def close(self) -> None:
        return None


class FakeS3:
    def __init__(self, *, failure: str) -> None:
        self.failure = failure
        self.objects: dict[tuple[str, str], bytes] = {}
        self.events: list[tuple[str, str]] = []
        self.manifest_put_started = asyncio.Event()
        self.manifest_readback_started = asyncio.Event()
        self.manifest_delete_started = asyncio.Event()
        self.release_manifest_delete = asyncio.Event()

    async def upload_file(self, filename: str, bucket: str, key: str) -> None:
        self.events.append(("upload", key))
        self.objects[(bucket, key)] = Path(filename).read_bytes()

    async def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        self.events.append(("get", Key))
        if self.failure in {
            "manifest_readback_cancel",
            "manifest_delete_block",
        } and Key.endswith(backup_db.MANIFEST_SUFFIX):
            self.manifest_readback_started.set()
            await asyncio.Event().wait()
        content = self.objects[(Bucket, Key)]
        if self.failure == "manifest_readback" and Key.endswith(
            backup_db.MANIFEST_SUFFIX
        ):
            content += b"corrupt"
        return {"Body": FakeBody(content), "ContentLength": len(content)}

    async def put_object(
        self, *, Bucket: str, Key: str, Body: bytes, ContentType: str
    ) -> None:
        del ContentType
        self.events.append(("put", Key))
        self.objects[(Bucket, Key)] = Body
        if self.failure == "manifest_put_cancel_after_write":
            self.manifest_put_started.set()
            await asyncio.Event().wait()
        if self.failure in {
            "manifest_put_after_write",
            "manifest_put_after_write_cancel_cleanup",
        }:
            raise OSError("synthetic uncertain write outcome")

    async def delete_object(self, *, Bucket: str, Key: str) -> dict[str, str]:
        self.events.append(("delete", Key))
        if self.failure in {
            "manifest_delete_block",
            "manifest_put_after_write_cancel_cleanup",
        }:
            self.manifest_delete_started.set()
            await self.release_manifest_delete.wait()
        self.objects.pop((Bucket, Key), None)
        return {}


@pytest.mark.parametrize("failure", ["manifest_put_after_write", "manifest_readback"])
@pytest.mark.asyncio
async def test_failed_manifest_publication_removes_completion_marker(
    tmp_path: Path, failure: str
) -> None:
    archive = tmp_path / "synthetic.dump"
    archive.write_bytes(b"synthetic archive payload")
    manifest = backup_db.create_manifest(
        archive,
        source_database="synthetic_source",
        source_revision=("synthetic_revision",),
        artifact_key="synthetic/backup.dump",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    store = FakeS3(failure=failure)
    manifest_object_key = backup_db.manifest_key(manifest.artifact_key)

    with pytest.raises(backup_db.BackupArtifactError):
        await backup_db.publish_backup(store, "synthetic-backups", archive, manifest)

    assert ("synthetic-backups", manifest.artifact_key) in store.objects
    assert ("synthetic-backups", manifest_object_key) not in store.objects
    assert store.events[:3] == [
        ("upload", manifest.artifact_key),
        ("get", manifest.artifact_key),
        ("put", manifest_object_key),
    ]
    assert store.events[-1] == ("delete", manifest_object_key)


@pytest.mark.asyncio
async def test_cancelled_manifest_publication_removes_completion_marker(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "synthetic.dump"
    archive.write_bytes(b"synthetic archive payload")
    manifest = backup_db.create_manifest(
        archive,
        source_database="synthetic_source",
        source_revision=("synthetic_revision",),
        artifact_key="synthetic/backup.dump",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    store = FakeS3(failure="manifest_put_cancel_after_write")
    manifest_object_key = backup_db.manifest_key(manifest.artifact_key)
    publication = asyncio.create_task(
        backup_db.publish_backup(store, "synthetic-backups", archive, manifest)
    )
    await store.manifest_put_started.wait()

    publication.cancel()
    with pytest.raises(asyncio.CancelledError):
        await publication

    assert ("synthetic-backups", manifest.artifact_key) in store.objects
    assert ("synthetic-backups", manifest_object_key) not in store.objects
    assert store.events[-1] == ("delete", manifest_object_key)


@pytest.mark.asyncio
async def test_cancelled_manifest_verification_removes_completion_marker(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "synthetic.dump"
    archive.write_bytes(b"synthetic archive payload")
    manifest = backup_db.create_manifest(
        archive,
        source_database="synthetic_source",
        source_revision=("synthetic_revision",),
        artifact_key="synthetic/backup.dump",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    store = FakeS3(failure="manifest_readback_cancel")
    manifest_object_key = backup_db.manifest_key(manifest.artifact_key)
    publication = asyncio.create_task(
        backup_db.publish_backup(store, "synthetic-backups", archive, manifest)
    )
    await store.manifest_readback_started.wait()

    publication.cancel()
    with pytest.raises(asyncio.CancelledError):
        await publication

    assert ("synthetic-backups", manifest.artifact_key) in store.objects
    assert ("synthetic-backups", manifest_object_key) not in store.objects
    assert store.events[-1] == ("delete", manifest_object_key)


@pytest.mark.asyncio
async def test_cancellation_during_failed_manifest_cleanup_still_removes_marker(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "synthetic.dump"
    archive.write_bytes(b"synthetic archive payload")
    manifest = backup_db.create_manifest(
        archive,
        source_database="synthetic_source",
        source_revision=("synthetic_revision",),
        artifact_key="synthetic/backup.dump",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    store = FakeS3(failure="manifest_put_after_write_cancel_cleanup")
    manifest_object_key = backup_db.manifest_key(manifest.artifact_key)
    publication = asyncio.create_task(
        backup_db.publish_backup(store, "synthetic-backups", archive, manifest)
    )
    await store.manifest_delete_started.wait()

    publication.cancel()
    store.release_manifest_delete.set()

    with pytest.raises(asyncio.CancelledError):
        await publication

    assert ("synthetic-backups", manifest_object_key) not in store.objects


@pytest.mark.asyncio
async def test_repeated_cancellation_does_not_interrupt_manifest_cleanup() -> None:
    store = FakeS3(failure="manifest_delete_block")
    manifest_object_key = "synthetic/backup.dump.manifest.json"
    store.objects[("synthetic-backups", manifest_object_key)] = b"unverified"
    cleanup = asyncio.create_task(
        backup_db._finish_manifest_cleanup_after_cancellation(
            store, "synthetic-backups", manifest_object_key
        )
    )
    await store.manifest_delete_started.wait()

    cleanup.cancel()
    await asyncio.sleep(0)
    cleanup.cancel()
    store.release_manifest_delete.set()

    await cleanup

    assert ("synthetic-backups", manifest_object_key) not in store.objects
