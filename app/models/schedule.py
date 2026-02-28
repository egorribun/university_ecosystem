import uuid

from sqlalchemy import (
    UUID,
    CheckConstraint,
    Column,
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

    name = Column(String, index=True)
    course = Column(Integer)
    faculty = Column(String)

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
    subject = Column(String, nullable=False)
    teacher = Column(String)
    room = Column(String)
    weekday = Column(String, index=True, nullable=False)
    start_time = Column(DateTime(timezone=True), index=True, nullable=False)
    end_time = Column(DateTime(timezone=True), index=True, nullable=False)
    parity = Column(String, default="both", index=True)
    lesson_type = Column(String, default=None)

    __table_args__ = (
        CheckConstraint("end_time > start_time", name="ck_schedule_time_order"),
        Index("ix_schedule_group_start_time", "group_id", "start_time"),
    )

    def __repr__(self) -> str:
        return (
            f"<Schedule(id={self.id}, group_id={self.group_id}, "
            f"subject='{self.subject[:20]}...', starts={self.start_time})>"
        )
