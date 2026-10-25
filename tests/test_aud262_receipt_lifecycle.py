"""Durable chat send receipt key and repository contracts."""

from __future__ import annotations

import json
import uuid
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import fakeredis.aioredis
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import app.deps.cache as cache_module
import app.services.chat.command_service as command_service
from app.models import Chat, Message
from app.models.chat_send_receipt import ChatSendReceipt
from app.repositories.chat_repository import ChatRepository, SendReceiptState
from tests import test_chat_idempotency_ownership as _idempotency_tests
from tests.test_chat_idempotency_ownership import dispatcher

redis = _idempotency_tests.redis


def test_receipt_digest_is_stable_scoped_and_unaffected_by_cache_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    user_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
    key = "retry:ключ"
    digest = command_service._make_send_receipt_digest(chat_id, user_id, key)
    assert digest == "e226a725c554c186eb4a638b1eec3b9cfb5c136b9bbd8293803fbf82365632d7"
    assert len(digest) == 64
    assert set(digest) <= set("0123456789abcdef")
    for secret in ("", "rotation-before", "rotation-after"):
        monkeypatch.setattr(command_service.settings, "idempotency_hmac_secret", secret)
        assert (
            command_service._make_send_receipt_digest(chat_id, user_id, key) == digest
        )

    assert command_service._make_send_receipt_digest(user_id, chat_id, key) != digest
    assert (
        command_service._make_send_receipt_digest(chat_id, user_id, key + ":") != digest
    )
    assert (
        command_service._make_send_receipt_digest(chat_id, user_id, "retry:ключ ")
        != digest
    )


async def test_receipt_create_is_transactional_and_reads_do_not_extend_expiry(
    db_session: AsyncSession,
    user_factory,
) -> None:
    user = await user_factory()
    chat = Chat(participants=[user])
    db_session.add(chat)
    await db_session.flush()
    repository = ChatRepository(db_session)
    await repository.set_message_rls_user(user.id)
    message = Message(chat_id=chat.id, sender_id=user.id, content="receipt fixture")
    await repository.create_message(message)
    digest = command_service._make_send_receipt_digest(chat.id, user.id, "one")
    expiry = await repository.create_send_receipt(
        chat_id=chat.id, user_id=user.id, key_digest=digest, message_id=message.id
    )
    row = (
        await db_session.execute(
            select(ChatSendReceipt).where(ChatSendReceipt.key_digest == digest)
        )
    ).scalar_one()
    assert row.expires_at - row.completed_at == timedelta(hours=24)
    assert row.expires_at.replace(tzinfo=UTC) == expiry

    first = await repository.get_send_receipt(chat.id, user.id, digest)
    second = await repository.get_send_receipt(chat.id, user.id, digest)
    assert first is not None and second is not None
    assert first.message_id == second.message_id == message.id
    assert first.expires_at == second.expires_at == expiry
    assert first.observed_at <= second.observed_at
    assert first.observed_at < first.expires_at
    remaining = await repository.send_receipt_remaining_seconds(expiry)
    assert 0 < remaining <= int((expiry - second.observed_at).total_seconds())
    with pytest.raises(FrozenInstanceError):
        first.message_id = uuid.uuid4()

    # A repository flush must never secretly commit the receipt or message.
    chat_id, user_id = chat.id, user.id
    await db_session.rollback()
    assert await repository.get_send_receipt(chat_id, user_id, digest) is None


@pytest.mark.parametrize(
    ("sqlstate", "constraint", "table", "schema", "expected_schema", "expected"),
    [
        ("23505", "uq_chat_send_receipts_chat_user_key", None, None, None, True),
        ("23505", "uq_chat_send_receipts_chat_user_key", None, None, "public", True),
        (
            "23505",
            "uq_chat_send_receipts_chat_user_key",
            "chat_send_receipts",
            "public",
            "public",
            True,
        ),
        ("23503", "uq_chat_send_receipts_chat_user_key", None, None, None, False),
        ("23505", "messages_pkey", None, None, None, False),
        ("23505", "uq_chat_send_receipts_chat_user_key_extra", None, None, None, False),
        ("23505", "uq_chat_send_receipts_chat_user_key", "messages", None, None, False),
        (
            "23505",
            "uq_chat_send_receipts_chat_user_key",
            "chat_send_receipts",
            "other",
            "public",
            False,
        ),
        (None, "uq_chat_send_receipts_chat_user_key", None, None, None, False),
        ("23505", None, None, None, None, False),
    ],
)
def test_receipt_conflict_requires_exact_driver_identity(
    sqlstate,
    constraint,
    table,
    schema,
    expected_schema,
    expected,
) -> None:
    driver = RuntimeError("owned driver error")
    driver.sqlstate = sqlstate
    driver.constraint_name = constraint
    if table is not None:
        driver.table_name = table
    if schema is not None:
        driver.schema_name = schema
    error = IntegrityError("INSERT", {}, driver)
    actual = command_service._is_send_receipt_conflict(
        error, expected_schema=expected_schema
    )
    assert actual is expected


