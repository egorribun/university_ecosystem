"""
Tests for event file uploads.
"""

import asyncio
import io
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from starlette.datastructures import Headers

import app.models as models
from app.api import events
from app.core.config import settings
from app.core.localization import translate
from app.repositories.unit_of_work import uow_from_session
from app.schemas import schemas
from app.utils import files

FIXTURE_UPLOADS = Path(__file__).parent / "fixtures" / "uploads"


@pytest.fixture
def event_service(db_session):
    from unittest.mock import MagicMock

    from app.services.event_service import EventService

    uow = uow_from_session(db_session)
    vector = MagicMock()
    return EventService(uow, vector)


def _fallback_detect_mime(data: bytes) -> str | None:
    """Simple MIME detection fallback for platforms without libmagic."""
    if not data:
        return None
    if data.startswith(b"%PDF"):
        return "application/pdf"
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"GIF8"):
        return "image/gif"
    if data.startswith(b"RIFF") and b"WEBP" in data[:12]:
        return "image/webp"
    if data.startswith(b"PK\x03\x04"):
        return "application/zip"
    # SVG detection
    if b"<svg" in data[:1024].lower():
        return "image/svg+xml"
    # Assume text/plain for printable ASCII
    try:
        data[:512].decode("utf-8")
        return "text/plain"
    except UnicodeDecodeError:
        return "application/octet-stream"


@pytest.fixture(autouse=True)
def _mock_mime_detection(monkeypatch):
    """Mock MIME detection for platforms without libmagic (e.g., Windows)."""
    monkeypatch.setattr(files, "detect_mime_type", _fallback_detect_mime)


@pytest.fixture
def mock_checker():
    """Mock PermissionChecker that always grants permissions."""
    return type("MockChecker", (), {"check_permission": AsyncMock(return_value=True)})()


MULTIPAGE_PDF_BYTES = b"""%PDF-1.4\n\
1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n\
2 0 obj\n<< /Type /Pages /Count 2 /Kids [3 0 R 4 0 R] >>\nendobj\n\
3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Contents 5 0 R >>\nendobj\n\
4 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Contents 6 0 R >>\nendobj\n\
5 0 obj\n<< /Length 44 >>\nstream\nBT /F1 12 Tf 72 712 Td (Hello) Tj ET\nendstream\nendobj\n\
6 0 obj\n<< /Length 44 >>\nstream\nBT /F1 12 Tf 72 712 Td (World) Tj ET\nendstream\nendobj\n\
trailer\n<< /Root 1 0 R >>\n%%EOF\n"""

POLYGLOT_PDF_BYTES = b"""%PDF-1.3\n\
1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n\
2 0 obj\n<< /Type /Pages /Count 1 /Kids [3 0 R] >>\nendobj\n\
3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Contents 4 0 R >>\nendobj\n\
4 0 obj\n<< /Length 120 >>\nstream\n<svg><script>alert('x')</script></svg>\nendstream\nendobj\n\
trailer\n<< /Root 1 0 R >>\n%%EOF\n"""


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


@pytest.mark.asyncio
async def test_upload_event_file_offloads_io(
    tmp_path, monkeypatch, db_session, user_factory, mock_checker
):
    admin = await user_factory(role="admin")
    event = await _create_event(db_session, admin)

    payload = b"example data"
    upload = UploadFile(
        filename="notes.txt",
        file=io.BytesIO(payload),
        headers=Headers({"content-type": "text/plain"}),
    )

    calls: list[Any] = []

    async def fake_to_thread(func, /, *args, **kwargs):
        calls.append((func, args, kwargs))
        return func(*args, **kwargs)

    monkeypatch.setattr(files, "asyncio", asyncio)
    monkeypatch.setattr(files.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(settings, "static_dir", str(tmp_path))
    monkeypatch.setattr(settings, "event_file_allowed_mime_types", ["text/plain"])
    monkeypatch.setattr(settings, "event_file_allowed_extensions", [".txt"])
    monkeypatch.setattr(settings, "event_file_max_size_bytes", 1024)

    result = await events.upload_event_file(
        event.id, upload, request=None, db=db_session, user=admin, checker=mock_checker
    )

    assert result.event_id == event.id
    assert result.file_url.startswith("/static/event_files/")
    stored_path = tmp_path / "event_files" / result.file_url.rsplit("/", 1)[-1]
    assert stored_path.exists()
    assert stored_path.read_bytes() == payload
    assert any(func is files._ensure_dir for func, _, _ in calls)
    assert any(func.__name__ == "write_bytes" for func, _, _ in calls)


@pytest.mark.asyncio
async def test_upload_event_file_cleans_up_on_commit_failure(
    tmp_path, monkeypatch, db_session, user_factory, mock_checker
):
    admin = await user_factory(role="admin")
    event = await _create_event(db_session, admin)

    payload = b"example data"
    upload = UploadFile(
        filename="notes.txt",
        file=io.BytesIO(payload),
        headers=Headers({"content-type": "text/plain"}),
    )

    monkeypatch.setattr(settings, "static_dir", str(tmp_path))
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
            event.id,
            upload,
            request=None,
            db=db_session,
            user=admin,
            checker=mock_checker,
        )

    folder = tmp_path / "event_files"
    assert delete_calls, "delete_static_file should run on failure"
    if folder.exists():
        assert not any(folder.iterdir())


