from enum import StrEnum


class UserRole(StrEnum):
    """Available roles for users within the system."""

    STUDENT = "student"
    TEACHER = "teacher"
    ADMIN = "admin"
    SUPERUSER = "superuser"
    # LOW-W19: ANONYMOUS is used only for in-memory permission checks (SpiceDB
    # evaluation for unauthenticated request paths). It is never persisted to the
    # database — no User row will ever carry this role value.
    ANONYMOUS = "anonymous"


__all__ = ["UserRole"]
