from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request
from pydantic import ValidationError
from sqlalchemy import event, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from starlette.types import Scope

from app.api import users as api
from app.auth.security import get_password_hash
from app.core.db.base import Base
from app.models import ActiveSession, DataAccessLog, EmailChangeToken, User
from app.repositories.unit_of_work import uow_from_session
from app.schemas import schemas
from app.services.audit_service import SecureAuditService
from app.services.user.profile_service import UserProfileService


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(_element, _compiler, **_kwargs):
    return "TEXT"


def _request() -> Request:
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/users/me",
        "raw_path": b"/users/me",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": None,
        "server": ("testserver", 80),
        "state": {},
    }
    return Request(scope)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        "active",
        "active-stale",
        "absent-stale",
        "expired-stale",
        "used-stale",
        "latest",
        "invalid",
        "dirty-user",
        "dirty-session",
    ],
)
async def test_profile_response_does_not_update_users_and_keeps_signed_audit(
    monkeypatch, case
):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    names = ["users", "active_sessions", "email_change_tokens", "data_access_logs"]
    try:
        async with engine.begin() as connection:
            await connection.exec_driver_sql(
                "CREATE TABLE groups (id CHAR(32) PRIMARY KEY)"
            )
            await connection.exec_driver_sql(
                "CREATE TABLE tenants (id CHAR(32) PRIMARY KEY)"
            )
            await connection.run_sync(
                lambda sync: Base.metadata.create_all(
                    sync, tables=[Base.metadata.tables[n] for n in names]
                )
            )
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            now = datetime.now(UTC)
            user_id = uuid4()
            persisted = None if case in ("active", "latest") else "stale@example.com"
            user = User(
                id=user_id,
                email="member@example.com",
                hashed_password=await get_password_hash(f"Aa1!{uuid4().hex}"),
                is_active=True,
                pending_email=persisted,
            )
            db.add(user)
            await db.flush()
            active = ActiveSession(
                id=uuid4(),
                user_id=user_id,
                jti="synthetic",
                expires_at=now + timedelta(hours=1),
                last_seen_at=now,
                mfa_epoch=0,
            )
            db.add(active)

            def add_token(
                email: str, *, used: bool = False, offset: int = 0, valid: bool = True
            ):
                db.add(
                    EmailChangeToken(
                        id=uuid4(),
                        user_id=user_id,
                        new_email=email,
                        token_hash=uuid4().hex,
                        created_at=now + timedelta(seconds=offset),
                        expires_at=now + timedelta(hours=1)
                        if valid
                        else now - timedelta(hours=1),
                        used=used,
                    )
                )

            if case in ("active", "active-stale", "latest"):
                add_token("pending@example.com", offset=1)
            if case == "latest":
                add_token("older@example.com", offset=-1)
            if case == "expired-stale":
                add_token("expired@example.com", valid=False)
            if case == "used-stale":
                add_token("used@example.com", used=True)
            if case == "invalid":
                add_token("invalid-email")
            await db.commit()
            auth_before = (
                await db.execute(
                    select(ActiveSession.__table__).where(ActiveSession.id == active.id)
                )
            ).one()
            if case == "dirty-user":
                user.mfa_required = True
            if case == "dirty-session":
                active.last_seen_at = now + timedelta(seconds=37)
            expected = schemas.UserOut.model_validate(user).model_dump(mode="json")
            pending = (
                "pending@example.com"
                if case in ("active", "active-stale", "latest")
                else None
            )
            expected["pending_email"] = pending
            secure = SecureAuditService(signing_key=secrets.token_bytes(32))
            monkeypatch.setattr(
                "app.services.audit_service.get_secure_audit_service", lambda: secure
            )
            service = UserProfileService(
                uow=uow_from_session(db),
                audit=MagicMock(),
                notifications=MagicMock(),
            )
            categories = []

            def observe(_conn, _cursor, statement, _parameters, _context, _many):
                sql = " ".join(statement.upper().split())
                if sql.startswith("UPDATE USERS "):
                    categories.append("user_update")
                elif sql.startswith("INSERT INTO DATA_ACCESS_LOGS "):
                    categories.append("audit_insert")
                elif "FROM EMAIL_CHANGE_TOKENS" in sql:
                    categories.append("pending_select")
                elif sql.startswith("UPDATE ACTIVE_SESSIONS "):
                    categories.append("session_update")
                else:
                    categories.append("other")

            event.listen(engine.sync_engine, "before_cursor_execute", observe)
            request = _request()
            request.state.active_session = active
            if case == "invalid":
                with pytest.raises(ValidationError):
                    await api.me.__dishka_orig_func__(
                        request=request, db=db, service=service, user=user
                    )
            else:
                response = await api.me.__dishka_orig_func__(
                    request=request, db=db, service=service, user=user
                )
                assert response.model_dump(mode="json") == expected
            event.remove(engine.sync_engine, "before_cursor_execute", observe)
            expected_sql = ["pending_select", "audit_insert"]
            if case == "dirty-user":
                expected_sql.insert(0, "user_update")
            if case == "dirty-session":
                expected_sql.insert(0, "session_update")
            assert categories == expected_sql
            actual = (
                await db.execute(select(User.pending_email).where(User.id == user_id))
            ).scalar_one()
            assert actual == persisted
            if case == "dirty-user":
                assert (
                    await db.execute(
                        select(User.mfa_required).where(User.id == user_id)
                    )
                ).scalar_one() is True
            auth_after = (
                await db.execute(
                    select(ActiveSession.__table__).where(ActiveSession.id == active.id)
                )
            ).one()
            if case == "dirty-session":
                before_columns = dict(auth_before._mapping)
                after_columns = dict(auth_after._mapping)
                assert after_columns["last_seen_at"].replace(
                    tzinfo=UTC
                ) == now + timedelta(seconds=37)
                after_columns["last_seen_at"] = before_columns["last_seen_at"]
                assert after_columns == before_columns
            else:
                assert auth_after == auth_before
            logs = (await db.execute(select(DataAccessLog))).scalars().all()
            assert len(logs) == 1
            audit = logs[0]
            assert audit.actor_user_id == user_id and audit.subject_user_id == user_id
            assert audit.resource_type == "profile" and audit.action == "read"
            assert secure.verify_integrity(audit)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_invalid_profile_envelope_is_rejected_before_pending_and_audit(
    monkeypatch,
):
    request = _request()
    request.scope["headers"] = [(b"x-profile-cache-envelope", b"{}")]
    request.state.active_session = SimpleNamespace(signing_key=secrets.token_hex(32))
    service = MagicMock()
    service.get_pending_email = AsyncMock()
    audit = AsyncMock()
    monkeypatch.setattr(api, "log_data_access", audit)
    with pytest.raises(HTTPException) as error:
        await api.me.__dishka_orig_func__(
            request=request,
            db=MagicMock(),
            service=service,
            user=SimpleNamespace(id=uuid4()),
        )
    assert error.value.status_code == 400
    service.get_pending_email.assert_not_awaited()
    audit.assert_not_awaited()
