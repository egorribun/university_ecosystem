"""Closure tests for provider initialization success and DCL recheck."""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

from app.core import feature_flags


def test_ensure_provider_initializes_flagd_provider_successfully():
    provider = MagicMock()
    flagd_module = ModuleType("openfeature.contrib.provider.flagd")
    flagd_module.FlagdProvider = MagicMock(return_value=provider)

    with (
        patch.object(feature_flags, "_provider_initialized", False),
        patch.dict(sys.modules, {"openfeature.contrib.provider.flagd": flagd_module}),
        patch("openfeature.api.set_provider") as set_provider,
        patch(
            "app.core.config.settings",
            SimpleNamespace(flagd_host="flagd", flagd_port=8013),
        ),
    ):
        feature_flags._ensure_provider()

    flagd_module.FlagdProvider.assert_called_once_with(host="flagd", port=8013)
    set_provider.assert_called_once_with(provider)


def test_ensure_provider_double_check_returns_after_another_initializer_wins():
    class WinningLock:
        def __enter__(self):
            feature_flags._provider_initialized = True

        def __exit__(self, exc_type, exc, traceback):
            return False

    with (
        patch.object(feature_flags, "_provider_initialized", False),
        patch.object(feature_flags, "_provider_lock", WinningLock()),
    ):
        feature_flags._ensure_provider()
        assert feature_flags._provider_initialized is True
