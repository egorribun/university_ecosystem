from enum import Enum


class UserRole(str, Enum):
    """Available roles for users within the system."""

    STUDENT = "student"
    TEACHER = "teacher"
    ADMIN = "admin"
    SUPERUSER = "superuser"
    ANONYMOUS = "anonymous"


__all__ = ["UserRole"]
