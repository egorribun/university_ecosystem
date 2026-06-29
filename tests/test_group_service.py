import pytest

from app.services.group_service import GroupService


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "group_id, expected_status",
    [
        (1, True),
        (999, False),
    ],
)
async def test_get_group_status(group_id, expected_status, mock_db):
    service = GroupService(db=mock_db)
    result = await service.get_group_status(group_id)
    assert result == expected_status
