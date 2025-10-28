import types

import pytest

from app.services.storage import S3Storage, StaticFSStorage


@pytest.mark.asyncio
async def test_static_storage_saves_and_deletes(tmp_path):
    backend = StaticFSStorage(tmp_path, base_url="/static")
    url = await backend.save_file("avatars/test.png", b"payload", content_type="image/png")

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

    def put_object(self, **kwargs):
        self.put_calls.append(kwargs)

    def delete_object(self, **kwargs):
        self.delete_calls.append(kwargs)


@pytest.mark.asyncio
async def test_s3_storage_uses_client():
    client = DummyS3Client()
    backend = S3Storage(
        bucket="test-bucket",
        client=client,
        base_url="https://cdn.example/test-bucket",
    )

    url = await backend.save_file("avatars/test.png", b"payload", content_type="image/png")
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
