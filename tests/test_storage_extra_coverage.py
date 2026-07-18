"""Extra unit tests to close remaining coverage gaps in storage module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from app.services.storage import S3Storage, StaticFSStorage

# ── 1. StaticFSStorage Edge Cases ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_static_fs_storage_invalid_chars(tmp_path):
    storage = StaticFSStorage(base_dir=tmp_path)
    with pytest.raises(ValueError, match="invalid characters"):
        storage._normalize_relative_path("file\x00name.txt")
    with pytest.raises(ValueError, match="invalid characters"):
        storage._normalize_relative_path("file\\name.txt")


@pytest.mark.asyncio
async def test_static_fs_storage_absolute_path(tmp_path):
    storage = StaticFSStorage(base_dir=tmp_path)
    import os

    path_str = "C:/absolute/path.txt" if os.name == "nt" else "/absolute/path.txt"
    with pytest.raises(ValueError, match="absolute"):
        storage._normalize_relative_path(path_str)


@pytest.mark.asyncio
async def test_static_fs_storage_resolve_error(tmp_path):
    storage = StaticFSStorage(base_dir=tmp_path)
    with patch.object(Path, "resolve", side_effect=OSError("Resolution failed")):
        with pytest.raises(ValueError, match="Cannot resolve path"):
            storage._resolve_validated_path(Path("somefile.txt"))


@pytest.mark.asyncio
async def test_static_fs_storage_escape_dir(tmp_path):
    storage = StaticFSStorage(base_dir=tmp_path)
    # Target path that resolves outside base directory
    with pytest.raises(ValueError, match="escapes base directory"):
        storage._resolve_validated_path(Path("../outside.txt"))


@pytest.mark.asyncio
async def test_static_fs_storage_symlink_detection(tmp_path):
    storage = StaticFSStorage(base_dir=tmp_path)
    with patch.object(Path, "is_symlink", return_value=True):
        with patch.object(Path, "exists", return_value=True):
            with pytest.raises(ValueError, match="Symlink detected"):
                storage._resolve_validated_path(Path("somefile.txt"))


@pytest.mark.asyncio
async def test_static_fs_storage_extract_relative_path_empty(tmp_path):
    storage = StaticFSStorage(base_dir=tmp_path, base_url="/static")
    assert storage._extract_relative_path("/static") is None
    assert storage._extract_relative_path("/static/") is None
    assert storage._extract_relative_path("/static/../escape.txt") is None


@pytest.mark.asyncio
async def test_static_fs_storage_unlink_error(tmp_path):
    storage = StaticFSStorage(base_dir=tmp_path)
    with patch.object(Path, "unlink", side_effect=OSError("Permission denied")):
        # Should swallow OSError and log warning without crashing
        storage._unlink_ignore_missing(Path("somefile.txt"))


@pytest.mark.asyncio
async def test_static_fs_storage_delete_empty(tmp_path):
    storage = StaticFSStorage(base_dir=tmp_path)
    # Should return early
    await storage.delete_file("")


@pytest.mark.asyncio
async def test_static_fs_storage_exists_and_read_raw_paths(tmp_path):
    storage = StaticFSStorage(base_dir=tmp_path)
    assert await storage.exists("check.txt") is False

    with pytest.raises(FileNotFoundError):
        await storage.read_file("check.txt")

    # Cover lines 153 and 161 fallbacks
    with pytest.raises(ValueError):
        await storage.exists("/static/..")
    with pytest.raises(ValueError):
        await storage.read_file("/static/..")


# ── 2. S3Storage Edge Cases ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_s3_storage_save_file_connection_error():
    mock_client = AsyncMock()
    mock_client.put_object = AsyncMock(side_effect=ConnectionError("Lost connection"))
    s3 = S3Storage(bucket="test", client=mock_client)
    with pytest.raises(ConnectionError):
        await s3.save_file("fail.txt", b"data")


@pytest.mark.asyncio
async def test_s3_storage_build_client_production():
    with patch("aioboto3.Session") as mock_session_cls:
        mock_session = MagicMock()
        mock_client = AsyncMock()
        mock_session.client.return_value.__aenter__.return_value = mock_client
        mock_session_cls.return_value = mock_session

        s3 = S3Storage(bucket="test-bucket")
        async with s3._build_aioboto3_client() as client:
            assert client is mock_client


@pytest.mark.asyncio
async def test_s3_storage_extract_key_edge_cases():
    s3 = S3Storage(bucket="test-bucket")
    assert s3._extract_key("") is None
    assert s3._extract_key("   ") is None
    assert s3._extract_key("https://wrong-bucket.s3.amazonaws.com/file.txt") is None
    assert s3._extract_key("s3://wrong-bucket/file.txt") is None

    # Valid s3 url
    assert s3._extract_key("s3://test-bucket/path/file.txt") == "path/file.txt"
    # Raw key fallback
    assert s3._extract_key("/raw/path/file.txt") == "raw/path/file.txt"


@pytest.mark.asyncio
async def test_s3_storage_delete_empty_key():
    s3 = S3Storage(bucket="test")
    # Should return early
    await s3.delete_file("")


@pytest.mark.asyncio
async def test_s3_storage_delete_file_error():
    mock_client = AsyncMock()
    mock_client.delete_object = AsyncMock(side_effect=OSError("Deletion failed"))
    s3 = S3Storage(bucket="test", client=mock_client)
    # Deletion failures are caught and logged, not raised
    await s3.delete_file("https://test.s3.amazonaws.com/key.txt")


@pytest.mark.asyncio
async def test_s3_storage_exists_empty_key():
    mock_client = AsyncMock()
    mock_client.head_object = AsyncMock()
    s3 = S3Storage(bucket="test", client=mock_client)
    assert await s3.exists("") is True


@pytest.mark.asyncio
async def test_s3_storage_exists_error_propagation():
    mock_client = AsyncMock()
    mock_client.head_object = AsyncMock(side_effect=ValueError("Some connection error"))
    s3 = S3Storage(bucket="test", client=mock_client)
    with pytest.raises(ValueError):
        await s3.exists("key.txt")


@pytest.mark.asyncio
async def test_s3_storage_read_file_empty_key():
    mock_client = AsyncMock()
    mock_client.get_object = AsyncMock(return_value={})
    s3 = S3Storage(bucket="test", client=mock_client)
    with pytest.raises(KeyError):
        await s3.read_file("")


@pytest.mark.asyncio
async def test_s3_storage_read_file_no_body():
    mock_client = AsyncMock()
    mock_client.get_object = AsyncMock(return_value={})  # Missing "Body"
    s3 = S3Storage(bucket="test", client=mock_client)
    with pytest.raises(KeyError):
        await s3.read_file("key.txt")


@pytest.mark.asyncio
async def test_s3_storage_read_file_error():
    mock_client = AsyncMock()
    mock_client.get_object = AsyncMock(side_effect=TimeoutError("Timeout"))
    s3 = S3Storage(bucket="test", client=mock_client)
    # TimeoutError (subclass of OSError) is caught and raised as FileNotFoundError
    with pytest.raises(FileNotFoundError):
        await s3.read_file("key.txt")


@pytest.mark.asyncio
async def test_s3_storage_exists_client_error_not_found():
    mock_client = AsyncMock()
    mock_client.head_object = AsyncMock(
        side_effect=ClientError({"Error": {"Code": "403"}}, "HeadObject")
    )
    s3 = S3Storage(bucket="test", client=mock_client)
    with pytest.raises(ClientError):
        await s3.exists("key.txt")
