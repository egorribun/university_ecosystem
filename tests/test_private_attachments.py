from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.api.ws.serializers import serialize_message
from app.core import static as static_module
from app.core.static import PublicStaticFiles, is_private_static_path
from app.schemas.chat import AttachmentResponse, MessageResponse
from app.schemas.schemas import EventFileOut
from app.services.private_attachments import (
    is_private_attachment_path,
    private_attachment_filename,
    private_attachment_response,
    private_attachment_storage_key,
    private_attachment_url,
)


def test_private_attachment_urls_cover_local_s3_and_legacy_values() -> None:
    chat_id = uuid4()
    event_id = uuid4()
    chat_flat = (
        f"/static/chat_uploads/chat_{chat_id}_0123456789abcdef0123456789abcdef.pdf"
    )
    event_flat = (
        f"https://cdn.example/event_files/event_{event_id}_"
        "fedcba9876543210fedcba9876543210.docx"
    )
    chat_flat_name = chat_flat.rsplit("/", 1)[-1]
    event_flat_name = event_flat.rsplit("/", 1)[-1]
    assert private_attachment_filename(chat_flat, "chat") == chat_flat_name
    assert (
        private_attachment_url("chat", chat_id, chat_flat)
        == f"/api/v1/chats/{chat_id}/attachments/{chat_flat_name}"
    )
    assert private_attachment_filename(event_flat, "event") == event_flat_name
    assert (
        private_attachment_filename(
            f"/static/chat_uploads/chat_{chat_id}/report.pdf", "chat"
        )
        == "report.pdf"
    )
    assert (
        private_attachment_filename(
            f"https://cdn.example/event_files/event_{event_id}/agenda.docx?download=1",
            "event",
        )
        == "agenda.docx"
    )
    assert (
        private_attachment_url(
            "chat", chat_id, f"/static/chat_uploads/chat_{chat_id}/report.pdf"
        )
        == f"/api/v1/chats/{chat_id}/attachments/report.pdf"
    )
    assert (
        private_attachment_url(
            "event",
            event_id,
            f"https://cdn.example/event_files/event_{event_id}/agenda.docx",
        )
        == f"/api/v1/events/{event_id}/files/agenda.docx"
    )
    assert private_attachment_url("chat", chat_id, "/static/avatars/avatar.png") == (
        "/static/avatars/avatar.png"
    )
    assert (
        private_attachment_url(
            "chat", chat_id, f"/api/v1/chats/{chat_id}/attachments/report.pdf"
        )
        == f"/api/v1/chats/{chat_id}/attachments/report.pdf"
    )
    assert (
        private_attachment_url(
            "chat", chat_id, f"/static/event_files/event_{event_id}/agenda.docx"
        )
        == ""
    )
    assert is_private_attachment_path("chat_uploads/chat_id/report.pdf")
    assert is_private_attachment_path("%2563hat_uploads%2Fchat_id%2Freport.pdf")
    assert not is_private_attachment_path("avatars/avatar.png")


def test_private_attachment_helpers_fail_closed_for_invalid_paths() -> None:
    attachment_id = uuid4()
    assert private_attachment_filename("", "chat") is None
    assert (
        private_attachment_filename(
            f"/static/chat_uploads/chat_{attachment_id}/bad%2Fname.pdf", "chat"
        )
        is None
    )
    assert (
        private_attachment_filename(
            f"/static/chat_uploads/other_{attachment_id}/file.pdf", "chat"
        )
        is None
    )
    # A flat key under the protected prefix must match the generated-key
    # contract; otherwise it must not be exposed as a downloadable filename.
    assert (
        private_attachment_filename(
            "/static/chat_uploads/not-a-valid-flat-name.pdf", "chat"
        )
        is None
    )
    # The hierarchical compatibility path must reject an invalid resource id
    # instead of treating a user-controlled key as a valid private attachment.
    assert (
        private_attachment_filename("/static/chat_uploads/chat_bad!id/file.pdf", "chat")
        is None
    )
    assert (
        private_attachment_filename(
            f"/static/chat_uploads/chat_{attachment_id}/bad file.pdf", "chat"
        )
        is None
    )
    assert (
        private_attachment_url(
            "event", attachment_id, "/static/event_files/event_id/../../secret"
        )
        == ""
    )
    with pytest.raises(ValueError):
        private_attachment_url(
            "chat", "../escape", "/static/chat_uploads/chat_x/file.txt"
        )
    assert private_attachment_storage_key("chat", attachment_id, "file.txt") == (
        f"chat_uploads/chat_{attachment_id}/file.txt"
    )
    assert private_attachment_storage_key("event", 42, "agenda.pdf") == (
        "event_files/event_42/agenda.pdf"
    )
    with pytest.raises(ValueError, match=r"^Invalid attachment filename$"):
        private_attachment_storage_key("chat", "x", "../file.txt")
    for resource_id, filename in (
        ("../x", "file.txt"),
        (".", "file.txt"),
        ("x", "../file.txt"),
        ("x", ""),
        ("x", "a/b"),
    ):
        with pytest.raises(ValueError):
            private_attachment_storage_key("chat", resource_id, filename)


