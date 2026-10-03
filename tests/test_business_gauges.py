"""Product gauges that are refreshed by the hourly scheduler."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

import app.models as models
from app.services import business_gauges
from app.tasks import cleanups


async def _session(db, user, *, seen: timedelta, revoked: bool = False, jti: str):
    now = datetime.now(UTC)
    db.add(
        models.ActiveSession(
            user_id=user.id,
            jti=jti,
            expires_at=now + timedelta(days=1),
            last_seen_at=now - seen,
            revoked_at=now if revoked else None,
        )
    )
    await db.flush()


@pytest.mark.asyncio
async def test_gauges_count_distinct_recent_users_and_mfa(db_session, user_factory):
    daily = await user_factory()
    weekly = await user_factory()
    revoked = await user_factory()
    stale = await user_factory()
    mfa_user = await user_factory(mfa_default_method="totp")
    await _session(db_session, daily, seen=timedelta(hours=1), jti="d1")
    await _session(db_session, daily, seen=timedelta(hours=2), jti="d2")
    await _session(db_session, weekly, seen=timedelta(days=3), jti="w1")
    await _session(db_session, revoked, seen=timedelta(hours=1), revoked=True, jti="r1")
    await _session(db_session, stale, seen=timedelta(days=30), jti="s1")

    with (
        patch.object(business_gauges, "set_active_users") as active,
        patch.object(business_gauges, "set_mfa_adoption") as mfa,
    ):
        values = await business_gauges.refresh_business_gauges(db=db_session)

    assert values["daily"] == 1  # one distinct user despite two sessions
    assert values["weekly"] == 2
    assert values["mfa"] >= 1
    assert mfa_user.mfa_default_method == "totp"
    active.assert_any_call(1, period="daily")
    active.assert_any_call(2, period="weekly")
    mfa.assert_called_once_with(values["mfa"])


@pytest.mark.asyncio
async def test_gauges_open_their_own_session_when_none_is_given(db_session):
    @asynccontextmanager
    async def factory():
        yield db_session

    with patch.object(business_gauges, "async_session", factory):
        values = await business_gauges.refresh_business_gauges()

    assert set(values) == {"daily", "weekly", "mfa"}


@pytest.mark.asyncio
async def test_scheduler_task_delegates_to_refresh():
    with patch.object(cleanups, "refresh_business_gauges") as refresh:
        await cleanups.refresh_business_gauges_task()
    refresh.assert_awaited_once_with()
