import uuid
from datetime import datetime

from sqlalchemy import (
    UUID,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)

# Removed postgresql UUID import
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import UUID7PrimaryKeyMixin


class Group(Base, UUID7PrimaryKeyMixin):
    __tablename__ = "groups"

    name: Mapped[str | None] = mapped_column(
        String(512), index=True
    )  # LOW-W19: bounded String
    course: Mapped[int | None] = mapped_column(Integer)
    faculty: Mapped[str | None] = mapped_column(String(256))  # LOW-W19: bounded String

    # PERF-W19-OOM: changed from lazy="selectin" to lazy="noload" — eagerly
    # loading all users per group on list endpoints risks OOM for large groups.
    users = relationship(
        "User", back_populates="group", passive_deletes=True, lazy="noload"
    )

    def __repr__(self) -> str:
        return f"<Group(id={self.id}, name='{self.name}')>"


class Schedule(Base, UUID7PrimaryKeyMixin):
    __tablename__ = "schedule"

    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("groups.id", ondelete="CASCADE"),
        index=True,
    )
    # SEC-BE-01 (audit Wave 10): creator_id tracks ownership for IDOR protection.
    # Nullable so pre-existing rows without an owner can still be managed by admins.
    creator_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    subject: Mapped[str] = mapped_column(
        String(512), nullable=False
    )  # LOW-W19: bounded String
    teacher: Mapped[str | None] = mapped_column(String(512))  # LOW-W19: bounded String
    room: Mapped[str | None] = mapped_column(String(128))  # LOW-W19: bounded String
    weekday: Mapped[str] = mapped_column(
        String(50), index=True, nullable=False
    )  # LOW-W19: bounded String
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    end_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    parity: Mapped[str] = mapped_column(
        String(50), default="both", index=True
    )  # LOW-W19: bounded String
    lesson_type: Mapped[str | None] = mapped_column(
        String(50), default=None
    )  # LOW-W19: bounded String

    __table_args__ = (
        CheckConstraint("end_time > start_time", name="ck_schedule_time_order"),
        # LOW-W19: added CheckConstraint — weekday must be one of the standard English weekday names
        CheckConstraint(
            "weekday IN ('monday','tuesday','wednesday','thursday','friday','saturday','sunday')",
            name="ck_schedule_weekday_valid",
        ),
        # LOW-W19: added CheckConstraint — parity must be one of the three accepted values
        CheckConstraint(
            "parity IN ('odd','even','both')",
            name="ck_schedule_parity_valid",
        ),
        Index("ix_schedule_group_start_time", "group_id", "start_time"),
    )

    def __repr__(self) -> str:
        return (
            f"<Schedule(id={self.id}, group_id={self.group_id}, "
            f"subject='{self.subject[:20]}...', starts={self.start_time})>"
        )
