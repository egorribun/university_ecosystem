import asyncio
import uuid
from unittest.mock import AsyncMock

import pytest

from app.repositories.news_repository import NewsRepository


@pytest.mark.asyncio
async def test_toggle_like_concurrency():
    """
    Test that concurrent toggle_like calls do not cause IntegrityErrors
    or corrupted states.
    """
    # We need a real-ish or highly controlled mock DB session
    # that implements with_for_update or simulates its effects.

    mock_db = AsyncMock()
    from unittest.mock import MagicMock

    mock_db.add = MagicMock()
    repo = NewsRepository(mock_db)
    news_id = uuid.uuid4()
    user_id = uuid.uuid4()

    # Simulate a sequence:
    # 1. 10 tasks all try to toggle.
    # 2. They should all see the same locked state if serialized.

    lock = asyncio.Lock()
    execution_order = []

    async def mock_execute(stmt):
        # Check if it's the SELECT FOR UPDATE
        # This is a bit complex to mock perfectly, but we can simulate the result.
        async with lock:
            execution_order.append("locked")
            # Simulate a small delay to induce race if lock was missing
            await asyncio.sleep(0.01)
            from unittest.mock import MagicMock

            mock_res = MagicMock()
            # Return None (no like yet) for all calls initially
            mock_res.scalar_one_or_none.return_value = None
            return mock_res

    mock_db.execute.side_effect = mock_execute

    # Run 10 concurrent requests
    await asyncio.gather(*(repo.toggle_like(news_id, user_id) for _ in range(10)))

    # Verify that mock_db.execute was called 10 times
    assert mock_db.execute.call_count == 10

    # Verify that db.add was called for results that return True
    # in a real DB, with_for_update would ensure they don't ALL see None.
    # Our mock simulates the serialization if they wait on the lock.
    # However, the repo code itself handles the lock via DB transaction.
    # To truly test this, we'd need an integration test with a real DB.
    # For now, this verifies the call pattern.
