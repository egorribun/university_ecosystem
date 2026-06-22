import asyncio
import datetime as dt
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app.models import EmailChangeToken, User
from app.services import email_change_cleanup
from app.services.email_change_cleanup import (
    EmailChangeCleanupConfig,
    cleanup_stale_email_change_tokens,
    start_email_change_cleanup_scheduler,
)
from app.utils.email import RESET_TOKEN_EXPIRY_MINUTES

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_cleanup_stale_email_change_tokens_respects_retention(db_session):
    now = dt.datetime.now(dt.UTC)

    user = User(email="email-cleanup@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()

    expired_recent = EmailChangeToken(
        user_id=user.id,
        new_email="expired@example.com",
        token_hash="expired",
        expires_at=now - dt.timedelta(minutes=1),
        used=False,
        created_at=now - dt.timedelta(minutes=20),
    )
    very_old_unused = EmailChangeToken(
        user_id=user.id,
        new_email="very-old@example.com",
        token_hash="very-old",
        expires_at=now + dt.timedelta(minutes=10),
        used=False,
        created_at=now - dt.timedelta(minutes=40),
    )
    old_used = EmailChangeToken(
        user_id=user.id,
        new_email="old-used@example.com",
        token_hash="old-used",
        expires_at=now + dt.timedelta(minutes=5),
        used=True,
        created_at=now - dt.timedelta(minutes=35),
    )
    recent_active = EmailChangeToken(
        user_id=user.id,
        new_email="recent@example.com",
        token_hash="recent",
        expires_at=now + dt.timedelta(minutes=30),
        used=False,
        created_at=now - dt.timedelta(minutes=5),
    )

    db_session.add_all([expired_recent, very_old_unused, old_used, recent_active])
    await db_session.commit()

    cleaned = await cleanup_stale_email_change_tokens(now=now, retention_minutes=30)
    assert cleaned == 3

    db_session.expire_all()
    remaining = await db_session.execute(
        select(EmailChangeToken).order_by(EmailChangeToken.id)
    )
    tokens = remaining.scalars().all()
    assert {token.token_hash for token in tokens} == {"expired", "recent"}

    expired_record = next(token for token in tokens if token.token_hash == "expired")
    assert expired_record.used is True

    recent_record = next(token for token in tokens if token.token_hash == "recent")
    assert recent_record.used is False


async def test_cleanup_stale_email_change_tokens_default_retention(db_session):
    now = dt.datetime.now(dt.UTC)

    user = User(email="email-cleanup-default@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()

    stale = EmailChangeToken(
        user_id=user.id,
        new_email="stale@example.com",
        token_hash="stale",
        expires_at=now - dt.timedelta(minutes=RESET_TOKEN_EXPIRY_MINUTES + 1),
        used=False,
        created_at=now - dt.timedelta(minutes=RESET_TOKEN_EXPIRY_MINUTES + 1),
    )
    db_session.add(stale)
    await db_session.commit()

    cleaned = await cleanup_stale_email_change_tokens(now=now)
    assert cleaned >= 1  # May clean tokens from other tests too

    db_session.expire_all()
    remaining = await db_session.execute(
        select(EmailChangeToken.token_hash).where(
            EmailChangeToken.token_hash == "stale"
        )
    )
    assert list(remaining) == []


async def test_start_email_change_cleanup_scheduler(monkeypatch):
    calls: list[int] = []
    event = asyncio.Event()

    async def fake_cleanup(*, retention_minutes: int, **_: object) -> int:
        calls.append(retention_minutes)
        event.set()
        return 0

    monkeypatch.setattr(
        email_change_cleanup, "cleanup_stale_email_change_tokens", fake_cleanup
    )

    real_asyncio_sleep = asyncio.sleep

    async def fast_sleep(_: float) -> None:
        await real_asyncio_sleep(0)

    monkeypatch.setattr(email_change_cleanup.asyncio, "sleep", fast_sleep)

    config = EmailChangeCleanupConfig(
        interval_seconds=1, retention_minutes=RESET_TOKEN_EXPIRY_MINUTES
    )
    stop = await start_email_change_cleanup_scheduler(config=config)
    await asyncio.wait_for(event.wait(), timeout=0.1)
    await stop()

    assert calls
    assert calls[0] == config.normalized_retention_minutes()


async def test_cleanup_stale_email_change_tokens_no_args_and_zero_deleted(db_session):
    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__.return_value = db_session
    mock_factory.return_value.__aexit__ = AsyncMock()

    with patch("app.services.email_change_cleanup.async_session", mock_factory):
        cleaned = await cleanup_stale_email_change_tokens()
        assert cleaned == 0


async def test_email_change_cleanup_scheduler_cancel_and_error(monkeypatch):
    async def fake_cleanup_cancel(*args, **kwargs):
        raise asyncio.CancelledError()

    monkeypatch.setattr(
        email_change_cleanup, "cleanup_stale_email_change_tokens", fake_cleanup_cancel
    )

    real_sleep = asyncio.sleep

    async def fast_sleep(_: float):
        await real_sleep(0.0001)

    monkeypatch.setattr(email_change_cleanup.asyncio, "sleep", fast_sleep)

    stop = await start_email_change_cleanup_scheduler()
    await real_sleep(0.02)
    await stop()
    await stop()


async def test_email_change_cleanup_scheduler_other_error(monkeypatch):
    async def fake_cleanup_error(*args, **kwargs):
        raise ValueError("db error")

    monkeypatch.setattr(
        email_change_cleanup, "cleanup_stale_email_change_tokens", fake_cleanup_error
    )

    real_sleep = asyncio.sleep

    async def fast_sleep(_: float):
        await real_sleep(0.0001)

    monkeypatch.setattr(email_change_cleanup.asyncio, "sleep", fast_sleep)

    stop = await start_email_change_cleanup_scheduler()
    await real_sleep(0.02)
    await stop()
