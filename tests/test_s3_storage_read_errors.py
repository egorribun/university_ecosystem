"""S3 reads distinguish missing objects from permission and service failures."""

from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, call

import pytest
from botocore.exceptions import ClientError

from app.services.storage import S3Storage, StaticFSStorage


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["NoSuchKey", "404"])
async def test_read_file_maps_only_missing_object_to_not_found(code: str) -> None:
    client = AsyncMock()
    client.get_object.side_effect = ClientError(
        {"Error": {"Code": code, "Message": "Object not found"}}, "GetObject"
    )
    storage = S3Storage(bucket="uploads", base_url="/api/v1/img", client=client)

    with pytest.raises(FileNotFoundError, match="S3 file not found"):
        await storage.read_file("/api/v1/img/avatars/missing.png")

    client.get_object.assert_awaited_once_with(
        Bucket="uploads", Key="avatars/missing.png"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["AccessDenied", "InternalError"])
async def test_read_file_preserves_non_missing_s3_errors(code: str) -> None:
    client = AsyncMock()
    error = ClientError(
        {"Error": {"Code": code, "Message": "Service error"}}, "GetObject"
    )
    client.get_object.side_effect = error
    storage = S3Storage(bucket="uploads", base_url="/api/v1/img", client=client)

    with pytest.raises(ClientError) as exc_info:
        await storage.read_file("avatars/image.png")

    assert exc_info.value is error


@pytest.mark.asyncio
async def test_read_failure_log_does_not_expose_private_object_key(caplog) -> None:
    client = AsyncMock()
    client.get_object.side_effect = OSError("credential=private-access-token")
    storage = S3Storage(bucket="uploads", base_url="/api/v1/img", client=client)

    with pytest.raises(FileNotFoundError):
        await storage.read_file("/api/v1/img/private-user@example.edu/secret.pdf")

    assert "private-user@example.edu" not in caplog.text
    assert "private-access-token" not in caplog.text


@pytest.mark.asyncio
async def test_s3_bounded_read_requests_only_limit_plus_one() -> None:
    stream = AsyncMock()
    stream.read.return_value = b"123456"

    @asynccontextmanager
    async def body():
        yield stream

    client = AsyncMock()
    client.get_object.return_value = {"Body": body()}
    storage = S3Storage(bucket="uploads", base_url="/api/v1/img", client=client)

    assert await storage.read_file("/api/v1/img/file.bin", max_bytes=5) == b"123456"
    stream.read.assert_awaited_once_with(6)


@pytest.mark.asyncio
async def test_s3_bounded_read_collects_fragmented_stream_to_limit() -> None:
    stream = AsyncMock()
    stream.read.side_effect = [b"ab", b"cd", b"e", b""]

    @asynccontextmanager
    async def body():
        yield stream

    client = AsyncMock()
    client.get_object.return_value = {"Body": body()}
    storage = S3Storage(bucket="uploads", base_url="/api/v1/img", client=client)

    assert await storage.read_file("/api/v1/img/file.bin", max_bytes=5) == b"abcde"
    assert stream.read.await_args_list == [call(6), call(4), call(2), call(1)]


@pytest.mark.asyncio
async def test_s3_bounded_read_caps_oversized_stream_chunk() -> None:
    stream = AsyncMock()
    stream.read.return_value = b"abcdefghi"

    @asynccontextmanager
    async def body():
        yield stream

    client = AsyncMock()
    client.get_object.return_value = {"Body": body()}
    storage = S3Storage(bucket="uploads", base_url="/api/v1/img", client=client)

    assert await storage.read_file("/api/v1/img/file.bin", max_bytes=5) == b"abcdef"
    stream.read.assert_awaited_once_with(6)


@pytest.mark.asyncio
async def test_s3_bounded_read_rejects_negative_limit() -> None:
    storage = S3Storage(bucket="uploads", base_url="/api/v1/img", client=AsyncMock())

    with pytest.raises(ValueError, match="max_bytes"):
        await storage.read_file("/api/v1/img/file.bin", max_bytes=-1)


@pytest.mark.asyncio
async def test_static_bounded_read_never_loads_entire_file(tmp_path: Path) -> None:
    storage = StaticFSStorage(tmp_path, base_url="/static")
    url = await storage.save_file("private/file.bin", b"0123456789")

    assert await storage.read_file(url, max_bytes=3) == b"0123"
    assert await storage.read_file(url) == b"0123456789"

    with pytest.raises(ValueError, match="max_bytes"):
        await storage.read_file(url, max_bytes=-1)
