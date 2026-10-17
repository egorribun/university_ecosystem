from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api import chat as chat_api
from app.api import events as events_api
from app.services.chat.command_service import ChatMessageDispatcher
from tests.conftest import call_injected


def _result(*, scalar: object = None, rows: list[object] | None = None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value = rows or []
    return result


@pytest.mark.asyncio
async def test_chat_attachment_download_authorizes_member_and_reads_storage() -> None:
    chat_id = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4())
    operation_order: list[str] = []
    filename = f"chat_{chat_id}_0123456789abcdef0123456789abcdef.pdf"
    raw_url = f"/static/chat_uploads/{filename}"
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(id=chat_id)

    async def execute(statement: object) -> MagicMock:
        operation_order.append(
            "membership" if len(operation_order) == 0 else "attachment-query"
        )
        if len(operation_order) == 1:
            return _result(scalar=user.id)
        return _result(rows=[SimpleNamespace(url=raw_url, size=len(b"private bytes"))])

    async def set_message_identity(user_id: uuid.UUID) -> None:
        assert user_id == user.id
        operation_order.append("rls-identity")

    db.execute.side_effect = execute
    backend = MagicMock()
    backend.read_file = AsyncMock(return_value=b"private bytes")

    with (
        patch.object(chat_api, "_get_storage_backend", return_value=backend),
        patch.object(
            chat_api.ChatRepository,
            "set_message_rls_user",
            new=AsyncMock(side_effect=set_message_identity),
        ) as set_identity,
    ):
        response = await call_injected(
            chat_api.download_chat_attachment,
            chat_id,
            filename,
            current_user=user,
            locale="en",
            provides={"AsyncDatabaseSession": db},
        )

    assert response.status_code == 200
    assert response.body == b"private bytes"
    assert response.media_type == "application/pdf"
    backend.read_file.assert_awaited_once_with(raw_url, max_bytes=len(b"private bytes"))
    set_identity.assert_awaited_once_with(user.id)
    assert operation_order == ["membership", "rls-identity", "attachment-query"]


@pytest.mark.asyncio
async def test_chat_attachment_download_rejects_storage_key_owned_by_another_chat() -> (
    None
):
    chat_id = uuid.uuid4()
    other_chat_id = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4())
    filename = "report.pdf"
    foreign_url = f"/static/chat_uploads/chat_{other_chat_id}/{filename}"
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(id=chat_id)
    db.execute.side_effect = [
        _result(scalar=user.id),
        _result(rows=[SimpleNamespace(url=foreign_url)]),
    ]
    backend = MagicMock()
    backend.read_file = AsyncMock(return_value=b"foreign chat bytes")

    with (
        patch.object(chat_api, "_get_storage_backend", return_value=backend),
        patch.object(chat_api.ChatRepository, "set_message_rls_user", new=AsyncMock()),
    ):
        with pytest.raises(HTTPException) as denied:
            await call_injected(
                chat_api.download_chat_attachment,
                chat_id,
                filename,
                current_user=user,
                locale="en",
                provides={"AsyncDatabaseSession": db},
            )

    assert denied.value.status_code == 404
    backend.read_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_chat_attachment_download_rejects_storage_size_mismatch() -> None:
    chat_id = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4())
    filename = f"chat_{chat_id}_0123456789abcdef0123456789abcdef.pdf"
    raw_url = f"/static/chat_uploads/{filename}"
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(id=chat_id)
    db.execute.side_effect = [
        _result(scalar=user.id),
        _result(rows=[SimpleNamespace(url=raw_url, size=4)]),
    ]
    backend = MagicMock()
    backend.read_file = AsyncMock(return_value=b"more than four bytes")

    with (
        patch.object(chat_api, "_get_storage_backend", return_value=backend),
        patch.object(chat_api.ChatRepository, "set_message_rls_user", new=AsyncMock()),
    ):
        with pytest.raises(HTTPException) as mismatch:
            await call_injected(
                chat_api.download_chat_attachment,
                chat_id,
                filename,
                current_user=user,
                locale="en",
                provides={"AsyncDatabaseSession": db},
            )

    assert mismatch.value.status_code == 404
    backend.read_file.assert_awaited_once_with(raw_url, max_bytes=4)


