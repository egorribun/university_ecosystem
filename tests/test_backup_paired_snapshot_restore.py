from __future__ import annotations

import asyncio
import hashlib
import json
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from scripts import backup_db

_PREFIX_NOT_SUPPLIED = object()


class FakeBody:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.closed = False

    async def read(self, size: int = -1) -> bytes:
        if size < 0:
            content, self.content = self.content, b""
            return content
        content, self.content = self.content[:size], self.content[size:]
        return content

    async def close(self) -> None:
        self.closed = True

    async def __aenter__(self) -> FakeBody:
        return self

    async def __aexit__(self, *_args: Any) -> None:
        await self.close()


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.etags: dict[tuple[str, str], str] = {}
        self.version_ids: dict[tuple[str, str], str] = {}
        self.headers: dict[tuple[str, str], dict[str, Any]] = {}
        self.events: list[tuple[str, str, str]] = []
        self.reject_put_keys: set[tuple[str, str]] = set()
        self.hidden_versions: dict[str, list[str]] = {}
        self.hidden_delete_markers: dict[str, list[str]] = {}
        self.pending_uploads: dict[str, list[str]] = {}
        self.multipart: dict[tuple[str, str, str], list[bytes]] = {}
        self.fail_inventory: set[str] = set()
        self.inventory_requests: list[dict[str, Any]] = []
        self.reject_conditional_writes = False
        self.omit_pagination_marker = False
        self.duplicate_inventory_entry = False

    @staticmethod
    def _etag(content: bytes) -> str:
        return f'"{hashlib.md5(content, usedforsecurity=False).hexdigest()}"'

    async def list_objects_v2(
        self,
        *,
        Bucket: str,
        MaxKeys: int,
        Prefix: Any = _PREFIX_NOT_SUPPLIED,
        **_: Any,
    ) -> dict[str, Any]:
        prefix_supplied = Prefix is not _PREFIX_NOT_SUPPLIED
        prefix = Prefix if prefix_supplied else ""
        self.inventory_requests.append(
            {
                "operation": "list_objects_v2",
                "Bucket": Bucket,
                "MaxKeys": MaxKeys,
                "Prefix": prefix,
                "PrefixSupplied": prefix_supplied,
            }
        )
        del MaxKeys
        if "current" in self.fail_inventory:
            raise OSError("synthetic list failure")
        contents = [
            {"Key": key, "Size": len(content), "ETag": self.etags[(Bucket, key)]}
            for bucket, key in sorted(self.objects)
            if bucket == Bucket and key.startswith(prefix)
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
        self,
        *,
        Bucket: str,
        MaxKeys: int,
        Prefix: Any = _PREFIX_NOT_SUPPLIED,
    ) -> dict[str, Any]:
        prefix_supplied = Prefix is not _PREFIX_NOT_SUPPLIED
        prefix = Prefix if prefix_supplied else ""
        self.inventory_requests.append(
            {
                "operation": "list_object_versions",
                "Bucket": Bucket,
                "MaxKeys": MaxKeys,
                "Prefix": prefix,
                "PrefixSupplied": prefix_supplied,
            }
        )
        del MaxKeys
        if "versions" in self.fail_inventory:
            raise OSError("synthetic version inventory unavailable")
        self.events.append(("list", Bucket, "versions"))
        versions = [
            {"Key": key}
            for key in self.hidden_versions.get(Bucket, [])
            if key.startswith(prefix)
        ]
        delete_markers = [
            {"Key": key}
            for key in self.hidden_delete_markers.get(Bucket, [])
            if key.startswith(prefix)
        ]
        return {
            "Versions": versions,
            "DeleteMarkers": delete_markers,
            "IsTruncated": False,
        }

    async def list_multipart_uploads(
        self,
        *,
        Bucket: str,
        MaxUploads: int,
        Prefix: Any = _PREFIX_NOT_SUPPLIED,
    ) -> dict[str, Any]:
        prefix_supplied = Prefix is not _PREFIX_NOT_SUPPLIED
        prefix = Prefix if prefix_supplied else ""
        self.inventory_requests.append(
            {
                "operation": "list_multipart_uploads",
                "Bucket": Bucket,
                "MaxUploads": MaxUploads,
                "Prefix": prefix,
                "PrefixSupplied": prefix_supplied,
            }
        )
        del MaxUploads
        if "uploads" in self.fail_inventory:
            raise OSError("synthetic upload inventory unavailable")
        self.events.append(("list", Bucket, "uploads"))
        uploads = [
            {"Key": key}
            for key in self.pending_uploads.get(Bucket, [])
            if key.startswith(prefix)
        ]
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
        identity = (Bucket, Key)
        if self.reject_conditional_writes or identity in self.reject_put_keys:
            raise OSError("conditional writes unsupported")
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


def _s3_settings(
    bucket: str, *, public_base_url: str | None = None
) -> backup_db.S3Settings:
    return backup_db.S3Settings(
        endpoint_url="https://s3.example.test",
        bucket=bucket,
        prefix="database",
        region="test-region",
        public_base_url=public_base_url,
    )


def _target_public_base_url(bucket: str) -> str:
    return f"https://s3.example.test/{bucket}"


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
        "schema_version": 3,
        "snapshot_id": snapshot_id,
        "consistency_mode": "operator_quiesced",
        "quiescence_confirmed": True,
        "quiescence_confirmed_at": "2026-10-01T00:00:00Z",
        "source_object_bucket": "synthetic-uploads",
        "source_storage_public_base_url": "https://s3.example.test/synthetic-uploads",
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


@pytest.mark.parametrize("payload", [b"[]", b"null", b'"manifest"'])
def test_paired_snapshot_manifest_rejects_non_object_json(payload: bytes) -> None:
    with pytest.raises(backup_db.BackupArtifactError, match="fields do not match"):
        backup_db.parse_paired_snapshot_manifest(
            payload,
            expected_manifest_key=(
                "database/snapshots/0123456789abcdef0123456789abcdef/database.manifest.json"
            ),
        )


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        " https://storage.example.test",
        "https://storage.example.test/" + "x" * 2048,
        "https://storage.example.test/a%2Fb",
    ],
)
def test_storage_public_base_url_rejects_invalid_unparsed_values(value: Any) -> None:
    with pytest.raises(backup_db.BackupArtifactError, match="is invalid"):
        backup_db._validate_storage_public_base_url(value, label="test URL")


def test_storage_public_base_url_rejects_invalid_port_and_url_structure() -> None:
    for value in ("https://storage.example.test:99999", "ftp://storage.example.test"):
        with pytest.raises(backup_db.BackupArtifactError, match="is invalid"):
            backup_db._validate_storage_public_base_url(value, label="test URL")


def test_storage_public_base_url_allows_http_only_for_opted_in_local_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_url = "http://localhost:9000/uploads"
    with pytest.raises(backup_db.BackupArtifactError, match="must use HTTPS"):
        backup_db._validate_storage_public_base_url(local_url, label="test URL")

    monkeypatch.setenv("BACKUP_S3_ALLOW_HTTP_FOR_LOCAL_DEV", "true")
    assert (
        backup_db._validate_storage_public_base_url(local_url, label="test URL")
        == local_url
    )
    with pytest.raises(backup_db.BackupArtifactError, match="must use HTTPS"):
        backup_db._validate_storage_public_base_url(
            "http://storage.example.test/uploads", label="test URL"
        )


def test_storage_public_base_url_uses_application_override_endpoint_and_aws_default() -> (
    None
):
    assert (
        backup_db._s3_storage_public_base_url(
            _s3_settings(
                "synthetic-uploads", public_base_url="https://cdn.example.test/uploads/"
            )
        )
        == "https://cdn.example.test/uploads"
    )
    assert (
        backup_db._s3_storage_public_base_url(_s3_settings("synthetic-uploads"))
        == "https://s3.example.test/synthetic-uploads"
    )
    assert (
        backup_db._s3_storage_public_base_url(
            replace(_s3_settings("synthetic-uploads"), endpoint_url=None)
        )
        == "https://synthetic-uploads.s3.amazonaws.com"
    )


@pytest.mark.parametrize("key", ["", " leading", "bad%escape", "a//b", "a/../b"])
def test_application_storage_key_rejects_keys_outside_app_contract(key: str) -> None:
    with pytest.raises(backup_db.BackupArtifactError, match="unsupported"):
        backup_db._validate_application_storage_key(key)


def _parsed_paired_manifest() -> backup_db.PairedSnapshotManifest:
    return backup_db.parse_paired_snapshot_manifest(
        json.dumps(_paired_manifest_data()).encode(),
        expected_manifest_key=(
            "database/snapshots/0123456789abcdef0123456789abcdef/database.manifest.json"
        ),
    )


def test_storage_reference_mapping_fails_closed_and_skips_non_app_keys() -> None:
    manifest = _parsed_paired_manifest()
    with pytest.raises(backup_db.BackupArtifactError, match="does not bind"):
        backup_db._build_storage_reference_url_map(
            replace(manifest, source_storage_public_base_url=None),
            "restore-run",
            "https://target.example.test/uploads",
        )

    unsupported_key_manifest = replace(
        manifest,
        objects=(replace(manifest.objects[0], source_key="unsupported%key"),),
    )
    assert (
        backup_db._build_storage_reference_url_map(
            unsupported_key_manifest,
            "restore-run",
            "https://target.example.test/uploads",
        )
        == {}
    )


def test_storage_reference_mapping_rejects_duplicate_application_urls() -> None:
    manifest = _parsed_paired_manifest()
    with pytest.raises(backup_db.BackupArtifactError, match="duplicate application"):
        backup_db._build_storage_reference_url_map(
            replace(manifest, objects=manifest.objects * 2),
            "restore-run",
            "https://target.example.test/uploads",
        )


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


@pytest.mark.parametrize("value", [None, 1, "", "x" * 1025, "line\nfeed"])
def test_snapshot_version_ids_return_none_or_reject_invalid_values(value: Any) -> None:
    if value is None:
        assert backup_db._manifest_version_id(value, label="test") is None
        return

    with pytest.raises(backup_db.BackupArtifactError, match="test is invalid"):
        backup_db._manifest_version_id(value, label="test")


@pytest.mark.parametrize(
    "value",
    [None, 1, "", "x" * 257, "line\rfeed", "line\nfeed"],
)
def test_snapshot_etags_reject_invalid_values(value: Any) -> None:
    with pytest.raises(backup_db.BackupArtifactError, match="test is invalid"):
        backup_db._manifest_etag(value, label="test")


