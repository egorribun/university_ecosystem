from __future__ import annotations

import hashlib
import json
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
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
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.etags: dict[tuple[str, str], str] = {}
        self.version_ids: dict[tuple[str, str], str] = {}
        self.headers: dict[tuple[str, str], dict[str, Any]] = {}
        self.events: list[tuple[str, str, str]] = []
        self.hidden_versions: dict[str, list[str]] = {}
        self.hidden_delete_markers: dict[str, list[str]] = {}
        self.pending_uploads: dict[str, list[str]] = {}
        self.multipart: dict[tuple[str, str, str], list[bytes]] = {}
        self.fail_inventory: set[str] = set()
        self.reject_conditional_writes = False
        self.omit_pagination_marker = False
        self.duplicate_inventory_entry = False

    @staticmethod
    def _etag(content: bytes) -> str:
        return f'"{hashlib.md5(content, usedforsecurity=False).hexdigest()}"'

    async def list_objects_v2(
        self, *, Bucket: str, MaxKeys: int, **_: Any
    ) -> dict[str, Any]:
        del MaxKeys
        if "current" in self.fail_inventory:
            raise OSError("synthetic list failure")
        contents = [
            {"Key": key, "Size": len(content), "ETag": self.etags[(Bucket, key)]}
            for bucket, key in sorted(self.objects)
            if bucket == Bucket
            for content in [self.objects[(bucket, key)]]
        ]
        if self.duplicate_inventory_entry and contents:
            contents.append(dict(contents[0]))
        self.events.append(("list", Bucket, "current"))
        page = {"Contents": contents, "KeyCount": len(contents)}
        if not self.omit_pagination_marker:
            page["IsTruncated"] = False
        return page

    async def list_object_versions(
        self, *, Bucket: str, MaxKeys: int
    ) -> dict[str, Any]:
        del MaxKeys
        if "versions" in self.fail_inventory:
            raise OSError("synthetic version inventory unavailable")
        self.events.append(("list", Bucket, "versions"))
        versions = [{"Key": key} for key in self.hidden_versions.get(Bucket, [])]
        delete_markers = [
            {"Key": key} for key in self.hidden_delete_markers.get(Bucket, [])
        ]
        return {
            "Versions": versions,
            "DeleteMarkers": delete_markers,
            "IsTruncated": False,
        }

    async def list_multipart_uploads(
        self, *, Bucket: str, MaxUploads: int
    ) -> dict[str, Any]:
        del MaxUploads
        if "uploads" in self.fail_inventory:
            raise OSError("synthetic upload inventory unavailable")
        self.events.append(("list", Bucket, "uploads"))
        uploads = [{"Key": key} for key in self.pending_uploads.get(Bucket, [])]
        return {"Uploads": uploads, "IsTruncated": False}

    async def get_object(
        self,
        *,
        Bucket: str,
        Key: str,
        VersionId: str | None = None,
        IfMatch: str | None = None,
    ) -> dict[str, Any]:
        identity = (Bucket, Key)
        content = self.objects[identity]
        self.events.append(("get", Bucket, Key))
        if VersionId is not None and self.version_ids.get(identity) != VersionId:
            raise OSError("synthetic version mismatch")
        if IfMatch is not None and self.etags[identity] != IfMatch:
            raise OSError("synthetic ETag mismatch")
        return {
            "Body": FakeBody(content),
            "ContentLength": len(content),
            "ETag": self.etags[identity],
            "VersionId": self.version_ids.get(identity),
            **self.headers.get(identity, {}),
        }

    async def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: bytes,
        IfNoneMatch: str,
        **headers: Any,
    ) -> dict[str, str]:
        self.events.append(("put", Bucket, Key))
        assert IfNoneMatch == "*"
        if self.reject_conditional_writes:
            raise OSError("conditional writes unsupported")
        identity = (Bucket, Key)
        if identity in self.objects:
            raise OSError("precondition failed")
        self.objects[identity] = Body
        self.etags[identity] = self._etag(Body)
        self.version_ids[identity] = f"version-{len(self.objects)}"
        self.headers[identity] = headers
        return {"ETag": self.etags[identity], "VersionId": self.version_ids[identity]}

    async def create_multipart_upload(
        self, *, Bucket: str, Key: str, **headers: Any
    ) -> dict[str, str]:
        upload_id = f"upload-{len(self.multipart) + 1}"
        self.multipart[(Bucket, Key, upload_id)] = []
        self.headers[(Bucket, Key)] = headers
        return {"UploadId": upload_id}

    async def upload_part(
        self,
        *,
        Bucket: str,
        Key: str,
        UploadId: str,
        PartNumber: int,
        Body: bytes,
    ) -> dict[str, str]:
        parts = self.multipart[(Bucket, Key, UploadId)]
        assert PartNumber == len(parts) + 1
        parts.append(Body)
        return {"ETag": self._etag(Body)}

    async def complete_multipart_upload(
        self,
        *,
        Bucket: str,
        Key: str,
        UploadId: str,
        MultipartUpload: dict[str, Any],
        IfNoneMatch: str,
    ) -> dict[str, str]:
        assert IfNoneMatch == "*"
        if self.reject_conditional_writes:
            raise OSError("conditional writes unsupported")
        identity = (Bucket, Key)
        if identity in self.objects:
            raise OSError("precondition failed")
        parts = self.multipart.pop((Bucket, Key, UploadId))
        content = b"".join(parts)
        self.events.append(("complete", Bucket, Key))
        self.objects[identity] = content
        self.etags[identity] = self._etag(content)
        self.version_ids[identity] = f"version-{len(self.objects)}"
        return {"ETag": self.etags[identity], "VersionId": self.version_ids[identity]}

    async def abort_multipart_upload(
        self, *, Bucket: str, Key: str, UploadId: str
    ) -> None:
        self.multipart.pop((Bucket, Key, UploadId), None)