@pytest.mark.asyncio
async def test_non_member_upload_is_rejected_before_attachment_processing() -> None:
    chat_id = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4())
    uow = MagicMock()
    uow.chats.get_by_id = AsyncMock(return_value=SimpleNamespace(id=chat_id))
    uow.chats.check_participant = AsyncMock(return_value=False)
    attachment_service = MagicMock()
    attachment_service.process_upload = AsyncMock()
    upload = SimpleNamespace(size=4)
    dispatcher = ChatMessageDispatcher(uow, attachment_service, MagicMock())

    with pytest.raises(HTTPException) as denied:
        await dispatcher.send_message(
            chat_id,
            user,
            "synthetic upload",
            [upload],
            "en",
        )

    assert denied.value.status_code == 403
    uow.chats.check_participant.assert_awaited_once_with(chat_id, user.id)
    attachment_service.process_upload.assert_not_awaited()


@pytest.mark.asyncio
async def test_chat_attachment_download_resolves_same_name_only_within_requested_chat() -> (
    None
):
    chat_id = uuid.uuid4()
    other_chat_id = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4())
    filename = "report.pdf"
    local_url = f"/static/chat_uploads/chat_{chat_id}/{filename}"
    foreign_url = f"/static/chat_uploads/chat_{other_chat_id}/{filename}"
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(id=chat_id)

    async def execute(statement: object) -> MagicMock:
        sql = str(statement)
        if "chat_participants" in sql:
            return _result(scalar=user.id)
        assert "messages.chat_id =" in sql
        compiled = statement.compile()  # type: ignore[union-attr]
        assert chat_id in compiled.params.values()
        # Deliberately include both colliding hierarchical names. The URL owner
        # check must skip the foreign row even if an adapter returns it first.
        return _result(
            rows=[
                SimpleNamespace(url=foreign_url),
                SimpleNamespace(url=local_url, size=len(b"local chat bytes")),
            ]
        )

    db.execute.side_effect = execute
    backend = MagicMock()
    backend.read_file = AsyncMock(return_value=b"local chat bytes")

    with (
        patch.object(chat_api, "_get_storage_backend", return_value=backend),
        patch.object(chat_api.ChatRepository, "set_message_rls_user", new=AsyncMock()),
    ):
        response = await call_injected(
            chat_api.download_chat_attachment,
            chat_id,
            filename,
            current_user=user,
            locale="en",
            provides={"AsyncDatabaseSession": db},
        )

    assert response.status_code == 200
    assert response.body == b"local chat bytes"
    backend.read_file.assert_awaited_once_with(
        local_url, max_bytes=len(b"local chat bytes")
    )


@pytest.mark.asyncio
async def test_chat_attachment_download_denies_non_member_and_missing_values() -> None:
    chat_id = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4())
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(id=chat_id)
    db.execute.return_value = _result(scalar=None)
    with pytest.raises(HTTPException) as denied:
        await call_injected(
            chat_api.download_chat_attachment,
            chat_id,
            "report.pdf",
            current_user=user,
            locale="en",
            provides={"AsyncDatabaseSession": db},
        )
    assert denied.value.status_code == 403

    db.get.return_value = None
    with pytest.raises(HTTPException) as missing_chat:
        await call_injected(
            chat_api.download_chat_attachment,
            chat_id,
            "report.pdf",
            current_user=user,
            locale="en",
            provides={"AsyncDatabaseSession": db},
        )
    assert missing_chat.value.status_code == 404

    with pytest.raises(HTTPException) as invalid:
        await call_injected(
            chat_api.download_chat_attachment,
            chat_id,
            "../secret",
            current_user=user,
            locale="en",
            provides={"AsyncDatabaseSession": db},
        )
    assert invalid.value.status_code == 404


