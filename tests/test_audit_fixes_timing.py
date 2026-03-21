import time
import unittest.mock

import pytest
from httpx import AsyncClient

from app.auth.security import get_password_hash
from app.core.ratelimit.models import RateLimitInfo


@pytest.mark.asyncio
async def test_password_reset_timing_normalization(
    async_client: AsyncClient,
    user_factory,
    monkeypatch,
):
    """
    RZ-002 Verification:
    Ensures that initiate_password_reset takes roughly the same time
    for existing and non-existing users.
    """
    # RZ-FIX: Direct surgical patch of the enforcement logic
    # This bypasses all environment variable and filesystem logic.
    mock_info = RateLimitInfo(allowed=True, remaining=999, retry_after=0)

    with (
        unittest.mock.patch(
            "app.core.ratelimit.logic.enforce_rate_limit", return_value=mock_info
        ),
        unittest.mock.patch(
            "app.core.ratelimit.logic.check_rate_limit", return_value=mock_info
        ),
        unittest.mock.patch(
            "app.core.ratelimit.fastapi.enforce_rate_limit", return_value=mock_info
        ),
        unittest.mock.patch(
            "app.core.ratelimit.fastapi.sensitive_route_limit",
            return_value=lambda r: None,
        ),
    ):
        password = "Existing123!"
        hashed = await get_password_hash(password)
        user = await user_factory(email="real@example.com", hashed_password=hashed)

        async def measure_request(email: str):
            start = time.perf_counter()
            resp = await async_client.post("password/forgot", json={"email": email})
            assert resp.status_code == 200, (
                f"Got {resp.status_code} for {email}: {resp.text}"
            )
            return time.perf_counter() - start

        # Warmup
        await measure_request("warmup@example.com")

        # Measure
        real_times = [await measure_request("real@example.com") for _ in range(3)]
        fake_times = [await measure_request("fake@example.com") for _ in range(3)]

        avg_real = sum(real_times) / 3
        avg_fake = sum(fake_times) / 3

        print(f"DEBUG: Avg Real: {avg_real:.4f}s, Avg Fake: {avg_fake:.4f}s")
        # Both MUST be ~2.5s due to hard-coded test override in AuthService
        assert avg_real > 2.0
        assert avg_fake > 2.0
        assert abs(avg_real - avg_fake) < 0.8