def _s3_settings(bucket: str) -> backup_db.S3Settings:
    return backup_db.S3Settings(
        endpoint_url="https://s3.example.test",
        bucket=bucket,
        prefix="database",
        region="test-region",
    )


def _v1_database_manifest() -> dict[str, Any]:
    payload = b"synthetic database archive"
    return {
        "schema_version": 1,
        "source_database": "synthetic_source",
        "source_revision": ["synthetic_revision"],
        "created_at": "2026-10-01T00:00:00Z",
        "format": "pg_dump.custom",
        "artifact_key": "database/snapshots/0123456789abcdef0123456789abcdef/database.dump",
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _paired_manifest_data() -> dict[str, Any]:
    digest = hashlib.sha256(b"synthetic object").hexdigest()
    snapshot_id = "0123456789abcdef0123456789abcdef"
    root = f"database/snapshots/{snapshot_id}"
    return {
        "schema_version": 2,
        "snapshot_id": snapshot_id,
        "consistency_mode": "operator_quiesced",
        "quiescence_confirmed": True,
        "quiescence_confirmed_at": "2026-10-01T00:00:00Z",
        "source_object_bucket": "synthetic-uploads",
        "database": _v1_database_manifest(),
        "database_archive_version_id": None,
        "database_archive_etag": '"database-etag"',
        "objects": [
            {
                "source_key": "users/42/avatar.png",
                "source_version_id": "source-version-7",
                "archive_key": f"{root}/objects/{digest}.blob",
                "archive_version_id": None,
                "archive_etag": '"object-etag"',
                "size_bytes": len(b"synthetic object"),
                "sha256": digest,
                "content_type": "image/png",
                "content_encoding": None,
                "cache_control": "private, max-age=60",
                "content_disposition": None,
            }
        ],
    }


def test_paired_snapshot_manifest_round_trips_source_version_and_quiescence() -> None:
    data = _paired_manifest_data()
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()

    manifest = backup_db.parse_paired_snapshot_manifest(
        payload,
        expected_manifest_key=(
            "database/snapshots/0123456789abcdef0123456789abcdef/database.manifest.json"
        ),
    )

    assert manifest.snapshot_id == "0123456789abcdef0123456789abcdef"
    assert manifest.quiescence_confirmed is True
    assert manifest.objects[0].source_version_id == "source-version-7"
    assert manifest.objects[0].source_key == "users/42/avatar.png"
    assert manifest.to_json_bytes() == payload + b"\n"
    assert b"password" not in manifest.to_json_bytes().lower()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("quiescence_confirmed", False),
        ("consistency_mode", "best_effort"),
        ("source_object_bucket", "invalid_bucket_name"),
    ],
)
def test_paired_snapshot_manifest_rejects_untrusted_consistency_or_bucket(
    field: str, value: Any
) -> None:
    data = _paired_manifest_data()
    data[field] = value

    with pytest.raises(backup_db.BackupArtifactError):
        backup_db.parse_paired_snapshot_manifest(
            json.dumps(data).encode(),
            expected_manifest_key=(
                "database/snapshots/0123456789abcdef0123456789abcdef/database.manifest.json"
            ),
        )


