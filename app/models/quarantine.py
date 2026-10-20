from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import UUID7PrimaryKeyMixin


class QuarantineStorageScope(Base):
    """Inventory readiness and serialization row for one physical store."""

    __tablename__ = "quarantine_storage_scopes"

    scope_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    inventory_complete: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    inventory_cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )


class QuarantineReservation(UUID7PrimaryKeyMixin, Base):
    """Durable byte charge retained until a managed object is verified absent."""

    __tablename__ = "quarantine_reservations"
    __table_args__ = (
        CheckConstraint("size_bytes >= 0", name="ck_quarantine_reservation_size"),
        CheckConstraint(
            "status IN ('pending', 'stored', 'deleting')",
            name="ck_quarantine_reservation_status",
        ),
        UniqueConstraint(
            "scope_id", "object_key", name="uq_quarantine_reservation_object"
        ),
        Index(
            "ix_quarantine_reservations_expiry",
            "scope_id",
            "status",
            "expires_at",
        ),
    )

    scope_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("quarantine_storage_scopes.scope_id"),
        nullable=False,
    )
    object_key: Mapped[str] = mapped_column(String(2048), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        default="pending",
        server_default=text("'pending'"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
