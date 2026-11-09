"""Keyed chat sends retain their database receipt when Redis is unavailable."""

from __future__ import annotations

import asyncio
import json
import ssl
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import fakeredis.aioredis
import pytest
from fastapi import HTTPException
from redis.asyncio.connection import SSLConnection
from redis.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ClusterDownError,
    ExternalAuthProviderError,
    MasterDownError,
    ReadOnlyError,
    ResponseError,
)
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from sqlalchemy import event as sa_event
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import app.deps.cache as cache_module
import app.services.chat.command_service as command_service
from app.core.events import (
    MessageSent,
    _persist_captured_events,
    capture_domain_events,
    capture_on_commit,
)
from app.models import Chat, Message, User
from app.models.chat_send_receipt import ChatSendReceipt
from app.models.domain_events import StoredEvent
from app.repositories.unit_of_work import uow_from_session


async def _fail_cache_at(
    monkeypatch, cache, chat_id, user_id, client_key, phase, error
):
    get_client = AsyncMock(return_value=cache)
    if phase == "client":
        get_client.side_effect = error
    elif phase == "get":
        monkeypatch.setattr(cache, "get", AsyncMock(side_effect=error))
    elif phase == "set":
        monkeypatch.setattr(cache, "set", AsyncMock(side_effect=error))
    else:
        if phase == "stale-clear":
            key = command_service._make_idempotency_key(chat_id, user_id, client_key)
            await cache.set(
                key,
                json.dumps({"receipt_version": 1, "message_id": str(uuid.uuid4())}),
            )
        monkeypatch.setattr(
            command_service, "_change_idempotency_slot", AsyncMock(side_effect=error)
        )
    monkeypatch.setattr(cache_module, "get_cache_client", get_client)
    monkeypatch.setattr(
        command_service, "ws_manager", SimpleNamespace(is_online=lambda _: False)
    )
    return get_client


@pytest.mark.parametrize("phase", ["client", "get", "set", "stale-clear", "renew"])
@pytest.mark.parametrize(
    "failure_type",
    [
        RedisConnectionError,
        RedisTimeoutError,
        OSError,
        ReadOnlyError,
        MasterDownError,
        ClusterDownError,
    ],
)
async def test_transport_outage_sends_once_and_replays_real_receipt(
    db_session, user_factory, monkeypatch, phase, failure_type
):
    cache = fakeredis.aioredis.FakeRedis(decode_responses=True)
    user, peer = await user_factory(), await user_factory()
    chat = Chat(participants=[user, peer])
    db_session.add(chat)
    await db_session.commit()
    chat_id, user_id = chat.id, user.id
    client_key = uuid.uuid4().hex
    get_client = await _fail_cache_at(
        monkeypatch,
        cache,
        chat_id,
        user_id,
        client_key,
        phase,
        failure_type("simulated Redis outage"),
    )
    listeners = (
        ("after_flush", capture_domain_events),
        ("after_flush_postexec", _persist_captured_events),
        ("before_commit", capture_on_commit),
    )
    for name, listener in listeners:
        sa_event.listen(db_session.sync_session, name, listener)
    try:
        sender = command_service.ChatMessageDispatcher(
            uow_from_session(db_session), MagicMock(), MagicMock()
        )
        sent = await sender.send_message(
            chat_id, user, "first payload", [], "en", idempotency_key=client_key
        )

        async with AsyncSession(db_session.bind, expire_on_commit=False) as check:
            receipt = await check.scalar(
                select(ChatSendReceipt).where(
                    ChatSendReceipt.chat_id == chat_id,
                    ChatSendReceipt.user_id == user_id,
                )
            )
            assert receipt is not None
            assert receipt.message_id == sent.id
            assert (
                await check.scalar(
                    select(func.count())
                    .select_from(Message)
                    .where(Message.chat_id == chat_id)
                )
                == 1
            )
            assert (
                await check.scalar(
                    select(func.count())
                    .select_from(StoredEvent)
                    .where(
                        StoredEvent.event_type == MessageSent.EVENT_TYPE,
                        StoredEvent.aggregate_id == str(sent.id),
                    )
                )
                == 1
            )

            # Replay is authorized against a new session and must not need Redis.
            get_client.side_effect = AssertionError("replay must use the receipt")
            replay_sender = command_service.ChatMessageDispatcher(
                uow_from_session(check), MagicMock(), MagicMock()
            )
            replay = await replay_sender.send_message(
                chat_id, user, "different retry", [], "en", idempotency_key=client_key
            )
            assert replay.id == sent.id
            assert replay.content == "first payload"
            assert (
                await check.scalar(
                    select(func.count())
                    .select_from(Message)
                    .where(Message.chat_id == chat_id)
                )
                == 1
            )
    finally:
        for name, listener in listeners:
            sa_event.remove(db_session.sync_session, name, listener)
        await cache.aclose()


