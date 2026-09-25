"""S3 reads distinguish missing objects from permission and service failures."""

from unittest.mock import AsyncMock

import pytest
from botocore.exceptions import ClientError

from app.services.storage import S3Storage


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
