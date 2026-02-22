from enum import StrEnum


class UserRole(StrEnum):
    """Available roles for users within the system."""

    STUDENT = "student"
    TEACHER = "teacher"
    ADMIN = "admin"
    SUPERUSER = "superuser"
    ANONYMOUS = "anonymous"


__all__ = ["UserRole"]
