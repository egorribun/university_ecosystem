from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable


@runtime_checkable
class UserLike(Protocol):
    """
    Protocol for objects that behave like a User in the context of email updates.
    This allows both ORM entities and DTOs to be handled by the same logic.
    """

    id: uuid.UUID
    pending_email: str | None