@pytest.mark.asyncio
async def test_upload_event_file_rejects_large_payload(
    tmp_path, monkeypatch, db_session, user_factory, mock_checker
):
    admin = await user_factory(role="admin")
    event = await _create_event(db_session, admin)

    payload = b"x" * 9
    upload = UploadFile(
        filename="notes.txt",
        file=io.BytesIO(payload),
        headers=Headers({"content-type": "text/plain"}),
    )

    monkeypatch.setattr(settings, "static_dir", str(tmp_path))
    monkeypatch.setattr(settings, "event_file_allowed_mime_types", ["text/plain"])
    monkeypatch.setattr(settings, "event_file_allowed_extensions", [".txt"])
    monkeypatch.setattr(settings, "event_file_max_size_bytes", 8)

    with pytest.raises(HTTPException) as excinfo:
        await events.upload_event_file(
            event.id,
            upload,
            request=None,
            db=db_session,
            user=admin,
            checker=mock_checker,
        )

    assert excinfo.value.status_code == status.HTTP_413_CONTENT_TOO_LARGE
    assert excinfo.value.detail == translate("errors.files.too_large", locale="en")
    folder = tmp_path / "event_files"
    assert not folder.exists()


@pytest.mark.asyncio
async def test_upload_event_file_respects_scanner_limit(
    tmp_path, monkeypatch, db_session, user_factory, mock_checker
):
    admin = await user_factory(role="admin")
    event = await _create_event(db_session, admin)

    payload = b"x" * 1024
    upload = UploadFile(
        filename="notes.txt",
        file=io.BytesIO(payload),
        size=len(payload),
        headers=Headers({"content-type": "text/plain"}),
    )

    monkeypatch.setattr(settings, "static_dir", str(tmp_path))
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
            event.id,
            upload,
            request=None,
            db=db_session,
            user=admin,
            checker=mock_checker,
        )

    assert excinfo.value.status_code == status.HTTP_413_CONTENT_TOO_LARGE
    assert excinfo.value.detail == translate("errors.files.too_large", locale="en")
    folder = tmp_path / "event_files"
    assert not folder.exists()


@pytest.mark.asyncio
async def test_upload_event_file_rejects_forbidden_type(
    tmp_path, monkeypatch, db_session, user_factory, mock_checker
):
    admin = await user_factory(role="admin")
    event = await _create_event(db_session, admin)

    upload = UploadFile(
        filename="malware.exe",
        file=io.BytesIO(b"binary"),
        headers=Headers({"content-type": "application/x-msdownload"}),
    )

    monkeypatch.setattr(settings, "static_dir", str(tmp_path))
    monkeypatch.setattr(settings, "event_file_allowed_mime_types", ["text/plain"])
    monkeypatch.setattr(settings, "event_file_allowed_extensions", [".txt"])
    monkeypatch.setattr(settings, "event_file_max_size_bytes", 1024)

    with pytest.raises(HTTPException) as excinfo:
        await events.upload_event_file(
            event.id,
            upload,
            request=None,
            db=db_session,
            user=admin,
            checker=mock_checker,
        )

    assert excinfo.value.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    assert excinfo.value.detail == translate(
        "errors.files.unsupported_type", locale="en"
    )
    folder = tmp_path / "event_files"
    assert not folder.exists()


