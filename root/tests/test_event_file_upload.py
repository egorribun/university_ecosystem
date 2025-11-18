import asyncio
import io
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from starlette.datastructures import Headers

from app.api import events
from app.core.config import settings
from app.localization import translate
from app.models import models
from app.schemas import schemas
from app.utils import files


async def _create_event(db_session, user: models.User) -> models.Event:
    event = models.Event(
        title="Test Event",
        description="desc",
        location="",
        event_type="workshop",
        starts_at=datetime.now(UTC),
        ends_at=datetime.now(UTC) + timedelta(hours=1),
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

    result = await events.upload_event_file(
        event.id, upload, request=None, db=db_session, user=admin
    )

    assert result.event_id == event.id
    assert result.file_url.startswith("/static/event_files/")
    stored_path = tmp_path / "event_files" / result.file_url.rsplit("/", 1)[-1]
    assert stored_path.exists()
    assert stored_path.read_bytes() == payload
    assert any(func is files._ensure_dir for func, _, _ in calls)
    assert any(func.__name__ == "write_bytes" for func, _, _ in calls)


@pytest.mark.anyio("asyncio")
async def test_upload_event_file_cleans_up_on_commit_failure(
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

    delete_calls: list[str] = []
    original_delete = events.delete_static_file

    async def tracking_delete(url: str) -> None:
        delete_calls.append(url)
        await original_delete(url)

    monkeypatch.setattr(events, "delete_static_file", tracking_delete)

    async def failing_commit(*_args, **_kwargs):
        raise RuntimeError("commit failed")

    monkeypatch.setattr(db_session, "commit", failing_commit)

    with pytest.raises(RuntimeError):
        await events.upload_event_file(
            event.id, upload, request=None, db=db_session, user=admin
        )

    folder = tmp_path / "event_files"
    assert delete_calls, "delete_static_file should run on failure"
    if folder.exists():
        assert not any(folder.iterdir())


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
        await events.upload_event_file(
            event.id, upload, request=None, db=db_session, user=admin
        )

    assert excinfo.value.status_code == status.HTTP_413_CONTENT_TOO_LARGE
    assert excinfo.value.detail == translate("errors.files.too_large", locale="en")
    folder = tmp_path / "event_files"
    assert not folder.exists()


@pytest.mark.anyio("asyncio")
async def test_upload_event_file_respects_scanner_limit(
    tmp_path, monkeypatch, db_session, user_factory
):
    admin = await user_factory(role="admin")
    event = await _create_event(db_session, admin)

    payload = b"x" * 1024
    upload = UploadFile(
        filename="notes.txt",
        file=io.BytesIO(payload),
        headers=Headers({"content-type": "text/plain"}),
    )

    monkeypatch.setattr(settings, "static_dir_path", tmp_path)
    monkeypatch.setattr(settings, "event_file_allowed_mime_types", ["text/plain"])
    monkeypatch.setattr(settings, "event_file_allowed_extensions", [".txt"])
    monkeypatch.setattr(settings, "event_file_max_size_bytes", 2048)
    monkeypatch.setattr(settings, "event_file_scanner_enabled", True)
    monkeypatch.setattr(
        settings,
        "event_file_scanner_max_size_mb",
        (len(payload) - 1) / (1024 * 1024),
    )

    with pytest.raises(HTTPException) as excinfo:
        await events.upload_event_file(
            event.id, upload, request=None, db=db_session, user=admin
        )

    assert excinfo.value.status_code == status.HTTP_413_CONTENT_TOO_LARGE
    assert excinfo.value.detail == translate("errors.files.too_large", locale="en")
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
        await events.upload_event_file(
            event.id, upload, request=None, db=db_session, user=admin
        )

    assert excinfo.value.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    assert excinfo.value.detail == translate(
        "errors.files.unsupported_type", locale="en"
    )
    folder = tmp_path / "event_files"
    assert not folder.exists()


@pytest.mark.anyio("asyncio")
async def test_upload_event_file_prefers_detected_metadata(
    tmp_path, monkeypatch, db_session, user_factory
):
    admin = await user_factory(role="admin")
    event = await _create_event(db_session, admin)

    pdf_payload = b"%PDF-1.7\n" + b"0" * 100
    upload = UploadFile(
        filename="notes.txt",
        file=io.BytesIO(pdf_payload),
        headers=Headers({"content-type": "text/plain"}),
    )

    monkeypatch.setattr(settings, "static_dir_path", tmp_path)
    monkeypatch.setattr(
        settings,
        "event_file_allowed_mime_types",
        ["text/plain", "application/pdf"],
    )
    monkeypatch.setattr(settings, "event_file_allowed_extensions", [".txt", ".pdf"])
    monkeypatch.setattr(settings, "event_file_max_size_bytes", 1024)

    result = await events.upload_event_file(
        event.id, upload, request=None, db=db_session, user=admin
    )

    stored_path = tmp_path / "event_files" / result.file_url.rsplit("/", 1)[-1]
    assert stored_path.exists()
    assert stored_path.suffix == ".pdf"
    assert stored_path.read_bytes() == pdf_payload


@pytest.mark.anyio("asyncio")
async def test_upload_event_file_rejects_infected_payload(
    tmp_path, monkeypatch, db_session, user_factory
):
    admin = await user_factory(role="admin")
    event = await _create_event(db_session, admin)

    payload = b"clean-looking"
    upload = UploadFile(
        filename="notes.txt",
        file=io.BytesIO(payload),
        headers=Headers({"content-type": "text/plain"}),
    )

    monkeypatch.setattr(settings, "static_dir_path", tmp_path)
    monkeypatch.setattr(settings, "event_file_allowed_mime_types", ["text/plain"])
    monkeypatch.setattr(settings, "event_file_allowed_extensions", [".txt"])
    monkeypatch.setattr(settings, "event_file_max_size_bytes", 1024)

    async def fake_scan(
        scanned, *, locale: str | None = None, size_bytes: int | None = None
    ) -> None:
        assert scanned is upload
        assert size_bytes == len(payload)
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=translate("errors.files.infected", locale=locale),
        )

    monkeypatch.setattr(files, "scan_for_malware", fake_scan)

    with pytest.raises(HTTPException) as excinfo:
        await events.upload_event_file(
            event.id, upload, request=None, db=db_session, user=admin
        )

    assert excinfo.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert excinfo.value.detail == translate("errors.files.infected", locale="en")
    folder = tmp_path / "event_files"
    assert not folder.exists()


@pytest.mark.anyio("asyncio")
async def test_upload_event_file_rejects_detected_type_not_allowed(
    tmp_path, monkeypatch, db_session, user_factory
):
    admin = await user_factory(role="admin")
    event = await _create_event(db_session, admin)

    pdf_payload = b"%PDF-1.7\n" + b"0" * 100
    upload = UploadFile(
        filename="notes.txt",
        file=io.BytesIO(pdf_payload),
        headers=Headers({"content-type": "text/plain"}),
    )

    monkeypatch.setattr(settings, "static_dir_path", tmp_path)
    monkeypatch.setattr(settings, "event_file_allowed_mime_types", ["text/plain"])
    monkeypatch.setattr(settings, "event_file_allowed_extensions", [".txt"])
    monkeypatch.setattr(settings, "event_file_max_size_bytes", 1024)

    with pytest.raises(HTTPException) as excinfo:
        await events.upload_event_file(
            event.id, upload, request=None, db=db_session, user=admin
        )

    assert excinfo.value.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    assert excinfo.value.detail == translate(
        "errors.files.unsupported_type", locale="en"
    )
    folder = tmp_path / "event_files"
    assert not folder.exists()


@pytest.mark.anyio("asyncio")
async def test_upload_event_file_allows_clean_payload_with_scanner(
    tmp_path, monkeypatch, db_session, user_factory
):
    admin = await user_factory(role="admin")
    event = await _create_event(db_session, admin)

    payload = b"safe data"
    upload = UploadFile(
        filename="notes.txt",
        file=io.BytesIO(payload),
        headers=Headers({"content-type": "text/plain"}),
    )

    monkeypatch.setattr(settings, "static_dir_path", tmp_path)
    monkeypatch.setattr(settings, "event_file_allowed_mime_types", ["text/plain"])
    monkeypatch.setattr(settings, "event_file_allowed_extensions", [".txt"])
    monkeypatch.setattr(settings, "event_file_max_size_bytes", 1024)

    calls: list[tuple[bytes, str | None]] = []

    async def fake_scan(
        scanned, *, locale: str | None = None, size_bytes: int | None = None
    ) -> None:
        calls.append((scanned, locale, size_bytes))
        assert scanned is upload
        assert size_bytes == len(payload)
        return None

    monkeypatch.setattr(files, "scan_for_malware", fake_scan)

    result = await events.upload_event_file(
        event.id, upload, request=None, db=db_session, user=admin
    )

    assert result.event_id == event.id
    assert calls and calls[0][0] is upload
    stored_path = tmp_path / "event_files" / result.file_url.rsplit("/", 1)[-1]
    assert stored_path.exists()
    assert stored_path.read_bytes() == payload


@pytest.mark.anyio("asyncio")
async def test_update_event_replaces_image_removes_old_file(
    tmp_path, monkeypatch, db_session, user_factory
):
    admin = await user_factory(role="admin")
    event = await _create_event(db_session, admin)

    old_filename = "old.png"
    old_path = tmp_path / "event_images" / old_filename
    old_path.parent.mkdir(parents=True, exist_ok=True)
    old_path.write_bytes(b"old")

    event.image_url = f"/static/event_images/{old_filename}"
    await db_session.commit()
    await db_session.refresh(event)

    monkeypatch.setattr(settings, "static_dir_path", tmp_path)

    payload = schemas.EventUpdate(image_url="/static/event_images/new.png")
    result = await events.update_event(
        event.id, payload, request=None, db=db_session, user=admin
    )

    assert result.image_url == "/static/event_images/new.png"
    assert not old_path.exists()


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
        event.id, upload, request=None, db=db_session, user=admin
    )

    stored_path = tmp_path / "event_files" / event_file.file_url.rsplit("/", 1)[-1]
    assert stored_path.exists()

    result = await events.delete_event_file(
        event_file.id, request=None, db=db_session, user=admin
    )

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

    image_path = tmp_path / "event_images" / "banner.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(b"banner")
    event.image_url = "/static/event_images/banner.png"
    await db_session.commit()
    await db_session.refresh(event)

    stored_paths = []
    for idx in range(2):
        upload = UploadFile(
            filename=f"notes-{idx}.txt",
            file=io.BytesIO(f"payload-{idx}".encode()),
            headers=Headers({"content-type": "text/plain"}),
        )
        event_file = await events.upload_event_file(
            event.id, upload, request=None, db=db_session, user=admin
        )
        stored_paths.append(
            tmp_path / "event_files" / event_file.file_url.rsplit("/", 1)[-1]
        )

    for path in stored_paths:
        assert path.exists()

    result = await events.delete_event(
        event.id, request=None, db=db_session, user=admin
    )

    assert result == {"ok": True}
    for path in stored_paths:
        assert not path.exists()
    assert not image_path.exists()
    remaining_files = (
        await db_session.execute(
            select(models.EventFile).where(models.EventFile.event_id == event.id)
        )
    ).scalars()
    assert list(remaining_files) == []
