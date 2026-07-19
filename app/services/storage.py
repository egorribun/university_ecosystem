"""Storage backends for user-uploaded files."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast, runtime_checkable
from urllib.parse import urlparse

from app.core.logging import get_logger

# RZ-29-01: Business-level timeout guards for S3 operations.
# DB already has command_timeout=15s (asyncpg), but aioboto3 HTTP calls
# can hang indefinitely on network issues without an explicit deadline.
_S3_WRITE_TIMEOUT: float = 30.0  # seconds — upload/put
_S3_READ_TIMEOUT: float = 15.0  # seconds — get/head/delete

if TYPE_CHECKING:
    from app.core.config import Settings

logger = get_logger(__name__)


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

    async def read_file(self, file_url_or_path: str) -> bytes:
        """Read file content as bytes."""


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
            if current.exists() and current.is_symlink():
                raise ValueError(f"Symlink detected in path at {current.name}")
        return resolved

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
            logger.warning("Failed to remove file at %s", path, exc_info=True)

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

    async def read_file(self, file_url_or_path: str) -> bytes:
        relative = self._extract_relative_path(file_url_or_path)
        if relative is None:
            # Fallback for raw paths
            relative = self._normalize_relative_path(file_url_or_path)
        target = self._resolve_validated_path(relative)  # RZ-30-02
        if not await asyncio.to_thread(target.exists):
            raise FileNotFoundError(f"File not found: {file_url_or_path}")
        return await asyncio.to_thread(target.read_bytes)


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
        cleaned = relative_path.strip().strip("/")
        if not cleaned:
            raise ValueError("Relative path must not be empty")
        candidate = Path(cleaned)
        if candidate.is_absolute() or any(part == ".." for part in candidate.parts):
            raise ValueError("Relative path must not escape bucket prefix")
        return candidate.as_posix()

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
        except (ConnectionError, TimeoutError, OSError):# RZ-28-01
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

    def _extract_key(self, file_url: str) -> str | None:
        if not file_url:
            return None
        trimmed = file_url.strip()
        if not trimmed:
            return None
        parsed = urlparse(trimmed)
        if parsed.scheme in {"http", "https"}:
            if parsed.netloc and parsed.netloc != self._base_url_parsed.netloc:
                return None
            path = parsed.path or ""
            base_path = (self._base_url_parsed.path or "").rstrip("/")
            if base_path and path.startswith(base_path):
                path = path[len(base_path) :]
            key = path.lstrip("/")
            return key or None
        if parsed.scheme == "s3":
            if parsed.netloc and parsed.netloc != self.bucket:
                return None
            key = parsed.path.lstrip("/")
            return key or None
        trimmed = trimmed.lstrip("/")
        return trimmed or None

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
            logger.warning(
                "Failed to delete %s from bucket %s", key, self.bucket, exc_info=True
            )

    async def exists(self, file_url_or_path: str) -> bool:
        key = self._extract_key(file_url_or_path)
        if not key:
            key = file_url_or_path.lstrip("/")
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
            from botocore.exceptions import ClientError

            if isinstance(exc, ClientError):
                error_code = exc.response.get("Error", {}).get("Code", "")
                if error_code in ("404", "NoSuchKey"):
                    return False
            raise

    async def read_file(self, file_url_or_path: str) -> bytes:
        key = self._extract_key(file_url_or_path)
        if not key:
            key = file_url_or_path.lstrip("/")
        try:
            async with asyncio.timeout(_S3_READ_TIMEOUT):  # RZ-29-01
                async with self._build_aioboto3_client() as s3:
                    response = await s3.get_object(Bucket=self.bucket, Key=key)
                    async with response["Body"] as stream:
                        return cast(bytes, await stream.read())
        except (FileNotFoundError, OSError, ConnectionError) as exc:
            # RZ-20-04: Narrowed — S3 read errors. Converts to FileNotFoundError
            # for uniform caller interface.
            logger.error("Failed to read %s from bucket %s: %s", key, self.bucket, exc)
            raise FileNotFoundError(f"S3 file not found: {file_url_or_path}") from exc


def get_storage_backend(settings: Settings) -> StorageBackend:
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