@pytest.mark.parametrize("phase", ["client", "get", "set", "stale-clear", "renew"])
@pytest.mark.parametrize(
    "failure_type",
    [
        ResponseError,
        ValueError,
        asyncio.CancelledError,
        AuthenticationError,
        AuthorizationError,
        ExternalAuthProviderError,
    ],
)
async def test_unexpected_cache_errors_and_cancellation_propagate(
    db_session, user_factory, monkeypatch, phase, failure_type
):
    cache = fakeredis.aioredis.FakeRedis(decode_responses=True)
    user, peer = await user_factory(), await user_factory()
    chat = Chat(participants=[user, peer])
    db_session.add(chat)
    await db_session.commit()
    chat_id = chat.id
    key = uuid.uuid4().hex
    failure = failure_type("unexpected cache failure")
    await _fail_cache_at(monkeypatch, cache, chat_id, user.id, key, phase, failure)

    try:
        sender = command_service.ChatMessageDispatcher(
            uow_from_session(db_session), MagicMock(), MagicMock()
        )
        # asyncio.shield propagates SET-task cancellation without its message.
        failure_message = (
            None
            if failure_type is asyncio.CancelledError and phase == "set"
            else "unexpected cache failure"
        )
        with pytest.raises(failure_type, match=failure_message):
            await sender.send_message(
                chat_id, user, "must not commit", [], "en", idempotency_key=key
            )
        assert (
            await db_session.scalar(
                select(func.count())
                .select_from(Message)
                .where(Message.chat_id == chat_id)
            )
            == 0
        )
        assert (
            await db_session.scalar(
                select(func.count())
                .select_from(ChatSendReceipt)
                .where(ChatSendReceipt.chat_id == chat_id)
            )
            == 0
        )
    finally:
        await cache.aclose()


@pytest.mark.parametrize(
    "failure_type", [AuthenticationError, AuthorizationError, ExternalAuthProviderError]
)
async def test_postcommit_auth_failure_propagates_and_receipt_still_replays(
    db_session, user_factory, monkeypatch, failure_type
):
    cache = fakeredis.aioredis.FakeRedis(decode_responses=True)
    cache_client = AsyncMock(return_value=cache)
    monkeypatch.setattr(cache_module, "get_cache_client", cache_client)
    monkeypatch.setattr(
        command_service, "ws_manager", SimpleNamespace(is_online=lambda _: False)
    )
    real_change = command_service._change_idempotency_slot

    async def fail_completed_promotion(key, expected, value=None, *, ttl=300):
        if value is not None and json.loads(value).get("status") == "completed":
            raise failure_type("cache authentication failure")
        return await real_change(key, expected, value, ttl=ttl)

    monkeypatch.setattr(
        command_service, "_change_idempotency_slot", fail_completed_promotion
    )
    user, peer = await user_factory(), await user_factory()
    chat = Chat(participants=[user, peer])
    db_session.add(chat)
    await db_session.commit()
    chat_id = chat.id
    key = uuid.uuid4().hex
    sender = command_service.ChatMessageDispatcher(
        uow_from_session(db_session), MagicMock(), MagicMock()
    )
    try:
        with pytest.raises(failure_type, match="cache authentication failure"):
            await sender.send_message(
                chat_id, user, "committed", [], "en", idempotency_key=key
            )
        receipt = await db_session.scalar(
            select(ChatSendReceipt).where(ChatSendReceipt.chat_id == chat_id)
        )
        assert receipt is not None and receipt.message_id is not None
        cache_client.side_effect = AssertionError("committed replay must bypass Redis")
        replay = await sender.send_message(
            chat_id, user, "retry", [], "en", idempotency_key=key
        )
        assert replay.id == receipt.message_id
        assert replay.content == "committed"
    finally:
        await cache.aclose()


