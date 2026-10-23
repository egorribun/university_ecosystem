from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import users as users_api
from app.core.database import get_read_db
from app.core.protocols import AsyncDatabaseSession
from app.models import DataAccessLog, User
from app.services import audit_service
from app.services.audit_service import SecureAuditService
from tests.conftest import dishka_overrides


class _ReadOnlyReplica:
    """Reject writes if a route accidentally resolves its audit session here."""

    def __init__(self) -> None:
        self.write_attempts = 0

    def add(self, _value: object) -> None:
        self.write_attempts += 1
        raise RuntimeError("read-only replica rejects writes")


@pytest.mark.asyncio
async def test_users_me_audit_write_uses_primary_with_distinct_read_component(
    app: FastAPI,
    async_client: AsyncClient,
    db_session: AsyncSession,
    user_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user: User = await user_factory()
    replica = _ReadOnlyReplica()

    async def read_replica_session() -> AsyncIterator[AsyncDatabaseSession]:
        yield cast(AsyncDatabaseSession, replica)

    monkeypatch.setitem(app.dependency_overrides, get_read_db, read_replica_session)
    monkeypatch.setitem(
        app.dependency_overrides, users_api.get_current_user_full, lambda: user
    )
    monkeypatch.setattr(
        audit_service,
        "get_secure_audit_service",
        lambda: SecureAuditService(signing_key=bytes(range(32))),
    )

    # The repository conftest rebuilds the real Dishka container from its
    # dependency overrides, keeping the default DB on the test DB while giving
    # the read component a distinct write-rejecting session.
    with dishka_overrides(app):
        response = await async_client.get("/users/me")

    assert response.status_code == 200
    assert response.json()["id"] == str(user.id)
    assert replica.write_attempts == 0

    rows = list(
        (
            await db_session.scalars(
                select(DataAccessLog).where(
                    DataAccessLog.actor_user_id == user.id,
                    DataAccessLog.subject_user_id == user.id,
                    DataAccessLog.resource_type == "profile",
                    DataAccessLog.action == "read",
                )
            )
        ).all()
    )
    assert len(rows) == 1
    assert rows[0].resource_id == str(user.id)
    assert rows[0].signature
