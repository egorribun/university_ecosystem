"""Storage backends for user-uploaded files."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import stat
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable
from urllib.parse import urlparse

from botocore.exceptions import ClientError

from app.core.logging import get_logger

# RZ-29-01: Business-level timeout guards for S3 operations.
# DB already has command_timeout=15s (asyncpg), but aioboto3 HTTP calls
# can hang indefinitely on network issues without an explicit deadline.
_S3_WRITE_TIMEOUT: float = 30.0  # seconds — upload/put
_S3_READ_TIMEOUT: float = 15.0  # seconds — get/head/delete
_QUARANTINE_PAGE_SIZE_MAX = 1000
_QUARANTINE_DIRECTORY_ENTRIES_MAX = 10_000
_QUARANTINE_SCAN_STEPS_MAX = 10_000

if TYPE_CHECKING:
    from app.core.config import Settings

logger = get_logger(__name__)


@dataclass(frozen=True)
class QuarantineObject:
    """Bounded inventory metadata for one regular quarantined object."""

    key: str
    size_bytes: int
    last_modified: datetime | None


@dataclass(frozen=True)
class QuarantineStoragePage:
    """One bounded page from a backend's exact quarantine prefix."""

    objects: tuple[QuarantineObject, ...]
    next_cursor: str | None


class UnsafeQuarantineInventoryKey(RuntimeError):
    """An object under the quarantine prefix cannot be safely managed."""


def _has_control_chars(value: str) -> bool:
    """C0 controls and DEL can split or disguise object keys and URLs."""
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


@runtime_checkable
class StorageBackend(Protocol):
    """Protocol implemented by storage backends."""

    async def save_file(
        self,
        relative_path: str,
        data: bytes,
        *,
        content_type: str | None = None,
        cache_control: str | None = None,
    ) -> str:
        """Persist ``data`` under ``relative_path`` and return a public URL."""

    async def delete_file(self, file_url: str) -> None:
        """Delete file referenced by ``file_url`` if it exists."""

    async def exists(self, file_url_or_path: str) -> bool:
        """Check if file exists."""

    async def read_file(
        self, file_url_or_path: str, *, max_bytes: int | None = None
    ) -> bytes:
        """Read file content as bytes."""


@runtime_checkable
class QuarantineStorageBackend(StorageBackend, Protocol):
    """Storage operations required by the durable quarantine ledger."""

    async def list_quarantine_page(
        self, cursor: str | None, *, limit: int
    ) -> QuarantineStoragePage:
        """List at most ``limit`` regular objects under ``quarantine/``."""

    async def delete_quarantine_key(self, key: str) -> bool:
        """Delete one exact-prefix object and confirm it is absent."""


