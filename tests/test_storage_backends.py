import types
from unittest.mock import AsyncMock

import pytest

from app.services.storage import S3Storage, StaticFSStorage


@pytest.mark.asyncio
async def test_static_storage_saves_and_deletes(tmp_path):
    backend = StaticFSStorage(tmp_path, base_url="/static")
    url = await backend.save_file(
        "avatars/test.png", b"payload", content_type="image/png"
    )

    assert url == "/static/avatars/test.png"
    stored = tmp_path / "avatars" / "test.png"
    assert stored.exists()
    assert stored.read_bytes() == b"payload"

    await backend.delete_file(url)
    assert not stored.exists()


class DummyS3Client:
    def __init__(self) -> None:
        self.put_calls: list[dict[str, object]] = []
        self.delete_calls: list[dict[str, object]] = []
        self.meta = types.SimpleNamespace(endpoint_url="https://s3.mock.local")

    async def put_object(self, **kwargs):
        self.put_calls.append(kwargs)

    async def delete_object(self, **kwargs):
        self.delete_calls.append(kwargs)


@pytest.mark.asyncio
async def test_s3_storage_uses_client():
    client = DummyS3Client()
    backend = S3Storage(
        bucket="test-bucket",
        client=client,
        base_url="https://cdn.example/test-bucket",
    )

    url = await backend.save_file(
        "avatars/test.png", b"payload", content_type="image/png"
    )
    assert url == "https://cdn.example/test-bucket/avatars/test.png"

    assert client.put_calls
    put_args = client.put_calls[0]
    assert put_args["Bucket"] == "test-bucket"
    assert put_args["Key"] == "avatars/test.png"
    assert put_args["Body"] == b"payload"
    assert put_args["ContentType"] == "image/png"

    await backend.delete_file(url)
    assert client.delete_calls
    delete_args = client.delete_calls[0]
    assert delete_args["Bucket"] == "test-bucket"
    assert delete_args["Key"] == "avatars/test.png"

    # Deleting with raw key should also work and avoid extra calls.
    client.delete_calls.clear()
    await backend.delete_file("avatars/test.png")
    assert client.delete_calls
    assert client.delete_calls[0]["Key"] == "avatars/test.png"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "key", ["avatars/ExamX_2026.PNG", "X/report.pdf", "documents/AZ09_-x.json"]
)
async def test_s3_preserves_case_sensitive_object_keys_across_operations(
    key: str,
) -> None:
    client = AsyncMock()
    body = AsyncMock()
    body.read.return_value = b"payload"
    body.__aenter__.return_value = body
    body.__aexit__.return_value = None
    client.get_object.return_value = {"Body": body}
    storage = S3Storage(
        bucket="uploads", client=client, base_url="https://cdn.example/uploads"
    )

    url = await storage.save_file(key, b"payload")

    assert url == f"https://cdn.example/uploads/{key}"
    client.put_object.assert_awaited_once_with(
        Bucket="uploads", Key=key, Body=b"payload"
    )
    assert await storage.read_file(url) == b"payload"
    client.get_object.assert_awaited_once_with(Bucket="uploads", Key=key)
    assert await storage.exists(f"s3://uploads/{key}") is True
    client.head_object.assert_awaited_once_with(Bucket="uploads", Key=key)
    await storage.delete_file(key)
    client.delete_object.assert_awaited_once_with(Bucket="uploads", Key=key)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "key",
    [
        "docs/X%41",
        "docs/X?download=1",
        "docs/X#fragment",
        "docs/X;version",
        r"docs\X",
        "docs/\x00X",
        "docs/../X",
    ],
)
async def test_s3_uppercase_keys_do_not_bypass_invalid_path_rejection(
    key: str,
) -> None:
    client = AsyncMock()
    storage = S3Storage(bucket="uploads", client=client)

    with pytest.raises(ValueError):
        await storage.save_file(key, b"payload")

    client.put_object.assert_not_awaited()
