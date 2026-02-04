import uuid

from sqlalchemy import UUID, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.utils.uuid_v7 import generate_uuid7


class UUID7PrimaryKeyMixin:
    """
    Final Phase 3 Mixin: UUID v7 is the PRIMARY KEY.
    Used for both new and migrated tables.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid7,
        doc="Time-ordered UUID v7 primary key",
    )


class ShadowUUIDMixin:
    """
    Phase 1/2 Mixin: Keeps binary/int id as PK, adds shadow uuid_id.
    """

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        unique=True,
        index=True,
        default=generate_uuid7,
        doc="Shadow UUID for Phase 1/2 migration",
    )


class UserFK:
    """
    Final Phase 3: References the UUID primary key on users.
    """

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )


class ShadowUserFK:
    """
    Phase 1/2: References legacy INT user_id, but keeps shadow_user_uuid.
    """

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_uuid: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        index=True,
        doc="Shadow FK for Phase 1/2 migration",
    )