def test_paired_snapshot_manifest_rejects_duplicate_source_object_keys() -> None:
    data = _paired_manifest_data()
    data["objects"].append(dict(data["objects"][0]))

    with pytest.raises(backup_db.BackupArtifactError, match="unique"):
        backup_db.parse_paired_snapshot_manifest(
            json.dumps(data).encode(),
            expected_manifest_key=(
                "database/snapshots/0123456789abcdef0123456789abcdef/database.manifest.json"
            ),
        )


def test_paired_snapshot_manifest_rejects_inconsistent_deduplicated_artifact() -> None:
    data = _paired_manifest_data()
    duplicate = dict(data["objects"][0])
    duplicate["source_key"] = "users/43/avatar.png"
    duplicate["size_bytes"] += 1
    data["objects"].append(duplicate)

    with pytest.raises(backup_db.BackupArtifactError, match="inconsistent metadata"):
        backup_db.parse_paired_snapshot_manifest(
            json.dumps(data).encode(),
            expected_manifest_key=(
                "database/snapshots/0123456789abcdef0123456789abcdef/database.manifest.json"
            ),
        )


@pytest.mark.asyncio
async def test_paired_snapshot_uploads_every_source_object_before_commit_manifest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FakeS3()
    source_bucket = "synthetic-uploads"
    backup_bucket = "synthetic-backups"
    source_values = {
        "chat/file.bin": (b"synthetic chat object", None),
        "users/42/avatar.png": (b"synthetic avatar", "source-version-7"),
    }
    for key, (content, version_id) in source_values.items():
        identity = (source_bucket, key)
        store.objects[identity] = content
        store.etags[identity] = store._etag(content)
        if version_id is not None:
            store.version_ids[identity] = version_id
        store.headers[identity] = {"ContentType": "application/octet-stream"}

    @asynccontextmanager
    async def fake_client(_settings: backup_db.S3Settings):
        yield store

    monkeypatch.setattr(backup_db, "s3_client", fake_client)
    monkeypatch.setattr(
        backup_db,
        "source_database_metadata",
        lambda _url: ("synthetic_source", ("synthetic_revision",)),
    )

    def fake_dump(_url: str, archive_path: Path) -> None:
        archive_path.write_bytes(b"synthetic database archive")

    monkeypatch.setattr(backup_db, "dump_database", fake_dump)
    key = await backup_db.backup_paired_snapshot_to_s3(
        "postgresql://synthetic@localhost/source",
        _s3_settings(backup_bucket),
        _s3_settings(source_bucket),
        confirm_source_quiesced=True,
    )

    payload = store.objects[(backup_bucket, key)]
    manifest = backup_db.parse_paired_snapshot_manifest(
        payload, expected_manifest_key=key
    )
    assert manifest.consistency_mode == "operator_quiesced"
    assert manifest.quiescence_confirmed is True
    assert {entry.source_key for entry in manifest.objects} == set(source_values)
    assert {
        entry.source_key: entry.source_version_id for entry in manifest.objects
    } == {
        "chat/file.bin": None,
        "users/42/avatar.png": "source-version-7",
    }
    for entry in manifest.objects:
        assert (
            store.objects[(backup_bucket, entry.archive_key)]
            == source_values[entry.source_key][0]
        )
    database_identity = (backup_bucket, manifest.database.artifact_key)
    assert store.objects[database_identity] == b"synthetic database archive"
    assert [event for event in store.events if event[0] == "put"][-1] == (
        "put",
        backup_bucket,
        key,
    )
    assert not any(event[0] == "delete" for event in store.events)
    assert all(
        store.objects[(source_bucket, key)] == value[0]
        for key, value in source_values.items()
    )


