from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import replace
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
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects
        self.get_calls: list[str] = []

    async def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        del Bucket
        self.get_calls.append(Key)
        content = self.objects[Key]
        return {"Body": FakeBody(content), "ContentLength": len(content)}


def _settings() -> backup_db.S3Settings:
    return backup_db.S3Settings(
        endpoint_url="https://s3.example.test",
        bucket="synthetic-backups",
        prefix="synthetic",
        region="test-region",
    )


def _manifest(archive: Path) -> backup_db.BackupManifest:
    return backup_db.create_manifest(
        archive,
        source_database="synthetic_source",
        source_revision=("synthetic_revision",),
        artifact_key="synthetic/backup.dump",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


@pytest.mark.parametrize("target_database", ["", "unsafe-target"])
@pytest.mark.asyncio
async def test_restore_rejects_missing_or_unsafe_target_before_s3_or_database(
    monkeypatch: pytest.MonkeyPatch, target_database: str
) -> None:
    s3_calls: list[bool] = []
    database_calls: list[bool] = []

    @asynccontextmanager
    async def forbidden_s3_client(_settings: backup_db.S3Settings):
        s3_calls.append(True)
        pytest.fail("invalid restore target reached S3 client creation")
        yield None

    def forbidden_database_connect(*_args: Any, **_kwargs: Any) -> None:
        database_calls.append(True)
        pytest.fail("invalid restore target reached the database")

    monkeypatch.setattr(backup_db, "s3_client", forbidden_s3_client)
    monkeypatch.setattr(backup_db.psycopg, "connect", forbidden_database_connect)

    with pytest.raises(backup_db.BackupArtifactError):
        await backup_db.restore_from_s3(
            "synthetic/backup.manifest.json",
            target_database,
            "postgresql://localhost/synthetic_target",
            _settings(),
        )

    assert s3_calls == []
    assert database_calls == []


@pytest.mark.asyncio
async def test_restore_rejects_non_manifest_key_before_s3_or_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    s3_calls: list[bool] = []
    database_calls: list[bool] = []

    @asynccontextmanager
    async def forbidden_s3_client(_settings: backup_db.S3Settings):
        s3_calls.append(True)
        pytest.fail("invalid manifest key reached S3 client creation")
        yield None

    def forbidden_database_connect(*_args: Any, **_kwargs: Any) -> None:
        database_calls.append(True)
        pytest.fail("invalid manifest key reached the database")

    monkeypatch.setattr(backup_db, "s3_client", forbidden_s3_client)
    monkeypatch.setattr(backup_db.psycopg, "connect", forbidden_database_connect)

    with pytest.raises(backup_db.BackupArtifactError):
        await backup_db.restore_from_s3(
            "synthetic/backup.dump",
            "restore_sandbox",
            "postgresql://localhost/synthetic_target",
            _settings(),
        )

    assert s3_calls == []
    assert database_calls == []


def test_restore_archive_rejects_checksum_mismatch_before_pg_or_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "synthetic.dump"
    original_content = b"synthetic archive payload"
    archive.write_bytes(original_content)
    manifest = _manifest(archive)
    archive.write_bytes(original_content[:-1] + b"!")
    database_calls: list[bool] = []
    pg_tool_calls: list[list[str]] = []

    def forbidden_database_connect(*_args: Any, **_kwargs: Any) -> None:
        database_calls.append(True)
        pytest.fail("unverified archive reached the database")

    def forbidden_pg_tool(command: list[str], **_kwargs: Any) -> None:
        pg_tool_calls.append(command)
        pytest.fail("unverified archive reached a PostgreSQL tool")

    monkeypatch.setattr(backup_db.psycopg, "connect", forbidden_database_connect)

    with pytest.raises(backup_db.BackupArtifactError, match="manifest"):
        backup_db.restore_archive(
            archive,
            manifest,
            "postgresql://localhost/synthetic_target",
            "restore_sandbox",
            command_runner=forbidden_pg_tool,
        )

    assert database_calls == []
    assert pg_tool_calls == []


def test_restore_archive_rejects_malformed_manifest_before_pg_or_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "synthetic.dump"
    archive.write_bytes(b"synthetic archive payload")
    manifest = replace(_manifest(archive), sha256="synthetic-invalid-digest")
    database_calls: list[bool] = []
    pg_tool_calls: list[list[str]] = []

    def forbidden_database_connect(*_args: Any, **_kwargs: Any) -> None:
        database_calls.append(True)
        pytest.fail("invalid manifest reached the database")

    def forbidden_pg_tool(command: list[str], **_kwargs: Any) -> None:
        pg_tool_calls.append(command)
        pytest.fail("invalid manifest reached a PostgreSQL tool")

    monkeypatch.setattr(backup_db.psycopg, "connect", forbidden_database_connect)

    with pytest.raises(backup_db.BackupArtifactError, match="checksum"):
        backup_db.restore_archive(
            archive,
            manifest,
            "postgresql://localhost/synthetic_target",
            "restore_sandbox",
            command_runner=forbidden_pg_tool,
        )

    assert database_calls == []
    assert pg_tool_calls == []


@pytest.mark.asyncio
async def test_invalid_remote_manifest_stops_before_artifact_fetch_or_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_key = "synthetic/invalid.manifest.json"
    client = FakeS3({manifest_key: b"{}"})
    restore_calls: list[bool] = []
    database_calls: list[bool] = []

    @asynccontextmanager
    async def fake_s3_client(_settings: backup_db.S3Settings):
        yield client

    def forbidden_restore(*_args: Any, **_kwargs: Any) -> None:
        restore_calls.append(True)
        pytest.fail("invalid remote manifest reached restore")

    def forbidden_database_connect(*_args: Any, **_kwargs: Any) -> None:
        database_calls.append(True)
        pytest.fail("invalid remote manifest reached the database")

    monkeypatch.setattr(backup_db, "s3_client", fake_s3_client)
    monkeypatch.setattr(backup_db, "restore_archive", forbidden_restore)
    monkeypatch.setattr(backup_db.psycopg, "connect", forbidden_database_connect)

    with pytest.raises(backup_db.BackupArtifactError):
        await backup_db.restore_from_s3(
            manifest_key,
            "restore_sandbox",
            "postgresql://localhost/synthetic_target",
            _settings(),
        )

    assert client.get_calls == [manifest_key]
    assert restore_calls == []
    assert database_calls == []


@pytest.mark.asyncio
async def test_target_matching_manifest_source_stops_before_artifact_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "synthetic.dump"
    archive.write_bytes(b"synthetic archive payload")
    manifest = backup_db.create_manifest(
        archive,
        source_database="restore_sandbox",
        source_revision=("synthetic_revision",),
        artifact_key="synthetic/backup.dump",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    manifest_key = backup_db.manifest_key(manifest.artifact_key)
    client = FakeS3(
        {
            manifest_key: manifest.to_json_bytes(),
            manifest.artifact_key: archive.read_bytes(),
        }
    )
    restore_calls: list[bool] = []

    @asynccontextmanager
    async def fake_s3_client(_settings: backup_db.S3Settings):
        yield client

    def forbidden_restore(*_args: Any, **_kwargs: Any) -> None:
        restore_calls.append(True)
        pytest.fail("restore target equal to source reached archive restore")

    monkeypatch.setattr(backup_db, "s3_client", fake_s3_client)
    monkeypatch.setattr(backup_db, "restore_archive", forbidden_restore)

    with pytest.raises(backup_db.BackupArtifactError, match="different"):
        await backup_db.restore_from_s3(
            manifest_key,
            "restore_sandbox",
            "postgresql://localhost/synthetic_target",
            _settings(),
        )

    assert client.get_calls == [manifest_key]
    assert restore_calls == []


@pytest.mark.asyncio
async def test_remote_checksum_mismatch_stops_before_restore_or_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "synthetic.dump"
    original_content = b"synthetic archive payload"
    archive.write_bytes(original_content)
    manifest = _manifest(archive)
    manifest_key = backup_db.manifest_key(manifest.artifact_key)
    client = FakeS3(
        {
            manifest_key: manifest.to_json_bytes(),
            manifest.artifact_key: original_content[:-1] + b"!",
        }
    )
    restore_calls: list[bool] = []
    database_calls: list[bool] = []

    @asynccontextmanager
    async def fake_s3_client(_settings: backup_db.S3Settings):
        yield client

    def forbidden_restore(*_args: Any, **_kwargs: Any) -> None:
        restore_calls.append(True)
        pytest.fail("checksum-mismatched archive reached restore")

    def forbidden_database_connect(*_args: Any, **_kwargs: Any) -> None:
        database_calls.append(True)
        pytest.fail("checksum-mismatched archive reached the database")

    monkeypatch.setattr(backup_db, "s3_client", fake_s3_client)
    monkeypatch.setattr(backup_db, "restore_archive", forbidden_restore)
    monkeypatch.setattr(backup_db.psycopg, "connect", forbidden_database_connect)

    with pytest.raises(backup_db.BackupArtifactError, match="checksum"):
        await backup_db.restore_from_s3(
            manifest_key,
            "restore_sandbox",
            "postgresql://localhost/synthetic_target",
            _settings(),
        )

    assert client.get_calls == [manifest_key, manifest.artifact_key]
    assert restore_calls == []
    assert database_calls == []


@pytest.mark.asyncio
async def test_remote_length_mismatch_is_rejected_before_streaming_artifact(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "synthetic.dump"
    archive.write_bytes(b"synthetic archive payload")
    manifest = _manifest(archive)
    manifest_key = backup_db.manifest_key(manifest.artifact_key)

    class CountingBody(FakeBody):
        def __init__(self, content: bytes) -> None:
            super().__init__(content)
            self.bytes_read = 0
            self.closed = False

        async def read(self, size: int = -1) -> bytes:
            result = await super().read(size)
            self.bytes_read += len(result)
            return result

        async def close(self) -> None:
            self.closed = True

    body = CountingBody(b"corrupted" * 10_000)

    class Client:
        async def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
            del Bucket
            if Key == manifest_key:
                payload = manifest.to_json_bytes()
                return {"Body": FakeBody(payload), "ContentLength": len(payload)}
            return {"Body": body, "ContentLength": len(b"corrupted" * 10_000)}

    destination = tmp_path / "unverified.dump"
    with pytest.raises(backup_db.BackupArtifactError, match="length"):
        await backup_db.download_verified_backup(
            Client(), "synthetic-backups", manifest_key, destination
        )

    assert body.bytes_read == 0
    assert body.closed
    assert not destination.exists()


@pytest.mark.asyncio
async def test_remote_length_mismatch_without_content_length_is_bounded(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "synthetic.dump"
    archive.write_bytes(b"synthetic archive payload")
    manifest = _manifest(archive)
    manifest_key = backup_db.manifest_key(manifest.artifact_key)

    class CountingBody(FakeBody):
        def __init__(self, content: bytes) -> None:
            super().__init__(content)
            self.bytes_read = 0
            self.closed = False

        async def read(self, size: int = -1) -> bytes:
            result = await super().read(size)
            self.bytes_read += len(result)
            return result

        async def close(self) -> None:
            self.closed = True

    body = CountingBody(b"corrupted" * 10_000)

    class Client:
        async def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
            del Bucket
            if Key == manifest_key:
                payload = manifest.to_json_bytes()
                return {"Body": FakeBody(payload), "ContentLength": len(payload)}
            return {"Body": body}

    destination = tmp_path / "unverified.dump"
    with pytest.raises(backup_db.BackupArtifactError, match="length"):
        await backup_db.download_verified_backup(
            Client(), "synthetic-backups", manifest_key, destination
        )

    assert body.bytes_read <= manifest.size_bytes + 1
    assert body.closed
    assert not destination.exists()
