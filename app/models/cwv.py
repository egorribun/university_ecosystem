"""Append-only, PII-free field Core Web Vitals evidence."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import UUID7PrimaryKeyMixin


class CwvObservation(Base, UUID7PrimaryKeyMixin):
    """A server-normalised observation; application code exposes no update path."""

    __tablename__ = "cwv_observations"

    metric: Mapped[str] = mapped_column(String(3), nullable=False)
    unit: Mapped[str] = mapped_column(String(5), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    metric_id: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    collector_id: Mapped[str] = mapped_column(String(32), nullable=False)
    navigation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    session_id: Mapped[str] = mapped_column(String(128), nullable=False)
    device_class: Mapped[str] = mapped_column(String(7), nullable=False)
    route_group: Mapped[str] = mapped_column(String(48), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    sampling_bucket: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    release_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    frontend_image_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    deployment_run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    deployment_run_attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    envelope_nonce: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "metric IN ('LCP','INP','CLS')", name="ck_cwv_observation_metric"
        ),
        CheckConstraint(
            "device_class IN ('mobile','desktop')", name="ck_cwv_device_class"
        ),
        CheckConstraint("value >= 0", name="ck_cwv_value_nonnegative"),
        UniqueConstraint("navigation_id", "metric", name="uq_cwv_navigation_metric"),
        UniqueConstraint("envelope_nonce", "metric", name="uq_cwv_nonce_metric"),
        UniqueConstraint(
            "release_sha",
            "deployment_run_id",
            "deployment_run_attempt",
            "collector_id",
            "route_group",
            "metric",
            "sampling_bucket",
            name="uq_cwv_manual_sample_bucket",
        ),
        Index(
            "ix_cwv_release_deployment_observed",
            "release_sha",
            "frontend_image_digest",
            "deployment_run_id",
            "deployment_run_attempt",
            "observed_at",
        ),
        Index("ix_cwv_created_at", "created_at"),
    )