class StaticFSStorage(StorageBackend):
    """Store files on the local filesystem under a static directory."""

    def __init__(self, base_dir: Path, base_url: str = "/static") -> None:
        self.base_dir = base_dir
        self.base_url = base_url.rstrip("/") or ""

    def _normalize_relative_path(self, relative_path: str) -> Path:
        cleaned = relative_path.strip().strip("/")
        if not cleaned:
            raise ValueError("Relative path must not be empty")
        if "\x00" in cleaned or "\\" in cleaned:
            raise ValueError("Relative path contains invalid characters")
        candidate = Path(cleaned)
        if candidate.is_absolute():
            raise ValueError("Relative path must not be absolute")
        parts = candidate.parts
        if not parts or any(part in {"", ".", ".."} for part in parts):
            raise ValueError("Relative path must not escape base directory")
        return candidate

    def _resolve_validated_path(self, relative_path: Path) -> Path:
        """RZ-30-02: Reject symlinks and ensure resolved path stays within base_dir.

        Defense-in-depth against ZipSlip-style attacks where a symlink inside
        the upload directory points to an arbitrary filesystem location.
        ``_normalize_relative_path`` guards against ``..`` components but cannot
        detect symlinks — this method resolves the real path and verifies it.
        """
        target = self.base_dir / relative_path
        try:
            resolved = target.resolve(strict=False)  # codeql[py/path-injection]
        except OSError as exc:
            raise ValueError(f"Cannot resolve path: {exc}") from exc
        base_resolved = self.base_dir.resolve()
        if not resolved.is_relative_to(base_resolved):
            raise ValueError("Resolved path escapes base directory")
        # Walk each component to catch symlinks before the final target exists.
        current = self.base_dir
        for part in target.relative_to(self.base_dir).parts:
            current = current / part
            if current.is_symlink():
                raise ValueError(f"Symlink detected in path at {current.name}")
        return resolved

    @staticmethod
    def _validate_quarantine_limit(limit: int) -> None:
        if isinstance(limit, bool) or not 1 <= limit <= _QUARANTINE_PAGE_SIZE_MAX:
            raise ValueError(
                f"Quarantine page size must be between 1 and {_QUARANTINE_PAGE_SIZE_MAX}"
            )

    @staticmethod
    def _encode_quarantine_cursor(stack: list[tuple[str, int]]) -> str:
        payload = json.dumps(
            {"version": 1, "stack": [[path, offset] for path, offset in stack]},
            separators=(",", ":"),
        ).encode("utf-8")
        return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")

    def _decode_quarantine_cursor(self, cursor: str) -> list[tuple[str, int]]:
        try:
            encoded = cursor.encode("ascii")
            payload = base64.b64decode(
                encoded + b"=" * (-len(encoded) % 4), altchars=b"-_", validate=True
            )
            decoded = json.loads(payload)
        except (UnicodeEncodeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid quarantine inventory cursor") from exc
        if (
            not isinstance(decoded, dict)
            or decoded.get("version") != 1
            or not isinstance(decoded.get("stack"), list)
        ):
            raise ValueError("Invalid quarantine inventory cursor")
        stack: list[tuple[str, int]] = []
        for frame in decoded["stack"]:
            if (
                not isinstance(frame, list)
                or len(frame) != 2
                or not isinstance(frame[0], str)
                or isinstance(frame[1], bool)
                or not isinstance(frame[1], int)
                or frame[1] < 0
            ):
                raise ValueError("Invalid quarantine inventory cursor")
            relative = self._normalize_relative_path(frame[0]).as_posix()
            if relative != frame[0] or not (
                relative == "quarantine" or relative.startswith("quarantine/")
            ):
                raise ValueError("Invalid quarantine inventory cursor")
            stack.append((relative, frame[1]))
        return stack

    @staticmethod
    def _read_quarantine_directory(path: Path) -> list[tuple[str, str]]:
        """Read a bounded, deterministic snapshot of one directory."""
        entries: list[tuple[str, str]] = []
        with os.scandir(path) as iterator:
            for entry in iterator:
                if len(entries) >= _QUARANTINE_DIRECTORY_ENTRIES_MAX:
                    raise RuntimeError(
                        "Quarantine directory exceeds the inventory bound"
                    )
                if entry.is_symlink():
                    kind = "symlink"
                elif entry.is_dir(follow_symlinks=False):
                    kind = "directory"
                elif entry.is_file(follow_symlinks=False):
                    kind = "file"
                else:
                    kind = "other"
                entries.append((entry.name, kind))
        entries.sort(key=lambda item: item[0])
        return entries

    async def list_quarantine_page(
        self, cursor: str | None, *, limit: int
    ) -> QuarantineStoragePage:
        """Walk only regular files under quarantine using a bounded cursor."""
        self._validate_quarantine_limit(limit)
        if cursor is None:
            root = self._resolve_validated_path(Path("quarantine"))
            if not await asyncio.to_thread(root.exists):
                return QuarantineStoragePage((), None)
            if not await asyncio.to_thread(root.is_dir):
                raise RuntimeError("Quarantine root is not a directory")
            stack = [("quarantine", 0)]
        else:
            stack = self._decode_quarantine_cursor(cursor)

        objects: list[QuarantineObject] = []
        steps = 0
        while stack and len(objects) < limit and steps < _QUARANTINE_SCAN_STEPS_MAX:
            relative_dir, offset = stack[-1]
            directory = self._resolve_validated_path(Path(relative_dir))
            entries = await asyncio.to_thread(
                self._read_quarantine_directory, directory
            )
            if offset >= len(entries):
                stack.pop()
                continue

            name, kind = entries[offset]
            stack[-1] = (relative_dir, offset + 1)
            steps += 1
            relative_child = f"{relative_dir}/{name}"
            try:
                normalized_child = self._normalize_relative_path(relative_child)
            except ValueError as exc:
                raise UnsafeQuarantineInventoryKey(
                    "Filesystem returned an invalid quarantine object key"
                ) from exc
            if (
                normalized_child.as_posix() != relative_child
                or _has_control_chars(relative_child)
                or not relative_child.startswith("quarantine/")
            ):
                raise UnsafeQuarantineInventoryKey(
                    "Filesystem returned an invalid quarantine object key"
                )
            if kind in {"symlink", "other"}:
                continue
            if kind == "directory":
                stack.append((relative_child, 0))
                continue

            child_path = self._resolve_validated_path(Path(relative_child))
            metadata = await asyncio.to_thread(child_path.stat, follow_symlinks=False)
            if not stat.S_ISREG(metadata.st_mode):
                continue
            objects.append(
                QuarantineObject(
                    key=relative_child,
                    size_bytes=metadata.st_size,
                    last_modified=datetime.fromtimestamp(metadata.st_mtime, UTC),
                )
            )

        next_cursor = self._encode_quarantine_cursor(stack) if stack else None
        return QuarantineStoragePage(tuple(objects), next_cursor)

    async def delete_quarantine_key(self, key: str) -> bool:
        """Delete one file below the quarantine root without following links."""
        relative = self._normalize_relative_path(key)
        normalized = relative.as_posix()
        if normalized != key or not normalized.startswith("quarantine/"):
            raise ValueError("Quarantine key must use the quarantine prefix")
        target = self._resolve_validated_path(relative)
        return await asyncio.to_thread(self._unlink_quarantine_file, target)

    @staticmethod
    def _unlink_quarantine_file(path: Path) -> bool:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return not os.path.lexists(path)

    async def save_file(
        self,
        relative_path: str,
        data: bytes,
        *,
        content_type: str | None = None,
        cache_control: str | None = None,
    ) -> str:
        del content_type, cache_control  # unused for filesystem storage
        normalized = self._normalize_relative_path(relative_path)
        target = self._resolve_validated_path(normalized)  # RZ-30-02
        # target is resolved and constrained to base_dir by _resolve_validated_path.
        await asyncio.to_thread(  # codeql[py/path-injection]
            target.parent.mkdir, parents=True, exist_ok=True
        )
        await asyncio.to_thread(target.write_bytes, data)  # codeql[py/path-injection]
        relative_str = normalized.as_posix()
        if self.base_url:
            return f"{self.base_url}/{relative_str}"
        return f"/{relative_str}"

    def _extract_relative_path(self, file_url: str) -> Path | None:
        if not file_url:
            return None
        trimmed = file_url.strip()
        if not trimmed:
            return None
        prefix = self.base_url.rstrip("/") if self.base_url else ""
        if prefix and trimmed.startswith(prefix):
            trimmed = trimmed[len(prefix) :]
        trimmed = trimmed.lstrip("/")
        if not trimmed:
            return None
        try:
            return self._normalize_relative_path(trimmed)
        except ValueError:
            return None

    @staticmethod
    def _unlink_ignore_missing(path: Path) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            return
        except OSError:
            # Paths and OS exception messages can carry user data. Durable
            # callers verify that the file still exists before acknowledging.
            logger.warning("static_delete_failed")

    async def delete_file(self, file_url: str) -> None:
        relative = self._extract_relative_path(file_url)
        if relative is None:
            return
        target = self._resolve_validated_path(relative)  # RZ-30-02
        await asyncio.to_thread(self._unlink_ignore_missing, target)

    async def exists(self, file_url_or_path: str) -> bool:
        relative = self._extract_relative_path(file_url_or_path)
        if relative is None:
            # Fallback for raw paths
            relative = self._normalize_relative_path(file_url_or_path)
        target = self._resolve_validated_path(relative)  # RZ-30-02
        return await asyncio.to_thread(target.exists)

    @staticmethod
    def _read_bounded(path: Path, max_bytes: int) -> bytes:
        with path.open("rb") as file:
            return file.read(max_bytes + 1)

    async def read_file(
        self, file_url_or_path: str, *, max_bytes: int | None = None
    ) -> bytes:
        if max_bytes is not None and max_bytes < 0:
            raise ValueError("max_bytes must be nonnegative")
        relative = self._extract_relative_path(file_url_or_path)
        if relative is None:
            # Fallback for raw paths
            relative = self._normalize_relative_path(file_url_or_path)
        target = self._resolve_validated_path(relative)  # RZ-30-02
        if not await asyncio.to_thread(target.exists):
            raise FileNotFoundError(f"File not found: {file_url_or_path}")
        if max_bytes is None:
            return await asyncio.to_thread(target.read_bytes)
        return await asyncio.to_thread(self._read_bounded, target, max_bytes)


class S3Storage(StorageBackend):
    """Store files in an S3-compatible object storage.

    PERF-7 (audit 2026-03-05): Uses aioboto3 (async-native boto3 wrapper, v15.5.0)
    instead of synchronous boto3 + asyncio.to_thread. Native async removes the
    thread-pool overhead on every single S3 operation.
    """

    def __init__(
        self,
        *,
        bucket: str,
        region: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        endpoint_url: str | None = None,
        base_url: str | None = None,
        client: Any = None,
        extra_put_object_args: dict[str, Any] | None = None,
    ) -> None:
        if not bucket:
            raise ValueError("Bucket name must not be empty")
        self.bucket = bucket
        # client parameter kept for test injection (allows passing a mock async client).
        self._injected_client = client
        self._region = region
        self._access_key_id = access_key
        self._secret_access_key = secret_key
        self._endpoint_url = endpoint_url
        # Derive the public base URL used in returned file URLs.
        resolved_base_url = (base_url or "").rstrip("/")
        if not resolved_base_url:
            if endpoint_url:
                resolved_base_url = f"{endpoint_url.rstrip('/')}/{bucket}"
            else:
                resolved_base_url = f"https://{bucket}.s3.amazonaws.com"
        self.base_url = resolved_base_url
        self._base_url_parsed = urlparse(self.base_url)
        self._extra_put_object_args: dict[str, str] = extra_put_object_args or {}

    def _normalize_key(self, relative_path: str) -> str:
        if _has_control_chars(relative_path):
            raise ValueError("Relative path contains control characters")
        if not relative_path:
            raise ValueError("Relative path must not be empty")
        if relative_path.strip() != relative_path:
            raise ValueError("Relative path must not contain outer whitespace")
        if self._validated_key(relative_path) is None:
            raise ValueError("Relative path must not escape bucket prefix")
        return relative_path

    @staticmethod
    def _validated_key(key: str) -> str | None:
        """Accept only unambiguous POSIX object keys, without rewriting them."""
        if (
            not key
            or any(char in "\\%?#;" for char in key)
            or _has_control_chars(key)
            or any(part in {"", ".", ".."} for part in key.split("/"))
        ):
            return None
        return key

    async def save_file(
        self,
        relative_path: str,
        data: bytes,
        *,
        content_type: str | None = None,
        cache_control: str | None = None,
    ) -> str:
        key = self._normalize_key(relative_path)
        args: dict[str, Any] = {
            "Bucket": self.bucket,
            "Key": key,
            "Body": data,
            **self._extra_put_object_args,
        }
        if content_type:
            args["ContentType"] = content_type
        if cache_control:
            args["CacheControl"] = cache_control
        try:
            async with asyncio.timeout(_S3_WRITE_TIMEOUT):  # RZ-29-01
                async with self._build_aioboto3_client() as s3:
                    await s3.put_object(**args)
        except (ConnectionError, TimeoutError, OSError):  # RZ-28-01
            # RZ-20-04: Narrowed — S3/MinIO upload failures are infra issues.
            logger.exception("Failed to upload %s to bucket %s", key, self.bucket)
            raise
        return f"{self.base_url}/{key}"

    @asynccontextmanager
    async def _build_aioboto3_client(self) -> AsyncIterator[Any]:
        """Yield an async S3 client for the duration of a single operation.

        Two modes:
        - Test injection: if ``_injected_client`` was passed to the constructor
          it is yielded directly (no real AWS connection).
        - Production: opens an aioboto3 session and client as async context
          managers, ensuring the HTTP connection is closed after every call.
        """
        if self._injected_client is not None:
            yield self._injected_client
            return

        import aioboto3

        session = aioboto3.Session()
        async with session.client(
            "s3",
            region_name=self._region or None,
            aws_access_key_id=self._access_key_id or None,
            aws_secret_access_key=self._secret_access_key or None,
            endpoint_url=self._endpoint_url or None,
        ) as client:
            yield client

    async def probe_bucket(self) -> None:
        """Check S3 bucket availability without interpreting an empty key."""
        async with asyncio.timeout(_S3_READ_TIMEOUT):
            async with self._build_aioboto3_client() as s3:
                await s3.head_bucket(Bucket=self.bucket)

    async def assert_quarantine_versioning_disabled(self) -> None:
        """Refuse managed quota when versioned object bytes can remain hidden."""
        async with asyncio.timeout(_S3_READ_TIMEOUT):
            async with self._build_aioboto3_client() as s3:
                response = await s3.get_bucket_versioning(Bucket=self.bucket)
        allowed_fields = {"Status", "MFADelete", "ResponseMetadata"}
        metadata = (
            response.get("ResponseMetadata") if isinstance(response, dict) else None
        )
        if (
            not isinstance(response, dict)
            or not set(response).issubset(allowed_fields)
            or response.get("Status") not in (None, "")
            or response.get("MFADelete") not in (None, "")
            or (metadata is not None and not isinstance(metadata, dict))
        ):
            raise RuntimeError("Quarantine requires an unversioned S3 bucket")

    @staticmethod
    def _validate_quarantine_limit(limit: int) -> None:
        if isinstance(limit, bool) or not 1 <= limit <= _QUARANTINE_PAGE_SIZE_MAX:
            raise ValueError(
                f"Quarantine page size must be between 1 and {_QUARANTINE_PAGE_SIZE_MAX}"
            )

    @staticmethod
    def _validate_quarantine_key(key: str) -> str:
        if (
            not isinstance(key, str)
            or not key.startswith("quarantine/")
            or S3Storage._validated_key(key) != key
        ):
            raise ValueError("Quarantine key must use the quarantine prefix")
        return key

    async def list_quarantine_page(
        self, cursor: str | None, *, limit: int
    ) -> QuarantineStoragePage:
        """List at most one bounded S3 page under the exact owned prefix."""
        self._validate_quarantine_limit(limit)
        args: dict[str, Any] = {
            "Bucket": self.bucket,
            "Prefix": "quarantine/",
            "MaxKeys": limit,
        }
        if cursor is not None:
            if not cursor:
                raise ValueError("Invalid S3 quarantine inventory cursor")
            args["ContinuationToken"] = cursor

        async with asyncio.timeout(_S3_READ_TIMEOUT):
            async with self._build_aioboto3_client() as s3:
                response = await s3.list_objects_v2(**args)

        if (
            not isinstance(response, dict)
            or "IsTruncated" not in response
            or not isinstance(response["IsTruncated"], bool)
        ):
            raise RuntimeError("S3 returned an invalid quarantine page status")
        contents = response.get("Contents", [])
        if not isinstance(contents, list) or len(contents) > limit:
            raise RuntimeError("S3 returned an invalid quarantine inventory page")
        objects: list[QuarantineObject] = []
        for item in contents:
            if not isinstance(item, dict):
                raise RuntimeError("S3 returned invalid quarantine object metadata")
            key = item.get("Key")
            size = item.get("Size")
            if not isinstance(key, str):
                raise RuntimeError("S3 returned an invalid quarantine object key")
            # Be defensive about a nonconforming S3 endpoint despite Prefix.
            if not key.startswith("quarantine/") or key == "quarantine/":
                continue
            try:
                self._validate_quarantine_key(key)
            except ValueError as exc:
                raise UnsafeQuarantineInventoryKey(
                    "S3 returned an invalid quarantine object key"
                ) from exc
            if isinstance(size, bool) or not isinstance(size, int) or size < 0:
                raise RuntimeError("S3 returned an invalid quarantine object size")
            last_modified = item.get("LastModified")
            if isinstance(last_modified, datetime) and last_modified.tzinfo is None:
                last_modified = last_modified.replace(tzinfo=UTC)
            if not isinstance(last_modified, datetime):
                last_modified = None
            objects.append(QuarantineObject(key, size, last_modified))

        truncated = response["IsTruncated"]
        next_cursor = response.get("NextContinuationToken") if truncated else None
        if truncated and (not isinstance(next_cursor, str) or not next_cursor):
            raise RuntimeError("S3 omitted its quarantine continuation token")
        return QuarantineStoragePage(tuple(objects), next_cursor)

    async def delete_quarantine_key(self, key: str) -> bool:
        """Delete one exact quarantine object and verify the key is absent."""
        normalized = self._validate_quarantine_key(key)
        async with asyncio.timeout(_S3_READ_TIMEOUT):
            async with self._build_aioboto3_client() as s3:
                await s3.delete_object(Bucket=self.bucket, Key=normalized)
                try:
                    await s3.head_object(Bucket=self.bucket, Key=normalized)
                except ClientError as exc:
                    error_code = exc.response.get("Error", {}).get("Code", "")
                    if error_code in {"404", "NoSuchKey", "NotFound"}:
                        return True
                    raise
                return False

    def _extract_key(self, file_url: str) -> str | None:
        if not file_url:
            return None
        # Validate before strip(): otherwise leading/trailing controls could
        # select a different object key from the caller-provided value.
        if _has_control_chars(file_url):
            return None
        trimmed = file_url.strip()
        if not trimmed or trimmed != file_url or trimmed.startswith("//"):
            return None
        parsed = urlparse(trimmed)
        if parsed.params or parsed.query or parsed.fragment:
            return None
        if parsed.scheme in {"http", "https"}:
            if (
                parsed.scheme != self._base_url_parsed.scheme
                or parsed.netloc != self._base_url_parsed.netloc
            ):
                return None
            path = parsed.path or ""
            base_path = self._base_url_parsed.path
            if base_path:
                if not path.startswith(f"{base_path}/"):
                    return None
                key = path[len(base_path) + 1 :]
            else:
                if not path.startswith("/"):
                    return None
                key = path[1:]
            return self._validated_key(key)
        if parsed.scheme == "s3":
            if parsed.netloc != self.bucket or not parsed.path.startswith("/"):
                return None
            key = parsed.path[1:]
            return self._validated_key(key)
        if parsed.scheme or parsed.netloc:
            return None
        path = parsed.path
        if path.startswith("/"):
            if self._base_url_parsed.scheme:
                return None
            base_path = self._base_url_parsed.path
            if not base_path or not path.startswith(f"{base_path}/"):
                return None
            key = path[len(base_path) + 1 :]
        else:
            key = path
        return self._validated_key(key)

    async def delete_file(self, file_url: str) -> None:
        key = self._extract_key(file_url)
        if not key:
            return
        try:
            async with asyncio.timeout(_S3_READ_TIMEOUT):  # RZ-29-01
                async with self._build_aioboto3_client() as s3:
                    await s3.delete_object(Bucket=self.bucket, Key=key)
        except (ConnectionError, TimeoutError, OSError):
            # RZ-20-04: Narrowed — S3 delete is best-effort (fire-and-forget).
            # Object keys and provider exception messages may contain private
            # user data. Durable callers verify object absence and retry.
            logger.warning("s3_delete_failed")

    async def exists(self, file_url_or_path: str) -> bool:
        key = self._extract_key(file_url_or_path)
        if not key:
            return False
        try:
            async with asyncio.timeout(_S3_READ_TIMEOUT):  # RZ-29-01
                async with self._build_aioboto3_client() as s3:
                    await s3.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception as exc:  # RZ-22-01-JUSTIFIED: re-raise-after-cleanup — only swallows 404, re-raises others (reviewed TD-27-04)
            # HIGH-W19 + RZ-20-04: Only swallow S3 "not found" (404/NoSuchKey);
            # re-raise everything else (credentials, network, programming errors).
            # We keep `except Exception` here intentionally because botocore may
            # raise non-ClientError types (EndpointConnectionError, etc.) that
            # must propagate — the isinstance check ensures ONLY 404 is swallowed.
            if isinstance(exc, ClientError):
                error_code = exc.response.get("Error", {}).get("Code", "")
                if error_code in ("404", "NoSuchKey"):
                    return False
            raise

    async def read_file(
        self, file_url_or_path: str, *, max_bytes: int | None = None
    ) -> bytes:
        if max_bytes is not None and max_bytes < 0:
            raise ValueError("max_bytes must be nonnegative")
        key = self._extract_key(file_url_or_path)
        if not key:
            raise FileNotFoundError(f"S3 file not found: {file_url_or_path}")
        try:
            async with asyncio.timeout(_S3_READ_TIMEOUT):  # RZ-29-01
                async with self._build_aioboto3_client() as s3:
                    response = await s3.get_object(Bucket=self.bucket, Key=key)
                    body_stream = response["Body"]
                    async with body_stream:
                        if max_bytes is None:
                            body: bytes = await body_stream.read()
                            return body
                        content = bytearray()
                        limit = max_bytes + 1
                        while len(content) < limit:
                            remaining = limit - len(content)
                            chunk: bytes = await body_stream.read(remaining)
                            if not chunk:
                                break
                            content.extend(chunk[:remaining])
                        return bytes(content)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code in ("404", "NoSuchKey"):
                raise FileNotFoundError(
                    f"S3 file not found: {file_url_or_path}"
                ) from exc
            raise
        except (FileNotFoundError, OSError, ConnectionError) as exc:
            # RZ-20-04: Narrowed — S3 read errors. Converts to FileNotFoundError
            # for uniform caller interface.
            logger.error("s3_read_failed")
            raise FileNotFoundError(f"S3 file not found: {file_url_or_path}") from exc


def get_storage_backend(settings: Settings) -> QuarantineStorageBackend:
    backend = str(settings.storage_backend).strip().lower()
    if backend in {"static", "filesystem", "local"}:
        return StaticFSStorage(
            settings.static_dir_path, base_url=settings.storage_static_base_url
        )
    if backend in {"s3", "minio"}:
        return S3Storage(
            bucket=settings.storage_s3_bucket,
            region=getattr(settings, "storage_s3_region", None) or None,
            access_key=getattr(settings, "storage_s3_access_key_id", None) or None,
            secret_key=getattr(settings, "storage_s3_secret_access_key", None) or None,
            endpoint_url=getattr(settings, "storage_s3_endpoint_url", None) or None,
            base_url=getattr(settings, "storage_s3_base_url", None) or None,
        )
    raise ValueError(f"Unsupported storage backend: {settings.storage_backend}")
