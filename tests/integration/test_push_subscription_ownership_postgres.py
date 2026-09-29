"""ADR-041 push ownership contracts against separate PostgreSQL sessions."""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select

import app.core.database as database
from app.models import PushSubscription, UserPushTopic
from app.routers import notifications
from app.schemas.notifications import PushSubscriptionIn
from app.services.push_topics import (
    resolve_subscription_topics_for_user,
    synchronize_user_topics,
)
from tests.conftest import call_injected

pytestmark = pytest.mark.integration

EVENTS = "events.published"
SYSTEM = "system.release"


def _require_postgres() -> None:
    if database.engine.dialect.name != "postgresql":
        # SQLite unit shards share one connection and cannot race sessions.
        # QUALITY-2509 @egorribun: required PostgreSQL lane runs this file.
        pytest.skip("push ownership concurrency requires PostgreSQL sessions")


async def _preference(user_id: uuid.UUID) -> list[str] | None:
    async with database.async_session() as session:
        row = (
            await session.execute(
                select(UserPushTopic).where(UserPushTopic.user_id == user_id)
            )
        ).scalar_one_or_none()
        return None if row is None else list(row.topics)


async def _claim(endpoint: str, user_id: uuid.UUID) -> object:
    payload = PushSubscriptionIn(
        endpoint=endpoint, keys={"p256dh": "p256dh", "auth": "auth"}
    )
    request = MagicMock()
    request.client = None
    request.headers.get.return_value = None
    async with database.async_session() as session:
        return await call_injected(
            notifications.subscribe,
            payload=payload,
            request=request,
            user=SimpleNamespace(id=user_id, role=None, locale=None),
            provides={"AsyncDatabaseSession": session},
        )


async def test_concurrent_claims_leave_the_row_bound_to_its_final_owner(
    user_factory,
) -> None:
    _require_postgres()
    first = await user_factory()
    second = await user_factory()
    async with database.async_session() as session:
        await synchronize_user_topics(session, user_id=first.id, topics=[EVENTS])
        await synchronize_user_topics(session, user_id=second.id, topics=[SYSTEM])
        await session.commit()
    endpoint = f"https://push.example.test/{uuid.uuid4().hex}"

    with (
        patch.object(
            notifications,
            "_validate_subscription_payload",
            new=AsyncMock(return_value=(endpoint, "p256dh", "auth")),
        ),
        patch.object(notifications, "enforce_rate_limit", new=AsyncMock()),
    ):
        results = await asyncio.gather(
            _claim(endpoint, first.id),
            _claim(endpoint, second.id),
            return_exceptions=True,
        )

    for result in results:
        if isinstance(result, BaseException):
            assert isinstance(result, HTTPException)
            assert result.status_code == 409
    assert any(not isinstance(result, BaseException) for result in results)
    async with database.async_session() as session:
        row = (
            await session.execute(
                select(PushSubscription).where(PushSubscription.endpoint == endpoint)
            )
        ).scalar_one()
    expected = {first.id: [EVENTS], second.id: [SYSTEM]}
    assert row.topics == expected[row.user_id]
    assert await _preference(first.id) == [EVENTS]
    assert await _preference(second.id) == [SYSTEM]


async def test_explicit_opt_out_is_stored_as_an_empty_json_list(user_factory) -> None:
    _require_postgres()
    user = await user_factory()
    async with database.async_session() as session:
        await synchronize_user_topics(session, user_id=user.id, topics=[])
        await session.commit()

    assert await _preference(user.id) == []
    async with database.async_session() as session:
        assert (
            await resolve_subscription_topics_for_user(
                session, user_id=user.id, requested_topics=None
            )
            == []
        )
