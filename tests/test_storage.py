"""Tests for storage backend services.

Coverage targets:
- StaticFSStorage: save, delete, path normalization, relative path extraction
- S3Storage: save, delete, key normalization, key extraction (async aioboto3 mock)
- get_storage_backend: factory logic
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

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


@pytest.mark.asyncio
async def test_static_fs_save_file(static_storage, tmp_path):
    """Test saving a file to local filesystem."""
    data = b"hello world"
    rel_path = "avatars/user.txt"
    url = await static_storage.save_file(rel_path, data)

    assert url == "/static/avatars/user.txt"
    full_path = tmp_path / "avatars/user.txt"
    assert full_path.exists()
    assert full_path.read_bytes() == data


@pytest.mark.asyncio
async def test_static_fs_delete_file(static_storage, tmp_path):
    """Test deleting a file from local filesystem."""
    full_path = tmp_path / "avatars/test.jpg"
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(b"data")

    await static_storage.delete_file("/static/avatars/test.jpg")
    assert not full_path.exists()


@pytest.mark.asyncio
async def test_static_fs_delete_non_existent(static_storage):
    """Test deleting non-existent file doesn't crash."""
    await static_storage.delete_file("/static/missing.jpg")
    # No exception


def test_static_fs_extract_path(static_storage):
    """Test extracting relative path from URL."""
    # Prefix match
    assert static_storage._extract_relative_path("/static/a/b.txt") == Path("a/b.txt")

    # Implementation doesn't handle schema-based URL extraction for
    # StaticFS (simple string slicing)
    # So we test what it DOES support
    assert static_storage._extract_relative_path("/static/a.jpg") == Path("a.jpg")

    # If prefix doesn't match, it still returns the Path as long as
    # it's not absolute or escaping
    assert static_storage._extract_relative_path("/other/path.txt") == Path(
        "other/path.txt"
    )
    assert static_storage._extract_relative_path("") is None


# ============================================================
# S3Storage tests
# ============================================================


@pytest.fixture
def mock_s3_client():
    """Async mock matching aioboto3's async client interface."""
    client = AsyncMock()
    client.put_object = AsyncMock(return_value={})
    client.delete_object = AsyncMock(return_value={})
    return client


@pytest.fixture
def s3_storage(mock_s3_client):
    """S3Storage injected with an async mock client.

    PERF-7 (audit 2026-03-05): S3Storage._build_aioboto3_client() returns an
    async context manager when self._injected_client is set, so we pass it here.
    """
    return S3Storage(
        bucket="test-bucket", client=mock_s3_client, base_url="https://cdn.example.com"
    )


@pytest.mark.asyncio
async def test_s3_save_file_success(s3_storage, mock_s3_client):
    """Test saving a file to S3 via async aioboto3 client."""
    data = b"s3 data"
    url = await s3_storage.save_file(
        "docs/file.pdf", data, content_type="application/pdf"
    )

    assert url == "https://cdn.example.com/docs/file.pdf"
    mock_s3_client.put_object.assert_called_once()


@pytest.mark.asyncio
async def test_s3_delete_file(s3_storage, mock_s3_client):
    """Test deleting a file from S3 via async aioboto3 client."""
    await s3_storage.delete_file("https://cdn.example.com/images/old.png")
    mock_s3_client.delete_object.assert_called_once_with(
        Bucket="test-bucket", Key="images/old.png"
    )


def test_s3_extract_key(s3_storage):
    """Test extracting key from S3 URL."""
    assert s3_storage._extract_key("https://cdn.example.com/my-key") == "my-key"
    assert s3_storage._extract_key("/my-key") is None
    assert (
        s3_storage._extract_key("s3://test-bucket/direct/key.jpg") == "direct/key.jpg"
    )
    assert s3_storage._extract_key("s3://other-bucket/key.jpg") is None


@pytest.mark.parametrize(
    "file_url",
    [
        "http://cdn.example.com:8443/uploads/image.png",
        "https://cdn.example.com:443/uploads/image.png",
        "https://evil.example.com:8443/uploads/image.png",
        "https://cdn.example.com:8443/uploads-extra/image.png",
        "https://cdn.example.com:8443/other/image.png",
        "https://cdn.example.com:8443/uploads",
        "//evil.example.com/uploads/image.png",
        "ftp://cdn.example.com:8443/uploads/image.png",
    ],
)
def test_s3_rejects_urls_outside_exact_public_origin_and_base_path(file_url):
    storage = S3Storage(
        bucket="uploads", base_url="https://cdn.example.com:8443/uploads"
    )

    assert storage._extract_key(file_url) is None


def test_s3_extract_key_preserves_valid_canonical_urls_and_raw_keys():
    storage = S3Storage(
        bucket="uploads", base_url="https://cdn.example.com:8443/uploads"
    )

    assert (
        storage._extract_key("https://cdn.example.com:8443/uploads/a/b.png")
        == "a/b.png"
    )
    assert storage._extract_key("a/b.png") == "a/b.png"
    assert storage._extract_key("/a/b.png") is None
    assert storage._extract_key("s3://uploads/a/b.png") == "a/b.png"


@pytest.mark.asyncio
async def test_s3_saved_url_round_trips_to_exact_written_key(mock_s3_client):
    storage = S3Storage(
        bucket="uploads",
        client=mock_s3_client,
        base_url="https://cdn.example.com:8443/uploads",
    )

    url = await storage.save_file("a/b.png", b"image")

    assert url == "https://cdn.example.com:8443/uploads/a/b.png"
    assert storage._extract_key(url) == "a/b.png"
    mock_s3_client.put_object.assert_awaited_once_with(
        Bucket="uploads", Key="a/b.png", Body=b"image"
    )


