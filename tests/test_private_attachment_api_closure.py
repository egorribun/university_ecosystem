from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api import chat as chat_api
from app.api import events as events_api


def _result(*, scalar: object = None, rows: list[object] | None = None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value = rows or []
    return result


@pytest.mark.asyncio
async def test_chat_attachment_download_authorizes_member_and_reads_storage() -> None:
    chat_id = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4())
    filename = f"chat_{chat_id}_0123456789abcdef0123456789abcdef.pdf"
    raw_url = f"/static/chat_uploads/{filename}"
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(id=chat_id)
    db.execute.side_effect = [
        _result(scalar=user.id),
        _result(rows=[SimpleNamespace(url=raw_url)]),
    ]
    backend = MagicMock()
    backend.read_file = AsyncMock(return_value=b"private bytes")

    with patch.object(chat_api, "_get_storage_backend", return_value=backend):
        response = await chat_api.download_chat_attachment(
            chat_id, filename, user, "en", db
        )

    assert response.status_code == 200
    assert response.body == b"private bytes"
    assert response.media_type == "application/pdf"
    backend.read_file.assert_awaited_once_with(raw_url)


@pytest.mark.asyncio
async def test_chat_attachment_download_denies_non_member_and_missing_values() -> None:
    chat_id = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4())
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(id=chat_id)
    db.execute.return_value = _result(scalar=None)
    with pytest.raises(HTTPException) as denied:
        await chat_api.download_chat_attachment(chat_id, "report.pdf", user, "en", db)
    assert denied.value.status_code == 403

    db.get.return_value = None
    with pytest.raises(HTTPException) as missing_chat:
        await chat_api.download_chat_attachment(chat_id, "report.pdf", user, "en", db)
    assert missing_chat.value.status_code == 404

    with pytest.raises(HTTPException) as invalid:
        await chat_api.download_chat_attachment(chat_id, "../secret", user, "en", db)
    assert invalid.value.status_code == 404


@pytest.mark.asyncio
async def test_chat_attachment_download_handles_missing_attachment_and_storage() -> (
    None
):
    chat_id = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4())
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(id=chat_id)
    db.execute.side_effect = [
        _result(scalar=user.id),
        _result(
            rows=[SimpleNamespace(url="/static/chat_uploads/chat_other/other.txt")]
        ),
    ]
    with pytest.raises(HTTPException) as missing:
        await chat_api.download_chat_attachment(chat_id, "report.pdf", user, "en", db)
    assert missing.value.status_code == 404

    filename = f"chat_{chat_id}_0123456789abcdef0123456789abcdef.pdf"
    raw_url = (
        f"/static/chat_uploads/chat_{chat_id}_0123456789abcdef0123456789abcdef.pdf"
    )
    db.execute.side_effect = [
        _result(scalar=user.id),
        _result(rows=[SimpleNamespace(url=raw_url)]),
    ]
    backend = MagicMock()
    backend.read_file = AsyncMock(side_effect=FileNotFoundError)
    with patch.object(chat_api, "_get_storage_backend", return_value=backend):
        with pytest.raises(HTTPException) as storage_missing:
            await chat_api.download_chat_attachment(chat_id, filename, user, "en", db)
    assert storage_missing.value.status_code == 404


@pytest.mark.asyncio
async def test_event_file_download_authorizes_viewer_and_handles_denial() -> None:
    event_id = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4(), role="student")
    filename = f"event_{event_id}_0123456789abcdef0123456789abcdef.pdf"
    raw_url = f"/static/event_files/{filename}"
    event = SimpleNamespace(id=event_id)
    db = AsyncMock()
    db.get.return_value = event
    checker = MagicMock()
    checker.check_permission = AsyncMock(return_value=True)
    repo_files = [SimpleNamespace(file_url=raw_url)]
    backend = MagicMock()
    backend.read_file = AsyncMock(return_value=b"event bytes")

    with (
        patch.object(
            events_api.EventRepository,
            "get_event_files",
            new=AsyncMock(return_value=repo_files),
        ),
        patch.object(events_api, "_get_storage_backend", return_value=backend),
        patch.object(events_api, "resolve_locale", return_value="en"),
    ):
        response = await events_api.download_event_file(
            event_id,
            filename,
            request=SimpleNamespace(),
            db=db,
            user=user,
            checker=checker,
        )
    assert response.body == b"event bytes"
    checker.check_permission.assert_awaited_once_with(
        resource_type="event",
        resource_id=str(event_id),
        permission="view",
        user_id=str(user.id),
    )

    checker.check_permission = AsyncMock(return_value=False)
    with patch.object(events_api, "resolve_locale", return_value="en"):
        with pytest.raises(HTTPException) as denied:
            await events_api.download_event_file(
                event_id,
                filename,
                request=SimpleNamespace(),
                db=db,
                user=user,
                checker=checker,
            )
    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_event_file_download_missing_parent_file_storage_and_id() -> None:
    event_id = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4(), role="student")
    checker = MagicMock()
    checker.check_permission = AsyncMock(return_value=True)
    db = AsyncMock()
    db.get.return_value = None
    with patch.object(events_api, "resolve_locale", return_value="en"):
        with pytest.raises(HTTPException) as missing_event:
            await events_api.download_event_file(
                event_id,
                "agenda.pdf",
                request=SimpleNamespace(),
                db=db,
                user=user,
                checker=checker,
            )
    assert missing_event.value.status_code == 404
    checker.check_permission.assert_not_awaited()

    with patch.object(events_api, "resolve_locale", return_value="en"):
        with pytest.raises(HTTPException) as invalid:
            await events_api.download_event_file(
                event_id,
                "../agenda.pdf",
                request=SimpleNamespace(),
                db=db,
                user=user,
                checker=checker,
            )
    assert invalid.value.status_code == 404

    db.get.return_value = SimpleNamespace(id=event_id)
    files = [SimpleNamespace(file_url="/static/event_files/event_other/other.pdf")]
    with (
        patch.object(events_api, "resolve_locale", return_value="en"),
        patch.object(
            events_api.EventRepository,
            "get_event_files",
            new=AsyncMock(return_value=files),
        ),
    ):
        with pytest.raises(HTTPException) as missing_file:
            await events_api.download_event_file(
                event_id,
                "agenda.pdf",
                request=SimpleNamespace(),
                db=db,
                user=user,
                checker=checker,
            )
    assert missing_file.value.status_code == 404

    # A matching private key whose backing object disappeared must map to the
    # same non-enumerating 404 contract as an unknown attachment.
    matching_name = f"event_{event_id}_0123456789abcdef0123456789abcdef.pdf"
    matching_url = f"/static/event_files/{matching_name}"
    db.execute = AsyncMock()
    with (
        patch.object(events_api, "resolve_locale", return_value="en"),
        patch.object(
            events_api.EventRepository,
            "get_event_files",
            new=AsyncMock(return_value=[SimpleNamespace(file_url=matching_url)]),
        ),
        patch.object(
            events_api,
            "_get_storage_backend",
            return_value=SimpleNamespace(
                read_file=AsyncMock(side_effect=FileNotFoundError)
            ),
        ),
    ):
        with pytest.raises(HTTPException) as storage_missing:
            await events_api.download_event_file(
                event_id,
                matching_name,
                request=SimpleNamespace(),
                db=db,
                user=user,
                checker=checker,
            )
    assert storage_missing.value.status_code == 404
