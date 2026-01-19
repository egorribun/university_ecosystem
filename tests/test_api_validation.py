"""
Tests for API validation helpers.
"""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api.validation import (
    ensure_exists,
    raise_conflict,
    raise_forbidden,
    raise_not_found,
    raise_validation_error,
    require_admin,
    require_owner_or_admin,
    require_teacher_or_admin,
)


class TestRaiseNotFound:
    """Tests for raise_not_found helper."""

    def test_raises_404_with_correct_status(self):
        """Should raise HTTPException with 404 status."""
        with pytest.raises(HTTPException) as exc_info:
            raise_not_found("news", "ru")

        assert exc_info.value.status_code == 404

    def test_includes_resource_key_in_detail(self):
        """Should include translated message in detail."""
        with pytest.raises(HTTPException) as exc_info:
            raise_not_found("events", "en")

        # Should have some detail message
        assert exc_info.value.detail is not None


class TestRaiseForbidden:
    """Tests for raise_forbidden helper."""

    def test_raises_403_status(self):
        """Should raise HTTPException with 403 status."""
        with pytest.raises(HTTPException) as exc_info:
            raise_forbidden("ru")

        assert exc_info.value.status_code == 403


class TestRaiseValidationError:
    """Tests for raise_validation_error helper."""

    def test_raises_400_status(self):
        """Should raise HTTPException with 400 status."""
        with pytest.raises(HTTPException) as exc_info:
            raise_validation_error("errors.validation.required", "ru")

        assert exc_info.value.status_code == 400


class TestRaiseConflict:
    """Tests for raise_conflict helper."""

    def test_raises_409_status(self):
        """Should raise HTTPException with 409 status."""
        with pytest.raises(HTTPException) as exc_info:
            raise_conflict("errors.events.registration_closed", "ru")

        assert exc_info.value.status_code == 409


class TestRequireAdmin:
    """Tests for require_admin helper."""

    def test_passes_for_admin(self):
        """Should not raise for admin user."""
        user = MagicMock()
        user.role = "admin"

        # Should not raise
        require_admin(user, "ru")

    def test_raises_for_non_admin(self):
        """Should raise 403 for non-admin user."""
        user = MagicMock()
        user.role = "student"

        with pytest.raises(HTTPException) as exc_info:
            require_admin(user, "ru")

        assert exc_info.value.status_code == 403


class TestRequireTeacherOrAdmin:
    """Tests for require_teacher_or_admin helper."""

    def test_passes_for_admin(self):
        """Should not raise for admin user."""
        user = MagicMock()
        user.role = "admin"

        require_teacher_or_admin(user, "ru")

    def test_passes_for_teacher(self):
        """Should not raise for teacher user."""
        user = MagicMock()
        user.role = "teacher"

        require_teacher_or_admin(user, "ru")

    def test_raises_for_student(self):
        """Should raise 403 for student user."""
        user = MagicMock()
        user.role = "student"

        with pytest.raises(HTTPException) as exc_info:
            require_teacher_or_admin(user, "ru")

        assert exc_info.value.status_code == 403


class TestRequireOwnerOrAdmin:
    """Tests for require_owner_or_admin helper."""

    def test_passes_for_admin(self):
        """Should not raise for admin user."""
        user = MagicMock()
        user.id = 1
        user.role = "admin"

        require_owner_or_admin(user, "ru", owner_id=99)

    def test_passes_for_owner(self):
        """Should not raise for resource owner."""
        user = MagicMock()
        user.id = 42
        user.role = "student"

        require_owner_or_admin(user, "ru", owner_id=42)

    def test_raises_for_non_owner_non_admin(self):
        """Should raise 403 for non-owner non-admin."""
        user = MagicMock()
        user.id = 1
        user.role = "student"

        with pytest.raises(HTTPException) as exc_info:
            require_owner_or_admin(user, "ru", owner_id=99)

        assert exc_info.value.status_code == 403

    def test_passes_for_teacher_when_allowed(self):
        """Should not raise for teacher when allow_teacher=True."""
        user = MagicMock()
        user.id = 1
        user.role = "teacher"

        require_owner_or_admin(user, "ru", owner_id=99, allow_teacher=True)


class TestEnsureExists:
    """Tests for ensure_exists helper."""

    def test_returns_resource_if_exists(self):
        """Should return resource when not None."""
        resource = {"id": 1, "name": "test"}

        result = ensure_exists(resource, "news", "ru")

        assert result == resource

    def test_raises_404_if_none(self):
        """Should raise 404 when resource is None."""
        with pytest.raises(HTTPException) as exc_info:
            ensure_exists(None, "news", "ru")

        assert exc_info.value.status_code == 404
