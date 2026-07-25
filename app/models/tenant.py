"""Tenant model for multi-tenant federation."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import UUID7PrimaryKeyMixin


class Tenant(Base, UUID7PrimaryKeyMixin):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(256), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    domain: Mapped[str | None] = mapped_column(
        String(256), unique=True, index=True, nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, server_default="true", nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