@pytest.mark.asyncio
async def test_paired_snapshot_requires_quiescence_before_database_or_s3_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        backup_db,
        "source_database_metadata",
        lambda _url: calls.append("database") or ("source", ("revision",)),
    )

    @asynccontextmanager
    async def fake_client(_settings: backup_db.S3Settings):
        calls.append("s3")
        pytest.fail("unconfirmed snapshot reached object storage")
        yield None

    monkeypatch.setattr(backup_db, "s3_client", fake_client)
    with pytest.raises(backup_db.BackupArtifactError, match="quiescence"):
        await backup_db.backup_paired_snapshot_to_s3(
            "postgresql://synthetic@localhost/source",
            _s3_settings("synthetic-backups"),
            _s3_settings("synthetic-uploads"),
            confirm_source_quiesced=False,
        )
    assert calls == []


@pytest.mark.asyncio
async def test_source_object_inventory_rejects_unknown_pagination_state() -> None:
    store = FakeS3()
    store.omit_pagination_marker = True

    with pytest.raises(backup_db.BackupArtifactError, match="pagination"):
        await backup_db._list_current_objects(store, "synthetic-uploads")


@pytest.mark.asyncio
async def test_source_object_inventory_rejects_duplicate_keys() -> None:
    store = FakeS3()
    store.objects[("synthetic-uploads", "users/42/avatar.png")] = b"synthetic"
    store.etags[("synthetic-uploads", "users/42/avatar.png")] = store._etag(
        b"synthetic"
    )
    store.duplicate_inventory_entry = True

    with pytest.raises(backup_db.BackupArtifactError, match="duplicate"):
        await backup_db._list_current_objects(store, "synthetic-uploads")


@pytest.mark.asyncio
async def test_source_object_inventory_rejects_non_string_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FakeS3()

    async def invalid_inventory(**_kwargs: Any) -> dict[str, Any]:
        return {
            "Contents": [{"Key": None, "Size": 0, "ETag": '"empty"'}],
            "KeyCount": 1,
            "IsTruncated": False,
        }

    monkeypatch.setattr(store, "list_objects_v2", invalid_inventory)

    with pytest.raises(backup_db.BackupArtifactError, match="object key"):
        await backup_db._list_current_objects(store, "synthetic-uploads")


def test_source_storage_settings_require_s3_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.core.config.storage.StorageSettings",
        lambda: SimpleNamespace(
            storage_backend="filesystem",
            storage_s3_endpoint_url="https://objects.example.test",
            storage_s3_bucket="synthetic-uploads",
            storage_s3_region="test-region",
            storage_s3_access_key_id="",
            storage_s3_secret_access_key="",
        ),
    )

    with pytest.raises(backup_db.BackupArtifactError, match="S3 storage backend"):
        backup_db.storage_s3_settings_from_environment()


def test_storage_credentials_are_not_rendered_by_settings_repr() -> None:
    marker = "synthetic-s3-secret-marker"
    settings = backup_db.S3Settings(
        endpoint_url="https://s3.example.test",
        bucket="synthetic-uploads",
        prefix="",
        region="test-region",
        access_key_id="synthetic-access-key",
        secret_access_key=marker,
    )

    assert marker not in repr(settings)


@pytest.mark.parametrize("backend", ["s3", "minio"])
def test_application_s3_settings_use_the_canonical_configured_fields(
    monkeypatch: pytest.MonkeyPatch, backend: str
) -> None:
    marker = "synthetic-storage-secret-marker"
    monkeypatch.setattr(
        "app.core.config.storage.StorageSettings",
        lambda: SimpleNamespace(
            storage_backend=backend,
            storage_s3_endpoint_url="https://objects.example.test",
            storage_s3_bucket="synthetic-uploads",
            storage_s3_region="eu-test-1",
            storage_s3_access_key_id="synthetic-access",
            storage_s3_secret_access_key=marker,
        ),
    )

    settings = backup_db.storage_s3_settings_from_environment()

    assert settings.endpoint_url == "https://objects.example.test"
    assert settings.bucket == "synthetic-uploads"
    assert settings.region == "eu-test-1"
    assert settings.access_key_id == "synthetic-access"
    assert settings.secret_access_key == marker
    assert marker not in repr(settings)


