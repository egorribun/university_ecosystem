import asyncio
import datetime as dt

import pytest
from sqlalchemy import select

from app.models.models import PasswordResetToken, User
from app.services import password_reset_cleanup
from app.services.password_reset_cleanup import (
    PasswordResetCleanupConfig,
    cleanup_stale_password_reset_tokens,
    start_password_reset_cleanup_scheduler,
)
from app.utils.email import RESET_TOKEN_EXPIRY_MINUTES


@pytest.mark.asyncio
async def test_cleanup_stale_password_reset_tokens_respects_retention(db_session):
    now = dt.datetime.now(dt.UTC)

    user = User(email="reset-cleanup@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()

    expired = PasswordResetToken(
        user_id=user.id,
        token_hash="expired",
        expires_at=now - dt.timedelta(minutes=1),
        used=False,
        created_at=now - dt.timedelta(minutes=RESET_TOKEN_EXPIRY_MINUTES + 5),
    )
    used_old = PasswordResetToken(
        user_id=user.id,
        token_hash="used-old",
        expires_at=now + dt.timedelta(minutes=10),
        used=True,
        created_at=now - dt.timedelta(minutes=60),
    )
    used_recent = PasswordResetToken(
        user_id=user.id,
        token_hash="used-recent",
        expires_at=now + dt.timedelta(minutes=10),
        used=True,
        created_at=now - dt.timedelta(minutes=10),
    )
    active = PasswordResetToken(
        user_id=user.id,
        token_hash="active",
        expires_at=now + dt.timedelta(minutes=30),
        used=False,
    )

    db_session.add_all([expired, used_old, used_recent, active])
    await db_session.commit()

    removed = await cleanup_stale_password_reset_tokens(now=now, retention_minutes=30)
    assert removed == 2

    remaining_tokens = await db_session.execute(select(PasswordResetToken.token_hash))
    remaining = {row[0] for row in remaining_tokens}
    assert remaining == {"used-recent", "active"}


@pytest.mark.asyncio
async def test_cleanup_stale_password_reset_tokens_default_retention(db_session):
    now = dt.datetime.now(dt.UTC)

    user = User(email="reset-default@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()

    expired = PasswordResetToken(
        user_id=user.id,
        token_hash="expired-default",
        expires_at=now - dt.timedelta(minutes=RESET_TOKEN_EXPIRY_MINUTES + 1),
        used=False,
        created_at=now - dt.timedelta(minutes=RESET_TOKEN_EXPIRY_MINUTES + 1),
    )
    db_session.add(expired)
    await db_session.commit()

    removed = await cleanup_stale_password_reset_tokens(now=now)
    assert removed == 1

    remaining_tokens = await db_session.execute(select(PasswordResetToken.token_hash))
    assert list(remaining_tokens) == []


@pytest.mark.asyncio
async def test_start_password_reset_cleanup_scheduler(monkeypatch):
    calls: list[int] = []
    event = asyncio.Event()

    async def fake_cleanup(*, retention_minutes: int, **_: object) -> None:
        calls.append(retention_minutes)
        event.set()

    monkeypatch.setattr(
        password_reset_cleanup, "cleanup_stale_password_reset_tokens", fake_cleanup
    )

    real_asyncio_sleep = asyncio.sleep

    async def fast_sleep(_: float) -> None:
        await real_asyncio_sleep(0)

    monkeypatch.setattr(password_reset_cleanup.asyncio, "sleep", fast_sleep)

    config = PasswordResetCleanupConfig(
        interval_seconds=1, retention_minutes=RESET_TOKEN_EXPIRY_MINUTES
    )
    stop = await start_password_reset_cleanup_scheduler(config=config)
    await asyncio.wait_for(event.wait(), timeout=0.1)
    await stop()

    assert calls
    assert calls[0] == config.normalized_retention_minutes()
