import uuid

import pytest

from app.repositories.user_stats_repository import UserStatsRepository
from app.schemas.dtos import UserDTO


@pytest.mark.asyncio
async def test_inherited_get_returns_public_user_dto(db_session, user_factory):
    user = await user_factory(email="stats-reader@example.com")
    user_id = user.id
    db_session.expunge_all()
    repo = UserStatsRepository(db_session)

    result = await repo.get(user_id)

    assert isinstance(result, UserDTO)
    assert result.id == user_id
    assert result.email == "stats-reader@example.com"
    assert result.is_active is True
    assert "hashed_password" not in result.model_dump()
    assert await repo.get(uuid.uuid4()) is None