@pytest.mark.parametrize(
    "phase", ["client", "get", "set", "stale-clear", "renew", "completion"]
)
@pytest.mark.parametrize("wrapping", ["direct", "redis-context", "redis-cause"])
async def test_tls_failures_never_become_outage_fallback(
    db_session, user_factory, monkeypatch, phase, wrapping
):
    tls_error = ssl.SSLCertVerificationError("certificate verification failed")
    if wrapping == "direct":
        failure = tls_error
    elif wrapping == "redis-context":
        connection = SSLConnection(host="redis.invalid")
        monkeypatch.setattr(connection, "_connect", AsyncMock(side_effect=tls_error))
        with pytest.raises(RedisConnectionError) as captured:
            await connection.connect_check_health(retry_socket_connect=False)
        failure = captured.value
        assert failure.__context__ is tls_error
    else:
        failure = RedisConnectionError("TLS failure")
        failure.__cause__ = tls_error

    cache = fakeredis.aioredis.FakeRedis(decode_responses=True)
    user, peer = await user_factory(), await user_factory()
    chat = Chat(participants=[user, peer])
    db_session.add(chat)
    await db_session.commit()
    chat_id, key = chat.id, uuid.uuid4().hex
    if phase == "completion":
        monkeypatch.setattr(
            cache_module, "get_cache_client", AsyncMock(return_value=cache)
        )
        real_change = command_service._change_idempotency_slot

        async def fail_completion(key, expected, value=None, *, ttl=300):
            if value is not None and json.loads(value).get("status") == "completed":
                raise failure
            return await real_change(key, expected, value, ttl=ttl)

        monkeypatch.setattr(
            command_service, "_change_idempotency_slot", fail_completion
        )
    else:
        await _fail_cache_at(monkeypatch, cache, chat_id, user.id, key, phase, failure)
    sender = command_service.ChatMessageDispatcher(
        uow_from_session(db_session), MagicMock(), MagicMock()
    )
    try:
        with pytest.raises(type(failure)) as caught:
            await sender.send_message(
                chat_id, user, "message", [], "en", idempotency_key=key
            )
        assert caught.value is failure
        count = await db_session.scalar(
            select(func.count()).select_from(Message).where(Message.chat_id == chat_id)
        )
        assert count == (1 if phase == "completion" else 0)
    finally:
        await cache.aclose()


@pytest.mark.parametrize(
    "error_type", [AuthenticationError, AuthorizationError, ExternalAuthProviderError]
)
@pytest.mark.parametrize("attribute", ["__cause__", "__context__"])
def test_wrapped_authentication_failure_is_classified(error_type, attribute):
    wrapped = RedisConnectionError("connection wrapper")
    setattr(wrapped, attribute, error_type("authentication failure"))
    assert command_service._redis_security_error(wrapped)


def test_redis_security_error_traversal_handles_exception_cycles():
    first, second = RedisConnectionError("first"), RedisConnectionError("second")
    first.__context__ = second
    second.__context__ = first
    assert not command_service._redis_security_error(first)
    second.__cause__ = ssl.SSLError("TLS failure")
    assert command_service._redis_security_error(first)


@pytest.mark.parametrize("phase", ["upload", "database"])
async def test_send_failure_after_cache_outage_preserves_original_error(
    db_session, user_factory, monkeypatch, phase
):
    cache_client = AsyncMock(side_effect=RedisConnectionError("Redis unavailable"))
    cache_change = AsyncMock(side_effect=AssertionError("no lease was attempted"))
    monkeypatch.setattr(cache_module, "get_cache_client", cache_client)
    monkeypatch.setattr(command_service, "_change_idempotency_slot", cache_change)
    user, peer = await user_factory(), await user_factory()
    chat = Chat(participants=[user, peer])
    db_session.add(chat)
    await db_session.commit()
    chat_id = chat.id
    failure = ValueError("original send failure")
    attachments = SimpleNamespace(
        process_upload=AsyncMock(side_effect=failure), cleanup_files=AsyncMock()
    )
    sender = command_service.ChatMessageDispatcher(
        uow_from_session(db_session), attachments, MagicMock()
    )
    if phase == "database":
        sender.repository.create_message = AsyncMock(side_effect=failure)
    expected = ExceptionGroup if phase == "upload" else ValueError
    with pytest.raises(expected) as caught:
        await sender.send_message(
            chat_id,
            user,
            "message",
            [SimpleNamespace(size=1)] if phase == "upload" else [],
            "en",
            idempotency_key=uuid.uuid4().hex,
        )
    if phase == "upload":
        assert caught.value.exceptions == (failure,)
    else:
        assert caught.value is failure
    cache_client.assert_awaited_once()
    cache_change.assert_not_awaited()
    assert (
        await db_session.scalar(
            select(func.count()).select_from(Message).where(Message.chat_id == chat_id)
        )
        == 0
    )


