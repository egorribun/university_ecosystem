"""A development fallback from an unreadable RS256 key must say why."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

import app.core.config.mixins.jwt_settings as jwt_settings_module
from app.core.config.mixins.jwt_settings import JwtSettingsMixin


def test_missing_private_key_fallback_warning_names_the_path_and_the_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    missing = str(tmp_path / "missing-private-key.pem")
    logger = MagicMock()
    monkeypatch.setattr(jwt_settings_module, "_logger", logger)
    mixin = type(
        "JwtConfig",
        (JwtSettingsMixin,),
        {
            "jwt_signing_keys": "",
            "jwt_active_kid": None,
            "algorithm": "RS256",
            "jwt_private_key_path": missing,
            "secret_key": "s" * 48,  # pragma: allowlist secret
            "environment": "development",
        },
    )()

    entries = mixin._build_jwt_signing_key_entries()

    assert entries == [("primary", "s" * 48)]
    logger.warning.assert_called_once()
    message, *arguments = logger.warning.call_args.args
    assert arguments[0] == missing
    assert isinstance(arguments[1], FileNotFoundError)
    rendered = message % tuple(arguments)
    assert missing in rendered
    assert "missing-private-key.pem" in rendered
    assert "No such file" in rendered or "cannot find" in rendered.lower()
