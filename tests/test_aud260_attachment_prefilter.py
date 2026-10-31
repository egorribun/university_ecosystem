from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import Select
from sqlalchemy.dialects import postgresql

from app.api import chat as chat_api
from app.models.chat import Attachment, Chat, Message
from tests.conftest import call_injected


async def _prepare_attachment_rows(db_session, user_factory, order):
    member = await user_factory()
    chat = Chat(participants=[member])
    db_session.add(chat)
    await db_session.flush()
    message = Message(chat_id=chat.id, sender_id=member.id, content="attachment")
    db_session.add(message)
    await db_session.flush()
    filename = "report.pdf"
    key_path = f"/chat_uploads/chat_{chat.id}/{filename}"
    canonical_url = f"https://objects.example{key_path}"
    urls = {
        "query_decoy": f"https://objects.example/unrelated?redirect={key_path}",
        "fragment_decoy": f"https://objects.example/unrelated#redirect={key_path}",
        "authority_decoy": f"https://chat_uploads/chat_{chat.id}/{filename}",
        "matching": f"{canonical_url}?download=1",
    }
    for kind in order:
        db_session.add(
            Attachment(
                message_id=message.id,
                url=urls[kind],
                file_type="file",
                filename=filename,
                size=5,
            )
        )
    await db_session.commit()
    return member, chat, filename, canonical_url


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "decoys",
    [
        ("query_decoy", "fragment_decoy"),
        ("authority_decoy", "authority_decoy"),
    ],
    ids=["query-and-fragment", "authority"],
)
async def test_url_decoys_do_not_hide_a_live_attachment(
    db_session, user_factory, monkeypatch, decoys
) -> None:
    member, chat, filename, canonical_url = await _prepare_attachment_rows(
        db_session, user_factory, [*decoys, "matching"]
    )
    storage = SimpleNamespace(read_file=AsyncMock(return_value=b"bytes"))
    monkeypatch.setattr(chat_api, "_get_storage_backend", lambda: storage)
    statements = []
    execute = db_session.execute

    async def record_execute(statement, *args, **kwargs):
        if isinstance(statement, Select) and any(
            column.get("entity") is Attachment
            for column in statement.column_descriptions
        ):
            statements.append(statement)
        return await execute(statement, *args, **kwargs)

    monkeypatch.setattr(db_session, "execute", record_execute)

    response = await call_injected(
        chat_api.download_chat_attachment,
        chat.id,
        filename,
        current_user=member,
        locale="en",
        provides={"AsyncDatabaseSession": db_session},
    )

    assert response.body == b"bytes"
    storage.read_file.assert_awaited_once_with(canonical_url, max_bytes=5)
    assert len(statements) == 1
    compiled = statements[0].compile(dialect=postgresql.dialect())
    assert " ~ " in compiled.string
    assert "LIMIT" in compiled.string
    assert 2 in compiled.params.values()


@pytest.mark.asyncio
async def test_query_decoy_cannot_hide_duplicate_live_storage_keys(
    db_session, user_factory, monkeypatch
) -> None:
    member, chat, filename, _canonical_url = await _prepare_attachment_rows(
        db_session, user_factory, ["query_decoy", "matching", "matching"]
    )
    storage = SimpleNamespace(read_file=AsyncMock(return_value=b"bytes"))
    monkeypatch.setattr(chat_api, "_get_storage_backend", lambda: storage)

    with pytest.raises(HTTPException) as denied:
        await call_injected(
            chat_api.download_chat_attachment,
            chat.id,
            filename,
            current_user=member,
            locale="en",
            provides={"AsyncDatabaseSession": db_session},
        )

    assert denied.value.status_code == 404
    storage.read_file.assert_not_awaited()
