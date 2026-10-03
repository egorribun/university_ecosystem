"""Real S3-compatible storage-cell contract tests for ``S3Storage``.

These tests are intentionally opt-in because they need a Docker daemon. The
fast unit suite keeps its deterministic fake-client coverage; this module
proves the production ``S3Storage`` backend against an actual S3-compatible
server (the pinned SeaweedFS cell from ``tests/conftest.py``).
"""

from __future__ import annotations

import inspect
import os
import re

import pytest

from app.services.storage import S3Storage
from tests.conftest import minio_container

pytestmark = pytest.mark.integration


def test_disposable_s3_cell_uses_pinned_seaweedfs() -> None:
    fixture_source = inspect.getsource(minio_container)
    assert re.search(
        r"ghcr\.io/chrislusf/seaweedfs:4\.47@sha256:[0-9a-f]{64}", fixture_source
    )
    assert '.with_command("mini -dir=/data -s3.port=9000")' in fixture_source
    assert '.with_env("S3_BUCKET", "quality-tests")' in fixture_source


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("USE_TESTCONTAINERS_MINIO") != "1",
    reason="Set USE_TESTCONTAINERS_MINIO=1 to run the disposable S3 cell",
)
async def test_s3_storage_save_read_exists_delete_round_trip(
    minio_container: dict[str, str],
) -> None:
    storage = S3Storage(
        bucket="quality-tests",
        region="us-east-1",
        access_key=minio_container["access_key"],
        secret_key=minio_container["secret_key"],
        endpoint_url=f"http://{minio_container['endpoint']}",
    )
    await storage.probe_bucket()

    file_url = await storage.save_file(
        "integration/round-trip.txt", b"quality-cell", content_type="text/plain"
    )
    assert file_url.endswith("/quality-tests/integration/round-trip.txt")

    assert await storage.exists(file_url) is True
    assert await storage.read_file(file_url) == b"quality-cell"
    # The bounded read returns max_bytes + 1 bytes so callers can detect overflow.
    assert await storage.read_file(file_url, max_bytes=7) == b"quality-"

    await storage.delete_file(file_url)
    assert await storage.exists(file_url) is False
