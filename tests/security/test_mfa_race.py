"""AUD-426: one MFA challenge is consumed once under real PostgreSQL contention.

The requests go through the application's HTTP stack (httpx ASGI transport) and
each request opens its own database session.  Single use is enforced by the
PostgreSQL row locks taken in ``consume_challenge`` (the User row, then the
challenge row) and by the post-lock re-read of the challenge, not by a
Python-level ``asyncio.Lock``.  SQLite has no ``SELECT ... FOR UPDATE``, so these
tests are opt-in and run only when DATABASE_URL names PostgreSQL.
"""

from __future__ import annotations

import asyncio
import os

import pyotp
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.models as models
from tests.fixtures.auth.auth_fixtures import create_access_token

_DATABASE_URL = os.getenv("DATABASE_URL", "")
CONCURRENT_REQUESTS = 10

pytestmark = [
    pytest.mark.security,
    pytest.mark.integration,
    pytest.mark.skipif(
        not _DATABASE_URL.startswith("postgresql"),
        reason="AUD-426 requires a PostgreSQL DATABASE_URL (row-lock contention)",
    ),
]


async def _consumed_step_up_challenges(
    db_session: AsyncSession, user_id: object
) -> int:
    rows = (
        (
            await db_session.execute(
                select(models.MfaChallenge).where(
                    models.MfaChallenge.user_id == user_id,
                    models.MfaChallenge.flow == "step_up",
                    models.MfaChallenge.consumed_at.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    return len(rows)


async def test_mfa_challenge_race_condition(
    async_client: AsyncClient,
    user_with_totp,
    mfa_challenge_factory,
) -> None:
    """Concurrent verification of one login challenge yields exactly one success."""
    challenge = await mfa_challenge_factory(user_with_totp)
    payload = {
        "challenge_token": challenge.token,
        "code": pyotp.TOTP(user_with_totp._totp_secret).now(),
        "method": "totp",
    }

    results = await asyncio.gather(
        *(
            async_client.post("/auth/mfa/verify", json=payload)
            for _ in range(CONCURRENT_REQUESTS)
        )
    )

    statuses = [response.status_code for response in results]
    assert statuses.count(200) == 1, statuses
    assert statuses.count(400) == CONCURRENT_REQUESTS - 1, statuses


async def test_mfa_step_up_challenge_verification_race(
    async_client: AsyncClient,
    user_with_totp,
    db_session: AsyncSession,
) -> None:
    """Concurrent verification of one step-up challenge consumes it exactly once."""
    access_token, _session = await create_access_token(
        str(user_with_totp.id), db_session
    )
    headers = {"Authorization": f"Bearer {access_token}"}
    started = await async_client.post("/auth/mfa/step-up", headers=headers)
    assert started.status_code == 202, started.text
    totp_entry = next(
        method for method in started.json()["methods"] if method["method"] == "totp"
    )
    payload = {
        "challenge_token": totp_entry["challenge_token"],
        "code": pyotp.TOTP(user_with_totp._totp_secret).now(),
        "method": "totp",
    }

    results = await asyncio.gather(
        *(
            async_client.post("/auth/mfa/verify", json=payload, headers=headers)
            for _ in range(CONCURRENT_REQUESTS)
        )
    )

    statuses = [response.status_code for response in results]
    assert statuses.count(200) == 1, statuses
    assert statuses.count(400) == CONCURRENT_REQUESTS - 1, statuses
    assert await _consumed_step_up_challenges(db_session, user_with_totp.id) == 1