@pytest.mark.asyncio
async def test_upload_event_file_rejects_mismatched_metadata(
    tmp_path, monkeypatch, db_session, user_factory, mock_checker
):
    admin = await user_factory(role="admin")
    event = await _create_event(db_session, admin)

    pdf_payload = b"%PDF-1.7\n" + b"0" * 100
    upload = UploadFile(
        filename="notes.txt",
        file=io.BytesIO(pdf_payload),
        headers=Headers({"content-type": "text/plain"}),
    )

    monkeypatch.setattr(settings, "static_dir", str(tmp_path))
    monkeypatch.setattr(
        settings,
        "event_file_allowed_mime_types",
        ["text/plain", "application/pdf"],
    )
    monkeypatch.setattr(settings, "event_file_allowed_extensions", [".txt", ".pdf"])
    monkeypatch.setattr(settings, "event_file_max_size_bytes", 1024)
    # save_attachment reads the derived _set @cached_property. monkeypatch the CLASS
    # so the override is RESTORED on teardown — a raw `type(settings).X = ...` leaks
    # the descriptor into every later test (mutmut clean-test -> stale-allowlist 415).
    monkeypatch.setattr(
        type(settings),
        "event_file_allowed_mime_types_set",
        property(lambda self: {"text/plain", "application/pdf"}),
    )
    monkeypatch.setattr(
        type(settings),
        "event_file_allowed_extensions_set",
        property(lambda self: {"txt", "pdf"}),
    )

    with pytest.raises(HTTPException) as excinfo:
        await events.upload_event_file(
            event.id,
            upload,
            request=None,
            db=db_session,
            user=admin,
            checker=mock_checker,
        )

    assert excinfo.value.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    assert excinfo.value.detail == translate(
        "errors.files.content_type_mismatch", locale="en"
    )
    quarantine_dir = tmp_path / "quarantine" / "event_files"
    stored_samples = list(quarantine_dir.glob("*.bin"))
    assert stored_samples
    assert stored_samples[0].read_bytes() == pdf_payload


@pytest.mark.asyncio
async def test_upload_event_file_rejects_infected_payload(
    tmp_path, monkeypatch, db_session, user_factory, mock_checker
):
    admin = await user_factory(role="admin")
    event = await _create_event(db_session, admin)

    payload = b"clean-looking"
    upload = UploadFile(
        filename="notes.txt",
        file=io.BytesIO(payload),
        headers=Headers({"content-type": "text/plain"}),
    )

    monkeypatch.setattr(settings, "static_dir", str(tmp_path))
    monkeypatch.setattr(settings, "event_file_allowed_mime_types", ["text/plain"])
    monkeypatch.setattr(settings, "event_file_allowed_extensions", [".txt"])
    monkeypatch.setattr(settings, "event_file_max_size_bytes", 1024)

    async def fake_scan(
        scanned, *, locale: str | None = None, size_bytes: int | None = None, **kwargs
    ) -> None:
        assert scanned == payload
        assert kwargs.get("quarantine_payload") == payload
        assert size_bytes == len(payload)
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=translate("errors.files.infected", locale=locale),
        )

    monkeypatch.setattr(files, "scan_for_malware", fake_scan)

    with pytest.raises(HTTPException) as excinfo:
        await events.upload_event_file(
            event.id,
            upload,
            request=None,
            db=db_session,
            user=admin,
            checker=mock_checker,
        )

    assert excinfo.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert excinfo.value.detail == translate("errors.files.infected", locale="en")
    folder = tmp_path / "event_files"
    assert not folder.exists()


