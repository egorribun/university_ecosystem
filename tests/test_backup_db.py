from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from scripts import backup_db

CREATED_AT = datetime(2026, 9, 30, 12, 30, tzinfo=UTC)


class AsyncBody:
    def __init__(self, value: bytes) -> None:
        self._value = value
        self.closed = False

    async def read(self, size: int = -1) -> bytes:
        if size < 0:
            result, self._value = self._value, b""
            return result
        result, self._value = self._value[:size], self._value[size:]
        return result

    async def close(self) -> None:
        self.closed = True


class _RepeatedCancellationBody:
    def __init__(self, value: bytes) -> None:
        self._value = value
        self._read_count = 0
        self.second_read_started = asyncio.Event()
        self.close_started = asyncio.Event()

    async def read(self, size: int = -1) -> bytes:
        self._read_count += 1
        if self._read_count == 2:
            self.second_read_started.set()
            await asyncio.Event().wait()
        chunk_size = size if size >= 0 else len(self._value)
        if self._read_count == 1:
            chunk_size = max(1, min(chunk_size, len(self._value) // 2))
        result, self._value = self._value[:chunk_size], self._value[chunk_size:]
        return result

    async def close(self) -> None:
        self.close_started.set()
        await asyncio.Event().wait()


class FakeS3:
    def __init__(self, *, corrupt_reads_for: set[str] | None = None) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.corrupt_reads_for = corrupt_reads_for or set()
        self.get_calls: list[tuple[str, str]] = []

    async def upload_file(self, filename: str, bucket: str, key: str) -> None:
        self.objects[(bucket, key)] = Path(filename).read_bytes()

    async def put_object(self, *, Bucket: str, Key: str, Body: bytes, **_: Any) -> None:
        self.objects[(Bucket, Key)] = Body

    async def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        self.get_calls.append((Bucket, Key))
        value = self.objects[(Bucket, Key)]
        if Key in self.corrupt_reads_for:
            value = value + b"corrupt"
        return {"Body": AsyncBody(value), "ContentLength": len(value)}


def _archive(tmp_path: Path) -> Path:
    archive = tmp_path / "database.dump"
    archive.write_bytes(b"synthetic pg_dump archive")
    return archive


def _manifest(archive: Path) -> backup_db.BackupManifest:
    return backup_db.create_manifest(
        archive,
        source_database="university",
        source_revision=("202609250001",),
        artifact_key="daily/20260930T123000Z-00000000-0000-4000-8000-000000000001.dump",
        created_at=CREATED_AT,
    )


def test_manifest_is_versioned_and_round_trips_without_connection_details(
    tmp_path: Path,
) -> None:
    archive = _archive(tmp_path)
    manifest = _manifest(archive)

    payload = manifest.to_json_bytes()
    data = json.loads(payload)

    assert data["schema_version"] == 1
    assert data["source_database"] == "university"
    assert data["source_revision"] == ["202609250001"]
    assert data["created_at"] == "2026-09-30T12:30:00Z"
    assert data["format"] == "pg_dump.custom"
    assert data["size_bytes"] == archive.stat().st_size
    assert data["sha256"] == backup_db.sha256_file(archive)
    assert data["artifact_key"] == manifest.artifact_key
    assert "password" not in payload.decode().lower()
    assert (
        backup_db.parse_manifest(
            payload, expected_manifest_key=backup_db.manifest_key(manifest.artifact_key)
        )
        == manifest
    )


def test_manifest_rejects_unsupported_version_and_key_mismatch(
    tmp_path: Path,
) -> None:
    manifest = _manifest(_archive(tmp_path))
    data = json.loads(manifest.to_json_bytes())

    data["schema_version"] = 99
    with pytest.raises(backup_db.BackupArtifactError, match="schema version"):
        backup_db.parse_manifest(
            json.dumps(data).encode(),
            expected_manifest_key=backup_db.manifest_key(manifest.artifact_key),
        )

    data["schema_version"] = 1
    with pytest.raises(backup_db.BackupArtifactError, match="artifact key"):
        backup_db.parse_manifest(
            json.dumps(data).encode(),
            expected_manifest_key="other/object.manifest.json",
        )


@pytest.mark.asyncio
async def test_publish_reads_back_archive_before_publishing_manifest(
    tmp_path: Path,
) -> None:
    archive = _archive(tmp_path)
    manifest = _manifest(archive)
    store = FakeS3()

    published_manifest_key = await backup_db.publish_backup(
        store, "synthetic-backups", archive, manifest
    )

    assert published_manifest_key == backup_db.manifest_key(manifest.artifact_key)
    assert (
        store.objects[("synthetic-backups", manifest.artifact_key)]
        == archive.read_bytes()
    )
    assert (
        store.objects[("synthetic-backups", published_manifest_key)]
        == manifest.to_json_bytes()
    )
    assert store.get_calls == [
        ("synthetic-backups", manifest.artifact_key),
        ("synthetic-backups", published_manifest_key),
    ]


@pytest.mark.asyncio
async def test_publish_does_not_publish_manifest_when_remote_archive_is_corrupt(
    tmp_path: Path,
) -> None:
    archive = _archive(tmp_path)
    manifest = _manifest(archive)
    store = FakeS3(corrupt_reads_for={manifest.artifact_key})

    with pytest.raises(backup_db.BackupArtifactError, match="read-back verification"):
        await backup_db.publish_backup(store, "synthetic-backups", archive, manifest)

    assert (
        "synthetic-backups",
        backup_db.manifest_key(manifest.artifact_key),
    ) not in store.objects


@pytest.mark.asyncio
async def test_publish_bounds_remote_archive_readback_to_manifest_size(
    tmp_path: Path,
) -> None:
    archive = _archive(tmp_path)
    manifest = _manifest(archive)

    class CountingBody:
        def __init__(self, value: bytes) -> None:
            self.value = value
            self.bytes_read = 0
            self.closed = False

        async def read(self, size: int = -1) -> bytes:
            count = len(self.value) if size < 0 else size
            result, self.value = self.value[:count], self.value[count:]
            self.bytes_read += len(result)
            return result

        async def close(self) -> None:
            self.closed = True

    body = CountingBody(archive.read_bytes() + b"x" * 1_000_000)

    class OversizedReadbackClient:
        def __init__(self) -> None:
            self.put_calls = 0

        async def upload_file(self, filename: str, bucket: str, key: str) -> None:
            del filename, bucket, key

        async def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
            del Bucket, Key
            return {"Body": body}

        async def put_object(self, **_kwargs: Any) -> None:
            self.put_calls += 1

    client = OversizedReadbackClient()

    with pytest.raises(backup_db.BackupArtifactError, match="read-back verification"):
        await backup_db.publish_backup(client, "synthetic-backups", archive, manifest)

    assert body.bytes_read <= manifest.size_bytes + 1
    assert body.closed
    assert client.put_calls == 0


@pytest.mark.asyncio
async def test_download_verifies_manifest_and_archive_before_returning(
    tmp_path: Path,
) -> None:
    archive = _archive(tmp_path)
    manifest = _manifest(archive)
    store = FakeS3()
    await backup_db.publish_backup(store, "synthetic-backups", archive, manifest)
    destination = tmp_path / "verified.dump"

    loaded = await backup_db.download_verified_backup(
        store,
        "synthetic-backups",
        backup_db.manifest_key(manifest.artifact_key),
        destination,
    )

    assert loaded == manifest
    assert destination.read_bytes() == archive.read_bytes()


def test_restore_target_must_be_new_and_isolated_from_source() -> None:
    with pytest.raises(backup_db.BackupArtifactError, match="restore_"):
        backup_db.validate_restore_target("university", "university")

    with pytest.raises(backup_db.BackupArtifactError, match="different"):
        backup_db.validate_restore_target("restore_university", "restore_university")


@pytest.mark.parametrize(
    "target_database",
    [
        "restore_target;DROP_DATABASE_university",
        'restore_target";DROP_DATABASE_university',
    ],
)
def test_restore_rejects_injected_database_identifiers_before_side_effects(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    target_database: str,
) -> None:
    archive = _archive(tmp_path)
    manifest = _manifest(archive)
    command_calls: list[list[str]] = []

    def reject_connection(*_: Any, **__: Any) -> None:
        pytest.fail("unsafe restore target reached the database connection")

    def capture_command(command: list[str], **_: Any) -> Any:
        command_calls.append(command)
        return type("Completed", (), {"returncode": 0})()

    monkeypatch.setattr(backup_db.psycopg, "connect", reject_connection)

    with pytest.raises(backup_db.BackupArtifactError, match="restore_"):
        backup_db.restore_archive(
            archive,
            manifest,
            "postgresql://admin@localhost/postgres",
            target_database,
            command_runner=capture_command,
        )

    assert command_calls == []


def test_postgres_tool_credentials_are_environment_only(tmp_path: Path) -> None:
    archive = tmp_path / "dump"
    calls: list[dict[str, Any]] = []
    marker = "synthetic-marker"

    def run(command: list[str], **kwargs: Any) -> Any:
        calls.append({"command": command, **kwargs})
        archive.write_bytes(b"synthetic pg_dump archive")
        return type("Completed", (), {"returncode": 0})()

    database_url = (
        backup_db.make_url("postgresql://backup_user@127.0.0.1:5432/source")
        .set(password=marker)
        .render_as_string(hide_password=False)
    )
    backup_db.dump_database(
        database_url,
        archive,
        command_runner=run,
    )

    assert len(calls) == 1
    assert marker not in " ".join(calls[0]["command"])
    assert calls[0]["env"]["PGPASSWORD"] == marker
    assert calls[0]["stdout"] is backup_db.subprocess.DEVNULL
    assert calls[0]["stderr"] is backup_db.subprocess.DEVNULL


def test_restore_refuses_existing_database_before_running_restore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = _archive(tmp_path)
    manifest = _manifest(archive)
    commands: list[list[str]] = []

    class ExistingDatabase:
        def execute(self, statement: Any, params: Any = None) -> Any:
            if isinstance(statement, str) and "pg_database" in statement:
                return type("Result", (), {"fetchone": lambda self: (1,)})()
            raise AssertionError("an existing target must not be modified")

        def __enter__(self) -> ExistingDatabase:
            return self

        def __exit__(self, *_: Any) -> None:
            return None

    monkeypatch.setattr(
        backup_db.psycopg,
        "connect",
        lambda *_args, **_kwargs: ExistingDatabase(),
    )

    def run(command: list[str], **kwargs: Any) -> Any:
        commands.append(command)
        return type("Completed", (), {"returncode": 0})()

    marker = "synthetic-marker"
    admin_database_url = (
        backup_db.make_url("postgresql://restore_admin@127.0.0.1:5432/postgres")
        .set(password=marker)
        .render_as_string(hide_password=False)
    )
    with pytest.raises(backup_db.BackupArtifactError, match="already exists"):
        backup_db.restore_archive(
            archive,
            manifest,
            admin_database_url,
            "restore_university_20260930",
            command_runner=run,
        )

    assert len(commands) == 1
    assert commands[0][0] == "pg_restore"
    assert marker not in " ".join(commands[0])


@pytest.mark.asyncio
async def test_download_removes_corrupted_archive_before_returning(
    tmp_path: Path,
) -> None:
    archive = _archive(tmp_path)
    manifest = _manifest(archive)
    store = FakeS3()
    await backup_db.publish_backup(store, "synthetic-backups", archive, manifest)
    store.corrupt_reads_for.add(manifest.artifact_key)
    destination = tmp_path / "unverified.dump"

    with pytest.raises(backup_db.BackupArtifactError, match=r"length|checksum"):
        await backup_db.download_verified_backup(
            store,
            "synthetic-backups",
            backup_db.manifest_key(manifest.artifact_key),
            destination,
        )

    assert not destination.exists()


@pytest.mark.asyncio
async def test_repeated_cancellation_during_body_close_removes_partial_download(
    tmp_path: Path,
) -> None:
    source_archive = _archive(tmp_path)
    manifest = _manifest(source_archive)
    manifest_object_key = backup_db.manifest_key(manifest.artifact_key)
    body = _RepeatedCancellationBody(source_archive.read_bytes())

    class Client:
        async def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
            del Bucket
            if Key == manifest_object_key:
                payload = manifest.to_json_bytes()
                return {
                    "Body": AsyncBody(payload),
                    "ContentLength": len(payload),
                }
            return {
                "Body": body,
                "ContentLength": source_archive.stat().st_size,
            }

    destination = tmp_path / "partial-restore.dump"
    download = asyncio.create_task(
        backup_db.download_verified_backup(
            Client(), "synthetic-backups", manifest_object_key, destination
        )
    )
    await body.second_read_started.wait()
    download.cancel()
    await body.close_started.wait()
    download.cancel()

    with pytest.raises(asyncio.CancelledError):
        await download

    assert not destination.exists()


@pytest.mark.asyncio
async def test_partial_cleanup_failure_still_closes_remote_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_archive = _archive(tmp_path)
    manifest = _manifest(source_archive)
    manifest_object_key = backup_db.manifest_key(manifest.artifact_key)

    class BlockingBody:
        def __init__(self) -> None:
            self.read_count = 0
            self.second_read_started = asyncio.Event()
            self.closed = False

        async def read(self, size: int = -1) -> bytes:
            del size
            self.read_count += 1
            if self.read_count == 1:
                return b"partial"
            self.second_read_started.set()
            await asyncio.Event().wait()
            return b""

        async def close(self) -> None:
            self.closed = True

    body = BlockingBody()

    class Client:
        async def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
            del Bucket
            if Key == manifest_object_key:
                payload = manifest.to_json_bytes()
                return {
                    "Body": AsyncBody(payload),
                    "ContentLength": len(payload),
                }
            return {"Body": body, "ContentLength": source_archive.stat().st_size}

    destination = tmp_path / "partial-cleanup-failure.dump"
    original_unlink = Path.unlink

    def fail_destination_unlink(path: Path, *args: Any, **kwargs: Any) -> None:
        if path == destination:
            raise PermissionError("synthetic unlink failure")
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_destination_unlink)
    download = asyncio.create_task(
        backup_db.download_verified_backup(
            Client(), "synthetic-backups", manifest_object_key, destination
        )
    )
    await body.second_read_started.wait()
    download.cancel()

    with pytest.raises(PermissionError, match="synthetic unlink failure"):
        await download

    assert body.closed


def test_restore_creates_a_new_database_without_putting_password_in_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = _archive(tmp_path)
    manifest = _manifest(archive)
    statements: list[tuple[Any, Any]] = []
    commands: list[dict[str, Any]] = []
    marker = "synthetic-marker"

    class MissingDatabase:
        def execute(self, statement: Any, params: Any = None) -> Any:
            statements.append((statement, params))
            if isinstance(statement, str) and "pg_database" in statement:
                return type("Result", (), {"fetchone": lambda self: None})()
            return None

        def __enter__(self) -> MissingDatabase:
            return self

        def __exit__(self, *_: Any) -> None:
            return None

    monkeypatch.setattr(
        backup_db.psycopg,
        "connect",
        lambda *_args, **_kwargs: MissingDatabase(),
    )

    def run(command: list[str], **kwargs: Any) -> Any:
        commands.append({"command": command, **kwargs})
        return type("Completed", (), {"returncode": 0})()

    admin_database_url = (
        backup_db.make_url("postgresql://restore_admin@127.0.0.1:5432/postgres")
        .set(password=marker)
        .render_as_string(hide_password=False)
    )
    backup_db.restore_archive(
        archive,
        manifest,
        admin_database_url,
        "restore_university_20260930",
        command_runner=run,
    )

    assert len(statements) == 1
    assert len(commands) == 3
    assert commands[1]["command"] == [
        "createdb",
        "--no-password",
        "--maintenance-db",
        "postgres",
        "restore_university_20260930",
    ]
    assert commands[2]["command"][0] == "pg_restore"
    assert commands[1]["env"]["PGPASSWORD"] == marker
    assert all(
        marker not in " ".join(call["command"])
        and call["stderr"] is backup_db.subprocess.DEVNULL
        for call in commands
    )


def test_cli_does_not_echo_a_connection_url_passed_as_an_argument(
    capsys: pytest.CaptureFixture[str],
) -> None:
    marker = "synthetic-marker"
    connection_url = (
        backup_db.make_url("postgresql://user@localhost/db")
        .set(password=marker)
        .render_as_string(hide_password=False)
    )

    result = backup_db.main(["backup", "--database-url", connection_url])

    captured = capsys.readouterr()
    assert result == 2
    assert marker not in captured.out + captured.err


def test_restore_cli_rejects_raw_admin_database_url_without_access_or_echo(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = "synthetic-restore-admin-marker"
    admin_database_url = (
        backup_db.make_url("postgresql://restore_admin@127.0.0.1:5432/postgres")
        .set(password=marker)
        .render_as_string(hide_password=False)
    )

    def reject_access(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("invalid CLI arguments reached a database or S3 operation")

    monkeypatch.setattr(backup_db, "s3_settings_from_environment", reject_access)
    monkeypatch.setattr(backup_db.aioboto3, "Session", reject_access)
    monkeypatch.setattr(backup_db.psycopg, "connect", reject_access)

    result = backup_db.main(
        [
            "restore",
            "--manifest-key",
            "daily/backup.manifest.json",
            "--target-database",
            "restore_target",
            "--admin-database-url",
            admin_database_url,
        ]
    )

    captured = capsys.readouterr()
    assert result == 2
    assert marker not in captured.out + captured.err


def test_source_metadata_uses_static_read_only_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statements: list[Any] = []

    class Result:
        def __init__(self, rows: list[tuple[str]]) -> None:
            self.rows = rows

        def fetchone(self) -> tuple[str] | None:
            return self.rows[0] if self.rows else None

        def fetchall(self) -> list[tuple[str]]:
            return self.rows

    class Connection:
        def __init__(self) -> None:
            self.call_count = 0

        def __enter__(self) -> Connection:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def execute(self, statement: Any) -> Result:
            statements.append(statement)
            self.call_count += 1
            if self.call_count == 1:
                return Result([("synthetic_source",)])
            return Result([("synthetic_revision",)])

    monkeypatch.setattr(backup_db.psycopg, "connect", lambda _dsn: Connection())

    assert backup_db.source_database_metadata(
        "postgresql://synthetic_user@localhost/synthetic_source"
    ) == ("synthetic_source", ("synthetic_revision",))
    assert statements == [
        "SELECT current_database()",
        "SELECT version_num FROM alembic_version ORDER BY version_num",
    ]


def test_backup_requires_a_stable_alembic_revision_during_dump() -> None:
    before = ("university", ("202609250001",))
    after = ("university", ("202610010001",))

    with pytest.raises(backup_db.BackupArtifactError, match="changed during dump"):
        backup_db.verify_source_metadata_unchanged(before, after)


@pytest.mark.parametrize("endpoint", ["http://localhost:8333", "http://seaweedfs:8333"])
def test_s3_http_endpoint_is_rejected_by_default(
    endpoint: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BACKUP_S3_ENDPOINT_URL", endpoint)
    monkeypatch.setenv("BACKUP_S3_BUCKET", "synthetic-backups")
    monkeypatch.delenv("BACKUP_S3_ALLOW_HTTP_FOR_LOCAL_DEV", raising=False)

    with pytest.raises(backup_db.BackupArtifactError, match="HTTPS is required"):
        backup_db.s3_settings_from_environment()


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://127.0.0.1:8333",
        "http://[::1]:8333",
        "http://10.0.0.7:8333",
        "http://[fd00::7]:8333",
        "http://localhost:8333",
        "http://minio:9000",
        "http://seaweedfs:9000",
    ],
)
def test_s3_http_local_endpoint_requires_opt_in(
    endpoint: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BACKUP_S3_ENDPOINT_URL", endpoint)
    monkeypatch.setenv("BACKUP_S3_BUCKET", "synthetic-backups")
    monkeypatch.setenv("BACKUP_S3_ALLOW_HTTP_FOR_LOCAL_DEV", "true")

    settings = backup_db.s3_settings_from_environment()

    assert settings.endpoint_url == endpoint


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://8.8.8.8:9000",
        "http://[2606:4700:4700::1111]:9000",
        "http://169.254.169.254:80",
        "http://s3.example.invalid:9000",
    ],
)
def test_s3_http_opt_in_rejects_public_hosts(
    endpoint: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BACKUP_S3_ENDPOINT_URL", endpoint)
    monkeypatch.setenv("BACKUP_S3_BUCKET", "synthetic-backups")
    monkeypatch.setenv("BACKUP_S3_ALLOW_HTTP_FOR_LOCAL_DEV", "true")

    with pytest.raises(
        backup_db.BackupArtifactError, match="approved local Docker hosts"
    ):
        backup_db.s3_settings_from_environment()


def test_https_s3_endpoint_needs_no_transport_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint = "https://s3.example.invalid"
    monkeypatch.setenv("BACKUP_S3_ENDPOINT_URL", endpoint)
    monkeypatch.setenv("BACKUP_S3_BUCKET", "synthetic-backups")
    monkeypatch.delenv("BACKUP_S3_ALLOW_HTTP_FOR_LOCAL_DEV", raising=False)

    settings = backup_db.s3_settings_from_environment()

    assert settings.endpoint_url == endpoint