@pytest.mark.parametrize("value", [1, "x" * 2049, "line\rfeed", "line\nfeed"])
def test_snapshot_headers_reject_invalid_values(value: Any) -> None:
    with pytest.raises(backup_db.BackupArtifactError, match="test is invalid"):
        backup_db._manifest_header(value, label="test")


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (None, "invalid"),
        ("not-a-timestamp", "invalid"),
        ("2026-10-01T01:00:00+01:00", "must be UTC"),
    ],
)
def test_snapshot_timestamps_reject_invalid_values(value: Any, message: str) -> None:
    with pytest.raises(backup_db.BackupArtifactError, match=message):
        backup_db._parse_utc_timestamp(value, label="test timestamp")


def test_restore_object_prefix_rejects_non_string_values() -> None:
    with pytest.raises(backup_db.BackupArtifactError, match="prefix is invalid"):
        backup_db._validate_object_prefix(1)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", True),
        ("schema_version", 1),
        ("snapshot_id", "not-a-snapshot-id"),
        ("quiescence_confirmed_at", None),
        ("quiescence_confirmed_at", "not-a-timestamp"),
        ("quiescence_confirmed_at", "2026-10-01T01:00:00+01:00"),
        ("source_object_bucket", "bad//bucket"),
        ("objects", None),
        ("objects", [None]),
    ],
)
def test_paired_snapshot_manifest_rejects_invalid_top_level_values(
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


def test_paired_snapshot_manifest_rejects_bad_key_json_size_and_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = "database/snapshots/0123456789abcdef0123456789abcdef/database.manifest.json"
    with pytest.raises(backup_db.BackupArtifactError, match="suffix"):
        backup_db.parse_paired_snapshot_manifest(
            b"{}", expected_manifest_key="snapshot.json"
        )
    with pytest.raises(backup_db.BackupArtifactError, match="valid JSON"):
        backup_db.parse_paired_snapshot_manifest(b"\xff", expected_manifest_key=key)

    original_maximum = backup_db.PAIRED_SNAPSHOT_MANIFEST_MAX_BYTES
    monkeypatch.setattr(backup_db, "PAIRED_SNAPSHOT_MANIFEST_MAX_BYTES", 1)
    with pytest.raises(backup_db.BackupArtifactError, match="too large"):
        backup_db.parse_paired_snapshot_manifest(b"{}", expected_manifest_key=key)

    monkeypatch.setattr(
        backup_db,
        "PAIRED_SNAPSHOT_MANIFEST_MAX_BYTES",
        original_maximum,
    )
    data = _paired_manifest_data()
    del data["database_archive_etag"]
    with pytest.raises(backup_db.BackupArtifactError, match="fields"):
        backup_db.parse_paired_snapshot_manifest(
            json.dumps(data).encode(), expected_manifest_key=key
        )


def test_legacy_paired_manifest_parses_but_does_not_claim_source_url_ownership() -> (
    None
):
    key = "database/snapshots/0123456789abcdef0123456789abcdef/database.manifest.json"
    data = _paired_manifest_data()
    data["schema_version"] = backup_db.LEGACY_PAIRED_SNAPSHOT_SCHEMA_VERSION
    del data["source_storage_public_base_url"]

    manifest = backup_db.parse_paired_snapshot_manifest(
        json.dumps(data).encode(), expected_manifest_key=key
    )

    assert manifest.schema_version == backup_db.LEGACY_PAIRED_SNAPSHOT_SCHEMA_VERSION
    assert manifest.source_storage_public_base_url is None
    serialized = json.loads(manifest.to_json_bytes())
    assert "source_storage_public_base_url" not in serialized


def test_paired_snapshot_manifest_rejects_snapshot_root_mismatch() -> None:
    data = _paired_manifest_data()
    data["database"]["artifact_key"] = (
        "database/snapshots/11111111111111111111111111111111/database.dump"
    )
    expected_key = backup_db.manifest_key(data["database"]["artifact_key"])

    with pytest.raises(backup_db.BackupArtifactError, match="does not match its id"):
        backup_db.parse_paired_snapshot_manifest(
            json.dumps(data).encode(), expected_manifest_key=expected_key
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_key", "bad//key"),
        ("source_version_id", "bad\nversion"),
        ("size_bytes", True),
        ("size_bytes", -1),
        ("sha256", "not-a-checksum"),
        ("archive_key", "database/snapshots/run/objects/wrong.blob"),
        ("archive_version_id", "bad\nversion"),
        ("archive_etag", "bad\netag"),
        ("content_type", "bad\nheader"),
    ],
)
def test_paired_snapshot_manifest_rejects_invalid_object_values(
    field: str, value: Any
) -> None:
    data = _paired_manifest_data()
    data["objects"][0][field] = value

    with pytest.raises(backup_db.BackupArtifactError):
        backup_db.parse_paired_snapshot_manifest(
            json.dumps(data).encode(),
            expected_manifest_key=(
                "database/snapshots/0123456789abcdef0123456789abcdef/database.manifest.json"
            ),
        )


def test_paired_snapshot_manifest_rejects_object_inventory_over_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(backup_db, "MAX_SNAPSHOT_OBJECTS", 0)
    data = _paired_manifest_data()

    with pytest.raises(backup_db.BackupArtifactError, match="inventory is invalid"):
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
        "chat/duplicate.bin": (b"synthetic chat object", None),
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
        "chat/duplicate.bin": None,
        "users/42/avatar.png": "source-version-7",
    }
    archive_by_source = {
        entry.source_key: entry.archive_key for entry in manifest.objects
    }
    assert archive_by_source["chat/file.bin"] == archive_by_source["chat/duplicate.bin"]
    assert len({entry.archive_key for entry in manifest.objects}) == 2
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
async def test_paired_snapshot_opens_backup_client_after_source_inventory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FakeS3()
    entered_buckets: list[str] = []
    exited_buckets: list[str] = []
    backup_entry_inventory_events: list[list[tuple[str, str, str]]] = []

    class ClientContext:
        def __init__(self, settings: backup_db.S3Settings) -> None:
            self.settings = settings

        async def __aenter__(self) -> FakeS3:
            entered_buckets.append(self.settings.bucket)
            if self.settings.bucket == "synthetic-backups":
                backup_entry_inventory_events.append(list(store.events))
            return store

        async def __aexit__(self, *_args: Any) -> bool:
            exited_buckets.append(self.settings.bucket)
            return False

    monkeypatch.setattr(backup_db, "s3_client", ClientContext)
    monkeypatch.setattr(
        backup_db,
        "source_database_metadata",
        lambda _url: ("synthetic_source", ("synthetic_revision",)),
    )
    monkeypatch.setattr(
        backup_db,
        "dump_database",
        lambda _url, path: path.write_bytes(b"synthetic database archive"),
    )

    manifest_key = await backup_db.backup_paired_snapshot_to_s3(
        "postgresql://synthetic@localhost/source",
        _s3_settings("synthetic-backups"),
        _s3_settings("synthetic-uploads"),
        confirm_source_quiesced=True,
    )

    manifest = backup_db.parse_paired_snapshot_manifest(
        store.objects[("synthetic-backups", manifest_key)],
        expected_manifest_key=manifest_key,
    )
    assert entered_buckets == ["synthetic-uploads", "synthetic-backups"]
    assert exited_buckets == ["synthetic-backups", "synthetic-uploads"]
    assert backup_entry_inventory_events == [[("list", "synthetic-uploads", "current")]]
    assert manifest.objects == ()
    assert store.objects[("synthetic-backups", manifest.database.artifact_key)]


@pytest.mark.asyncio
async def test_paired_snapshot_closes_source_client_if_backup_client_entry_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FakeS3()
    lifecycle: list[tuple[str, str]] = []

    class ClientContext:
        def __init__(self, settings: backup_db.S3Settings) -> None:
            self.settings = settings

        async def __aenter__(self) -> FakeS3:
            lifecycle.append(("enter", self.settings.bucket))
            if self.settings.bucket == "synthetic-backups":
                raise OSError("synthetic backup client entry failure")
            return store

        async def __aexit__(
            self, exc_type: type[BaseException] | None, *_args: Any
        ) -> bool:
            lifecycle.append(
                ("exit-error" if exc_type else "exit", self.settings.bucket)
            )
            return False

    monkeypatch.setattr(backup_db, "s3_client", ClientContext)
    monkeypatch.setattr(
        backup_db,
        "source_database_metadata",
        lambda _url: ("synthetic_source", ("synthetic_revision",)),
    )
    monkeypatch.setattr(
        backup_db,
        "dump_database",
        lambda _url, path: path.write_bytes(b"synthetic database archive"),
    )

    with pytest.raises(OSError, match="backup client entry failure"):
        await backup_db.backup_paired_snapshot_to_s3(
            "postgresql://synthetic@localhost/source",
            _s3_settings("synthetic-backups"),
            _s3_settings("synthetic-uploads"),
            confirm_source_quiesced=True,
        )

    assert lifecycle == [
        ("enter", "synthetic-uploads"),
        ("enter", "synthetic-backups"),
        ("exit-error", "synthetic-uploads"),
    ]


@pytest.mark.asyncio
async def test_paired_snapshot_does_not_enter_backup_client_if_inventory_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FakeS3()
    store.fail_inventory.add("current")
    lifecycle: list[tuple[str, str]] = []

    class ClientContext:
        def __init__(self, settings: backup_db.S3Settings) -> None:
            self.settings = settings

        async def __aenter__(self) -> FakeS3:
            lifecycle.append(("enter", self.settings.bucket))
            return store

        async def __aexit__(
            self, exc_type: type[BaseException] | None, *_args: Any
        ) -> bool:
            lifecycle.append(
                ("exit-error" if exc_type else "exit", self.settings.bucket)
            )
            return False

    monkeypatch.setattr(backup_db, "s3_client", ClientContext)
    monkeypatch.setattr(
        backup_db,
        "source_database_metadata",
        lambda _url: ("synthetic_source", ("synthetic_revision",)),
    )
    monkeypatch.setattr(
        backup_db,
        "dump_database",
        lambda _url, path: path.write_bytes(b"synthetic database archive"),
    )

    with pytest.raises(
        backup_db.BackupArtifactError,
        match="Unable to inventory application S3 objects",
    ):
        await backup_db.backup_paired_snapshot_to_s3(
            "postgresql://synthetic@localhost/source",
            _s3_settings("synthetic-backups"),
            _s3_settings("synthetic-uploads"),
            confirm_source_quiesced=True,
        )

    assert lifecycle == [
        ("enter", "synthetic-uploads"),
        ("exit-error", "synthetic-uploads"),
    ]


