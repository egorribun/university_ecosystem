from __future__ import annotations

import asyncio
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import fakeredis.aioredis
import pytest
from fastapi import HTTPException
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import ResponseError
from redis.exceptions import TimeoutError as RedisTimeoutError
from sqlalchemy import func, select

import app.deps.cache as cache_module
import app.services.chat.command_service as command_service
from app.models import Chat, Message
from app.repositories.unit_of_work import uow_from_session


@pytest.mark.parametrize(
    ("failure_type", "returns_response"),
    [
        pytest.param(OSError, True, id="os-error"),
        pytest.param(RedisConnectionError, True, id="redis-error"),
        pytest.param(RedisTimeoutError, True, id="redis-timeout"),
        pytest.param(ResponseError, False, id="redis-response-error-propagates"),
        pytest.param(asyncio.CancelledError, False, id="cancellation-propagates"),
        pytest.param(ValueError, False, id="unexpected-error-propagates"),
    ],
)
@pytest.mark.asyncio
async def test_postcommit_completion_failure_keeps_database_result(
    db_session, user_factory, monkeypatch, failure_type, returns_response
):
    cache = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(cache_module, "get_cache_client", AsyncMock(return_value=cache))
    monkeypatch.setattr(
        command_service,
        "ws_manager",
        SimpleNamespace(is_online=lambda _user_id: False),
    )

    user = await user_factory()
    peer = await user_factory()
    chat = Chat(participants=[user, peer])
    db_session.add(chat)
    await db_session.commit()

    real_change_slot = command_service._change_idempotency_slot
    failure_marker = f"completion-{uuid.uuid4().hex}"

    async def fail_completion_promotion(key, expected, replacement=None, *, ttl=300):
        if (
            replacement is not None
            and json.loads(replacement).get("status") == "completed"
        ):
            raise failure_type(failure_marker)
        return await real_change_slot(key, expected, replacement, ttl=ttl)

    monkeypatch.setattr(
        command_service, "_change_idempotency_slot", fail_completion_promotion
    )
    dispatcher = command_service.ChatMessageDispatcher(
        uow_from_session(db_session),
        MagicMock(),
        MagicMock(),
    )
    client_key = uuid.uuid4().hex
    response = None
    completion_error = None
    try:
        try:
            response = await dispatcher.send_message(
                chat.id,
                user,
                "message",
                [],
                "en",
                idempotency_key=client_key,
            )
        except (
            RedisConnectionError,
            RedisTimeoutError,
            ResponseError,
            OSError,
            asyncio.CancelledError,
            ValueError,
        ) as exc:
            completion_error = exc

        persisted = await db_session.scalar(
            select(func.count()).select_from(Message).where(Message.chat_id == chat.id)
        )
        assert persisted == 1, "database commit must precede Redis completion failure"

        key = command_service._make_idempotency_key(chat.id, user.id, client_key)
        pending = json.loads(await cache.get(key))
        assert pending["status"] == "pending"
        assert 0 < await cache.ttl(key) <= 300

        with pytest.raises(HTTPException) as retry:
            await dispatcher.send_message(
                chat.id,
                user,
                "message",
                [],
                "en",
                idempotency_key=client_key,
            )
        assert retry.value.status_code == 409

        persisted_after_retry = await db_session.scalar(
            select(func.count()).select_from(Message).where(Message.chat_id == chat.id)
        )
        assert persisted_after_retry == 1

        if returns_response:
            assert completion_error is None
            assert response is not None
            assert response.content == "message"
        else:
            assert isinstance(completion_error, failure_type)
            assert str(completion_error) == failure_marker
            assert response is None
    finally:
        await cache.aclose()


@pytest.mark.asyncio
async def test_message_without_idempotency_key_skips_cache_completion(
    db_session, user_factory, monkeypatch
):
    monkeypatch.setattr(cache_module, "get_cache_client", AsyncMock())
    monkeypatch.setattr(
        command_service,
        "ws_manager",
        SimpleNamespace(is_online=lambda _user_id: False),
    )
    monkeypatch.setattr(command_service, "_change_idempotency_slot", AsyncMock())

    user = await user_factory()
    peer = await user_factory()
    chat = Chat(participants=[user, peer])
    db_session.add(chat)
    await db_session.commit()

    dispatcher = command_service.ChatMessageDispatcher(
        uow_from_session(db_session),
        MagicMock(),
        MagicMock(),
    )
    response = await dispatcher.send_message(chat.id, user, "message", [], "en")

    persisted = await db_session.scalar(
        select(func.count()).select_from(Message).where(Message.chat_id == chat.id)
    )
    assert response.content == "message"
    assert persisted == 1
    cache_module.get_cache_client.assert_not_awaited()
    command_service._change_idempotency_slot.assert_not_awaited()
