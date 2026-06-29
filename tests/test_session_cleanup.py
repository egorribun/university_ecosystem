import pytest
import asyncio
import datetime as dt
import secrets
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.session_cleanup import (
    SessionCleanupConfig,
    cleanup_expired_sessions,
    start_session_cleanup_scheduler,
    delete_sessions_matching,
    revoke_sessions_matching,
)
from app.models import ActiveSession, MfaChallenge

# ============================================================
# SessionCleanupConfig tests
# ============================================================

def test_session_cleanup_config_default():
    config = SessionCleanupConfig()
    assert config.interval_seconds == 900
    assert config.normalized_interval() == 900

def test_session_cleanup_config_custom():
    config = SessionCleanupConfig(interval_seconds=120)
    assert config.normalized_interval() == 120

def test_session_cleanup_config_min_interval():
    config = SessionCleanupConfig(interval_seconds=10)
    assert config.normalized_interval() == 30

def test_session_cleanup_config_zero_interval():
    config = SessionCleanupConfig(interval_seconds=0)
    assert config.normalized_interval() == 30

def test_session_cleanup_config_negative():
    config = SessionCleanupConfig(interval_seconds=-100)
    assert config.normalized_interval() == 30

# ============================================================
# delete_sessions_matching tests
# ============================================================

@pytest.mark.anyio
async def test_delete_sessions_matching_sqlite():
    db = AsyncMock()
    mock_res = MagicMock()
    mock_res.rowcount = 4
    db.execute.return_value = mock_res
    
    whereclause = (ActiveSession.id == ActiveSession.id)
    
    # Under SQLite (default settings.database_url contains sqlite)
    with patch("app.core.config.settings.database_url", "sqlite+aiosqlite:///test.db"):
        res = await delete_sessions_matching(db=db, whereclause=whereclause)
        assert res == 4
        assert db.execute.call_count == 2 # 1 for challenges, 1 for active sessions

@pytest.mark.anyio
async def test_delete_sessions_matching_postgres_rowcount():
    db = AsyncMock()
    mock_res = MagicMock()
    mock_res.rowcount = 6
    del mock_res.raw # Ensure hasattr(delete_result, "raw") is False or fails
    db.execute.return_value = mock_res
    
    whereclause = (ActiveSession.id == ActiveSession.id)
    
    # Under PostgreSQL, rowcount is returned
    with patch("app.core.config.settings.database_url", "postgresql+asyncpg://user:pass@host/db"):
        res = await delete_sessions_matching(db=db, whereclause=whereclause)
        assert res == 6

@pytest.mark.anyio
async def test_delete_sessions_matching_postgres_raw_rowcount():
    db = AsyncMock()
    mock_res = MagicMock()
    mock_res.rowcount = None
    mock_raw = MagicMock()
    mock_raw.rowcount = 7
    mock_res.raw = mock_raw
    db.execute.return_value = mock_res
    
    whereclause = (ActiveSession.id == ActiveSession.id)
    
    with patch("app.core.config.settings.database_url", "postgresql+asyncpg://user:pass@host/db"):
        res = await delete_sessions_matching(db=db, whereclause=whereclause)
        assert res == 7

@pytest.mark.anyio
async def test_delete_sessions_matching_postgres_fetchall():
    db = AsyncMock()
    mock_res = MagicMock()
    mock_res.rowcount = None
    del mock_res.raw
    mock_res.fetchall.return_value = [1, 2, 3]
    db.execute.return_value = mock_res
    
    whereclause = (ActiveSession.id == ActiveSession.id)
    
    with patch("app.core.config.settings.database_url", "postgresql+asyncpg://user:pass@host/db"):
        res = await delete_sessions_matching(db=db, whereclause=whereclause)
        assert res == 3

# ============================================================
# revoke_sessions_matching tests
# ============================================================

