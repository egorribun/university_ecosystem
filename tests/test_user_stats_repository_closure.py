"""Closure tests for UserStatsRepository's repository contract."""

from app.repositories.user_stats_repository import (
    UserStatsRepository,
    get_user_stats_repository,
)


def test_user_stats_repository_contract_and_factory(db_session):
    repo = UserStatsRepository(db_session)

    assert repo.model.__name__ == "User"
    assert repo.dto_class.__name__ == "UserDTO"

    factory_repo = get_user_stats_repository(db_session)
    assert isinstance(factory_repo, UserStatsRepository)
    assert factory_repo.db is db_session
