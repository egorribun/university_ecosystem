import uuid

from sqlalchemy import UUID, ForeignKey
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


class TenantMixin:
    """
    Tenant isolation mixin for multi-tenant entity tables.
    """

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
