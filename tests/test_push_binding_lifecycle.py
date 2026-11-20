from __future__ import annotations

import secrets
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.sql import Select
from sqlalchemy.sql.dml import Delete

from app.models import PushSubscription, UserPushTopic
from app.routers import notifications
from app.schemas.notifications import (
    AdminUserTopicsUpdate,
    DisableUserPushRequest,
    PushSubscriptionDelete,
    PushSubscriptionIn,
    PushSubscriptionTopicsUpdate,
)
from tests.conftest import call_injected


@pytest.fixture(autouse=True)
def offline_push(monkeypatch: pytest.MonkeyPatch) -> None:
    async def validate(payload: PushSubscriptionIn, *, locale: str | None):
        return payload.endpoint, payload.keys.p256dh, payload.keys.auth

    monkeypatch.setattr(notifications, "_validate_subscription_payload", validate)
    monkeypatch.setattr(notifications, "enforce_rate_limit", AsyncMock())
    monkeypatch.setattr(notifications, "resolve_locale", lambda **_kwargs: "en")


def _request() -> MagicMock:
    request = MagicMock()
    request.client = None
    request.headers.get.return_value = None
    return request


def _payload(endpoint: str, *, p256dh: str, auth: str) -> PushSubscriptionIn:
    return PushSubscriptionIn(endpoint=endpoint, keys={"p256dh": p256dh, "auth": auth})


async def _subscribe(db, user, endpoint: str, *, p256dh: str, auth: str):
    return await call_injected(
        notifications.subscribe,
        payload=_payload(endpoint, p256dh=p256dh, auth=auth),
        request=_request(),
        user=user,
        provides={"AsyncDatabaseSession": db},
    )


@pytest.mark.asyncio
async def test_identical_rebind_advances_binding_generation(
    db_session, user_factory, push_subscription_factory
) -> None:
    user = await user_factory()
    sub = await push_subscription_factory(user=user)
    endpoint, key, auth = sub.endpoint, sub.p256dh, sub.auth
    assert sub.binding_version is None
    await _subscribe(db_session, user, endpoint, p256dh=key, auth=auth)
    await db_session.refresh(sub)
    assert sub.binding_version == 1
    await _subscribe(db_session, user, endpoint, p256dh=key, auth=auth)
    await db_session.refresh(sub)
    assert sub.binding_version == 2


