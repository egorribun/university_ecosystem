"""Synthetic ORM state regressions for push subscription rebinding."""

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import DBAPIError

from app.models import PushSubscription
from app.services import webpush
from app.services.notifications.delivery import _process_canonical_push_results


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["gone", "sent"])
@pytest.mark.parametrize("change", ["owner", "credentials", "same_binding_values"])
async def test_old_result_does_not_mutate_rebound_subscription(
    db_session, user_factory, push_subscription_factory, monkeypatch, status, change
):
    original_owner = await user_factory()
    replacement_owner = await user_factory()
    subscription = await push_subscription_factory(
        user=original_owner, last_seen_at=None
    )
    subscription_id = subscription.id
    result = webpush.WebPushResult(
        subscription_id=subscription_id,
        endpoint=subscription.endpoint,
        user_id=original_owner.id,
        status=status,
        _binding_version=subscription.binding_version or 0,
    )
    if change == "owner":
        subscription.user_id = replacement_owner.id
    elif change == "credentials":
        subscription.p256dh = "synthetic-replacement-public-key"
        subscription.auth = "synthetic-replacement-auth"
    # The production subscribe transaction increments this atomically.
    subscription.binding_version = (subscription.binding_version or 0) + 1
    await db_session.commit()

    @asynccontextmanager
    async def same_session():
        yield db_session

    monkeypatch.setattr(webpush, "async_session", same_session)
    monkeypatch.setattr(webpush, "_ensure_async_sessionmaker", AsyncMock())
    await webpush.process_push_results([result])

    current = (
        await db_session.execute(
            select(PushSubscription)
            .where(PushSubscription.id == subscription_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    assert current is not None
    assert current.last_seen_at is None
    if change == "owner":
        assert current.user_id == replacement_owner.id
    elif change == "credentials":
        assert current.p256dh == "synthetic-replacement-public-key"
        assert current.auth == "synthetic-replacement-auth"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["gone", "sent"])
@pytest.mark.parametrize("bound", [False, True])
@pytest.mark.parametrize("stored_version", [None, 0, 4])
async def test_current_result_requires_binding_proof(
    db_session,
    user_factory,
    push_subscription_factory,
    monkeypatch,
    status,
    bound,
    stored_version,
):
    owner = await user_factory()
    subscription = await push_subscription_factory(
        user=owner, last_seen_at=None, binding_version=stored_version
    )
    subscription_id = subscription.id
    version = subscription.binding_version or 0
    result = webpush.WebPushResult(
        subscription_id=subscription_id,
        endpoint=subscription.endpoint,
        user_id=owner.id,
        status=status,
        _binding_version=version if bound else None,
    )

    @asynccontextmanager
    async def same_session():
        yield db_session

    monkeypatch.setattr(webpush, "async_session", same_session)
    monkeypatch.setattr(webpush, "_ensure_async_sessionmaker", AsyncMock())
    await webpush.process_push_results([result])
    current = (
        await db_session.execute(
            select(PushSubscription)
            .where(PushSubscription.id == subscription_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if bound and status == "gone":
        assert current is None
    else:
        assert current is not None
        assert (current.last_seen_at is not None) == (bound and status == "sent")
        assert current.binding_version == stored_version


@pytest.mark.asyncio
async def test_old_gone_does_not_hide_new_binding_sent(
    db_session, user_factory, push_subscription_factory, monkeypatch
):
    owner = await user_factory()
    subscription = await push_subscription_factory(user=owner, last_seen_at=None)
    subscription_id = subscription.id
    old = webpush.WebPushResult(
        subscription_id=subscription_id,
        endpoint=subscription.endpoint,
        user_id=owner.id,
        status="gone",
        _binding_version=subscription.binding_version or 0,
    )
    subscription.binding_version = (subscription.binding_version or 0) + 1
    await db_session.commit()
    current = webpush.WebPushResult(
        subscription_id=subscription_id,
        endpoint=subscription.endpoint,
        user_id=owner.id,
        status="sent",
        _binding_version=subscription.binding_version or 0,
    )

    @asynccontextmanager
    async def same_session():
        yield db_session

    monkeypatch.setattr(webpush, "async_session", same_session)
    monkeypatch.setattr(webpush, "_ensure_async_sessionmaker", AsyncMock())
    aggregate = await _process_canonical_push_results([old, current])
    # Public aggregation remains per stable subscription ID.
    assert aggregate == [old]
    row = (
        await db_session.execute(
            select(PushSubscription)
            .where(PushSubscription.id == subscription_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert row.last_seen_at is not None
    assert row.binding_version == current._binding_version


def test_result_repr_omits_binding_proof():
    result = webpush.WebPushResult(
        subscription_id=uuid.uuid4(),
        endpoint="https://push.example.test/placeholder",
        user_id=uuid.uuid4(),
        status="sent",
        _binding_version=9812345,
    )
    assert "binding_version" not in repr(result)
    assert "9812345" not in repr(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("version", [None, False, -1, 2**63, "0"])
async def test_missing_or_invalid_binding_is_ignored(monkeypatch, version):
    result = webpush.WebPushResult(
        subscription_id=uuid.uuid4(),
        endpoint="https://push.example.test/placeholder",
        user_id=uuid.uuid4(),
        status="gone",
        _binding_version=version,
    )
    ensure = AsyncMock()
    monkeypatch.setattr(webpush, "_ensure_async_sessionmaker", ensure)
    await webpush.process_push_results([result])
    ensure.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_result_is_ignored(monkeypatch):
    ensure = AsyncMock()
    monkeypatch.setattr(webpush, "_ensure_async_sessionmaker", ensure)
    await webpush.process_push_results([object()])  # type: ignore[list-item]
    ensure.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["gone", "sent"])
async def test_owner_mismatch_cannot_mutate_even_when_version_matches(
    db_session, user_factory, push_subscription_factory, monkeypatch, status
):
    owner = await user_factory()
    other = await user_factory()
    subscription = await push_subscription_factory(user=owner, last_seen_at=None)
    subscription_id = subscription.id
    result = webpush.WebPushResult(
        subscription_id=subscription_id,
        endpoint=subscription.endpoint,
        user_id=other.id,
        status=status,
        _binding_version=subscription.binding_version or 0,
    )

    @asynccontextmanager
    async def same_session():
        yield db_session

    monkeypatch.setattr(webpush, "async_session", same_session)
    monkeypatch.setattr(webpush, "_ensure_async_sessionmaker", AsyncMock())
    await webpush.process_push_results([result])
    row = (
        await db_session.execute(
            select(PushSubscription)
            .where(PushSubscription.id == subscription_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert row.user_id == owner.id
    assert row.last_seen_at is None


@pytest.mark.asyncio
async def test_string_id_normalization_preserves_binding_proof(
    db_session, user_factory, push_subscription_factory, monkeypatch
):
    owner = await user_factory()
    subscription = await push_subscription_factory(user=owner, last_seen_at=None)
    subscription_id = subscription.id
    result = webpush.WebPushResult(
        subscription_id=str(subscription_id),  # type: ignore[arg-type]
        endpoint=subscription.endpoint,
        user_id=owner.id,
        status="sent",
        _binding_version=subscription.binding_version or 0,
    )

    @asynccontextmanager
    async def same_session():
        yield db_session

    monkeypatch.setattr(webpush, "async_session", same_session)
    monkeypatch.setattr(webpush, "_ensure_async_sessionmaker", AsyncMock())
    await webpush.process_push_results([result])
    row = (
        await db_session.execute(
            select(PushSubscription)
            .where(PushSubscription.id == subscription_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert row.last_seen_at is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["sent", "gone"])
async def test_processing_more_than_one_batch_preserves_all_current_bindings(
    db_session, user_factory, monkeypatch, status
):
    owner = await user_factory()
    subscriptions = [
        PushSubscription(
            user_id=owner.id,
            endpoint=f"https://push.example.test/synthetic-{index}",
            p256dh="synthetic-public-key",
            auth="synthetic-auth",
            topics=[],
        )
        for index in range(201)
    ]
    db_session.add_all(subscriptions)
    await db_session.commit()
    results = [
        webpush.WebPushResult(
            subscription_id=sub.id,
            endpoint=sub.endpoint,
            user_id=owner.id,
            status=status,
            _binding_version=sub.binding_version or 0,
        )
        for sub in subscriptions
    ]

    @asynccontextmanager
    async def same_session():
        yield db_session

    monkeypatch.setattr(webpush, "async_session", same_session)
    monkeypatch.setattr(webpush, "_ensure_async_sessionmaker", AsyncMock())
    parameter_counts = []
    engine = db_session.get_bind()

    def record_parameters(_conn, _cursor, statement, parameters, _context, _many):
        if (
            statement.lstrip()
            .upper()
            .startswith(("UPDATE PUSH_SUBSCRIPTIONS", "DELETE FROM PUSH_SUBSCRIPTIONS"))
        ):
            parameter_counts.append(len(parameters))

    event.listen(engine, "before_cursor_execute", record_parameters)
    try:
        await webpush.process_push_results(results)
    finally:
        event.remove(engine, "before_cursor_execute", record_parameters)
    assert len(parameter_counts) == 2
    assert max(parameter_counts) <= 999
    count = await db_session.scalar(
        select(func.count())
        .select_from(PushSubscription)
        .where(PushSubscription.user_id == owner.id)
    )
    assert count == (201 if status == "sent" else 0)
    if status == "sent":
        touched = await db_session.scalar(
            select(func.count())
            .select_from(PushSubscription)
            .where(PushSubscription.user_id == owner.id)
            .where(PushSubscription.last_seen_at.is_not(None))
        )
        assert touched == 201


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["sent", "gone"])
@pytest.mark.parametrize(
    "scenario",
    ["deadlock_once", "other_error", "exhausted", "contradictory", "invalidated"],
)
@pytest.mark.parametrize("code_attribute", ["sqlstate", "pgcode"])
async def test_result_transaction_retries_only_deadlocks(
    db_session,
    user_factory,
    push_subscription_factory,
    monkeypatch,
    status,
    scenario,
    code_attribute,
):
    owner = await user_factory()
    subscription = await push_subscription_factory(user=owner, last_seen_at=None)
    subscription_id, user_id = subscription.id, owner.id
    result = webpush.WebPushResult(
        subscription_id=subscription_id,
        endpoint=subscription.endpoint,
        user_id=user_id,
        status=status,
        _binding_version=0,
    )
    await db_session.rollback()

    class SyntheticDriverError(Exception):
        def __init__(self, sqlstate):
            if scenario == "contradictory":
                self.sqlstate = "23505"
                self.pgcode = "40P01"
            else:
                setattr(self, code_attribute, sqlstate)

    factory = webpush.async_session
    attempts = 0
    failure_limit = {
        "deadlock_once": 1,
        "other_error": 1,
        "exhausted": 3,
        "contradictory": 1,
        "invalidated": 1,
    }[scenario]

    @asynccontextmanager
    async def session_with_failure():
        nonlocal attempts
        attempts += 1
        async with factory() as session:
            execute = session.execute
            if attempts <= failure_limit:

                async def execute_then_fail(*args, **kwargs):
                    await execute(*args, **kwargs)
                    code = (
                        "23505"
                        if scenario in ("other_error", "contradictory")
                        else "40P01"
                    )
                    raise DBAPIError(
                        "synthetic-dml",
                        {},
                        SyntheticDriverError(code),
                        connection_invalidated=scenario == "invalidated",
                    )

                monkeypatch.setattr(session, "execute", execute_then_fail)
            yield session

    monkeypatch.setattr(webpush, "async_session", session_with_failure)
    monkeypatch.setattr(webpush, "_ensure_async_sessionmaker", AsyncMock())
    sender = Mock(side_effect=AssertionError("a result retry must not send"))
    monkeypatch.setattr(webpush, "send_web_push", sender)
    if scenario == "deadlock_once":
        await webpush.process_push_results([result])
        assert attempts == 2
    else:
        with pytest.raises(DBAPIError) as caught:
            await webpush.process_push_results([result])
        assert getattr(
            caught.value.orig,
            "sqlstate" if scenario == "contradictory" else code_attribute,
        ) == ("23505" if scenario in ("other_error", "contradictory") else "40P01")
        assert attempts == (3 if scenario == "exhausted" else 1)
    sender.assert_not_called()

    current = (
        await db_session.execute(
            select(PushSubscription)
            .where(PushSubscription.id == subscription_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if scenario == "deadlock_once" and status == "gone":
        assert current is None
    else:
        assert current is not None
        assert (current.last_seen_at is not None) == (
            scenario == "deadlock_once" and status == "sent"
        )
