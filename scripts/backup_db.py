"""Create and restore verified PostgreSQL backup artifacts.

Connection URLs and S3 credentials are read only from the environment. The
manifest deliberately records database name and Alembic revisions, never host,
user, or password.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import inspect
import ipaddress
import json
import os
import re
import subprocess  # nosec B404
import sys
import tempfile
import uuid
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager, suppress
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Never, cast

import aioboto3
import psycopg
from sqlalchemy.engine import URL, make_url

MANIFEST_SCHEMA_VERSION = 1
MANIFEST_MAX_BYTES = 64 * 1024
PAIRED_SNAPSHOT_SCHEMA_VERSION = 2
PAIRED_SNAPSHOT_MANIFEST_MAX_BYTES = 64 * 1024 * 1024
MAX_SNAPSHOT_OBJECTS = 100_000
SNAPSHOT_PART_SIZE = 8 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024
FORMAT = "pg_dump.custom"
ARTIFACT_SUFFIX = ".dump"
MANIFEST_SUFFIX = ".manifest.json"
_RESTORE_DATABASE_RE = re.compile(r"^restore_[a-z0-9_]{1,54}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SNAPSHOT_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_BUCKET_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
_LOCAL_DEV_S3_HOSTS = frozenset({"localhost", "minio", "seaweedfs"})
_LOCAL_DEV_S3_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "fc00::/7",
    )
)
_PG_URL_OPTIONS = {
    "application_name": "PGAPPNAME",
    "channel_binding": "PGCHANNELBINDING",
    "connect_timeout": "PGCONNECT_TIMEOUT",
    "keepalives": "PGKEEPALIVES",
    "keepalives_count": "PGKEEPALIVES_COUNT",
    "keepalives_idle": "PGKEEPALIVES_IDLE",
    "keepalives_interval": "PGKEEPALIVES_INTERVAL",
    "options": "PGOPTIONS",
    "sslcert": "PGSSLCERT",
    "sslkey": "PGSSLKEY",
    "sslmode": "PGSSLMODE",
    "sslrootcert": "PGSSLROOTCERT",
    "target_session_attrs": "PGTARGETSESSIONATTRS",
}
_PG_ENV_FALLBACKS = (
    "PGHOST",
    "PGPORT",
    "PGUSER",
    "PGPASSWORD",
    "PGPASSFILE",
    "PGSERVICE",
    "PGSERVICEFILE",
    "PGSSLMODE",
    "PGSSLROOTCERT",
    "PGSSLCERT",
    "PGSSLKEY",
    "PGAPPNAME",
    "PGCONNECT_TIMEOUT",
    "PGOPTIONS",
    "PGTARGETSESSIONATTRS",
    "PGCHANNELBINDING",
)
_SYSTEM_ENV = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")


class BackupArtifactError(RuntimeError):
    """A backup or restore operation cannot safely continue."""


class SafeArgumentParser(argparse.ArgumentParser):
    """Do not echo unrecognized arguments that could contain credentials."""

    def error(self, message: str) -> Never:
        del message
        raise BackupArtifactError("Invalid command-line arguments") from None


@dataclass(frozen=True)
class BackupManifest:
    schema_version: int
    source_database: str
    source_revision: tuple[str, ...]
    created_at: str
    format: str
    artifact_key: str
    size_bytes: int
    sha256: str

    def to_json_bytes(self) -> bytes:
        return (
            json.dumps(
                asdict(self),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            )
            + "\n"
        ).encode("utf-8")


@dataclass(frozen=True)
class SnapshotObjectManifest:
    source_key: str
    source_version_id: str | None
    archive_key: str
    archive_version_id: str | None
    archive_etag: str
    size_bytes: int
    sha256: str
    content_type: str | None
    content_encoding: str | None
    cache_control: str | None
    content_disposition: str | None


@dataclass(frozen=True)
class PairedSnapshotManifest:
    snapshot_id: str
    consistency_mode: str
    quiescence_confirmed: bool
    quiescence_confirmed_at: str
    source_object_bucket: str
    database: BackupManifest
    database_archive_version_id: str | None
    database_archive_etag: str
    objects: tuple[SnapshotObjectManifest, ...]

    def to_json_bytes(self) -> bytes:
        data = asdict(self)
        data["schema_version"] = PAIRED_SNAPSHOT_SCHEMA_VERSION
        return (
            json.dumps(
                data,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            )
            + "\n"
        ).encode("utf-8")


@dataclass(frozen=True)
class S3ObjectReceipt:
    version_id: str | None
    etag: str


def _validate_object_key(key: str) -> None:
    if (
        not isinstance(key, str)
        or not key
        or len(key) > 1024
        or key.startswith("/")
        or "\\" in key
        or any(part in ("", ".", "..") for part in key.split("/"))
    ):
        raise BackupArtifactError("Invalid S3 object key")
    try:
        encoded_length = len(key.encode("utf-8"))
    except UnicodeEncodeError:
        raise BackupArtifactError("Invalid S3 object key") from None
    if encoded_length > 1024:
        raise BackupArtifactError("Invalid S3 object key")


def manifest_key(artifact_key: str) -> str:
    _validate_object_key(artifact_key)
    if not artifact_key.endswith(ARTIFACT_SUFFIX):
        raise BackupArtifactError("Artifact key must name a custom-format dump")
    key = artifact_key[: -len(ARTIFACT_SUFFIX)] + MANIFEST_SUFFIX
    _validate_object_key(key)
    return key


def new_artifact_key(prefix: str = "database") -> str:
    if prefix:
        _validate_object_key(prefix)
        prefix = prefix.rstrip("/")
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    name = f"university-{timestamp}-{uuid.uuid4().hex}{ARTIFACT_SUFFIX}"
    key = f"{prefix}/{name}" if prefix else name
    # A published archive always has a sibling manifest; reserve space for it.
    manifest_key(key)
    return key


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_manifest(
    archive_path: Path,
    *,
    source_database: str,
    source_revision: Sequence[str],
    artifact_key: str,
    created_at: datetime | None = None,
) -> BackupManifest:
    _validate_object_key(artifact_key)
    if not artifact_key.endswith(ARTIFACT_SUFFIX):
        raise BackupArtifactError("Artifact key must name a custom-format dump")
    if not source_database or len(source_database) > 63:
        raise BackupArtifactError("Invalid source database name")
    revisions = tuple(source_revision)
    if not revisions or any(not value or len(value) > 255 for value in revisions):
        raise BackupArtifactError("Source Alembic revision is missing")
    timestamp = created_at or datetime.now(UTC)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise BackupArtifactError("Manifest timestamp must be timezone-aware")
    timestamp = timestamp.astimezone(UTC).replace(microsecond=0)
    size = archive_path.stat().st_size
    if size <= 0:
        raise BackupArtifactError("Database dump is empty")
    return BackupManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        source_database=source_database,
        source_revision=revisions,
        created_at=timestamp.isoformat(timespec="seconds").replace("+00:00", "Z"),
        format=FORMAT,
        artifact_key=artifact_key,
        size_bytes=size,
        sha256=sha256_file(archive_path),
    )


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BackupArtifactError("Manifest contains duplicate fields")
        result[key] = value
    return result


def parse_manifest(payload: bytes, *, expected_manifest_key: str) -> BackupManifest:
    _validate_object_key(expected_manifest_key)
    if not expected_manifest_key.endswith(MANIFEST_SUFFIX):
        raise BackupArtifactError("Manifest key has an invalid suffix")
    if len(payload) > MANIFEST_MAX_BYTES:
        raise BackupArtifactError("Manifest is too large")
    try:
        data = json.loads(payload, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise BackupArtifactError("Manifest is not valid JSON") from None
    if not isinstance(data, dict):
        raise BackupArtifactError("Manifest must be a JSON object")
    expected_fields = {
        "schema_version",
        "source_database",
        "source_revision",
        "created_at",
        "format",
        "artifact_key",
        "size_bytes",
        "sha256",
    }
    if set(data) != expected_fields:
        raise BackupArtifactError("Manifest fields do not match the supported schema")
    if (
        type(data["schema_version"]) is not int
        or data["schema_version"] != MANIFEST_SCHEMA_VERSION
    ):
        raise BackupArtifactError("Unsupported manifest schema version")
    if data["format"] != FORMAT:
        raise BackupArtifactError("Unsupported backup format")
    source_database = data["source_database"]
    if (
        not isinstance(source_database, str)
        or not source_database
        or len(source_database) > 63
    ):
        raise BackupArtifactError("Manifest source database is invalid")
    revisions = data["source_revision"]
    if (
        not isinstance(revisions, list)
        or not revisions
        or any(
            not isinstance(value, str) or not value or len(value) > 255
            for value in revisions
        )
    ):
        raise BackupArtifactError("Manifest source revision is invalid")
    created_at = data["created_at"]
    if not isinstance(created_at, str):
        raise BackupArtifactError("Manifest timestamp is invalid")
    try:
        parsed_timestamp = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        raise BackupArtifactError("Manifest timestamp is invalid") from None
    if parsed_timestamp.utcoffset() != UTC.utcoffset(parsed_timestamp):
        raise BackupArtifactError("Manifest timestamp must be UTC")
    artifact_key = data["artifact_key"]
    _validate_object_key(artifact_key)
    if (
        not artifact_key.endswith(ARTIFACT_SUFFIX)
        or manifest_key(artifact_key) != expected_manifest_key
    ):
        raise BackupArtifactError("Manifest artifact key does not match its object key")
    size = data["size_bytes"]
    if type(size) is not int or size <= 0:
        raise BackupArtifactError("Manifest size is invalid")
    checksum = data["sha256"]
    if not isinstance(checksum, str) or not _SHA256_RE.fullmatch(checksum):
        raise BackupArtifactError("Manifest checksum is invalid")
    return BackupManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        source_database=source_database,
        source_revision=tuple(revisions),
        created_at=created_at,
        format=FORMAT,
        artifact_key=artifact_key,
        size_bytes=size,
        sha256=checksum,
    )


def _validate_bucket_name(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not _BUCKET_NAME_RE.fullmatch(value)
        or ".." in value
    ):
        raise BackupArtifactError("Snapshot bucket name is invalid")
    return value


def _manifest_version_id(value: Any, *, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > 1024:
        raise BackupArtifactError(f"Snapshot {label} is invalid")
    if "\r" in value or "\n" in value:
        raise BackupArtifactError(f"Snapshot {label} is invalid")
    return value


def _manifest_etag(value: Any, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 256
        or "\r" in value
        or "\n" in value
    ):
        raise BackupArtifactError(f"Snapshot {label} is invalid")
    return value


def _manifest_header(value: Any, *, label: str) -> str | None:
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or len(value) > 2048
        or "\r" in value
        or "\n" in value
    ):
        raise BackupArtifactError(f"Snapshot {label} is invalid")
    return value


def _parse_utc_timestamp(value: Any, *, label: str) -> str:
    if not isinstance(value, str):
        raise BackupArtifactError(f"Snapshot {label} is invalid")
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise BackupArtifactError(f"Snapshot {label} is invalid") from None
    if timestamp.utcoffset() != UTC.utcoffset(timestamp):
        raise BackupArtifactError(f"Snapshot {label} must be UTC")
    return value


def _snapshot_root(database_artifact_key: str, snapshot_id: str) -> str:
    parts = database_artifact_key.split("/")
    if (
        len(parts) < 3
        or parts[-1] != "database.dump"
        or parts[-2] != snapshot_id
        or parts[-3] != "snapshots"
    ):
        raise BackupArtifactError("Snapshot database key does not match its id")
    return "/".join(parts[:-1])


def parse_paired_snapshot_manifest(
    payload: bytes, *, expected_manifest_key: str
) -> PairedSnapshotManifest:
    _validate_object_key(expected_manifest_key)
    if not expected_manifest_key.endswith(MANIFEST_SUFFIX):
        raise BackupArtifactError("Snapshot manifest key has an invalid suffix")
    if len(payload) > PAIRED_SNAPSHOT_MANIFEST_MAX_BYTES:
        raise BackupArtifactError("Snapshot manifest is too large")
    try:
        data = json.loads(payload, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise BackupArtifactError("Snapshot manifest is not valid JSON") from None
    expected_fields = {
        "schema_version",
        "snapshot_id",
        "consistency_mode",
        "quiescence_confirmed",
        "quiescence_confirmed_at",
        "source_object_bucket",
        "database",
        "database_archive_version_id",
        "database_archive_etag",
        "objects",
    }
    if not isinstance(data, dict) or set(data) != expected_fields:
        raise BackupArtifactError("Snapshot manifest fields do not match the schema")
    if (
        type(data["schema_version"]) is not int
        or data["schema_version"] != PAIRED_SNAPSHOT_SCHEMA_VERSION
    ):
        raise BackupArtifactError("Unsupported paired snapshot schema version")
    snapshot_id = data["snapshot_id"]
    if not isinstance(snapshot_id, str) or not _SNAPSHOT_ID_RE.fullmatch(snapshot_id):
        raise BackupArtifactError("Snapshot id is invalid")
    if data["consistency_mode"] != "operator_quiesced":
        raise BackupArtifactError("Snapshot consistency mode is unsupported")
    if data["quiescence_confirmed"] is not True:
        raise BackupArtifactError("Snapshot lacks operator quiescence confirmation")
    quiescence_confirmed_at = _parse_utc_timestamp(
        data["quiescence_confirmed_at"], label="quiescence timestamp"
    )
    source_bucket = _validate_bucket_name(data["source_object_bucket"])
    database_payload = json.dumps(
        data["database"], sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    database_manifest = parse_manifest(
        database_payload, expected_manifest_key=expected_manifest_key
    )
    root = _snapshot_root(database_manifest.artifact_key, snapshot_id)
    database_version_id = _manifest_version_id(
        data["database_archive_version_id"], label="database version id"
    )
    database_etag = _manifest_etag(
        data["database_archive_etag"], label="database archive ETag"
    )
    raw_objects = data["objects"]
    if not isinstance(raw_objects, list) or len(raw_objects) > MAX_SNAPSHOT_OBJECTS:
        raise BackupArtifactError("Snapshot object inventory is invalid")
    expected_object_fields = {
        "source_key",
        "source_version_id",
        "archive_key",
        "archive_version_id",
        "archive_etag",
        "size_bytes",
        "sha256",
        "content_type",
        "content_encoding",
        "cache_control",
        "content_disposition",
    }
    objects: list[SnapshotObjectManifest] = []
    seen_source_keys: set[str] = set()
    seen_archive_artifacts: dict[str, tuple[int, str | None, str]] = {}
    for raw_object in raw_objects:
        if (
            not isinstance(raw_object, dict)
            or set(raw_object) != expected_object_fields
        ):
            raise BackupArtifactError("Snapshot object entry is invalid")
        source_key = raw_object["source_key"]
        _validate_object_key(source_key)
        if source_key in seen_source_keys:
            raise BackupArtifactError("Snapshot object keys must be unique")
        seen_source_keys.add(source_key)
        source_version_id = _manifest_version_id(
            raw_object["source_version_id"], label="source version id"
        )
        size = raw_object["size_bytes"]
        if type(size) is not int or size < 0:
            raise BackupArtifactError("Snapshot object size is invalid")
        checksum = raw_object["sha256"]
        if not isinstance(checksum, str) or not _SHA256_RE.fullmatch(checksum):
            raise BackupArtifactError("Snapshot object checksum is invalid")
        archive_key = raw_object["archive_key"]
        _validate_object_key(archive_key)
        expected_archive_key = f"{root}/objects/{checksum}.blob"
        if archive_key != expected_archive_key:
            raise BackupArtifactError("Snapshot object archive key is invalid")
        archive_version_id = _manifest_version_id(
            raw_object["archive_version_id"], label="archive version id"
        )
        archive_etag = _manifest_etag(
            raw_object["archive_etag"], label="object archive ETag"
        )
        archive_identity = (size, archive_version_id, archive_etag)
        previous_archive = seen_archive_artifacts.get(archive_key)
        if previous_archive is not None and previous_archive != archive_identity:
            raise BackupArtifactError(
                "Snapshot references one archive key with inconsistent metadata"
            )
        seen_archive_artifacts[archive_key] = archive_identity
        objects.append(
            SnapshotObjectManifest(
                source_key=source_key,
                source_version_id=source_version_id,
                archive_key=archive_key,
                archive_version_id=archive_version_id,
                archive_etag=archive_etag,
                size_bytes=size,
                sha256=checksum,
                content_type=_manifest_header(
                    raw_object["content_type"], label="object content type"
                ),
                content_encoding=_manifest_header(
                    raw_object["content_encoding"], label="object content encoding"
                ),
                cache_control=_manifest_header(
                    raw_object["cache_control"], label="object cache control"
                ),
                content_disposition=_manifest_header(
                    raw_object["content_disposition"],
                    label="object content disposition",
                ),
            )
        )
    return PairedSnapshotManifest(
        snapshot_id=snapshot_id,
        consistency_mode="operator_quiesced",
        quiescence_confirmed=True,
        quiescence_confirmed_at=quiescence_confirmed_at,
        source_object_bucket=source_bucket,
        database=database_manifest,
        database_archive_version_id=database_version_id,
        database_archive_etag=database_etag,
        objects=tuple(objects),
    )


async def _read_body(body: Any, size: int = -1) -> bytes:
    value = body.read(size)
    if inspect.isawaitable(value):
        value = await value
    if not isinstance(value, bytes):
        raise BackupArtifactError("S3 response body was invalid")
    return value


async def _close_body(body: Any) -> None:
    close = getattr(body, "close", None)
    if close is None:
        return
    result = close()
    if inspect.isawaitable(result):
        await result


async def _get_object(client: Any, bucket: str, key: str) -> dict[str, Any]:
    try:
        response = await client.get_object(Bucket=bucket, Key=key)
        return cast(dict[str, Any], response)
    except Exception:
        raise BackupArtifactError("Unable to retrieve backup object from S3") from None


async def _hash_remote_object(
    client: Any, bucket: str, key: str, *, expected_size: int | None = None
) -> tuple[int, str]:
    response = await _get_object(client, bucket, key)
    body = response.get("Body")
    if body is None:
        raise BackupArtifactError("S3 backup object had no response body")
    digest = hashlib.sha256()
    size = 0
    content_length = response.get("ContentLength")
    try:
        if (
            expected_size is not None
            and content_length is not None
            and (type(content_length) is not int or content_length != expected_size)
        ):
            raise BackupArtifactError(
                "S3 read-back verification failed for database dump"
            )
        while chunk := await _read_body(
            body,
            CHUNK_SIZE
            if expected_size is None
            else min(CHUNK_SIZE, expected_size - size + 1),
        ):
            if expected_size is not None and size + len(chunk) > expected_size:
                raise BackupArtifactError(
                    "S3 read-back verification failed for database dump"
                )
            size += len(chunk)
            digest.update(chunk)
    finally:
        await _close_body(body)
    if content_length is not None and (
        type(content_length) is not int or content_length != size
    ):
        raise BackupArtifactError("S3 backup object length did not match its response")
    return size, digest.hexdigest()


async def _remove_unverified_manifest(client: Any, bucket: str, key: str) -> None:
    try:
        await client.delete_object(Bucket=bucket, Key=key)
    except Exception:
        raise BackupArtifactError(
            "Unable to remove unverified backup manifest from S3"
        ) from None


async def _finish_manifest_cleanup_after_cancellation(
    client: Any, bucket: str, key: str
) -> None:
    cleanup = asyncio.create_task(_remove_unverified_manifest(client, bucket, key))
    while not cleanup.done():
        try:
            await asyncio.shield(cleanup)
        except asyncio.CancelledError:
            continue
    cleanup.result()


async def _remove_unverified_manifest_before_propagating(
    client: Any, bucket: str, key: str
) -> None:
    try:
        await _remove_unverified_manifest(client, bucket, key)
    except asyncio.CancelledError:
        await _finish_manifest_cleanup_after_cancellation(client, bucket, key)
        raise


async def publish_backup(
    client: Any,
    bucket: str,
    archive_path: Path,
    manifest: BackupManifest,
) -> str:
    if (
        archive_path.stat().st_size != manifest.size_bytes
        or sha256_file(archive_path) != manifest.sha256
    ):
        raise BackupArtifactError("Local dump does not match its manifest")
    key = manifest.artifact_key
    manifest_object_key = manifest_key(key)
    try:
        await client.upload_file(str(archive_path), bucket, key)
    except Exception:
        raise BackupArtifactError("Unable to upload database dump to S3") from None
    remote_size, remote_sha256 = await _hash_remote_object(
        client, bucket, key, expected_size=manifest.size_bytes
    )
    if remote_size != manifest.size_bytes or remote_sha256 != manifest.sha256:
        raise BackupArtifactError("S3 read-back verification failed for database dump")
    payload = manifest.to_json_bytes()
    try:
        await client.put_object(
            Bucket=bucket,
            Key=manifest_object_key,
            Body=payload,
            ContentType="application/json",
        )
    except Exception:
        await _remove_unverified_manifest_before_propagating(
            client, bucket, manifest_object_key
        )
        raise BackupArtifactError("Unable to upload backup manifest to S3") from None
    except asyncio.CancelledError:
        await _finish_manifest_cleanup_after_cancellation(
            client, bucket, manifest_object_key
        )
        raise
    try:
        response = await _get_object(client, bucket, manifest_object_key)
        body = response.get("Body")
        if body is None:
            raise BackupArtifactError("S3 backup manifest had no response body")
        try:
            remote_manifest = bytearray()
            while chunk := await _read_body(
                body, min(CHUNK_SIZE, MANIFEST_MAX_BYTES + 1 - len(remote_manifest))
            ):
                remote_manifest.extend(chunk)
                if len(remote_manifest) > MANIFEST_MAX_BYTES:
                    raise BackupArtifactError("S3 backup manifest is too large")
        finally:
            await _close_body(body)
        if bytes(remote_manifest) != payload:
            raise BackupArtifactError("S3 read-back verification failed for manifest")
    except asyncio.CancelledError:
        await _finish_manifest_cleanup_after_cancellation(
            client, bucket, manifest_object_key
        )
        raise
    except Exception:
        await _remove_unverified_manifest_before_propagating(
            client, bucket, manifest_object_key
        )
        raise
    return manifest_object_key


async def download_verified_backup(
    client: Any,
    bucket: str,
    manifest_object_key: str,
    destination: Path,
    *,
    target_database: str | None = None,
) -> BackupManifest:
    _validate_object_key(manifest_object_key)
    if not manifest_object_key.endswith(MANIFEST_SUFFIX):
        raise BackupArtifactError("Restore requires an explicit manifest object key")
    if destination.exists():
        raise BackupArtifactError("Restore download destination already exists")
    response = await _get_object(client, bucket, manifest_object_key)
    body = response.get("Body")
    if body is None:
        raise BackupArtifactError("S3 backup manifest had no response body")
    try:
        payload = bytearray()
        while chunk := await _read_body(
            body, min(CHUNK_SIZE, MANIFEST_MAX_BYTES + 1 - len(payload))
        ):
            payload.extend(chunk)
            if len(payload) > MANIFEST_MAX_BYTES:
                raise BackupArtifactError("S3 backup manifest is too large")
    finally:
        await _close_body(body)
    manifest = parse_manifest(bytes(payload), expected_manifest_key=manifest_object_key)
    if target_database is not None:
        validate_restore_target(manifest.source_database, target_database)
    response = await _get_object(client, bucket, manifest.artifact_key)
    body = response.get("Body")
    if body is None:
        raise BackupArtifactError("S3 database dump had no response body")
    digest = hashlib.sha256()
    size = 0
    created = False
    verified = False
    body_closed = False
    try:
        content_length = response.get("ContentLength")
        if content_length is not None and (
            type(content_length) is not int or content_length != manifest.size_bytes
        ):
            raise BackupArtifactError(
                "S3 database dump length did not match its manifest"
            )
        with destination.open("xb") as stream:
            created = True
            while chunk := await _read_body(
                body, min(CHUNK_SIZE, manifest.size_bytes - size + 1)
            ):
                if size + len(chunk) > manifest.size_bytes:
                    raise BackupArtifactError(
                        "Downloaded database dump exceeded its manifest length"
                    )
                stream.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        await _close_body(body)
        body_closed = True
        if size != manifest.size_bytes or digest.hexdigest() != manifest.sha256:
            raise BackupArtifactError(
                "Downloaded database dump failed checksum verification"
            )
        verified = True
        return manifest
    except BackupArtifactError:
        raise
    except Exception:
        raise BackupArtifactError("Unable to download database dump from S3") from None
    finally:
        # Remove an unverified local artifact before awaiting remote cleanup.
        # A caller may cancel repeatedly while closing the streaming body; that
        # must not interrupt deletion of the partial file.
        try:
            if created and not verified:
                destination.unlink(missing_ok=True)
        finally:
            if not body_closed:
                with suppress(Exception):
                    await _close_body(body)


def _database_url(value: str) -> URL:
    try:
        url = make_url(value)
    except Exception:
        raise BackupArtifactError("Database URL is invalid") from None
    if not url.drivername.startswith("postgresql") or not url.database:
        raise BackupArtifactError("A PostgreSQL database URL is required")
    unsupported = set(url.query) - set(_PG_URL_OPTIONS)
    if unsupported:
        raise BackupArtifactError(
            "Database URL contains unsupported connection options"
        )
    return url


def _psycopg_dsn(url: URL) -> str:
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


def _pg_tool_environment(
    database_url: str, *, database_override: str | None = None
) -> dict[str, str]:
    url = _database_url(database_url)
    environment = {
        key: value for key in _SYSTEM_ENV if (value := os.environ.get(key)) is not None
    }
    for key in _PG_ENV_FALLBACKS:
        if key in os.environ:
            environment[key] = os.environ[key]
    if url.host is not None:
        environment["PGHOST"] = url.host
    if url.port is not None:
        environment["PGPORT"] = str(url.port)
    if url.username is not None:
        environment["PGUSER"] = url.username
    if url.password is not None:
        environment["PGPASSWORD"] = url.password
    environment["PGDATABASE"] = database_override or url.database or ""
    for key, raw_value in url.query.items():
        if isinstance(raw_value, tuple):
            if len(raw_value) != 1:
                raise BackupArtifactError(
                    "Database URL has repeated connection options"
                )
            value = raw_value[0]
        else:
            value = raw_value
        environment[_PG_URL_OPTIONS[key]] = str(value)
    return environment


def _run_pg_tool(
    command: list[str],
    environment: dict[str, str],
    *,
    command_runner: Callable[..., Any] = subprocess.run,
) -> None:
    # Callers supply only fixed pg_dump/pg_restore argv lists; shell stays disabled.
    try:
        result = command_runner(
            command,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except FileNotFoundError:
        raise BackupArtifactError(f"{command[0]} executable is unavailable") from None
    except Exception:
        raise BackupArtifactError(f"Unable to run {command[0]}") from None
    if result.returncode != 0:
        raise BackupArtifactError(
            f"{command[0]} failed with exit code {result.returncode}"
        )


def dump_database(
    database_url: str,
    archive_path: Path,
    *,
    command_runner: Callable[..., Any] = subprocess.run,
) -> None:
    environment = _pg_tool_environment(database_url)
    _run_pg_tool(
        [
            "pg_dump",
            "--format=custom",
            "--no-owner",
            "--no-privileges",
            "--file",
            str(archive_path),
        ],
        environment,
        command_runner=command_runner,
    )
    if not archive_path.is_file() or archive_path.stat().st_size <= 0:
        raise BackupArtifactError("pg_dump did not produce a non-empty archive")


def verify_source_metadata_unchanged(
    before: tuple[str, tuple[str, ...]],
    after: tuple[str, tuple[str, ...]],
) -> None:
    if before != after:
        raise BackupArtifactError(
            "Source database migration revision changed during dump"
        )


def source_database_metadata(database_url: str) -> tuple[str, tuple[str, ...]]:
    dsn = _psycopg_dsn(_database_url(database_url))
    try:
        with psycopg.connect(dsn) as connection:
            database_row = connection.execute("SELECT current_database()").fetchone()
            if database_row is None:
                raise BackupArtifactError("Source database metadata is unavailable")
            source_database = database_row[0]
            revisions = tuple(
                row[0]
                for row in connection.execute(
                    "SELECT version_num FROM alembic_version ORDER BY version_num"
                ).fetchall()
            )
    except BackupArtifactError:
        raise
    except Exception:
        raise BackupArtifactError(
            "Unable to read source database name and Alembic revision"
        ) from None
    if not source_database or not revisions:
        raise BackupArtifactError("Source database has no Alembic revision")
    return str(source_database), revisions


def _validate_restore_target_name(target_database: str) -> None:
    if not isinstance(target_database, str) or not _RESTORE_DATABASE_RE.fullmatch(
        target_database
    ):
        raise BackupArtifactError(
            "Restore target must be a new database named restore_<name>"
        )


def validate_restore_target(source_database: str, target_database: str) -> None:
    _validate_restore_target_name(target_database)
    if target_database == source_database:
        raise BackupArtifactError(
            "Restore target must be different from the source database"
        )


def _validate_restore_admin_database(
    admin_database_url: str, target_database: str
) -> URL:
    url = _database_url(admin_database_url)
    if url.database == target_database:
        raise BackupArtifactError(
            "Admin connection must not point at the restore target"
        )
    return url


def _require_absent_restore_database(
    admin_database_url: str,
    target_database: str,
    *,
    connect: Callable[..., Any] | None = None,
) -> None:
    url = _validate_restore_admin_database(admin_database_url, target_database)
    try:
        connector = connect or psycopg.connect
        with connector(_psycopg_dsn(url), autocommit=True) as connection:
            exists = connection.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s",
                (target_database,),
            ).fetchone()
    except Exception:
        raise BackupArtifactError(
            "Unable to verify that the restore database target is absent"
        ) from None
    if exists:
        raise BackupArtifactError("Restore target database already exists")


def _ensure_new_database(
    admin_database_url: str,
    target_database: str,
    *,
    command_runner: Callable[..., Any] = subprocess.run,
) -> None:
    _validate_restore_target_name(target_database)
    url = _validate_restore_admin_database(admin_database_url, target_database)
    dsn = _psycopg_dsn(url)
    try:
        with psycopg.connect(dsn, autocommit=True) as connection:
            exists = connection.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s",
                (target_database,),
            ).fetchone()
            if exists:
                raise BackupArtifactError("Restore target database already exists")
    except BackupArtifactError:
        raise
    except Exception:
        raise BackupArtifactError(
            "Unable to create the new restore target database"
        ) from None
    # PostgreSQL identifiers cannot be bound as SQL parameters. Use the
    # PostgreSQL client utility with the validated database name as its own
    # argv element instead of composing an executable SQL statement.
    _run_pg_tool(
        [
            "createdb",
            "--no-password",
            "--maintenance-db",
            url.database or "",
            target_database,
        ],
        _pg_tool_environment(admin_database_url),
        command_runner=command_runner,
    )


def restore_archive(
    archive_path: Path,
    manifest: BackupManifest,
    admin_database_url: str,
    target_database: str,
    *,
    command_runner: Callable[..., Any] = subprocess.run,
) -> None:
    try:
        manifest = parse_manifest(
            manifest.to_json_bytes(),
            expected_manifest_key=manifest_key(manifest.artifact_key),
        )
    except BackupArtifactError:
        raise
    except (AttributeError, TypeError, ValueError):
        raise BackupArtifactError("Restore manifest is invalid") from None

    validate_restore_target(manifest.source_database, target_database)
    if not archive_path.is_file():
        raise BackupArtifactError("Verified database dump is unavailable")
    try:
        archive_size = archive_path.stat().st_size
        archive_digest = sha256_file(archive_path)
    except OSError:
        raise BackupArtifactError("Unable to verify restore archive") from None
    if archive_size != manifest.size_bytes or archive_digest != manifest.sha256:
        raise BackupArtifactError(
            "Restore archive does not match manifest size/checksum"
        )

    environment = _pg_tool_environment(
        admin_database_url, database_override=target_database
    )
    _run_pg_tool(
        ["pg_restore", "--list", str(archive_path)],
        environment,
        command_runner=command_runner,
    )
    _ensure_new_database(
        admin_database_url, target_database, command_runner=command_runner
    )
    _run_pg_tool(
        [
            "pg_restore",
            "--exit-on-error",
            "--no-owner",
            "--no-privileges",
            "--dbname",
            target_database,
            str(archive_path),
        ],
        environment,
        command_runner=command_runner,
    )


@dataclass(frozen=True)
class S3Settings:
    endpoint_url: str | None
    bucket: str
    prefix: str
    region: str
    access_key_id: str | None = field(default=None, repr=False)
    secret_access_key: str | None = field(default=None, repr=False)


def _is_local_dev_s3_host(host: str) -> bool:
    normalized_host = host.casefold().rstrip(".")
    if normalized_host in _LOCAL_DEV_S3_HOSTS:
        return True
    try:
        address = ipaddress.ip_address(normalized_host)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return address.is_loopback or any(
        address in network for network in _LOCAL_DEV_S3_NETWORKS
    )


def s3_settings_from_environment() -> S3Settings:
    endpoint_url = os.environ.get("BACKUP_S3_ENDPOINT_URL", "").strip()
    bucket = os.environ.get("BACKUP_S3_BUCKET", "").strip()
    prefix = os.environ.get("BACKUP_S3_PREFIX", "database").strip("/")
    if not endpoint_url or not bucket:
        raise BackupArtifactError(
            "BACKUP_S3_ENDPOINT_URL and BACKUP_S3_BUCKET must be set"
        )
    from urllib.parse import urlsplit

    parsed = urlsplit(endpoint_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise BackupArtifactError(
            "BACKUP_S3_ENDPOINT_URL must be an HTTP(S) endpoint without credentials"
        )
    if (
        parsed.scheme == "http"
        and os.environ.get("BACKUP_S3_ALLOW_HTTP_FOR_LOCAL_DEV", "").casefold()
        != "true"
    ):
        raise BackupArtifactError(
            "HTTPS is required; HTTP is allowed only for isolated local/dev endpoints "
            "when BACKUP_S3_ALLOW_HTTP_FOR_LOCAL_DEV=true"
        )
    if parsed.scheme == "http" and (
        parsed.hostname is None or not _is_local_dev_s3_host(parsed.hostname)
    ):
        raise BackupArtifactError(
            "HTTP is restricted to loopback/private IPs and approved local Docker hosts"
        )
    if prefix:
        _validate_object_key(prefix)
    return S3Settings(
        endpoint_url=endpoint_url,
        bucket=bucket,
        prefix=prefix,
        region=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
    )


def storage_s3_settings_from_environment() -> S3Settings:
    """Read application object-storage settings without exposing credentials."""
    from app.core.config.storage import StorageSettings

    storage = StorageSettings()
    if storage.storage_backend not in {"s3", "minio"}:
        raise BackupArtifactError(
            "Paired snapshots require the configured S3 storage backend"
        )
    endpoint_url = storage.storage_s3_endpoint_url.strip() or None
    bucket = _validate_bucket_name(storage.storage_s3_bucket.strip())
    access_key_id = storage.storage_s3_access_key_id.strip() or None
    secret_access_key = storage.storage_s3_secret_access_key.strip() or None
    if bool(access_key_id) != bool(secret_access_key):
        raise BackupArtifactError(
            "Application S3 access key and secret must be configured together"
        )
    if endpoint_url is not None:
        from urllib.parse import urlsplit

        parsed = urlsplit(endpoint_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise BackupArtifactError(
                "Application S3 endpoint must be an HTTP(S) URL without credentials"
            )
        allow_local_http = (
            os.environ.get("BACKUP_S3_ALLOW_HTTP_FOR_LOCAL_DEV", "").casefold()
            == "true"
        )
        if parsed.scheme == "http" and (
            not allow_local_http
            or parsed.hostname is None
            or not _is_local_dev_s3_host(parsed.hostname)
        ):
            raise BackupArtifactError(
                "Application S3 HTTP is restricted to explicitly enabled local endpoints"
            )
    return S3Settings(
        endpoint_url=endpoint_url,
        bucket=bucket,
        prefix="",
        region=storage.storage_s3_region.strip() or "us-east-1",
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
    )


@asynccontextmanager
async def s3_client(settings: S3Settings) -> AsyncIterator[Any]:
    try:
        client_options: dict[str, Any] = {"region_name": settings.region}
        if settings.endpoint_url:
            client_options["endpoint_url"] = settings.endpoint_url
        if settings.access_key_id and settings.secret_access_key:
            client_options["aws_access_key_id"] = settings.access_key_id
            client_options["aws_secret_access_key"] = settings.secret_access_key
        async with aioboto3.Session().client(
            "s3",
            **client_options,
        ) as client:
            yield client
    except BackupArtifactError:
        raise
    except Exception:
        raise BackupArtifactError(
            "Unable to initialize the configured S3 client"
        ) from None


def _response_version_id(response: dict[str, Any]) -> str | None:
    value = response.get("VersionId")
    if value in (None, "", "null"):
        return None
    if not isinstance(value, str) or len(value) > 1024:
        raise BackupArtifactError("S3 returned an invalid object version id")
    return value


def _response_etag(response: dict[str, Any]) -> str:
    try:
        return _manifest_etag(response.get("ETag"), label="object ETag")
    except BackupArtifactError:
        raise BackupArtifactError(
            "S3 did not return an object validator required for verification"
        ) from None


async def _get_pinned_object(
    client: Any,
    bucket: str,
    key: str,
    *,
    version_id: str | None = None,
    etag: str | None = None,
) -> dict[str, Any]:
    request: dict[str, Any] = {"Bucket": bucket, "Key": key}
    if version_id is not None:
        request["VersionId"] = version_id
    elif etag is not None:
        request["IfMatch"] = etag
    else:
        raise BackupArtifactError("Snapshot object has no immutable read validator")
    try:
        return cast(dict[str, Any], await client.get_object(**request))
    except Exception:
        raise BackupArtifactError(
            "Unable to retrieve a pinned snapshot object"
        ) from None


async def _download_object_to_file(
    client: Any,
    bucket: str,
    key: str,
    destination: Path,
    *,
    expected_size: int,
    expected_sha256: str | None = None,
    version_id: str | None = None,
    etag: str | None = None,
) -> tuple[int, str, dict[str, Any]]:
    _validate_object_key(key)
    if destination.exists():
        raise BackupArtifactError("Snapshot download destination already exists")
    response = await _get_pinned_object(
        client, bucket, key, version_id=version_id, etag=etag
    )
    body = response.get("Body")
    if body is None:
        raise BackupArtifactError("Snapshot object had no response body")
    content_length = response.get("ContentLength")
    if content_length is not None and (
        type(content_length) is not int or content_length != expected_size
    ):
        await _close_body(body)
        raise BackupArtifactError("Snapshot object length does not match its inventory")
    digest = hashlib.sha256()
    size = 0
    created = False
    verified = False
    try:
        with destination.open("xb") as stream:
            created = True
            while chunk := await _read_body(
                body, min(CHUNK_SIZE, expected_size - size + 1)
            ):
                if size + len(chunk) > expected_size:
                    raise BackupArtifactError(
                        "Snapshot object exceeded its manifest size"
                    )
                stream.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        if size != expected_size:
            raise BackupArtifactError(
                "Snapshot object length does not match its inventory"
            )
        checksum = digest.hexdigest()
        if expected_sha256 is not None and checksum != expected_sha256:
            raise BackupArtifactError(
                "Snapshot object checksum does not match its manifest"
            )
        verified = True
        return size, checksum, response
    except BackupArtifactError:
        raise
    except Exception:
        raise BackupArtifactError(
            "Unable to download a pinned snapshot object"
        ) from None
    finally:
        try:
            if created and not verified:
                destination.unlink(missing_ok=True)
        finally:
            with suppress(Exception):
                await _close_body(body)


async def _upload_file_create_only(
    client: Any,
    bucket: str,
    key: str,
    path: Path,
    *,
    content_type: str = "application/octet-stream",
    content_encoding: str | None = None,
    cache_control: str | None = None,
    content_disposition: str | None = None,
) -> S3ObjectReceipt:
    _validate_object_key(key)
    if not path.is_file():
        raise BackupArtifactError("Snapshot source artifact is unavailable")
    size = path.stat().st_size
    headers = {"ContentType": content_type}
    for name, value in (
        ("ContentEncoding", content_encoding),
        ("CacheControl", cache_control),
        ("ContentDisposition", content_disposition),
    ):
        if value is not None:
            headers[name] = value
    if size <= SNAPSHOT_PART_SIZE:
        try:
            response = await client.put_object(
                Bucket=bucket,
                Key=key,
                Body=path.read_bytes(),
                IfNoneMatch="*",
                **headers,
            )
        except Exception:
            raise BackupArtifactError(
                "Snapshot object was not created conditionally"
            ) from None
        return S3ObjectReceipt(
            version_id=_response_version_id(response), etag=_response_etag(response)
        )

    try:
        created = await client.create_multipart_upload(
            Bucket=bucket, Key=key, **headers
        )
    except Exception:
        raise BackupArtifactError("Unable to stage immutable snapshot object") from None
    upload_id = created.get("UploadId")
    if not isinstance(upload_id, str) or not upload_id:
        raise BackupArtifactError("S3 did not return a multipart upload identity")
    parts: list[dict[str, Any]] = []
    completed = False
    try:
        with path.open("rb") as stream:
            part_number = 1
            while chunk := stream.read(SNAPSHOT_PART_SIZE):
                if part_number > 10_000:
                    raise BackupArtifactError(
                        "Snapshot artifact exceeds multipart limits"
                    )
                result = await client.upload_part(
                    Bucket=bucket,
                    Key=key,
                    UploadId=upload_id,
                    PartNumber=part_number,
                    Body=chunk,
                )
                part_etag = _response_etag(result)
                parts.append({"ETag": part_etag, "PartNumber": part_number})
                part_number += 1
        response = await client.complete_multipart_upload(
            Bucket=bucket,
            Key=key,
            UploadId=upload_id,
            MultipartUpload={"Parts": parts},
            IfNoneMatch="*",
        )
        completed = True
        return S3ObjectReceipt(
            version_id=_response_version_id(response), etag=_response_etag(response)
        )
    except asyncio.CancelledError:
        with suppress(Exception):
            await asyncio.shield(
                client.abort_multipart_upload(
                    Bucket=bucket, Key=key, UploadId=upload_id
                )
            )
        raise
    except BackupArtifactError:
        raise
    except Exception:
        raise BackupArtifactError(
            "Snapshot multipart object was not completed conditionally"
        ) from None
    finally:
        if not completed:
            with suppress(Exception):
                await client.abort_multipart_upload(
                    Bucket=bucket, Key=key, UploadId=upload_id
                )


async def _verify_uploaded_file(
    client: Any,
    bucket: str,
    key: str,
    path: Path,
    *,
    receipt: S3ObjectReceipt,
) -> None:
    expected_size = path.stat().st_size
    expected_sha256 = sha256_file(path)
    downloaded_path = path.with_name(f"{path.name}.readback")
    size, checksum, _ = await _download_object_to_file(
        client,
        bucket,
        key,
        downloaded_path,
        expected_size=expected_size,
        expected_sha256=expected_sha256,
        version_id=receipt.version_id,
        etag=None if receipt.version_id else receipt.etag,
    )
    downloaded_path.unlink(missing_ok=True)
    if size != expected_size or checksum != expected_sha256:
        raise BackupArtifactError("Snapshot S3 read-back verification failed")


async def _list_current_objects(client: Any, bucket: str) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    continuation_token: str | None = None
    seen_tokens: set[str] = set()
    while True:
        request: dict[str, Any] = {"Bucket": bucket, "MaxKeys": 1000}
        if continuation_token is not None:
            request["ContinuationToken"] = continuation_token
        try:
            page = await client.list_objects_v2(**request)
        except Exception:
            raise BackupArtifactError(
                "Unable to inventory application S3 objects"
            ) from None
        entries = page.get("Contents", [])
        if (
            not isinstance(entries, list)
            or type(page.get("KeyCount")) is not int
            or page["KeyCount"] != len(entries)
        ):
            raise BackupArtifactError("S3 returned an invalid object inventory")
        for entry in entries:
            if not isinstance(entry, dict):
                raise BackupArtifactError("S3 returned an invalid object inventory")
            key = entry.get("Key")
            size = entry.get("Size")
            if not isinstance(key, str):
                raise BackupArtifactError(
                    "S3 object inventory contains an invalid object key"
                )
            _validate_object_key(key)
            if key in seen_keys:
                raise BackupArtifactError("S3 object inventory contains duplicate keys")
            seen_keys.add(key)
            if type(size) is not int or size < 0:
                raise BackupArtifactError("S3 returned an invalid object size")
            etag = entry.get("ETag")
            if not isinstance(etag, str) or not etag:
                raise BackupArtifactError("S3 object inventory lacks a stable ETag")
            objects.append({"Key": key, "Size": size, "ETag": etag})
            if len(objects) > MAX_SNAPSHOT_OBJECTS:
                raise BackupArtifactError(
                    "Application S3 object inventory is too large"
                )
        is_truncated = page.get("IsTruncated")
        if type(is_truncated) is not bool:
            raise BackupArtifactError("S3 object inventory pagination is invalid")
        if not is_truncated:
            break
        next_token = page.get("NextContinuationToken")
        if (
            not isinstance(next_token, str)
            or not next_token
            or next_token in seen_tokens
            or next_token == continuation_token
        ):
            raise BackupArtifactError("S3 object inventory pagination is invalid")
        seen_tokens.add(next_token)
        continuation_token = next_token
    return objects


async def _require_empty_restore_bucket(client: Any, bucket: str) -> None:
    try:
        current = await client.list_objects_v2(Bucket=bucket, MaxKeys=1)
        versions = await client.list_object_versions(Bucket=bucket, MaxKeys=1)
        uploads = await client.list_multipart_uploads(Bucket=bucket, MaxUploads=1)
    except Exception:
        raise BackupArtifactError(
            "Restore bucket emptiness and conditional-write prerequisites could not be verified"
        ) from None
    if (
        type(current.get("KeyCount")) is not int
        or current.get("KeyCount") != 0
        or current.get("IsTruncated") is not False
        or versions.get("IsTruncated") is not False
        or uploads.get("IsTruncated") is not False
    ):
        raise BackupArtifactError("Restore bucket emptiness could not be established")
    if (
        current.get("Contents")
        or versions.get("Versions")
        or versions.get("DeleteMarkers")
    ):
        raise BackupArtifactError("Restore object bucket must be empty")
    if uploads.get("Uploads"):
        raise BackupArtifactError(
            "Restore object bucket has incomplete multipart uploads"
        )


def _object_bucket_is_distinct(
    source_bucket: str, backup_bucket: str, target_bucket: str
) -> None:
    _validate_bucket_name(target_bucket)
    if target_bucket in {source_bucket, backup_bucket}:
        raise BackupArtifactError(
            "Restore object bucket must differ from source and backup buckets"
        )


def _snapshot_key(prefix: str, snapshot_id: str, suffix: str) -> str:
    base = f"{prefix}/" if prefix else ""
    key = f"{base}snapshots/{snapshot_id}/{suffix}"
    _validate_object_key(key)
    return key


async def _read_limited_body(response: dict[str, Any], *, maximum: int) -> bytes:
    body = response.get("Body")
    if body is None:
        raise BackupArtifactError("Snapshot manifest had no response body")
    content_length = response.get("ContentLength")
    if content_length is not None and (
        type(content_length) is not int
        or content_length < 0
        or content_length > maximum
    ):
        await _close_body(body)
        raise BackupArtifactError("Snapshot manifest size is invalid")
    payload = bytearray()
    try:
        while chunk := await _read_body(
            body, min(CHUNK_SIZE, maximum + 1 - len(payload))
        ):
            payload.extend(chunk)
            if len(payload) > maximum:
                raise BackupArtifactError("Snapshot manifest is too large")
    finally:
        with suppress(Exception):
            await _close_body(body)
    if content_length is not None and len(payload) != content_length:
        raise BackupArtifactError("Snapshot manifest length is invalid")
    return bytes(payload)


async def _publish_paired_manifest(
    client: Any, bucket: str, key: str, payload: bytes
) -> None:
    if len(payload) > PAIRED_SNAPSHOT_MANIFEST_MAX_BYTES:
        raise BackupArtifactError(
            "Snapshot manifest exceeds the supported inventory size"
        )
    try:
        response = await client.put_object(
            Bucket=bucket,
            Key=key,
            Body=payload,
            ContentType="application/json",
            IfNoneMatch="*",
        )
    except Exception:
        raise BackupArtifactError(
            "Paired snapshot commit manifest was not created conditionally"
        ) from None
    receipt = S3ObjectReceipt(
        version_id=_response_version_id(response), etag=_response_etag(response)
    )
    remote = await _get_pinned_object(
        client,
        bucket,
        key,
        version_id=receipt.version_id,
        etag=None if receipt.version_id else receipt.etag,
    )
    if (
        await _read_limited_body(remote, maximum=PAIRED_SNAPSHOT_MANIFEST_MAX_BYTES)
        != payload
    ):
        raise BackupArtifactError("Paired snapshot commit manifest read-back failed")


async def backup_paired_snapshot_to_s3(
    database_url: str,
    backup_settings: S3Settings,
    source_storage_settings: S3Settings,
    *,
    confirm_source_quiesced: bool,
) -> str:
    if confirm_source_quiesced is not True:
        raise BackupArtifactError(
            "Paired snapshot requires explicit source-quiescence confirmation"
        )
    if source_storage_settings.bucket == backup_settings.bucket:
        raise BackupArtifactError("Application and backup object buckets must differ")

    source_identity = source_database_metadata(database_url)
    source_database, source_revision = source_identity
    snapshot_id = uuid.uuid4().hex
    confirmed_at = datetime.now(UTC).replace(microsecond=0)
    database_key = _snapshot_key(backup_settings.prefix, snapshot_id, "database.dump")
    database_manifest_key = manifest_key(database_key)
    snapshot_root = database_key.rsplit("/", maxsplit=1)[0]
    with tempfile.TemporaryDirectory(prefix="university-paired-backup-") as temp_dir:
        temp_path = Path(temp_dir)
        database_path = temp_path / "database.dump"
        dump_database(database_url, database_path)
        verify_source_metadata_unchanged(
            source_identity, source_database_metadata(database_url)
        )
        async with s3_client(source_storage_settings) as source_client:
            source_objects = await _list_current_objects(
                source_client, source_storage_settings.bucket
            )
            async with s3_client(backup_settings) as backup_client:
                snapshot_objects: list[SnapshotObjectManifest] = []
                receipts_by_digest: dict[str, S3ObjectReceipt] = {}
                sizes_by_digest: dict[str, int] = {}
                for index, source_entry in enumerate(source_objects):
                    source_key = cast(str, source_entry["Key"])
                    expected_size = cast(int, source_entry["Size"])
                    source_etag = cast(str, source_entry["ETag"])
                    source_path = temp_path / f"object-{index:08d}.blob"
                    size, checksum, source_response = await _download_object_to_file(
                        source_client,
                        source_storage_settings.bucket,
                        source_key,
                        source_path,
                        expected_size=expected_size,
                        etag=source_etag,
                    )
                    if (
                        source_response.get("ETag") is not None
                        and source_response.get("ETag") != source_etag
                    ):
                        raise BackupArtifactError(
                            "Application S3 object changed during the quiesced snapshot"
                        )
                    source_version_id = _response_version_id(source_response)
                    archive_key = f"{snapshot_root}/objects/{checksum}.blob"
                    receipt = receipts_by_digest.get(checksum)
                    if receipt is None:
                        prior_size = sizes_by_digest.get(checksum)
                        if prior_size is not None and prior_size != size:
                            raise BackupArtifactError(
                                "Snapshot object digest has inconsistent lengths"
                            )
                        receipt = await _upload_file_create_only(
                            backup_client,
                            backup_settings.bucket,
                            archive_key,
                            source_path,
                        )
                        await _verify_uploaded_file(
                            backup_client,
                            backup_settings.bucket,
                            archive_key,
                            source_path,
                            receipt=receipt,
                        )
                        receipts_by_digest[checksum] = receipt
                        sizes_by_digest[checksum] = size
                    snapshot_objects.append(
                        SnapshotObjectManifest(
                            source_key=source_key,
                            source_version_id=source_version_id,
                            archive_key=archive_key,
                            archive_version_id=receipt.version_id,
                            archive_etag=receipt.etag,
                            size_bytes=size,
                            sha256=checksum,
                            content_type=_manifest_header(
                                source_response.get("ContentType"),
                                label="source content type",
                            ),
                            content_encoding=_manifest_header(
                                source_response.get("ContentEncoding"),
                                label="source content encoding",
                            ),
                            cache_control=_manifest_header(
                                source_response.get("CacheControl"),
                                label="source cache control",
                            ),
                            content_disposition=_manifest_header(
                                source_response.get("ContentDisposition"),
                                label="source content disposition",
                            ),
                        )
                    )
                    source_path.unlink(missing_ok=True)

                database_manifest = create_manifest(
                    database_path,
                    source_database=source_database,
                    source_revision=source_revision,
                    artifact_key=database_key,
                    created_at=confirmed_at,
                )
                database_receipt = await _upload_file_create_only(
                    backup_client,
                    backup_settings.bucket,
                    database_key,
                    database_path,
                )
                await _verify_uploaded_file(
                    backup_client,
                    backup_settings.bucket,
                    database_key,
                    database_path,
                    receipt=database_receipt,
                )
                snapshot_manifest = PairedSnapshotManifest(
                    snapshot_id=snapshot_id,
                    consistency_mode="operator_quiesced",
                    quiescence_confirmed=True,
                    quiescence_confirmed_at=confirmed_at.isoformat().replace(
                        "+00:00", "Z"
                    ),
                    source_object_bucket=source_storage_settings.bucket,
                    database=database_manifest,
                    database_archive_version_id=database_receipt.version_id,
                    database_archive_etag=database_receipt.etag,
                    objects=tuple(snapshot_objects),
                )
                manifest_payload = snapshot_manifest.to_json_bytes()
                parse_paired_snapshot_manifest(
                    manifest_payload,
                    expected_manifest_key=database_manifest_key,
                )
                await _publish_paired_manifest(
                    backup_client,
                    backup_settings.bucket,
                    database_manifest_key,
                    manifest_payload,
                )
    return database_manifest_key


async def _download_paired_manifest(
    client: Any, bucket: str, manifest_key_value: str
) -> PairedSnapshotManifest:
    _validate_object_key(manifest_key_value)
    if not manifest_key_value.endswith(MANIFEST_SUFFIX):
        raise BackupArtifactError("Paired restore requires a manifest object key")
    response = await _get_object(client, bucket, manifest_key_value)
    payload = await _read_limited_body(
        response, maximum=PAIRED_SNAPSHOT_MANIFEST_MAX_BYTES
    )
    return parse_paired_snapshot_manifest(
        payload, expected_manifest_key=manifest_key_value
    )


async def restore_paired_snapshot_from_s3(
    manifest_object_key: str,
    target_database: str,
    admin_database_url: str,
    backup_settings: S3Settings,
    target_storage_settings: S3Settings,
    target_object_bucket: str,
    *,
    database_connect: Callable[..., Any] | None = None,
) -> PairedSnapshotManifest:
    _validate_object_key(manifest_object_key)
    if not manifest_object_key.endswith(MANIFEST_SUFFIX):
        raise BackupArtifactError("Paired restore requires a manifest object key")
    _validate_restore_target_name(target_database)
    _validate_restore_admin_database(admin_database_url, target_database)
    target_object_bucket = _validate_bucket_name(target_object_bucket)

    with tempfile.TemporaryDirectory(prefix="university-paired-restore-") as temp_dir:
        temp_path = Path(temp_dir)
        database_path = temp_path / "database.dump"
        async with s3_client(backup_settings) as backup_client:
            manifest = await _download_paired_manifest(
                backup_client, backup_settings.bucket, manifest_object_key
            )
            validate_restore_target(manifest.database.source_database, target_database)
            _object_bucket_is_distinct(
                manifest.source_object_bucket,
                backup_settings.bucket,
                target_object_bucket,
            )
            database_record = manifest.database
            await _download_object_to_file(
                backup_client,
                backup_settings.bucket,
                database_record.artifact_key,
                database_path,
                expected_size=database_record.size_bytes,
                expected_sha256=database_record.sha256,
                version_id=manifest.database_archive_version_id,
                etag=(
                    None
                    if manifest.database_archive_version_id
                    else manifest.database_archive_etag
                ),
            )
            archive_paths: dict[str, Path] = {}
            for index, object_record in enumerate(manifest.objects):
                if object_record.archive_key in archive_paths:
                    continue
                object_path = temp_path / f"object-{index:08d}.blob"
                await _download_object_to_file(
                    backup_client,
                    backup_settings.bucket,
                    object_record.archive_key,
                    object_path,
                    expected_size=object_record.size_bytes,
                    expected_sha256=object_record.sha256,
                    version_id=object_record.archive_version_id,
                    etag=(
                        None
                        if object_record.archive_version_id
                        else object_record.archive_etag
                    ),
                )
                archive_paths[object_record.archive_key] = object_path

        _require_absent_restore_database(
            admin_database_url, target_database, connect=database_connect
        )
        async with s3_client(target_storage_settings) as target_client:
            await _require_empty_restore_bucket(target_client, target_object_bucket)

            # The database remains isolated until the caller explicitly points an
            # application deployment at the target database and object bucket.
            restore_archive(
                database_path,
                manifest.database,
                admin_database_url,
                target_database,
            )
            if manifest.objects:
                try:
                    for object_record in manifest.objects:
                        source_path = archive_paths[object_record.archive_key]
                        receipt = await _upload_file_create_only(
                            target_client,
                            target_object_bucket,
                            object_record.source_key,
                            source_path,
                            content_type=(
                                object_record.content_type or "application/octet-stream"
                            ),
                            content_encoding=object_record.content_encoding,
                            cache_control=object_record.cache_control,
                            content_disposition=object_record.content_disposition,
                        )
                        await _verify_uploaded_file(
                            target_client,
                            target_object_bucket,
                            object_record.source_key,
                            source_path,
                            receipt=receipt,
                        )
                except Exception:
                    raise BackupArtifactError(
                        "Snapshot restore is incomplete; inspect the isolated target database and object bucket"
                    ) from None
    return manifest


async def backup_to_s3(database_url: str, settings: S3Settings) -> str:
    source_identity = source_database_metadata(database_url)
    source_database, source_revision = source_identity
    with tempfile.TemporaryDirectory(prefix="university-db-backup-") as temp_dir:
        archive_path = Path(temp_dir) / "database.dump"
        dump_database(database_url, archive_path)
        verify_source_metadata_unchanged(
            source_identity, source_database_metadata(database_url)
        )
        artifact_key = new_artifact_key(settings.prefix)
        manifest = create_manifest(
            archive_path,
            source_database=source_database,
            source_revision=source_revision,
            artifact_key=artifact_key,
        )
        async with s3_client(settings) as client:
            return await publish_backup(client, settings.bucket, archive_path, manifest)


async def restore_from_s3(
    manifest_object_key: str,
    target_database: str,
    admin_database_url: str,
    settings: S3Settings,
) -> None:
    _validate_object_key(manifest_object_key)
    if not manifest_object_key.endswith(MANIFEST_SUFFIX):
        raise BackupArtifactError("Restore requires a manifest object key")
    _validate_restore_target_name(target_database)
    _validate_restore_admin_database(admin_database_url, target_database)
    with tempfile.TemporaryDirectory(prefix="university-db-restore-") as temp_dir:
        archive_path = Path(temp_dir) / "database.dump"
        async with s3_client(settings) as client:
            manifest = await download_verified_backup(
                client,
                settings.bucket,
                manifest_object_key,
                archive_path,
                target_database=target_database,
            )
        restore_archive(archive_path, manifest, admin_database_url, target_database)


def _environment_value(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise BackupArtifactError("Environment variable name is invalid")
    value = os.environ.get(name, "").strip()
    if not value:
        raise BackupArtifactError(f"Environment variable {name} is not set")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = SafeArgumentParser(description=__doc__, allow_abbrev=False)
    subparsers = parser.add_subparsers(
        dest="operation", parser_class=SafeArgumentParser
    )
    backup_parser = subparsers.add_parser(
        "backup", help="create and verify a PostgreSQL backup", allow_abbrev=False
    )
    backup_parser.add_argument("--database-url-env", default="DATABASE_URL")
    restore_parser = subparsers.add_parser(
        "restore",
        help="restore an artifact to a new isolated database",
        allow_abbrev=False,
    )
    restore_parser.add_argument("--manifest-key", required=True)
    restore_parser.add_argument("--target-database", required=True)
    restore_parser.add_argument(
        "--admin-database-url-env",
        default="BACKUP_RESTORE_ADMIN_DATABASE_URL",
    )
    snapshot_parser = subparsers.add_parser(
        "snapshot",
        help="create a quiesced PostgreSQL and S3 application-object snapshot",
        allow_abbrev=False,
    )
    snapshot_parser.add_argument("--database-url-env", default="DATABASE_URL")
    snapshot_parser.add_argument(
        "--confirm-source-quiesced", action="store_true", required=True
    )
    restore_snapshot_parser = subparsers.add_parser(
        "restore-snapshot",
        help="restore a paired snapshot into isolated database and object targets",
        allow_abbrev=False,
    )
    restore_snapshot_parser.add_argument("--manifest-key", required=True)
    restore_snapshot_parser.add_argument("--target-database", required=True)
    restore_snapshot_parser.add_argument("--objects-target-bucket", required=True)
    restore_snapshot_parser.add_argument(
        "--admin-database-url-env",
        default="BACKUP_RESTORE_ADMIN_DATABASE_URL",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        arguments = ["backup"]
    parser = build_parser()
    try:
        args = parser.parse_args(arguments)
    except BackupArtifactError:
        print(
            "Backup operation failed: Invalid command-line arguments", file=sys.stderr
        )
        return 2
    try:
        settings = s3_settings_from_environment()
        if args.operation in (None, "backup"):
            database_url_env = getattr(args, "database_url_env", "DATABASE_URL")
            manifest_object_key = asyncio.run(
                backup_to_s3(_environment_value(database_url_env), settings)
            )
            print(f"Backup uploaded and verified (manifest key: {manifest_object_key})")
            return 0
        if args.operation == "snapshot":
            database_url_env = getattr(args, "database_url_env", "DATABASE_URL")
            manifest_object_key = asyncio.run(
                backup_paired_snapshot_to_s3(
                    _environment_value(database_url_env),
                    settings,
                    storage_s3_settings_from_environment(),
                    confirm_source_quiesced=args.confirm_source_quiesced,
                )
            )
            print(
                "Paired snapshot uploaded and verified "
                f"(manifest key: {manifest_object_key})"
            )
            return 0
        if args.operation == "restore-snapshot":
            admin_database_url = _environment_value(args.admin_database_url_env)
            asyncio.run(
                restore_paired_snapshot_from_s3(
                    args.manifest_key,
                    args.target_database,
                    admin_database_url,
                    settings,
                    storage_s3_settings_from_environment(),
                    args.objects_target_bucket,
                )
            )
            print(
                "Paired snapshot restored into isolated database "
                f"{args.target_database} and object bucket {args.objects_target_bucket}"
            )
            return 0
        if args.operation == "restore":
            admin_database_url = _environment_value(args.admin_database_url_env)
            asyncio.run(
                restore_from_s3(
                    args.manifest_key,
                    args.target_database,
                    admin_database_url,
                    settings,
                )
            )
            print(f"Restore completed into new database {args.target_database}")
            return 0
        parser.error("operation is required")
    except BackupArtifactError as error:
        print(f"Backup operation failed: {error}", file=sys.stderr)
        return 1
    except Exception:
        print(
            "Backup operation failed; diagnostic details are suppressed",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
