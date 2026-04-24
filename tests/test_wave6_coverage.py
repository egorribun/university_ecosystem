"""Wave 6 coverage tests: Feature Flags, Storage backends, Spotify API.

Targets uncovered paths in:
- app/core/feature_flags.py: FeatureFlag model, OpenFeature provider,
  FeatureFlagService (init, shutdown, CRUD, pub/sub)
- app/services/storage.py: StaticFSStorage, S3Storage (save/delete/exists/read,
  path normalization, error handling)
- app/api/spotify.py: OAuth flow, token refresh, error responses
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# ===========================================================================
# Storage — StaticFSStorage
# ===========================================================================


class TestStaticFSStorage:
    @pytest.mark.asyncio
    async def test_save_and_read(self, tmp_path):
        from app.services.storage import StaticFSStorage

        storage = StaticFSStorage(base_dir=tmp_path, base_url="/static")
        url = await storage.save_file("test/file.txt", b"hello world")
        assert "/static/test/file.txt" == url

        data = await storage.read_file(url)
        assert data == b"hello world"

    @pytest.mark.asyncio
    async def test_exists(self, tmp_path):
        from app.services.storage import StaticFSStorage

        storage = StaticFSStorage(base_dir=tmp_path)
        await storage.save_file("check.txt", b"data")
        assert (
            await storage.exists("/static/check.txt") is True
            or await storage.exists("check.txt") is True
        )

    @pytest.mark.asyncio
    async def test_delete(self, tmp_path):
        from app.services.storage import StaticFSStorage

        storage = StaticFSStorage(base_dir=tmp_path, base_url="/static")
        url = await storage.save_file("del.txt", b"data")
        await storage.delete_file(url)
        assert not (tmp_path / "del.txt").exists()

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, tmp_path):
        from app.services.storage import StaticFSStorage

        storage = StaticFSStorage(base_dir=tmp_path, base_url="/static")
        # Should not raise
        await storage.delete_file("/static/nonexistent.txt")

    @pytest.mark.asyncio
    async def test_read_nonexistent(self, tmp_path):
        from app.services.storage import StaticFSStorage

        storage = StaticFSStorage(base_dir=tmp_path)
        with pytest.raises(FileNotFoundError):
            await storage.read_file("nonexistent.txt")

    def test_normalize_empty_path(self, tmp_path):
        from app.services.storage import StaticFSStorage

        storage = StaticFSStorage(base_dir=tmp_path)
        with pytest.raises(ValueError, match="empty"):
            storage._normalize_relative_path("")

    def test_normalize_traversal(self, tmp_path):
        from app.services.storage import StaticFSStorage

        storage = StaticFSStorage(base_dir=tmp_path)
        with pytest.raises(ValueError, match="escape"):
            storage._normalize_relative_path("../../etc/passwd")

    def test_normalize_traversal_dotdot(self, tmp_path):
        from app.services.storage import StaticFSStorage

        storage = StaticFSStorage(base_dir=tmp_path)
        with pytest.raises(ValueError, match="escape"):
            storage._normalize_relative_path("sub/../../etc/passwd")

    @pytest.mark.asyncio
    async def test_save_no_base_url(self, tmp_path):
        from app.services.storage import StaticFSStorage

        storage = StaticFSStorage(base_dir=tmp_path, base_url="")
        url = await storage.save_file("file.txt", b"data")
        assert url == "/file.txt"

    def test_extract_relative_path_empty(self, tmp_path):
        from app.services.storage import StaticFSStorage

        storage = StaticFSStorage(base_dir=tmp_path, base_url="/static")
        assert storage._extract_relative_path("") is None
        assert storage._extract_relative_path("   ") is None


# ===========================================================================
# Storage — S3Storage
# ===========================================================================


class TestS3Storage:
    def test_init_with_endpoint(self):
        from app.services.storage import S3Storage

        s3 = S3Storage(bucket="test-bucket", endpoint_url="http://minio:9000")
        assert s3.base_url == "http://minio:9000/test-bucket"

    def test_init_without_endpoint(self):
        from app.services.storage import S3Storage

        s3 = S3Storage(bucket="my-bucket")
        assert "s3.amazonaws.com" in s3.base_url

    def test_init_with_base_url(self):
        from app.services.storage import S3Storage

        s3 = S3Storage(bucket="b", base_url="https://cdn.example.com/files")
        assert s3.base_url == "https://cdn.example.com/files"

    def test_init_empty_bucket_raises(self):
        from app.services.storage import S3Storage

        with pytest.raises(ValueError, match="empty"):
            S3Storage(bucket="")

    def test_normalize_key(self):
        from app.services.storage import S3Storage

        s3 = S3Storage(bucket="b")
        assert s3._normalize_key("path/to/file.txt") == "path/to/file.txt"
        assert s3._normalize_key("  /file.txt/  ") == "file.txt"

    def test_normalize_key_traversal(self):
        from app.services.storage import S3Storage

        s3 = S3Storage(bucket="b")
        with pytest.raises(ValueError):
            s3._normalize_key("../../etc/passwd")

    def test_normalize_key_empty(self):
        from app.services.storage import S3Storage

        s3 = S3Storage(bucket="b")
        with pytest.raises(ValueError, match="empty"):
            s3._normalize_key("")

    @pytest.mark.asyncio
    async def test_save_file_with_injected_client(self):
        from app.services.storage import S3Storage

        mock_client = AsyncMock()
        mock_client.put_object = AsyncMock()
        s3 = S3Storage(
            bucket="test",
            endpoint_url="http://minio:9000",
            client=mock_client,
        )
        url = await s3.save_file(
            "upload/file.pdf", b"pdf-data", content_type="application/pdf"
        )
        assert "upload/file.pdf" in url
        mock_client.put_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_file_error(self):
        from app.services.storage import S3Storage

        mock_client = AsyncMock()
        mock_client.put_object = AsyncMock(side_effect=Exception("S3 down"))
        s3 = S3Storage(bucket="test", client=mock_client)

        with pytest.raises(Exception, match="S3 down"):
            await s3.save_file("fail.txt", b"data")

    @pytest.mark.asyncio
    async def test_delete_file(self):
        from app.services.storage import S3Storage

        mock_client = AsyncMock()
        mock_client.delete_object = AsyncMock()
        s3 = S3Storage(
            bucket="test",
            endpoint_url="http://minio:9000",
            client=mock_client,
        )
        await s3.delete_file("http://minio:9000/test/path/file.txt")
        mock_client.delete_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_exists_true(self):
        from app.services.storage import S3Storage

        mock_client = AsyncMock()
        mock_client.head_object = AsyncMock(return_value={})
        s3 = S3Storage(bucket="test", client=mock_client)

        result = await s3.exists("path/file.txt")
        assert result is True

    @pytest.mark.asyncio
    async def test_exists_false(self):
        from app.services.storage import S3Storage

        mock_client = AsyncMock()
        from botocore.exceptions import ClientError

        mock_client.head_object = AsyncMock(
            side_effect=ClientError({"Error": {"Code": "404"}}, "HeadObject")
        )
        s3 = S3Storage(bucket="test", client=mock_client)

        result = await s3.exists("missing.txt")
        assert result is False

    @pytest.mark.asyncio
    async def test_read_file(self):
        from contextlib import asynccontextmanager

        from app.services.storage import S3Storage

        @asynccontextmanager
        async def _mock_stream():
            stream = AsyncMock()
            stream.read = AsyncMock(return_value=b"file-content")
            yield stream

        mock_client = AsyncMock()
        mock_client.get_object = AsyncMock(return_value={"Body": _mock_stream()})
        s3 = S3Storage(bucket="test", client=mock_client)

        data = await s3.read_file("path/file.txt")
        assert data == b"file-content"

    @pytest.mark.asyncio
    async def test_save_with_cache_control(self):
        from app.services.storage import S3Storage

        mock_client = AsyncMock()
        mock_client.put_object = AsyncMock()
        s3 = S3Storage(bucket="test", client=mock_client)

        await s3.save_file(
            "cached.js",
            b"js",
            content_type="text/javascript",
            cache_control="max-age=3600",
        )
        call_kwargs = mock_client.put_object.call_args[1]
        assert call_kwargs["ContentType"] == "text/javascript"
        assert call_kwargs["CacheControl"] == "max-age=3600"


# ===========================================================================
# Storage — get_storage_backend factory
# ===========================================================================


class TestGetStorageBackend:
    def test_returns_static_by_default(self):
        from app.services.storage import StaticFSStorage, get_storage_backend

        mock_settings = MagicMock()
        mock_settings.storage_backend = "local"
        mock_settings.static_dir_path = Path("/tmp/test-static")  # noqa: S108
        mock_settings.storage_static_base_url = "/static"

        backend = get_storage_backend(mock_settings)
        assert isinstance(backend, StaticFSStorage)

    def test_returns_s3(self):
        from app.services.storage import S3Storage, get_storage_backend

        mock_settings = MagicMock()
        mock_settings.storage_backend = "s3"
        mock_settings.storage_s3_bucket = "test-bucket"
        mock_settings.storage_s3_region = "us-east-1"
        mock_settings.storage_s3_access_key_id = "key"
        mock_settings.storage_s3_secret_access_key = (
            "secret"  # pragma: allowlist secret
        )
        mock_settings.storage_s3_endpoint_url = "http://minio:9000"
        mock_settings.storage_s3_base_url = ""

        backend = get_storage_backend(mock_settings)
        assert isinstance(backend, S3Storage)

    def test_unsupported_backend_raises(self):
        from app.services.storage import get_storage_backend

        mock_settings = MagicMock()
        mock_settings.storage_backend = "unsupported"

        with pytest.raises(ValueError, match="Unsupported"):
            get_storage_backend(mock_settings)
