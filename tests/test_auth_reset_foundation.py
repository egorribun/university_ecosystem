"""Focused contracts for auth reset configuration, identity privacy, and CLI preflight."""

from __future__ import annotations

import hashlib
import hmac
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from app.core.config.security import SecuritySettings
from app.services.auth_service import (
    AuthService,
    _password_reset_rate_limit_identifier,
)

runner = CliRunner()


def test_token_hmac_secret_loads_from_file(tmp_path, monkeypatch):
    secret_file = tmp_path / "token-hmac-secret"
    secret = (
        "token-hmac-" + "random-material-0123456789abcdef"
    )  # pragma: allowlist secret
    secret_file.write_text(f"\n{secret}\n", encoding="utf-8")
    monkeypatch.setenv("TOKEN_HMAC_SECRET_FILE", str(secret_file))
    monkeypatch.delenv("TOKEN_HMAC_SECRET", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "testing")

    settings = SecuritySettings()

    assert settings.token_hmac_secret == secret


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_token_hmac_secret_is_required_and_has_entropy(monkeypatch, environment):
    monkeypatch.setenv("ENVIRONMENT", environment)
    with pytest.raises(ValueError, match="TOKEN_HMAC_SECRET"):
        SecuritySettings(token_hmac_secret=None)
    with pytest.raises(ValueError, match="entropy"):
        SecuritySettings(token_hmac_secret="a" * 64)


def test_token_hmac_secret_rejects_blank_short_placeholder_and_patterned_values(
    monkeypatch,
):
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(ValueError, match="explicitly configured"):
        SecuritySettings(token_hmac_secret="   ")
    with pytest.raises(ValueError, match="at least 32 bytes"):
        SecuritySettings(token_hmac_secret="short")  # pragma: allowlist secret
    with pytest.raises(ValueError, match="placeholder or repeated"):
        SecuritySettings(  # pragma: allowlist secret
            token_hmac_secret="example-recovery-key-material-0123456789"  # pragma: allowlist secret
        )
    with pytest.raises(ValueError, match="placeholder or repeated"):
        SecuritySettings(token_hmac_secret="abcd" * 16)  # pragma: allowlist secret


def test_token_hmac_secret_blank_is_allowed_only_in_development(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "testing")

    assert SecuritySettings(token_hmac_secret="   ").token_hmac_secret is None


def test_token_hmac_secret_accepts_random_production_value(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    secret = (  # pragma: allowlist secret
        "6d4b4a4a-fd2f-4a74-a63a-746cc0f244f1/" + "qX8!"
    )
    settings = SecuritySettings(
        token_hmac_secret=secret,  # pragma: allowlist secret
        algorithm="RS256",
        audit_log_secret="audit-log-random-material-0123456789abcdef",  # pragma: allowlist secret
        internal_hmac_secret="internal-hmac-random-material-0123456789",  # pragma: allowlist secret
    )
    assert settings.token_hmac_secret == secret


def test_password_reset_identifier_is_canonical_domain_separated(monkeypatch):
    settings = SimpleNamespace(
        token_hmac_secret="reset-secret-with-at-least-32-bytes-0000",  # pragma: allowlist secret
        environment="testing",
        secret_key="fallback-not-used",  # pragma: allowlist secret
    )
    monkeypatch.setattr("app.services.auth_service.settings", settings)

    first = _password_reset_rate_limit_identifier("  Student@Example.EDU ")
    second = _password_reset_rate_limit_identifier("student@example.edu")
    expected = hmac.new(
        settings.token_hmac_secret.encode(),
        b"password-reset-rate-limit-v1\x1fstudent@example.edu",
        hashlib.sha256,
    ).hexdigest()

    assert first == second == f"password-reset:{expected}"
    assert len(first.rsplit(":", 1)[-1]) == 64
    assert "student@example.edu" not in first
    assert "@" not in first


def test_rate_limit_hmac_false_positive_has_narrow_codeql_disposition():
    source = (
        Path(__file__).parents[1] / "app" / "services" / "auth_service.py"
    ).read_text(encoding="utf-8")
    helper = source.split("def _password_reset_rate_limit_identifier", 1)[1].split(
        "class AuthService", 1
    )[0]

    assert "hmac.new" in helper
    assert "HMAC-SHA256 pseudonymous rate-limit key, not password storage" in helper
    assert "# codeql[py/weak-sensitive-data-hashing]" in helper


@pytest.mark.asyncio
async def test_forgot_password_rate_limit_uses_private_key_before_lookup(monkeypatch):
    service = AuthService(
        audit=MagicMock(),
        auth_repo=MagicMock(),
        user_repo=MagicMock(),
        session_repo=MagicMock(),
        uow=MagicMock(),
    )
    service.user_repo.get_by_email = AsyncMock(return_value=None)
    calls: list[tuple[str, str]] = []

    async def capture_limit(*, identifier, **_kwargs):
        calls.append(("limit", identifier))

    async def capture_lookup(email):
        calls.append(("lookup", email))
        return None

    service.user_repo.get_by_email.side_effect = capture_lookup
    monkeypatch.setattr("app.core.ratelimit.enforce_rate_limit", capture_limit)
    monkeypatch.setattr(
        "app.services.auth_service.settings",
        SimpleNamespace(
            token_hmac_secret="reset-secret-with-at-least-32-bytes-0000",  # pragma: allowlist secret
            environment="testing",
            secret_key="fallback-not-used",  # pragma: allowlist secret
            app_base_url_clean="http://localhost",
        ),
    )
    monkeypatch.setattr("app.services.auth_service.resolve_locale", lambda **_: "en")
    request = MagicMock()

    with patch("asyncio.sleep", new=AsyncMock()):
        await service.initiate_password_reset(
            "  Student@Example.EDU ", request, MagicMock()
        )

    assert calls[0][0] == "limit"
    assert calls[1] == ("lookup", "student@example.edu")
    assert "student@example.edu" not in calls[0][1]
    assert "@" not in calls[0][1]


def test_migration_cli_has_read_only_assert_none_contract():
    from app.cli import migrate_passwords

    result = runner.invoke(migrate_passwords.app, ["assert-none", "--help"])
    assert result.exit_code == 0
    assert "legacy bcrypt" in result.stdout.lower()
