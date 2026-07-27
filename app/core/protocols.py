from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Protocol, Union, runtime_checkable

if TYPE_CHECKING:
    from app.models import User
    from app.schemas.dtos import UserDTO

# TD-07: Standardized UserLike union for service signatures
UserLike = Union["User", "UserDTO", uuid.UUID, str]


@runtime_checkable
class Identifiable(Protocol):
    """Protocol for objects that have an 'id' attribute."""

    id: Any


def extract_user_id(user: UserLike) -> uuid.UUID:
    """Safely extracts a UUID from any UserLike object for strict type compliance."""
    if isinstance(user, str):
        # LOW-W19: Wrap uuid.UUID() construction so callers receive a clear
        # ValueError with context rather than the bare "badly formed hexadecimal
        # UUID string" message from the uuid module.
        try:
            return uuid.UUID(user)
        except (ValueError, AttributeError) as exc:
            raise ValueError(
                f"extract_user_id: {user!r} is not a valid UUID string"
            ) from exc
    if isinstance(user, uuid.UUID):
        return user
    return user.id


@runtime_checkable
class DatabaseSession(Protocol):
    """Sync session protocol (for completeness if needed)."""

    def execute(
        self, statement: Any, params: Any = None, **kwargs: Any
    ) -> Any: ...  # pragma: no branch
    def commit(self) -> None: ...  # pragma: no branch
    def rollback(self) -> None: ...  # pragma: no branch
    def add(self, instance: Any) -> None: ...  # pragma: no branch
    def flush(self, objects: Any = None) -> None: ...  # pragma: no branch
    def refresh(
        self, instance: Any, attribute_names: Any = None, **kwargs: Any
    ) -> None: ...  # pragma: no branch


if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    AsyncDatabaseSession = AsyncSession
else:
    AsyncDatabaseSession = Any


@runtime_checkable
class UserAnalyticsServiceProtocol(Protocol):
    """Protocol for user analytics service."""

    async def get_attendance_stats(
        self,
        *,
        user_id: uuid.UUID | str,
        period_days: int,
        period_key: str | None = None,
        cache: Any | None = None,
        skip_cache: bool = False,
    ) -> dict[str, Any]: ...  # pragma: no branch

    async def get_grade_stats(
        self,
        *,
        user_id: uuid.UUID | str,
        period_days: int,
        period_key: str | None = None,
        cache: Any | None = None,
        skip_cache: bool = False,
    ) -> dict[str, Any]: ...  # pragma: no branch

    async def get_participation_stats(
        self,
        *,
        user_id: uuid.UUID | str,
        period_days: int,
        period_key: str | None = None,
        cache: Any | None = None,
        skip_cache: bool = False,
    ) -> dict[str, Any]: ...  # pragma: no branch
