import asyncio
import datetime as dt
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pyotp
import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select

from app.auth import mfa
from app.auth.security import get_password_hash
from app.core.config import settings
from app.models import ActiveSession


@pytest.fixture(autouse=True)
def _set_query_budget(async_client):
    async_client.headers["X-Query-Budget"] = "15"


async def _login(
    async_client: AsyncClient,
    *,
    email: str,
    password: str,
    user_agent: str = "pytest-agent/1.0",
    forwarded_for: str | None = "203.0.113.42",
) -> dict[str, str]:
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": user_agent,
    }
    if forwarded_for:
        headers["X-Forwarded-For"] = forwarded_for
    response = await async_client.post(
        "/auth/login",
        data={"username": email, "password": password},
        headers=headers,
    )
    if response.status_code == status.HTTP_202_ACCEPTED:
        pytest.fail(
            "Login returned an MFA challenge; this helper expects a non-MFA user"
        )
    assert response.status_code == 200
    token = response.cookies.get("access_token_v2")
    return {
        "Authorization": f"Bearer {token}",
        "User-Agent": user_agent,
        "X-Query-Budget": "15",
    }


async def _enable_totp(async_client: AsyncClient, headers: dict[str, str]) -> str:
    start = await async_client.post("/auth/mfa/totp/start", headers=headers)
    assert start.status_code == status.HTTP_200_OK, start.text
    data = start.json()
    secret = data["secret"]
    enrollment_id = data["enrollment"]["id"]
    totp = pyotp.TOTP(secret)
    confirm = await async_client.post(
        "/auth/mfa/totp/confirm",
        headers=headers,
        json={"enrollment_id": enrollment_id, "code": totp.now()},
    )
    assert confirm.status_code == status.HTTP_200_OK, confirm.text
    return cast(str, secret)


async def _complete_step_up(
    async_client: AsyncClient, headers: dict[str, str], secret: str
) -> dict:
    challenge = await async_client.post("/auth/mfa/step-up", headers=headers)
    assert challenge.status_code == status.HTTP_202_ACCEPTED, challenge.text
    payload = challenge.json()
    assert payload["default_method"] == mfa.MFA_METHOD_TOTP
    assert len(payload["methods"]) == 1
    method = payload["methods"][0]
    assert method["method"] == mfa.MFA_METHOD_TOTP
    code = pyotp.TOTP(secret).now()
    verify = await async_client.post(
        "/auth/mfa/verify",
        headers=headers,
        json={
            "method": mfa.MFA_METHOD_TOTP,
            "challenge_token": method["challenge_token"],
            "code": code,
        },
    )
    assert verify.status_code == status.HTTP_200_OK, verify.text
    token = verify.cookies.get("access_token_v2")
    assert token is not None, "access_token_v2 cookie missing after MFA verify"
    headers["Authorization"] = f"Bearer {token}"
    return cast(dict[Any, Any], payload)


@pytest.mark.asyncio
async def test_list_sessions_includes_current_session_metadata(
    async_client: AsyncClient,
    user_factory,
    db_session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "trusted_proxies_list", ["testserver", "127.0.0.1"])
    password = "Sessions123!"
    hashed = await get_password_hash(password)
    user = await user_factory(email="sessions@example.com", hashed_password=hashed)

    headers = await _login(
        async_client,
        email=user.email,
        password=password,
        user_agent="pytest-agent/2.0",
        forwarded_for="198.51.100.5",
    )

    response = await async_client.get("/auth/sessions", headers=headers)
    assert response.status_code == 200
    sessions = response.json()
    assert isinstance(sessions, list)
    assert len(sessions) == 1
    entry = sessions[0]
    assert entry["user_id"] == str(user.id)
    assert entry["is_current"] is True
    assert entry["ip_address"] == "198.51.100.5"
    assert entry["user_agent"] == "pytest-agent/2.0"
    assert entry["revoked_at"] is None
    assert entry["last_seen_at"] is not None