@pytest.mark.parametrize("diagnostic_style", ["direct", "diag"])
def test_receipt_conflict_unwraps_driver_cause_and_pgcode(
    diagnostic_style: str,
) -> None:
    driver = RuntimeError("owned driver cause")
    driver.pgcode = "23505"
    fields = {
        "constraint_name": "uq_chat_send_receipts_chat_user_key",
        "table_name": "chat_send_receipts",
        "schema_name": "public",
    }
    if diagnostic_style == "diag":
        driver.diag = SimpleNamespace(**fields)
    else:
        for name, value in fields.items():
            setattr(driver, name, value)
    wrapper = RuntimeError("owned adapter error")
    wrapper.__cause__ = driver
    error = IntegrityError("INSERT", {}, wrapper)
    assert command_service._is_send_receipt_conflict(error, expected_schema="public")


def test_receipt_conflict_cause_cycle_without_match_is_not_a_duplicate() -> None:
    first = RuntimeError("owned cycle one")
    second = RuntimeError("owned cycle two")
    first.__cause__ = second
    second.__cause__ = first
    error = IntegrityError("INSERT", {}, first)
    assert not command_service._is_send_receipt_conflict(error)


async def test_exact_expiry_equality_does_not_replay_legacy_cache(redis) -> None:
    """Exercise dispatcher equality using a frozen database observation boundary."""
    instant = datetime(2026, 1, 1, tzinfo=UTC)
    chat_id, user_id, message_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    user = SimpleNamespace(id=user_id)
    original = SimpleNamespace(id=message_id, content="first", created_at=instant)
    sender = dispatcher(user, chat_id, [original])
    sender.repository.get_send_receipt = AsyncMock(
        return_value=SendReceiptState(
            message_id=message_id, expires_at=instant, observed_at=instant
        )
    )
    key = "exact-boundary"
    await redis.set(
        command_service._make_idempotency_key(chat_id, user_id, key),
        json.dumps({"message_id": str(message_id)}),
        ex=86400,
    )
    with pytest.raises(HTTPException) as caught:
        await sender.send_message(chat_id, user, "", [], "en", idempotency_key=key)
    # Expired means this is a new send, so its empty payload must be rejected.
    assert caught.value.status_code == 400


@pytest.mark.parametrize("limit", [0, -1])
async def test_invalid_prune_limit_does_not_mutate_expired_receipt(
    db_session: AsyncSession,
    user_factory,
    limit: int,
) -> None:
    user = await user_factory()
    chat = Chat(participants=[user])
    db_session.add(chat)
    await db_session.flush()
    repository = ChatRepository(db_session)
    await repository.set_message_rls_user(user.id)
    row = ChatSendReceipt(
        chat_id=chat.id,
        user_id=user.id,
        key_digest="c" * 64,
        message_id=None,
        completed_at=datetime(2000, 1, 1, tzinfo=UTC),
        expires_at=datetime(2000, 1, 2, tzinfo=UTC),
    )
    db_session.add(row)
    await db_session.flush()
    with pytest.raises(ValueError):
        await repository.prune_expired_send_receipts(chat.id, user.id, limit=limit)
    state = await repository.get_send_receipt(chat.id, user.id, "c" * 64)
    assert state is not None and state.message_id is None
    assert state.expires_at == datetime(2000, 1, 2, tzinfo=UTC)
    assert state.expires_at < state.observed_at
    assert await repository.send_receipt_remaining_seconds(state.expires_at) == 0
    remaining_ids = (
        (
            await db_session.execute(
                select(ChatSendReceipt.id).where(ChatSendReceipt.chat_id == chat.id)
            )
        )
        .scalars()
        .all()
    )
    assert remaining_ids == [row.id]


@pytest.mark.parametrize("replace_owner", [False, True])
async def test_elapsed_receipt_completion_releases_only_its_own_pending_cache(
    redis,
    replace_owner: bool,
) -> None:
    user = SimpleNamespace(id=uuid.uuid4())
    chat_id = uuid.uuid4()
    attempted = []
    sender = dispatcher(user, chat_id, attempted)
    sender.repository.send_receipt_remaining_seconds = AsyncMock(return_value=0)
    cache_key = command_service._make_idempotency_key(chat_id, user.id, "elapsed")
    replacement = json.dumps({"status": "pending", "owner": "replacement"})

    async def commit_boundary() -> None:
        if replace_owner:
            await redis.set(cache_key, replacement, ex=300)

    sender.uow.commit.side_effect = commit_boundary
    result = await sender.send_message(
        chat_id, user, "completed", [], "en", idempotency_key="elapsed"
    )
    assert len(attempted) == 1
    assert result.id == attempted[0].id
    assert await redis.get(cache_key) == (replacement if replace_owner else None)