@pytest.mark.asyncio
async def test_response_is_the_callers_snapshot_even_if_another_owner_commits_next(
    db_session, user_factory, push_subscription_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    previous = await user_factory()
    caller = await user_factory()
    next_owner = await user_factory()
    sub = await push_subscription_factory(user=previous)
    endpoint = sub.endpoint
    caller_key, caller_auth = secrets.token_urlsafe(16), secrets.token_urlsafe(16)
    later_key, later_auth = secrets.token_urlsafe(16), secrets.token_urlsafe(16)
    original_commit = db_session.commit
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def commit_then_transfer() -> None:
        await original_commit()
        async with sessions() as other:
            await other.execute(
                update(PushSubscription)
                .where(PushSubscription.endpoint == endpoint)
                .values(user_id=next_owner.id, p256dh=later_key, auth=later_auth)
            )
            await other.commit()

    monkeypatch.setattr(db_session, "commit", commit_then_transfer)
    result = await _subscribe(
        db_session, caller, endpoint, p256dh=caller_key, auth=caller_auth
    )
    assert result.user_id == caller.id
    assert result.p256dh == caller_key
    assert result.auth == caller_auth
    await db_session.refresh(sub)
    assert sub.user_id == next_owner.id


@pytest.mark.asyncio
async def test_unsubscribe_is_one_owner_qualified_delete() -> None:
    caller = uuid.uuid4()
    endpoint = f"https://push.invalid/{uuid.uuid4().hex}"
    old_row = SimpleNamespace(id=uuid.uuid4(), user_id=caller, endpoint=endpoint)
    db = AsyncMock()
    observed = []

    async def execute(statement):
        observed.append(statement)
        result = MagicMock()
        # A transfer after an obsolete read must make the later delete miss.
        result.scalar_one_or_none.return_value = (
            None if isinstance(statement, Delete) else old_row
        )
        return result

    db.execute.side_effect = execute
    result = await call_injected(
        notifications.unsubscribe,
        payload=PushSubscriptionDelete(endpoint=endpoint),
        request=_request(),
        user=SimpleNamespace(id=caller),
        provides={"AsyncDatabaseSession": db},
    )
    assert result == {"ok": True, "removed": False}
    assert len(observed) == 1
    assert isinstance(observed[0], Delete)
    compiled = observed[0].compile(dialect=postgresql.dialect())
    assert "push_subscriptions.endpoint =" in str(compiled)
    assert "push_subscriptions.user_id =" in str(compiled)
    assert " AND " in str(compiled)
    assert endpoint in compiled.params.values()
    assert caller in compiled.params.values()
    db.delete.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_two_stale_orm_identities_increment_in_the_database(
    db_session, user_factory, push_subscription_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = await user_factory()
    sub = await push_subscription_factory(user=user)
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)
    monkeypatch.setattr(
        notifications,
        "resolve_subscription_topics_for_user",
        AsyncMock(return_value=[]),
    )
    async with sessions() as first, sessions() as second:
        first_row = await first.get(PushSubscription, sub.id)
        second_row = await second.get(PushSubscription, sub.id)
        assert first_row.binding_version is None and second_row.binding_version is None
        for session, row in ((first, first_row), (second, second_row)):
            await notifications._bind_subscription_to_user(
                session,
                row,
                user_id=user.id,
                p256dh=sub.p256dh,
                auth=sub.auth,
                user_agent="",
                now=sub.created_at,
                requested_topics=None,
                is_existing=True,
            )
            await session.commit()
    await db_session.refresh(sub)
    assert sub.binding_version == 2


@pytest.mark.asyncio
async def test_new_subscription_starts_at_zero(db_session, user_factory) -> None:
    user = await user_factory()
    endpoint = f"https://push.invalid/{uuid.uuid4().hex}"
    result = await _subscribe(
        db_session,
        user,
        endpoint,
        p256dh=secrets.token_urlsafe(16),
        auth=secrets.token_urlsafe(16),
    )
    sub = (
        await db_session.execute(
            select(PushSubscription).where(PushSubscription.endpoint == endpoint)
        )
    ).scalar_one()
    assert result.user_id == user.id
    assert sub.binding_version is None


@pytest.mark.asyncio
async def test_topic_patch_returns_owned_snapshot_before_transfer(
    db_session, user_factory, push_subscription_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    caller = await user_factory()
    next_owner = await user_factory()
    sub = await push_subscription_factory(user=caller)
    endpoint, key, auth = sub.endpoint, sub.p256dh, sub.auth
    original_commit = db_session.commit
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def commit_then_transfer() -> None:
        await original_commit()
        async with sessions() as other:
            await other.execute(
                update(PushSubscription)
                .where(PushSubscription.endpoint == endpoint)
                .values(user_id=next_owner.id, p256dh=secrets.token_urlsafe(16))
            )
            await other.commit()

    monkeypatch.setattr(db_session, "commit", commit_then_transfer)
    result = await call_injected(
        notifications.update_subscription_topics,
        payload=PushSubscriptionTopicsUpdate(
            endpoint=endpoint, topics=["news.published"]
        ),
        request=_request(),
        user=caller,
        provides={"AsyncDatabaseSession": db_session},
    )
    assert result.user_id == caller.id
    assert result.p256dh == key
    assert result.auth == auth
    assert result.topics == ["news.published"]
    await db_session.refresh(sub)
    assert sub.user_id == next_owner.id
    assert sub.binding_version is None


@pytest.mark.asyncio
async def test_failed_commit_never_returns_the_prepared_snapshot(
    db_session, user_factory, push_subscription_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = await user_factory()
    sub = await push_subscription_factory(user=user)
    monkeypatch.setattr(
        db_session, "commit", AsyncMock(side_effect=RuntimeError("commit failure"))
    )
    with pytest.raises(RuntimeError, match="commit failure"):
        await _subscribe(
            db_session, user, sub.endpoint, p256dh=sub.p256dh, auth=sub.auth
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["owner", "stale", "final-recovery"])
async def test_binding_retry_reloads_and_increments_once(
    db_session,
    user_factory,
    push_subscription_factory,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    user = await user_factory()
    user_id = user.id
    sub = await push_subscription_factory(user=user)
    endpoint, key, auth = sub.endpoint, sub.p256dh, sub.auth
    original = notifications._locked_subscription_for_binding
    attempts = 0
    count = 3 if failure == "final-recovery" else 1

    async def racing_lock(db, *, endpoint, user_id):
        nonlocal attempts
        attempts += 1
        if attempts <= count:
            if failure == "stale":
                raise StaleDataError("synthetic stale update")
            raise notifications._SubscriptionOwnerChanged
        return await original(db, endpoint=endpoint, user_id=user_id)

    monkeypatch.setattr(notifications, "_locked_subscription_for_binding", racing_lock)
    monkeypatch.setattr(notifications.asyncio, "sleep", AsyncMock())
    result = await _subscribe(db_session, user, endpoint, p256dh=key, auth=auth)
    assert result.user_id == user_id
    assert attempts == count + 1
    await db_session.refresh(sub)
    assert sub.binding_version == 1


@pytest.mark.asyncio
async def test_owner_locks_are_sorted_before_endpoint_lock() -> None:
    caller, previous = sorted((uuid.uuid4(), uuid.uuid4()), reverse=True)
    endpoint = f"https://push.invalid/{uuid.uuid4().hex}"
    row = SimpleNamespace(user_id=previous)
    results = [MagicMock(), MagicMock(), MagicMock()]
    results[0].scalar_one_or_none.return_value = previous
    results[2].scalar_one_or_none.return_value = row
    db = AsyncMock()
    db.execute.side_effect = results
    assert (
        await notifications._locked_subscription_for_binding(
            db, endpoint=endpoint, user_id=caller
        )
        is row
    )
    owner_lock = (
        db.execute.await_args_list[1].args[0].compile(dialect=postgresql.dialect())
    )
    endpoint_lock = (
        db.execute.await_args_list[2].args[0].compile(dialect=postgresql.dialect())
    )
    assert "ORDER BY users.id FOR UPDATE" in str(owner_lock)
    assert next(iter(owner_lock.params.values())) == sorted([caller, previous])
    assert "FOR UPDATE" in str(endpoint_lock)


@pytest.mark.asyncio
async def test_owner_change_during_lock_is_retried_not_bound() -> None:
    caller, previous, newer = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    results = [MagicMock(), MagicMock(), MagicMock()]
    results[0].scalar_one_or_none.return_value = previous
    results[2].scalar_one_or_none.return_value = SimpleNamespace(user_id=newer)
    db = AsyncMock()
    db.execute.side_effect = results
    with pytest.raises(notifications._SubscriptionOwnerChanged):
        await notifications._locked_subscription_for_binding(
            db, endpoint="https://push.invalid/device", user_id=caller
        )


@pytest.mark.asyncio
async def test_unsubscribe_commits_only_a_returned_deleted_row() -> None:
    caller = uuid.uuid4()
    endpoint = f"https://push.invalid/{uuid.uuid4().hex}"
    result = MagicMock()
    result.scalar_one_or_none.return_value = uuid.uuid4()
    db = AsyncMock()
    db.execute.return_value = result
    response = await call_injected(
        notifications.unsubscribe,
        payload=PushSubscriptionDelete(endpoint=endpoint),
        request=_request(),
        user=SimpleNamespace(id=caller),
        provides={"AsyncDatabaseSession": db},
    )
    assert response == {"ok": True, "removed": True}
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("last_state", ["missing", "owner_changed"])
async def test_exhausted_binding_recovery_returns_conflict(
    db_session, user_factory, monkeypatch: pytest.MonkeyPatch, last_state: str
) -> None:
    user = await user_factory()
    endpoint = f"https://push.invalid/{uuid.uuid4().hex}"
    failure = notifications._SubscriptionOwnerChanged()
    last = None if last_state == "missing" else failure
    monkeypatch.setattr(
        notifications,
        "_locked_subscription_for_binding",
        AsyncMock(side_effect=[failure, failure, failure, last]),
    )
    monkeypatch.setattr(notifications.asyncio, "sleep", AsyncMock())
    with pytest.raises(notifications.HTTPException) as raised:
        await _subscribe(
            db_session,
            user,
            endpoint,
            p256dh=secrets.token_urlsafe(16),
            auth=secrets.token_urlsafe(16),
        )
    assert raised.value.status_code == 409
    assert raised.value.detail["error"] == "duplicate_endpoint"


@pytest.mark.asyncio
async def test_admin_topic_update_locks_owner_before_synchronizing(
    db_session, user_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = await user_factory()
    target = await user_factory()
    original_execute = db_session.execute
    locks = []

    async def record(statement, *args, **kwargs):
        if isinstance(statement, Select) and statement._for_update_arg is not None:
            locks.append(str(statement.compile(dialect=postgresql.dialect())))
        return await original_execute(statement, *args, **kwargs)

    monkeypatch.setattr(db_session, "execute", record)
    result = await call_injected(
        notifications.admin_update_user_topics,
        user_id=target.id,
        payload=AdminUserTopicsUpdate(topics=["news.published"]),
        request=_request(),
        user=admin,
        provides={"AsyncDatabaseSession": db_session},
    )
    assert result.user_id == target.id
    assert result.topics == ["news.published"]
    assert len(locks) == 1
    assert "FROM users" in locks[0] and "FOR UPDATE" in locks[0]


@pytest.mark.asyncio
async def test_admin_disable_locks_owner_before_removing_devices(
    db_session, user_factory, push_subscription_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = await user_factory()
    target = await user_factory()
    await push_subscription_factory(user=target)
    original_get = db_session.get
    locked = []

    async def record(*args, **kwargs):
        locked.append(kwargs.get("with_for_update"))
        return await original_get(*args, **kwargs)

    monkeypatch.setattr(db_session, "get", record)
    result = await call_injected(
        notifications.disable_user_push,
        payload=DisableUserPushRequest(user_id=target.id),
        request=_request(),
        user=admin,
        provides={"AsyncDatabaseSession": db_session},
    )
    assert result == {"ok": True, "removed": 1}
    assert locked == [True]


@pytest.mark.asyncio
async def test_transfer_with_topics_preserves_previous_owner_and_other_devices(
    db_session, user_factory, push_subscription_factory
) -> None:
    previous = await user_factory()
    caller = await user_factory()
    moved = await push_subscription_factory(user=previous, topics=["events.published"])
    previous_device = await push_subscription_factory(
        user=previous, topics=["events.published"]
    )
    caller_device = await push_subscription_factory(
        user=caller, topics=["news.published"]
    )
    db_session.add_all(
        [
            UserPushTopic(user_id=previous.id, topics=["events.published"]),
            UserPushTopic(user_id=caller.id, topics=["news.published"]),
        ]
    )
    await db_session.commit()
    endpoint = moved.endpoint
    payload = PushSubscriptionIn(
        endpoint=endpoint,
        keys={"p256dh": secrets.token_urlsafe(16), "auth": secrets.token_urlsafe(16)},
        topics=["system.release"],
    )
    result = await call_injected(
        notifications.subscribe,
        payload=payload,
        request=_request(),
        user=caller,
        provides={"AsyncDatabaseSession": db_session},
    )
    for sub in (moved, previous_device, caller_device):
        await db_session.refresh(sub)
    preferences = dict(
        (
            await db_session.execute(
                select(UserPushTopic.user_id, UserPushTopic.topics)
            )
        ).all()
    )
    assert result.user_id == caller.id
    assert result.topics == ["system.release"]
    assert moved.user_id == caller.id and moved.binding_version == 1
    assert previous_device.topics == ["events.published"]
    assert caller_device.topics == ["system.release"]
    assert (
        previous_device.binding_version is None
        and caller_device.binding_version is None
    )
    assert preferences[previous.id] == ["events.published"]
    assert preferences[caller.id] == ["system.release"]


@pytest.mark.asyncio
async def test_unsubscribe_only_removes_the_current_owners_row(
    db_session, user_factory, push_subscription_factory
) -> None:
    previous = await user_factory()
    current = await user_factory()
    sub = await push_subscription_factory(user=current)
    db_session.add(UserPushTopic(user_id=current.id, topics=["news.published"]))
    await db_session.commit()
    endpoint = sub.endpoint

    async def unsubscribe_as(user):
        return await call_injected(
            notifications.unsubscribe,
            payload=PushSubscriptionDelete(endpoint=endpoint),
            request=_request(),
            user=user,
            provides={"AsyncDatabaseSession": db_session},
        )

    assert await unsubscribe_as(previous) == {"ok": True, "removed": False}
    assert await unsubscribe_as(current) == {"ok": True, "removed": True}
    assert (
        await db_session.execute(
            select(PushSubscription.id).where(PushSubscription.endpoint == endpoint)
        )
    ).scalar_one_or_none() is None
    assert (
        await db_session.execute(
            select(UserPushTopic.topics).where(UserPushTopic.user_id == current.id)
        )
    ).scalar_one() == ["news.published"]


class _SyntheticDatabaseError(Exception):
    def __init__(self, sqlstate: str) -> None:
        super().__init__("synthetic database failure")
        self.sqlstate = sqlstate


def _database_error(sqlstate: str) -> OperationalError:
    return OperationalError(
        "synthetic statement", {}, _SyntheticDatabaseError(sqlstate)
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("driver_field", ["sqlstate", "pgcode"])
@pytest.mark.parametrize("operation", ["subscribe", "topics"])
async def test_deadlock_retries_only_the_database_transaction_after_rollback(
    db_session,
    user_factory,
    push_subscription_factory,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    driver_field: str,
) -> None:
    user = await user_factory()
    user_id = user.id
    sub = await push_subscription_factory(user=user)
    endpoint, key, auth = sub.endpoint, sub.p256dh, sub.auth
    original = notifications._commit_subscription_snapshot
    attempts = 0
    error = _database_error("40P01")
    if driver_field == "pgcode":
        del error.orig.sqlstate
        error.orig.pgcode = "40P01"

    async def deadlock_once(db, subscription):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            await db.flush()
            raise error
        return await original(db, subscription)

    monkeypatch.setattr(notifications, "_commit_subscription_snapshot", deadlock_once)
    validation = AsyncMock(wraps=notifications._validate_subscription_payload)
    monkeypatch.setattr(notifications, "_validate_subscription_payload", validation)
    rollback = AsyncMock(wraps=db_session.rollback)
    monkeypatch.setattr(db_session, "rollback", rollback)
    if operation == "subscribe":
        result = await _subscribe(db_session, user, endpoint, p256dh=key, auth=auth)
        notifications.enforce_rate_limit.assert_awaited_once()
        validation.assert_awaited_once()
    else:
        result = await call_injected(
            notifications.update_subscription_topics,
            payload=PushSubscriptionTopicsUpdate(
                endpoint=endpoint, topics=["news.published"]
            ),
            request=_request(),
            user=user,
            provides={"AsyncDatabaseSession": db_session},
        )
    assert result.user_id == user_id
    assert attempts == 2
    rollback.assert_awaited_once()
    await db_session.refresh(sub)
    assert sub.binding_version == (1 if operation == "subscribe" else None)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["subscribe", "topics"])
@pytest.mark.parametrize("sqlstate, expected_attempts", [("40P01", 3), ("08006", 1)])
async def test_deadlock_retry_is_bounded_and_other_database_errors_propagate(
    db_session,
    user_factory,
    push_subscription_factory,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    sqlstate: str,
    expected_attempts: int,
) -> None:
    user = await user_factory()
    sub = await push_subscription_factory(user=user)
    endpoint, key, auth = sub.endpoint, sub.p256dh, sub.auth
    error = _database_error(sqlstate)
    attempts = 0

    async def fail(db, subscription):
        nonlocal attempts
        attempts += 1
        await db.flush()
        raise error

    monkeypatch.setattr(notifications, "_commit_subscription_snapshot", fail)
    rollback = AsyncMock(wraps=db_session.rollback)
    monkeypatch.setattr(db_session, "rollback", rollback)
    with pytest.raises(OperationalError) as raised:
        if operation == "subscribe":
            await _subscribe(db_session, user, endpoint, p256dh=key, auth=auth)
        else:
            await call_injected(
                notifications.update_subscription_topics,
                payload=PushSubscriptionTopicsUpdate(
                    endpoint=endpoint, topics=["news.published"]
                ),
                request=_request(),
                user=user,
                provides={"AsyncDatabaseSession": db_session},
            )
    assert raised.value is error
    assert attempts == expected_attempts
    assert rollback.await_count == (3 if sqlstate == "40P01" else 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("sqlstate", ["40P01", "08006"])
async def test_final_integrity_recovery_propagates_database_failures(
    db_session, user_factory, monkeypatch: pytest.MonkeyPatch, sqlstate: str
) -> None:
    user = await user_factory()
    endpoint = f"https://push.invalid/{uuid.uuid4().hex}"
    retry = notifications._SubscriptionOwnerChanged()
    error = _database_error(sqlstate)
    lock = AsyncMock(side_effect=[retry, retry, retry, error])
    monkeypatch.setattr(notifications, "_locked_subscription_for_binding", lock)
    rollback = AsyncMock(wraps=db_session.rollback)
    monkeypatch.setattr(db_session, "rollback", rollback)
    with pytest.raises(OperationalError) as raised:
        await _subscribe(
            db_session,
            user,
            endpoint,
            p256dh=secrets.token_urlsafe(16),
            auth=secrets.token_urlsafe(16),
        )
    assert raised.value is error
    assert lock.await_count == 4
    assert rollback.await_count == (4 if sqlstate == "40P01" else 3)


@pytest.mark.asyncio
async def test_topic_patch_does_not_mutate_another_owners_endpoint(
    db_session, user_factory, push_subscription_factory
) -> None:
    caller = await user_factory()
    owner = await user_factory()
    sub = await push_subscription_factory(user=owner, topics=["events.published"])
    with pytest.raises(notifications.HTTPException) as raised:
        await call_injected(
            notifications.update_subscription_topics,
            payload=PushSubscriptionTopicsUpdate(
                endpoint=sub.endpoint, topics=["news.published"]
            ),
            request=_request(),
            user=caller,
            provides={"AsyncDatabaseSession": db_session},
        )
    assert raised.value.status_code == 404
    await db_session.refresh(sub)
    assert sub.user_id == owner.id
    assert sub.topics == ["events.published"]
    assert sub.binding_version is None


def test_conflicting_database_error_codes_do_not_broaden_retry() -> None:
    error = _database_error("08006")
    error.orig.pgcode = "40P01"
    assert notifications._is_postgres_deadlock(error) is False


def test_invalidated_connection_is_not_retried_as_a_deadlock() -> None:
    error = _database_error("40P01")
    error.connection_invalidated = True
    assert notifications._is_postgres_deadlock(error) is False