def test_private_attachment_response_headers_cover_mime_fallback() -> None:
    pdf = private_attachment_response(b"pdf", "report.pdf")
    assert pdf.media_type == "application/pdf"
    assert pdf.headers["cache-control"] == "private, no-store"
    assert pdf.headers["content-disposition"] == 'inline; filename="report.pdf"'
    assert pdf.headers["x-content-type-options"] == "nosniff"
    binary = private_attachment_response(b"bytes", "archive.unknownextension")
    assert binary.media_type == "application/octet-stream"


def test_static_private_path_selector_and_blocked_response() -> None:
    assert is_private_static_path("/static/chat_uploads/chat_x/file.txt")
    assert is_private_static_path(r"chat_uploads\chat_x\file.txt")
    assert is_private_static_path("event_files/event_x/file.txt")
    assert is_private_static_path("/static/%2563hat_uploads/chat_x/file.txt")
    assert is_private_static_path("foo/../chat_uploads/chat_x/file.txt")
    assert is_private_static_path("/static/foo/%252e%252e/event_files/event_x/file.txt")
    # Only leading slashes are ignored; arbitrary leading ``X`` characters
    # must not be stripped as a side effect of path normalization.
    assert not is_private_static_path("Xchat_uploads/chat_x/file.txt")
    assert not is_private_static_path("/static/avatars/avatar.png")

    static = PublicStaticFiles(directory=".")
    response = __import__("asyncio").run(
        static.get_response("chat_uploads/chat_x/file.txt", {"type": "http"})
    )
    assert response.status_code == 404
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_private_static_response_uses_canonical_security_header_names(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_response(*, status_code: int, headers: dict[str, str]):
        captured["status_code"] = status_code
        captured["headers"] = headers
        return object()

    monkeypatch.setattr(static_module, "Response", fake_response)
    response = __import__("asyncio").run(
        PublicStaticFiles(directory=".").get_response(
            "chat_uploads/chat_x/file.txt", {"type": "http"}
        )
    )

    assert response is not None
    assert captured == {
        "status_code": 404,
        "headers": {
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    }


def test_public_static_files_delegate_to_starlette(tmp_path) -> None:
    public_file = tmp_path / "public.txt"
    public_file.write_text("public", encoding="utf-8")
    static = PublicStaticFiles(directory=str(tmp_path))

    response = __import__("asyncio").run(
        static.get_response(
            "public.txt",
            {"type": "http", "method": "GET", "path": "/public.txt", "headers": []},
        )
    )

    assert response.status_code == 200
    assert response.headers["content-length"] == "6"
    assert response.path == str(public_file)


def test_uuid_type_is_supported_without_string_coercion() -> None:
    value = UUID(str(uuid4()))
    assert private_attachment_storage_key("chat", value, "x.bin").startswith(
        "chat_uploads/chat_"
    )


def test_rest_and_websocket_serializers_publish_private_api_urls() -> None:
    chat_id = uuid4()
    message_id = uuid4()
    attachment_id = uuid4()
    raw_url = f"/static/chat_uploads/chat_{chat_id}/photo.png"
    attachment = AttachmentResponse(
        id=attachment_id,
        url=raw_url,
        file_type="image",
        filename="photo.png",
        size=3,
    )
    response = MessageResponse(
        id=message_id,
        chat_id=chat_id,
        sender_id=uuid4(),
        content="hello",
        created_at=datetime.now(),
        read_status=False,
        attachments=[attachment],
    )
    expected = f"/api/v1/chats/{chat_id}/attachments/photo.png"
    assert response.attachments[0].url == expected

    orm_message = SimpleNamespace(
        id=message_id,
        chat_id=chat_id,
        sender_id=response.sender_id,
        content="hello",
        created_at=datetime.now(),
        read_status=False,
        read_at=None,
        edited_at=None,
        deleted_at=None,
        sender=None,
        attachments=[
            SimpleNamespace(
                id=attachment_id,
                url=raw_url,
                file_type="image",
                filename="photo.png",
                size=3,
            )
        ],
        forwarded_from_name=None,
    )
    wire = serialize_message(orm_message)
    assert wire["attachments"][0]["url"] == expected

    event_file = EventFileOut(
        id=uuid4(),
        event_id=chat_id,
        file_url=f"/static/event_files/event_{chat_id}/agenda.pdf",
    )
    assert event_file.file_url == f"/api/v1/events/{chat_id}/files/agenda.pdf"
