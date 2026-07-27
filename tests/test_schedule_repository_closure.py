"""Focused cache and factory coverage for schedule repositories."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.cache import schedule_cache
from app.repositories.base import BaseRepository
from app.repositories.schedule_repository import (
    GroupRepository,
    ScheduleRepository,
    get_group_repository,
    get_schedule_repository,
)


@pytest.mark.asyncio
async def test_group_repository_returns_cached_groups():
    repo = GroupRepository(MagicMock())

    with patch.object(
        schedule_cache, "get", new=AsyncMock(return_value=["cached-group"])
    ):
        result = await repo.list_groups()

    assert result == ["cached-group"]


@pytest.mark.asyncio
async def test_schedule_repository_returns_cached_items():
    repo = ScheduleRepository(MagicMock())

    with patch.object(
        schedule_cache, "get", new=AsyncMock(return_value=["cached-item"])
    ):
        result = await repo.get_by_group(uuid4())

    assert result == ["cached-item"]


@pytest.mark.asyncio
async def test_create_records_creator_and_invalidates_global_cache():
    repo = ScheduleRepository(MagicMock())
    payload = {
        "subject": "Independent study",
        "start_time": datetime(2026, 1, 1, 10, 0),
        "end_time": datetime(2026, 1, 1, 11, 0),
    }
    created = object()

    with (
        patch.object(
            BaseRepository, "create", new=AsyncMock(return_value=created)
        ) as base_create,
        patch.object(schedule_cache, "delete", new=AsyncMock()) as delete,
    ):
        result = await repo.create(payload, creator_id="creator-1")

    assert result is created
    base_create.assert_awaited_once()
    created_payload = base_create.await_args.args[0]
    assert created_payload["creator_id"] == "creator-1"
    assert delete.await_count == 1
    delete.assert_awaited_once_with("schedule:groups")


def test_repository_factories_bind_database():
    db = MagicMock()

    assert get_group_repository(db).db is db
    assert get_schedule_repository(db).db is db