@pytest.mark.parametrize("relative_path", ["a?b", "a#b", "a;b", "a/%41.png"])
def test_s3_save_key_rejects_unencoded_url_delimiters(relative_path):
    storage = S3Storage(bucket="uploads")

    with pytest.raises(ValueError):
        storage._normalize_key(relative_path)


@pytest.mark.parametrize("relative_path", ["\tsecret.png", "secret.png\n"])
def test_s3_save_key_rejects_control_characters_before_whitespace_trimming(
    relative_path,
):
    storage = S3Storage(bucket="uploads")

    with pytest.raises(ValueError):
        storage._normalize_key(relative_path)


@pytest.mark.parametrize(
    "relative_path", [" foo", "foo ", "/foo", "foo/", "//foo", "a//b"]
)
def test_s3_save_key_rejects_noncanonical_slashes_and_outer_spaces(relative_path):
    storage = S3Storage(bucket="uploads")

    with pytest.raises(ValueError):
        storage._normalize_key(relative_path)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "file_url",
    [
        "",
        "   ",
        "https://cdn.example.com:8443/uploads",
        "https://cdn.example.com:8443/uploads-other/secret.png",
        "https://elsewhere.example.com:8443/uploads/secret.png",
        "s3://other-bucket/secret.png",
    ],
)
async def test_s3_rejected_urls_never_reach_head_or_get_object(file_url):
    client = AsyncMock()
    storage = S3Storage(
        bucket="uploads", client=client, base_url="https://cdn.example.com:8443/uploads"
    )

    assert await storage.exists(file_url) is False
    with pytest.raises(FileNotFoundError):
        await storage.read_file(file_url)

    client.head_object.assert_not_awaited()
    client.get_object.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "file_url", ["/storage/uploads/avatars/user.png", "/avatars/user.png"]
)
async def test_s3_relative_base_rejects_legacy_or_bare_slash_prefixed_urls(file_url):
    client = AsyncMock()
    storage = S3Storage(bucket="uploads", client=client, base_url="/api/v1/img")

    assert storage._extract_key(file_url) is None
    assert await storage.exists(file_url) is False
    with pytest.raises(FileNotFoundError):
        await storage.read_file(file_url)
    await storage.delete_file(file_url)

    client.head_object.assert_not_awaited()
    client.get_object.assert_not_awaited()
    client.delete_object.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "file_url",
    [
        "a/../secret.png",
        "a/./secret.png",
        "a//secret.png",
        r"a\secret.png",
        "a/\x00secret.png",
        "a/\nsecret.png",
        "a/\tsecret.png",
        "\tsecret.png",
        "secret.png\n",
        "a/%2e%2e/secret.png",
        "a/%252e%252e/secret.png",
        "a/%2fsecret.png",
        "a/%252fsecret.png",
        "a/%5csecret.png",
        "a/%00secret.png",
        "a/%ffsecret.png",
        "a/%41.png",
        " secret.png",
        "secret.png ",
        "///secret.png",
        "////secret.png",
        "secret.png?another-key=1",
        "secret.png#another-key",
        "secret.png;another-key",
        "s3://uploads/secret.png?another-key=1",
        "s3://uploads//secret.png",
        "s3://uploads/a/../secret.png",
        "https://cdn.example.com:8443/uploads//secret.png",
        "https://cdn.example.com:8443/uploads/secret.png?w=400",
        "https://cdn.example.com:8443/uploads/a//secret.png",
        "https://cdn.example.com:8443/uploads/a/%2e%2e/secret.png",
    ],
)
async def test_s3_noncanonical_keys_cannot_reach_object_operations(file_url):
    client = AsyncMock()
    storage = S3Storage(
        bucket="uploads", client=client, base_url="https://cdn.example.com:8443/uploads"
    )

    assert storage._extract_key(file_url) is None
    assert await storage.exists(file_url) is False
    with pytest.raises(FileNotFoundError):
        await storage.read_file(file_url)
    await storage.delete_file(file_url)

    client.head_object.assert_not_awaited()
    client.get_object.assert_not_awaited()
    client.delete_object.assert_not_awaited()


def test_s3_root_public_url_rejects_repeated_path_delimiter():
    storage = S3Storage(bucket="uploads", base_url="https://cdn.example.com:8443")

    assert storage._extract_key("https://cdn.example.com:8443//secret.png") is None


@pytest.mark.asyncio
async def test_s3_relative_image_proxy_url_round_trips_to_original_key(
    mock_s3_client,
):
    storage = S3Storage(bucket="uploads", client=mock_s3_client, base_url="/api/v1/img")

    url = await storage.save_file("avatars/user.png", b"image")

    assert url == "/api/v1/img/avatars/user.png"
    assert storage._extract_key("/api/v1/img") is None
    assert storage._extract_key(f"{url}?w=400") is None
    await storage.delete_file(url)
    mock_s3_client.delete_object.assert_awaited_once_with(
        Bucket="uploads", Key="avatars/user.png"
    )


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


def test_get_storage_backend_s3():
    """Test factory returns S3Storage when configured.

    PERF-7 note: aioboto3 Session is lazy — no network call at construction
    time, so no patch needed. The session is only used inside async with.
    """
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
