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
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Never, cast

import aioboto3
import psycopg
from psycopg import sql
from sqlalchemy.engine import URL, make_url

MANIFEST_SCHEMA_VERSION = 1
MANIFEST_MAX_BYTES = 64 * 1024
CHUNK_SIZE = 1024 * 1024
FORMAT = "pg_dump.custom"
ARTIFACT_SUFFIX = ".dump"
MANIFEST_SUFFIX = ".manifest.json"
_RESTORE_DATABASE_RE = re.compile(r"^restore_[a-z0-9_]{1,54}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
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


def manifest_key(artifact_key: str) -> str:
    _validate_object_key(artifact_key)
    if not artifact_key.endswith(ARTIFACT_SUFFIX):
        raise BackupArtifactError("Artifact key must name a custom-format dump")
    return artifact_key[: -len(ARTIFACT_SUFFIX)] + MANIFEST_SUFFIX


def new_artifact_key(prefix: str = "database") -> str:
    if prefix:
        _validate_object_key(prefix)
        prefix = prefix.rstrip("/")
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    name = f"university-{timestamp}-{uuid.uuid4().hex}{ARTIFACT_SUFFIX}"
    return f"{prefix}/{name}" if prefix else name


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


async def _hash_remote_object(client: Any, bucket: str, key: str) -> tuple[int, str]:
    response = await _get_object(client, bucket, key)
    body = response.get("Body")
    if body is None:
        raise BackupArtifactError("S3 backup object had no response body")
    digest = hashlib.sha256()
    size = 0
    try:
        while chunk := await _read_body(body, CHUNK_SIZE):
            size += len(chunk)
            digest.update(chunk)
    finally:
        await _close_body(body)
    content_length = response.get("ContentLength")
    if content_length is not None and content_length != size:
        raise BackupArtifactError("S3 backup object length did not match its response")
    return size, digest.hexdigest()


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
    remote_size, remote_sha256 = await _hash_remote_object(client, bucket, key)
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
        raise BackupArtifactError("Unable to upload backup manifest to S3") from None
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
    return manifest_object_key


async def download_verified_backup(
    client: Any,
    bucket: str,
    manifest_object_key: str,
    destination: Path,
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
        with destination.open("xb") as stream:
            created = True
            while chunk := await _read_body(body, CHUNK_SIZE):
                stream.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        await _close_body(body)
        body_closed = True
        content_length = response.get("ContentLength")
        if content_length is not None and content_length != size:
            raise BackupArtifactError(
                "S3 database dump length did not match its response"
            )
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
        if not body_closed:
            with suppress(Exception):
                await _close_body(body)
        if created and not verified:
            destination.unlink(missing_ok=True)


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
    except Exception:
        raise BackupArtifactError(
            "Unable to read source database name and Alembic revision"
        ) from None
    if not source_database or not revisions:
        raise BackupArtifactError("Source database has no Alembic revision")
    return str(source_database), revisions


def validate_restore_target(source_database: str, target_database: str) -> None:
    if not isinstance(target_database, str) or not _RESTORE_DATABASE_RE.fullmatch(
        target_database
    ):
        raise BackupArtifactError(
            "Restore target must be a new database named restore_<name>"
        )
    if target_database == source_database:
        raise BackupArtifactError(
            "Restore target must be different from the source database"
        )


def _ensure_new_database(
    admin_database_url: str,
    target_database: str,
) -> None:
    url = _database_url(admin_database_url)
    if url.database == target_database:
        raise BackupArtifactError(
            "Admin connection must not point at the restore target"
        )
    dsn = _psycopg_dsn(url)
    try:
        with psycopg.connect(dsn, autocommit=True) as connection:
            exists = connection.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s",
                (target_database,),
            ).fetchone()
            if exists:
                raise BackupArtifactError("Restore target database already exists")
            # psycopg Identifier safely quotes the validated target identifier.
            connection.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target_database))
            )
    except BackupArtifactError:
        raise
    except Exception:
        raise BackupArtifactError(
            "Unable to create the new restore target database"
        ) from None


def restore_archive(
    archive_path: Path,
    manifest: BackupManifest,
    admin_database_url: str,
    target_database: str,
    *,
    command_runner: Callable[..., Any] = subprocess.run,
) -> None:
    validate_restore_target(manifest.source_database, target_database)
    if not archive_path.is_file():
        raise BackupArtifactError("Verified database dump is unavailable")
    environment = _pg_tool_environment(
        admin_database_url, database_override=target_database
    )
    _run_pg_tool(
        ["pg_restore", "--list", str(archive_path)],
        environment,
        command_runner=command_runner,
    )
    _ensure_new_database(admin_database_url, target_database)
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
    endpoint_url: str
    bucket: str
    prefix: str
    region: str


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


@asynccontextmanager
async def s3_client(settings: S3Settings) -> AsyncIterator[Any]:
    try:
        async with aioboto3.Session().client(
            "s3",
            endpoint_url=settings.endpoint_url,
            region_name=settings.region,
        ) as client:
            yield client
    except BackupArtifactError:
        raise
    except Exception:
        raise BackupArtifactError(
            "Unable to initialize the configured S3 client"
        ) from None


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
    with tempfile.TemporaryDirectory(prefix="university-db-restore-") as temp_dir:
        archive_path = Path(temp_dir) / "database.dump"
        async with s3_client(settings) as client:
            manifest = await download_verified_backup(
                client,
                settings.bucket,
                manifest_object_key,
                archive_path,
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
