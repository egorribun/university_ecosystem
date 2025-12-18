"""Storage backends for user-uploaded files."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

from app.core.config import Settings

logger = logging.getLogger(__name__)


class StorageBackend(Protocol):
    """Protocol implemented by storage backends."""

    async def save_file(
        self, relative_path: str, data: bytes, *, content_type: str | None = None, cache_control: str | None = None
    ) -> str:
        """Persist ``data`` under ``relative_path`` and return a public URL."""

    async def delete_file(self, file_url: str) -> None:
        """Delete file referenced by ``file_url`` if it exists."""


class StaticFSStorage(StorageBackend):
    """Store files on the local filesystem under a static directory."""

    def __init__(self, base_dir: Path, base_url: str = "/static") -> None:
        self.base_dir = base_dir
        self.base_url = base_url.rstrip("/") or ""

    def _normalize_relative_path(self, relative_path: str) -> Path:
        cleaned = relative_path.strip().strip("/")
        if not cleaned:
            raise ValueError("Relative path must not be empty")
        candidate = Path(cleaned)
        if candidate.is_absolute() or any(part == ".." for part in candidate.parts):
            raise ValueError("Relative path must not escape base directory")
        return candidate

    async def save_file(
        self, relative_path: str, data: bytes, *, content_type: str | None = None, cache_control: str | None = None
    ) -> str:
        del content_type, cache_control  # unused for filesystem storage
        normalized = self._normalize_relative_path(relative_path)
        target = self.base_dir / normalized
        await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(target.write_bytes, data)
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
        await asyncio.to_thread(self._unlink_ignore_missing, self.base_dir / relative)


class S3Storage(StorageBackend):
    """Store files in an S3-compatible object storage."""

    def __init__(
        self,
        *,
        bucket: str,
        region: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        endpoint_url: str | None = None,
        base_url: str | None = None,
        client=None,
        extra_put_object_args: dict[str, str] | None = None,
    ) -> None:
        if not bucket:
            raise ValueError("Bucket name must not be empty")
        self.bucket = bucket
        if client is None:
            try:
                import boto3
            except (
                ImportError
            ) as exc:  # pragma: no cover - import error handled in tests
                raise RuntimeError("boto3 is required for S3 storage") from exc
            client = boto3.client(
                "s3",
                region_name=region,
                aws_access_key_id=access_key_id or None,
                aws_secret_access_key=secret_access_key or None,
                endpoint_url=endpoint_url or None,
            )
        self.client = client
        self._extra_put_object_args = extra_put_object_args or {}
        resolved_base_url = base_url.rstrip("/") if base_url else None
        if not resolved_base_url:
            endpoint = getattr(getattr(self.client, "meta", None), "endpoint_url", "")
            endpoint = (endpoint or "").rstrip("/")
            if endpoint:
                resolved_base_url = f"{endpoint}/{bucket}"
            else:
                resolved_base_url = f"https://{bucket}.s3.amazonaws.com"
        self.base_url = resolved_base_url
        self._base_url_parsed = urlparse(self.base_url)

    def _normalize_key(self, relative_path: str) -> str:
        cleaned = relative_path.strip().strip("/")
        if not cleaned:
            raise ValueError("Relative path must not be empty")
        candidate = Path(cleaned)
        if candidate.is_absolute() or any(part == ".." for part in candidate.parts):
            raise ValueError("Relative path must not escape bucket prefix")
        return candidate.as_posix()

    async def save_file(
        self, relative_path: str, data: bytes, *, content_type: str | None = None, cache_control: str | None = None
    ) -> str:
        key = self._normalize_key(relative_path)
        await asyncio.to_thread(self._put_object, key, data, content_type, cache_control)
        return f"{self.base_url}/{key}"

    def _put_object(self, key: str, data: bytes, content_type: str | None, cache_control: str | None = None) -> None:
        args = {
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
            self.client.put_object(**args)
        except Exception:  # pragma: no cover - depends on boto3 internals
            logger.exception("Failed to upload %s to bucket %s", key, self.bucket)
            raise

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
        await asyncio.to_thread(self._delete_object, key)

    def _delete_object(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except Exception:  # pragma: no cover - depends on boto3 internals
            logger.warning(
                "Failed to delete %s from bucket %s", key, self.bucket, exc_info=True
            )


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
            access_key_id=getattr(settings, "storage_s3_access_key_id", None) or None,
            secret_access_key=getattr(settings, "storage_s3_secret_access_key", None)
            or None,
            endpoint_url=getattr(settings, "storage_s3_endpoint_url", None) or None,
            base_url=getattr(settings, "storage_s3_base_url", None) or None,
        )
    raise ValueError(f"Unsupported storage backend: {settings.storage_backend}")
