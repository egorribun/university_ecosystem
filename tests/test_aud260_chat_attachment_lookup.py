from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy import Select

from app.api import chat as chat_api
from app.models.chat import Attachment, Chat, Message
from app.services.storage import StaticFSStorage
from tests.conftest import call_injected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("legacy_layout", "url_suffix"),
    [
        ("flat", ""),
        ("flat", "?signature=legacy-token"),
        ("flat", "#preview"),
        ("hierarchical", ""),
        ("hierarchical", "?signature=legacy-token"),
        ("hierarchical", "#preview"),
    ],
)
async def test_attachment_lookup_targets_legacy_key_before_bounded_fetch(
    db_session,
    user_factory,
    monkeypatch,
    tmp_path,
    legacy_layout: str,
    url_suffix: str,
) -> None:
    member = await user_factory()
    outsider = await user_factory()
    chat = Chat(participants=[member])
    foreign_chat = Chat(participants=[outsider])
    db_session.add_all([chat, foreign_chat])
    await db_session.flush()

    live_message = Message(chat_id=chat.id, sender_id=member.id, content="live")
    deleted_message = Message(
        chat_id=chat.id,
        sender_id=member.id,
        content="",
        deleted_at=datetime.now(UTC),
    )
    foreign_message = Message(
        chat_id=foreign_chat.id, sender_id=outsider.id, content="foreign"
    )
    db_session.add_all([live_message, deleted_message, foreign_message])
    await db_session.flush()

    if legacy_layout == "flat":
        filename = f"chat_{chat.id}_0123456789abcdef0123456789abcdef.pdf"
        key_path = f"chat_uploads/{filename}"
    else:
        filename = "legacy-report.pdf"
        key_path = f"chat_uploads/chat_{chat.id}/{filename}"
    storage = _RecordingStaticFSStorage(
        tmp_path, base_url="https://objects.example/prefix"
    )
    canonical_storage_url = await storage.save_file(key_path, b"target bytes")
    storage_url = f"{canonical_storage_url}{url_suffix}"

    # These same-chat rows are deliberately unrelated to the requested key.
    decoys = [
        Attachment(
            message_id=live_message.id,
            url=(
                "https://objects.example/prefix/chat_uploads/"
                f"chat_{chat.id}/decoy-{index}.txt"
            ),
            file_type="file",
            filename=f"decoy-{index}.txt",
            size=1,
        )
        for index in range(64)
    ]
    db_session.add_all(
        [
            *decoys,
            Attachment(
                message_id=live_message.id,
                url=storage_url,
                file_type="file",
                filename="requested.pdf",
                size=len(b"target bytes"),
            ),
            Attachment(
                message_id=deleted_message.id,
                url=storage_url,
                file_type="file",
                filename="deleted duplicate.pdf",
                size=len(b"deleted bytes"),
            ),
            Attachment(
                message_id=foreign_message.id,
                url=storage_url,
                file_type="file",
                filename="foreign duplicate.pdf",
                size=len(b"foreign bytes"),
            ),
        ]
    )
    await db_session.commit()

    attachment_selects: list[Select[Any]] = []
    execute = db_session.execute

    async def _record_execute(statement, *args, **kwargs):
        if isinstance(statement, Select) and any(
            description.get("entity") is Attachment
            for description in statement.column_descriptions
        ):
            attachment_selects.append(statement)
        return await execute(statement, *args, **kwargs)

    monkeypatch.setattr(db_session, "execute", _record_execute)
    monkeypatch.setattr(chat_api, "_get_storage_backend", lambda: storage)

    response = await call_injected(
        chat_api.download_chat_attachment,
        chat.id,
        filename,
        current_user=member,
        locale="en",
        provides={"AsyncDatabaseSession": db_session},
    )

    assert response.status_code == 200
    assert response.body == b"target bytes"
    assert storage.read_urls == [canonical_storage_url]
    assert len(attachment_selects) == 1
    compiled = attachment_selects[0].compile(dialect=db_session.get_bind().dialect)
    assert "LIMIT" in compiled.string.upper()
    assert 2 in compiled.params.values()
    bound_values = [str(value) for value in compiled.params.values()]
    expected_key_path = (
        f"chat_uploads/{filename}"
        if legacy_layout == "flat"
        else f"chat_uploads/chat_{chat.id}/{filename}"
    )
    expected_escaped_pattern = f"%/{expected_key_path}".replace("_", "!_")
    assert any(value.startswith(expected_escaped_pattern) for value in bound_values)
    assert any(str(chat.id) in value for value in bound_values)


class _RecordingStaticFSStorage(StaticFSStorage):
    def __init__(self, base_dir: Path, base_url: str = "/static") -> None:
        super().__init__(base_dir, base_url=base_url)
        self.read_urls: list[str] = []

    async def read_file(
        self, file_url_or_path: str, *, max_bytes: int | None = None
    ) -> bytes:
        self.read_urls.append(file_url_or_path)
        return await super().read_file(file_url_or_path, max_bytes=max_bytes)


@pytest.mark.asyncio
async def test_attachment_lookup_rejects_ambiguous_live_storage_key(
    monkeypatch,
) -> None:
    chat_id = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4())
    filename = f"chat_{chat_id}_0123456789abcdef0123456789abcdef.pdf"
    storage_url = f"https://objects.example/chat_uploads/{filename}"
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(id=chat_id)
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = user.id
    attachment_result = MagicMock()
    attachment_result.scalars.return_value = [
        SimpleNamespace(url=storage_url, size=5),
        SimpleNamespace(url=storage_url, size=5),
    ]
    db.execute.side_effect = [member_result, attachment_result]
    storage = SimpleNamespace(read_file=AsyncMock(return_value=b"bytes"))
    monkeypatch.setattr(chat_api, "_get_storage_backend", lambda: storage)
    monkeypatch.setattr(chat_api.ChatRepository, "set_message_rls_user", AsyncMock())

    with pytest.raises(HTTPException) as ambiguous:
        await call_injected(
            chat_api.download_chat_attachment,
            chat_id,
            filename,
            current_user=user,
            locale="en",
            provides={"AsyncDatabaseSession": db},
        )

    assert ambiguous.value.status_code == 404
    storage.read_file.assert_not_awaited()
