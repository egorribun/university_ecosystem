import asyncio
import datetime as dt
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.models import PasswordResetToken, User
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


@pytest.mark.asyncio
async def test_forgot_password_limits_active_tokens(
    async_client, user_factory, db_session
):
    user = await user_factory(email="limit-reset@example.com")

    iterations = settings.password_reset_max_active_tokens + 2
    for _ in range(iterations):
        response = await async_client.post(
            "/password/forgot", json={"email": user.email}
        )
        assert response.status_code == 200

    active = await db_session.execute(
        select(func.count())
        .select_from(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used.is_(False),
        )
    )
    active_count = active.scalar_one()

    assert active_count <= max(1, settings.password_reset_max_active_tokens)


@pytest.mark.asyncio
async def test_cleanup_stale_password_reset_tokens_no_args_and_zero_deleted(db_session):
    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__.return_value = db_session
    mock_factory.return_value.__aexit__ = AsyncMock()

    with patch("app.services.password_reset_cleanup.async_session", mock_factory):
        deleted = await cleanup_stale_password_reset_tokens()
        assert deleted == 0


@pytest.mark.asyncio
async def test_password_reset_cleanup_scheduler_cancel_and_error(monkeypatch):
    async def fake_cleanup_cancel(*args, **kwargs):
        raise asyncio.CancelledError()

    monkeypatch.setattr(
        password_reset_cleanup,
        "cleanup_stale_password_reset_tokens",
        fake_cleanup_cancel,
    )

    real_sleep = asyncio.sleep

    async def fast_sleep(_: float):
        await real_sleep(0.0001)

    monkeypatch.setattr(password_reset_cleanup.asyncio, "sleep", fast_sleep)

    stop = await start_password_reset_cleanup_scheduler()
    await real_sleep(0.02)
    await stop()
    await stop()


@pytest.mark.asyncio
async def test_password_reset_cleanup_scheduler_other_error(monkeypatch):
    async def fake_cleanup_error(*args, **kwargs):
        raise ValueError("db error")

    monkeypatch.setattr(
        password_reset_cleanup,
        "cleanup_stale_password_reset_tokens",
        fake_cleanup_error,
    )

    real_sleep = asyncio.sleep

    async def fast_sleep(_: float):
        await real_sleep(0.0001)

    monkeypatch.setattr(password_reset_cleanup.asyncio, "sleep", fast_sleep)

    stop = await start_password_reset_cleanup_scheduler()
    await real_sleep(0.02)
    await stop()
