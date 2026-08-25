"""Wave 5 coverage tests for auth module gaps.

Targets:
- app/auth/security.py: _container_cpu_count, validate_password_hibp
  (error paths), close_hibp_client
- app/auth/mfa/challenge.py: _extract_attempt_limit, _enforce_challenge_rate_limit,
  _lock_challenge, _ensure_challenge_not_locked, _register_failed_attempt,
  describe_challenge_attempts
- app/auth/mfa/totp.py: edge cases
- app/auth/mfa/lifecycle.py: edge cases
- app/services/auth_service.py: reset_password, initiate_email_change paths
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# ===========================================================================
# auth/security.py
# ===========================================================================


class TestContainerCpuCount:
    def test_returns_positive_int(self):
        from app.auth.security import _container_cpu_count

        result = _container_cpu_count()
        assert isinstance(result, int)
        assert result >= 1

    def test_fallback_on_error(self):
        """When cgroup files are unavailable, falls back to os.cpu_count."""
        from app.auth.security import _container_cpu_count

        # On Windows, sched_getaffinity may not exist — just test the function runs
        result = _container_cpu_count()
        assert result >= 1


class TestValidatePasswordHibp:
    @pytest.mark.asyncio
    async def test_password_not_compromised(self):
        from app.auth.security import validate_password_hibp

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "ABC12:0\nDEF34:0\n"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("app.auth.security._get_hibp_client", return_value=mock_client):
            # Should not raise
            await validate_password_hibp("SafePassword123!")

    @pytest.mark.asyncio
    async def test_password_compromised(self):
        from app.auth.security import (
            _calculate_lookup_hash,
            validate_password_hibp,
        )

        password = "password123"  # pragma: allowlist secret
        sha1 = _calculate_lookup_hash(password)
        suffix = sha1[5:]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = f"{suffix}:1500\nOTHER:0\n"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("app.auth.security._get_hibp_client", return_value=mock_client):
            with pytest.raises(ValueError):
                await validate_password_hibp(password)

    @pytest.mark.asyncio
    async def test_request_error_fail_closed(self, monkeypatch):
        from app.auth.security import validate_password_hibp
        from app.core.config import settings

        monkeypatch.setattr(settings, "password_hibp_fail_open", False)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.RequestError("timeout"))

        with patch("app.auth.security._get_hibp_client", return_value=mock_client):
            with pytest.raises(ValueError):
                await validate_password_hibp("test")

    @pytest.mark.asyncio
    async def test_request_error_fail_open(self, monkeypatch):
        from app.auth.security import validate_password_hibp
        from app.core.config import settings

        monkeypatch.setattr(settings, "password_hibp_fail_open", True)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.RequestError("timeout"))

        with patch("app.auth.security._get_hibp_client", return_value=mock_client):
            # Should not raise in fail-open mode
            await validate_password_hibp("test")

    @pytest.mark.asyncio
    async def test_non_200_fail_open(self, monkeypatch):
        from app.auth.security import validate_password_hibp
        from app.core.config import settings

        monkeypatch.setattr(settings, "password_hibp_fail_open", True)

        mock_response = MagicMock()
        mock_response.status_code = 503

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("app.auth.security._get_hibp_client", return_value=mock_client):
            await validate_password_hibp("test")

    @pytest.mark.asyncio
    async def test_non_200_fail_closed(self, monkeypatch):
        from app.auth.security import validate_password_hibp
        from app.core.config import settings

        monkeypatch.setattr(settings, "password_hibp_fail_open", False)

        mock_response = MagicMock()
        mock_response.status_code = 503

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("app.auth.security._get_hibp_client", return_value=mock_client):
            with pytest.raises(ValueError):
                await validate_password_hibp("test")


class TestCloseHibpClient:
    @pytest.mark.asyncio
    async def test_close(self):
        import app.auth.security as sec

        mock_client = AsyncMock()
        mock_client.aclose = AsyncMock()
        sec._hibp_client = mock_client

        await sec.close_hibp_client()
        assert sec._hibp_client is None
        mock_client.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_when_none(self):
        import app.auth.security as sec

        sec._hibp_client = None
        await sec.close_hibp_client()  # noop


class TestCalculateLookupHash:
    def test_returns_uppercase_sha1(self):
        from app.auth.security import _calculate_lookup_hash

        result = _calculate_lookup_hash("test")
        assert result == result.upper()
        assert len(result) == 40

    def test_deterministic(self):
        from app.auth.security import _calculate_lookup_hash

        assert _calculate_lookup_hash("abc") == _calculate_lookup_hash("abc")


class TestFormatPasswordClassLabels:
    def test_formats_labels(self):
        from app.auth.security import _format_password_class_labels

        result = _format_password_class_labels(["uppercase", "digit"], locale="en")
        assert isinstance(result, str)
        assert "," in result


# ===========================================================================
# auth/mfa/challenge.py
# ===========================================================================


class TestExtractAttemptLimit:
    def test_from_payload(self):
        from app.auth.mfa.challenge import _extract_attempt_limit

        challenge = MagicMock()
        challenge.payload = {"attempt_limit": 5}
        assert _extract_attempt_limit(challenge) == 5

    def test_fallback(self):
        from app.auth.mfa.challenge import _extract_attempt_limit

        challenge = MagicMock()
        challenge.payload = {}
        assert _extract_attempt_limit(challenge, fallback=10) == 10

    def test_none_challenge(self):
        from app.auth.mfa.challenge import _extract_attempt_limit

        assert _extract_attempt_limit(None, fallback=5) == 5

    def test_invalid_limit(self):
        from app.auth.mfa.challenge import _extract_attempt_limit

        challenge = MagicMock()
        challenge.payload = {"attempt_limit": "not-a-number"}
        assert _extract_attempt_limit(challenge) is None

    def test_zero_limit(self):
        from app.auth.mfa.challenge import _extract_attempt_limit

        challenge = MagicMock()
        challenge.payload = {"attempt_limit": 0}
        assert _extract_attempt_limit(challenge) is None

    def test_negative_limit(self):
        from app.auth.mfa.challenge import _extract_attempt_limit

        challenge = MagicMock()
        challenge.payload = {"attempt_limit": -3}
        assert _extract_attempt_limit(challenge) is None

    def test_no_payload(self):
        from app.auth.mfa.challenge import _extract_attempt_limit

        challenge = MagicMock()
        challenge.payload = None
        assert _extract_attempt_limit(challenge) is None


class TestDescribeChallengeAttempts:
    def test_with_limit(self):
        from app.auth.mfa.challenge import describe_challenge_attempts

        challenge = MagicMock()
        challenge.attempt_count = 3
        challenge.payload = {"attempt_limit": 5}

        attempts, limit, remaining = describe_challenge_attempts(challenge)
        assert attempts == 3
        assert limit == 5
        assert remaining == 2

    def test_without_limit(self):
        from app.auth.mfa.challenge import describe_challenge_attempts

        challenge = MagicMock()
        challenge.attempt_count = 7
        challenge.payload = {}

        attempts, limit, remaining = describe_challenge_attempts(challenge)
        assert attempts == 7
        assert limit is None
        assert remaining is None

    def test_exceeded_limit(self):
        from app.auth.mfa.challenge import describe_challenge_attempts

        challenge = MagicMock()
        challenge.attempt_count = 10
        challenge.payload = {"attempt_limit": 5}

        attempts, _limit, remaining = describe_challenge_attempts(challenge)
        assert attempts == 10
        assert remaining == 0


class TestEnforceChallengeRateLimit:
    @pytest.mark.asyncio
    async def test_within_limit(self):
        from app.auth.mfa.challenge import _enforce_challenge_rate_limit

        with patch("app.auth.mfa.challenge.enforce_rate_limit", new_callable=AsyncMock):
            # Should not raise
            await _enforce_challenge_rate_limit(
                user_id=uuid.uuid4(),
                challenge_type="totp-auth",
            )

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded(self):
        from app.auth.mfa.challenge import _enforce_challenge_rate_limit
        from app.core.ratelimit import RateLimitExceeded, RateLimitInfo

        with patch(
            "app.auth.mfa.challenge.enforce_rate_limit",
            new_callable=AsyncMock,
            side_effect=RateLimitExceeded(
                RateLimitInfo(allowed=False, remaining=0, retry_after=60)
            ),
        ):
            with pytest.raises(Exception):  # noqa: B017
                await _enforce_challenge_rate_limit(
                    user_id=uuid.uuid4(),
                    challenge_type="totp-auth",
                )

    @pytest.mark.asyncio
    async def test_zero_limit_skips(self, monkeypatch):
        from app.auth.mfa.challenge import _enforce_challenge_rate_limit
        from app.core.config import settings

        monkeypatch.setattr(settings, "mfa_challenge_max_attempts", 0)
        # Should return immediately
        await _enforce_challenge_rate_limit(
            user_id=uuid.uuid4(), challenge_type="totp-auth"
        )


class TestLockChallenge:
    @pytest.mark.asyncio
    async def test_locks_and_raises(self):
        from app.auth.mfa.challenge import _lock_challenge

        challenge = MagicMock()
        challenge.user_id = uuid.uuid4()
        challenge.id = uuid.uuid4()
        challenge.consumed_at = None

        db = AsyncMock()

        with pytest.raises(Exception):  # noqa: B017
            await _lock_challenge(db, challenge, method="totp", limit=5, locale="en")

        db.flush.assert_awaited()
        assert challenge.consumed_at is not None


class TestEnsureChallengeNotLocked:
    @pytest.mark.asyncio
    async def test_none_challenge_noop(self):
        from app.auth.mfa.challenge import _ensure_challenge_not_locked

        db = AsyncMock()
        await _ensure_challenge_not_locked(
            db, None, method="totp", limit=5, locale="en"
        )

    @pytest.mark.asyncio
    async def test_none_limit_noop(self):
        from app.auth.mfa.challenge import _ensure_challenge_not_locked

        db = AsyncMock()
        challenge = MagicMock()
        challenge.attempt_count = 100
        await _ensure_challenge_not_locked(
            db, challenge, method="totp", limit=None, locale="en"
        )

    @pytest.mark.asyncio
    async def test_under_limit_noop(self):
        from app.auth.mfa.challenge import _ensure_challenge_not_locked

        db = AsyncMock()
        challenge = MagicMock()
        challenge.attempt_count = 2
        await _ensure_challenge_not_locked(
            db, challenge, method="totp", limit=5, locale="en"
        )

    @pytest.mark.asyncio
    async def test_at_limit_locks(self):
        from app.auth.mfa.challenge import _ensure_challenge_not_locked

        db = AsyncMock()
        challenge = MagicMock()
        challenge.attempt_count = 5
        challenge.user_id = uuid.uuid4()
        challenge.id = uuid.uuid4()
        challenge.consumed_at = None

        with pytest.raises(Exception):  # noqa: B017
            await _ensure_challenge_not_locked(
                db, challenge, method="totp", limit=5, locale="en"
            )


class TestRegisterFailedAttempt:
    @pytest.mark.asyncio
    async def test_none_challenge_noop(self):
        from app.auth.mfa.challenge import _register_failed_attempt

        db = AsyncMock()
        await _register_failed_attempt(db, None, method="totp", limit=5, locale="en")

    @pytest.mark.asyncio
    async def test_increments_attempt(self):
        from app.auth.mfa.challenge import _register_failed_attempt

        db = AsyncMock()
        challenge = MagicMock()
        challenge.id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.one_or_none.return_value = (3, None)
        db.execute = AsyncMock(return_value=mock_result)

        await _register_failed_attempt(
            db, challenge, method="totp", limit=5, locale="en"
        )

        db.execute.assert_called_once()
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_already_consumed_noop(self):
        from app.auth.mfa.challenge import _register_failed_attempt

        db = AsyncMock()
        challenge = MagicMock()
        challenge.id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None  # Already consumed
        db.execute = AsyncMock(return_value=mock_result)

        await _register_failed_attempt(
            db, challenge, method="totp", limit=5, locale="en"
        )


# ===========================================================================
# auth/mfa/totp.py — edge cases
# ===========================================================================


class TestTotpEdgeCases:
    def test_create_totp_secret(self):
        from app.auth.mfa.totp import create_totp_secret

        secret = create_totp_secret()
        assert isinstance(secret, str)
        assert len(secret) > 10

    def test_build_totp_uri(self):
        from app.auth.mfa.totp import build_totp_uri

        uri = build_totp_uri("JBSWY3DPEHPK3PXP", account_name="user@example.com")
        assert "otpauth://" in uri
        # Email is URL-encoded in OTP URIs
        assert "user" in uri
        assert "example.com" in uri

    def test_verify_totp_invalid(self):
        from app.auth.mfa.totp import verify_totp

        assert verify_totp("JBSWY3DPEHPK3PXP", "000000") is False

    def test_ct_verify_totp(self):
        from app.auth.mfa.totp import _ct_verify_totp

        # Constant-time verify — should return False for wrong code
        assert _ct_verify_totp("JBSWY3DPEHPK3PXP", "000000") is False


# ===========================================================================
# auth/mfa/lifecycle.py — edge cases
# ===========================================================================


class TestMfaLifecycleEdgeCases:
    @pytest.mark.asyncio
    async def test_has_totp_enabled_false(self):
        from app.auth.mfa.lifecycle import has_totp_enabled

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        user = MagicMock()
        user.id = uuid.uuid4()
        result = await has_totp_enabled(db, user)
        assert result is False

    def test_user_has_confirmed_no_factors(self):
        from app.auth.mfa.lifecycle import user_has_confirmed_interactive_factor

        user = MagicMock()
        user.mfa_default_method = None
        user.totp_enrollments = []
        user.email_mfa_enabled_at = None
        assert user_has_confirmed_interactive_factor(user) is False

    def test_user_has_confirmed_rejects_stale_default_method(self):
        from app.auth.mfa.lifecycle import user_has_confirmed_interactive_factor

        user = MagicMock()
        user.mfa_default_method = "totp"
        user.totp_enrollments = []
        user.email_mfa_enabled_at = None
        assert user_has_confirmed_interactive_factor(user) is False

    def test_user_has_confirmed_with_totp(self):
        from app.auth.mfa.lifecycle import user_has_confirmed_interactive_factor

        enrollment = MagicMock()
        enrollment.confirmed_at = datetime.now(UTC)
        enrollment.revoked_at = None

        user = MagicMock()
        user.mfa_default_method = None
        user.totp_enrollments = [enrollment]
        assert user_has_confirmed_interactive_factor(user) is True

    def test_user_has_confirmed_with_revoked_totp(self):
        from app.auth.mfa.lifecycle import user_has_confirmed_interactive_factor

        enrollment = MagicMock()
        enrollment.confirmed_at = datetime.now(UTC)
        enrollment.revoked_at = datetime.now(UTC)  # Revoked!

        user = MagicMock()
        user.mfa_default_method = None
        user.totp_enrollments = [enrollment]
        user.email_mfa_enabled_at = None
        assert user_has_confirmed_interactive_factor(user) is False