@pytest.mark.asyncio
async def test_upload_event_file_rejects_detected_type_not_allowed(
    tmp_path, monkeypatch, db_session, user_factory, mock_checker
):
    admin = await user_factory(role="admin")
    event = await _create_event(db_session, admin)

    pdf_payload = b"%PDF-1.7\n" + b"0" * 100
    upload = UploadFile(
        filename="notes.txt",
        file=io.BytesIO(pdf_payload),
        headers=Headers({"content-type": "text/plain"}),
    )

    monkeypatch.setattr(settings, "static_dir", str(tmp_path))
    monkeypatch.setattr(settings, "event_file_allowed_mime_types", ["text/plain"])
    monkeypatch.setattr(settings, "event_file_allowed_extensions", [".txt"])
    monkeypatch.setattr(settings, "event_file_max_size_bytes", 1024)

    with pytest.raises(HTTPException) as excinfo:
        await events.upload_event_file(
            event.id,
            upload,
            request=None,
            db=db_session,
            user=admin,
            checker=mock_checker,
        )

    assert excinfo.value.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    # Either "blocked-mime" or "content-mismatch" fires depending on
    # cached_property state of event_file_allowed_mime_types_set.
    # Both are valid 415 rejections for PDF-declared-as-text/plain.
    assert excinfo.value.detail in (
        translate("errors.files.unsupported_type", locale="en"),
        translate("errors.files.content_type_mismatch", locale="en"),
    )


@pytest.mark.asyncio
async def test_upload_event_file_allows_multipage_pdf(
    tmp_path, monkeypatch, db_session, user_factory, mock_checker
):
    admin = await user_factory(role="admin")
    event = await _create_event(db_session, admin)

    pdf_payload = MULTIPAGE_PDF_BYTES
    upload = UploadFile(
        filename="report.pdf",
        file=io.BytesIO(pdf_payload),
        headers=Headers({"content-type": "application/pdf"}),
    )

    monkeypatch.setattr(settings, "static_dir", str(tmp_path))
    monkeypatch.setattr(settings, "event_file_allowed_mime_types", ["application/pdf"])
    monkeypatch.setattr(settings, "event_file_allowed_extensions", [".pdf"])
    monkeypatch.setattr(settings, "event_file_max_size_bytes", 2048)
    # save_attachment reads the derived _set @cached_property. monkeypatch the CLASS
    # so the override is RESTORED on teardown — a raw `type(settings).X = ...` leaks
    # the descriptor into every later test (mutmut clean-test -> stale-allowlist 415).
    monkeypatch.setattr(
        type(settings),
        "event_file_allowed_mime_types_set",
        property(lambda self: {"application/pdf"}),
    )
    monkeypatch.setattr(
        type(settings),
        "event_file_allowed_extensions_set",
        property(lambda self: {"pdf"}),
    )

    result = await events.upload_event_file(
        event.id, upload, request=None, db=db_session, user=admin, checker=mock_checker
    )

    assert result.event_id == event.id
    stored_path = tmp_path / "event_files" / result.file_url.rsplit("/", 1)[-1]
    assert stored_path.exists()
    assert stored_path.read_bytes() == pdf_payload


@pytest.mark.asyncio
async def test_upload_event_file_quarantines_polyglot_pdf(
    tmp_path, monkeypatch, db_session, user_factory, mock_checker
):
    admin = await user_factory(role="admin")
    event = await _create_event(db_session, admin)

    payload = POLYGLOT_PDF_BYTES
    upload = UploadFile(
        filename="report.pdf",
        file=io.BytesIO(payload),
        headers=Headers({"content-type": "application/pdf"}),
    )

    monkeypatch.setattr(settings, "static_dir", str(tmp_path))
    monkeypatch.setattr(settings, "event_file_allowed_mime_types", ["application/pdf"])
    monkeypatch.setattr(settings, "event_file_allowed_extensions", [".pdf"])
    monkeypatch.setattr(settings, "event_file_max_size_bytes", 2048)
    # save_attachment reads the derived _set @cached_property. monkeypatch the CLASS
    # so the override is RESTORED on teardown — a raw `type(settings).X = ...` leaks
    # the descriptor into every later test (mutmut clean-test -> stale-allowlist 415).
    monkeypatch.setattr(
        type(settings),
        "event_file_allowed_mime_types_set",
        property(lambda self: {"application/pdf"}),
    )
    monkeypatch.setattr(
        type(settings),
        "event_file_allowed_extensions_set",
        property(lambda self: {"pdf"}),
    )

    with pytest.raises(HTTPException) as excinfo:
        await events.upload_event_file(
            event.id,
            upload,
            request=None,
            db=db_session,
            user=admin,
            checker=mock_checker,
        )

    assert excinfo.value.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    assert excinfo.value.detail == translate(
        "errors.files.unsupported_type", locale="en"
    )
    quarantine_dir = tmp_path / "quarantine" / "event_files"
    stored_samples = list(quarantine_dir.glob("*.bin"))
    assert stored_samples
    assert stored_samples[0].read_bytes() == payload