@pytest.mark.asyncio
async def test_paired_snapshot_closes_entered_clients_in_reverse_order_on_body_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FakeS3()
    lifecycle: list[tuple[str, str]] = []

    class ClientContext:
        def __init__(self, settings: backup_db.S3Settings) -> None:
            self.settings = settings

        async def __aenter__(self) -> FakeS3:
            lifecycle.append(("enter", self.settings.bucket))
            return store

        async def __aexit__(
            self, exc_type: type[BaseException] | None, *_args: Any
        ) -> bool:
            lifecycle.append(
                ("exit-error" if exc_type else "exit", self.settings.bucket)
            )
            return False

    monkeypatch.setattr(backup_db, "s3_client", ClientContext)
    monkeypatch.setattr(
        backup_db,
        "source_database_metadata",
        lambda _url: ("synthetic_source", ("synthetic_revision",)),
    )
    monkeypatch.setattr(
        backup_db,
        "dump_database",
        lambda _url, path: path.write_bytes(b"synthetic database archive"),
    )

    async def failed_publish(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("synthetic manifest publish failure")

    monkeypatch.setattr(backup_db, "_publish_paired_manifest", failed_publish)
    with pytest.raises(OSError, match="manifest publish failure"):
        await backup_db.backup_paired_snapshot_to_s3(
            "postgresql://synthetic@localhost/source",
            _s3_settings("synthetic-backups"),
            _s3_settings("synthetic-uploads"),
            confirm_source_quiesced=True,
        )

    assert lifecycle == [
        ("enter", "synthetic-uploads"),
        ("enter", "synthetic-backups"),
        ("exit-error", "synthetic-backups"),
        ("exit-error", "synthetic-uploads"),
    ]


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
            storage_s3_base_url="https://cdn.example.test/uploads",
        ),
    )

    settings = backup_db.storage_s3_settings_from_environment()

    assert settings.endpoint_url == "https://objects.example.test"
    assert settings.bucket == "synthetic-uploads"
    assert settings.region == "eu-test-1"
    assert settings.access_key_id == "synthetic-access"
    assert settings.secret_access_key == marker
    assert settings.public_base_url == "https://cdn.example.test/uploads"
    assert marker not in repr(settings)


def test_snapshot_cli_requires_explicit_quiescence_confirmation() -> None:
    with pytest.raises(backup_db.BackupArtifactError, match="Invalid command-line"):
        backup_db.build_parser().parse_args(["snapshot"])


def test_snapshot_cli_uses_environment_and_reports_manifest_key(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    backup_settings = _s3_settings("synthetic-backups")
    source_settings = _s3_settings("synthetic-uploads")
    calls: list[tuple[Any, ...]] = []

    async def fake_snapshot(*args: Any, **kwargs: Any) -> str:
        calls.append((*args, kwargs))
        return "database/snapshots/synthetic/database.manifest.json"

    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://synthetic@localhost/synthetic_source"
    )
    monkeypatch.setattr(
        backup_db, "s3_settings_from_environment", lambda: backup_settings
    )
    monkeypatch.setattr(
        backup_db, "storage_s3_settings_from_environment", lambda: source_settings
    )
    monkeypatch.setattr(backup_db, "backup_paired_snapshot_to_s3", fake_snapshot)

    result = backup_db.main(["snapshot", "--confirm-source-quiesced"])

    output = capsys.readouterr()
    assert result == 0
    assert calls == [
        (
            "postgresql://synthetic@localhost/synthetic_source",
            backup_settings,
            source_settings,
            {"confirm_source_quiesced": True},
        )
    ]
    assert "database/snapshots/synthetic/database.manifest.json" in output.out
    assert output.err == ""


def test_restore_snapshot_cli_requires_an_explicit_target_public_base_url() -> None:
    with pytest.raises(backup_db.BackupArtifactError, match="Invalid command-line"):
        backup_db.build_parser().parse_args(
            [
                "restore-snapshot",
                "--manifest-key",
                "database/snapshots/run/database.manifest.json",
                "--target-database",
                "restore_target",
                "--objects-target-bucket",
                "restore-objects",
                "--objects-target-prefix",
                "restore-run",
            ]
        )


