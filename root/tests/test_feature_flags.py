"""Tests for Feature Flags system."""

import pytest

from app.core.feature_flags import (
    FeatureFlag,
    FeatureFlagService,
    FlagStatus,
    feature_flags,
)


class TestFeatureFlag:
    """Tests for FeatureFlag dataclass."""

    def test_disabled_flag(self):
        """Test disabled flag returns False."""
        flag = FeatureFlag(name="test", status=FlagStatus.DISABLED)
        assert flag.is_enabled_for_user(1) is False
        assert flag.is_enabled_for_user(None) is False

    def test_enabled_flag(self):
        """Test enabled flag returns True."""
        flag = FeatureFlag(name="test", status=FlagStatus.ENABLED)
        assert flag.is_enabled_for_user(1) is True
        assert flag.is_enabled_for_user(None) is True

    def test_user_allowlist(self):
        """Test user allowlist bypasses percentage."""
        flag = FeatureFlag(
            name="test",
            status=FlagStatus.PERCENTAGE,
            percentage=0,  # Would normally be False
            allowed_users={42},
        )
        assert flag.is_enabled_for_user(42) is True
        assert flag.is_enabled_for_user(1) is False

    def test_percentage_rollout_deterministic(self):
        """Test percentage rollout is deterministic for same user."""
        flag = FeatureFlag(
            name="test",
            status=FlagStatus.PERCENTAGE,
            percentage=50,
        )
        # Same user should get same result
        result1 = flag.is_enabled_for_user(123)
        result2 = flag.is_enabled_for_user(123)
        assert result1 == result2

    def test_percentage_100(self):
        """Test 100% rollout enables for all."""
        flag = FeatureFlag(
            name="test",
            status=FlagStatus.PERCENTAGE,
            percentage=100,
        )
        # Check multiple users
        for user_id in range(1, 20):
            assert flag.is_enabled_for_user(user_id) is True

    def test_percentage_0(self):
        """Test 0% rollout disables for all."""
        flag = FeatureFlag(
            name="test",
            status=FlagStatus.PERCENTAGE,
            percentage=0,
        )
        for user_id in range(1, 20):
            assert flag.is_enabled_for_user(user_id) is False


class TestFeatureFlagService:
    """Tests for FeatureFlagService."""

    def test_register_and_get(self):
        """Test registering and retrieving flags."""
        service = FeatureFlagService()
        flag = FeatureFlag(name="my_feature", status=FlagStatus.ENABLED)

        service.register(flag)

        retrieved = service.get("my_feature")
        assert retrieved is not None
        assert retrieved.name == "my_feature"

    def test_is_enabled_unknown_flag(self):
        """Test unknown flag returns default."""
        service = FeatureFlagService()

        assert service.is_enabled("unknown", default=False) is False
        assert service.is_enabled("unknown", default=True) is True

    def test_is_enabled_with_user(self):
        """Test is_enabled with user ID."""
        service = FeatureFlagService()
        flag = FeatureFlag(
            name="user_feature",
            status=FlagStatus.PERCENTAGE,
            percentage=100,
        )
        service.register(flag)

        assert service.is_enabled("user_feature", user_id=1) is True

    def test_enable_disable(self):
        """Test enable and disable methods."""
        service = FeatureFlagService()
        flag = FeatureFlag(name="toggle", status=FlagStatus.DISABLED)
        service.register(flag)

        assert service.is_enabled("toggle") is False

        service.enable("toggle")
        assert service.is_enabled("toggle") is True

        service.disable("toggle")
        assert service.is_enabled("toggle") is False

    def test_set_percentage(self):
        """Test setting percentage rollout."""
        service = FeatureFlagService()
        flag = FeatureFlag(name="gradual", status=FlagStatus.DISABLED)
        service.register(flag)

        service.set_percentage("gradual", 50)

        retrieved = service.get("gradual")
        assert retrieved is not None
        assert retrieved.status == FlagStatus.PERCENTAGE
        assert retrieved.percentage == 50

    def test_set_percentage_clamps_values(self):
        """Test percentage is clamped to 0-100."""
        service = FeatureFlagService()
        flag = FeatureFlag(name="clamp", status=FlagStatus.DISABLED)
        service.register(flag)

        service.set_percentage("clamp", 150)
        assert service.get("clamp").percentage == 100  # type: ignore

        service.set_percentage("clamp", -50)
        assert service.get("clamp").percentage == 0  # type: ignore

    def test_list_flags(self):
        """Test listing all flags."""
        service = FeatureFlagService()
        service.register(FeatureFlag(name="flag1"))
        service.register(FeatureFlag(name="flag2"))

        flags = service.list_flags()
        assert len(flags) == 2
        names = {f.name for f in flags}
        assert names == {"flag1", "flag2"}


class TestGlobalFeatureFlags:
    """Test global feature_flags instance."""

    def test_global_instance_exists(self):
        """Test global instance is available."""
        assert feature_flags is not None
        assert isinstance(feature_flags, FeatureFlagService)

    def test_default_flags_registered(self):
        """Test default flags are pre-registered."""
        # These are registered in the module
        assert feature_flags.get("new_dashboard") is not None
        assert feature_flags.get("websocket_v2") is not None
        assert feature_flags.get("push_batching") is not None
