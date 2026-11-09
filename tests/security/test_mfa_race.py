"""AUD-426: one MFA challenge is consumed once under real PostgreSQL contention.

The requests travel over a real loopback TCP socket: the application runs under
a uvicorn server started inside the test loop, and every request is an HTTP
request from an ``httpx`` client, so each one is parsed by the server and opens
its own database session.  Single use is enforced by the PostgreSQL row locks
taken in ``consume_challenge`` (the User row, then the challenge row) and by the
post-lock re-read of the challenge.  No Python-level ``asyncio.Lock`` serialises
the requests.  SQLite has no ``SELECT ... FOR UPDATE``, so these tests are
opt-in and run only when DATABASE_URL names PostgreSQL.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator

import httpx
import pyotp
import pytest
import pytest_asyncio
import uvicorn
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.models as models
from tests.fixtures.auth.auth_fixtures import create_access_token
from tests.fixtures.infrastructure.infrastructure import _configure_csrf_client

_DATABASE_URL = os.getenv("DATABASE_URL", "")
CONCURRENT_REQUESTS = 10
_SERVER_START_TIMEOUT_SECONDS = 10.0

pytestmark = [
    pytest.mark.security,
    pytest.mark.integration,
    pytest.mark.skipif(
        not _DATABASE_URL.startswith("postgresql"),
        reason="AUD-426 requires a PostgreSQL DATABASE_URL (row-lock contention)",
    ),
]


@pytest_asyncio.fixture
async def live_client(app) -> AsyncIterator[httpx.AsyncClient]:
    """HTTP client for the application served on a real loopback socket."""
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=0,
        lifespan="off",
        access_log=False,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    serving = asyncio.create_task(server.serve())
    try:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + _SERVER_START_TIMEOUT_SECONDS
        while not server.started:
            if serving.done() or loop.time() > deadline:
                raise RuntimeError("uvicorn did not start for the AUD-426 race test")
            await asyncio.sleep(0.01)
        sockets = server.servers[0].sockets
        port = sockets[0].getsockname()[1]
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{port}/api/v1",
            follow_redirects=True,
            timeout=httpx.Timeout(30.0),
        ) as client:
            await _configure_csrf_client(client, "/auth/csrf-cookie")
            yield client
    finally:
        server.should_exit = True
        await serving


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
    async_client: httpx.AsyncClient,
    live_client: httpx.AsyncClient,
    user_with_totp,
    mfa_challenge_factory,
) -> None:
    """Concurrent verification of one login challenge yields exactly one success."""
    # The factory binds the challenge to the pre-auth cookie and user agent of
    # the ASGI client; the live socket client must present the same identity.
    challenge = await mfa_challenge_factory(user_with_totp)
    live_client.headers["user-agent"] = async_client.headers["user-agent"]
    live_client.cookies.set(
        "mfa_pre_auth_v1", async_client.cookies["mfa_pre_auth_v1"], path="/"
    )
    payload = {
        "challenge_token": challenge.token,
        "code": pyotp.TOTP(user_with_totp._totp_secret).now(),
        "method": "totp",
    }

    results = await asyncio.gather(
        *(
            live_client.post("/auth/mfa/verify", json=payload)
            for _ in range(CONCURRENT_REQUESTS)
        )
    )

    statuses = [response.status_code for response in results]
    assert statuses.count(200) == 1, statuses
    assert statuses.count(400) == CONCURRENT_REQUESTS - 1, statuses


async def test_mfa_step_up_challenge_verification_race(
    live_client: httpx.AsyncClient,
    user_with_totp,
    db_session: AsyncSession,
) -> None:
    """Concurrent HTTP verification of one step-up challenge consumes it once."""
    access_token, _session = await create_access_token(
        str(user_with_totp.id), db_session
    )
    headers = {"Authorization": f"Bearer {access_token}"}
    started = await live_client.post("/auth/mfa/step-up", headers=headers)
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
            live_client.post("/auth/mfa/verify", json=payload, headers=headers)
            for _ in range(CONCURRENT_REQUESTS)
        )
    )

    statuses = [response.status_code for response in results]
    assert statuses.count(200) == 1, statuses
    assert statuses.count(400) == CONCURRENT_REQUESTS - 1, statuses
    assert await _consumed_step_up_challenges(db_session, user_with_totp.id) == 1
