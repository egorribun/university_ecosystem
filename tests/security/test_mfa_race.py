import asyncio

import pytest


@pytest.mark.skip(reason="Requires complex MFA/TOTP fixtures not yet implemented")
@pytest.mark.asyncio
async def test_mfa_challenge_race_condition(async_client):
    """
    Test that multiple parallel requests to consume the same challenge fail.
    Only one should succeed.

    Note: This test requires MFA challenge fixtures which are not yet available.
    The test verifies race condition protection in the MFA verification flow.
    """
    # This test needs complex setup:
    # 1. User with TOTP enabled
    # 2. Valid MFA challenge token
    # 3. Proper test isolation for race conditions

    challenge_token = "test-challenge-token"

    async def call_verify():
        return await async_client.post(
            "/auth/mfa/verify",
            json={
                "challenge_token": challenge_token,
                "method": "totp",
                "code": "123456",
            },
        )

    # Trigger 5 parallel requests
    results = await asyncio.gather(
        *[call_verify() for _ in range(5)], return_exceptions=True
    )

    # Analyze results: only ONE should potentially be "Processing" (not 400 Invalid)
    status_codes = [r.status_code for r in results if not isinstance(r, Exception)]

    # If the check is atomic, we shouldn't see multiple 200/202 responses.
    success_or_processing = [s for s in status_codes if s < 400]
    assert len(success_or_processing) <= 1