def test_restore_snapshot_cli_reads_admin_url_from_environment_and_passes_prefix(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    secret = (
        "synthetic-admin-secret"  # pragma: allowlist secret -- synthetic test fixture
    )
    backup_settings = _s3_settings("synthetic-backups")
    storage_settings = _s3_settings("synthetic-restore")
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    async def fake_restore(*args: Any, **kwargs: Any) -> None:
        calls.append((args, kwargs))

    monkeypatch.setenv(
        "BACKUP_RESTORE_ADMIN_DATABASE_URL",
        f"postgresql://restore_admin:{secret}@localhost/postgres",
    )
    monkeypatch.setattr(
        backup_db, "s3_settings_from_environment", lambda: backup_settings
    )
    monkeypatch.setattr(
        backup_db, "storage_s3_settings_from_environment", lambda: storage_settings
    )
    monkeypatch.setattr(backup_db, "restore_paired_snapshot_from_s3", fake_restore)

    result = backup_db.main(
        [
            "restore-snapshot",
            "--manifest-key",
            "database/snapshots/run/database.manifest.json",
            "--target-database",
            "restore_target",
            "--objects-target-bucket",
            "synthetic-restore",
            "--objects-target-prefix",
            "",
            "--objects-target-public-base-url",
            TARGET_PUBLIC_BASE_URL,
        ]
    )

    output = capsys.readouterr()
    assert result == 0
    assert calls == [
        (
            (
                "database/snapshots/run/database.manifest.json",
                "restore_target",
                f"postgresql://restore_admin:{secret}@localhost/postgres",
                backup_settings,
                storage_settings,
                "synthetic-restore",
                "",
            ),
            {"target_public_base_url": TARGET_PUBLIC_BASE_URL},
        )
    ]
    assert secret not in output.out
    assert secret not in output.err


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


def _append_paired_archive_object(
    store: FakeS3,
    manifest_key: str,
    *,
    source_key: str,
    content: bytes,
) -> str:
    backup_bucket = "synthetic-backups"
    manifest_identity = (backup_bucket, manifest_key)
    manifest_data = json.loads(store.objects[manifest_identity])
    digest = hashlib.sha256(content).hexdigest()
    archive_key = (
        f"database/snapshots/{manifest_data['snapshot_id']}/objects/{digest}.blob"
    )
    archive_identity = (backup_bucket, archive_key)
    store.objects[archive_identity] = content
    store.etags[archive_identity] = store._etag(content)
    manifest_data["objects"].append(
        {
            "source_key": source_key,
            "source_version_id": None,
            "archive_key": archive_key,
            "archive_version_id": None,
            "archive_etag": store.etags[archive_identity],
            "size_bytes": len(content),
            "sha256": digest,
            "content_type": "image/jpeg",
            "content_encoding": None,
            "cache_control": None,
            "content_disposition": None,
        }
    )
    payload = json.dumps(manifest_data, sort_keys=True, separators=(",", ":"))
    manifest_bytes = payload.encode() + b"\n"
    store.objects[manifest_identity] = manifest_bytes
    store.etags[manifest_identity] = store._etag(manifest_bytes)
    return archive_key


RESTORE_PREFIX = "restore-run"
SOURCE_PUBLIC_BASE_URL = "https://s3.example.test/synthetic-uploads"
TARGET_PUBLIC_BASE_URL = "https://s3.example.test/synthetic-restore"


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


class FakeQueryResult:
    def __init__(self, rows: list[tuple[Any, ...]], rowcount: int = 0) -> None:
        self.rows = rows
        self.rowcount = rowcount

    def fetchone(self) -> tuple[Any, ...] | None:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self.rows


class FakeStorageReferenceCursor:
    def __init__(self, database: FakeStorageReferenceDatabase) -> None:
        self.database = database

    def __enter__(self) -> FakeStorageReferenceCursor:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def execute(self, query: Any, params: tuple[Any, ...] = ()) -> FakeQueryResult:
        return self.database.execute(query, params)

    def executemany(self, query: Any, params_seq: Any) -> None:
        self.database.executemany(query, params_seq)


class FakeStorageReferenceDatabase:
    """Small PostgreSQL boundary fake for the restore reference transaction."""

    def __init__(self, *, source_base_url: str) -> None:
        self.source_prefix = f"{source_base_url.rstrip('/')}/"
        self.revision = "synthetic_revision"
        self.reference_columns = {
            ("user_profiles", "avatar_url"),
            ("user_profiles", "cover_url"),
            ("stories", "cover_url"),
            ("events", "image_url"),
            ("event_files", "file_url"),
            ("news", "image_url"),
            ("attachments", "url"),
        }
        self.storage_reference_max_lengths: dict[tuple[str, str], int | None] = {
            ("user_profiles", "avatar_url"): 2048,
            ("user_profiles", "cover_url"): 2048,
            ("stories", "cover_url"): None,
            ("events", "image_url"): None,
            ("event_files", "file_url"): None,
            ("news", "image_url"): None,
            ("attachments", "url"): None,
        }
        self.storage_reference_types: dict[tuple[str, str], str] = {
            key: "character varying" for key in self.storage_reference_max_lengths
        }
        self.outbox_types: dict[tuple[str, str], str] = {
            ("stored_events", "payload"): "json",
            ("stored_events", "processed_at"): "timestamp with time zone",
            ("failed_outbox_events", "payload"): "json",
            ("failed_outbox_events", "resolved_at"): "timestamp with time zone",
        }
        self.missing_catalog_columns: set[tuple[str, str]] = set()
        self.references: dict[tuple[str, str], list[str | None]] = {
            ("user_profiles", "avatar_url"): [],
            ("user_profiles", "cover_url"): [],
            ("stories", "cover_url"): [],
            ("events", "image_url"): [],
            ("event_files", "file_url"): [],
            ("news", "image_url"): [],
            ("attachments", "url"): [],
        }
        self.pending_stored_event_payloads: list[str] = []
        self.stored_event_status = "pending"
        self.stored_event_processed_at: str | None = None
        self.pending_failed_event_payloads: list[str] = []
        self.pending_failed_event_resolved_at: str | None = None
        self.url_map: dict[str, str] = {}
        self.fail_on_update_table: str | None = None
        self._references_before_transaction: (
            dict[tuple[str, str], list[str | None]] | None
        ) = None
        self._url_map_before_transaction: dict[str, str] | None = None
        self.committed = False
        self.rolled_back = False
        self.executed: list[tuple[str, tuple[Any, ...]]] = []

    def __enter__(self) -> FakeStorageReferenceDatabase:
        self._references_before_transaction = {
            key: list(values) for key, values in self.references.items()
        }
        self._url_map_before_transaction = dict(self.url_map)
        return self

    def __exit__(self, exc_type: Any, *_args: Any) -> None:
        self.rolled_back = exc_type is not None
        self.committed = exc_type is None
        if exc_type is not None and self._references_before_transaction is not None:
            self.references = self._references_before_transaction
        if exc_type is not None and self._url_map_before_transaction is not None:
            self.url_map = self._url_map_before_transaction

    def execute(self, query: Any, params: tuple[Any, ...] = ()) -> FakeQueryResult:
        sql = str(query)
        self.executed.append((sql, params))
        if "FROM alembic_version" in sql:
            return FakeQueryResult([(self.revision,)])
        if "FROM information_schema.columns" in sql:
            rows = [
                (
                    table,
                    column,
                    self.storage_reference_types[(table, column)],
                    self.storage_reference_max_lengths[(table, column)],
                )
                for table, column in self.reference_columns
            ]
            rows.extend(
                (table, column, data_type, None)
                for (table, column), data_type in self.outbox_types.items()
            )
            rows.extend([("stored_events", "status", "character varying", 20)])
            rows = [
                row
                for row in rows
                if (row[0], row[1]) not in self.missing_catalog_columns
            ]
            return FakeQueryResult(rows)
        if "FROM stored_events" in sql:
            return FakeQueryResult(
                [
                    (payload,)
                    for payload in self.pending_stored_event_payloads
                    if self.stored_event_processed_at is None
                    and self._payload_contains_source_url(sql, payload)
                ]
            )
        if "FROM failed_outbox_events" in sql:
            return FakeQueryResult(
                [
                    (payload,)
                    for payload in self.pending_failed_event_payloads
                    if self.pending_failed_event_resolved_at is None
                    and self._payload_contains_source_url(sql, payload)
                ]
            )
        if sql.startswith("CREATE TEMP TABLE"):
            return FakeQueryResult([])
        if sql.startswith("SELECT DISTINCT"):
            fields = sql.split()
            key = (fields[4], fields[2])
            prefix = params[0]
            return FakeQueryResult(
                [
                    (value,)
                    for value in self.references.get(key, [])
                    if value is not None and value.startswith(prefix)
                ]
            )
        if sql.startswith("UPDATE"):
            fields = sql.split()
            table, column = fields[1], fields[5]
            if table == self.fail_on_update_table:
                raise OSError("synthetic SQL failure")
            rows = self.references[(table, column)]
            changed = 0
            for index, value in enumerate(rows):
                if value in self.url_map:
                    rows[index] = self.url_map[value]
                    changed += 1
            return FakeQueryResult([], rowcount=changed)
        raise AssertionError(f"Unexpected storage reference query: {sql}")

    def _payload_contains_source_url(self, sql: str, payload: str) -> bool:
        if "jsonb_path_query" not in sql:
            return self.source_prefix in payload

        def strings(value: Any) -> list[str]:
            if isinstance(value, str):
                return [value]
            if isinstance(value, dict):
                return [item for child in value.values() for item in strings(child)]
            if isinstance(value, list):
                return [item for child in value for item in strings(child)]
            return []

        return any(self.source_prefix in item for item in strings(json.loads(payload)))

    def cursor(self) -> FakeStorageReferenceCursor:
        return FakeStorageReferenceCursor(self)

    def executemany(self, query: Any, params_seq: Any) -> None:
        assert "INSERT INTO" in str(query)
        self.url_map.update(dict(params_seq))


def _empty_restore_reference_connect(_dsn: str) -> FakeStorageReferenceDatabase:
    return FakeStorageReferenceDatabase(source_base_url=SOURCE_PUBLIC_BASE_URL)


def test_restore_storage_schema_accepts_postgresql_unbounded_reference_columns() -> (
    None
):
    database = _empty_restore_reference_connect("unused")
    database.storage_reference_types[("stories", "cover_url")] = "text"

    lengths = backup_db._validate_restored_storage_schema(
        database, ("synthetic_revision",)
    )

    assert lengths[("user_profiles", "avatar_url")] == 2048
    assert lengths[("stories", "cover_url")] is None


@pytest.mark.parametrize(
    ("column", "data_type", "maximum_length", "outbox_column", "outbox_type"),
    [
        (("stories", "cover_url"), "integer", None, None, None),
        (("user_profiles", "avatar_url"), "character varying", 0, None, None),
        (("stories", "cover_url"), "text", 1024, None, None),
        (
            None,
            None,
            None,
            ("stored_events", "processed_at"),
            "character varying",
        ),
    ],
)
def test_restore_storage_schema_rejects_incompatible_reference_catalog(
    column: tuple[str, str] | None,
    data_type: str | None,
    maximum_length: int | None,
    outbox_column: tuple[str, str] | None,
    outbox_type: str | None,
) -> None:
    database = _empty_restore_reference_connect("unused")
    if column is not None:
        database.storage_reference_types[column] = data_type or ""
        database.storage_reference_max_lengths[column] = maximum_length
    if outbox_column is not None:
        database.outbox_types[outbox_column] = outbox_type or ""

    with pytest.raises(backup_db.BackupArtifactError, match="incompatible"):
        backup_db._validate_restored_storage_schema(database, ("synthetic_revision",))


def test_restore_storage_schema_rejects_missing_outbox_reference_column() -> None:
    database = _empty_restore_reference_connect("unused")
    database.missing_catalog_columns.add(("failed_outbox_events", "resolved_at"))

    with pytest.raises(backup_db.BackupArtifactError, match="outbox reference checks"):
        backup_db._validate_restored_storage_schema(database, ("synthetic_revision",))


def test_restore_storage_reference_transaction_requires_manifest_source_base() -> None:
    manifest = replace(_parsed_paired_manifest(), source_storage_public_base_url=None)

    with pytest.raises(backup_db.BackupArtifactError, match="does not bind"):
        backup_db._rebase_restored_storage_references(
            _empty_restore_reference_connect("unused"),
            manifest,
            "restore-run",
            "https://target.example.test/uploads",
            {},
        )


@pytest.mark.parametrize(
    ("table", "payloads_attribute"),
    [
        ("stored_events", "pending_stored_event_payloads"),
        ("failed_outbox_events", "pending_failed_event_payloads"),
    ],
)
def test_restore_outbox_guard_decodes_unicode_and_escaped_nested_urls(
    table: str, payloads_attribute: str
) -> None:
    source_base_url = "https://source.example.test/upløads"
    source_url = f"{source_base_url}/events/cover.png"
    payload = json.dumps(
        {"nested": {"attachments": [{"url": source_url}]}}, ensure_ascii=True
    ).replace("/", "\\/")
    assert "ø" not in payload
    assert "\\/" in payload

    manifest = replace(
        _parsed_paired_manifest(), source_storage_public_base_url=source_base_url
    )
    database = FakeStorageReferenceDatabase(source_base_url=source_base_url)
    getattr(database, payloads_attribute).append(payload)
    column_lengths = backup_db._validate_restored_storage_schema(
        database, ("synthetic_revision",)
    )

    with pytest.raises(backup_db.BackupArtifactError, match="unresolved outbox events"):
        backup_db._rebase_restored_storage_references(
            database,
            manifest,
            "restore-run",
            "https://target.example.test/restored",
            column_lengths,
        )

    guard_query = next(
        sql for sql, _params in database.executed if f"FROM {table}" in sql
    )
    guard_params = next(
        params for sql, params in database.executed if f"FROM {table}" in sql
    )
    assert "jsonb_path_query" in guard_query
    assert "payload::text" not in guard_query
    assert guard_params == (f"{source_base_url}/",)


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
async def test_restore_paired_snapshot_rejects_non_manifest_key_before_clients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def forbidden_client(_settings: backup_db.S3Settings):
        pytest.fail("non-manifest key reached object storage")

    monkeypatch.setattr(backup_db, "s3_client", forbidden_client)

    with pytest.raises(backup_db.BackupArtifactError, match="manifest object key"):
        await backup_db.restore_paired_snapshot_from_s3(
            "database/snapshots/synthetic/database.dump",
            "restore_acceptance",
            "postgresql://synthetic@localhost/admin",
            _s3_settings("synthetic-backups"),
            _s3_settings("synthetic-restore"),
            "synthetic-restore",
            RESTORE_PREFIX,
            target_public_base_url=_target_public_base_url("synthetic-restore"),
            database_reference_connect=_empty_restore_reference_connect,
        )


@pytest.mark.parametrize(
    ("configured_bucket", "target_public_base_url", "message"),
    [
        (
            "synthetic-uploads",
            TARGET_PUBLIC_BASE_URL,
            "must match the configured target application bucket",
        ),
        (
            "synthetic-restore",
            "https://wrong.example.test/uploads",
            "must match the configured application storage URL",
        ),
    ],
)
@pytest.mark.asyncio
async def test_restore_requires_target_storage_configuration_to_match_cli_target(
    monkeypatch: pytest.MonkeyPatch,
    configured_bucket: str,
    target_public_base_url: str,
    message: str,
) -> None:
    async def forbidden_client(_settings: backup_db.S3Settings):
        pytest.fail("mismatched target storage settings reached object storage")

    monkeypatch.setattr(backup_db, "s3_client", forbidden_client)

    with pytest.raises(backup_db.BackupArtifactError, match=message):
        await backup_db.restore_paired_snapshot_from_s3(
            "database/snapshots/run/database.manifest.json",
            "restore_acceptance",
            "postgresql://synthetic@localhost/admin",
            _s3_settings("synthetic-backups"),
            _s3_settings(configured_bucket),
            "synthetic-restore",
            RESTORE_PREFIX,
            target_public_base_url=target_public_base_url,
            database_connect=lambda *_args, **_kwargs: pytest.fail(
                "mismatched target settings reached database preflight"
            ),
            database_reference_connect=_empty_restore_reference_connect,
        )


@pytest.mark.asyncio
async def test_restore_paired_snapshot_preflights_then_restores_into_empty_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FakeS3()
    manifest_key, database_bytes, object_bytes, source_key = _seed_paired_backup(store)
    events: list[str] = []
    source_identity = ("synthetic-uploads", source_key)
    store.objects[source_identity] = b"unchanged source object"
    store.etags[source_identity] = store._etag(store.objects[source_identity])
    unrelated_target_identity = ("synthetic-restore", "operator-data/keep.txt")
    store.objects[unrelated_target_identity] = b"unrelated target data"
    store.etags[unrelated_target_identity] = store._etag(
        store.objects[unrelated_target_identity]
    )
    neighboring_prefix_identity = (
        "synthetic-restore",
        f"{RESTORE_PREFIX}ner/current.txt",
    )
    store.objects[neighboring_prefix_identity] = b"neighboring prefix data"
    store.etags[neighboring_prefix_identity] = store._etag(
        store.objects[neighboring_prefix_identity]
    )
    store.hidden_versions["synthetic-restore"] = [
        f"{RESTORE_PREFIX}ner/previous-version.bin"
    ]
    store.hidden_delete_markers["synthetic-restore"] = [
        f"{RESTORE_PREFIX}ner/previously-deleted.bin"
    ]
    store.pending_uploads["synthetic-restore"] = [f"{RESTORE_PREFIX}ner/unfinished.bin"]

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
        _s3_settings("synthetic-restore"),
        "synthetic-restore",
        RESTORE_PREFIX,
        database_connect=fake_connect,
        target_public_base_url=_target_public_base_url("synthetic-restore"),
        database_reference_connect=_empty_restore_reference_connect,
    )

    assert result.snapshot_id == "0123456789abcdef0123456789abcdef"
    assert restore_calls
    target_key = f"{RESTORE_PREFIX}/{source_key}"
    assert store.objects[("synthetic-restore", target_key)] == object_bytes
    assert (
        store.headers[("synthetic-restore", target_key)]["ContentType"] == "image/png"
    )
    assert store.objects[source_identity] == b"unchanged source object"
    assert store.objects[unrelated_target_identity] == b"unrelated target data"
    assert store.objects[neighboring_prefix_identity] == b"neighboring prefix data"
    assert store.hidden_versions["synthetic-restore"] == [
        f"{RESTORE_PREFIX}ner/previous-version.bin"
    ]
    assert store.hidden_delete_markers["synthetic-restore"] == [
        f"{RESTORE_PREFIX}ner/previously-deleted.bin"
    ]
    assert store.pending_uploads["synthetic-restore"] == [
        f"{RESTORE_PREFIX}ner/unfinished.bin"
    ]
    assert store.inventory_requests == [
        {
            "operation": "list_objects_v2",
            "Bucket": "synthetic-restore",
            "MaxKeys": 1,
            "Prefix": f"{RESTORE_PREFIX}/",
            "PrefixSupplied": True,
        },
        {
            "operation": "list_object_versions",
            "Bucket": "synthetic-restore",
            "MaxKeys": 1,
            "Prefix": f"{RESTORE_PREFIX}/",
            "PrefixSupplied": True,
        },
        {
            "operation": "list_multipart_uploads",
            "Bucket": "synthetic-restore",
            "MaxUploads": 1,
            "Prefix": f"{RESTORE_PREFIX}/",
            "PrefixSupplied": True,
        },
    ]
    assert events.index("database-preflight") < events.index("database-restored")
    assert events.index("database-restored") < next(
        index
        for index, event in enumerate(store.events)
        if event == ("put", "synthetic-restore", target_key)
    )
    assert not any(event[0] == "delete" for event in store.events)
    assert store.objects[("synthetic-backups", manifest_key)]


