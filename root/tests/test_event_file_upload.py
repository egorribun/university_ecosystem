import asyncio
import io
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException, UploadFile, status
from starlette.datastructures import Headers
from sqlalchemy import select

from app.api import events
from app.core.config import settings
from app.models import models
from app.utils import files


async def _create_event(db_session, user: models.User) -> models.Event:
    event = models.Event(
        title="Test Event",
        description="desc",
        location="",
        event_type="workshop",
        starts_at=datetime.now(timezone.utc),
        ends_at=datetime.now(timezone.utc) + timedelta(hours=1),
        created_by=user.id,
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)
    return event


@pytest.mark.anyio("asyncio")
async def test_upload_event_file_offloads_io(
    tmp_path, monkeypatch, db_session, user_factory
):
    admin = await user_factory(role="admin")
    event = await _create_event(db_session, admin)

    payload = b"example data"
    upload = UploadFile(
        filename="notes.txt",
        file=io.BytesIO(payload),
        headers=Headers({"content-type": "text/plain"}),
    )

    calls: list[tuple[object, tuple[object, ...], dict[str, object]]] = []

    async def fake_to_thread(func, /, *args, **kwargs):  # type: ignore[override]
        calls.append((func, args, kwargs))
        return func(*args, **kwargs)

    monkeypatch.setattr(files, "asyncio", asyncio)
    monkeypatch.setattr(files.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(settings, "static_dir_path", tmp_path)
    monkeypatch.setattr(settings, "event_file_allowed_mime_types", ["text/plain"])
    monkeypatch.setattr(settings, "event_file_allowed_extensions", [".txt"])
    monkeypatch.setattr(settings, "event_file_max_size_bytes", 1024)

    result = await events.upload_event_file(event.id, upload, db=db_session, user=admin)

    assert result.event_id == event.id
    assert result.file_url.startswith("/static/event_files/")
    stored_path = tmp_path / "event_files" / result.file_url.rsplit("/", 1)[-1]
    assert stored_path.exists()
    assert stored_path.read_bytes() == payload
    assert any(func is files._ensure_dir for func, _, _ in calls)
    assert any(func.__name__ == "write_bytes" for func, _, _ in calls)


@pytest.mark.anyio("asyncio")
async def test_upload_event_file_rejects_large_payload(
    tmp_path, monkeypatch, db_session, user_factory
):
    admin = await user_factory(role="admin")
    event = await _create_event(db_session, admin)

    payload = b"x" * 9
    upload = UploadFile(
        filename="notes.txt",
        file=io.BytesIO(payload),
        headers=Headers({"content-type": "text/plain"}),
    )

    monkeypatch.setattr(settings, "static_dir_path", tmp_path)
    monkeypatch.setattr(settings, "event_file_allowed_mime_types", ["text/plain"])
    monkeypatch.setattr(settings, "event_file_allowed_extensions", [".txt"])
    monkeypatch.setattr(settings, "event_file_max_size_bytes", 8)

    with pytest.raises(HTTPException) as excinfo:
        await events.upload_event_file(event.id, upload, db=db_session, user=admin)

    assert excinfo.value.status_code == status.HTTP_413_CONTENT_TOO_LARGE
    folder = tmp_path / "event_files"
    assert not folder.exists()


@pytest.mark.anyio("asyncio")
async def test_upload_event_file_rejects_forbidden_type(
    tmp_path, monkeypatch, db_session, user_factory
):
    admin = await user_factory(role="admin")
    event = await _create_event(db_session, admin)

    upload = UploadFile(
        filename="malware.exe",
        file=io.BytesIO(b"binary"),
        headers=Headers({"content-type": "application/x-msdownload"}),
    )

    monkeypatch.setattr(settings, "static_dir_path", tmp_path)
    monkeypatch.setattr(settings, "event_file_allowed_mime_types", ["text/plain"])
    monkeypatch.setattr(settings, "event_file_allowed_extensions", [".txt"])
    monkeypatch.setattr(settings, "event_file_max_size_bytes", 1024)

    with pytest.raises(HTTPException) as excinfo:
        await events.upload_event_file(event.id, upload, db=db_session, user=admin)

    assert excinfo.value.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    folder = tmp_path / "event_files"
    assert not folder.exists()


@pytest.mark.anyio("asyncio")
async def test_delete_event_file_removes_payload(
    tmp_path, monkeypatch, db_session, user_factory
):
    admin = await user_factory(role="admin")
    event = await _create_event(db_session, admin)

    payload = b"example data"
    upload = UploadFile(
        filename="notes.txt",
        file=io.BytesIO(payload),
        headers=Headers({"content-type": "text/plain"}),
    )

    monkeypatch.setattr(settings, "static_dir_path", tmp_path)
    monkeypatch.setattr(settings, "event_file_allowed_mime_types", ["text/plain"])
    monkeypatch.setattr(settings, "event_file_allowed_extensions", [".txt"])
    monkeypatch.setattr(settings, "event_file_max_size_bytes", 1024)

    event_file = await events.upload_event_file(
        event.id, upload, db=db_session, user=admin
    )

    stored_path = tmp_path / "event_files" / event_file.file_url.rsplit("/", 1)[-1]
    assert stored_path.exists()

    result = await events.delete_event_file(event_file.id, db=db_session, user=admin)

    assert result == {"ok": True}
    assert not stored_path.exists()


@pytest.mark.anyio("asyncio")
async def test_delete_event_removes_all_files(
    tmp_path, monkeypatch, db_session, user_factory
):
    admin = await user_factory(role="admin")
    event = await _create_event(db_session, admin)

    monkeypatch.setattr(settings, "static_dir_path", tmp_path)
    monkeypatch.setattr(settings, "event_file_allowed_mime_types", ["text/plain"])
    monkeypatch.setattr(settings, "event_file_allowed_extensions", [".txt"])
    monkeypatch.setattr(settings, "event_file_max_size_bytes", 1024)

    stored_paths = []
    for idx in range(2):
        upload = UploadFile(
            filename=f"notes-{idx}.txt",
            file=io.BytesIO(f"payload-{idx}".encode()),
            headers=Headers({"content-type": "text/plain"}),
        )
        event_file = await events.upload_event_file(
            event.id, upload, db=db_session, user=admin
        )
        stored_paths.append(
            tmp_path / "event_files" / event_file.file_url.rsplit("/", 1)[-1]
        )

    for path in stored_paths:
        assert path.exists()

    result = await events.delete_event(event.id, db=db_session, user=admin)

    assert result == {"ok": True}
    for path in stored_paths:
        assert not path.exists()
    remaining_files = (
        await db_session.execute(
            select(models.EventFile).where(models.EventFile.event_id == event.id)
        )
    ).scalars()
    assert list(remaining_files) == []
