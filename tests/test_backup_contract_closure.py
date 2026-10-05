from __future__ import annotations

import builtins
import json
import os
import runpy
import secrets
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from scripts import backup_db


def _archive(tmp_path: Path, content: bytes = b"synthetic dump") -> Path:
    path = tmp_path / "synthetic.dump"
    path.write_bytes(content)
    return path


def _manifest(archive: Path) -> backup_db.BackupManifest:
    return backup_db.create_manifest(
        archive,
        source_database="synthetic_source",
        source_revision=("synthetic_revision",),
        artifact_key="synthetic/backup.dump",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _valid_manifest_data(archive: Path) -> dict[str, Any]:
    return asdict(_manifest(archive))


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"format": "plain"}, "format"),
        ({"source_database": ""}, "source database"),
        ({"source_database": "d" * 64}, "source database"),
        ({"source_revision": []}, "source revision"),
        ({"source_revision": [""]}, "source revision"),
        ({"source_revision": ["r" * 256]}, "source revision"),
        ({"created_at": 42}, "timestamp"),
        ({"created_at": "not-a-timestamp"}, "timestamp"),
        ({"created_at": "2026-01-01T00:00:00+01:00"}, "UTC"),
        ({"artifact_key": "synthetic/backup.tar"}, "artifact key"),
        ({"size_bytes": True}, "size"),
        ({"size_bytes": 0}, "size"),
        ({"sha256": "not-a-checksum"}, "checksum"),
    ],
)
def test_manifest_parser_rejects_invalid_metadata_before_restore(
    tmp_path: Path, changes: dict[str, Any], message: str
) -> None:
    data = _valid_manifest_data(_archive(tmp_path))
    data.update(changes)

    with pytest.raises(backup_db.BackupArtifactError, match=message):
        backup_db.parse_manifest(
            json.dumps(data).encode(),
            expected_manifest_key="synthetic/backup.manifest.json",
        )


@pytest.mark.parametrize(
    "payload",
    [b"not json", b"\xff", b"[]"],
    ids=["syntax", "encoding", "non-object"],
)
def test_manifest_parser_rejects_invalid_json_and_root_types(
    payload: bytes,
) -> None:
    with pytest.raises(backup_db.BackupArtifactError):
        backup_db.parse_manifest(
            payload,
            expected_manifest_key="synthetic/backup.manifest.json",
        )


def test_manifest_parser_rejects_duplicate_fields_and_oversized_payload(
    tmp_path: Path,
) -> None:
    manifest = _manifest(_archive(tmp_path))
    valid = manifest.to_json_bytes()
    duplicate = valid.replace(
        b'"schema_version":1', b'"schema_version":1,"schema_version":1'
    )

    with pytest.raises(backup_db.BackupArtifactError, match="duplicate"):
        backup_db.parse_manifest(
            duplicate,
            expected_manifest_key="synthetic/backup.manifest.json",
        )
    with pytest.raises(backup_db.BackupArtifactError, match="too large"):
        backup_db.parse_manifest(
            b"x" * (backup_db.MANIFEST_MAX_BYTES + 1),
            expected_manifest_key="synthetic/backup.manifest.json",
        )


@pytest.mark.parametrize(
    ("expected_key", "message"),
    [
        ("synthetic/backup.dump", "suffix"),
        ("synthetic/another.manifest.json", "does not match"),
    ],
)
def test_manifest_parser_binds_manifest_to_exact_archive_key(
    tmp_path: Path, expected_key: str, message: str
) -> None:
    manifest = _manifest(_archive(tmp_path))
    with pytest.raises(backup_db.BackupArtifactError, match=message):
        backup_db.parse_manifest(
            manifest.to_json_bytes(), expected_manifest_key=expected_key
        )


