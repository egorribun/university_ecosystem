"""Branch closure tests for the generic repository implementation."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_repository_base import UserRepository


@pytest.fixture
def repository():
    return UserRepository(AsyncMock(spec=AsyncSession))


@pytest.mark.asyncio
async def test_create_accepts_plain_mapping(repository):
    mock_db = repository.db

    def assign_identity(obj):
        obj.id = 1

    mock_db.add.side_effect = assign_identity

    result = await repository.create({"email": "mapping@example.com"})

    assert result.id == 1
    assert result.email == "mapping@example.com"


def test_ensure_utc_adds_utc_to_naive_datetime(repository):
    value = datetime(2026, 1, 2, 3, 4, 5)

    result = repository._ensure_utc(value)

    assert result.tzinfo is UTC


def test_ensure_utc_converts_aware_datetime(repository):
    value = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)

    result = repository._ensure_utc(value)

    assert result == value
    assert result.tzinfo is UTC


def test_add_delegates_to_database_session(repository):
    obj = object()

    repository.add(obj)

    repository.db.add.assert_called_once_with(obj)