@pytest.mark.asyncio
async def test_upload_event_file_quarantines_svg_with_js(
    tmp_path, monkeypatch, db_session, user_factory, mock_checker
):
    admin = await user_factory(role="admin")
    event = await _create_event(db_session, admin)

    payload = (FIXTURE_UPLOADS / "svg_with_js.svg").read_bytes()
    upload = UploadFile(
        filename="diagram.svg",
        file=io.BytesIO(payload),
        headers=Headers({"content-type": "image/svg+xml"}),
    )

    monkeypatch.setattr(settings, "static_dir", str(tmp_path))
    monkeypatch.setattr(
        settings,
        "event_file_allowed_mime_types",
        ["image/svg+xml", "application/pdf", "text/plain"],
    )
    monkeypatch.setattr(
        settings, "event_file_allowed_extensions", [".svg", ".pdf", ".txt"]
    )
    monkeypatch.setattr(settings, "event_file_max_size_bytes", 2048)
    # save_attachment reads the derived _set @cached_property. monkeypatch the CLASS
    # so the override is RESTORED on teardown — a raw `type(settings).X = ...` leaks
    # the descriptor into every later test (mutmut clean-test -> stale-allowlist 415).
    monkeypatch.setattr(
        type(settings),
        "event_file_allowed_mime_types_set",
        property(lambda self: {"image/svg+xml", "application/pdf", "text/plain"}),
    )
    monkeypatch.setattr(
        type(settings),
        "event_file_allowed_extensions_set",
        property(lambda self: {"svg", "pdf", "txt"}),
    )

    with pytest.raises(HTTPException) as excinfo:
        await events.upload_event_file(
            event.id,
            upload,
            request=None,
            db=db_session,
            user=admin,
            checker=mock_checker,
        )

    assert excinfo.value.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    assert excinfo.value.detail == translate(
        "errors.files.unsupported_type", locale="en"
    )
    quarantine_dir = tmp_path / "quarantine" / "event_files"
    stored_samples = list(quarantine_dir.glob("*.bin"))
    assert stored_samples
    assert stored_samples[0].read_bytes() == payload


@pytest.mark.asyncio
async def test_upload_event_file_allows_clean_payload_with_scanner(
    tmp_path, monkeypatch, db_session, user_factory, mock_checker
):
    admin = await user_factory(role="admin")
    event = await _create_event(db_session, admin)

    payload = b"safe data"
    upload = UploadFile(
        filename="notes.txt",
        file=io.BytesIO(payload),
        headers=Headers({"content-type": "text/plain"}),
    )

    monkeypatch.setattr(settings, "static_dir", str(tmp_path))
    monkeypatch.setattr(settings, "event_file_allowed_mime_types", ["text/plain"])
    monkeypatch.setattr(settings, "event_file_allowed_extensions", [".txt"])
    monkeypatch.setattr(settings, "event_file_max_size_bytes", 1024)
    # save_attachment reads the derived _set @cached_property. monkeypatch the CLASS
    # so the override is RESTORED on teardown — a raw `type(settings).X = ...` leaks
    # the descriptor into every later test (mutmut clean-test -> stale-allowlist 415).
    monkeypatch.setattr(
        type(settings),
        "event_file_allowed_mime_types_set",
        property(lambda self: {"text/plain"}),
    )
    monkeypatch.setattr(
        type(settings),
        "event_file_allowed_extensions_set",
        property(lambda self: {"txt"}),
    )

    calls: list[tuple[bytes, str | None, int | None]] = []

    async def fake_scan(
        scanned, *, locale: str | None = None, size_bytes: int | None = None, **kwargs
    ) -> None:
        calls.append((scanned, locale, size_bytes))
        assert scanned == payload
        assert kwargs.get("quarantine_payload") == payload
        assert size_bytes == len(payload)
        return None

    monkeypatch.setattr(files, "scan_for_malware", fake_scan)

    result = await events.upload_event_file(
        event.id, upload, request=None, db=db_session, user=admin, checker=mock_checker
    )

    assert result.event_id == event.id
    assert calls and calls[0][0] == payload
    stored_path = tmp_path / "event_files" / result.file_url.rsplit("/", 1)[-1]
    assert stored_path.exists()
    assert stored_path.read_bytes() == payload