def test_artifact_key_unicode_encoding_and_manifest_pair_limits() -> None:
    with pytest.raises(backup_db.BackupArtifactError, match="Invalid S3 object key"):
        backup_db.manifest_key("synthetic/\ud800.dump")
    with pytest.raises(backup_db.BackupArtifactError, match="custom-format dump"):
        backup_db.manifest_key("synthetic/backup.sql")

    generated_key = backup_db.new_artifact_key("")
    assert generated_key.endswith(backup_db.ARTIFACT_SUFFIX)
    assert backup_db.manifest_key(generated_key).endswith(backup_db.MANIFEST_SUFFIX)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"artifact_key": "synthetic/backup.sql"}, "custom-format dump"),
        ({"source_database": ""}, "source database"),
        ({"source_database": "d" * 64}, "source database"),
        ({"source_revision": ()}, "revision"),
        ({"source_revision": ("r" * 256,)}, "revision"),
        ({"created_at": datetime(2026, 1, 1)}, "timezone-aware"),
    ],
)
def test_manifest_creation_rejects_incomplete_source_identity(
    tmp_path: Path, kwargs: dict[str, Any], message: str
) -> None:
    archive = _archive(tmp_path)
    arguments: dict[str, Any] = {
        "source_database": "synthetic_source",
        "source_revision": ("synthetic_revision",),
        "artifact_key": "synthetic/backup.dump",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    arguments.update(kwargs)

    with pytest.raises(backup_db.BackupArtifactError, match=message):
        backup_db.create_manifest(archive, **arguments)


def test_manifest_creation_rejects_empty_dump(tmp_path: Path) -> None:
    archive = _archive(tmp_path, b"")
    with pytest.raises(backup_db.BackupArtifactError, match="empty"):
        backup_db.create_manifest(
            archive,
            source_database="synthetic_source",
            source_revision=("synthetic_revision",),
            artifact_key="synthetic/backup.dump",
        )


@pytest.mark.asyncio
async def test_unverified_manifest_cleanup_sanitizes_remote_delete_errors() -> None:
    class DeleteFailure:
        async def delete_object(self, **_kwargs: Any) -> None:
            raise OSError("synthetic bucket access marker")

    with pytest.raises(
        backup_db.BackupArtifactError, match="remove unverified"
    ) as error:
        await backup_db._remove_unverified_manifest(
            DeleteFailure(), "synthetic", "synthetic/backup.manifest.json"
        )
    assert "bucket access marker" not in str(error.value)


@pytest.mark.asyncio
async def test_stream_helpers_handle_sync_bodies_and_reject_non_bytes() -> None:
    class SyncBody:
        def __init__(self, value: Any) -> None:
            self.value = value
            self.closed = False

        def read(self, _size: int = -1) -> Any:
            return self.value

        def close(self) -> None:
            self.closed = True

    body = SyncBody(b"synthetic")
    assert await backup_db._read_body(body, 9) == b"synthetic"
    await backup_db._close_body(body)
    assert body.closed
    await backup_db._close_body(object())

    with pytest.raises(backup_db.BackupArtifactError, match="invalid"):
        await backup_db._read_body(SyncBody("not bytes"))


@pytest.mark.asyncio
async def test_s3_fetch_and_remote_hash_fail_closed_on_invalid_responses() -> None:
    class Client:
        async def get_object(self, **_kwargs: Any) -> dict[str, Any]:
            raise OSError("synthetic transport detail")

    with pytest.raises(backup_db.BackupArtifactError, match="retrieve") as error:
        await backup_db._get_object(Client(), "synthetic", "synthetic/key")
    assert "synthetic transport detail" not in str(error.value)

    class MissingBodyClient:
        async def get_object(self, **_kwargs: Any) -> dict[str, Any]:
            return {}

    with pytest.raises(backup_db.BackupArtifactError, match="no response body"):
        await backup_db._hash_remote_object(MissingBodyClient(), "synthetic", "key")

    class Body:
        def __init__(self, payload: bytes) -> None:
            self.payload = payload
            self.closed = False

        async def read(self, size: int = -1) -> bytes:
            if size < 0:
                result, self.payload = self.payload, b""
                return result
            result, self.payload = self.payload[:size], self.payload[size:]
            return result

        async def close(self) -> None:
            self.closed = True

    body = Body(b"abc")

    class WrongLengthClient:
        async def get_object(self, **_kwargs: Any) -> dict[str, Any]:
            return {"Body": body, "ContentLength": True}

    with pytest.raises(backup_db.BackupArtifactError, match="verification"):
        await backup_db._hash_remote_object(
            WrongLengthClient(), "synthetic", "key", expected_size=3
        )
    assert body.closed

    body = Body(b"abc")

    class InconsistentLengthClient:
        async def get_object(self, **_kwargs: Any) -> dict[str, Any]:
            return {"Body": body, "ContentLength": 2}

    with pytest.raises(backup_db.BackupArtifactError, match="length"):
        await backup_db._hash_remote_object(
            InconsistentLengthClient(), "synthetic", "key"
        )
    assert body.closed


@pytest.mark.asyncio
async def test_publish_rejects_local_mismatch_and_sanitizes_upload_failures(
    tmp_path: Path,
) -> None:
    archive = _archive(tmp_path)
    manifest = _manifest(archive)

    class ForbiddenClient:
        async def upload_file(self, *_args: Any) -> None:
            pytest.fail("invalid local dump reached S3")

    archive.write_bytes(b"changed after manifest creation")
    with pytest.raises(backup_db.BackupArtifactError, match="Local dump"):
        await backup_db.publish_backup(
            ForbiddenClient(), "synthetic", archive, manifest
        )

    archive.write_bytes(b"synthetic dump")

    class UploadFailure:
        async def upload_file(self, *_args: Any) -> None:
            raise OSError("synthetic S3 credential marker")

    with pytest.raises(
        backup_db.BackupArtifactError, match="upload database dump"
    ) as error:
        await backup_db.publish_backup(UploadFailure(), "synthetic", archive, manifest)
    assert "credential marker" not in str(error.value)


@pytest.mark.asyncio
async def test_publish_fails_closed_on_bad_manifest_readback(
    tmp_path: Path,
) -> None:
    archive = _archive(tmp_path)
    manifest = _manifest(archive)

    class Body:
        def __init__(self, content: bytes) -> None:
            self.content = content
            self.closed = False

        async def read(self, size: int = -1) -> bytes:
            if size < 0:
                result, self.content = self.content, b""
                return result
            result, self.content = self.content[:size], self.content[size:]
            return result

        async def close(self) -> None:
            self.closed = True

    class CorruptArchiveClient:
        async def upload_file(self, *_args: Any) -> None:
            return None

        async def get_object(self, **_kwargs: Any) -> dict[str, Any]:
            body = Body(b"synthetic dumq")
            self.body = body
            return {"Body": body, "ContentLength": len(b"synthetic dumq")}

        async def put_object(self, **_kwargs: Any) -> None:
            pytest.fail("checksum-mismatched archive published its manifest")

    corrupt = CorruptArchiveClient()
    with pytest.raises(backup_db.BackupArtifactError, match="read-back verification"):
        await backup_db.publish_backup(corrupt, "synthetic", archive, manifest)
    assert corrupt.body.closed

    class ManifestReadbackClient:
        def __init__(self, *, oversized: bool = False) -> None:
            self.oversized = oversized
            self.manifest_body: Body | None = None

        async def upload_file(self, *_args: Any) -> None:
            return None

        async def get_object(self, *, Key: str, **_kwargs: Any) -> dict[str, Any]:
            if Key == manifest.artifact_key:
                body = Body(archive.read_bytes())
                return {"Body": body, "ContentLength": manifest.size_bytes}
            if self.oversized:
                self.manifest_body = Body(b"x" * (backup_db.MANIFEST_MAX_BYTES + 1))
                return {"Body": self.manifest_body}
            return {}

        async def put_object(self, **_kwargs: Any) -> None:
            return None

        async def delete_object(self, **_kwargs: Any) -> None:
            return None

    missing = ManifestReadbackClient()
    with pytest.raises(
        backup_db.BackupArtifactError, match="manifest had no response body"
    ):
        await backup_db.publish_backup(missing, "synthetic", archive, manifest)

    oversized = ManifestReadbackClient(oversized=True)
    with pytest.raises(backup_db.BackupArtifactError, match="manifest is too large"):
        await backup_db.publish_backup(oversized, "synthetic", archive, manifest)
    assert oversized.manifest_body is not None
    assert oversized.manifest_body.closed


@pytest.mark.asyncio
async def test_download_preflights_paths_and_closes_invalid_remote_streams(
    tmp_path: Path,
) -> None:
    archive = _archive(tmp_path)
    manifest = _manifest(archive)
    manifest_key = backup_db.manifest_key(manifest.artifact_key)

    existing = tmp_path / "existing.dump"
    existing.write_bytes(b"preserve existing")
    with pytest.raises(backup_db.BackupArtifactError, match="already exists"):
        await backup_db.download_verified_backup(
            object(), "synthetic", manifest_key, existing
        )
    assert existing.read_bytes() == b"preserve existing"

    with pytest.raises(backup_db.BackupArtifactError, match="explicit manifest"):
        await backup_db.download_verified_backup(
            object(), "synthetic", "synthetic/backup.dump", tmp_path / "wrong-key.dump"
        )

    class Body:
        def __init__(self, content: bytes) -> None:
            self.content = content
            self.closed = False

        async def read(self, size: int = -1) -> bytes:
            if size < 0:
                result, self.content = self.content, b""
                return result
            result, self.content = self.content[:size], self.content[size:]
            return result

        async def close(self) -> None:
            self.closed = True

    class MissingManifestBody:
        async def get_object(self, **_kwargs: Any) -> dict[str, Any]:
            return {}

    with pytest.raises(
        backup_db.BackupArtifactError, match="manifest had no response body"
    ):
        await backup_db.download_verified_backup(
            MissingManifestBody(), "synthetic", manifest_key, tmp_path / "none.dump"
        )

    oversized_body = Body(b"x" * (backup_db.MANIFEST_MAX_BYTES + 1))

    class OversizedManifestBody:
        async def get_object(self, **_kwargs: Any) -> dict[str, Any]:
            return {"Body": oversized_body}

    with pytest.raises(backup_db.BackupArtifactError, match="manifest is too large"):
        await backup_db.download_verified_backup(
            OversizedManifestBody(),
            "synthetic",
            manifest_key,
            tmp_path / "oversized.dump",
        )
    assert oversized_body.closed

    class ValidManifestNoArchiveBody:
        async def get_object(self, *, Key: str, **_kwargs: Any) -> dict[str, Any]:
            if Key == manifest_key:
                payload = manifest.to_json_bytes()
                return {"Body": Body(payload), "ContentLength": len(payload)}
            return {}

    with pytest.raises(
        backup_db.BackupArtifactError, match="dump had no response body"
    ):
        await backup_db.download_verified_backup(
            ValidManifestNoArchiveBody(),
            "synthetic",
            manifest_key,
            tmp_path / "missing-archive.dump",
        )

    class ReadFailureBody(Body):
        def __init__(self) -> None:
            super().__init__(b"start")
            self.read_count = 0

        async def read(self, _size: int = -1) -> bytes:
            self.read_count += 1
            if self.read_count == 1:
                return b"partial"
            raise OSError("synthetic transport credential marker")

    partial_body = ReadFailureBody()

    class ReadFailureClient:
        async def get_object(self, *, Key: str, **_kwargs: Any) -> dict[str, Any]:
            if Key == manifest_key:
                payload = manifest.to_json_bytes()
                return {"Body": Body(payload), "ContentLength": len(payload)}
            return {"Body": partial_body, "ContentLength": manifest.size_bytes}

    partial_path = tmp_path / "partial-read.dump"
    with pytest.raises(
        backup_db.BackupArtifactError, match="Unable to download"
    ) as error:
        await backup_db.download_verified_backup(
            ReadFailureClient(), "synthetic", manifest_key, partial_path
        )
    assert "credential marker" not in str(error.value)
    assert not partial_path.exists()
    assert partial_body.closed


@pytest.mark.parametrize("fail_kind", ["missing", "empty"])
def test_dump_requires_nonempty_archive_output(tmp_path: Path, fail_kind: str) -> None:
    archive = tmp_path / "missing.dump"

    def runner(_command: list[str], **_kwargs: Any) -> SimpleNamespace:
        if fail_kind == "empty":
            archive.write_bytes(b"")
        return SimpleNamespace(returncode=0)

    with pytest.raises(backup_db.BackupArtifactError, match="non-empty"):
        backup_db.dump_database(
            "postgresql://synthetic@localhost/source",
            archive,
            command_runner=runner,
        )


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("not a database URL", "invalid"),
        ("sqlite:///tmp/not-postgres.db", "PostgreSQL"),
        ("postgresql://localhost", "PostgreSQL"),
        ("postgresql://localhost/source?unsupported_option=secret", "unsupported"),
        (
            "postgresql://localhost/source?application_name=first&application_name=second",
            "repeated",
        ),
    ],
)
def test_database_url_rejects_invalid_or_unsupported_connection_options(
    url: str, message: str
) -> None:
    with pytest.raises(backup_db.BackupArtifactError, match=message):
        backup_db._pg_tool_environment(url)


