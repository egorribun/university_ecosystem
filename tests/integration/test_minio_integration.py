"""Real MinIO storage-cell contract tests.

These tests are intentionally opt-in because they need a Docker daemon. The
fast unit suite keeps its deterministic fake-storage coverage; this module
proves the async wrapper against the actual S3-compatible server.
"""

from __future__ import annotations

import asyncio
import os
from io import BytesIO

import pytest
from minio.error import S3Error

from app.services.minio_storage import MinIOClient

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("USE_TESTCONTAINERS_MINIO") != "1",
        reason="Set USE_TESTCONTAINERS_MINIO=1 to run the MinIO cell",
    ),
]


@pytest.mark.asyncio
async def test_minio_upload_presign_and_delete_round_trip(
    minio_container: dict[str, str],
) -> None:
    storage = MinIOClient(
        endpoint=minio_container["endpoint"],
        access_key=minio_container["access_key"],
        secret_key=minio_container["secret_key"],
        default_bucket="quality-tests",
    )
    await storage.initialize()

    object_name = "integration/round-trip.txt"
    payload = BytesIO(b"quality-cell")
    await storage.upload_file(object_name, payload, content_type="text/plain")

    signed_url = await storage.get_presigned_url(object_name)
    assert "/quality-tests/integration/round-trip.txt" in signed_url

    response = await asyncio.to_thread(
        storage._client.get_object, "quality-tests", object_name
    )
    try:
        assert response.read() == b"quality-cell"
    finally:
        response.close()
        response.release_conn()

    await storage.delete_object(object_name)
    with pytest.raises(S3Error):
        await asyncio.to_thread(
            storage._client.stat_object, "quality-tests", object_name
        )
