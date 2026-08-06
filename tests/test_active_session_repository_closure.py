"""Branch and factory closure tests for ActiveSessionRepository."""

from __future__ import annotations

from sqlalchemy.orm import load_only

from app.models import User
from app.repositories.active_session_repository import (
    ActiveSessionRepository,
    get_active_session_repository,
)


def test_repository_exposes_model_and_dto_contract(db_session):
    repo = ActiveSessionRepository(db_session)

    assert repo.model.__name__ == "ActiveSession"
    assert repo.dto_class.__name__ == "ActiveSessionDTO"


def test_repository_factory_returns_bound_repository(db_session):
    repo = get_active_session_repository(db_session)

    assert isinstance(repo, ActiveSessionRepository)
    assert repo.db is db_session


async def test_get_active_session_with_user_accepts_load_options(
    db_session, user_factory
):
    user = await user_factory()
    from datetime import UTC, datetime, timedelta

    from app.models import ActiveSession

    now = datetime.now(UTC)
    db_session.add(
        ActiveSession(
            user_id=user.id,
            jti="load-option",
            created_at=now,
            expires_at=now + timedelta(hours=1),
            last_seen_at=now,
            ip_address="127.0.0.1",
            user_agent="pytest",
        )
    )
    await db_session.flush()

    result = await ActiveSessionRepository(db_session).get_active_session_with_user(
        user.id,
        "load-option",
        load_options=[load_only(User.id)],
    )

    assert result is not None
    assert result[0].id == user.id
