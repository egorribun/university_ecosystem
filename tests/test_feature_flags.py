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


@pytest.mark.asyncio
async def test_feature_flags_additional_coverage():
    # 1. Test bridge initialize/close
    await feature_flags.initialize()
    await feature_flags.close()

    # 2. Test bridge update with invalid name
    res = await feature_flags.update("non-existent-flag", enabled=True)
    assert res is None

    # 3. Test bridge update with enabled=None
    res = await feature_flags.update(FLAG_NEW_CHAT_UI, enabled=None)
    assert res["name"] == FLAG_NEW_CHAT_UI
    assert res["enabled"] is False

    # 4. Test is_enabled_sync exception handling
    with patch("openfeature.api.get_client", side_effect=Exception("Sync error")):
        assert is_enabled_sync("some-flag", default=True) is True

    # 5. Test _ensure_provider fast path (already initialized)
    from app.core.feature_flags import _ensure_provider
    with patch("app.core.feature_flags._provider_initialized", True):
        # Should return immediately
        _ensure_provider()

    # 6. Test _ensure_provider flagd initialization exception
    import sys
    mock_flagd = MagicMock()
    mock_flagd.FlagdProvider = MagicMock(side_effect=ValueError("Flagd init error"))
    with patch.dict(sys.modules, {"openfeature.contrib.provider.flagd": mock_flagd}):
        with patch("app.core.feature_flags._provider_initialized", False):
            _ensure_provider()

    # 7. Test _ensure_provider ImportError fallback
    import builtins
    orig_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if "openfeature" in name:
            raise ImportError("Simulated import error")
        return orig_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=mock_import):
        with patch("app.core.feature_flags._provider_initialized", False):
            _ensure_provider()

    # 8. Test is_enabled ImportError fallback
    with patch("builtins.__import__", side_effect=mock_import):
        res = await is_enabled("some-flag", default=True)
        assert res is True

    # 9. Test is_enabled_sync ImportError fallback
    with patch("builtins.__import__", side_effect=mock_import):
        res = is_enabled_sync("some-flag", default=True)
        assert res is True

