from enum import Enum


class UserRole(str, Enum):
    """Available roles for users within the system."""

    STUDENT = "student"
    TEACHER = "teacher"
    ADMIN = "admin"


__all__ = ["UserRole"]