@pytest.mark.anyio
async def test_revoke_sessions_matching():
    db = AsyncMock()
    
    # Create real active sessions in memory
    session_1 = ActiveSession(revoked_at=None, jti="jti1")
    session_2 = ActiveSession(revoked_at=dt.datetime.now(dt.timezone.utc), jti="jti2")
    
    mock_exec_res = MagicMock()
    mock_exec_res.scalars.return_value = [session_1, session_2]
    db.execute.return_value = mock_exec_res
    
    mock_backend = AsyncMock()
    
    whereclause = (ActiveSession.id == ActiveSession.id)
    
    with patch("app.services.session_cleanup.get_session_backend", return_value=mock_backend):
        # 1. With rotate_signing_key = True (default)
        res = await revoke_sessions_matching(db=db, whereclause=whereclause)
        assert res == 2
        assert session_1.revoked_at is not None
        mock_backend.revoke_session.assert_called_once_with("jti1")
        assert session_1.signing_key is not None
        
        # 2. With rotate_signing_key = False
        session_3 = ActiveSession(revoked_at=None, jti="jti3")
        mock_exec_res.scalars.return_value = [session_3]
        
        res = await revoke_sessions_matching(db=db, whereclause=whereclause, rotate_signing_key=False)
        assert res == 1
        assert session_3.revoked_at is not None
        assert getattr(session_3, "signing_key", None) is None

    # 3. With revoke_session raising an exception (should be suppressed)
    session_4 = ActiveSession(revoked_at=None, jti="jti4")
    mock_exec_res.scalars.return_value = [session_4]
    
    mock_backend.revoke_session.side_effect = Exception("redis error")
    with patch("app.services.session_cleanup.get_session_backend", return_value=mock_backend):
        res = await revoke_sessions_matching(db=db, whereclause=whereclause)
        assert res == 1
        mock_backend.revoke_session.assert_called_with("jti4")

# ============================================================
# cleanup_expired_sessions tests
# ============================================================

@pytest.mark.anyio
async def test_cleanup_expired_sessions():
    db = AsyncMock()
    
    with patch("app.services.session_cleanup.delete_sessions_matching", return_value=5) as mock_delete:
        res = await cleanup_expired_sessions(db=db)
        assert res == 5
        mock_delete.assert_called_once()
        db.commit.assert_called_once()
        
    with patch("app.services.session_cleanup.delete_sessions_matching", return_value=0) as mock_delete:
        res = await cleanup_expired_sessions(db=db)
        assert res == 0
        
    # With owns_session (db = None)
    with patch("app.services.session_cleanup.async_session") as mock_session, \
         patch("app.services.session_cleanup.delete_sessions_matching", return_value=3) as mock_delete:
        mock_session.return_value.__aenter__.return_value = db
        res = await cleanup_expired_sessions()
        assert res == 3

# ============================================================
# start_session_cleanup_scheduler tests
# ============================================================

@pytest.mark.anyio
async def test_start_session_cleanup_scheduler_normal():
    config = SessionCleanupConfig(interval_seconds=30)
    
    real_sleep = asyncio.sleep
    async def mock_sleep_fn(delay, *args, **kwargs):
        await real_sleep(0.0001)
        
    with patch("app.services.session_cleanup.cleanup_expired_sessions", new_callable=AsyncMock) as mock_cleanup, \
         patch("app.services.session_cleanup.asyncio.sleep", side_effect=mock_sleep_fn) as mock_sleep:
        
        mock_cleanup.return_value = 4
        
        stop_fn = await start_session_cleanup_scheduler(config=config)
        assert stop_fn is not None
        
        await real_sleep(0.05)
        mock_cleanup.assert_called()
        mock_sleep.assert_called()
        await stop_fn()
        # Double stop when already done
        await stop_fn()

@pytest.mark.anyio
async def test_start_session_cleanup_scheduler_error():
    real_sleep = asyncio.sleep
    async def mock_sleep_fn(delay, *args, **kwargs):
        await real_sleep(0.0001)

    with patch("app.services.session_cleanup.cleanup_expired_sessions", new_callable=AsyncMock) as mock_cleanup, \
         patch("app.services.session_cleanup.asyncio.sleep", side_effect=mock_sleep_fn) as mock_sleep:
        
        mock_cleanup.side_effect = ValueError("db error")
        stop_fn = await start_session_cleanup_scheduler()
        await real_sleep(0.05)
        await stop_fn()

@pytest.mark.anyio
async def test_start_session_cleanup_scheduler_cancel_error():
    real_sleep = asyncio.sleep
    async def mock_sleep_fn(delay, *args, **kwargs):
        await real_sleep(0.0001)

    with patch("app.services.session_cleanup.cleanup_expired_sessions", new_callable=AsyncMock) as mock_cleanup, \
         patch("app.services.session_cleanup.asyncio.sleep", side_effect=mock_sleep_fn) as mock_sleep:
        
        mock_cleanup.side_effect = asyncio.CancelledError()
        stop_fn = await start_session_cleanup_scheduler()
        await real_sleep(0.05)
        await stop_fn()
