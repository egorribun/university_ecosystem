"""S3 reads distinguish missing objects from permission and service failures."""

from pathlib import Path
from unittest.mock import AsyncMock, call

import pytest
from aiobotocore.response import StreamingBody
from botocore.exceptions import ClientError, IncompleteReadError

from app.services.storage import S3Storage, StaticFSStorage


class _MockStreamingContent:
    def __init__(self, stream: AsyncMock) -> None:
        self.stream = stream

    async def read(self, size: int = -1) -> bytes:
        return await self.stream.read(size)


class _MockStreamingResponse:
    def __init__(self, stream: AsyncMock) -> None:
        self.content = _MockStreamingContent(stream)

    async def read(self) -> bytes:
        return await self.content.read(-1)

    async def __aenter__(self) -> _MockStreamingResponse:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


def _streaming_body(stream: AsyncMock, content_length: int) -> StreamingBody:
    return StreamingBody(_MockStreamingResponse(stream), str(content_length))


class _AiohttpContent:
    def __init__(self, payload: bytes, *, chunk_size: int | None = None) -> None:
        self.payload = payload
        self.offset = 0
        self.chunk_size = chunk_size
        self.read_sizes: list[int] = []

    async def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        if self.offset >= len(self.payload):
            return b""
        remaining = len(self.payload) - self.offset
        requested = remaining if size < 0 else min(size, remaining)
        if self.chunk_size is not None:
            requested = min(requested, self.chunk_size)
        chunk = self.payload[self.offset : self.offset + requested]
        self.offset += len(chunk)
        return chunk


class _AiohttpClientResponse:
    """Match aiohttp: read() consumes all content and accepts no size argument."""

    def __init__(self, payload: bytes, *, chunk_size: int | None = None) -> None:
        self.content = _AiohttpContent(payload, chunk_size=chunk_size)
        self.closed = False

    async def read(self) -> bytes:
        return await self.content.read(-1)

    async def __aenter__(self) -> _AiohttpClientResponse:
        return self

    async def __aexit__(self, *_: object) -> None:
        self.closed = True


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
    # Like a real body, a zero-byte read yields nothing.
    stream.read.side_effect = lambda size: b"123456" if size else b""

    client = AsyncMock()
    client.get_object.return_value = {"Body": _streaming_body(stream, 6)}
    storage = S3Storage(bucket="uploads", base_url="/api/v1/img", client=client)

    assert await storage.read_file("/api/v1/img/file.bin", max_bytes=5) == b"123456"
    stream.read.assert_awaited_once_with(6)


@pytest.mark.asyncio
async def test_s3_bounded_read_collects_fragmented_stream_to_limit() -> None:
    stream = AsyncMock()
    stream.read.side_effect = [b"ab", b"cd", b"e", b""]

    client = AsyncMock()
    client.get_object.return_value = {"Body": _streaming_body(stream, 5)}
    storage = S3Storage(bucket="uploads", base_url="/api/v1/img", client=client)

    assert await storage.read_file("/api/v1/img/file.bin", max_bytes=5) == b"abcde"
    assert stream.read.await_args_list == [call(6), call(4), call(2), call(1)]


@pytest.mark.asyncio
async def test_s3_bounded_read_caps_oversized_stream_chunk() -> None:
    stream = AsyncMock()
    # Like a real body, a zero-byte read yields nothing.
    stream.read.side_effect = lambda size: b"abcdefghi" if size else b""

    client = AsyncMock()
    client.get_object.return_value = {"Body": _streaming_body(stream, 9)}
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


@pytest.mark.asyncio
async def test_s3_real_streaming_body_uses_bounded_read_and_closes_response() -> None:
    response = _AiohttpClientResponse(b"abcdefghij", chunk_size=2)
    client = AsyncMock()
    client.get_object.return_value = {
        "Body": StreamingBody(response, str(len(response.content.payload)))
    }
    storage = S3Storage(bucket="uploads", base_url="/api/v1/img", client=client)

    actual = await storage.read_file("avatars/item.webp", max_bytes=5)

    assert actual == b"abcdef"
    assert response.content.read_sizes == [6, 4, 2]
    assert response.closed


@pytest.mark.asyncio
async def test_s3_real_streaming_body_keeps_unbounded_read_behavior() -> None:
    response = _AiohttpClientResponse(b"complete object")
    client = AsyncMock()
    client.get_object.return_value = {
        "Body": StreamingBody(response, str(len(response.content.payload)))
    }
    storage = S3Storage(bucket="uploads", base_url="/api/v1/img", client=client)

    actual = await storage.read_file("avatars/item.webp")

    assert actual == b"complete object"
    assert response.content.read_sizes == [-1]
    assert response.closed


@pytest.mark.asyncio
async def test_s3_real_streaming_body_rejects_truncated_object_and_closes_response() -> (
    None
):
    payload = b"truncated payload"
    response = _AiohttpClientResponse(payload)
    client = AsyncMock()
    client.get_object.return_value = {
        "Body": StreamingBody(response, str(len(payload) + 1))
    }
    storage = S3Storage(bucket="uploads", base_url="/api/v1/img", client=client)

    with pytest.raises(IncompleteReadError) as exc_info:
        await storage.read_file("avatars/item.webp")

    assert exc_info.value.kwargs == {
        "actual_bytes": len(payload),
        "expected_bytes": len(payload) + 1,
    }
    assert response.content.read_sizes == [-1]
    assert response.closed


@pytest.mark.asyncio
async def test_s3_real_streaming_body_zero_limit_reads_only_probe_byte() -> None:
    response = _AiohttpClientResponse(b"xmore")
    client = AsyncMock()
    client.get_object.return_value = {
        "Body": StreamingBody(response, str(len(response.content.payload)))
    }
    storage = S3Storage(bucket="uploads", base_url="/api/v1/img", client=client)

    actual = await storage.read_file("avatars/item.webp", max_bytes=0)

    assert actual == b"x"
    assert response.content.read_sizes == [1]
    assert response.closed
