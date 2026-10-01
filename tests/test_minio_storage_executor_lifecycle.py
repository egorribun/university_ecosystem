"""Lifecycle contracts for the process-wide MinIO executor."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import MagicMock

import pytest

import app.services.minio_storage as minio_module
from app.services.minio_storage import MinIOClient


def test_minio_executor_serves_distinct_loops_and_survives_loop_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rendezvous = Barrier(2)

    class FakeMinio:
        def presigned_get_object(
            self, bucket: str, object_name: str, *, expires: object
        ) -> str:
            if object_name in {"left", "right"}:
                rendezvous.wait(timeout=3)
            return f"fake-s3://{bucket}/{object_name}"

    fake_sdk = FakeMinio()
    monkeypatch.setattr(minio_module, "Minio", lambda *_args, **_kwargs: fake_sdk)
    client = MinIOClient("fake-minio:9000", "access", "secret")

    async def get_url(object_name: str) -> str:
        return await client.get_presigned_url(object_name)

    with ThreadPoolExecutor(max_workers=2) as loop_drivers:
        futures = [
            loop_drivers.submit(asyncio.run, get_url(object_name))
            for object_name in ("left", "right")
        ]
        results = [future.result(timeout=5) for future in futures]

    assert set(results) == {
        "fake-s3://uploads/left",
        "fake-s3://uploads/right",
    }

    # Both asyncio.run loops have now closed. The process-level executor must
    # remain usable from a newly created loop rather than retaining stale loop state.
    assert asyncio.run(get_url("after-loop-shutdown")) == (
        "fake-s3://uploads/after-loop-shutdown"
    )


def test_minio_operation_propagates_executor_submit_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk_call = MagicMock(return_value="fake-s3://uploads/item")
    fake_sdk = type(
        "FakeMinio",
        (),
        {"presigned_get_object": staticmethod(sdk_call)},
    )()
    monkeypatch.setattr(minio_module, "Minio", lambda *_args, **_kwargs: fake_sdk)

    class RejectedExecutor:
        def submit(self, *_args: object, **_kwargs: object) -> object:
            raise RuntimeError("cannot schedule new futures after shutdown")

    monkeypatch.setattr(minio_module, "_executor", RejectedExecutor())
    client = MinIOClient("fake-minio:9000", "access", "secret")

    with pytest.raises(RuntimeError, match="after shutdown"):
        asyncio.run(client.get_presigned_url("item"))

    sdk_call.assert_not_called()