@pytest.mark.asyncio
async def test_restore_rebases_storage_references_that_app_can_read_from_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.storage import S3Storage

    store = FakeS3()
    manifest_key, database_bytes, object_bytes, source_key = _seed_paired_backup(store)
    source_url = f"{SOURCE_PUBLIC_BASE_URL}/{source_key}"
    target_key = f"{RESTORE_PREFIX}/{source_key}"
    target_url = f"{TARGET_PUBLIC_BASE_URL}/{target_key}"
    reference_database = FakeStorageReferenceDatabase(
        source_base_url=SOURCE_PUBLIC_BASE_URL
    )
    for table, column in sorted(reference_database.reference_columns):
        reference_database.references[(table, column)].append(source_url)
    reference_database.references[("news", "image_url")].append(
        "https://external.example.test/news/banner.png"
    )

    @asynccontextmanager
    async def fake_client(_settings: backup_db.S3Settings):
        yield store

    monkeypatch.setattr(backup_db, "s3_client", fake_client)

    def fake_restore(archive_path: Path, *_args: Any) -> None:
        assert archive_path.read_bytes() == database_bytes

    monkeypatch.setattr(backup_db, "restore_archive", fake_restore)
    database_dsns: list[str] = []

    def fake_reference_connect(_dsn: str) -> FakeStorageReferenceDatabase:
        database_dsns.append(_dsn)
        return reference_database

    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://synthetic@source.invalid/source_database"
    )

    await backup_db.restore_paired_snapshot_from_s3(
        manifest_key,
        "restore_acceptance",
        "postgresql://synthetic@localhost/admin",
        _s3_settings("synthetic-backups"),
        _s3_settings("synthetic-restore"),
        "synthetic-restore",
        RESTORE_PREFIX,
        target_public_base_url=TARGET_PUBLIC_BASE_URL,
        database_connect=lambda *_args, **_kwargs: FakeDatabaseConnection(),
        database_reference_connect=fake_reference_connect,
    )

    for table, column in reference_database.reference_columns:
        expected_urls = (
            [target_url, "https://external.example.test/news/banner.png"]
            if (table, column) == ("news", "image_url")
            else [target_url]
        )
        assert reference_database.references[(table, column)] == expected_urls
    assert reference_database.references[("news", "image_url")][1] == (
        "https://external.example.test/news/banner.png"
    )
    assert database_dsns == ["postgresql://synthetic@localhost/restore_acceptance"]
    app_storage = S3Storage(
        bucket="synthetic-restore",
        base_url=TARGET_PUBLIC_BASE_URL,
        client=store,
    )
    assert await app_storage.read_file(target_url) == object_bytes
    assert store.objects[("synthetic-backups", manifest_key)]


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        ("unknown-reference", "unresolved application storage reference"),
        ("stored-outbox", "unresolved outbox events"),
        ("failed-outbox", "unresolved outbox events"),
        ("revision", "Alembic revision"),
        ("missing-column", "missing an application storage reference column"),
        ("sql-update", "Unable to rebase restored application storage references"),
        ("column-overflow", "exceeds its database column limit"),
    ],
)
@pytest.mark.asyncio
async def test_restore_reference_failures_roll_back_and_never_report_success(
    monkeypatch: pytest.MonkeyPatch, failure: str, message: str
) -> None:
    store = FakeS3()
    manifest_key, _database_bytes, _object_bytes, source_key = _seed_paired_backup(
        store
    )
    target_base_url = TARGET_PUBLIC_BASE_URL
    if failure == "column-overflow":
        base_prefix = "https://s3.example.test/"
        target_base_url = base_prefix + "x" * (2048 - len(base_prefix))

    reference_database = FakeStorageReferenceDatabase(
        source_base_url=SOURCE_PUBLIC_BASE_URL
    )
    source_url = f"{SOURCE_PUBLIC_BASE_URL}/{source_key}"
    for table, column in reference_database.reference_columns:
        reference_database.references[(table, column)].append(source_url)
    if failure == "unknown-reference":
        reference_database.references[("stories", "cover_url")].append(
            f"{SOURCE_PUBLIC_BASE_URL}/unknown/not-in-manifest.png"
        )
    elif failure == "stored-outbox":
        reference_database.stored_event_status = "processed"
        reference_database.pending_stored_event_payloads.append(
            json.dumps({"url": source_url})
        )
    elif failure == "failed-outbox":
        reference_database.pending_failed_event_payloads.append(
            json.dumps({"url": source_url})
        )
    elif failure == "revision":
        reference_database.revision = "different_revision"
    elif failure == "missing-column":
        reference_database.reference_columns.remove(("stories", "cover_url"))
    elif failure == "sql-update":
        reference_database.fail_on_update_table = "events"

    @asynccontextmanager
    async def fake_client(_settings: backup_db.S3Settings):
        yield store

    monkeypatch.setattr(backup_db, "s3_client", fake_client)
    monkeypatch.setattr(backup_db, "restore_archive", lambda *_args: None)

    target_settings = _s3_settings("synthetic-restore", public_base_url=target_base_url)
    with pytest.raises(backup_db.BackupArtifactError, match=message):
        await backup_db.restore_paired_snapshot_from_s3(
            manifest_key,
            "restore_acceptance",
            "postgresql://synthetic@localhost/admin",
            _s3_settings("synthetic-backups"),
            target_settings,
            "synthetic-restore",
            RESTORE_PREFIX,
            target_public_base_url=target_base_url,
            database_connect=lambda *_args, **_kwargs: FakeDatabaseConnection(),
            database_reference_connect=lambda _dsn: reference_database,
        )

    assert reference_database.rolled_back is True
    assert reference_database.committed is False
    if failure == "stored-outbox":
        stored_event_query = next(
            sql
            for sql, _params in reference_database.executed
            if "FROM stored_events" in sql
        )
        assert reference_database.stored_event_status == "processed"
        assert reference_database.stored_event_processed_at is None
        assert "WHERE processed_at IS NULL" in stored_event_query
        assert "status" not in stored_event_query
    assert not any(
        event[0] == "put" and event[1] == "synthetic-restore" for event in store.events
    )
    if failure == "sql-update":
        assert all(
            values == [source_url] for values in reference_database.references.values()
        )


@pytest.mark.asyncio
async def test_legacy_paired_snapshot_is_rejected_before_target_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FakeS3()
    manifest_key, _database_bytes, _object_bytes, _source_key = _seed_paired_backup(
        store
    )
    manifest_identity = ("synthetic-backups", manifest_key)
    data = json.loads(store.objects[manifest_identity])
    data["schema_version"] = backup_db.LEGACY_PAIRED_SNAPSHOT_SCHEMA_VERSION
    del data["source_storage_public_base_url"]
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    store.objects[manifest_identity] = payload
    store.etags[manifest_identity] = store._etag(payload)

    @asynccontextmanager
    async def fake_client(_settings: backup_db.S3Settings):
        yield store

    monkeypatch.setattr(backup_db, "s3_client", fake_client)
    monkeypatch.setattr(
        backup_db,
        "restore_archive",
        lambda *_args: pytest.fail("legacy manifest reached database restore"),
    )

    with pytest.raises(backup_db.BackupArtifactError, match="schema-v3 snapshot"):
        await backup_db.restore_paired_snapshot_from_s3(
            manifest_key,
            "restore_acceptance",
            "postgresql://synthetic@localhost/admin",
            _s3_settings("synthetic-backups"),
            _s3_settings("synthetic-restore"),
            "synthetic-restore",
            RESTORE_PREFIX,
            target_public_base_url=TARGET_PUBLIC_BASE_URL,
            database_connect=lambda *_args, **_kwargs: pytest.fail(
                "legacy manifest reached database preflight"
            ),
            database_reference_connect=_empty_restore_reference_connect,
        )

    assert store.events == [("get", "synthetic-backups", manifest_key)]


