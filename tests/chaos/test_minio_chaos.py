"""S3 failure-injection tests backed by real disposable services.

The fast storage unit tests keep their deterministic SDK fakes.  These tests
are different: CI starts a disposable S3-compatible service and routes the
application through a ToxiProxy listener.  The S3 error uses the real MinIO
SDK; the network-timeout path uses the application's actual async S3 client.
"""

from __future__ import annotations

import asyncio
import io
import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any
from urllib.parse import urlparse

import httpx
import pytest
from fastapi import UploadFile
from minio.error import S3Error
from PIL import Image
from sqlalchemy import select
from starlette.datastructures import Headers

import app.utils.files
from app.models import UserProfile
from app.services.storage import S3Storage
from app.services.user.media_service import UserMediaService
from tests.minio_chaos_client import MinIOClient

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
        reason="S3-compatible chaos endpoints are not configured",
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


def _s3_storage(endpoint: str = MINIO_PROXY_ENDPOINT) -> S3Storage:
    endpoint_url = endpoint if "://" in endpoint else f"http://{endpoint}"
    return S3Storage(
        bucket=MINIO_BUCKET,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        endpoint_url=endpoint_url,
        base_url=f"{endpoint_url.rstrip('/')}/{MINIO_BUCKET}",
    )


async def _add_toxic(name: str, toxic_type: str, attributes: dict[str, int]) -> None:
    async with httpx.AsyncClient(base_url=TOXIPROXY_URL) as http:
        response = await http.post(
            "/proxies/minio/toxics",
            json={
                "name": name,
                "type": toxic_type,
                "stream": "downstream",
                "toxicity": 1.0,
                "attributes": attributes,
            },
        )
        response.raise_for_status()
        response = await http.get(f"/proxies/minio/toxics/{name}")
        response.raise_for_status()
        toxic = response.json()
        assert toxic["name"] == name
        assert toxic["type"] == toxic_type
        assert toxic["stream"] == "downstream"
        assert toxic["toxicity"] == 1.0
        assert toxic["attributes"] == attributes


async def _remove_toxic(name: str) -> None:
    async with httpx.AsyncClient(base_url=TOXIPROXY_URL) as http:
        response = await http.delete(f"/proxies/minio/toxics/{name}")
        if response.status_code not in {200, 404}:
            response.raise_for_status()
        response = await http.get(f"/proxies/minio/toxics/{name}")
        assert response.status_code == 404, "ToxiProxy toxic was not removed"


@pytest.mark.asyncio
async def test_s3_no_such_bucket_error_is_propagated() -> None:
    """A real S3 ``NoSuchBucket`` response is not hidden as a fake error."""

    missing_bucket = f"quality-chaos-missing-{uuid.uuid4().hex}"
    # Keep the protocol-level S3 assertion direct.  The MinIO SDK's bucket-region
    # discovery request is not transparently forwarded by every ToxiProxy
    # build, while the timeout scenario below deliberately exercises the
    # network-fault path through the proxy.
    storage = _direct_minio_client(bucket=missing_bucket)

    with pytest.raises(S3Error) as error:
        await storage.upload_file("chaos/missing-bucket.txt", io.BytesIO(b"boom"))

    assert error.value.code == "NoSuchBucket"


@pytest.mark.asyncio
async def test_s3_outage_blocks_avatar_upload_and_preserves_state(
    db_session, user_factory, monkeypatch
) -> None:
    """A ToxiProxy timeout blocks the upload while the avatar row stays unchanged."""

    direct_storage = _direct_minio_client()
    await direct_storage.initialize()
    real_storage = _s3_storage()
    direct_s3_storage = _s3_storage(MINIO_DIRECT_ENDPOINT)
    # Both paths must reach the same live bucket before the fault is applied.
    async with asyncio.timeout(10):
        await direct_s3_storage.probe_bucket()
        await real_storage.probe_bucket()
    monkeypatch.setattr(app.utils.files, "storage_backend", real_storage)

    original_avatar = "/static/avatars/existing.png"
    user = await user_factory(is_active=True, avatar_url=original_avatar)
    avatar_query = select(UserProfile.avatar_url).where(UserProfile.user_id == user.id)
    assert (await db_session.execute(avatar_query)).scalar_one() == original_avatar

    request_attempted = asyncio.Event()
    attempted_requests: list[tuple[str, str]] = []
    attempted_keys: set[str] = set()
    build_client = real_storage._build_aioboto3_client

    @asynccontextmanager
    async def observed_client() -> AsyncIterator[Any]:
        async with build_client() as client:

            def observe_put(request: Any, **_kwargs: Any) -> None:
                attempted_requests.append((request.method, request.url))
                path = urlparse(request.url).path
                prefix = f"/{MINIO_BUCKET}/avatars/"
                if request.method == "PUT" and path.startswith(prefix):
                    attempted_keys.add(path[len(f"/{MINIO_BUCKET}/") :])
                request_attempted.set()

            client.meta.events.register("before-send.s3.PutObject", observe_put)
            yield client

    monkeypatch.setattr(real_storage, "_build_aioboto3_client", observed_client)
    toxic_name = f"minio_upload_timeout_{uuid.uuid4().hex}"
    try:
        # The finally block also runs if the create response is lost after the
        # server installed the toxic.
        await _add_toxic(toxic_name, "timeout", {"timeout": 0})
        async with asyncio.timeout(10):
            await direct_s3_storage.probe_bucket()
        with pytest.raises(TimeoutError):
            async with asyncio.timeout(2):
                await real_storage.probe_bucket()

        upload = UploadFile(
            filename="avatar.png",
            file=io.BytesIO(_make_png_bytes()),
            headers=Headers({"content-type": "image/png"}),
        )
        from app.repositories.unit_of_work import uow_from_session

        service = UserMediaService(uow_from_session(db_session))
        upload_task = asyncio.create_task(service.upload_avatar(user.id, upload))
        try:
            # A timeout elsewhere in the service is not evidence of an S3 fault.
            await asyncio.wait_for(request_attempted.wait(), timeout=10)
            method, request_url = attempted_requests[0]
            proxy_endpoint = (
                MINIO_PROXY_ENDPOINT
                if "://" in MINIO_PROXY_ENDPOINT
                else f"http://{MINIO_PROXY_ENDPOINT}"
            )
            proxy = urlparse(proxy_endpoint)
            destination = urlparse(request_url)
            assert method == "PUT"
            assert (destination.scheme, destination.netloc) == (
                proxy.scheme,
                proxy.netloc,
            )
            assert destination.path.startswith(f"/{MINIO_BUCKET}/avatars/")
            done, _ = await asyncio.wait({upload_task}, timeout=2)
            assert not done, "The avatar upload did not remain blocked by the toxic"
        finally:
            upload_task.cancel()
            with suppress(asyncio.CancelledError):
                await upload_task
    finally:
        try:
            await _remove_toxic(toxic_name)
        finally:
            # A downstream toxic can hide a successful PUT response. Delete the
            # exact attempted object even when the service never saw success.
            for key in attempted_keys:
                async with asyncio.timeout(10):
                    await direct_s3_storage.delete_file(key)
                    assert not await direct_s3_storage.exists(key)

    # Removal must restore the proxied path and leave the existing row intact.
    async with asyncio.timeout(10):
        await real_storage.probe_bucket()
    assert (await db_session.execute(avatar_query)).scalar_one() == original_avatar
