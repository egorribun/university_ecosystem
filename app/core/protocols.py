from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Protocol, Union, runtime_checkable

if TYPE_CHECKING:
    from app.models.models import User
    from app.schemas.dtos import UserDTO

# TD-07: Standardized UserLike union for service signatures
UserLike = Union["User", "UserDTO", uuid.UUID, str]


@runtime_checkable
class DatabaseSession(Protocol):
    """Sync session protocol (for completeness if needed)."""

    def execute(self, statement: Any, params: Any = None, **kwargs: Any) -> Any: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def add(self, instance: Any) -> None: ...
    def flush(self, objects: Any = None) -> None: ...
    def refresh(
        self, instance: Any, attribute_names: Any = None, **kwargs: Any
    ) -> None: ...


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
    ) -> dict[str, Any]: ...

    async def get_grade_stats(
        self,
        *,
        user_id: uuid.UUID | str,
        period_days: int,
        period_key: str | None = None,
        cache: Any | None = None,
        skip_cache: bool = False,
    ) -> dict[str, Any]: ...

    async def get_participation_stats(
        self,
        *,
        user_id: uuid.UUID | str,
        period_days: int,
        period_key: str | None = None,
        cache: Any | None = None,
        skip_cache: bool = False,
    ) -> dict[str, Any]: ...
