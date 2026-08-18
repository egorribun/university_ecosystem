"""Feature-flag evaluation and lifecycle tests."""

import subprocess
import sys
import textwrap
from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from openfeature.evaluation_context import EvaluationContext

from app.core.feature_flags import (
    FLAG_NEW_CHAT_UI,
    FLAG_PUSH_BATCHING,
    initialize_feature_flags,
    is_enabled,
    is_enabled_sync,
    list_feature_flags,
    shutdown_feature_flags,
)


@pytest.fixture(autouse=True)
def _isolate_openfeature_provider() -> Iterator[None]:
    """Keep unit tests from opening a real background gRPC channel."""
    with patch("app.core.feature_flags._provider_initialized", True):
        yield


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


def test_list_feature_flags_reports_evaluation_and_gitops_ownership():
    details = MagicMock(
        value=True,
        reason="TARGETING_MATCH",
    )
    provider_metadata = SimpleNamespace(name="flagd Provider")
    with (
        patch("openfeature.api.get_client") as get_client,
        patch("openfeature.api.get_provider_metadata", return_value=provider_metadata),
    ):
        get_client.return_value.get_boolean_details.return_value = details
        flags = list_feature_flags()

    assert len(flags) == 4
    assert flags[0] == {
        "name": FLAG_NEW_CHAT_UI,
        "enabled": True,
        "default": False,
        "description": "Enable the next-generation chat interface.",
        "provider": "flagd Provider",
        "evaluation_reason": "TARGETING_MATCH",
        "management": "gitops",
        "config_path": "k8s/flagd/flags.json",
    }
    assert get_client.return_value.get_boolean_details.call_count == 4


def test_list_feature_flags_reports_unavailable_provider_with_fallbacks():
    with (
        patch(
            "openfeature.api.get_provider_metadata",
            return_value=SimpleNamespace(name="FlagdProvider"),
        ),
        patch("openfeature.api.get_client", side_effect=RuntimeError("provider down")),
    ):
        flags = list_feature_flags()

    assert [flag["enabled"] for flag in flags] == [False, False, True, False]
    assert {flag["provider"] for flag in flags} == {"unavailable"}
    assert {flag["evaluation_reason"] for flag in flags} == {"ERROR"}


def test_list_feature_flags_reports_default_noop_provider_as_unavailable():
    """The SDK no-op provider must never look like a healthy control plane."""
    provider_metadata = SimpleNamespace(
        name="No-op Provider",
        is_default_provider=True,
    )
    with (
        patch("openfeature.api.get_client") as get_client,
        patch("openfeature.api.get_provider_metadata", return_value=provider_metadata),
    ):
        flags = list_feature_flags()

    get_client.return_value.get_boolean_details.assert_not_called()
    assert [flag["enabled"] for flag in flags] == [False, False, True, False]
    assert {flag["provider"] for flag in flags} == {"unavailable"}
    assert {flag["evaluation_reason"] for flag in flags} == {"ERROR"}


def test_list_feature_flags_isolates_an_individual_evaluation_failure():
    details = MagicMock(value=True, reason="DEFAULT")
    with (
        patch("openfeature.api.get_client") as get_client,
        patch(
            "openfeature.api.get_provider_metadata",
            return_value=SimpleNamespace(name="FlagdProvider"),
        ),
    ):
        get_client.return_value.get_boolean_details.side_effect = [
            RuntimeError("bad flag"),
            details,
            details,
            details,
        ]
        flags = list_feature_flags()

    assert flags[0]["enabled"] is False
    assert flags[0]["evaluation_reason"] == "ERROR"
    assert all(flag["provider"] == "FlagdProvider" for flag in flags)
    assert [flag["evaluation_reason"] for flag in flags[1:]] == [
        "DEFAULT",
        "DEFAULT",
        "DEFAULT",
    ]


