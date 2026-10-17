import datetime as dt
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.story_cleanup import (
    cleanup_expired_stories,
)


@pytest.mark.anyio
async def test_cleanup_expired_stories():
    db = AsyncMock()
    mock_res = MagicMock()
    mock_res.rowcount = 3
    db.execute.return_value = mock_res

    # 1. With explicit db and now (with tzinfo)
    tz_now = dt.datetime.now(dt.UTC)
    res = await cleanup_expired_stories(db=db, now=tz_now)
    assert res == 3

    # 2. With naive dt
    naive_now = dt.datetime.now()
    res_naive = await cleanup_expired_stories(db=db, now=naive_now)
    assert res_naive == 3

    # 3. With owns_session (db = None)
    with patch("app.services.story_cleanup.async_session") as mock_session:
        mock_session.return_value.__aenter__.return_value = db
        res2 = await cleanup_expired_stories()
        assert res2 == 3
