from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from scripts import backup_db


class FakeBody:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    async def read(self, size: int = -1) -> bytes:
        if size < 0:
            payload, self.payload = self.payload, b""
            return payload
        payload, self.payload = self.payload[:size], self.payload[size:]
        return payload

    async def close(self) -> None:
        return None


class RecordingS3:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects
        self.get_calls: list[str] = []

    async def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        del Bucket
        self.get_calls.append(Key)
        payload = self.objects[Key]
        return {"Body": FakeBody(payload), "ContentLength": len(payload)}


@pytest.mark.asyncio
async def test_admin_connection_to_restore_target_is_rejected_before_s3_reads(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "synthetic.dump"
    archive.write_bytes(b"synthetic PostgreSQL archive")
    manifest = backup_db.create_manifest(
        archive,
        source_database="synthetic_source",
        source_revision=("synthetic_revision",),
        artifact_key="synthetic/backup.dump",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    manifest_key = backup_db.manifest_key(manifest.artifact_key)
    client = RecordingS3(
        {
            manifest_key: manifest.to_json_bytes(),
            manifest.artifact_key: archive.read_bytes(),
        }
    )

    @asynccontextmanager
    async def fake_s3_client(_settings: backup_db.S3Settings):
        yield client

    real_restore_archive = backup_db.restore_archive

    def restore_with_fake_pg_restore(*args: Any) -> None:
        real_restore_archive(
            *args,
            command_runner=lambda *_args, **_kwargs: SimpleNamespace(returncode=0),
        )

    monkeypatch.setattr(backup_db, "s3_client", fake_s3_client)
    monkeypatch.setattr(backup_db, "restore_archive", restore_with_fake_pg_restore)
    monkeypatch.setattr(
        backup_db.psycopg,
        "connect",
        lambda *_args, **_kwargs: pytest.fail("unsafe target reached PostgreSQL"),
    )

    target_database = "restore_synthetic_target"
    with pytest.raises(
        backup_db.BackupArtifactError,
        match="Admin connection must not point at the restore target",
    ):
        await backup_db.restore_from_s3(
            manifest_key,
            target_database,
            f"postgresql://restore_admin@localhost/{target_database}",
            backup_db.S3Settings(
                endpoint_url="https://s3.example.test",
                bucket="synthetic-backups",
                prefix="synthetic",
                region="test-region",
            ),
        )

    assert client.get_calls == []