@pytest.mark.asyncio
async def test_chat_attachment_download_handles_missing_attachment_and_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_id = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4())
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(id=chat_id)
    monkeypatch.setattr(
        chat_api.ChatRepository,
        "set_message_rls_user",
        AsyncMock(),
    )
    db.execute.side_effect = [
        _result(scalar=user.id),
        _result(
            rows=[SimpleNamespace(url="/static/chat_uploads/chat_other/other.txt")]
        ),
    ]
    with pytest.raises(HTTPException) as missing:
        await call_injected(
            chat_api.download_chat_attachment,
            chat_id,
            "report.pdf",
            current_user=user,
            locale="en",
            provides={"AsyncDatabaseSession": db},
        )
    assert missing.value.status_code == 404

    filename = f"chat_{chat_id}_0123456789abcdef0123456789abcdef.pdf"
    raw_url = (
        f"/static/chat_uploads/chat_{chat_id}_0123456789abcdef0123456789abcdef.pdf"
    )
    db.execute.side_effect = [
        _result(scalar=user.id),
        _result(rows=[SimpleNamespace(url=raw_url, size=3)]),
    ]
    backend = MagicMock()
    backend.read_file = AsyncMock(side_effect=FileNotFoundError)
    with patch.object(chat_api, "_get_storage_backend", return_value=backend):
        with pytest.raises(HTTPException) as storage_missing:
            await call_injected(
                chat_api.download_chat_attachment,
                chat_id,
                filename,
                current_user=user,
                locale="en",
                provides={"AsyncDatabaseSession": db},
            )
    assert storage_missing.value.status_code == 404


