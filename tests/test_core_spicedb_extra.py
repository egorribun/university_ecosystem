from unittest.mock import MagicMock

import pytest

from app.core.spicedb import SpiceDBClient


@pytest.mark.asyncio
async def test_spicedb_check_permission(monkeypatch):
    mock_client = MagicMock()
    mock_client.CheckPermission.return_value = {"allowed": True}
    monkeypatch.setattr(
        "app.core.spicedb.SpiceDBClient.get_client", lambda x: mock_client
    )

    client = SpiceDBClient()
    result = await client.check("user", "read", "resource")
    assert result is True