def test_snapshot_cli_requires_explicit_quiescence_confirmation() -> None:
    with pytest.raises(backup_db.BackupArtifactError, match="Invalid command-line"):
        backup_db.build_parser().parse_args(["snapshot"])


def _seed_paired_backup(store: FakeS3) -> tuple[str, bytes, bytes, str]:
    data = _paired_manifest_data()
    database = data["database"]
    database_bytes = b"synthetic database archive"
    object_bytes = b"synthetic object"
    backup_bucket = "synthetic-backups"
    database_key = database["artifact_key"]
    object_entry = data["objects"][0]
    object_key = object_entry["archive_key"]
    for key, content in ((database_key, database_bytes), (object_key, object_bytes)):
        identity = (backup_bucket, key)
        store.objects[identity] = content
        store.etags[identity] = store._etag(content)
    data["database_archive_etag"] = store.etags[(backup_bucket, database_key)]
    object_entry["archive_etag"] = store.etags[(backup_bucket, object_key)]
    manifest_key = backup_db.manifest_key(database_key)
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    store.objects[(backup_bucket, manifest_key)] = payload
    store.etags[(backup_bucket, manifest_key)] = store._etag(payload)
    return manifest_key, database_bytes, object_bytes, object_entry["source_key"]


class FakeDatabaseConnection:
    def __init__(
        self, *, exists: bool = False, events: list[str] | None = None
    ) -> None:
        self.exists = exists
        self.events = events if events is not None else []

    def __enter__(self) -> FakeDatabaseConnection:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def execute(self, query: Any, params: tuple[str, ...]) -> Any:
        assert "SELECT 1 FROM pg_database" in str(query)
        self.events.append("database-preflight")
        assert params == ("restore_acceptance",)
        return type(
            "Result", (), {"fetchone": lambda _self: (1,) if self.exists else None}
        )()


def test_restore_database_creation_uses_createdb_with_separate_identifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target_database = "restore_safe_target"
    marker = "synthetic-admin-password"
    admin_url = (
        backup_db.make_url("postgresql://restore_admin@localhost:5432/postgres")
        .set(password=marker)
        .render_as_string(hide_password=False)
    )
    query_calls: list[tuple[Any, Any]] = []
    command_calls: list[dict[str, Any]] = []

    class MissingDatabaseConnection:
        def __enter__(self) -> MissingDatabaseConnection:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def execute(self, query: Any, params: tuple[str, ...]) -> Any:
            query_calls.append((query, params))
            assert query == "SELECT 1 FROM pg_database WHERE datname = %s"
            assert params == (target_database,)
            return type("Result", (), {"fetchone": lambda _self: None})()

    monkeypatch.setattr(
        backup_db.psycopg,
        "connect",
        lambda *_args, **_kwargs: MissingDatabaseConnection(),
    )

    def capture_command(command: list[str], **kwargs: Any) -> Any:
        command_calls.append({"command": command, **kwargs})
        return SimpleNamespace(returncode=0)

    backup_db._ensure_new_database(
        admin_url, target_database, command_runner=capture_command
    )

    assert query_calls == [
        ("SELECT 1 FROM pg_database WHERE datname = %s", (target_database,))
    ]
    assert len(command_calls) == 1
    assert command_calls[0]["command"] == [
        "createdb",
        "--no-password",
        "--maintenance-db",
        "postgres",
        target_database,
    ]
    assert marker not in " ".join(command_calls[0]["command"])
    assert command_calls[0]["env"]["PGPASSWORD"] == marker
    assert command_calls[0]["stderr"] is backup_db.subprocess.DEVNULL