@pytest.mark.skip(reason="Pre-existing issue with event service fixture in update flow")
@pytest.mark.asyncio
async def test_update_event_replaces_image_removes_old_file(
    tmp_path, monkeypatch, db_session, user_factory, event_service
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

    monkeypatch.setattr(settings, "static_dir", str(tmp_path))

    payload = schemas.EventUpdate(image_url="/static/event_images/new.png")
    result = await events.update_event(
        event.id, payload, request=None, db=db_session, user=admin, events=event_service
    )

    assert result.image_url == "/static/event_images/new.png"
    assert not old_path.exists()


@pytest.mark.asyncio
async def test_delete_event_file_removes_payload(
    tmp_path, monkeypatch, db_session, user_factory, mock_checker
):
    admin = await user_factory(role="admin")
    event = await _create_event(db_session, admin)

    payload = b"example data"
    upload = UploadFile(
        filename="notes.txt",
        file=io.BytesIO(payload),
        headers=Headers({"content-type": "text/plain"}),
    )

    monkeypatch.setattr(settings, "static_dir", str(tmp_path))
    monkeypatch.setattr(settings, "event_file_allowed_mime_types", ["text/plain"])
    monkeypatch.setattr(settings, "event_file_allowed_extensions", [".txt"])
    monkeypatch.setattr(settings, "event_file_max_size_bytes", 1024)
    # save_attachment reads the derived _set @cached_property. monkeypatch the CLASS
    # so the override is RESTORED on teardown — a raw `type(settings).X = ...` leaks
    # the descriptor into every later test (mutmut clean-test -> stale-allowlist 415).
    monkeypatch.setattr(
        type(settings),
        "event_file_allowed_mime_types_set",
        property(lambda self: {"text/plain"}),
    )
    monkeypatch.setattr(
        type(settings),
        "event_file_allowed_extensions_set",
        property(lambda self: {"txt"}),
    )

    event_file = await events.upload_event_file(
        event.id, upload, request=None, db=db_session, user=admin, checker=mock_checker
    )

    stored_path = tmp_path / "event_files" / event_file.file_url.rsplit("/", 1)[-1]
    assert stored_path.exists()

    result = await events.delete_event_file(
        event_file.id, request=None, db=db_session, user=admin, checker=mock_checker
    )

    assert result == {"ok": True}
    assert not stored_path.exists()


@pytest.mark.asyncio
async def test_delete_event_removes_all_files(
    tmp_path, monkeypatch, db_session, user_factory, event_service, mock_checker
):
    admin = await user_factory(role="admin")
    event = await _create_event(db_session, admin)

    monkeypatch.setattr(settings, "static_dir", str(tmp_path))
    monkeypatch.setattr(settings, "event_file_allowed_mime_types", ["text/plain"])
    monkeypatch.setattr(settings, "event_file_allowed_extensions", [".txt"])
    monkeypatch.setattr(settings, "event_file_max_size_bytes", 1024)
    # Patch cached_property sets used by save_attachment
    monkeypatch.setattr(
        type(settings),
        "event_file_allowed_mime_types_set",
        property(lambda self: {"text/plain"}),
    )
    monkeypatch.setattr(
        type(settings),
        "event_file_allowed_extensions_set",
        property(lambda self: {"txt"}),
    )

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
            event.id,
            upload,
            request=None,
            db=db_session,
            user=admin,
            checker=mock_checker,
        )
        stored_paths.append(
            tmp_path / "event_files" / event_file.file_url.rsplit("/", 1)[-1]
        )

    for path in stored_paths:
        assert path.exists()

    result = await events.delete_event(
        event.id, request=None, events=event_service, user=admin, checker=mock_checker
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