def test_pg_tool_environment_uses_url_fields_and_only_known_fallbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PGPASSWORD", "synthetic-fallback")
    monkeypatch.setenv("PGAPPNAME", "fallback-app")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "synthetic-aws-marker")
    environment = backup_db._pg_tool_environment(
        "postgresql://url_user:url_password@db.example.test:5440/source"  # pragma: allowlist secret -- synthetic backup subprocess credential fixture
        "?application_name=backup-job&sslmode=verify-full",
        database_override="restore_sandbox",
    )

    assert environment["PGHOST"] == "db.example.test"
    assert environment["PGPORT"] == "5440"
    assert environment["PGUSER"] == "url_user"
    assert (
        environment["PGPASSWORD"] == "url_password"  # pragma: allowlist secret
    )
    assert environment["PGDATABASE"] == "restore_sandbox"
    assert environment["PGAPPNAME"] == "backup-job"
    assert environment["PGSSLMODE"] == "verify-full"
    assert "AWS_SECRET_ACCESS_KEY" not in environment
    assert environment["PATH"] == os.environ["PATH"]


def test_pg_tool_environment_accepts_single_value_query_tuple(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = backup_db.make_url("postgresql:///source").set(
        query={"application_name": ("synthetic-job",)}
    )
    monkeypatch.setattr(backup_db, "_database_url", lambda _value: url)

    environment = backup_db._pg_tool_environment("synthetic-placeholder")
    assert environment["PGDATABASE"] == "source"
    assert environment["PGAPPNAME"] == "synthetic-job"
    assert "PGHOST" not in environment


@pytest.mark.parametrize(
    "failure", [FileNotFoundError("synthetic"), OSError("synthetic")]
)
def test_pg_tool_runner_suppresses_process_exception_details(
    failure: Exception,
) -> None:
    def runner(*_args: Any, **_kwargs: Any) -> None:
        raise failure

    with pytest.raises(backup_db.BackupArtifactError) as error:
        backup_db._run_pg_tool(["pg_dump"], {}, command_runner=runner)

    assert "synthetic" not in str(error.value)
    expected = (
        "unavailable" if isinstance(failure, FileNotFoundError) else "Unable to run"
    )
    assert expected in str(error.value)


@pytest.mark.parametrize(
    ("database_row", "revisions", "connect_failure", "message"),
    [
        (None, [], False, "metadata is unavailable"),
        (("synthetic_source",), [], False, "no Alembic revision"),
        (("synthetic_source",), [("revision",)], True, "Unable to read"),
    ],
)
def test_source_metadata_fails_closed_for_missing_catalog_data(
    monkeypatch: pytest.MonkeyPatch,
    database_row: tuple[str] | None,
    revisions: list[tuple[str]],
    connect_failure: bool,
    message: str,
) -> None:
    class Result:
        def __init__(self, rows: list[tuple[str]]) -> None:
            self.rows = rows

        def fetchone(self) -> tuple[str] | None:
            return self.rows[0] if self.rows else None

        def fetchall(self) -> list[tuple[str]]:
            return revisions

    class Connection:
        def __enter__(self) -> Connection:
            if connect_failure:
                raise OSError("synthetic database diagnostic")
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def execute(self, _statement: Any) -> Result:
            return Result([database_row] if database_row else [])

    monkeypatch.setattr(
        backup_db.psycopg, "connect", lambda *_args, **_kwargs: Connection()
    )

    with pytest.raises(backup_db.BackupArtifactError, match=message):
        backup_db.source_database_metadata("postgresql://localhost/source")


def test_restore_target_and_catalog_failures_do_not_expose_database_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for bad_target in ["restore_", "restore_" + "x" * 55]:
        with pytest.raises(backup_db.BackupArtifactError, match="restore_<name>"):
            backup_db.validate_restore_target("source", bad_target)

    class Connection:
        def __enter__(self) -> Connection:
            raise OSError("synthetic connection password marker")

        def __exit__(self, *_args: Any) -> None:
            return None

    monkeypatch.setattr(
        backup_db.psycopg,
        "connect",
        lambda *_args, **_kwargs: Connection(),
    )

    with pytest.raises(
        backup_db.BackupArtifactError, match="Unable to create"
    ) as error:
        backup_db._ensure_new_database(
            "postgresql://admin:synthetic-password@localhost/postgres",  # pragma: allowlist secret -- synthetic backup authentication fixture
            "restore_sandbox",
        )
    assert "synthetic connection password marker" not in str(error.value)


def test_restore_archive_rejects_missing_or_unreadable_archive_before_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "not-created.dump"
    manifest = backup_db.create_manifest(
        _archive(tmp_path),
        source_database="synthetic_source",
        source_revision=("synthetic_revision",),
        artifact_key="synthetic/backup.dump",
    )
    monkeypatch.setattr(
        backup_db.psycopg,
        "connect",
        lambda *_args, **_kwargs: pytest.fail("invalid archive reached database"),
    )
    with pytest.raises(backup_db.BackupArtifactError, match="unavailable"):
        backup_db.restore_archive(
            archive,
            manifest,
            "postgresql://admin@localhost/postgres",
            "restore_sandbox",
        )


def test_restore_archive_sanitizes_archive_read_errors_before_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = _archive(tmp_path)
    manifest = _manifest(archive)
    monkeypatch.setattr(
        backup_db,
        "sha256_file",
        lambda _path: (_ for _ in ()).throw(OSError("synthetic read failure")),
    )
    monkeypatch.setattr(
        backup_db.psycopg,
        "connect",
        lambda *_args, **_kwargs: pytest.fail("unverified archive reached database"),
    )

    with pytest.raises(
        backup_db.BackupArtifactError, match="Unable to verify"
    ) as error:
        backup_db.restore_archive(
            archive,
            manifest,
            "postgresql://admin@localhost/postgres",
            "restore_sandbox",
        )
    assert "synthetic read failure" not in str(error.value)


def test_restore_archive_rejects_non_manifest_object_before_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = _archive(tmp_path)
    monkeypatch.setattr(
        backup_db.psycopg,
        "connect",
        lambda *_args, **_kwargs: pytest.fail("invalid manifest reached database"),
    )

    with pytest.raises(backup_db.BackupArtifactError, match="invalid"):
        backup_db.restore_archive(
            archive,
            None,  # type: ignore[arg-type]
            "postgresql://admin@localhost/postgres",
            "restore_sandbox",
        )


@pytest.mark.parametrize(
    ("endpoint", "allow_http", "message"),
    [
        ("", "false", "must be set"),
        (
            "https://user:pass@s3.example.test",  # pragma: allowlist secret
            "false",  # pragma: allowlist secret
            "without credentials",  # pragma: allowlist secret
        ),
        ("https://s3.example.test?token=synthetic", "false", "without credentials"),
        ("ftp://s3.example.test", "false", "without credentials"),
        ("http://s3.example.test", "true", "restricted"),
        ("https://s3.example.test", "false", "Invalid S3"),
    ],
)
def test_s3_settings_reject_unsafe_endpoint_or_bucket(
    monkeypatch: pytest.MonkeyPatch,
    endpoint: str,
    allow_http: str,
    message: str,
) -> None:
    monkeypatch.setenv("BACKUP_S3_ENDPOINT_URL", endpoint)
    monkeypatch.setenv("BACKUP_S3_BUCKET", "synthetic-bucket")
    monkeypatch.setenv("BACKUP_S3_ALLOW_HTTP_FOR_LOCAL_DEV", allow_http)
    if endpoint == "https://s3.example.test":
        monkeypatch.setenv("BACKUP_S3_PREFIX", "bad//prefix")
    with pytest.raises(backup_db.BackupArtifactError, match=message):
        backup_db.s3_settings_from_environment()


def test_s3_http_accepts_ipv4_mapped_private_ipv6_and_normalizes_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BACKUP_S3_ENDPOINT_URL", "http://[::ffff:10.20.30.40]:9000")
    monkeypatch.setenv("BACKUP_S3_BUCKET", "synthetic-bucket")
    monkeypatch.setenv("BACKUP_S3_ALLOW_HTTP_FOR_LOCAL_DEV", "true")
    monkeypatch.setenv("BACKUP_S3_PREFIX", "///")
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)

    settings = backup_db.s3_settings_from_environment()
    assert settings.region == "us-east-1"
    assert settings.prefix == ""


