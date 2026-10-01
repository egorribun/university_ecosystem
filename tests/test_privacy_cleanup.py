"""Tests for privacy cleanup service (app/services/privacy_cleanup.py).

Validates retention cutoff calculation, config normalization, artifact cleanup
for sessions/MFA/failed logins, scheduler lifecycle, and metrics tracking.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.privacy_cleanup import (
    PrivacyCleanupConfig,
    _cutoff,
    cleanup_privacy_artifacts,
)

# ---------------------------------------------------------------------------
# _cutoff: correct calculation
# ---------------------------------------------------------------------------


class TestCutoff:
    """Tests for the _cutoff retention date helper."""

    def test_positive_retention_days(self):
        """Cutoff is now minus retention_days."""
        cutoff = _cutoff(30)
        expected = datetime.now(UTC) - timedelta(days=30)
        # Allow 2 seconds of clock drift
        assert abs((cutoff - expected).total_seconds()) < 2

    def test_zero_retention_days(self):
        """Zero retention_days means cutoff is approximately now."""
        cutoff = _cutoff(0)
        now = datetime.now(UTC)
        assert abs((cutoff - now).total_seconds()) < 2

    def test_negative_retention_days(self):
        """Negative retention_days is clamped to 0 via max(0, ...)."""
        cutoff = _cutoff(-10)
        now = datetime.now(UTC)
        # max(0, -10) == 0, so cutoff should be approximately now
        assert abs((cutoff - now).total_seconds()) < 2

    def test_large_retention_days(self):
        """Large retention_days produces a cutoff far in the past."""
        cutoff = _cutoff(365)
        expected = datetime.now(UTC) - timedelta(days=365)
        assert abs((cutoff - expected).total_seconds()) < 2


# ---------------------------------------------------------------------------
# PrivacyCleanupConfig
# ---------------------------------------------------------------------------


class TestPrivacyCleanupConfig:
    """Tests for the PrivacyCleanupConfig dataclass."""

    def test_default_values(self):
        """Verify default configuration values."""
        config = PrivacyCleanupConfig()
        assert config.session_retention_days == 90
        assert config.mfa_retention_days == 30
        assert config.failed_login_retention_days == 30
        assert config.audit_log_retention_days == 180
        assert config.interval_seconds == 86_400

    def test_custom_values(self):
        """Custom values override defaults."""
        config = PrivacyCleanupConfig(
            session_retention_days=7,
            mfa_retention_days=14,
            interval_seconds=3600,
        )
        assert config.session_retention_days == 7
        assert config.mfa_retention_days == 14
        assert config.interval_seconds == 3600

    def test_normalized_interval_above_minimum(self):
        """normalized_interval returns original value when >= 60."""
        config = PrivacyCleanupConfig(interval_seconds=120)
        assert config.normalized_interval() == 120

    def test_normalized_interval_below_minimum(self):
        """normalized_interval clamps to 60 seconds minimum."""
        config = PrivacyCleanupConfig(interval_seconds=10)
        assert config.normalized_interval() == 60

    def test_normalized_interval_exactly_60(self):
        """normalized_interval returns 60 when set to exactly 60."""
        config = PrivacyCleanupConfig(interval_seconds=60)
        assert config.normalized_interval() == 60

    def test_normalized_interval_zero(self):
        """normalized_interval clamps 0 to 60."""
        config = PrivacyCleanupConfig(interval_seconds=0)
        assert config.normalized_interval() == 60

    def test_normalized_interval_negative(self):
        """normalized_interval clamps negative values to 60."""
        config = PrivacyCleanupConfig(interval_seconds=-100)
        assert config.normalized_interval() == 60


# ---------------------------------------------------------------------------
# cleanup_privacy_artifacts
# ---------------------------------------------------------------------------


class TestCleanupPrivacyArtifacts:
    """Tests for the cleanup_privacy_artifacts function."""

    @pytest.mark.asyncio
    async def test_counts_returned_correctly(self):
        """All artifact types return their deletion counts."""
        config = PrivacyCleanupConfig()
        mock_db = AsyncMock()

        # Mock execute to return a result with rowcount
        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        with patch(
            "app.services.privacy_cleanup.cleanup_access_logs",
            new_callable=AsyncMock,
            return_value=3,
        ):
            counts = await cleanup_privacy_artifacts(db=mock_db, config=config)

        assert "sessions" in counts
        assert "mfa_challenges" in counts
        assert "mfa_enrollments" in counts
        assert "failed_logins" in counts
        assert "access_logs" in counts
        assert counts["access_logs"] == 3
        # Each of the 4 DB operations returns rowcount=5
        assert counts["sessions"] == 5

    @pytest.mark.asyncio
    async def test_db_none_creates_own_session(self):
        """When db=None, cleanup_privacy_artifacts creates its own session."""
        config = PrivacyCleanupConfig()

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(
                "app.services.privacy_cleanup.async_session",
                return_value=mock_context,
            ),
            patch(
                "app.services.privacy_cleanup.cleanup_access_logs",
                new_callable=AsyncMock,
                return_value=0,
            ),
        ):
            counts = await cleanup_privacy_artifacts(db=None, config=config)

        assert isinstance(counts, dict)

    @pytest.mark.asyncio
    async def test_metrics_tracking(self):
        """Metrics context manager is invoked during cleanup."""
        config = PrivacyCleanupConfig()
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.rowcount = 2
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        mock_run = MagicMock()
        mock_run.observe_deleted = MagicMock()

        mock_track = AsyncMock()
        mock_track.__aenter__ = AsyncMock(return_value=mock_run)
        mock_track.__aexit__ = AsyncMock(return_value=None)

        mock_metrics = MagicMock()
        mock_metrics.track_execution.return_value = mock_track

        with (
            patch(
                "app.services.privacy_cleanup._METRICS",
                mock_metrics,
            ),
            patch(
                "app.services.privacy_cleanup.cleanup_access_logs",
                new_callable=AsyncMock,
                return_value=1,
            ),
        ):
            counts = await cleanup_privacy_artifacts(db=mock_db, config=config)

        # observe_deleted should be called with total count
        total = sum(counts.values())
        mock_run.observe_deleted.assert_called_once_with(total)

    @pytest.mark.asyncio
    async def test_zero_rowcount_handled(self):
        """When no records are deleted, rowcount=None is handled as 0."""
        config = PrivacyCleanupConfig()
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.rowcount = None  # Some drivers return None for 0 rows
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        with patch(
            "app.services.privacy_cleanup.cleanup_access_logs",
            new_callable=AsyncMock,
            return_value=0,
        ):
            counts = await cleanup_privacy_artifacts(db=mock_db, config=config)

        for artifact_type, count in counts.items():
            assert count >= 0


# ---------------------------------------------------------------------------
# start_privacy_cleanup_scheduler
# ---------------------------------------------------------------------------