@pytest.mark.asyncio
async def test_admin_can_list_sessions_for_other_user(
    async_client: AsyncClient,
    user_factory,
    db_session,
):
    password = "AdminSessions42!"
    admin = await user_factory(
        email="admin@example.com",
        hashed_password=await get_password_hash(password),
        role="admin",
    )
    target = await user_factory(email="target@example.com")
    session = ActiveSession(
        user_id=target.id,
        jti="target-session",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        ip_address="192.0.2.10",
        user_agent="target-agent",
        last_seen_at=datetime.now(UTC),
    )
    db_session.add(session)
    await db_session.commit()

    headers = await _login(async_client, email=admin.email, password=password)
    headers["X-Disable-Query-Budget"] = "true"

    response = await async_client.get(
        f"/auth/sessions?user_id={target.id}",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["jti"] == "target-session"
    assert data[0]["is_current"] is False


@pytest.mark.asyncio
async def test_non_admin_cannot_list_sessions_for_other_user(
    async_client: AsyncClient,
    user_factory,
    db_session,
):
    password = "Forbidden42!"
    actor = await user_factory(
        email="actor@example.com", hashed_password=await get_password_hash(password)
    )
    other = await user_factory(email="other@example.com")
    db_session.add(
        ActiveSession(
            user_id=other.id,
            jti="other-session",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    await db_session.commit()

    headers = await _login(async_client, email=actor.email, password=password)

    response = await async_client.get(
        f"/auth/sessions?user_id={other.id}",
        headers=headers,
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Access denied"


@pytest.mark.asyncio
async def test_revoke_session_removes_from_listing(
    async_client: AsyncClient,
    user_factory,
    db_session,
):
    password = "Revoke123!"
    user = await user_factory(
        email="revoker@example.com", hashed_password=await get_password_hash(password)
    )
    other_session = ActiveSession(
        user_id=user.id,
        jti="revocable",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        last_seen_at=datetime.now(UTC),
    )
    db_session.add(other_session)
    await db_session.commit()

    headers = await _login(async_client, email=user.email, password=password)

    response = await async_client.get("/auth/sessions", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 2

    response = await async_client.delete(
        f"/auth/sessions/{other_session.id}", headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["revoked_at"] is not None
    assert body["is_current"] is False

    listing = await async_client.get("/auth/sessions", headers=headers)
    assert listing.status_code == 200
    sessions = listing.json()
    assert len(sessions) == 1
    assert all(entry["jti"] != "revocable" for entry in sessions)

    deleted = await db_session.execute(
        select(ActiveSession.revoked_at).where(ActiveSession.id == other_session.id)
    )
    assert deleted.scalar_one() is not None


@pytest.mark.asyncio
async def test_admin_can_revoke_foreign_session(
    async_client: AsyncClient,
    user_factory,
    db_session,
):
    password = "AdminDelete7!"
    admin = await user_factory(
        email="admin-del@example.com",
        hashed_password=await get_password_hash(password),
        role="admin",
    )
    target = await user_factory(email="victim@example.com")
    doomed = ActiveSession(
        user_id=target.id,
        jti="doomed",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(doomed)
    await db_session.commit()

    headers = await _login(async_client, email=admin.email, password=password)

    response = await async_client.delete(f"/auth/sessions/{doomed.id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["revoked_at"] is not None

    deleted = await db_session.execute(
        select(ActiveSession.revoked_at).where(ActiveSession.id == doomed.id)
    )
    assert deleted.scalar_one() is not None


@pytest.mark.asyncio
async def test_logout_removes_session_immediately(
    async_client: AsyncClient,
    user_factory,
    db_session,
):
    password = "Logout123!"
    user = await user_factory(
        email="logout@example.com", hashed_password=await get_password_hash(password)
    )

    headers = await _login(async_client, email=user.email, password=password)

    response = await async_client.get("/auth/sessions", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 1

    logout_response = await async_client.post("/auth/logout", headers=headers)
    assert logout_response.status_code == 200

    remaining = await db_session.execute(
        select(ActiveSession.id)
        .where(ActiveSession.user_id == user.id)
        .where(ActiveSession.revoked_at.is_(None))
    )
    assert remaining.scalars().all() == []

    new_headers = await _login(async_client, email=user.email, password=password)
    refreshed = await async_client.get("/auth/sessions", headers=new_headers)
    assert refreshed.status_code == 200
    refreshed_sessions = refreshed.json()
    assert len(refreshed_sessions) == 1
    assert refreshed_sessions[0]["is_current"] is True


@pytest.mark.asyncio
async def test_revoke_session_requires_step_up(
    async_client: AsyncClient,
    user_factory,
    db_session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "mfa_step_up_ttl_seconds", 60)
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "max_sessions_per_user", 10)
    password = "StepUpSessions123!"
    hashed = await get_password_hash(password)
    user = await user_factory(
        email="stepup-sessions@example.com", hashed_password=hashed
    )

    headers = await _login(async_client, email=user.email, password=password)
    secret = await _enable_totp(async_client, headers)

    other_session = ActiveSession(
        user_id=user.id,
        jti="step-up-other",
        expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
        last_seen_at=dt.datetime.now(dt.UTC),
    )
    db_session.add(other_session)
    await db_session.commit()

    result = await db_session.execute(
        select(ActiveSession)
        .where(ActiveSession.user_id == user.id)
        .where(ActiveSession.jti != "step-up-other")
    )
    current_session = result.scalars().first()
    assert current_session is not None
    current_session_id = current_session.id

    # Expire the mfa_verified_at via a SEPARATE session to avoid contaminating
    # the shared db_session identity map. If we mutate through db_session and
    # commit, the User object becomes detached and causes SQLA InvalidRequestError
    # when the subsequent HTTP request handler's own session tries to refresh it.
    from app.core.database import async_session as make_session

    async with make_session() as isolated_db:
        isolated_session = (
            (
                await isolated_db.execute(
                    select(ActiveSession).where(ActiveSession.id == current_session_id)
                )
            )
            .scalars()
            .first()
        )
        assert isolated_session is not None
        isolated_session.mfa_verified_at = dt.datetime.now(dt.UTC) - dt.timedelta(
            hours=1
        )
        await isolated_db.commit()

    blocked = await async_client.delete(
        f"/auth/sessions/{other_session.id}", headers=headers
    )
    assert blocked.status_code == status.HTTP_428_PRECONDITION_REQUIRED
    detail = blocked.json()["detail"]
    assert detail["error"] == "mfa_step_up_required"

    # Give the server a moment before requesting the challenge so the refreshed
    # access token minted after verification has a distinct timestamp. This
    # prevents the rate-limit middleware from grouping the requests under the
    # same identifier when everything happens within a single second.
    await asyncio.sleep(1.1)
    payload = await _complete_step_up(async_client, headers, secret)
    assert payload["session_id"] == str(current_session_id)

    success = await async_client.delete(
        f"/auth/sessions/{other_session.id}", headers=headers
    )
    assert success.status_code == 200
    assert success.json()["revoked_at"] is not None


@pytest.mark.asyncio
async def test_revoke_other_user_session_forbidden(
    async_client: AsyncClient,
    user_factory,
    db_session,
):
    password = "Nope123!"
    actor = await user_factory(
        email="nope@example.com", hashed_password=await get_password_hash(password)
    )
    other = await user_factory(email="outsider@example.com")
    session = ActiveSession(
        user_id=other.id,
        jti="outsider",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(session)
    await db_session.commit()

    headers = await _login(async_client, email=actor.email, password=password)

    response = await async_client.delete(
        f"/auth/sessions/{session.id}", headers=headers
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Access denied"


@pytest.mark.asyncio
async def test_revoke_missing_session_returns_404(
    async_client: AsyncClient,
    user_factory,
    db_session,
):
    password = "Missing404!"
    user = await user_factory(
        email="missing@example.com", hashed_password=await get_password_hash(password)
    )
    headers = await _login(async_client, email=user.email, password=password)

    non_existent_id = uuid.uuid4()
    response = await async_client.delete(
        f"/auth/sessions/{non_existent_id}", headers=headers
    )
    assert response.status_code == 404
    assert "auth.session_not_found" in response.json()["detail"]
