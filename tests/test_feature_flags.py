"""Modern tests for Feature Flags system using OpenFeature.

These tests replace the legacy FeatureFlag/FlagStatus/FeatureFlagService tests
which were skipped during the OpenFeature migration.
"""

from unittest.mock import MagicMock, patch

import pytest
from openfeature.evaluation_context import EvaluationContext

from app.core.feature_flags import (
    FLAG_NEW_CHAT_UI,
    FLAG_PUSH_BATCHING,
    feature_flags,
    is_enabled,
    is_enabled_sync,
)


@pytest.mark.asyncio
async def test_is_enabled_calls_openfeature():
    """Test that is_enabled correctly interacts with OpenFeature API."""
    with patch("openfeature.api.get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.get_boolean_value.return_value = True
        mock_get_client.return_value = mock_client

        result = await is_enabled(FLAG_NEW_CHAT_UI, context={"user_id": "42"})

        assert result is True
        mock_client.get_boolean_value.assert_called_once()
        args, _kwargs = mock_client.get_boolean_value.call_args
        assert args[0] == FLAG_NEW_CHAT_UI
        assert isinstance(args[2], EvaluationContext)
        assert args[2].attributes == {"user_id": "42"}


def test_is_enabled_sync_calls_openfeature():
    """Test that is_enabled_sync correctly interacts with OpenFeature API."""
    with patch("openfeature.api.get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.get_boolean_value.return_value = False
        mock_get_client.return_value = mock_client

        result = is_enabled_sync(FLAG_PUSH_BATCHING, default=True)

        assert result is False
        mock_client.get_boolean_value.assert_called_once_with(
            FLAG_PUSH_BATCHING, True, None
        )


@pytest.mark.asyncio
async def test_is_enabled_handles_exceptions():
    """Test that is_enabled falls back to default on provider errors."""
    with patch("openfeature.api.get_client", side_effect=Exception("Provider down")):
        result = await is_enabled("some-flag", default=True)
        assert result is True


class TestLegacyFeatureFlagsBridge:
    """Tests for the backward-compatibility bridge."""

    def test_list_flags(self):
        with patch("app.core.feature_flags.is_enabled_sync", return_value=True):
            flags = feature_flags.list_flags()
            assert len(flags) > 0
            assert all("name" in f and "enabled" in f for f in flags)
            assert any(f["name"] == FLAG_PUSH_BATCHING for f in flags)

    @pytest.mark.asyncio
    async def test_update_shim(self):
        # Update is a no-op in flagd but returns the updated state
        result = await feature_flags.update(FLAG_NEW_CHAT_UI, enabled=True)
        assert result["name"] == FLAG_NEW_CHAT_UI
        assert result["enabled"] is True

    def test_to_dict(self):
        with patch("app.core.feature_flags.is_enabled_sync", return_value=False):
            d = feature_flags.to_dict()
            assert isinstance(d, dict)
            assert FLAG_NEW_CHAT_UI in d
            assert d[FLAG_NEW_CHAT_UI] is False
