"""MinIO failure-injection tests backed by real disposable services.

The fast storage unit tests keep their deterministic SDK fakes.  These tests
are different: CI starts a real MinIO service and routes the application
through a ToxiProxy listener so that the S3 error and network-timeout paths
are exercised against the actual async S3 client.
"""

from __future__ import annotations

import asyncio
import io
import os
from urllib.parse import urlparse

import httpx
import pytest
from fastapi import UploadFile
from minio.error import S3Error
from PIL import Image
from sqlalchemy import text
from starlette.datastructures import Headers

import app.utils.files
from app.services.minio_storage import MinIOClient
from app.services.storage import S3Storage
from app.services.user.media_service import UserMediaService

TOXIPROXY_URL = os.getenv("TOXIPROXY_URL", "http://localhost:8474").rstrip("/")
MINIO_PROXY_ENDPOINT = os.getenv("MINIO_PROXY_ENDPOINT", "")
MINIO_DIRECT_ENDPOINT = os.getenv("MINIO_DIRECT_ENDPOINT", "")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "quality-chaos")


def _toxiproxy_available() -> bool:
    """Return True when the chaos control plane is reachable."""

    try:
        response = httpx.get(f"{TOXIPROXY_URL}/version", timeout=2.0)
        return response.status_code == 200
    except (httpx.HTTPError, OSError):
        return False


def _minio_chaos_configured() -> bool:
    return bool(
        MINIO_PROXY_ENDPOINT
        and MINIO_DIRECT_ENDPOINT
        and MINIO_ACCESS_KEY
        and MINIO_SECRET_KEY
    )


pytestmark = [
    pytest.mark.chaos,
    pytest.mark.integration,
    pytest.mark.skipif(
        not _toxiproxy_available(),
        reason="ToxiProxy not available",
    ),
    pytest.mark.skipif(
        not _minio_chaos_configured(),
        reason="Real MinIO chaos endpoints are not configured",
    ),
]


def _host_port(endpoint: str) -> str:
    """Convert an endpoint URL or host:port value to MinIO SDK format."""

    parsed = urlparse(endpoint if "://" in endpoint else f"http://{endpoint}")
    if not parsed.netloc:
        raise ValueError(f"Invalid MinIO endpoint: {endpoint}")
    return parsed.netloc


def _make_png_bytes(color: tuple[int, int, int] = (255, 0, 0)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (1, 1), color=color).save(buffer, format="PNG")
    return buffer.getvalue()


def _direct_minio_client(*, bucket: str = MINIO_BUCKET) -> MinIOClient:
    return MinIOClient(
        endpoint=_host_port(MINIO_DIRECT_ENDPOINT),
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        default_bucket=bucket,
    )


def _proxy_minio_client(*, bucket: str) -> MinIOClient:
    return MinIOClient(
        endpoint=_host_port(MINIO_PROXY_ENDPOINT),
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        default_bucket=bucket,
    )


def _s3_storage() -> S3Storage:
    return S3Storage(
        bucket=MINIO_BUCKET,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        endpoint_url=MINIO_PROXY_ENDPOINT,
        base_url=f"{MINIO_PROXY_ENDPOINT.rstrip('/')}/{MINIO_BUCKET}",
    )


async def _add_toxic(name: str, toxic_type: str, attributes: dict[str, int]) -> None:
    async with httpx.AsyncClient(base_url=TOXIPROXY_URL) as http:
        response = await http.post(
            "/proxies/minio/toxics",
            json={"name": name, "type": toxic_type, "attributes": attributes},
        )
        response.raise_for_status()


async def _remove_toxic(name: str) -> None:
    async with httpx.AsyncClient(base_url=TOXIPROXY_URL) as http:
        response = await http.delete(f"/proxies/minio/toxics/{name}")
        if response.status_code not in {200, 404}:
            response.raise_for_status()


@pytest.mark.asyncio
async def test_real_minio_s3_error_is_propagated() -> None:
    """A real MinIO ``NoSuchBucket`` response is not hidden as a fake error."""

    missing_bucket = "quality-chaos-missing-bucket"
    # Keep the protocol-level S3 assertion direct.  MinIO's bucket-region
    # discovery request is not transparently forwarded by every ToxiProxy
    # build, while the timeout scenario below deliberately exercises the
    # network-fault path through the proxy.
    storage = _direct_minio_client(bucket=missing_bucket)

    with pytest.raises(S3Error) as error:
        await storage.upload_file("chaos/missing-bucket.txt", io.BytesIO(b"boom"))

    assert error.value.code == "NoSuchBucket"


@pytest.mark.asyncio
async def test_minio_timeout_rolls_back_avatar_state(
    db_session, user_factory, monkeypatch
) -> None:
    """A ToxiProxy timeout aborts the real upload before avatar state changes."""

    direct_storage = _direct_minio_client()
    await direct_storage.initialize()
    real_storage = _s3_storage()
    monkeypatch.setattr(app.utils.files, "storage_backend", real_storage)

    user = await user_factory(is_active=True)
    await _add_toxic("minio_upload_timeout", "timeout", {"timeout": 0})
    try:
        upload = UploadFile(
            filename="avatar.png",
            file=io.BytesIO(_make_png_bytes()),
            headers=Headers({"content-type": "image/png"}),
        )
        from app.repositories.unit_of_work import uow_from_session

        service = UserMediaService(uow_from_session(db_session))
        with pytest.raises(TimeoutError):
            async with asyncio.timeout(5):
                await service.upload_avatar(user.id, upload)
    finally:
        await _remove_toxic("minio_upload_timeout")

    result = await db_session.execute(
        text("SELECT avatar_url FROM user_profiles WHERE user_id = :user_id"),
        {"user_id": str(user.id)},
    )
    assert result.scalar() is None