@pytest.mark.asyncio
async def test_s3_client_sanitizes_setup_errors_and_preserves_contract_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = backup_db.S3Settings(
        endpoint_url="https://s3.example.test",
        bucket="synthetic",
        prefix="synthetic",
        region="test",
    )

    class SessionFails:
        def __init__(self) -> None:
            raise OSError("synthetic credential material")

    monkeypatch.setattr(backup_db.aioboto3, "Session", SessionFails)
    with pytest.raises(backup_db.BackupArtifactError, match="initialize") as error:
        async with backup_db.s3_client(settings):
            pytest.fail("failed client unexpectedly yielded")
    assert "synthetic credential material" not in str(error.value)

    client = object()

    class SuccessContext:
        async def __aenter__(self) -> object:
            return client

        async def __aexit__(self, *_args: Any) -> None:
            return None

    class SessionWorks:
        def client(self, *_args: Any, **_kwargs: Any) -> SuccessContext:
            return SuccessContext()

    monkeypatch.setattr(backup_db.aioboto3, "Session", SessionWorks)
    async with backup_db.s3_client(settings) as yielded:
        assert yielded is client

    class ContractFailureContext:
        async def __aenter__(self) -> object:
            raise backup_db.BackupArtifactError("synthetic contract failure")

        async def __aexit__(self, *_args: Any) -> None:
            return None

    class SessionReturnsContractFailure:
        def client(self, *_args: Any, **_kwargs: Any) -> ContractFailureContext:
            return ContractFailureContext()

    monkeypatch.setattr(backup_db.aioboto3, "Session", SessionReturnsContractFailure)
    with pytest.raises(
        backup_db.BackupArtifactError, match="synthetic contract failure"
    ):
        async with backup_db.s3_client(settings):
            pytest.fail("failed context unexpectedly yielded")


