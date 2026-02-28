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

    name: Mapped[str | None] = mapped_column(String, index=True)
    course: Mapped[int | None] = mapped_column(Integer)
    faculty: Mapped[str | None] = mapped_column(String)

    students = relationship(
        "User", back_populates="group", passive_deletes=True, lazy="selectin"
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
    subject: Mapped[str] = mapped_column(String, nullable=False)
    teacher: Mapped[str | None] = mapped_column(String)
    room: Mapped[str | None] = mapped_column(String)
    weekday: Mapped[str] = mapped_column(String, index=True, nullable=False)
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    end_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    parity: Mapped[str] = mapped_column(String, default="both", index=True)
    lesson_type: Mapped[str | None] = mapped_column(String, default=None)

    __table_args__ = (
        CheckConstraint("end_time > start_time", name="ck_schedule_time_order"),
        Index("ix_schedule_group_start_time", "group_id", "start_time"),
    )

    def __repr__(self) -> str:
        return (
            f"<Schedule(id={self.id}, group_id={self.group_id}, "
            f"subject='{self.subject[:20]}...', starts={self.start_time})>"
        )
