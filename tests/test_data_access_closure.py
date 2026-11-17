"""Closure test for owned-session access-log cleanup."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app.core import database
from app.models.logs import DataAccessLog
from app.services.data_access import cleanup_access_logs


@pytest.mark.asyncio
async def test_cleanup_access_logs_opens_session_when_db_is_not_supplied():
    session = AsyncMock()
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=session)
    session_context.__aexit__ = AsyncMock(return_value=None)
    repository = MagicMock()
    repository.prune_logs = AsyncMock(return_value=4)

    with (
        patch("app.services.data_access.async_session", return_value=session_context),
        patch(
            "app.services.data_access.AuditRepository",
            return_value=repository,
        ),
    ):
        assert await cleanup_access_logs(db=None, retention_days=30) == 4

    session_context.__aenter__.assert_awaited_once()
    session_context.__aexit__.assert_awaited_once()
    repository.prune_logs.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("owns_session", [True, False])
async def test_cleanup_access_logs_transaction_ownership(
    db_session, monkeypatch, owns_session
):
    now = datetime.now(UTC)
    expired = DataAccessLog(
        resource_type="cleanup-contract",
        action="read",
        created_at=now - timedelta(days=2),
    )
    recent = DataAccessLog(
        resource_type="cleanup-contract",
        action="read",
        created_at=now,
    )
    db_session.add_all([expired, recent])
    await db_session.commit()
    expired_id, recent_id = expired.id, recent.id
    monkeypatch.setattr(
        "app.services.data_access.async_session", database.async_session
    )

    if owns_session:
        assert await cleanup_access_logs(retention_days=1) == 1
    else:
        assert await cleanup_access_logs(db=db_session, retention_days=1) == 1
        await db_session.rollback()

    async with database.async_session() as observer:
        ids = set(
            (
                await observer.scalars(
                    select(DataAccessLog.id).where(
                        DataAccessLog.id.in_([expired_id, recent_id])
                    )
                )
            ).all()
        )
    assert recent_id in ids
    assert (expired_id not in ids) is owns_session


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_stage", ["prune", "commit"])
async def test_owned_cleanup_propagates_failure(failure_stage):
    session = AsyncMock()
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=session)
    session_context.__aexit__ = AsyncMock(return_value=None)
    repository = MagicMock()
    repository.prune_logs = AsyncMock(return_value=4)
    failure = RuntimeError("cleanup failed")
    if failure_stage == "prune":
        repository.prune_logs.side_effect = failure
    else:
        session.commit.side_effect = failure

    with (
        patch("app.services.data_access.async_session", return_value=session_context),
        patch("app.services.data_access.AuditRepository", return_value=repository),
        pytest.raises(RuntimeError, match="cleanup failed"),
    ):
        await cleanup_access_logs(retention_days=30)

    session_context.__aexit__.assert_awaited_once()
    if failure_stage == "prune":
        session.commit.assert_not_awaited()
    else:
        session.commit.assert_awaited_once()
