"""Tests for modular configuration settings."""

import os
from unittest import mock

from app.config.database import DatabaseSettings
from app.config.notifications import NotificationsSettings
from app.config.security import SecuritySettings


class TestDatabaseSettings:
    """Tests for DatabaseSettings."""

    def test_default_values(self):
        """Test default database settings."""
        settings = DatabaseSettings()

        assert settings.database_pool_size == 5
        assert settings.database_max_overflow == 10
        assert settings.database_pool_timeout == 30.0
        assert settings.database_pool_recycle == 3600
        assert settings.database_echo is False

    def test_has_read_replica_false(self):
        """Test has_read_replica with no replica configured."""
        settings = DatabaseSettings()
        assert settings.has_read_replica is False

    def test_has_read_replica_true(self):
        """Test has_read_replica with replica configured."""
        settings = DatabaseSettings(
            database_read_url="postgresql+asyncpg://ro@localhost/db"
        )
        assert settings.has_read_replica is True


class TestSecuritySettings:
    """Tests for SecuritySettings."""

    def test_default_values(self):
        """Test security settings have expected types."""
        settings = SecuritySettings()

        assert isinstance(settings.algorithm, str)
        assert isinstance(settings.access_token_expire_minutes, int)
        assert settings.access_token_expire_minutes > 0
        assert isinstance(settings.password_hash_algorithm, str)
        assert isinstance(settings.cookie_secure, bool)
        assert isinstance(settings.cookie_samesite, str)

    def test_cors_origins_list_single(self):
        """Test CORS origins parsing with single origin."""
        settings = SecuritySettings(cors_allow_origins="http://localhost:3000")
        assert settings.cors_origins_list == ["http://localhost:3000"]

    def test_cors_origins_list_multiple(self):
        """Test CORS origins parsing with multiple origins."""
        settings = SecuritySettings(
            cors_allow_origins="http://localhost:3000, https://example.com"
        )
        assert settings.cors_origins_list == [
            "http://localhost:3000",
            "https://example.com",
        ]

    def test_mfa_defaults(self):
        """Test MFA default settings."""
        settings = SecuritySettings()
        assert settings.mfa_required_default is False
        assert settings.mfa_totp_attempt_limit == 5


class TestNotificationsSettings:
    """Tests for NotificationsSettings."""

    def test_default_values(self):
        """Test default notification settings."""
        settings = NotificationsSettings()

        assert settings.push_batch_size == 100
        assert settings.push_retry_attempts == 3
        assert settings.push_ttl_seconds == 86400
        assert settings.notification_retention_days == 90

    def test_has_vapid_keys_false(self):
        """Test has_vapid_keys without keys."""
        with mock.patch.dict(
            os.environ, {"VAPID_PRIVATE_KEY": "", "VAPID_PUBLIC_KEY": ""}
        ):
            settings = NotificationsSettings()
            assert settings.has_vapid_keys is False

    def test_has_vapid_keys_true(self):
        """Test has_vapid_keys with keys configured."""
        settings = NotificationsSettings(
            vapid_private_key="private_key",
            vapid_public_key="public_key",
        )
        assert settings.has_vapid_keys is True

    def test_quiet_hours(self):
        """Test quiet hours defaults."""
        settings = NotificationsSettings()
        assert settings.quiet_hours_start == 22
        assert settings.quiet_hours_end == 7

    def test_schedule_reminder(self):
        """Test schedule reminder minutes."""
        settings = NotificationsSettings()
        assert settings.schedule_reminder_minutes == 15


class TestConfigImports:
    """Test config package imports."""

    def test_database_settings_importable(self):
        """Test DatabaseSettings can be imported from package."""
        from app.config import DatabaseSettings as PkgDatabaseSettings

        assert PkgDatabaseSettings is not None

    def test_security_settings_importable(self):
        """Test SecuritySettings can be imported from package."""
        from app.config import SecuritySettings as PkgSecuritySettings

        assert PkgSecuritySettings is not None

    def test_notifications_settings_importable(self):
        """Test NotificationsSettings can be imported from package."""
        from app.config import NotificationsSettings as PkgNotificationsSettings

        assert PkgNotificationsSettings is not None
