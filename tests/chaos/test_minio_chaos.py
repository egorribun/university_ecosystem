"""MinIO storage chaos tests.

Verifies that object storage write failures (S3Errors, timeouts) degrade
gracefully, roll back database state, and do not leave orphaned file entries.
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock

import pytest
from fastapi import UploadFile
from minio.error import S3Error
from PIL import Image
from sqlalchemy import text
from starlette.datastructures import Headers

import app.utils.files
from app.services.user.media_service import UserMediaService


def _make_png_bytes(color: tuple[int, int, int] = (255, 0, 0)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (1, 1), color=color).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_minio_upload_failure_rolls_back_db(
    db_session, user_factory, monkeypatch
) -> None:
    """Verify that a MinIO write failure (S3Error) aborts the upload, rolls back DB, and raises error."""
    user = await user_factory(is_active=True)

    # 1. Simulate MinIO S3Error on write
    s3_err = S3Error(
        MagicMock(),  # response
        "SlowDown",  # code
        "Simulated storage write slowdown/failure",
        "uploads",  # resource
        "req-1",
        "host-1",
    )

    async def mock_save_file(*args, **kwargs):
        raise s3_err

    # Patch active storage backend save_file method directly
    monkeypatch.setattr(app.utils.files.storage_backend, "save_file", mock_save_file)

    # 2. Build upload file
    payload = _make_png_bytes()
    upload = UploadFile(
        filename="avatar.png",
        file=io.BytesIO(payload),
        headers=Headers({"content-type": "image/png"}),
    )

    # Instantiate the real UserMediaService using uow_from_session
    from app.repositories.unit_of_work import uow_from_session

    uow = uow_from_session(db_session)
    service = UserMediaService(uow)

    # 3. Executing the upload must raise S3Error
    with pytest.raises(S3Error):
        await service.upload_avatar(user.id, upload)

    # 4. Verify DB was rolled back — use raw SQL to avoid ORM lazy loading issues
    res = await db_session.execute(
        text("SELECT avatar_url FROM user_profiles WHERE user_id = :user_id"),
        {"user_id": str(user.id)},
    )
    avatar_url = res.scalar()
    assert avatar_url is None
