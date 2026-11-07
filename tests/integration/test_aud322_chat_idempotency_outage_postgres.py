"""PostgreSQL settles overlapping same-key sends during a Redis outage."""

from __future__ import annotations

import asyncio
import uuid
from io import BytesIO

import pytest
from fastapi import UploadFile
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.ext.asyncio import AsyncSession

import app.deps.cache as cache_module
import app.services.chat.command_service as command_service
from app.core import database
from app.models import Message, User
from app.repositories.chat_repository import ChatRepository
from tests.integration.test_aud262_receipt_lifecycle_postgres import (
    MemoryUploads,
    _snapshot,
)
from tests.test_aud262_durable_replay_postgres import (
    _WAIT_SECONDS,
    _dispatcher,
    _seed_chat,
)
from tests.test_aud262_durable_replay_postgres import (
    _owned_outbox_listeners as _owned_outbox_listeners,
)
from tests.test_aud262_durable_replay_postgres import (
    pytestmark as pytestmark,
)


async def test_outage_overlapping_writers_commit_one_message_and_clean_loser(
    db_session: AsyncSession, user_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    chat_id, user = await _seed_chat(db_session, user_factory)
    user_id, key = user.id, uuid.uuid4().hex
    storage = MemoryUploads()
    ready, release = asyncio.Event(), asyncio.Event()
    arrived = 0

    async def unavailable():
        raise RedisConnectionError("simulated Redis outage")

    monkeypatch.setattr(cache_module, "get_cache_client", unavailable)
    monkeypatch.setattr(command_service.ws_manager, "is_online", lambda _: False)

    async def writer(label: str):
        nonlocal arrived
        async with AsyncSession(database.engine, expire_on_commit=False) as session:
            bound_user = await session.get(User, user_id)
            assert bound_user is not None
            await ChatRepository(session).set_message_rls_user(user_id)
            sender = _dispatcher(session)
            sender.attachment_service = storage
            real_create = sender.repository.create_message

            async def rendezvous(message: Message):
                nonlocal arrived
                arrived += 1
                if arrived == 2:
                    ready.set()
                await asyncio.wait_for(release.wait(), timeout=_WAIT_SECONDS)
                await real_create(message)

            monkeypatch.setattr(sender.repository, "create_message", rendezvous)
            upload = UploadFile(
                file=BytesIO(label.encode()), filename=f"{label}.txt", size=len(label)
            )
            try:
                return await sender.send_message(
                    chat_id, bound_user, label, [upload], "en", idempotency_key=key
                )
            finally:
                await upload.close()

    tasks = [asyncio.create_task(writer(label)) for label in ("first", "second")]
    try:
        await asyncio.wait_for(ready.wait(), timeout=_WAIT_SECONDS)
        assert len(storage.objects) == 2
        release.set()
        results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=_WAIT_SECONDS)
    finally:
        release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True), timeout=_WAIT_SECONDS
        )

    assert results[0].id == results[1].id
    assert results[0].content == results[1].content
    assert len(results[0].attachments) == len(results[1].attachments) == 1
    winner_url = results[0].attachments[0].url
    assert results[1].attachments[0].url == winner_url
    assert set(storage.objects) == {winner_url}
    assert len(storage.deleted) == 1 and winner_url not in storage.deleted
    assert await _snapshot(chat_id, user_id) == (1, 1, 1, 1)