@pytest.mark.asyncio
async def test_restore_with_empty_prefix_targets_original_keys_at_bucket_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FakeS3()
    manifest_key, database_bytes, object_bytes, source_key = _seed_paired_backup(store)
    events: list[str] = []

    @asynccontextmanager
    async def fake_client(_settings: backup_db.S3Settings):
        yield store

    monkeypatch.setattr(backup_db, "s3_client", fake_client)

    def fake_restore(
        archive_path: Path,
        _manifest: backup_db.BackupManifest,
        _admin_url: str,
        _target_database: str,
    ) -> None:
        assert archive_path.read_bytes() == database_bytes
        events.append("database-restored")

    monkeypatch.setattr(backup_db, "restore_archive", fake_restore)

    await backup_db.restore_paired_snapshot_from_s3(
        manifest_key,
        "restore_acceptance",
        "postgresql://synthetic@localhost/admin",
        _s3_settings("synthetic-backups"),
        _s3_settings("synthetic-restore-root"),
        "synthetic-restore-root",
        "",
        database_connect=lambda *_args, **_kwargs: FakeDatabaseConnection(
            events=events
        ),
        target_public_base_url=_target_public_base_url("synthetic-restore-root"),
        database_reference_connect=_empty_restore_reference_connect,
    )

    target_identity = ("synthetic-restore-root", source_key)
    assert store.objects[target_identity] == object_bytes
    assert ("synthetic-restore-root", f"/{source_key}") not in store.objects
    assert store.inventory_requests == [
        {
            "operation": "list_objects_v2",
            "Bucket": "synthetic-restore-root",
            "MaxKeys": 1,
            "Prefix": "",
            "PrefixSupplied": False,
        },
        {
            "operation": "list_object_versions",
            "Bucket": "synthetic-restore-root",
            "MaxKeys": 1,
            "Prefix": "",
            "PrefixSupplied": False,
        },
        {
            "operation": "list_multipart_uploads",
            "Bucket": "synthetic-restore-root",
            "MaxUploads": 1,
            "Prefix": "",
            "PrefixSupplied": False,
        },
    ]
    assert events == ["database-preflight", "database-restored"]


@pytest.mark.parametrize(
    "preexisting",
    [
        "current",
        "version",
        "delete-marker",
        "multipart",
        "inventory-unavailable",
        "root-current",
    ],
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
    target_prefix = "" if preexisting == "root-current" else RESTORE_PREFIX
    if preexisting in {"current", "root-current"}:
        operator_key = (
            f"{target_prefix}/operator-owned.txt"
            if target_prefix
            else "operator-owned.txt"
        )
        identity = (target_bucket, operator_key)
        store.objects[identity] = b"operator data"
        store.etags[identity] = store._etag(b"operator data")
    elif preexisting == "version":
        store.hidden_versions[target_bucket] = [
            f"{target_prefix}/previously-deleted.bin"
        ]
    elif preexisting == "delete-marker":
        store.hidden_delete_markers[target_bucket] = [
            f"{target_prefix}/deleted-by-operator.bin"
        ]
    elif preexisting == "inventory-unavailable":
        store.fail_inventory.add("versions")
    else:
        store.pending_uploads[target_bucket] = [f"{target_prefix}/unfinished.bin"]

    @asynccontextmanager
    async def fake_client(_settings: backup_db.S3Settings):
        yield store

    monkeypatch.setattr(backup_db, "s3_client", fake_client)
    database_events: list[str] = []
    monkeypatch.setattr(
        backup_db,
        "restore_archive",
        lambda *_args, **_kwargs: pytest.fail(
            "invalid target bucket reached DB restore"
        ),
    )

    with pytest.raises(backup_db.BackupArtifactError, match=r"prefix|bucket"):
        await backup_db.restore_paired_snapshot_from_s3(
            manifest_key,
            "restore_acceptance",
            "postgresql://synthetic@localhost/admin",
            _s3_settings("synthetic-backups"),
            _s3_settings(target_bucket),
            target_bucket,
            target_prefix,
            database_connect=lambda *_args, **_kwargs: FakeDatabaseConnection(
                events=database_events
            ),
            target_public_base_url=_target_public_base_url(target_bucket),
            database_reference_connect=_empty_restore_reference_connect,
        )

    assert database_events == ["database-preflight"]
    expected_operations = [
        "list_objects_v2",
        "list_object_versions",
        "list_multipart_uploads",
    ]
    if preexisting == "inventory-unavailable":
        expected_operations.pop()
    assert [request["operation"] for request in store.inventory_requests] == (
        expected_operations
    )
    assert all(
        request["Bucket"] == target_bucket
        and request["Prefix"] == (f"{target_prefix}/" if target_prefix else "")
        and request["PrefixSupplied"] is bool(target_prefix)
        for request in store.inventory_requests
    )
    assert not any(
        event[0] == "put" and event[1] == target_bucket for event in store.events
    )
    assert store.objects[("synthetic-backups", manifest_key)]
    if preexisting in {"current", "root-current"}:
        operator_key = (
            f"{target_prefix}/operator-owned.txt"
            if target_prefix
            else "operator-owned.txt"
        )
        assert store.objects[(target_bucket, operator_key)] == b"operator data"
    assert source_key not in {
        key for bucket, key in store.objects if bucket == target_bucket
    }


@pytest.mark.parametrize("artifact", ["database", "object"])
@pytest.mark.asyncio
async def test_restore_preflights_all_checksums_before_database_or_object_writes(
    monkeypatch: pytest.MonkeyPatch, artifact: str
) -> None:
    store = FakeS3()
    manifest_key, _database_bytes, _object_bytes, _source_key = _seed_paired_backup(
        store
    )
    manifest = backup_db.parse_paired_snapshot_manifest(
        store.objects[("synthetic-backups", manifest_key)],
        expected_manifest_key=manifest_key,
    )
    if artifact == "database":
        artifact_key = manifest.database.artifact_key
        original = _database_bytes
    else:
        artifact_key = manifest.objects[0].archive_key
        original = _object_bytes
    store.objects[("synthetic-backups", artifact_key)] = b"X" + original[1:]
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
            _s3_settings("synthetic-restore"),
            "synthetic-restore",
            RESTORE_PREFIX,
            database_connect=lambda *_args, **_kwargs: database_preflights.append(
                "called"
            ),
            target_public_base_url=_target_public_base_url("synthetic-restore"),
            database_reference_connect=_empty_restore_reference_connect,
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
        target_key = f"{RESTORE_PREFIX}/{source_key}"
        identity = (target_bucket, target_key)
        store.objects[identity] = content
        store.etags[identity] = store._etag(content)
        store.events.append(("foreign-write", target_bucket, target_key))

    monkeypatch.setattr(backup_db, "restore_archive", race_during_database_restore)

    with pytest.raises(backup_db.BackupArtifactError, match="incomplete"):
        await backup_db.restore_paired_snapshot_from_s3(
            manifest_key,
            "restore_acceptance",
            "postgresql://synthetic@localhost/admin",
            _s3_settings("synthetic-backups"),
            _s3_settings(target_bucket),
            target_bucket,
            RESTORE_PREFIX,
            database_connect=lambda *_args, **_kwargs: FakeDatabaseConnection(),
            target_public_base_url=_target_public_base_url(target_bucket),
            database_reference_connect=_empty_restore_reference_connect,
        )

    target_key = f"{RESTORE_PREFIX}/{source_key}"
    assert store.objects[(target_bucket, target_key)] == (
        b"operator object created after empty-bucket preflight"
    )
    assert not any(event[0] == "delete" for event in store.events)


@pytest.mark.asyncio
async def test_partial_restore_keeps_completed_target_objects_and_hides_write_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FakeS3()
    manifest_key, _database_bytes, first_object_bytes, first_source_key = (
        _seed_paired_backup(store)
    )
    second_object_bytes = b"synthetic second object"
    second_source_key = "users/43/avatar.png"
    _append_paired_archive_object(
        store,
        manifest_key,
        source_key=second_source_key,
        content=second_object_bytes,
    )
    backup_objects_before = {
        key: value
        for (bucket, key), value in store.objects.items()
        if bucket == "synthetic-backups"
    }
    target_bucket = "synthetic-restore"
    first_target_key = f"{RESTORE_PREFIX}/{first_source_key}"
    second_target_key = f"{RESTORE_PREFIX}/{second_source_key}"
    store.reject_put_keys.add((target_bucket, second_target_key))
    database_events: list[str] = []

    @asynccontextmanager
    async def fake_client(_settings: backup_db.S3Settings):
        yield store

    monkeypatch.setattr(backup_db, "s3_client", fake_client)

    def fake_restore(*_args: Any, **_kwargs: Any) -> None:
        database_events.append("database-restored")

    monkeypatch.setattr(backup_db, "restore_archive", fake_restore)

    with pytest.raises(backup_db.BackupArtifactError) as failure:
        await backup_db.restore_paired_snapshot_from_s3(
            manifest_key,
            "restore_acceptance",
            "postgresql://synthetic@localhost/admin",
            _s3_settings("synthetic-backups"),
            _s3_settings(target_bucket),
            target_bucket,
            RESTORE_PREFIX,
            database_connect=lambda *_args, **_kwargs: FakeDatabaseConnection(
                events=database_events
            ),
            target_public_base_url=_target_public_base_url(target_bucket),
            database_reference_connect=_empty_restore_reference_connect,
        )

    assert str(failure.value) == (
        "Snapshot restore is incomplete; inspect the isolated target database "
        "and object bucket"
    )
    assert database_events == ["database-preflight", "database-restored"]
    assert store.objects[(target_bucket, first_target_key)] == first_object_bytes
    assert (target_bucket, second_target_key) not in store.objects
    assert [event[2] for event in store.events if event[0] == "put"] == [
        first_target_key,
        second_target_key,
    ]
    assert not any(event[0] == "delete" for event in store.events)
    assert all(
        store.objects[("synthetic-backups", key)] == content
        for key, content in backup_objects_before.items()
    )


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
            _s3_settings("synthetic-restore"),
            "synthetic-restore",
            RESTORE_PREFIX,
            database_connect=lambda *_args, **_kwargs: FakeDatabaseConnection(
                exists=True
            ),
            target_public_base_url=_target_public_base_url("synthetic-restore"),
            database_reference_connect=_empty_restore_reference_connect,
        )

    assert not any(
        event[0] == "put" and event[1] == "synthetic-restore" for event in store.events
    )


@pytest.mark.asyncio
async def test_restore_rejects_database_target_matching_v2_manifest_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FakeS3()
    manifest_key, _database_bytes, _object_bytes, _source_key = _seed_paired_backup(
        store
    )
    identity = ("synthetic-backups", manifest_key)
    data = json.loads(store.objects[identity])
    data["database"]["source_database"] = "restore_acceptance"
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    store.objects[identity] = payload
    store.etags[identity] = store._etag(payload)

    @asynccontextmanager
    async def fake_client(_settings: backup_db.S3Settings):
        yield store

    monkeypatch.setattr(backup_db, "s3_client", fake_client)
    monkeypatch.setattr(
        backup_db,
        "restore_archive",
        lambda *_args, **_kwargs: pytest.fail("source database reached restore"),
    )

    with pytest.raises(backup_db.BackupArtifactError, match="different"):
        await backup_db.restore_paired_snapshot_from_s3(
            manifest_key,
            "restore_acceptance",
            "postgresql://synthetic@localhost/admin",
            _s3_settings("synthetic-backups"),
            _s3_settings("synthetic-restore"),
            "synthetic-restore",
            RESTORE_PREFIX,
            database_connect=lambda *_args, **_kwargs: pytest.fail(
                "source database target reached PostgreSQL preflight"
            ),
            target_public_base_url=_target_public_base_url("synthetic-restore"),
            database_reference_connect=_empty_restore_reference_connect,
        )

    assert store.events == [("get", "synthetic-backups", manifest_key)]


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
            _s3_settings(target_bucket),
            target_bucket,
            RESTORE_PREFIX,
            database_connect=lambda *_args, **_kwargs: pytest.fail(
                "bucket alias reached database preflight"
            ),
            target_public_base_url=_target_public_base_url(target_bucket),
            database_reference_connect=_empty_restore_reference_connect,
        )

    assert store.events == [("get", "synthetic-backups", manifest_key)]
    assert not any(event[0] == "put" for event in store.events)


