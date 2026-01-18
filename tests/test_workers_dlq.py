from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workers.dead_letter_queue import DeadLetterQueue, JobStatus


@pytest.mark.asyncio
async def test_dlq_basic():
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.add_all = MagicMock()
    dlq = DeadLetterQueue(mock_db)

    # Coverage for add_failed_job branches
    with patch("app.workers.dead_letter_queue.compute_job_hash", return_value="hash1"):
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)
        await dlq.add_failed_job("type", {"p": 1}, "error")

    # Coverage for stats
    mock_db.execute.return_value = []
    res = await dlq.get_queue_stats()
    assert res[JobStatus.PENDING.value] == 0