@pytest.mark.parametrize(
    ("storage_url", "filename"),
    [
        ("/static/public/report.pdf", "report.pdf"),
        ("/static/chat_uploads/chat_owner/nested/report.pdf", "report.pdf"),
        ("/static/chat_uploads/chat_owner/other.pdf", "report.pdf"),
    ],
)
def test_chat_attachment_resource_match_rejects_unrecognized_storage_layouts(
    storage_url: str,
    filename: str,
) -> None:
    assert (
        chat_api._chat_attachment_url_matches_resource(
            storage_url,
            uuid.uuid4(),
            filename,
        )
        is False
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("max_size_bytes", "stored_size"),
    [(0, 1), (4, -1), (4, 5)],
)
async def test_chat_attachment_download_rejects_unsafe_stored_sizes_before_storage(
    monkeypatch: pytest.MonkeyPatch,
    max_size_bytes: int,
    stored_size: int,
) -> None:
    chat_id = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4())
    filename = f"chat_{chat_id}_0123456789abcdef0123456789abcdef.pdf"
    raw_url = f"/static/chat_uploads/{filename}"
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(id=chat_id)
    db.execute.side_effect = [
        _result(scalar=user.id),
        _result(rows=[SimpleNamespace(url=raw_url, size=stored_size)]),
    ]
    backend = MagicMock()
    backend.read_file = AsyncMock(return_value=b"must not be read")
    monkeypatch.setattr(
        chat_api.settings,
        "chat_attachment_max_size_bytes",
        max_size_bytes,
    )

    with (
        patch.object(chat_api, "_get_storage_backend", return_value=backend),
        patch.object(
            chat_api.ChatRepository,
            "set_message_rls_user",
            new=AsyncMock(),
        ),
    ):
        with pytest.raises(HTTPException) as rejected:
            await call_injected(
                chat_api.download_chat_attachment,
                chat_id,
                filename,
                current_user=user,
                locale="en",
                provides={"AsyncDatabaseSession": db},
            )

    assert rejected.value.status_code == 404
    backend.read_file.assert_not_awaited()


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
        response = await call_injected(
            events_api.download_event_file,
            event_id,
            filename,
            request=SimpleNamespace(),
            user=user,
            checker=checker,
            provides={"AsyncDatabaseSession": db},
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
            await call_injected(
                events_api.download_event_file,
                event_id,
                filename,
                request=SimpleNamespace(),
                user=user,
                checker=checker,
                provides={"AsyncDatabaseSession": db},
            )
    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_event_file_download_rejects_storage_key_owned_by_another_event() -> None:
    event_id = uuid.uuid4()
    other_event_id = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4(), role="student")
    event = SimpleNamespace(id=event_id)
    foreign_url = f"/static/event_files/event_{other_event_id}/agenda.pdf"
    db = AsyncMock()
    db.get.return_value = event
    checker = MagicMock()
    checker.check_permission = AsyncMock(return_value=True)
    backend = MagicMock()
    backend.read_file = AsyncMock(return_value=b"foreign event bytes")

    with (
        patch.object(
            events_api.EventRepository,
            "get_event_files",
            new=AsyncMock(return_value=[SimpleNamespace(file_url=foreign_url)]),
        ),
        patch.object(events_api, "_get_storage_backend", return_value=backend),
        patch.object(events_api, "resolve_locale", return_value="en"),
    ):
        with pytest.raises(HTTPException) as denied:
            await call_injected(
                events_api.download_event_file,
                event_id,
                "agenda.pdf",
                request=SimpleNamespace(),
                user=user,
                checker=checker,
                provides={"AsyncDatabaseSession": db},
            )

    assert denied.value.status_code == 404
    checker.check_permission.assert_awaited_once_with(
        resource_type="event",
        resource_id=str(event_id),
        permission="view",
        user_id=str(user.id),
    )
    backend.read_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_event_file_download_resolves_same_name_only_within_requested_event() -> (
    None
):
    event_id = uuid.uuid4()
    other_event_id = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4(), role="student")
    event = SimpleNamespace(id=event_id)
    filename = "agenda.pdf"
    local_url = f"/static/event_files/event_{event_id}/{filename}"
    foreign_url = f"/static/event_files/event_{other_event_id}/{filename}"
    db = AsyncMock()
    db.get.return_value = event
    checker = MagicMock()
    checker.check_permission = AsyncMock(return_value=True)
    backend = MagicMock()
    backend.read_file = AsyncMock(return_value=b"local event bytes")

    with (
        patch.object(
            events_api.EventRepository,
            "get_event_files",
            new=AsyncMock(
                return_value=[
                    SimpleNamespace(file_url=foreign_url),
                    SimpleNamespace(file_url=local_url),
                ]
            ),
        ) as get_event_files,
        patch.object(events_api, "_get_storage_backend", return_value=backend),
        patch.object(events_api, "resolve_locale", return_value="en"),
    ):
        response = await call_injected(
            events_api.download_event_file,
            event_id,
            filename,
            request=SimpleNamespace(),
            user=user,
            checker=checker,
            provides={"AsyncDatabaseSession": db},
        )

    assert response.status_code == 200
    assert response.body == b"local event bytes"
    get_event_files.assert_awaited_once_with(event_id)
    backend.read_file.assert_awaited_once_with(local_url)


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
            await call_injected(
                events_api.download_event_file,
                event_id,
                "agenda.pdf",
                request=SimpleNamespace(),
                user=user,
                checker=checker,
                provides={"AsyncDatabaseSession": db},
            )
    assert missing_event.value.status_code == 404
    checker.check_permission.assert_not_awaited()

    with patch.object(events_api, "resolve_locale", return_value="en"):
        with pytest.raises(HTTPException) as invalid:
            await call_injected(
                events_api.download_event_file,
                event_id,
                "../agenda.pdf",
                request=SimpleNamespace(),
                user=user,
                checker=checker,
                provides={"AsyncDatabaseSession": db},
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
            await call_injected(
                events_api.download_event_file,
                event_id,
                "agenda.pdf",
                request=SimpleNamespace(),
                user=user,
                checker=checker,
                provides={"AsyncDatabaseSession": db},
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
            await call_injected(
                events_api.download_event_file,
                event_id,
                matching_name,
                request=SimpleNamespace(),
                user=user,
                checker=checker,
                provides={"AsyncDatabaseSession": db},
            )
    assert storage_missing.value.status_code == 404
