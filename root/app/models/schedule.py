from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True)
    name = Column(String, index=True)
    course = Column(Integer)
    faculty = Column(String)

    students = relationship("User", back_populates="group", passive_deletes=True)


class Schedule(Base):
    __tablename__ = "schedule"

    id = Column(Integer, primary_key=True)
    group_id = Column(
        Integer, ForeignKey("groups.id", ondelete="CASCADE"), index=True, nullable=False
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