async def test_active_receipt_missing_scoped_message_conflicts_before_redis(
    redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instant = datetime(2026, 1, 1, tzinfo=UTC)
    user = SimpleNamespace(id=uuid.uuid4())
    chat_id = uuid.uuid4()
    attempted = []
    sender = dispatcher(user, chat_id, attempted)
    sender.repository.get_send_receipt = AsyncMock(
        return_value=SendReceiptState(
            message_id=uuid.uuid4(),
            expires_at=instant + timedelta(hours=24),
            observed_at=instant,
        )
    )

    async def forbidden_cache_access():
        raise AssertionError("active receipt must be resolved before Redis")

    monkeypatch.setattr(cache_module, "get_cache_client", forbidden_cache_access)
    with pytest.raises(HTTPException) as caught:
        await sender.send_message(
            chat_id, user, "", [], "en", idempotency_key="scoped-missing"
        )
    assert caught.value.status_code == 409
    assert caught.value.detail["error"] == "idempotency_in_progress"
    assert caught.value.headers["Retry-After"] == "1"
    assert attempted == []


async def test_stale_durable_cache_bytes_are_owned_deleted_before_new_send(
    redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = fakeredis.aioredis.FakeRedis(decode_responses=False)
    user = SimpleNamespace(id=uuid.uuid4())
    chat_id, stale_id = uuid.uuid4(), uuid.uuid4()
    key = "bytes"
    cache_key = command_service._make_idempotency_key(chat_id, user.id, key)
    attempted = []
    sender = dispatcher(user, chat_id, attempted)

    async def bytes_cache():
        return cache

    monkeypatch.setattr(cache_module, "get_cache_client", bytes_cache)
    try:
        await cache.set(
            cache_key,
            json.dumps(
                {
                    "status": "completed",
                    "receipt_version": 1,
                    "message_id": str(stale_id),
                    "expires_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
                }
            ),
            ex=86400,
        )
        assert isinstance(await cache.get(cache_key), bytes)
        result = await sender.send_message(
            chat_id, user, "new generation", [], "en", idempotency_key=key
        )
        assert len(attempted) == 1
        assert result.id == attempted[0].id and result.id != stale_id
        completed = json.loads(await cache.get(cache_key))
        assert completed["status"] == "completed"
        assert completed["receipt_version"] == 1
        assert completed["message_id"] == str(result.id)
    finally:
        await cache.aclose()


@pytest.mark.parametrize("winner_state", ["missing", "expired"])
async def test_exact_unique_conflict_without_live_winner_does_not_insert_again(
    redis,
    winner_state: str,
) -> None:
    instant = datetime(2026, 1, 1, tzinfo=UTC)
    user = SimpleNamespace(id=uuid.uuid4())
    chat_id = uuid.uuid4()
    attempted = []
    sender = dispatcher(user, chat_id, attempted)
    winner = (
        None
        if winner_state == "missing"
        else SendReceiptState(
            message_id=uuid.uuid4(), expires_at=instant, observed_at=instant
        )
    )
    sender.repository.get_send_receipt = AsyncMock(side_effect=[None, winner])
    sender.repository.set_message_rls_user = AsyncMock()
    sender.session.get_bind = MagicMock(
        return_value=SimpleNamespace(
            dialect=SimpleNamespace(default_schema_name="public")
        )
    )
    driver = RuntimeError("owned exact unique conflict")
    driver.sqlstate = "23505"
    driver.constraint_name = "uq_chat_send_receipts_chat_user_key"
    driver.table_name = "chat_send_receipts"
    driver.schema_name = "public"
    sender.repository.create_send_receipt = AsyncMock(
        side_effect=IntegrityError("INSERT", {}, driver)
    )

    async def forbidden_commit() -> None:
        raise AssertionError("receipt conflict must never commit the losing attempt")

    sender.uow.commit.side_effect = forbidden_commit
    with pytest.raises(HTTPException) as caught:
        await sender.send_message(
            chat_id, user, "loser", [], "en", idempotency_key="missing-winner"
        )
    assert caught.value.status_code == 409
    assert caught.value.detail["error"] == "idempotency_in_progress"
    assert caught.value.headers["Retry-After"] == "1"
    assert len(attempted) == 1
    cache_key = command_service._make_idempotency_key(
        chat_id, user.id, "missing-winner"
    )
    assert await redis.get(cache_key) is None
