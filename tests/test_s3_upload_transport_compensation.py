"""Exclusive S3 uploads compensate real SDK transport failures, not rejections."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from botocore.exceptions import (
    ClientError,
    ConnectionClosedError,
    EndpointConnectionError,
    HTTPClientError,
)

from app.services.storage import S3Storage


def transport_error(kind):
    if kind == "closed":
        return ConnectionClosedError(endpoint_url="https://private.invalid/secret")
    if kind == "endpoint":
        return EndpointConnectionError(endpoint_url="https://private.invalid/secret")
    return HTTPClientError(error="private transport detail")


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["closed", "endpoint", "http"])
async def test_landed_exclusive_put_with_lost_response_is_compensated(kind):
    original = transport_error(kind)
    objects = {"chat_uploads/unrelated.pdf": b"keep"}
    client = AsyncMock()

    async def put_object(**arguments):
        objects[arguments["Key"]] = arguments["Body"]
        raise original

    async def delete_object(**arguments):
        objects.pop(arguments["Key"], None)

    client.put_object.side_effect = put_object
    client.delete_object.side_effect = delete_object
    storage = S3Storage(bucket="uploads", base_url="/api/v1/img", client=client)

    with pytest.raises(type(original)) as caught:
        await storage.save_file_cancellable("chat_uploads/new.pdf", b"private")

    assert caught.value is original
    assert objects == {"chat_uploads/unrelated.pdf": b"keep"}
    client.delete_object.assert_awaited_once_with(
        Bucket="uploads", Key="chat_uploads/new.pdf"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["closed", "endpoint", "http"])
async def test_sdk_transport_failure_does_not_delete_shared_put(kind):
    original = transport_error(kind)
    client = AsyncMock()
    client.put_object.side_effect = original
    storage = S3Storage(bucket="uploads", client=client)

    with pytest.raises(type(original)) as caught:
        await storage.save_file("avatars/shared.png", b"bytes")

    assert caught.value is original
    client.delete_object.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["PreconditionFailed", "AccessDenied"])
async def test_definitive_sdk_rejection_does_not_compensate(code):
    original = ClientError(
        {
            "Error": {"Code": code, "Message": "private provider text"},
            "ResponseMetadata": {
                "HTTPStatusCode": 412 if code == "PreconditionFailed" else 403
            },
        },
        "PutObject",
    )
    client = AsyncMock()
    client.put_object.side_effect = original
    storage = S3Storage(bucket="uploads", client=client)

    with pytest.raises(ClientError) as caught:
        await storage.save_file_cancellable("chat_uploads/new.pdf", b"bytes")

    assert caught.value is original
    client.delete_object.assert_not_awaited()


@pytest.mark.asyncio
async def test_compensation_error_preserves_original_sdk_failure(caplog):
    original = transport_error("closed")
    client = AsyncMock()
    client.put_object.side_effect = original
    client.delete_object.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "private-delete-token"}},
        "DeleteObject",
    )
    storage = S3Storage(bucket="uploads", client=client)

    with pytest.raises(ConnectionClosedError) as caught:
        await storage.save_file_cancellable("chat_uploads/new.pdf", b"bytes")

    assert caught.value is original
    client.delete_object.assert_awaited_once()
    assert "private-delete-token" not in caplog.text
    assert "private.invalid" not in caplog.text


@pytest.mark.asyncio
async def test_upload_error_log_excludes_key_bucket_and_exception(caplog):
    original = OSError("provider-credential-private")
    client = AsyncMock()
    client.put_object.side_effect = original
    storage = S3Storage(bucket="private-bucket-name", client=client)

    with pytest.raises(OSError) as caught:
        await storage.save_file("private-user@example.edu/file.pdf", b"bytes")

    assert caught.value is original
    assert "s3_upload_failed" in caplog.text
    for secret in (
        "provider-credential-private",
        "private-bucket-name",
        "private-user@example.edu",
    ):
        assert secret not in caplog.text


@pytest.mark.asyncio
async def test_invalid_exclusive_key_never_deletes():
    client = AsyncMock()
    storage = S3Storage(bucket="uploads", client=client)

    with pytest.raises(ValueError):
        await storage.save_file_cancellable("../unowned.pdf", b"bytes")

    client.put_object.assert_not_awaited()
    client.delete_object.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancellation_during_sdk_compensation_keeps_delete_alive():
    client = AsyncMock()
    client.put_object.side_effect = transport_error("closed")
    started, release, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def delete_object(**_arguments):
        started.set()
        await release.wait()
        finished.set()

    client.delete_object.side_effect = delete_object
    storage = S3Storage(bucket="uploads", client=client)
    task = asyncio.create_task(
        storage.save_file_cancellable("chat_uploads/new.pdf", b"bytes")
    )
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        release.set()
        await asyncio.wait_for(finished.wait(), timeout=1)
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    client.delete_object.assert_awaited_once_with(
        Bucket="uploads", Key="chat_uploads/new.pdf"
    )
