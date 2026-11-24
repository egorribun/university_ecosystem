from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app.api.deps import auth
from app.auth.security import get_password_hash
from app.core.db.base import Base
from app.models import ActiveSession, User


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(_element, _compiler, **_kwargs):
    return "TEXT"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        "match",
        "foreign-sid",
        "same-user-sid",
        "revoked-sid",
        "unknown-sid",
        "invalid-sid",
        "no-sid",
        "revoked",
        "inactive",
        "wrong-jti",
        "wrong-user",
        "expired",
        "mfa-epoch",
    ],
)
async def test_actual_sqlite_join_and_authoritative_rejections(monkeypatch, case):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    names = [
        "users",
        "active_sessions",
        "user_preferences",
        "user_profiles",
        "spotify_integrations",
        "user_education_paths",
    ]
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
            uid, other_uid, sid, other_sid = uuid4(), uuid4(), uuid4(), uuid4()
            user = User(
                id=uid,
                email=f"{uid.hex}@example.invalid",
                hashed_password=await get_password_hash(f"Aa1!{uuid4().hex}"),
                is_active=case != "inactive",
                mfa_epoch=1 if case == "mfa-epoch" else 0,
            )
            other = User(
                id=other_uid,
                email=f"{other_uid.hex}@example.invalid",
                hashed_password=await get_password_hash(f"Aa1!{uuid4().hex}"),
                is_active=True,
                mfa_epoch=0,
            )
            session = ActiveSession(
                id=sid,
                user_id=other_uid if case == "wrong-user" else uid,
                jti="other-jti" if case == "wrong-jti" else "synthetic-jti",
                expires_at=now - timedelta(hours=1)
                if case == "expired"
                else now + timedelta(hours=1),
                revoked_at=now if case == "revoked" else None,
                last_seen_at=now,
                mfa_epoch=0,
            )
            foreign = ActiveSession(
                id=other_sid,
                user_id=uid if case == "same-user-sid" else other_uid,
                jti="foreign-jti",
                revoked_at=now if case == "revoked-sid" else None,
                expires_at=now + timedelta(hours=1),
                last_seen_at=now,
                mfa_epoch=0,
            )
            db.add_all([user, other, session, foreign])
            await db.flush()
            db.expunge_all()
            sid_hint = {
                "foreign-sid": str(other_sid),
                "same-user-sid": str(other_sid),
                "revoked-sid": str(other_sid),
                "unknown-sid": str(uuid4()),
                "invalid-sid": "invalid",
                "no-sid": None,
            }.get(case, str(sid))
            cache = AsyncMock()
            cache.get_session.return_value = {
                "user_id": str(uid),
                "session_id": sid_hint,
            }
            revocations = AsyncMock()
            revocations.exists.return_value = False
            fingerprint = MagicMock()
            fingerprint.validate_fingerprint = AsyncMock()
            request = MagicMock(headers={})
            request.state = SimpleNamespace()
            monkeypatch.setattr(auth, "resolve_locale", lambda **kw: "en")
            monkeypatch.setattr(auth, "settings", SimpleNamespace(mvp_tenant_id=None))
            monkeypatch.setattr(
                auth.AuthTokenService, "extract_and_decode_token", lambda *a: {}
            )
            monkeypatch.setattr(
                auth.AuthTokenService,
                "validate_payload",
                lambda *a: (uid, "synthetic-jti"),
            )
            monkeypatch.setattr(
                auth, "get_revocation_redis_client", AsyncMock(return_value=revocations)
            )
            monkeypatch.setattr(auth, "AuthFingerprintService", lambda *a: fingerprint)
            statements = []

            def capture(_conn, _cursor, statement, _params, _context, _many):
                statements.append(statement)

            event.listen(engine.sync_engine, "before_cursor_execute", capture)
            if case in (
                "match",
                "foreign-sid",
                "same-user-sid",
                "revoked-sid",
                "unknown-sid",
                "invalid-sid",
                "no-sid",
            ):
                resolved = await auth._resolve_current_user(request, "token", db, cache)
                assert resolved.id == uid
                assert request.state.active_session.id == sid
                assert fingerprint.validate_fingerprint.await_count == 1
            else:
                with pytest.raises(HTTPException) as error:
                    await auth._resolve_current_user(request, "token", db, cache)
                assert error.value.status_code == 401
                assert not hasattr(request.state, "active_session")
                fingerprint.validate_fingerprint.assert_not_awaited()
            assert len(statements) == 1
            assert statements[0].lstrip().upper().startswith("SELECT")
            assert "JOIN active_sessions" in statements[0]
    finally:
        await engine.dispose()