def test_restore_database_creation_rejects_untrusted_identifier_before_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_calls: list[bool] = []
    command_calls: list[list[str]] = []

    def forbidden_database_connect(*_args: Any, **_kwargs: Any) -> None:
        database_calls.append(True)
        pytest.fail("untrusted database identifier reached PostgreSQL")

    def forbidden_command(command: list[str], **_kwargs: Any) -> Any:
        command_calls.append(command)
        pytest.fail("untrusted database identifier reached createdb")

    monkeypatch.setattr(backup_db.psycopg, "connect", forbidden_database_connect)

    with pytest.raises(backup_db.BackupArtifactError, match="restore_<name>"):
        backup_db._ensure_new_database(
            "postgresql://restore_admin@localhost:5432/postgres",
            "restore_target;DROP_DATABASE_university",
            command_runner=forbidden_command,
        )

    assert database_calls == []
    assert command_calls == []


@pytest.mark.asyncio
async def test_restore_paired_snapshot_preflights_then_restores_into_empty_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FakeS3()
    manifest_key, database_bytes, object_bytes, source_key = _seed_paired_backup(store)
    events: list[str] = []

    @asynccontextmanager
    async def fake_client(_settings: backup_db.S3Settings):
        yield store

    monkeypatch.setattr(backup_db, "s3_client", fake_client)
    restore_calls: list[Path] = []

    def fake_restore(
        archive_path: Path,
        manifest: backup_db.BackupManifest,
        _admin_url: str,
        target_database: str,
    ) -> None:
        assert archive_path.read_bytes() == database_bytes
        assert manifest.source_database == "synthetic_source"
        assert target_database == "restore_acceptance"
        events.append("database-restored")
        restore_calls.append(archive_path)

    monkeypatch.setattr(backup_db, "restore_archive", fake_restore)

    def fake_connect(_dsn: str, *, autocommit: bool) -> FakeDatabaseConnection:
        assert autocommit is True
        return FakeDatabaseConnection(events=events)

    result = await backup_db.restore_paired_snapshot_from_s3(
        manifest_key,
        "restore_acceptance",
        "postgresql://synthetic@localhost/admin",
        _s3_settings("synthetic-backups"),
        _s3_settings("synthetic-uploads"),
        "synthetic-restore",
        database_connect=fake_connect,
    )

    assert result.snapshot_id == "0123456789abcdef0123456789abcdef"
    assert restore_calls
    assert store.objects[("synthetic-restore", source_key)] == object_bytes
    assert (
        store.headers[("synthetic-restore", source_key)]["ContentType"] == "image/png"
    )
    assert events.index("database-preflight") < events.index("database-restored")
    assert events.index("database-restored") < next(
        index
        for index, event in enumerate(store.events)
        if event == ("put", "synthetic-restore", source_key)
    )
    assert not any(event[0] == "delete" for event in store.events)
    assert store.objects[("synthetic-backups", manifest_key)]


@pytest.mark.parametrize(
    "preexisting",
    ["current", "version", "delete-marker", "multipart", "inventory-unavailable"],
)
@pytest.mark.asyncio
async def test_restore_rejects_nonempty_or_unverifiably_empty_bucket_before_writes(
    monkeypatch: pytest.MonkeyPatch, preexisting: str
) -> None:
    store = FakeS3()
    manifest_key, _database_bytes, _object_bytes, source_key = _seed_paired_backup(
        store
    )
    target_bucket = "synthetic-restore"
    if preexisting == "current":
        identity = (target_bucket, "operator-owned.txt")
        store.objects[identity] = b"operator data"
        store.etags[identity] = store._etag(b"operator data")
    elif preexisting == "version":
        store.hidden_versions[target_bucket] = ["previously-deleted.bin"]
    elif preexisting == "delete-marker":
        store.hidden_delete_markers[target_bucket] = ["deleted-by-operator.bin"]
    elif preexisting == "inventory-unavailable":
        store.fail_inventory.add("versions")
    else:
        store.pending_uploads[target_bucket] = ["unfinished.bin"]

    @asynccontextmanager
    async def fake_client(_settings: backup_db.S3Settings):
        yield store

    monkeypatch.setattr(backup_db, "s3_client", fake_client)
    monkeypatch.setattr(
        backup_db,
        "restore_archive",
        lambda *_args, **_kwargs: pytest.fail(
            "invalid target bucket reached DB restore"
        ),
    )

    with pytest.raises(backup_db.BackupArtifactError, match="bucket"):
        await backup_db.restore_paired_snapshot_from_s3(
            manifest_key,
            "restore_acceptance",
            "postgresql://synthetic@localhost/admin",
            _s3_settings("synthetic-backups"),
            _s3_settings("synthetic-uploads"),
            target_bucket,
            database_connect=lambda *_args, **_kwargs: FakeDatabaseConnection(),
        )

    assert not any(
        event[0] == "put" and event[1] == target_bucket for event in store.events
    )
    assert store.objects[("synthetic-backups", manifest_key)]
    if preexisting == "current":
        assert store.objects[(target_bucket, "operator-owned.txt")] == b"operator data"
    assert source_key not in {
        key for bucket, key in store.objects if bucket == target_bucket
    }


