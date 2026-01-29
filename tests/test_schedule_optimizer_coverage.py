from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.schedule_optimizer import (
    ScheduleItemInternal,
    ScheduleOptimizerService,
)


@pytest.fixture
def optimizer_service():
    return ScheduleOptimizerService(base_url="http://test", grpc_addr="test:50051")


@pytest.fixture
def sample_item():
    return ScheduleItemInternal(
        weekday="mon",
        start_time=datetime.now(UTC),
        end_time=datetime.now(UTC),
        parity="even",
    )


@pytest.mark.asyncio
async def test_detect_conflicts_success(optimizer_service, sample_item):
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        # Mock successful response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "conflicts": [sample_item.model_dump(mode="json")]
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        conflicts = await optimizer_service.detect_conflicts(sample_item, [sample_item])

        assert len(conflicts) == 1
        assert conflicts[0].weekday == sample_item.weekday


@pytest.mark.asyncio
async def test_detect_conflicts_failure(optimizer_service, sample_item):
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = Exception("API Error")

        conflicts = await optimizer_service.detect_conflicts(sample_item, [])

        assert conflicts == []


@pytest.mark.asyncio
async def test_batch_detect_conflicts(optimizer_service):
    # Just verifies the fallback/log logic for now
    result = await optimizer_service.batch_detect_conflicts([])
    assert result == []


@pytest.mark.asyncio
async def test_call_grpc_not_implemented(optimizer_service):
    with pytest.raises(NotImplementedError):
        await optimizer_service._call_grpc()
