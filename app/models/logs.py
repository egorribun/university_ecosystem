import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    UUID,
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
    resource_type: Mapped[str] = mapped_column(String(64), index=True)
    resource_id: Mapped[str | None] = mapped_column(String(128), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    context: Mapped[dict | list | None] = mapped_column(JSON)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    __table_args__ = ({"postgresql_partition_by": "RANGE (created_at)"},)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
        primary_key=not settings.database_url.startswith("sqlite"),
    )
    signature: Mapped[str | None] = mapped_column(String(512))

    actor = relationship("User", foreign_keys=[actor_user_id])
    subject = relationship("User", foreign_keys=[subject_user_id])