@pytest.mark.parametrize(
    "failure_type", [RedisConnectionError, RedisTimeoutError, OSError]
)
async def test_outage_releasing_upload_lease_preserves_original_failure(
    db_session, user_factory, monkeypatch, failure_type
):
    cache = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(cache_module, "get_cache_client", AsyncMock(return_value=cache))
    monkeypatch.setattr(
        command_service,
        "_change_idempotency_slot",
        AsyncMock(side_effect=failure_type("Redis went down during upload")),
    )
    user, peer = await user_factory(), await user_factory()
    chat = Chat(participants=[user, peer])
    db_session.add(chat)
    await db_session.commit()
    chat_id = chat.id
    attachments = SimpleNamespace(
        process_upload=AsyncMock(side_effect=ValueError("upload defect")),
        cleanup_files=AsyncMock(),
    )
    try:
        sender = command_service.ChatMessageDispatcher(
            uow_from_session(db_session), attachments, MagicMock()
        )
        with pytest.raises(ExceptionGroup) as caught:
            await sender.send_message(
                chat_id,
                user,
                "message",
                [SimpleNamespace(size=1)],
                "en",
                idempotency_key=uuid.uuid4().hex,
            )
        assert len(caught.value.exceptions) == 1
        assert isinstance(caught.value.exceptions[0], ValueError)
        assert str(caught.value.exceptions[0]) == "upload defect"
        assert (
            await db_session.scalar(
                select(func.count())
                .select_from(Message)
                .where(Message.chat_id == chat_id)
            )
            == 0
        )
    finally:
        await cache.aclose()


@pytest.mark.parametrize("phase", ["set-upload", "set-database", "renew-database"])
@pytest.mark.parametrize("replacement", [False, True])
async def test_lost_lease_ack_releases_only_its_owner_after_send_failure(
    db_session, user_factory, monkeypatch, phase, replacement
):
    cache = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(cache_module, "get_cache_client", AsyncMock(return_value=cache))
    monkeypatch.setattr(
        command_service, "ws_manager", SimpleNamespace(is_online=lambda _: False)
    )
    user, peer = await user_factory(), await user_factory()
    chat = Chat(participants=[user, peer])
    db_session.add(chat)
    await db_session.commit()
    chat_id, user_id = chat.id, user.id
    client_key = uuid.uuid4().hex
    cache_key = command_service._make_idempotency_key(chat_id, user_id, client_key)
    other_owner = json.dumps({"status": "pending", "owner": uuid.uuid4().hex})
    real_set = cache.set
    real_change = command_service._change_idempotency_slot

    if phase.startswith("set"):

        async def lost_set_ack(*args, **kwargs):
            if replacement:
                await real_set(cache_key, other_owner, ex=300)
            acquired = await real_set(*args, **kwargs)
            assert bool(acquired) is not replacement
            raise RedisTimeoutError("lost SET acknowledgement")

        monkeypatch.setattr(cache, "set", lost_set_ack)
    else:
        injected = False

        async def lost_renewal_ack(key, expected, value=None, *, ttl=300):
            nonlocal injected
            if not injected and value == expected:
                injected = True
                assert await real_change(key, expected, value, ttl=ttl)
                raise RedisTimeoutError("lost renewal acknowledgement")
            return await real_change(key, expected, value, ttl=ttl)

        monkeypatch.setattr(
            command_service, "_change_idempotency_slot", lost_renewal_ack
        )

    async def fail_send(*_args, **_kwargs):
        if replacement and phase.startswith("renew"):
            await real_set(cache_key, other_owner, ex=300)
        raise ValueError("send failed")

    attachments = SimpleNamespace(
        process_upload=AsyncMock(side_effect=fail_send), cleanup_files=AsyncMock()
    )
    sender = command_service.ChatMessageDispatcher(
        uow_from_session(db_session), attachments, MagicMock()
    )
    if phase.endswith("database"):
        sender.repository.create_message = AsyncMock(side_effect=fail_send)
    try:
        expected_error = ExceptionGroup if phase.endswith("upload") else ValueError
        with pytest.raises(expected_error):
            await sender.send_message(
                chat_id,
                user,
                "message",
                [SimpleNamespace(size=1)] if phase.endswith("upload") else [],
                "en",
                idempotency_key=client_key,
            )
        assert await cache.get(cache_key) == (other_owner if replacement else None)
        monkeypatch.setattr(cache, "set", real_set)
        retry_user = await db_session.get(User, user_id)
        assert retry_user is not None
        retry = command_service.ChatMessageDispatcher(
            uow_from_session(db_session), attachments, MagicMock()
        )
        if replacement:
            with pytest.raises(HTTPException) as caught:
                await retry.send_message(
                    chat_id, retry_user, "retry", [], "en", idempotency_key=client_key
                )
            assert caught.value.status_code == 409
            assert await cache.get(cache_key) == other_owner
        else:
            result = await retry.send_message(
                chat_id, retry_user, "retry", [], "en", idempotency_key=client_key
            )
            assert result.content == "retry"
    finally:
        await cache.aclose()


