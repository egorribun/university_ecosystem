from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user
from app.core.container import get_read_stats_handler
from app.main import app


@pytest.fixture
def mock_user():
    user = MagicMock()
    user.id = 1
    user.role = "student"
    return user


@pytest.fixture
def mock_stats_handler():
    handler = AsyncMock()
    # Mock result with payload and etag
    result = MagicMock()
    result.payload = {"data": "test"}
    result.etag = "test-etag"
    result.not_modified = False
    handler.handle.return_value = result
    return handler


@pytest.mark.asyncio
async def test_stats_api_coverage(mock_user, mock_stats_handler):
    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_read_stats_handler] = lambda: mock_stats_handler
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as ac:
            # Test attendance
            res = await ac.get("/api/v1/stats/attendance")
            assert res.status_code == 200
            assert res.json() == {"data": "test"}
            assert res.headers["ETag"] == '"test-etag"'

            # Test grades with period
            await ac.get("/api/v1/stats/grades?period=90d")

            # Test participation with invalid period (fallback to default)
            await ac.get("/api/v1/stats/participation?period=invalid")

            # Test 304 Not Modified
            mock_stats_handler.handle.return_value.not_modified = True
            res = await ac.get(
                "/api/v1/stats/attendance", headers={"If-None-Match": '"test-etag"'}
            )
            assert res.status_code == 304
    finally:
        # Cleaned up by conftest
        pass
