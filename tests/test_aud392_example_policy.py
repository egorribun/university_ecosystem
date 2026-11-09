"""AUD-392: the example's policy values reach deployed password hashing."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

import pytest

from app.auth import security
from app.core.config import Settings
from tests.test_aud392_password_policy_defaults import (
    ELEVEN_CHARACTERS,
    TWELVE_CHARACTERS,
    WEAK_SCORE_ONE,
)
from tests.test_aud467_settings_integration_environment import (
    _valid_production_settings,
)

EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"
POLICY_NAMES = (
    "PASSWORD_MIN_LENGTH",
    "PASSWORD_MAX_LENGTH",
    "PASSWORD_MIN_CHARACTER_CLASSES",
    "PASSWORD_ZXCVBN_MIN_SCORE",
)


@pytest.mark.parametrize("environment", ("staging", "production"))
@pytest.mark.parametrize(
    ("candidate", "reason"),
    (
        pytest.param(ELEVEN_CHARACTERS, "length", id="short"),
        pytest.param(WEAK_SCORE_ONE, "strength", id="weak-score"),
        pytest.param(TWELVE_CHARACTERS, None, id="strong-control"),
    ),
)
async def test_example_password_policy_through_deployed_hashing(
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
    candidate: str,
    reason: str | None,
) -> None:
    with monkeypatch.context() as config_patch:
        # Do not read operator values or mounted secrets when building Settings.
        field_names = {name.upper() for name in Settings.model_fields}
        for name in tuple(os.environ):
            if name.upper() in field_names or name.upper().endswith("_FILE"):
                config_patch.delenv(name, raising=False)

        found: dict[str, str] = {}
        for line in EXAMPLE.read_text(encoding="utf-8").splitlines():
            name, separator, value = line.partition("=")
            if separator and name in POLICY_NAMES:
                assert name not in found
                found[name] = value
        assert set(found) == set(POLICY_NAMES)
        for name, value in found.items():
            config_patch.setenv(name, value)

        # The example's local HIBP opt-out fails deployed startup. Enable it here
        # so that the separate password-policy values are exercised after startup.
        config_patch.setenv("PASSWORD_HIBP_CHECK_ENABLED", "true")
        settings_inputs = _valid_production_settings()
        settings_inputs.update(
            environment=environment,
            elasticsearch_password=secrets.token_urlsafe(32),
            _env_file=None,
        )
        deployed = Settings(**settings_inputs)
    assert {name.lower() for name in POLICY_NAMES} <= deployed.model_fields_set
    assert deployed.password_hibp_check_enabled is True
    monkeypatch.setattr(security, "settings", deployed)
    monkeypatch.setattr(security, "translate", lambda key, **_: key)

    if reason is None:
        assert (await security.get_password_hash(candidate)).startswith("$argon2")
    else:
        with pytest.raises(ValueError, match=f"password_policy_{reason}"):
            await security.get_password_hash(candidate)