@pytest.mark.asyncio
async def test_backup_workflow_publishes_only_after_stable_source_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_urls: list[str] = []
    revisions = iter(
        [
            ("synthetic_source", ("synthetic_revision",)),
            ("synthetic_source", ("synthetic_revision",)),
        ]
    )

    def metadata(url: str) -> tuple[str, tuple[str, ...]]:
        observed_urls.append(url)
        return next(revisions)

    def dump(url: str, path: Path) -> None:
        assert url == "postgresql://backup@localhost/source"
        path.write_bytes(b"synthetic dump")

    class Client:
        async def upload_file(self, filename: str, bucket: str, key: str) -> None:
            del filename, bucket, key

        async def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
            del Bucket, Key
            raise AssertionError("backup tests must not use real S3")

    client = Client()

    class ClientContext:
        async def __aenter__(self) -> Client:
            return client

        async def __aexit__(self, *_args: Any) -> None:
            return None

    monkeypatch.setattr(backup_db, "source_database_metadata", metadata)
    monkeypatch.setattr(backup_db, "dump_database", dump)
    monkeypatch.setattr(
        backup_db,
        "s3_client",
        lambda _settings: ClientContext(),
    )

    async def publish(
        _client: Any, _bucket: str, _path: Path, manifest: backup_db.BackupManifest
    ) -> str:
        assert manifest.source_database == "synthetic_source"
        assert manifest.source_revision == ("synthetic_revision",)
        return backup_db.manifest_key(manifest.artifact_key)

    monkeypatch.setattr(backup_db, "publish_backup", publish)
    settings = backup_db.S3Settings(
        endpoint_url="https://s3.example.test",
        bucket="synthetic-bucket",
        prefix="synthetic",
        region="test",
    )

    result = await backup_db.backup_to_s3(
        "postgresql://backup@localhost/source", settings
    )
    assert result.startswith("synthetic/university-")
    assert result.endswith(backup_db.MANIFEST_SUFFIX)
    assert len(observed_urls) == 2


