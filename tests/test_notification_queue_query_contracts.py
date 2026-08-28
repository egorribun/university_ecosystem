"""Focused query contracts for the notification dead-letter queue."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.services.notification_queue import list_dead_lettered_jobs


@pytest.mark.asyncio
async def test_dead_letter_listing_keeps_named_snapshot_ctes_and_true_filter() -> None:
    """The page and count must share an explicit, dead-letter-only snapshot.

    This assertion deliberately inspects the generated PostgreSQL statement.  A
    unit test that only verifies the returned rows cannot detect a missing
    ``dead_lettered`` predicate or an anonymous/renamed CTE, both of which can
    silently change the administrative result set under load.
    """

    result = MagicMock()
    result.all.return_value = [(None, 0)]
    db = AsyncMock()

    db.execute.return_value = result
    jobs, total = await list_dead_lettered_jobs(db, limit=20, offset=100)

    assert jobs == []
    assert total == 0
    statement = db.execute.await_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "notification_dead_letter_page" in sql
    assert "notification_dead_letter_total" in sql
    assert sql.lower().count("notification_queue_jobs.dead_lettered is true") == 2
