import pytest
import asyncio
import datetime as dt
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.story_cleanup import (
    cleanup_expired_stories,
    start_story_cleanup_scheduler,
    StoryCleanupConfig,
)

@pytest.mark.anyio
async def test_cleanup_expired_stories():
    db = AsyncMock()
    mock_res = MagicMock()
    mock_res.rowcount = 3
    db.execute.return_value = mock_res
    
    # 1. With explicit db and now (with tzinfo)
    tz_now = dt.datetime.now(dt.timezone.utc)
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

def test_story_cleanup_config():
    config = StoryCleanupConfig(interval_seconds=10)
    assert config.normalized_interval() == 60
    
    config2 = StoryCleanupConfig(interval_seconds=120)
    assert config2.normalized_interval() == 120

@pytest.mark.anyio
async def test_start_story_cleanup_scheduler_normal():
    config = StoryCleanupConfig(interval_seconds=60)
    
    with patch("app.services.story_cleanup.cleanup_expired_stories", new_callable=AsyncMock) as mock_cleanup, \
         patch("app.services.story_cleanup.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        
        mock_cleanup.return_value = 2
        
        stop_fn = await start_story_cleanup_scheduler(config=config)
        assert stop_fn is not None
        
        await asyncio.sleep(0.05)
        await stop_fn()
        # Double stop when already done
        await stop_fn()

@pytest.mark.anyio
async def test_start_story_cleanup_scheduler_error():
    with patch("app.services.story_cleanup.cleanup_expired_stories", new_callable=AsyncMock) as mock_cleanup, \
         patch("app.services.story_cleanup.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        
        mock_cleanup.side_effect = ValueError("db error")
        stop_fn = await start_story_cleanup_scheduler()
        await asyncio.sleep(0.05)
        await stop_fn()