def test_environment_value_rejects_invalid_name_and_missing_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MISSING_BACKUP_ENV", raising=False)
    with pytest.raises(backup_db.BackupArtifactError, match="name is invalid"):
        backup_db._environment_value("DATABASE-URL")
    with pytest.raises(backup_db.BackupArtifactError, match="is not set"):
        backup_db._environment_value("MISSING_BACKUP_ENV")


def test_cli_no_arguments_defaults_to_backup_and_restore_success_is_reported(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = backup_db.S3Settings("https://s3.example.test", "synthetic", "", "test")
    monkeypatch.setattr(backup_db, "s3_settings_from_environment", lambda: settings)
    monkeypatch.setenv("DATABASE_URL", "postgresql://backup@localhost/source")
    monkeypatch.setenv(
        "BACKUP_RESTORE_ADMIN_DATABASE_URL",
        "postgresql://admin@localhost/postgres",
    )

    async def backup(_url: str, _settings: backup_db.S3Settings) -> str:
        return "synthetic/default.manifest.json"

    async def restore(*_args: Any) -> None:
        return None

    monkeypatch.setattr(backup_db, "backup_to_s3", backup)
    assert backup_db.main([]) == 0
    assert "synthetic/default.manifest.json" in capsys.readouterr().out

    monkeypatch.setattr(backup_db, "restore_from_s3", restore)
    result = backup_db.main(
        [
            "restore",
            "--manifest-key",
            "synthetic/backup.manifest.json",
            "--target-database",
            "restore_sandbox",
        ]
    )
    output = capsys.readouterr()
    assert result == 0
    assert "Restore completed into new database restore_sandbox" in output.out


def test_main_fails_closed_if_parser_returns_unknown_operation(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class InconsistentParser:
        def parse_args(self, _arguments: list[str]) -> SimpleNamespace:
            return SimpleNamespace(operation="unknown")

        def error(self, _message: str) -> None:
            raise backup_db.BackupArtifactError("Invalid command-line arguments")

    monkeypatch.setattr(backup_db, "build_parser", lambda: InconsistentParser())
    monkeypatch.setattr(
        backup_db,
        "s3_settings_from_environment",
        lambda: backup_db.S3Settings(
            "https://s3.example.test", "synthetic", "", "test"
        ),
    )

    assert backup_db.main(["synthetic-accepted-argument"]) == 1
    assert "Invalid command-line arguments" in capsys.readouterr().err


def test_module_entrypoint_routes_help_without_starting_backup(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["backup_db.py", "--help"])
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(str(Path(backup_db.__file__)), run_name="__main__")

    assert exit_info.value.code == 0
    assert (
        "Create and restore verified PostgreSQL backup artifacts"
        in capsys.readouterr().out
    )


def test_cli_backup_success_uses_environment_and_prints_only_manifest_key(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    marker = "synthetic-cli-password-marker"
    monkeypatch.setenv(
        "CUSTOM_DATABASE_URL",
        f"postgresql://backup:{marker}@localhost/source",
    )
    monkeypatch.setattr(
        backup_db,
        "s3_settings_from_environment",
        lambda: backup_db.S3Settings(
            "https://s3.example.test", "synthetic", "", "test"
        ),
    )

    async def backup(database_url: str, _settings: backup_db.S3Settings) -> str:
        assert marker in database_url
        return "synthetic/backup.dump.manifest.json"

    monkeypatch.setattr(backup_db, "backup_to_s3", backup)
    result = backup_db.main(["backup", "--database-url-env", "CUSTOM_DATABASE_URL"])
    output = capsys.readouterr()

    assert result == 0
    assert "synthetic/backup.dump.manifest.json" in output.out
    assert marker not in output.out + output.err


def test_cli_reports_internal_failures_without_exception_details(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    marker = "synthetic-internal-secret-marker"
    monkeypatch.setattr(
        backup_db,
        "s3_settings_from_environment",
        lambda: (_ for _ in ()).throw(RuntimeError(marker)),
    )

    assert backup_db.main(["backup"]) == 1
    output = capsys.readouterr()
    assert "diagnostic details are suppressed" in output.err
    assert marker not in output.out + output.err


def test_restore_database_preflight_sanitizes_connector_failure() -> None:
    def reject_connection(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("synthetic diagnostic detail")

    with pytest.raises(
        backup_db.BackupArtifactError,
        match="Unable to verify that the restore database target is absent",
    ) as error:
        backup_db._require_absent_restore_database(
            "postgresql://restore_admin@localhost/postgres",
            "restore_sandbox",
            connect=reject_connection,
        )

    assert "synthetic diagnostic detail" not in str(error.value)


def _configured_storage_settings(**changes: Any) -> SimpleNamespace:
    values: dict[str, Any] = {
        "storage_backend": "s3",
        "storage_s3_endpoint_url": "https://objects.example.test",
        "storage_s3_bucket": "synthetic-uploads",
        "storage_s3_region": "eu-test-1",
        "storage_s3_access_key_id": "",
        "storage_s3_secret_access_key": "",
        "storage_s3_base_url": "",
    }
    values.update(changes)
    return SimpleNamespace(**values)


def _write_storage_env_file(path: Path, *, bucket: str) -> None:
    access_key = secrets.token_urlsafe(16)
    secret_key = secrets.token_urlsafe(24)
    path.write_text(
        "\n".join(
            (
                "STORAGE_BACKEND=minio",
                f"STORAGE_S3_BUCKET={bucket}",
                "STORAGE_S3_REGION=eu-test-1",
                f"STORAGE_S3_ACCESS_KEY_ID={access_key}",
                f"STORAGE_S3_SECRET_ACCESS_KEY={secret_key}",
                "STORAGE_S3_ENDPOINT_URL=https://objects.example.test",
                "STORAGE_S3_BASE_URL=https://cdn.example.test/api/v1/img",
            )
        ),
        encoding="utf-8",
    )


def test_storage_cli_reader_uses_project_dotenv_and_environment_precedence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project_root = tmp_path / "project"
    scripts_dir = project_root / "scripts"
    scripts_dir.mkdir(parents=True)
    monkeypatch.setattr(backup_db, "__file__", str(scripts_dir / "backup_db.py"))
    _write_storage_env_file(project_root / ".env", bucket="project-bucket")
    _write_storage_env_file(project_root / ".env.local", bucket="local-bucket")
    for name in (
        "STORAGE_BACKEND",
        "STORAGE_S3_BUCKET",
        "STORAGE_S3_REGION",
        "STORAGE_S3_ACCESS_KEY_ID",
        "STORAGE_S3_SECRET_ACCESS_KEY",
        "STORAGE_S3_ENDPOINT_URL",
        "STORAGE_S3_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("ENV_FILE_PATH", raising=False)
    monkeypatch.setenv("STORAGE_S3_BUCKET", "process-bucket")

    original_import = builtins.__import__

    def reject_application_config(
        name: str,
        globals: dict[str, Any] | None = None,
        locals: dict[str, Any] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        if name == "app.core.config" or name.startswith("app.core.config."):
            raise AssertionError("storage CLI must not import global app settings")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", reject_application_config)
    settings = backup_db.storage_s3_settings_from_environment()

    assert settings.bucket == "process-bucket"
    assert settings.region == "eu-test-1"
    assert settings.endpoint_url == "https://objects.example.test"
    assert settings.public_base_url == "https://cdn.example.test/api/v1/img"
    assert settings.access_key_id is not None
    assert settings.secret_access_key is not None


def test_storage_cli_reader_honors_explicit_env_file_and_empty_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project_root = tmp_path / "project"
    scripts_dir = project_root / "scripts"
    scripts_dir.mkdir(parents=True)
    monkeypatch.setattr(backup_db, "__file__", str(scripts_dir / "backup_db.py"))
    _write_storage_env_file(project_root / ".env", bucket="project-bucket")
    selected_file = tmp_path / "selected.env"
    _write_storage_env_file(selected_file, bucket="selected-bucket")
    for name in (
        "STORAGE_BACKEND",
        "STORAGE_S3_BUCKET",
        "STORAGE_S3_REGION",
        "STORAGE_S3_ACCESS_KEY_ID",
        "STORAGE_S3_SECRET_ACCESS_KEY",
        "STORAGE_S3_ENDPOINT_URL",
        "STORAGE_S3_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)

    monkeypatch.setenv("ENV_FILE_PATH", str(selected_file))
    assert backup_db.storage_s3_settings_from_environment().bucket == "selected-bucket"

    monkeypatch.setenv("ENV_FILE_PATH", "")
    with pytest.raises(backup_db.BackupArtifactError, match="S3 storage backend"):
        backup_db.storage_s3_settings_from_environment()


def test_storage_cli_reader_falls_back_to_project_env_local(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project_root = tmp_path / "project"
    scripts_dir = project_root / "scripts"
    scripts_dir.mkdir(parents=True)
    monkeypatch.setattr(backup_db, "__file__", str(scripts_dir / "backup_db.py"))
    _write_storage_env_file(project_root / ".env.local", bucket="local-only-bucket")
    for name in (
        "STORAGE_BACKEND",
        "STORAGE_S3_BUCKET",
        "STORAGE_S3_REGION",
        "STORAGE_S3_ACCESS_KEY_ID",
        "STORAGE_S3_SECRET_ACCESS_KEY",
        "STORAGE_S3_ENDPOINT_URL",
        "STORAGE_S3_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("ENV_FILE_PATH", raising=False)

    settings = backup_db.storage_s3_settings_from_environment()

    assert settings.bucket == "local-only-bucket"
    assert settings.region == "eu-test-1"


def test_storage_cli_reader_does_not_fallback_for_missing_explicit_env_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project_root = tmp_path / "project"
    scripts_dir = project_root / "scripts"
    scripts_dir.mkdir(parents=True)
    monkeypatch.setattr(backup_db, "__file__", str(scripts_dir / "backup_db.py"))
    _write_storage_env_file(project_root / ".env", bucket="project-bucket")
    missing_file = tmp_path / "missing.env"
    for name in (
        "STORAGE_BACKEND",
        "STORAGE_S3_BUCKET",
        "STORAGE_S3_REGION",
        "STORAGE_S3_ACCESS_KEY_ID",
        "STORAGE_S3_SECRET_ACCESS_KEY",
        "STORAGE_S3_ENDPOINT_URL",
        "STORAGE_S3_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ENV_FILE_PATH", str(missing_file))

    with pytest.raises(backup_db.BackupArtifactError, match="S3 storage backend"):
        backup_db.storage_s3_settings_from_environment()


def test_storage_cli_reader_normalizes_backend_like_application_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENV_FILE_PATH", "")
    monkeypatch.setenv("STORAGE_BACKEND", " MiNiO ")
    monkeypatch.setenv("STORAGE_S3_BUCKET", "normalized-bucket")
    monkeypatch.setenv("STORAGE_S3_REGION", "eu-test-1")
    monkeypatch.setenv("STORAGE_S3_ACCESS_KEY_ID", secrets.token_urlsafe(16))
    monkeypatch.setenv("STORAGE_S3_SECRET_ACCESS_KEY", secrets.token_urlsafe(24))
    monkeypatch.setenv("STORAGE_S3_ENDPOINT_URL", "https://objects.example.test")
    monkeypatch.setenv("STORAGE_S3_BASE_URL", "https://cdn.example.test/api/v1/img")

    settings = backup_db.storage_s3_settings_from_environment()

    assert settings.bucket == "normalized-bucket"
    assert settings.endpoint_url == "https://objects.example.test"


def test_storage_cli_reader_preserves_backend_enum_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENV_FILE_PATH", "")
    monkeypatch.setenv("STORAGE_BACKEND", "unsupported-backend")

    with pytest.raises(ValidationError, match="STORAGE_BACKEND must be one of"):
        backup_db.storage_s3_settings_from_environment()


def test_application_s3_settings_reject_unpaired_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        backup_db,
        "_backup_storage_environment_settings",
        lambda: _configured_storage_settings(storage_s3_access_key_id="synthetic-id"),
    )

    with pytest.raises(backup_db.BackupArtifactError, match="configured together"):
        backup_db.storage_s3_settings_from_environment()


def test_application_s3_settings_default_optional_endpoint_and_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        backup_db,
        "_backup_storage_environment_settings",
        lambda: _configured_storage_settings(
            storage_s3_endpoint_url=" ", storage_s3_region=" "
        ),
    )

    settings = backup_db.storage_s3_settings_from_environment()

    assert settings.endpoint_url is None
    assert settings.region == "us-east-1"


@pytest.mark.parametrize(
    ("endpoint", "allow_http", "message"),
    [
        ("ftp://objects.example.test", "true", "endpoint must"),
        ("http://objects.example.test", "false", "restricted"),
        ("http://objects.example.test", "true", "restricted"),
    ],
)
def test_application_s3_settings_reject_unsafe_endpoints(
    monkeypatch: pytest.MonkeyPatch,
    endpoint: str,
    allow_http: str,
    message: str,
) -> None:
    monkeypatch.setattr(
        backup_db,
        "_backup_storage_environment_settings",
        lambda: _configured_storage_settings(storage_s3_endpoint_url=endpoint),
    )
    monkeypatch.setenv("BACKUP_S3_ALLOW_HTTP_FOR_LOCAL_DEV", allow_http)

    with pytest.raises(backup_db.BackupArtifactError, match=message):
        backup_db.storage_s3_settings_from_environment()


def test_application_s3_settings_allow_explicit_local_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        backup_db,
        "_backup_storage_environment_settings",
        lambda: _configured_storage_settings(
            storage_s3_endpoint_url="http://127.0.0.1:9000"
        ),
    )
    monkeypatch.setenv("BACKUP_S3_ALLOW_HTTP_FOR_LOCAL_DEV", "true")

    assert (
        backup_db.storage_s3_settings_from_environment().endpoint_url
        == "http://127.0.0.1:9000"
    )


@pytest.mark.asyncio
async def test_s3_client_passes_optional_endpoint_and_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[dict[str, Any]] = []
    client = object()

    class ClientContext:
        async def __aenter__(self) -> object:
            return client

        async def __aexit__(self, *_args: Any) -> None:
            return None

    class Session:
        def client(self, service: str, **options: Any) -> ClientContext:
            assert service == "s3"
            captured.append(options)
            return ClientContext()

    monkeypatch.setattr(backup_db.aioboto3, "Session", Session)
    generated_value = bytes(range(32)).hex()
    settings = backup_db.S3Settings(
        endpoint_url=None,
        bucket="synthetic-uploads",
        prefix="",
        region="test-region",
        access_key_id="credential-one",
        secret_access_key=generated_value,
    )

    async with backup_db.s3_client(settings) as yielded:
        assert yielded is client

    assert captured == [
        {
            "region_name": "test-region",
            "aws_access_key_id": "credential-one",
            "aws_secret_access_key": generated_value,
        }
    ]


@pytest.mark.parametrize("version_id", [None, "", "null"])
def test_s3_response_version_id_treats_absent_markers_as_unversioned(
    version_id: Any,
) -> None:
    assert backup_db._response_version_id({"VersionId": version_id}) is None


@pytest.mark.parametrize("version_id", [1, "x" * 1025])
def test_s3_response_version_id_rejects_invalid_values(version_id: Any) -> None:
    with pytest.raises(backup_db.BackupArtifactError, match="invalid object version"):
        backup_db._response_version_id({"VersionId": version_id})


def test_s3_response_etag_requires_a_stable_validator() -> None:
    with pytest.raises(backup_db.BackupArtifactError, match="validator"):
        backup_db._response_etag({})


@pytest.mark.asyncio
async def test_pinned_s3_reads_require_a_validator_and_sanitize_failures() -> None:
    with pytest.raises(
        backup_db.BackupArtifactError, match="no immutable read validator"
    ):
        await backup_db._get_pinned_object(object(), "synthetic", "snapshot.dump")

    class FailingClient:
        async def get_object(self, **_kwargs: Any) -> dict[str, Any]:
            raise OSError("synthetic transport detail")

    with pytest.raises(
        backup_db.BackupArtifactError,
        match="Unable to retrieve a pinned snapshot object",
    ) as error:
        await backup_db._get_pinned_object(
            FailingClient(), "synthetic", "snapshot.dump", etag='"stable"'
        )

    assert "synthetic transport detail" not in str(error.value)