@pytest.mark.asyncio
async def test_restore_preflights_all_checksums_before_database_or_object_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FakeS3()
    manifest_key, _database_bytes, _object_bytes, _source_key = _seed_paired_backup(
        store
    )
    manifest = backup_db.parse_paired_snapshot_manifest(
        store.objects[("synthetic-backups", manifest_key)],
        expected_manifest_key=manifest_key,
    )
    object_key = manifest.objects[0].archive_key
    store.objects[("synthetic-backups", object_key)] = b"Xynthetic object"
    database_preflights: list[str] = []

    @asynccontextmanager
    async def fake_client(_settings: backup_db.S3Settings):
        yield store

    monkeypatch.setattr(backup_db, "s3_client", fake_client)
    monkeypatch.setattr(
        backup_db,
        "restore_archive",
        lambda *_args, **_kwargs: pytest.fail("checksum failure reached DB restore"),
    )

    with pytest.raises(backup_db.BackupArtifactError, match="checksum"):
        await backup_db.restore_paired_snapshot_from_s3(
            manifest_key,
            "restore_acceptance",
            "postgresql://synthetic@localhost/admin",
            _s3_settings("synthetic-backups"),
            _s3_settings("synthetic-uploads"),
            "synthetic-restore",
            database_connect=lambda *_args, **_kwargs: database_preflights.append(
                "called"
            ),
        )

    assert database_preflights == []
    assert not any(
        event[0] == "list" and event[1] == "synthetic-restore" for event in store.events
    )
    assert not any(
        event[0] == "put" and event[1] == "synthetic-restore" for event in store.events
    )


@pytest.mark.asyncio
async def test_target_create_only_write_preserves_a_concurrent_foreign_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FakeS3()
    manifest_key, _database_bytes, _object_bytes, source_key = _seed_paired_backup(
        store
    )
    target_bucket = "synthetic-restore"

    @asynccontextmanager
    async def fake_client(_settings: backup_db.S3Settings):
        yield store

    monkeypatch.setattr(backup_db, "s3_client", fake_client)

    def race_during_database_restore(*_args: Any, **_kwargs: Any) -> None:
        content = b"operator object created after empty-bucket preflight"
        identity = (target_bucket, source_key)
        store.objects[identity] = content
        store.etags[identity] = store._etag(content)
        store.events.append(("foreign-write", target_bucket, source_key))

    monkeypatch.setattr(backup_db, "restore_archive", race_during_database_restore)

    with pytest.raises(backup_db.BackupArtifactError, match="incomplete"):
        await backup_db.restore_paired_snapshot_from_s3(
            manifest_key,
            "restore_acceptance",
            "postgresql://synthetic@localhost/admin",
            _s3_settings("synthetic-backups"),
            _s3_settings("synthetic-uploads"),
            target_bucket,
            database_connect=lambda *_args, **_kwargs: FakeDatabaseConnection(),
        )

    assert store.objects[(target_bucket, source_key)] == (
        b"operator object created after empty-bucket preflight"
    )
    assert not any(event[0] == "delete" for event in store.events)


