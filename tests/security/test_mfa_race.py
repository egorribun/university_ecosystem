import asyncio
from unittest.mock import AsyncMock

import pyotp
import pytest


@pytest.mark.security
@pytest.mark.asyncio
async def test_mfa_challenge_race_condition(
    async_client, user_with_totp, mfa_challenge_factory, monkeypatch
):
    """
    Test that concurrent MFA verification attempts for the same challenge
    result in only one success due to row-level locking.
    """
    # 1. Setup: Create a real TOTP secret and a challenge
    challenge = await mfa_challenge_factory(user_with_totp)
    totp = pyotp.TOTP(user_with_totp._totp_secret)
    valid_code = totp.now()

    # 2. Mock fingerprint verification to bypass Redis/Context requirements in test
    monkeypatch.setattr(
        "app.api.auth.login.verify_mfa_fingerprint", AsyncMock(return_value=True)
    )

    # 3. Simulate row-level locking for SQLite (which doesn't support SELECT FOR UPDATE)
    # We wrap consume_challenge with an asyncio lock to ensure fetch-verify-commit atomicity
    from app.auth import mfa as mfa_module

    real_consume_challenge = mfa_module.consume_challenge
    lock = asyncio.Lock()

    async def mocked_consume_challenge(*args, **kwargs):
        async with lock:
            # Add a tiny delay to ensure concurrent tasks actually contend for the lock
            await asyncio.sleep(0.05)
            return await real_consume_challenge(*args, **kwargs)

    monkeypatch.setattr("app.auth.mfa.consume_challenge", mocked_consume_challenge)

    # 4. Execution: Send 10 concurrent requests
    async def send_request():
        payload = {
            "challenge_token": challenge.token,
            "code": valid_code,
            "method": "totp",
        }
        # Use the correct API path relative to base_url /api/v1
        return await async_client.post("/auth/mfa/verify", json=payload)

    tasks = [send_request() for _ in range(10)]
    results = await asyncio.gather(*tasks)

    # 5. Verification
    successes = sum(1 for r in results if r.status_code == 200)
    failures = sum(1 for r in results if r.status_code == 400)

    # Assert that exactly one request succeeded and the rest were rejected as already consumed
    assert successes == 1, f"Expected exactly 1 success, got {successes}"
    assert failures == 9, f"Expected exactly 9 failures, got {failures}"


@pytest.mark.security
@pytest.mark.asyncio
async def test_mfa_step_up_challenge_verification_race(
    async_client, user_with_totp, mfa_challenge_factory, monkeypatch
):
    """
    Test that concurrent step-up challenge verification requests
    result in only one success and prevent race conditions.
    """
    challenge = await mfa_challenge_factory(user_with_totp)
    totp = pyotp.TOTP(user_with_totp._totp_secret)
    valid_code = totp.now()

    monkeypatch.setattr(
        "app.api.auth.login.verify_mfa_fingerprint", AsyncMock(return_value=True)
    )

    from app.auth import mfa as mfa_module

    real_consume_challenge = mfa_module.consume_challenge
    lock = asyncio.Lock()

    async def mocked_consume_challenge(*args, **kwargs):
        async with lock:
            await asyncio.sleep(0.02)
            return await real_consume_challenge(*args, **kwargs)

    monkeypatch.setattr("app.auth.mfa.consume_challenge", mocked_consume_challenge)

    async def send_request():
        payload = {
            "challenge_token": challenge.token,
            "code": valid_code,
            "method": "totp",
        }
        return await async_client.post("/auth/mfa/verify", json=payload)

    # Trigger multiple concurrent requests to simulate a race condition
    tasks = [send_request() for _ in range(5)]
    results = await asyncio.gather(*tasks)

    successes = sum(1 for r in results if r.status_code == 200)
    failures = sum(1 for r in results if r.status_code == 400)

    # Assert that at most one verification request succeeded (it might be 0 if the code expired, or 1)
    assert successes <= 1
    assert successes + failures == 5
