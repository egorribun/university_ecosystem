import uuid as _uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, CheckConstraint, DateTime, Integer, String
from sqlalchemy import UUID as SAUUID
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

    # Cryptographic HMAC Hash-Chaining fields (R3 & R4)
    prev_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Outbox Pattern fields (RZ-F-11)
    subject: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )
    trace_context: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    error_count: Mapped[int] = mapped_column(Integer, default=0, index=True)
    last_error: Mapped[str | None] = mapped_column(
        String(4096), nullable=True
    )  # MED-W19: unbounded String → String(4096)

    # DEBT-01: Per-aggregate causal ordering fields (migration 202603140003).
    # aggregate_id_uuid stores the UUID form of aggregate_id (when the ID is a
    # UUID) so the outbox worker can use DISTINCT ON (aggregate_id_uuid) ORDER BY
    # aggregate_id_uuid, sequence_number to guarantee per-aggregate ordering
    # across multiple workers without losing parallelism between aggregates.
    # Both columns are nullable so existing rows are unaffected.
    aggregate_id_uuid: Mapped[_uuid.UUID | None] = mapped_column(
        SAUUID(as_uuid=True), nullable=True, index=True, name="aggregate_id_uuid"
    )
    sequence_number: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    __table_args__ = (
        # LOW-W19: added CheckConstraint — status must be one of the three outbox lifecycle values
        CheckConstraint(
            "status IN ('pending','processed','failed')",
            name="ck_stored_events_status_valid",
        ),
    )

    # PERF-03: Partial covering indexes (cannot be expressed in SQLAlchemy
    # mapped_column / Index DSL; created via raw SQL in migration 202603140002):
    #   ix_stored_events_pending_created          (created_at, id) WHERE processed_at IS NULL
    #   ix_stored_events_pending_aggregate_created (aggregate_id, created_at, id) WHERE processed_at IS NULL
    #
    # DEBT-01: Composite partial index for per-aggregate causal ordering
    # (migration 202603140003):
    #   ix_stored_events_aggregate_uuid (aggregate_id_uuid, sequence_number) WHERE processed_at IS NULL AND aggregate_id_uuid IS NOT NULL

    def __repr__(self) -> str:
        return (
            f"<StoredEvent(type={self.event_type}, "
            f"aggregate={self.aggregate_type}:{self.aggregate_id})>"
        )
