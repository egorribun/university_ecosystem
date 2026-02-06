import uuid

from sqlalchemy import (
    JSON,
    UUID,
    Column,
    DateTime,
    ForeignKey,
    String,
    func,
)

# Removed postgresql UUID import
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.core.database import Base
from app.models.mixins import UUID7PrimaryKeyMixin


class DataAccessLog(Base, UUID7PrimaryKeyMixin):
    __tablename__ = "data_access_logs"

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    subject_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    resource_type = Column(String(64), nullable=False, index=True)
    resource_id = Column(String(128), nullable=True, index=True)
    action = Column(String(64), nullable=False, index=True)
    context = Column(JSON, nullable=True)
    ip_address = Column(String(64))
    user_agent = Column(String(512))
    __table_args__ = ({"postgresql_partition_by": "RANGE (created_at)"},)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
        primary_key=not settings.database_url.startswith("sqlite"),
    )
    signature = Column(String(512), nullable=True)

    actor = relationship("User", foreign_keys=[actor_user_id])
    subject = relationship("User", foreign_keys=[subject_user_id])
