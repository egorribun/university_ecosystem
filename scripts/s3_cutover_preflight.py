"""Read-only object inventory and verification for an S3 storage cutover.

The command never copies or deletes objects. Operators must quiesce writers and
retain the old volume before comparing the source and destination inventories.
Credentials are read only from environment variables, never command arguments.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import sys
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse


@dataclass(frozen=True)
class ObjectSnapshot:
    size: int
    sha256: str
    content_type: str
    cache_control: str
    user_metadata: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class BucketSnapshot:
    objects: dict[str, ObjectSnapshot]
    count: int
    total_bytes: int
    fingerprint: str


class S3Client(Protocol):
    def get_bucket_versioning(self, bucket: str) -> object: ...

    def list_objects(self, bucket: str, *, recursive: bool) -> object: ...

    def stat_object(self, bucket: str, key: str) -> object: ...

    def get_object(self, bucket: str, key: str) -> object: ...


def snapshot_bucket(client: S3Client, bucket: str) -> BucketSnapshot:
    """Hash every current object and compare metadata relevant to delivery."""

    versioning = client.get_bucket_versioning(bucket)
    if getattr(versioning, "status", None) not in (None, ""):
        raise ValueError("bucket versioning needs a separate migration procedure")

    objects: dict[str, ObjectSnapshot] = {}
    total_bytes = 0
    for listing in client.list_objects(bucket, recursive=True):  # type: ignore[attr-defined]
        key = listing.object_name
        if not key or key in objects:
            raise ValueError("object inventory contains an empty or duplicate key")
        stat = client.stat_object(bucket, key)
        metadata = {
            str(name).lower(): str(value)
            for name, value in getattr(stat, "metadata", {}).items()
        }
        response = client.get_object(bucket, key)
        digest = hashlib.sha256()
        size = 0
        try:
            while chunk := response.read(1024 * 1024):  # type: ignore[attr-defined]
                digest.update(chunk)
                size += len(chunk)
        finally:
            response.close()  # type: ignore[attr-defined]
            response.release_conn()  # type: ignore[attr-defined]
        if size != listing.size:
            raise ValueError("object changed while inventory was being captured")
        objects[key] = ObjectSnapshot(
            size=size,
            sha256=digest.hexdigest(),
            content_type=str(getattr(stat, "content_type", "") or ""),
            cache_control=metadata.get("cache-control", ""),
            user_metadata=tuple(
                sorted(
                    (name, value)
                    for name, value in metadata.items()
                    if name.startswith("x-amz-meta-")
                )
            ),
        )
        total_bytes += size

    manifest = hashlib.sha256()
    for key, object_snapshot in sorted(objects.items()):
        for value in (
            key,
            str(object_snapshot.size),
            object_snapshot.sha256,
            object_snapshot.content_type,
            object_snapshot.cache_control,
            json.dumps(object_snapshot.user_metadata, separators=(",", ":")),
        ):
            encoded = value.encode("utf-8")
            manifest.update(len(encoded).to_bytes(8, "big"))
            manifest.update(encoded)
    return BucketSnapshot(
        objects=objects,
        count=len(objects),
        total_bytes=total_bytes,
        fingerprint=manifest.hexdigest(),
    )


def compare_snapshots(source: BucketSnapshot, target: BucketSnapshot) -> bool:
    """Exact keys, bytes, content types and cache policy must match."""

    return source.objects == target.objects


def _ensure_distinct_endpoints() -> None:
    source = urlparse(os.environ.get("S3_SOURCE_ENDPOINT", ""))
    target = urlparse(os.environ.get("S3_TARGET_ENDPOINT", ""))
    if not source.hostname or not target.hostname:
        return  # _client_from_environment reports the missing/invalid endpoint.
    source_port = source.port or (443 if source.scheme == "https" else 80)
    target_port = target.port or (443 if target.scheme == "https" else 80)
    if (
        source.scheme == target.scheme
        and source.hostname == target.hostname
        and source_port == target_port
    ):
        raise ValueError("source and target S3 endpoints must be distinct")
    source_addresses = {
        entry[4][0]
        for entry in socket.getaddrinfo(
            source.hostname, source_port, type=socket.SOCK_STREAM
        )
    }
    target_addresses = {
        entry[4][0]
        for entry in socket.getaddrinfo(
            target.hostname, target_port, type=socket.SOCK_STREAM
        )
    }
    if not source_addresses or not target_addresses:
        raise ValueError("source and target S3 endpoint identity is unresolved")
    if source_addresses & target_addresses:
        raise ValueError("source and target S3 endpoints must be distinct")


def _client_from_environment(prefix: str, *, allow_http: bool) -> S3Client:
    from minio import Minio

    endpoint = os.environ.get(f"S3_{prefix}_ENDPOINT", "")
    access_key = os.environ.get(f"S3_{prefix}_ACCESS_KEY", "")
    secret_key = os.environ.get(f"S3_{prefix}_SECRET_KEY", "")
    parsed = urlparse(endpoint)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or (parsed.scheme == "http" and not allow_http)
    ):
        raise ValueError(f"S3_{prefix}_ENDPOINT must be a bare HTTPS origin")
    if parsed.scheme == "http" and parsed.hostname not in {
        "localhost",
        "127.0.0.1",
        "minio",
        "seaweedfs-target",
    }:
        raise ValueError("HTTP is permitted only for local Compose endpoints")
    if not access_key or not secret_key:
        raise ValueError(f"S3_{prefix} credentials are required")
    return Minio(
        parsed.netloc,
        access_key=access_key,
        secret_key=secret_key,
        secure=parsed.scheme == "https",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("inventory", "verify"))
    parser.add_argument("--allow-http-local", action="store_true")
    args = parser.parse_args(argv)
    bucket = os.environ.get("S3_CUTOVER_BUCKET", "")
    if bucket != "uploads":
        print(
            "S3_CUTOVER_BUCKET must match the deployed uploads bucket", file=sys.stderr
        )
        return 2
    try:
        if args.mode == "verify":
            _ensure_distinct_endpoints()
        source = _client_from_environment("SOURCE", allow_http=args.allow_http_local)
        source_snapshot = snapshot_bucket(source, bucket)
        print(
            f"source count={source_snapshot.count} bytes={source_snapshot.total_bytes} "
            f"sha256={source_snapshot.fingerprint}"
        )
        if args.mode == "inventory":
            return 0
        target = _client_from_environment("TARGET", allow_http=args.allow_http_local)
        target_snapshot = snapshot_bucket(target, bucket)
        print(
            f"target count={target_snapshot.count} bytes={target_snapshot.total_bytes} "
            f"sha256={target_snapshot.fingerprint}"
        )
        if not compare_snapshots(source_snapshot, target_snapshot):
            print("source and target differ; cutover is blocked", file=sys.stderr)
            return 1
        print("object inventory matches; continue with URL and access-policy gates")
        return 0
    except Exception:  # RZ-22-01-JUSTIFIED: fail-closed S3 migration gate without leaking SDK exception text
        # SDK exceptions can include endpoint/credential details in their string
        # representation. Never print exception text into CI/operator logs.
        print("S3 inventory failed; cutover is blocked", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
