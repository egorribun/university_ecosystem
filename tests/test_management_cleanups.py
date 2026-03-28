from unittest.mock import AsyncMock, patch

from app.management.stories_cleanup import main as stories_main
from app.management.weekly_cleanup import main as weekly_main


def test_stories_cleanup_main():
    with patch(
        "app.management.stories_cleanup.cleanup_expired_stories", new_callable=AsyncMock
    ) as mock_cleanup:
        mock_cleanup.return_value = 5
        with patch("app.management.stories_cleanup.logger") as mock_log:
            stories_main()
            mock_cleanup.assert_called_once()
            # Source uses lazy logging: logger.info("Removed %s expired stories", removed)
            mock_log.info.assert_any_call("Removed %s expired stories", 5)


def test_weekly_cleanup_main():
    with patch(
        "app.management.weekly_cleanup.run_weekly_cleanup", new_callable=AsyncMock
    ) as mock_run:
        mock_run.return_value = {
            "subscriptions_removed": 10,
            "subscriptions_orphaned": 4,
            "subscriptions_stale": 6,
        }
        with patch("app.management.weekly_cleanup.logger") as mock_log:
            weekly_main()
            mock_run.assert_called_once()
            # Source uses lazy logging: logger.info("Weekly cleanup finished: %s", stats)
            mock_log.info.assert_any_call(
                "Weekly cleanup finished: %s", mock_run.return_value
            )