@pytest.mark.parametrize("phase", ["set", "renew"])
async def test_lost_lease_ack_retains_lease_after_unknown_commit(
    db_session, user_factory, monkeypatch, phase
):
    cache = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(cache_module, "get_cache_client", AsyncMock(return_value=cache))
    user, peer = await user_factory(), await user_factory()
    chat = Chat(participants=[user, peer])
    db_session.add(chat)
    await db_session.commit()
    chat_id, user_id = chat.id, user.id
    client_key = uuid.uuid4().hex
    cache_key = command_service._make_idempotency_key(chat_id, user_id, client_key)
    real_set = cache.set
    real_change = command_service._change_idempotency_slot
    injected = False

    if phase == "set":

        async def lost_set_ack(*args, **kwargs):
            assert await real_set(*args, **kwargs)
            raise RedisTimeoutError("lost SET acknowledgement")

        monkeypatch.setattr(cache, "set", lost_set_ack)
    else:

        async def lost_renewal_ack(key, expected, value=None, *, ttl=300):
            nonlocal injected
            if not injected and value == expected:
                injected = True
                assert await real_change(key, expected, value, ttl=ttl)
                raise RedisTimeoutError("lost renewal acknowledgement")
            return await real_change(key, expected, value, ttl=ttl)

        monkeypatch.setattr(
            command_service, "_change_idempotency_slot", lost_renewal_ack
        )

    sender = command_service.ChatMessageDispatcher(
        uow_from_session(db_session), MagicMock(), MagicMock()
    )
    sender.uow.commit = AsyncMock(side_effect=RuntimeError("unknown commit outcome"))
    try:
        with pytest.raises(RuntimeError, match="unknown commit outcome"):
            await sender.send_message(
                chat_id, user, "message", [], "en", idempotency_key=client_key
            )
        lease = json.loads(await cache.get(cache_key))
        assert lease["status"] == "pending"
        assert lease["owner"]
        assert 0 < await cache.ttl(cache_key) <= 300
        monkeypatch.setattr(cache, "set", real_set)
        retry_user = await db_session.get(User, user_id)
        assert retry_user is not None
        retry = command_service.ChatMessageDispatcher(
            uow_from_session(db_session), MagicMock(), MagicMock()
        )
        with pytest.raises(HTTPException) as caught:
            await retry.send_message(
                chat_id, retry_user, "retry", [], "en", idempotency_key=client_key
            )
        assert caught.value.status_code == 409
        assert json.loads(await cache.get(cache_key)) == lease
    finally:
        await cache.aclose()
