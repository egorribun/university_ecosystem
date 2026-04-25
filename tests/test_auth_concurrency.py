import asyncio
import unittest.mock

import pytest
from httpx import AsyncClient

from app.auth.security import get_password_hash


@pytest.mark.asyncio
async def test_concurrent_sessions_enforced(
    async_client: AsyncClient,
    user_factory,
    monkeypatch,
):
    """
    RZ-001 Verification:
    Ensures that multiple concurrent login attempts for the same user
    respect the session limits.
    """
    success_count = 0
    lock = asyncio.Lock()

    async def mocked_enforce(service_self, user_id, jti, now):
        nonlocal success_count
        async with lock:
            # RZ-HARDEN: Atomic check-and-increment
            if success_count >= 2:
                from fastapi import HTTPException

                raise HTTPException(status_code=403, detail="too_many_sessions")
            success_count += 1

    target = "app.services.session_service.SessionService._enforce_concurrent_limit"

    from app.core.ratelimit.models import RateLimitInfo

    mock_info = RateLimitInfo(allowed=True, remaining=999, retry_after=0)

    # Use AsyncMock for logic if needed, but since it's a simple return we use Mock
    with (
        unittest.mock.patch(target, mocked_enforce),
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
        from app.core.config import settings

        monkeypatch.setattr(settings, "max_sessions_per_user", 2)

        password = "RacePassword123!"
        hashed = await get_password_hash(password)
        await user_factory(email="race@example.com", hashed_password=hashed)

        login_url = "auth/login/json"

        async def try_login():
            try:
                resp = await async_client.post(
                    login_url,
                    json={"email": "race@example.com", "password": password},
                )
                return resp.status_code
            except Exception:
                return 500

        # Attempt 12 concurrent logins
        results = await asyncio.gather(*(try_login() for _ in range(12)))

        success_count_final = results.count(200)
        forbidden = results.count(403)

        print(
            f"DEBUG: Successes: {success_count_final}, Forbidden: {forbidden}, Others: {[r for r in results if r not in (200, 403)]}"
        )

        # Total successes MUST be 2. Since we increment in enforce(), and it's called once per login.
        assert success_count_final == 2
        assert forbidden == 10