@pytest.mark.asyncio
async def test_feature_flags_additional_coverage():
    await initialize_feature_flags()
    await shutdown_feature_flags()

    with patch("openfeature.api.get_client", side_effect=Exception("Sync error")):
        assert is_enabled_sync("some-flag", default=True) is True

    from app.core.feature_flags import _ensure_provider

    with patch("app.core.feature_flags._provider_initialized", True):
        # Should return immediately
        _ensure_provider()

    # Provider construction errors degrade to safe call-site defaults.
    import sys

    mock_flagd = MagicMock()
    mock_flagd.FlagdProvider = MagicMock(side_effect=ValueError("Flagd init error"))
    with patch.dict(sys.modules, {"openfeature.contrib.provider.flagd": mock_flagd}):
        with patch("app.core.feature_flags._provider_initialized", False):
            _ensure_provider()

    # Packaging errors degrade to safe call-site defaults and are logged.
    import builtins

    orig_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if "openfeature" in name:
            raise ImportError("Simulated import error")
        return orig_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=mock_import):
        with patch("app.core.feature_flags._provider_initialized", False):
            _ensure_provider()

    # Evaluation remains fail-safe if the SDK cannot be imported at runtime.
    with patch("builtins.__import__", side_effect=mock_import):
        res = await is_enabled("some-flag", default=True)
        assert res is True

    with patch("builtins.__import__", side_effect=mock_import):
        res = is_enabled_sync("some-flag", default=True)
        assert res is True


def test_flagd_provider_is_a_required_runtime_dependency():
    from openfeature.contrib.provider.flagd import FlagdProvider

    assert FlagdProvider is not None


def test_real_flagd_provider_shutdown_releases_background_resources():
    """A configured gRPC resolver must not keep the interpreter alive."""
    script = textwrap.dedent(
        """
        import asyncio

        from openfeature import api as of_api
        from openfeature.contrib.provider.flagd import FlagdProvider

        from app.core import feature_flags

        of_api.set_provider(FlagdProvider(host="127.0.0.1", port=65534))
        feature_flags._provider_initialized = True
        asyncio.run(feature_flags.shutdown_feature_flags())
        assert feature_flags._provider_initialized is False
        """
    )

    completed = subprocess.run(  # noqa: S603 - fixed interpreter and script
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert completed.returncode == 0


@pytest.mark.asyncio
async def test_shutdown_feature_flags_is_best_effort_and_resets_lifecycle():
    from app.core import feature_flags as feature_flags_module

    with (
        patch.object(feature_flags_module, "_provider_initialized", True),
        patch("openfeature.api.shutdown", side_effect=RuntimeError("shutdown failed")),
    ):
        await shutdown_feature_flags()
        assert feature_flags_module._provider_initialized is False


@pytest.mark.asyncio
async def test_admin_feature_flag_handlers_delegate_and_reject_legacy_writes():
    """Keep the thin HTTP adapter covered without database or gRPC side effects."""
    from app.api.admin import feature_flags as admin_feature_flags

    snapshot = {
        "name": FLAG_NEW_CHAT_UI,
        "enabled": False,
        "default": False,
        "description": "Enable the next-generation chat interface.",
        "provider": "unavailable",
        "evaluation_reason": "ERROR",
        "management": "gitops",
        "config_path": "k8s/flagd/flags.json",
    }
    with patch.object(
        admin_feature_flags,
        "list_feature_flag_snapshots",
        return_value=[snapshot],
    ) as list_snapshots:
        result = await admin_feature_flags.list_feature_flags(MagicMock())

    assert result == [snapshot]
    list_snapshots.assert_called_once_with()

    with pytest.raises(HTTPException) as caught:
        await admin_feature_flags.reject_feature_flag_update(
            FLAG_NEW_CHAT_UI,
            MagicMock(),
        )

    assert caught.value.status_code == 405
    assert caught.value.headers == {"Allow": "GET"}
    assert "k8s/flagd/flags.json" in str(caught.value.detail)
