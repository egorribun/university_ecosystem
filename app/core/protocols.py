from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any, Protocol, runtime_checkable, TYPE_CHECKING


@runtime_checkable
class UserLike(Protocol):
    """
    Protocol for objects that behave like a User in the context of email updates.
    This allows both ORM entities and DTOs to be handled by the same logic.
    """

    id: uuid.UUID
    pending_email: str | None


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