@pytest.mark.asyncio
async def test_pinned_object_download_preflights_body_and_cleans_partial_files(
    tmp_path: Path,
) -> None:
    class ResponseClient:
        def __init__(self, response: dict[str, Any]) -> None:
            self.response = response
            self.calls = 0

        async def get_object(self, **_kwargs: Any) -> dict[str, Any]:
            self.calls += 1
            return self.response

    existing = tmp_path / "existing-object"
    existing.write_bytes(b"preserve")
    unused = ResponseClient({})
    with pytest.raises(backup_db.BackupArtifactError, match="already exists"):
        await backup_db._download_object_to_file(
            unused,
            "synthetic-backups",
            "snapshot/object.blob",
            existing,
            expected_size=8,
            etag='"stable"',
        )
    assert existing.read_bytes() == b"preserve"
    assert unused.calls == 0

    no_body = ResponseClient({})
    with pytest.raises(backup_db.BackupArtifactError, match="no response body"):
        await backup_db._download_object_to_file(
            no_body,
            "synthetic-backups",
            "snapshot/object.blob",
            tmp_path / "no-body",
            expected_size=1,
            etag='"stable"',
        )

    declared_body = FakeBody(b"data")
    wrong_length = ResponseClient({"Body": declared_body, "ContentLength": 5})
    with pytest.raises(backup_db.BackupArtifactError, match="length"):
        await backup_db._download_object_to_file(
            wrong_length,
            "synthetic-backups",
            "snapshot/object.blob",
            tmp_path / "wrong-length",
            expected_size=4,
            etag='"stable"',
        )
    assert declared_body.closed

    oversized_body = FakeBody(b"too long")
    oversized = ResponseClient({"Body": oversized_body})
    oversized_path = tmp_path / "oversized"
    with pytest.raises(backup_db.BackupArtifactError, match="exceeded"):
        await backup_db._download_object_to_file(
            oversized,
            "synthetic-backups",
            "snapshot/object.blob",
            oversized_path,
            expected_size=2,
            etag='"stable"',
        )
    assert not oversized_path.exists()
    assert oversized_body.closed

    truncated_body = FakeBody(b"short")
    truncated = ResponseClient({"Body": truncated_body})
    truncated_path = tmp_path / "truncated"
    with pytest.raises(backup_db.BackupArtifactError, match="length"):
        await backup_db._download_object_to_file(
            truncated,
            "synthetic-backups",
            "snapshot/object.blob",
            truncated_path,
            expected_size=10,
            etag='"stable"',
        )
    assert not truncated_path.exists()
    assert truncated_body.closed

    class ReadFailureBody(FakeBody):
        def __init__(self) -> None:
            super().__init__(b"partial")
            self.reads = 0

        async def read(self, _size: int = -1) -> bytes:
            self.reads += 1
            if self.reads == 1:
                return b"par"
            raise OSError("synthetic transport detail")

    failing_body = ReadFailureBody()
    failing_path = tmp_path / "failed-read"
    with pytest.raises(backup_db.BackupArtifactError, match="Unable to download"):
        await backup_db._download_object_to_file(
            ResponseClient({"Body": failing_body}),
            "synthetic-backups",
            "snapshot/object.blob",
            failing_path,
            expected_size=6,
            etag='"stable"',
        )
    assert not failing_path.exists()
    assert failing_body.closed


@pytest.mark.asyncio
async def test_limited_manifest_body_closes_on_missing_or_invalid_payloads() -> None:
    with pytest.raises(backup_db.BackupArtifactError, match="no response body"):
        await backup_db._read_limited_body({}, maximum=3)

    for content_length in (True, -1, 4):
        body = FakeBody(b"x")
        with pytest.raises(backup_db.BackupArtifactError, match="size is invalid"):
            await backup_db._read_limited_body(
                {"Body": body, "ContentLength": content_length}, maximum=3
            )
        assert body.closed

    oversized_body = FakeBody(b"123")
    with pytest.raises(backup_db.BackupArtifactError, match="too large"):
        await backup_db._read_limited_body({"Body": oversized_body}, maximum=2)
    assert oversized_body.closed

    mismatched_body = FakeBody(b"12")
    with pytest.raises(backup_db.BackupArtifactError, match="length is invalid"):
        await backup_db._read_limited_body(
            {"Body": mismatched_body, "ContentLength": 3}, maximum=3
        )
    assert mismatched_body.closed


@pytest.mark.asyncio
async def test_application_object_inventory_paginates_with_opaque_tokens() -> None:
    pages = [
        {
            "Contents": [{"Key": "first", "Size": 1, "ETag": '"one"'}],
            "KeyCount": 1,
            "IsTruncated": True,
            "NextContinuationToken": "cursor-2",
        },
        {"Contents": [], "KeyCount": 0, "IsTruncated": False},
    ]

    class PageClient:
        def __init__(self) -> None:
            self.requests: list[dict[str, Any]] = []

        async def list_objects_v2(self, **request: Any) -> dict[str, Any]:
            self.requests.append(request)
            return pages[len(self.requests) - 1]

    client = PageClient()

    objects = await backup_db._list_current_objects(client, "synthetic-uploads")

    assert objects == [{"Key": "first", "Size": 1, "ETag": '"one"'}]
    assert client.requests[0] == {"Bucket": "synthetic-uploads", "MaxKeys": 1000}
    assert client.requests[1]["ContinuationToken"] == "cursor-2"


@pytest.mark.parametrize(
    ("pages", "message"),
    [
        ([OSError("synthetic transport")], "Unable to inventory"),
        (
            [{"Contents": [], "KeyCount": True, "IsTruncated": False}],
            "invalid object inventory",
        ),
        (
            [{"Contents": [None], "KeyCount": 1, "IsTruncated": False}],
            "invalid object inventory",
        ),
        (
            [
                {
                    "Contents": [{"Key": "one", "Size": True, "ETag": '"one"'}],
                    "KeyCount": 1,
                    "IsTruncated": False,
                }
            ],
            "invalid object size",
        ),
        (
            [
                {
                    "Contents": [{"Key": "one", "Size": 1, "ETag": ""}],
                    "KeyCount": 1,
                    "IsTruncated": False,
                }
            ],
            "stable ETag",
        ),
        (
            [{"Contents": [], "KeyCount": 0, "IsTruncated": True}],
            "pagination is invalid",
        ),
        (
            [
                {
                    "Contents": [],
                    "KeyCount": 0,
                    "IsTruncated": True,
                    "NextContinuationToken": "",
                }
            ],
            "pagination is invalid",
        ),
        (
            [
                {
                    "Contents": [],
                    "KeyCount": 0,
                    "IsTruncated": True,
                    "NextContinuationToken": "cursor",
                },
                {
                    "Contents": [],
                    "KeyCount": 0,
                    "IsTruncated": True,
                    "NextContinuationToken": "cursor",
                },
            ],
            "pagination is invalid",
        ),
    ],
)
@pytest.mark.asyncio
async def test_application_object_inventory_rejects_invalid_pages(
    pages: list[Any], message: str
) -> None:
    class PageClient:
        def __init__(self) -> None:
            self.calls = 0

        async def list_objects_v2(self, **_request: Any) -> dict[str, Any]:
            page = pages[self.calls]
            self.calls += 1
            if isinstance(page, Exception):
                raise page
            return page

    with pytest.raises(backup_db.BackupArtifactError, match=message):
        await backup_db._list_current_objects(PageClient(), "synthetic-uploads")


@pytest.mark.asyncio
async def test_application_object_inventory_enforces_maximum_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(backup_db, "MAX_SNAPSHOT_OBJECTS", 1)

    class TooManyObjects:
        async def list_objects_v2(self, **_request: Any) -> dict[str, Any]:
            return {
                "Contents": [
                    {"Key": "one", "Size": 0, "ETag": '"one"'},
                    {"Key": "two", "Size": 0, "ETag": '"two"'},
                ],
                "KeyCount": 2,
                "IsTruncated": False,
            }

    with pytest.raises(backup_db.BackupArtifactError, match="too large"):
        await backup_db._list_current_objects(TooManyObjects(), "synthetic-uploads")


@pytest.mark.asyncio
async def test_create_only_upload_rejects_missing_file_and_verification_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(backup_db.BackupArtifactError, match="source artifact"):
        await backup_db._upload_file_create_only(
            object(),
            "synthetic-backups",
            "snapshot/object.blob",
            tmp_path / "missing-artifact",
        )

    artifact = tmp_path / "verified-artifact"
    artifact.write_bytes(b"synthetic artifact")

    async def false_readback(
        *_args: Any, **_kwargs: Any
    ) -> tuple[int, str, dict[str, Any]]:
        return artifact.stat().st_size, "0" * 64, {}

    monkeypatch.setattr(backup_db, "_download_object_to_file", false_readback)
    with pytest.raises(backup_db.BackupArtifactError, match="read-back verification"):
        await backup_db._verify_uploaded_file(
            object(),
            "synthetic-backups",
            "snapshot/object.blob",
            artifact,
            receipt=backup_db.S3ObjectReceipt(version_id=None, etag='"stable"'),
        )


@pytest.mark.asyncio
async def test_multipart_upload_failure_paths_abort_only_the_started_upload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(backup_db, "SNAPSHOT_PART_SIZE", 2)
    artifact = tmp_path / "multipart-artifact"
    artifact.write_bytes(b"synthetic multipart bytes")

    class UploadClient:
        def __init__(self, failure: str) -> None:
            self.failure = failure
            self.aborts = 0

        async def create_multipart_upload(self, **_kwargs: Any) -> dict[str, str]:
            if self.failure == "create":
                raise OSError("synthetic setup failure")
            if self.failure == "missing-id":
                return {}
            return {"UploadId": "upload-1"}

        async def upload_part(self, **_kwargs: Any) -> dict[str, str]:
            if self.failure == "cancel":
                raise asyncio.CancelledError
            if self.failure == "part":
                raise OSError("synthetic part failure")
            if self.failure == "bad-part-etag":
                return {}
            return {"ETag": '"part"'}

        async def complete_multipart_upload(self, **_kwargs: Any) -> dict[str, str]:
            if self.failure == "complete":
                raise OSError("synthetic completion failure")
            return {"ETag": '"complete"'}

        async def abort_multipart_upload(self, **_kwargs: Any) -> None:
            self.aborts += 1

    failures: tuple[tuple[str, str | None, int], ...] = (
        ("create", "stage immutable", 0),
        ("missing-id", "upload identity", 0),
        ("part", "not completed conditionally", 1),
        ("bad-part-etag", "validator required", 1),
        ("complete", "not completed conditionally", 1),
        ("cancel", None, 2),
    )
    for failure, message, expected_aborts in failures:
        client = UploadClient(failure)
        if failure == "cancel":
            with pytest.raises(asyncio.CancelledError):
                await backup_db._upload_file_create_only(
                    client,
                    "synthetic-backups",
                    "snapshot/object.blob",
                    artifact,
                )
        else:
            assert message is not None
            with pytest.raises(backup_db.BackupArtifactError, match=message):
                await backup_db._upload_file_create_only(
                    client,
                    "synthetic-backups",
                    "snapshot/object.blob",
                    artifact,
                )
        assert client.aborts == expected_aborts


