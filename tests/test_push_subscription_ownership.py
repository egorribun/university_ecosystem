"""Ownership and canonical topic-preference contracts for push subscriptions.

ADR-041: ``UserPushTopic`` is the canonical per-user preference.  No record
means the default (all topics), an explicit ``[]`` record opts out of every
topic, and a list restricts delivery to those topics.  ``POST /push/subscribe``
binds a (possibly transferred) endpoint to the *caller's* preference; only a
non-empty topic list updates it.  A transfer never reads or alters the
previous owner's preference.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import get_password_hash
from app.models import PushSubscription, UserPushTopic
from app.services.push_topics import (
    filter_user_ids_by_topic,
    resolve_subscription_topics_for_user,
)

_TEST_PASSWORD = "TestPassword123!"  # pragma: allowlist secret
NEWS = "news.published"
EVENTS = "events.published"
SYSTEM = "system.release"


async def _login(client: AsyncClient, email: str) -> dict[str, str]:
    resp = await client.post(
        "/auth/login",
        data={"username": email, "password": _TEST_PASSWORD},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 200, resp.text
    token = resp.cookies.get("access_token_v2") or client.cookies.get("access_token_v2")
    assert token
    return {"Authorization": f"Bearer {token}", "X-Query-Budget": "15"}


def _payload(endpoint: str, **extra: Any) -> dict[str, Any]:
    return {
        "endpoint": endpoint,
        "keys": {"p256dh": "test_p256dh_key_for_push", "auth": "test_auth_key"},
        **extra,
    }


def _endpoint() -> str:
    return f"https://push.example.com/{uuid.uuid4().hex}"


async def _user(user_factory: Any) -> Any:
    hashed = await get_password_hash(_TEST_PASSWORD)
    return await user_factory(hashed_password=hashed, is_active=True)


async def _record(db: AsyncSession, user_id: uuid.UUID) -> list[str] | None:
    row = (
        await db.execute(
            select(UserPushTopic)
            .where(UserPushTopic.user_id == user_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    return None if row is None else list(row.topics)


async def _subscription(db: AsyncSession, endpoint: str) -> PushSubscription:
    return (
        await db.execute(
            select(PushSubscription)
            .where(PushSubscription.endpoint == endpoint)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


async def _set_record(db: AsyncSession, user_id: uuid.UUID, topics: list[str]) -> None:
    db.add(UserPushTopic(user_id=user_id, topics=topics))
    await db.commit()


# ---------------------------------------------------------------------------
# Service: resolve_subscription_topics_for_user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_omitted_without_record_returns_default_and_writes_nothing(
    db_session: AsyncSession, user_factory: Any
) -> None:
    user = await user_factory()

    topics = await resolve_subscription_topics_for_user(
        db_session, user_id=user.id, requested_topics=None
    )

    assert topics == []
    assert await _record(db_session, user.id) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("requested", [None, []], ids=["omitted", "empty"])
async def test_resolve_follows_the_canonical_record_without_rewriting_it(
    db_session: AsyncSession, user_factory: Any, requested: list[str] | None
) -> None:
    user = await user_factory()
    await _set_record(db_session, user.id, [EVENTS, "unknown-topic"])

    topics = await resolve_subscription_topics_for_user(
        db_session, user_id=user.id, requested_topics=requested
    )

    assert topics == [EVENTS]
    assert await _record(db_session, user.id) == [EVENTS, "unknown-topic"]


@pytest.mark.asyncio
async def test_resolve_keeps_an_explicit_opt_out_record(
    db_session: AsyncSession, user_factory: Any
) -> None:
    user = await user_factory()
    await _set_record(db_session, user.id, [])

    topics = await resolve_subscription_topics_for_user(
        db_session, user_id=user.id, requested_topics=[]
    )

    assert topics == []
    assert await _record(db_session, user.id) == []


@pytest.mark.asyncio
async def test_resolve_explicit_list_updates_only_the_owner_and_mirrors_devices(
    db_session: AsyncSession, user_factory: Any, push_subscription_factory: Any
) -> None:
    owner = await user_factory()
    other = await user_factory()
    first = await push_subscription_factory(user=owner, topics=[SYSTEM])
    second = await push_subscription_factory(user=owner, topics=[])
    foreign = await push_subscription_factory(user=other, topics=[SYSTEM])
    await _set_record(db_session, other.id, [SYSTEM])

    topics = await resolve_subscription_topics_for_user(
        db_session, user_id=owner.id, requested_topics=[NEWS]
    )
    await db_session.commit()

    assert topics == [NEWS]
    assert await _record(db_session, owner.id) == [NEWS]
    assert (await _subscription(db_session, first.endpoint)).topics == [NEWS]
    assert (await _subscription(db_session, second.endpoint)).topics == [NEWS]
    assert (await _subscription(db_session, foreign.endpoint)).topics == [SYSTEM]
    assert await _record(db_session, other.id) == [SYSTEM]


# ---------------------------------------------------------------------------
# Router: endpoint transfer and preference preservation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("extra", [{}, {"topics": []}], ids=["omitted", "empty"])
async def test_transfer_binds_endpoint_to_the_new_owner_preferences(
    async_client: AsyncClient,
    db_session: AsyncSession,
    user_factory: Any,
    push_subscription_factory: Any,
    extra: dict[str, Any],
) -> None:
    previous = await _user(user_factory)
    caller = await _user(user_factory)
    endpoint = _endpoint()
    await push_subscription_factory(user=previous, endpoint=endpoint, topics=[NEWS])
    await _set_record(db_session, previous.id, [NEWS])
    await _set_record(db_session, caller.id, [EVENTS])

    headers = await _login(async_client, caller.email)
    resp = await async_client.post(
        "/push/subscribe", json=_payload(endpoint, **extra), headers=headers
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["topics"] == [EVENTS]
    row = await _subscription(db_session, endpoint)
    assert row.user_id == caller.id
    assert row.topics == [EVENTS]
    assert await _record(db_session, previous.id) == [NEWS]
    assert await _record(db_session, caller.id) == [EVENTS]


@pytest.mark.asyncio
async def test_transfer_to_owner_without_record_uses_the_default(
    async_client: AsyncClient,
    db_session: AsyncSession,
    user_factory: Any,
    push_subscription_factory: Any,
) -> None:
    previous = await _user(user_factory)
    caller = await _user(user_factory)
    endpoint = _endpoint()
    await push_subscription_factory(user=previous, endpoint=endpoint, topics=[NEWS])
    await _set_record(db_session, previous.id, [NEWS])

    headers = await _login(async_client, caller.email)
    resp = await async_client.post(
        "/push/subscribe", json=_payload(endpoint), headers=headers
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["topics"] == []
    assert (await _subscription(db_session, endpoint)).topics == []
    assert await _record(db_session, caller.id) is None
    assert await _record(db_session, previous.id) == [NEWS]
    topics = await async_client.get("/push/topics", headers=headers)
    assert topics.json()["has_preferences"] is False


@pytest.mark.asyncio
async def test_transfer_with_explicit_topics_leaves_previous_owner_untouched(
    async_client: AsyncClient,
    db_session: AsyncSession,
    user_factory: Any,
    push_subscription_factory: Any,
) -> None:
    previous = await _user(user_factory)
    caller = await _user(user_factory)
    moved = _endpoint()
    kept = _endpoint()
    await push_subscription_factory(
        user=previous, endpoint=moved, topics=[NEWS, EVENTS]
    )
    await push_subscription_factory(user=previous, endpoint=kept, topics=[NEWS, EVENTS])
    await _set_record(db_session, previous.id, [NEWS, EVENTS])

    headers = await _login(async_client, caller.email)
    resp = await async_client.post(
        "/push/subscribe", json=_payload(moved, topics=[SYSTEM]), headers=headers
    )

    assert resp.status_code == 200, resp.text
    assert await _record(db_session, caller.id) == [SYSTEM]
    assert await _record(db_session, previous.id) == [NEWS, EVENTS]
    assert (await _subscription(db_session, kept)).topics == [NEWS, EVENTS]
    assert (await _subscription(db_session, moved)).topics == [SYSTEM]


@pytest.mark.asyncio
async def test_new_endpoint_without_topics_copies_the_callers_preference(
    async_client: AsyncClient, db_session: AsyncSession, user_factory: Any
) -> None:
    caller = await _user(user_factory)
    await _set_record(db_session, caller.id, [SYSTEM])
    endpoint = _endpoint()

    headers = await _login(async_client, caller.email)
    resp = await async_client.post(
        "/push/subscribe", json=_payload(endpoint), headers=headers
    )

    assert resp.status_code == 200, resp.text
    assert (await _subscription(db_session, endpoint)).topics == [SYSTEM]
    assert await _record(db_session, caller.id) == [SYSTEM]


@pytest.mark.asyncio
@pytest.mark.parametrize("extra", [{}, {"topics": []}], ids=["omitted", "empty"])
async def test_resubscribe_preserves_an_explicit_opt_out(
    async_client: AsyncClient,
    db_session: AsyncSession,
    user_factory: Any,
    push_subscription_factory: Any,
    extra: dict[str, Any],
) -> None:
    caller = await _user(user_factory)
    endpoint = _endpoint()
    await push_subscription_factory(user=caller, endpoint=endpoint, topics=[])
    headers = await _login(async_client, caller.email)
    opt_out = await async_client.patch(
        "/push/subscribe/topics",
        json={"endpoint": endpoint, "topics": []},
        headers=headers,
    )
    assert opt_out.status_code == 200, opt_out.text

    resp = await async_client.post(
        "/push/subscribe", json=_payload(endpoint, **extra), headers=headers
    )

    assert resp.status_code == 200, resp.text
    assert await _record(db_session, caller.id) == []
    topics = await async_client.get("/push/topics", headers=headers)
    assert topics.json() | {"allowed": None, "updated_at": None} == {
        "allowed": None,
        "topics": [],
        "has_preferences": True,
        "updated_at": None,
    }
    assert (
        await filter_user_ids_by_topic(db_session, user_ids=[caller.id], topic=NEWS)
        == []
    )


@pytest.mark.asyncio
async def test_unsubscribing_the_last_device_keeps_the_preference(
    async_client: AsyncClient,
    db_session: AsyncSession,
    user_factory: Any,
    push_subscription_factory: Any,
) -> None:
    caller = await _user(user_factory)
    endpoint = _endpoint()
    await push_subscription_factory(user=caller, endpoint=endpoint, topics=[])
    await _set_record(db_session, caller.id, [])

    headers = await _login(async_client, caller.email)
    resp = await async_client.post(
        "/push/unsubscribe", json={"endpoint": endpoint}, headers=headers
    )

    assert resp.json() == {"ok": True, "removed": True}
    assert await _record(db_session, caller.id) == []


@pytest.mark.asyncio
async def test_explicit_topics_are_mirrored_to_every_owner_device(
    async_client: AsyncClient,
    db_session: AsyncSession,
    user_factory: Any,
    push_subscription_factory: Any,
) -> None:
    caller = await _user(user_factory)
    other_device = _endpoint()
    await push_subscription_factory(user=caller, endpoint=other_device, topics=[])
    endpoint = _endpoint()

    headers = await _login(async_client, caller.email)
    resp = await async_client.post(
        "/push/subscribe", json=_payload(endpoint, topics=[NEWS]), headers=headers
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["topics"] == [NEWS]
    assert await _record(db_session, caller.id) == [NEWS]
    assert (await _subscription(db_session, other_device)).topics == [NEWS]


@pytest.mark.asyncio
async def test_unknown_only_topics_are_treated_as_omitted(
    async_client: AsyncClient, db_session: AsyncSession, user_factory: Any
) -> None:
    caller = await _user(user_factory)
    await _set_record(db_session, caller.id, [EVENTS])
    endpoint = _endpoint()

    headers = await _login(async_client, caller.email)
    resp = await async_client.post(
        "/push/subscribe",
        json=_payload(endpoint, topics=["legacy-unknown"]),
        headers=headers,
    )

    assert resp.status_code == 200, resp.text
    assert await _record(db_session, caller.id) == [EVENTS]
    assert (await _subscription(db_session, endpoint)).topics == [EVENTS]


@pytest.mark.asyncio
async def test_get_topics_reports_when_the_preference_was_updated(
    async_client: AsyncClient, db_session: AsyncSession, user_factory: Any
) -> None:
    caller = await _user(user_factory)
    await _set_record(db_session, caller.id, [NEWS])

    headers = await _login(async_client, caller.email)
    resp = await async_client.get("/push/topics", headers=headers)

    assert resp.json()["updated_at"] is not None
