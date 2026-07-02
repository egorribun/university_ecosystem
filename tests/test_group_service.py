from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.schemas.dtos import GroupDTO
from app.services.group_service import GroupService


@pytest.mark.asyncio
async def test_get_groups():
    db = AsyncMock()
    repo = AsyncMock()
    repo.list_groups.return_value = [GroupDTO(id=uuid4(), name="Group 1")]

    service = GroupService(db, repo)
    res = await service.get_groups()

    assert len(res) == 1
    assert res[0].name == "Group 1"
    repo.list_groups.assert_called_once()
