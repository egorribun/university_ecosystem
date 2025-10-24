from datetime import UTC, datetime, timedelta
from typing import Dict

import pytest
from fastapi import status
from httpx import AsyncClient

from app.auth.security import get_password_hash
from app.models.models import ActiveSession


async def _login(
    async_client: AsyncClient,
    *,
    email: str,
    password: str,
    user_agent: str = "pytest-agent/1.0",
    forwarded_for: str | None = "203.0.113.42",
) -> Dict[str, str]:
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
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}", "User-Agent": user_agent}


@pytest.mark.anyio
async def test_list_sessions_includes_current_session_metadata(
    async_client: AsyncClient,
    user_factory,
    db_session,
):
    password = "Sessions123!"
    hashed = get_password_hash(password)
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
    assert entry["user_id"] == user.id
    assert entry["is_current"] is True
    assert entry["ip_address"] == "198.51.100.5"
    assert entry["user_agent"] == "pytest-agent/2.0"
    assert entry["revoked_at"] is None
    assert entry["last_seen_at"] is not None


@pytest.mark.anyio
async def test_admin_can_list_sessions_for_other_user(
    async_client: AsyncClient,
    user_factory,
    db_session,
):
    password = "AdminSessions42!"
    admin = await user_factory(
        email="admin@example.com",
        hashed_password=get_password_hash(password),
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


@pytest.mark.anyio
async def test_non_admin_cannot_list_sessions_for_other_user(
    async_client: AsyncClient,
    user_factory,
    db_session,
):
    password = "Forbidden42!"
    actor = await user_factory(
        email="actor@example.com", hashed_password=get_password_hash(password)
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


@pytest.mark.anyio
async def test_revoke_session_marks_revoked(
    async_client: AsyncClient,
    user_factory,
    db_session,
):
    password = "Revoke123!"
    user = await user_factory(
        email="revoker@example.com", hashed_password=get_password_hash(password)
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

    response = await async_client.delete(
        f"/auth/sessions/{other_session.id}", headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["revoked_at"] is not None
    assert body["is_current"] is False

    await db_session.refresh(other_session)
    assert other_session.revoked_at is not None


@pytest.mark.anyio
async def test_admin_can_revoke_foreign_session(
    async_client: AsyncClient,
    user_factory,
    db_session,
):
    password = "AdminDelete7!"
    admin = await user_factory(
        email="admin-del@example.com",
        hashed_password=get_password_hash(password),
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


@pytest.mark.anyio
async def test_revoke_other_user_session_forbidden(
    async_client: AsyncClient,
    user_factory,
    db_session,
):
    password = "Nope123!"
    actor = await user_factory(
        email="nope@example.com", hashed_password=get_password_hash(password)
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


@pytest.mark.anyio
async def test_revoke_missing_session_returns_404(
    async_client: AsyncClient,
    user_factory,
    db_session,
):
    password = "Missing404!"
    user = await user_factory(
        email="missing@example.com", hashed_password=get_password_hash(password)
    )
    headers = await _login(async_client, email=user.email, password=password)

    response = await async_client.delete("/auth/sessions/9999", headers=headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Session not found"