@pytest.mark.asyncio
async def test_multipart_upload_rejects_artifacts_above_s3_part_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(backup_db, "SNAPSHOT_PART_SIZE", 1)
    artifact = tmp_path / "too-many-parts"
    artifact.write_bytes(b"x" * 10_001)

    class CountingClient:
        def __init__(self) -> None:
            self.uploaded_parts = 0
            self.aborts = 0

        async def create_multipart_upload(self, **_kwargs: Any) -> dict[str, str]:
            return {"UploadId": "upload-1"}

        async def upload_part(self, **_kwargs: Any) -> dict[str, str]:
            self.uploaded_parts += 1
            return {"ETag": '"part"'}

        async def complete_multipart_upload(self, **_kwargs: Any) -> dict[str, str]:
            pytest.fail("an over-limit multipart upload must not complete")

        async def abort_multipart_upload(self, **_kwargs: Any) -> None:
            self.aborts += 1

    client = CountingClient()
    with pytest.raises(backup_db.BackupArtifactError, match="multipart limits"):
        await backup_db._upload_file_create_only(
            client,
            "synthetic-backups",
            "snapshot/object.blob",
            artifact,
        )

    assert client.uploaded_parts == 10_000
    assert client.aborts == 1


@pytest.mark.asyncio
async def test_paired_manifest_publish_requires_conditional_create_and_exact_readback() -> (
    None
):
    class PutFailure:
        async def put_object(self, **_kwargs: Any) -> None:
            raise OSError("synthetic conditional write failure")

    with pytest.raises(
        backup_db.BackupArtifactError, match="not created conditionally"
    ):
        await backup_db._publish_paired_manifest(
            PutFailure(), "synthetic-backups", "snapshot/manifest.json", b"{}"
        )

    class MismatchedReadback:
        async def put_object(self, **_kwargs: Any) -> dict[str, str]:
            return {"ETag": '"committed"'}

        async def get_object(self, **_kwargs: Any) -> dict[str, Any]:
            body = FakeBody(b"different")
            return {"Body": body, "ContentLength": len(b"different")}

    with pytest.raises(backup_db.BackupArtifactError, match="read-back failed"):
        await backup_db._publish_paired_manifest(
            MismatchedReadback(),
            "synthetic-backups",
            "snapshot/manifest.json",
            b"{}",
        )


@pytest.mark.asyncio
async def test_paired_manifest_download_requires_manifest_suffix() -> None:
    with pytest.raises(backup_db.BackupArtifactError, match="manifest object key"):
        await backup_db._download_paired_manifest(
            object(), "synthetic-backups", "snapshot/database.dump"
        )


@pytest.mark.asyncio
async def test_paired_snapshot_requires_distinct_object_buckets_before_database_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_metadata(_url: str) -> tuple[str, tuple[str, ...]]:
        pytest.fail("same-bucket validation must precede database access")

    monkeypatch.setattr(backup_db, "source_database_metadata", forbidden_metadata)

    with pytest.raises(backup_db.BackupArtifactError, match="buckets must differ"):
        await backup_db.backup_paired_snapshot_to_s3(
            "postgresql://synthetic@localhost/source",
            _s3_settings("synthetic-bucket"),
            _s3_settings("synthetic-bucket"),
            confirm_source_quiesced=True,
        )


@pytest.mark.asyncio
async def test_paired_snapshot_commits_a_database_when_source_bucket_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FakeS3()

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

    manifest_key = await backup_db.backup_paired_snapshot_to_s3(
        "postgresql://synthetic@localhost/source",
        _s3_settings("synthetic-backups"),
        _s3_settings("synthetic-uploads"),
        confirm_source_quiesced=True,
    )

    manifest = backup_db.parse_paired_snapshot_manifest(
        store.objects[("synthetic-backups", manifest_key)],
        expected_manifest_key=manifest_key,
    )
    assert manifest.objects == ()
    assert store.objects[("synthetic-backups", manifest.database.artifact_key)] == (
        b"synthetic database archive"
    )


@pytest.mark.asyncio
async def test_paired_snapshot_rejects_source_object_changed_after_inventory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FakeS3()
    identity = ("synthetic-uploads", "users/42/avatar.png")
    content = b"synthetic avatar"
    store.objects[identity] = content
    store.etags[identity] = store._etag(content)
    original_get = store.get_object

    async def changed_get(**kwargs: Any) -> dict[str, Any]:
        response = await original_get(**kwargs)
        return {**response, "ETag": '"changed-after-inventory"'}

    monkeypatch.setattr(store, "get_object", changed_get)

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

    with pytest.raises(backup_db.BackupArtifactError, match="changed during"):
        await backup_db.backup_paired_snapshot_to_s3(
            "postgresql://synthetic@localhost/source",
            _s3_settings("synthetic-backups"),
            _s3_settings("synthetic-uploads"),
            confirm_source_quiesced=True,
        )

    assert store.objects[identity] == content
    assert not any(event[0] == "put" for event in store.events)


@pytest.mark.asyncio
async def test_paired_snapshot_rejects_same_digest_with_inconsistent_lengths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FakeS3()
    for key, content in (("one", b"a"), ("two", b"bb")):
        identity = ("synthetic-uploads", key)
        store.objects[identity] = content
        store.etags[identity] = store._etag(content)

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

    async def colliding_download(
        _client: Any,
        _bucket: str,
        _key: str,
        destination: Path,
        *,
        expected_size: int,
        etag: str | None = None,
        **_kwargs: Any,
    ) -> tuple[int, str, dict[str, Any]]:
        destination.write_bytes(b"x" * expected_size)
        return expected_size, "f" * 64, {"ETag": etag}

    uploaded_sizes: list[int] = []

    async def fake_upload(
        _client: Any,
        _bucket: str,
        _key: str,
        path: Path,
        **_kwargs: Any,
    ) -> backup_db.S3ObjectReceipt:
        uploaded_sizes.append(path.stat().st_size)
        return backup_db.S3ObjectReceipt(version_id=None, etag='"archive"')

    async def fake_verify(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(backup_db, "_download_object_to_file", colliding_download)
    monkeypatch.setattr(backup_db, "_upload_file_create_only", fake_upload)
    monkeypatch.setattr(backup_db, "_verify_uploaded_file", fake_verify)

    with pytest.raises(backup_db.BackupArtifactError, match="inconsistent lengths"):
        await backup_db.backup_paired_snapshot_to_s3(
            "postgresql://synthetic@localhost/source",
            _s3_settings("synthetic-backups"),
            _s3_settings("synthetic-uploads"),
            confirm_source_quiesced=True,
        )

    assert uploaded_sizes == [1]


@pytest.mark.asyncio
async def test_restore_reuses_a_single_download_for_duplicate_archive_objects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FakeS3()
    manifest_key, _database_bytes, object_bytes, source_key = _seed_paired_backup(store)
    archive_key = _append_paired_archive_object(
        store,
        manifest_key,
        source_key="users/43/avatar.png",
        content=object_bytes,
    )

    @asynccontextmanager
    async def fake_client(_settings: backup_db.S3Settings):
        yield store

    monkeypatch.setattr(backup_db, "s3_client", fake_client)
    monkeypatch.setattr(backup_db, "restore_archive", lambda *_args: None)
    monkeypatch.setattr(
        backup_db.psycopg,
        "connect",
        lambda *_args, **_kwargs: FakeDatabaseConnection(),
    )

    await backup_db.restore_paired_snapshot_from_s3(
        manifest_key,
        "restore_acceptance",
        "postgresql://synthetic@localhost/admin",
        _s3_settings("synthetic-backups"),
        _s3_settings("synthetic-restore"),
        "synthetic-restore",
        RESTORE_PREFIX,
        target_public_base_url=_target_public_base_url("synthetic-restore"),
        database_reference_connect=_empty_restore_reference_connect,
    )

    assert [
        event
        for event in store.events
        if event == ("get", "synthetic-backups", archive_key)
    ] == [("get", "synthetic-backups", archive_key)]
    assert (
        store.objects[("synthetic-restore", f"{RESTORE_PREFIX}/{source_key}")]
        == object_bytes
    )
    assert (
        store.objects[("synthetic-restore", f"{RESTORE_PREFIX}/users/43/avatar.png")]
        == object_bytes
    )


@pytest.mark.asyncio
async def test_restore_without_objects_creates_only_the_isolated_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FakeS3()
    manifest_key, _database_bytes, _object_bytes, _source_key = _seed_paired_backup(
        store
    )
    manifest_identity = ("synthetic-backups", manifest_key)
    data = json.loads(store.objects[manifest_identity])
    data["objects"] = []
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    store.objects[manifest_identity] = payload
    store.etags[manifest_identity] = store._etag(payload)
    events: list[str] = []

    @asynccontextmanager
    async def fake_client(_settings: backup_db.S3Settings):
        yield store

    monkeypatch.setattr(backup_db, "s3_client", fake_client)
    monkeypatch.setattr(
        backup_db, "restore_archive", lambda *_args: events.append("restore")
    )
    monkeypatch.setattr(
        backup_db.psycopg,
        "connect",
        lambda *_args, **_kwargs: FakeDatabaseConnection(events=events),
    )

    restored = await backup_db.restore_paired_snapshot_from_s3(
        manifest_key,
        "restore_acceptance",
        "postgresql://synthetic@localhost/admin",
        _s3_settings("synthetic-backups"),
        _s3_settings("synthetic-restore"),
        "synthetic-restore",
        RESTORE_PREFIX,
        target_public_base_url=_target_public_base_url("synthetic-restore"),
        database_reference_connect=_empty_restore_reference_connect,
    )

    assert restored.objects == ()
    assert events == ["database-preflight", "restore"]
    assert not any(
        event[0] == "put" and event[1] == "synthetic-restore" for event in store.events
    )
