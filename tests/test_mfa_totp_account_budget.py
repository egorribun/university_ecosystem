"""Account-wide TOTP verification budget across rotated login challenges."""

from __future__ import annotations

import time
from uuid import uuid4

import pyotp
import pytest
from fastapi import status

from app.auth import mfa
from app.auth.security import get_password_hash
from app.core.config import settings
from app.core.ratelimit.strategies.memory import MemorySlidingWindowStrategy


@pytest.fixture
def enable_mfa_api_memory_rate_limiter(async_client, monkeypatch):
    """Exercise live API rate-limit dependencies without fakeredis Lua fallback."""
    # The async_client dependency starts the app while the conftest default is
    # disabled; enabling here activates request-time dependencies, not middleware
    # captured during app construction.
    assert not async_client.is_closed
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_storage_backend", "memory")
    monkeypatch.setattr(
        "app.auth.mfa.challenge.get_default_strategy",
        lambda namespace: MemorySlidingWindowStrategy(namespace),
    )


async def _login_for_access_token(async_client, user, password: str) -> str:
    response = await async_client.post(
        "/auth/login",
        data={"username": user.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == status.HTTP_200_OK, response.text
    token = response.cookies.get("access_token_v2")
    assert token is not None
    return token


async def _enroll_totp(async_client, user, password: str) -> pyotp.TOTP:
    token = await _login_for_access_token(async_client, user, password)
    headers = {"Authorization": f"Bearer {token}"}
    start = await async_client.post("/auth/mfa/totp/start", headers=headers)
    assert start.status_code == status.HTTP_200_OK, start.text
    payload = start.json()
    totp = pyotp.TOTP(payload["secret"])
    confirm = await async_client.post(
        "/auth/mfa/totp/confirm",
        headers=headers,
        json={
            "enrollment_id": payload["enrollment"]["id"],
            "code": totp.now(),
        },
    )
    assert confirm.status_code == status.HTTP_200_OK, confirm.text
    return totp


async def _issue_totp_login_challenge(async_client, user, password: str) -> str:
    response = await async_client.post(
        "/auth/login",
        data={"username": user.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == status.HTTP_202_ACCEPTED, response.text
    for method in response.json().get("methods", []):
        if method.get("method") == mfa.MFA_METHOD_TOTP:
            return method["challenge_token"]
    raise AssertionError("TOTP challenge was not issued")


async def _verify_totp(async_client, challenge_token: str, code: str):
    return await async_client.post(
        "/auth/mfa/verify",
        json={
            "method": mfa.MFA_METHOD_TOTP,
            "challenge_token": challenge_token,
            "code": code,
        },
    )


def _code_outside_current_window(totp: pyotp.TOTP) -> str:
    now = time.time()
    accepted = {totp.at(now, counter_offset=offset) for offset in range(-3, 4)}
    return next(
        f"{candidate:06d}"
        for candidate in range(1_000_000)
        if f"{candidate:06d}" not in accepted
    )


@pytest.mark.asyncio
async def test_totp_budget_is_shared_across_challenges_and_not_reset_by_success(
    async_client, user_factory, monkeypatch, enable_mfa_api_memory_rate_limiter
):
    monkeypatch.setattr(settings, "mfa_totp_attempt_limit", 2)
    password = f"{uuid4().hex}Aa1!"
    user = await user_factory(
        email=f"mfa-budget-{uuid4().hex}@example.com",
        hashed_password=await get_password_hash(password),
    )
    totp = await _enroll_totp(async_client, user, password)

    first_challenge = await _issue_totp_login_challenge(async_client, user, password)
    successful_code = totp.now()
    first_success = await _verify_totp(async_client, first_challenge, successful_code)
    assert first_success.status_code == status.HTTP_200_OK, first_success.text

    second_challenge = await _issue_totp_login_challenge(async_client, user, password)
    wrong_code = _code_outside_current_window(totp)
    wrong_code_response = await _verify_totp(async_client, second_challenge, wrong_code)
    assert wrong_code_response.status_code == status.HTTP_400_BAD_REQUEST

    # Issuing a new challenge and succeeding earlier in this window must not
    # reset the per-user budget. This valid-looking replay must be rejected by
    # the account budget before the per-enrollment replay check runs.
    third_challenge = await _issue_totp_login_challenge(async_client, user, password)
    blocked = await _verify_totp(async_client, third_challenge, successful_code)
    assert blocked.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    retry_after = int(blocked.headers["Retry-After"])
    assert 1 <= retry_after <= settings.mfa_challenge_ttl_seconds


@pytest.mark.asyncio
async def test_totp_hourly_budget_blocks_rotated_login_challenges_over_http(
    async_client, user_factory, monkeypatch, enable_mfa_api_memory_rate_limiter
):
    monkeypatch.setattr(settings, "mfa_totp_attempt_limit", 5)
    monkeypatch.setattr(settings, "mfa_totp_attempt_hourly_limit", 2)
    short_window_seconds = settings.mfa_challenge_ttl_seconds
    password = f"{uuid4().hex}Aa1!"
    user = await user_factory(
        email=f"mfa-hourly-budget-{uuid4().hex}@example.com",
        hashed_password=await get_password_hash(password),
    )
    totp = await _enroll_totp(async_client, user, password)
    wrong_code = _code_outside_current_window(totp)

    challenge_tokens: set[str] = set()
    for _ in range(settings.mfa_totp_attempt_hourly_limit):
        challenge_token = await _issue_totp_login_challenge(
            async_client, user, password
        )
        assert challenge_token not in challenge_tokens
        challenge_tokens.add(challenge_token)

        response = await _verify_totp(async_client, challenge_token, wrong_code)
        assert response.status_code == status.HTTP_400_BAD_REQUEST, response.text

    # The next independently issued challenge cannot reset the account budget.
    challenge_token = await _issue_totp_login_challenge(async_client, user, password)
    assert challenge_token not in challenge_tokens
    blocked = await _verify_totp(async_client, challenge_token, wrong_code)
    assert blocked.status_code == status.HTTP_429_TOO_MANY_REQUESTS, blocked.text
    assert int(blocked.headers["Retry-After"]) > short_window_seconds


@pytest.mark.asyncio
async def test_totp_budget_isolated_between_users(
    async_client, user_factory, monkeypatch, enable_mfa_api_memory_rate_limiter
):
    monkeypatch.setattr(settings, "mfa_totp_attempt_limit", 1)
    password = f"{uuid4().hex}Aa1!"
    users = [
        await user_factory(
            email=f"mfa-budget-isolated-{uuid4().hex}@example.com",
            hashed_password=await get_password_hash(password),
        )
        for _ in range(2)
    ]

    for user in users:
        totp = await _enroll_totp(async_client, user, password)
        challenge = await _issue_totp_login_challenge(async_client, user, password)
        response = await _verify_totp(async_client, challenge, totp.now())
        assert response.status_code == status.HTTP_200_OK, response.text


@pytest.mark.asyncio
async def test_totp_budget_retry_after_matches_sliding_window_expiry(monkeypatch):
    from types import SimpleNamespace

    from fastapi import HTTPException

    from app.auth.mfa.challenge import _enforce_totp_attempt_budget
    from app.core.ratelimit.strategies import memory as memory_strategy

    monkeypatch.setattr(settings, "mfa_totp_attempt_limit", 2)
    monkeypatch.setattr(settings, "mfa_challenge_ttl_seconds", 10)
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_storage_backend", "memory")

    clock = {"now": 100.0}
    monkeypatch.setattr(
        memory_strategy, "time", SimpleNamespace(time=lambda: clock["now"])
    )
    user_id = uuid4()

    await _enforce_totp_attempt_budget(user_id=user_id)
    clock["now"] = 101.25
    await _enforce_totp_attempt_budget(user_id=user_id)

    clock["now"] = 104.75
    with pytest.raises(HTTPException) as blocked:
        await _enforce_totp_attempt_budget(user_id=user_id)
    assert blocked.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert blocked.value.headers["Retry-After"] == "6"

    # The oldest entry expires first; the newer request still occupies one slot.
    clock["now"] = 110.01
    await _enforce_totp_attempt_budget(user_id=user_id)

    # The second old entry expires at its own window boundary as well.
    clock["now"] = 111.26
    await _enforce_totp_attempt_budget(user_id=user_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(("limit", "window"), [(0, 30), (2, 0)])
async def test_totp_account_budget_skips_limiter_when_disabled(
    monkeypatch, limit: int, window: int
) -> None:
    from app.auth.mfa import challenge as challenge_module

    monkeypatch.setattr(settings, "mfa_totp_attempt_limit", limit)
    monkeypatch.setattr(settings, "mfa_challenge_ttl_seconds", window)
    calls: list[dict[str, object]] = []

    async def record_rate_limit_call(**kwargs: object) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(challenge_module, "enforce_rate_limit", record_rate_limit_call)
    await challenge_module._enforce_totp_attempt_budget(user_id=uuid4())

    assert calls == []


@pytest.mark.asyncio
async def test_get_challenge_consumption_persists_state(
    db_session, user_factory
) -> None:
    from sqlalchemy import select

    from app.models import MfaChallenge
    from app.models.auth import ChallengeState

    user = await user_factory()
    issued = await mfa.issue_challenge(
        db_session,
        user_id=user.id,
        challenge_type="totp-verify",
        flow="login",
        session_identifier=f"coverage-{uuid4().hex}",
        client_fingerprint="f" * 64,
    )
    await db_session.commit()

    consumed = await mfa.get_challenge(
        db_session,
        token=issued.challenge_token,
        challenge_type="totp-verify",
        user_id=user.id,
        consume=True,
    )
    assert consumed.consumed_at is not None
    assert consumed.state == ChallengeState.CONSUMED
    await db_session.commit()

    persisted = await db_session.scalar(
        select(MfaChallenge)
        .where(MfaChallenge.id == issued.id)
        .execution_options(populate_existing=True)
    )
    assert persisted is not None
    assert persisted.consumed_at == consumed.consumed_at
    assert persisted.state == ChallengeState.CONSUMED


@pytest.mark.asyncio
async def test_purge_expired_challenges_uses_current_time_when_omitted(
    db_session, user_factory, monkeypatch
) -> None:
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select

    from app.auth.mfa import challenge as challenge_module
    from app.models import MfaChallenge

    now = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(challenge_module, "_utcnow", lambda: now)
    user = await user_factory()

    expired = await mfa.issue_challenge(
        db_session,
        user_id=user.id,
        challenge_type="totp-verify",
        flow="login",
        session_identifier=f"expired-{uuid4().hex}",
        client_fingerprint="f" * 64,
    )
    active = await mfa.issue_challenge(
        db_session,
        user_id=user.id,
        challenge_type="totp-verify",
        flow="login",
        session_identifier=f"active-{uuid4().hex}",
        client_fingerprint="f" * 64,
    )
    expired.challenge.expires_at = now - timedelta(seconds=1)
    active.challenge.expires_at = now + timedelta(minutes=1)
    await db_session.commit()

    purged = await mfa.purge_expired_challenges(db_session, grace_period_seconds=0)
    await db_session.commit()

    remaining_ids = set((await db_session.scalars(select(MfaChallenge.id))).all())
    assert purged == 1
    assert remaining_ids == {active.id}


@pytest.mark.asyncio
async def test_totp_budget_hourly_cap_stops_guessing_across_refilled_windows(
    monkeypatch,
):
    """AUD-176: a short window that refills each cycle must not allow endless guessing."""
    from types import SimpleNamespace

    from fastapi import HTTPException

    from app.auth.mfa.challenge import _enforce_totp_attempt_budget
    from app.core.ratelimit.strategies import memory as memory_strategy

    monkeypatch.setattr(settings, "mfa_totp_attempt_limit", 2)
    monkeypatch.setattr(settings, "mfa_challenge_ttl_seconds", 600)
    monkeypatch.setattr(settings, "mfa_totp_attempt_hourly_limit", 5, raising=False)
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_storage_backend", "memory")

    clock = {"now": 1000.0}
    monkeypatch.setattr(
        memory_strategy, "time", SimpleNamespace(time=lambda: clock["now"])
    )
    user_id = uuid4()

    # Three short windows: two attempts, then 601 seconds later two more, then one.
    await _enforce_totp_attempt_budget(user_id=user_id)
    await _enforce_totp_attempt_budget(user_id=user_id)
    clock["now"] = 1601.0
    await _enforce_totp_attempt_budget(user_id=user_id)
    await _enforce_totp_attempt_budget(user_id=user_id)
    clock["now"] = 2202.0
    await _enforce_totp_attempt_budget(user_id=user_id)

    # The sixth attempt fits the short window but exhausts the hourly cap.
    with pytest.raises(HTTPException) as blocked:
        await _enforce_totp_attempt_budget(user_id=user_id)
    assert blocked.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert int(blocked.value.headers["Retry-After"]) > 600

    # Once the oldest hourly entry leaves the window, attempts resume.
    clock["now"] = 4601.0
    await _enforce_totp_attempt_budget(user_id=user_id)


@pytest.mark.asyncio
async def test_totp_hourly_budget_zero_leaves_only_the_short_window(monkeypatch):
    """AUD-176 neighbour: a zero hourly limit disables only the hourly cap."""
    from fastapi import HTTPException

    from app.auth.mfa.challenge import _enforce_totp_attempt_budget

    monkeypatch.setattr(settings, "mfa_totp_attempt_limit", 2)
    monkeypatch.setattr(settings, "mfa_challenge_ttl_seconds", 600)
    monkeypatch.setattr(settings, "mfa_totp_attempt_hourly_limit", 0)
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_storage_backend", "memory")
    user_id = uuid4()

    await _enforce_totp_attempt_budget(user_id=user_id)
    await _enforce_totp_attempt_budget(user_id=user_id)
    with pytest.raises(HTTPException) as blocked:
        await _enforce_totp_attempt_budget(user_id=user_id)
    assert blocked.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert int(blocked.value.headers["Retry-After"]) <= 600
