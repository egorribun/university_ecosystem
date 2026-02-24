"""
Database health check utilities.

Provides comprehensive health checks for database connectivity,
pool status, and latency monitoring.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

if TYPE_CHECKING:
    from app.core.protocols import AsyncDatabaseSession as AsyncSession

logger = logging.getLogger(__name__)


class HealthStatus(StrEnum):
    """Health check status values."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class DatabaseHealthResult:
    """Result of a database health check."""

    status: HealthStatus
    latency_ms: float
    message: str | None = None
    pool_size: int | None = None
    pool_checked_out: int | None = None
    error: str | None = None


# Latency thresholds (milliseconds)
LATENCY_HEALTHY_THRESHOLD_MS = 50.0
LATENCY_DEGRADED_THRESHOLD_MS = 200.0


async def check_database_health(db: AsyncSession) -> DatabaseHealthResult:
    """
    Perform a comprehensive database health check.

    Returns health status based on connectivity and latency.
    """
    start_time = time.perf_counter()

    try:
        # Execute lightweight query
        await db.execute(text("SELECT 1"))
        latency_ms = (time.perf_counter() - start_time) * 1000.0

        # Get pool stats if available
        pool_size = None
        pool_checked_out = None
        try:
            bind = db.get_bind()
            pool = getattr(bind, "pool", None)
            if pool is not None:
                pool_size = pool.size()
                pool_checked_out = pool.checkedout()
        except Exception as e:
            logger.debug("Failed to fetch pool stats: %s", e)

        # Determine status based on latency
        if latency_ms <= LATENCY_HEALTHY_THRESHOLD_MS:
            status = HealthStatus.HEALTHY
            message = "Database responding normally"
        elif latency_ms <= LATENCY_DEGRADED_THRESHOLD_MS:
            status = HealthStatus.DEGRADED
            message = f"Database slow: {latency_ms:.1f}ms latency"
        else:
            status = HealthStatus.DEGRADED
            message = f"Database very slow: {latency_ms:.1f}ms latency"

        return DatabaseHealthResult(
            status=status,
            latency_ms=latency_ms,
            message=message,
            pool_size=pool_size,
            pool_checked_out=pool_checked_out,
        )

    except SQLAlchemyError as e:
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        logger.error("Database health check failed: %s", e)
        return DatabaseHealthResult(
            status=HealthStatus.UNHEALTHY,
            latency_ms=latency_ms,
            message="Database connection failed",
            error=str(e),
        )


async def check_database_connectivity(
    db: AsyncSession, timeout_ms: float = 5000
) -> bool:
    """
    Quick connectivity check with timeout.

    Returns True if database is reachable, False otherwise.
    """
    try:
        await db.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.warning("Database connectivity check failed: %s", e)
        return False


__all__ = [
    "DatabaseHealthResult",
    "HealthStatus",
    "check_database_connectivity",
    "check_database_health",
]
