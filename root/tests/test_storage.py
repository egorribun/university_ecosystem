"""Tests for storage backend services.

Coverage targets:
- StaticFSStorage: save, delete, path normalization, relative path extraction
- S3Storage: save, delete, key normalization, key extraction (mocked)
- get_storage_backend: factory logic
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.storage import (
    S3Storage,
    StaticFSStorage,
    get_storage_backend,
)


@pytest.fixture
def static_storage(tmp_path):
    """Create StaticFSStorage with tmp_path."""
    return StaticFSStorage(base_dir=tmp_path, base_url="/static")


# ============================================================
# StaticFSStorage tests
# ============================================================


@pytest.mark.anyio
async def test_static_fs_save_file(static_storage, tmp_path):
    """Test saving a file to local filesystem."""
    data = b"hello world"
    rel_path = "avatars/user.txt"
    url = await static_storage.save_file(rel_path, data)

    assert url == "/static/avatars/user.txt"
    full_path = tmp_path / "avatars/user.txt"
    assert full_path.exists()
    assert full_path.read_bytes() == data


@pytest.mark.anyio
async def test_static_fs_delete_file(static_storage, tmp_path):
    """Test deleting a file from local filesystem."""
    full_path = tmp_path / "avatars/test.jpg"
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(b"data")

    await static_storage.delete_file("/static/avatars/test.jpg")
    assert not full_path.exists()


@pytest.mark.anyio
async def test_static_fs_delete_non_existent(static_storage):
    """Test deleting non-existent file doesn't crash."""
    await static_storage.delete_file("/static/missing.jpg")
    # No exception


def test_static_fs_extract_path(static_storage):
    """Test extracting relative path from URL."""
    # Prefix match
    assert static_storage._extract_relative_path("/static/a/b.txt") == Path("a/b.txt")

    # Implementation doesn't handle schema-based URL extraction for StaticFS (simple string slicing)
    # So we test what it DOES support
    assert static_storage._extract_relative_path("/static/a.jpg") == Path("a.jpg")

    # If prefix doesn't match, it still returns the Path as long as it's not absolute or escaping
    assert static_storage._extract_relative_path("/other/path.txt") == Path(
        "other/path.txt"
    )
    assert static_storage._extract_relative_path("") is None


# ============================================================
# S3Storage tests
# ============================================================


@pytest.fixture
def mock_s3_client():
    """Create mock S3 client."""
    client = MagicMock()
    # Mock boto3 internals for base_url resolution fallback if needed
    client.meta.endpoint_url = "https://s3.amazonaws.com"
    return client


@pytest.fixture
def s3_storage(mock_s3_client):
    """Create S3Storage with mock client."""
    return S3Storage(
        bucket="test-bucket", client=mock_s3_client, base_url="https://cdn.example.com"
    )


@pytest.mark.anyio
async def test_s3_save_file_success(s3_storage, mock_s3_client):
    """Test saving a file to S3."""
    data = b"s3 data"
    url = await s3_storage.save_file(
        "docs/file.pdf", data, content_type="application/pdf"
    )

    assert url == "https://cdn.example.com/docs/file.pdf"
    mock_s3_client.put_object.assert_called_once()


@pytest.mark.anyio
async def test_s3_delete_file(s3_storage, mock_s3_client):
    """Test deleting a file from S3."""
    await s3_storage.delete_file("https://cdn.example.com/images/old.png")
    mock_s3_client.delete_object.assert_called_once_with(
        Bucket="test-bucket", Key="images/old.png"
    )


def test_s3_extract_key(s3_storage):
    """Test extracting key from S3 URL."""
    assert s3_storage._extract_key("https://cdn.example.com/my-key") == "my-key"
    assert s3_storage._extract_key("/my-key") == "my-key"
    assert (
        s3_storage._extract_key("s3://test-bucket/direct/key.jpg") == "direct/key.jpg"
    )
    assert s3_storage._extract_key("s3://other-bucket/key.jpg") is None


# ============================================================
# get_storage_backend tests
# ============================================================


def test_get_storage_backend_static(tmp_path):
    """Test factory returns StaticFSStorage by default or when configured."""
    mock_settings = MagicMock()
    mock_settings.storage_backend = "static"
    mock_settings.static_dir_path = tmp_path
    mock_settings.storage_static_base_url = "/static"

    backend = get_storage_backend(mock_settings)
    assert isinstance(backend, StaticFSStorage)
    assert backend.base_url == "/static"


@patch("boto3.client")
def test_get_storage_backend_s3(mock_boto_client):
    """Test factory returns S3Storage when configured."""
    mock_settings = MagicMock()
    mock_settings.storage_backend = "s3"
    mock_settings.storage_s3_bucket = "bucket"
    mock_settings.storage_s3_region = "us-east-1"
    mock_settings.storage_s3_access_key_id = "key"
    mock_settings.storage_s3_secret_access_key = "secret"
    mock_settings.storage_s3_endpoint_url = "http://minio:9000"
    mock_settings.storage_s3_base_url = "https://cdn"

    backend = get_storage_backend(mock_settings)
    assert isinstance(backend, S3Storage)
    assert backend.bucket == "bucket"
    assert backend.base_url == "https://cdn"
