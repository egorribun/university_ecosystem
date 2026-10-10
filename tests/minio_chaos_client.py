"""MinIO object storage service client.

This module provides an async-friendly wrapper around the MinIO Python SDK
for storing and retrieving files from S3-compatible object storage.

Features:
- Presigned URL generation for secure uploads/downloads
- Bucket management
- Async-compatible operations via thread pool
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from functools import partial
from typing import TYPE_CHECKING

from minio import Minio  # type: ignore[import-not-found]  # no stubs
from minio.error import S3Error  # type: ignore[import-not-found]

from app.core.logging import get_logger

if TYPE_CHECKING:
    from io import BytesIO

logger = get_logger(__name__)

# Thread pool for blocking MinIO operations
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="minio")


class MinIOClient:
    """Async-compatible MinIO client wrapper."""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        secure: bool = False,
        default_bucket: str = "uploads",
    ) -> None:
        self._client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        self._default_bucket = default_bucket
        self._initialized = False

    async def initialize(self) -> None:
        """Ensure default bucket exists."""
        if self._initialized:
            return

        import asyncio

        loop = asyncio.get_running_loop()  # MED-W19
        try:
            exists = await loop.run_in_executor(
                _executor,
                self._client.bucket_exists,
                self._default_bucket,
            )
            if not exists:
                await loop.run_in_executor(
                    _executor,
                    self._client.make_bucket,
                    self._default_bucket,
                )
                logger.info("Created bucket: %s", self._default_bucket)
            self._initialized = True
        except S3Error as exc:
            logger.error("Failed to initialize MinIO: %s", exc)
            raise

    async def upload_file(
        self,
        object_name: str,
        data: BytesIO,
        content_type: str = "application/octet-stream",
        bucket: str | None = None,
    ) -> str:
        """Upload a file to object storage.

        Args:
            object_name: Name/path of the object in storage
            data: File data as BytesIO
            content_type: MIME type of the file
            bucket: Optional bucket name (uses default if not specified)

        Returns:
            Object name in storage
        """
        import asyncio

        bucket = bucket or self._default_bucket
        loop = asyncio.get_running_loop()  # MED-W19

        data.seek(0)
        size = data.getbuffer().nbytes

        await loop.run_in_executor(
            _executor,
            partial(
                self._client.put_object,
                bucket,
                object_name,
                data,
                size,
                content_type=content_type,
            ),
        )

        logger.debug("Uploaded %s to bucket %s", object_name, bucket)
        return object_name

    async def get_presigned_url(
        self,
        object_name: str,
        bucket: str | None = None,
        expires: timedelta = timedelta(hours=1),
    ) -> str:
        """Generate a presigned URL for downloading an object.

        Args:
            object_name: Name/path of the object
            bucket: Optional bucket name
            expires: URL expiration time

        Returns:
            Presigned URL string
        """
        import asyncio

        bucket = bucket or self._default_bucket
        loop = asyncio.get_running_loop()  # MED-W19

        url = await loop.run_in_executor(
            _executor,
            partial(
                self._client.presigned_get_object,
                bucket,
                object_name,
                expires=expires,
            ),
        )

        return url  # type: ignore[no-any-return]  # minio untyped

    async def get_presigned_upload_url(
        self,
        object_name: str,
        bucket: str | None = None,
        expires: timedelta = timedelta(hours=1),
    ) -> str:
        """Generate a presigned URL for uploading an object.

        Args:
            object_name: Name/path for the new object
            bucket: Optional bucket name
            expires: URL expiration time

        Returns:
            Presigned upload URL string
        """
        import asyncio

        bucket = bucket or self._default_bucket
        loop = asyncio.get_running_loop()  # MED-W19

        url = await loop.run_in_executor(
            _executor,
            partial(
                self._client.presigned_put_object,
                bucket,
                object_name,
                expires=expires,
            ),
        )

        return url  # type: ignore[no-any-return]  # minio untyped

    async def delete_object(
        self,
        object_name: str,
        bucket: str | None = None,
    ) -> None:
        """Delete an object from storage.

        Args:
            object_name: Name/path of the object to delete
            bucket: Optional bucket name
        """
        import asyncio

        bucket = bucket or self._default_bucket
        loop = asyncio.get_running_loop()  # MED-W19

        await loop.run_in_executor(
            _executor,
            partial(self._client.remove_object, bucket, object_name),
        )

        logger.debug("Deleted %s from bucket %s", object_name, bucket)


# Singleton instance (configure via settings)
_minio_client: MinIOClient | None = None
_minio_client_lock = threading.Lock()  # RZ-33-29: DCL per RZ-30-01


def get_minio_client() -> MinIOClient:
    """Get the configured MinIO client instance."""
    global _minio_client
    if _minio_client is not None:  # RZ-33-29: fast path — no lock after init
        return _minio_client
    with _minio_client_lock:  # RZ-33-29: slow path — double-checked locking
        if _minio_client is None:
            from app.core.config import settings

            access_key = getattr(settings, "minio_access_key", "minioadmin")
            secret_key = getattr(settings, "minio_secret_key", "minioadmin")

            # LOW-W19: warn when default MinIO credentials are in use.  The
            # factory-default "minioadmin"/"minioadmin" credentials are publicly
            # known and MUST be rotated before deploying to any non-development
            # environment.  An attacker with network access to the MinIO endpoint
            # can gain full bucket access if these defaults remain unchanged.
            _DEFAULT_CRED = "minioadmin"
            if access_key == _DEFAULT_CRED or secret_key == _DEFAULT_CRED:
                logger.warning(
                    "MinIO factory defaults are active; override both access "
                    "settings before staging or production"
                )

            _minio_client = MinIOClient(
                endpoint=getattr(settings, "minio_endpoint", "minio:9000"),
                access_key=access_key,
                secret_key=secret_key,
                secure=getattr(settings, "minio_secure", False),
                default_bucket=getattr(settings, "minio_bucket", "uploads"),
            )
        return _minio_client


__all__ = ["MinIOClient", "get_minio_client"]
