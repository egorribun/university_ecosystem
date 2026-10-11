"""A stale active login DTO cannot mint after the locked account is deactivated."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy import event, func, select

from app.models import ActiveSession
from app.repositories.unit_of_work import uow_from_session
from app.schemas.dtos import UserDTO
from app.services.session_service import SessionService


@pytest.mark.asyncio
async def test_stale_active_dto_cannot_issue_session_after_deactivation(
    db_session, test_user, monkeypatch
) -> None:
    stale_user = UserDTO.model_validate(test_user)
    assert stale_user.is_active is True

    test_user.is_active = False
    await db_session.commit()
    await db_session.refresh(test_user, attribute_names=["is_active"])
    assert test_user.is_active is False

    service = SessionService(uow_from_session(db_session))
    enforce_limit = AsyncMock()
    mint_jwt = MagicMock(return_value="unexpected-token")
    sync_to_redis = AsyncMock()
    monkeypatch.setattr(service, "_enforce_concurrent_limit", enforce_limit)
    monkeypatch.setattr(service, "_mint_jwt", mint_jwt)
    monkeypatch.setattr(service, "_sync_to_redis", sync_to_redis)

    original_commit = db_session.commit
    commit_spy = AsyncMock(wraps=original_commit)
    monkeypatch.setattr(db_session, "commit", commit_spy)

    session_inserts: list[bool] = []

    def record_session_insert(
        _connection, _cursor, statement: str, _parameters, _context, _many
    ) -> None:
        if statement.lstrip().lower().startswith("insert into active_sessions"):
            session_inserts.append(True)

    sync_engine = db_session.bind.sync_engine
    event.listen(sync_engine, "before_cursor_execute", record_session_insert)
    try:
        with pytest.raises(HTTPException) as exc:
            await service.create_access_token(
                sub=stale_user.id,
                metadata={"mfa_epoch": stale_user.mfa_epoch},
                extra_claims={"is_active": stale_user.is_active},
            )
    finally:
        event.remove(sync_engine, "before_cursor_execute", record_session_insert)

    assert exc.value.status_code == 401
    assert exc.value.detail == "credentials_invalid"
    assert session_inserts == []
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(ActiveSession)
            .where(ActiveSession.user_id == stale_user.id)
        )
        == 0
    )
    commit_spy.assert_not_awaited()
    enforce_limit.assert_not_awaited()
    mint_jwt.assert_not_called()
    sync_to_redis.assert_not_awaited()