@pytest.mark.asyncio
async def test_snapshot_manifest_size_cap_is_checked_before_conditional_publish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class PutForbidden:
        async def put_object(self, **_kwargs: Any) -> None:
            pytest.fail("oversized manifest reached S3")

    monkeypatch.setattr(backup_db, "PAIRED_SNAPSHOT_MANIFEST_MAX_BYTES", 4)

    with pytest.raises(backup_db.BackupArtifactError, match="size"):
        await backup_db._publish_paired_manifest(
            PutForbidden(), "synthetic-backups", "snapshot/manifest.json", b"12345"
        )


@pytest.mark.asyncio
async def test_create_only_uploads_fail_closed_without_conditional_write_support(
    tmp_path: Path,
) -> None:
    store = FakeS3()
    store.reject_conditional_writes = True
    artifact = tmp_path / "object.bin"
    artifact.write_bytes(b"synthetic immutable bytes")

    with pytest.raises(backup_db.BackupArtifactError, match="conditionally"):
        await backup_db._upload_file_create_only(
            store, "synthetic-bucket", "snapshots/run/object.blob", artifact
        )

    assert not store.objects


@pytest.mark.asyncio
async def test_multipart_snapshot_upload_uses_conditional_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = FakeS3()
    artifact = tmp_path / "large-object.bin"
    artifact.write_bytes(b"synthetic multipart bytes")
    monkeypatch.setattr(backup_db, "SNAPSHOT_PART_SIZE", 5)

    receipt = await backup_db._upload_file_create_only(
        store, "synthetic-bucket", "snapshots/run/object.blob", artifact
    )
    await backup_db._verify_uploaded_file(
        store,
        "synthetic-bucket",
        "snapshots/run/object.blob",
        artifact,
        receipt=receipt,
    )

    assert store.objects[("synthetic-bucket", "snapshots/run/object.blob")] == (
        artifact.read_bytes()
    )
    assert any(event[0] == "complete" for event in store.events)


@pytest.mark.asyncio
async def test_restore_rejects_existing_database_before_target_bucket_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FakeS3()
    manifest_key, _database_bytes, _object_bytes, _source_key = _seed_paired_backup(
        store
    )

    @asynccontextmanager
    async def fake_client(_settings: backup_db.S3Settings):
        yield store

    monkeypatch.setattr(backup_db, "s3_client", fake_client)
    monkeypatch.setattr(
        backup_db,
        "restore_archive",
        lambda *_args, **_kwargs: pytest.fail("existing target DB reached restore"),
    )

    with pytest.raises(backup_db.BackupArtifactError, match="already exists"):
        await backup_db.restore_paired_snapshot_from_s3(
            manifest_key,
            "restore_acceptance",
            "postgresql://synthetic@localhost/admin",
            _s3_settings("synthetic-backups"),
            _s3_settings("synthetic-uploads"),
            "synthetic-restore",
            database_connect=lambda *_args, **_kwargs: FakeDatabaseConnection(
                exists=True
            ),
        )

    assert not any(
        event[0] == "put" and event[1] == "synthetic-restore" for event in store.events
    )


@pytest.mark.parametrize("target_bucket", ["synthetic-uploads", "synthetic-backups"])
@pytest.mark.asyncio
async def test_restore_rejects_source_or_backup_bucket_as_target_before_reads(
    monkeypatch: pytest.MonkeyPatch, target_bucket: str
) -> None:
    store = FakeS3()
    manifest_key, _database_bytes, _object_bytes, _source_key = _seed_paired_backup(
        store
    )

    @asynccontextmanager
    async def fake_client(_settings: backup_db.S3Settings):
        yield store

    monkeypatch.setattr(backup_db, "s3_client", fake_client)

    with pytest.raises(backup_db.BackupArtifactError, match="differ"):
        await backup_db.restore_paired_snapshot_from_s3(
            manifest_key,
            "restore_acceptance",
            "postgresql://synthetic@localhost/admin",
            _s3_settings("synthetic-backups"),
            _s3_settings("synthetic-uploads"),
            target_bucket,
            database_connect=lambda *_args, **_kwargs: pytest.fail(
                "bucket alias reached database preflight"
            ),
        )

    assert store.events == [("get", "synthetic-backups", manifest_key)]
    assert not any(event[0] == "put" for event in store.events)
