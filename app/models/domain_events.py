from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import UUID7PrimaryKeyMixin


class StoredEvent(Base, UUID7PrimaryKeyMixin):
    """
    Persistent store for domain events.
    Captures state changes for auditability and asynchronous processing
    (CQRS/Projections).
    """

    __tablename__ = "stored_events"

    event_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, index=True
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    error_count: Mapped[int] = mapped_column(Integer, default=0, index=True)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<StoredEvent(type={self.event_type}, "
            f"aggregate={self.aggregate_type}:{self.aggregate_id})>"
        )
