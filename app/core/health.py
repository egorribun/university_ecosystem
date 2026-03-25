"""
Database health check utilities.

Provides comprehensive health checks for database connectivity,
pool status, and latency monitoring.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.core.protocols import AsyncDatabaseSession as AsyncSession

logger = get_logger(__name__)


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
        # HIGH-W19: db.get_bind() was removed in SQLAlchemy 2.0; read pool stats
        # directly from the engine obtained via get_read_engine() instead.
        pool_size = None
        pool_checked_out = None
        try:
            from app.core.database import get_read_engine

            engine = get_read_engine()
            pool = getattr(engine, "pool", None)
            if pool is not None:
                pool_size = pool.size()
                pool_checked_out = pool.checkedout()
        except Exception as e:  # RZ-22-01-JUSTIFIED: health probe — pool stats are optional (reviewed TD-27-04)
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
        # HIGH-W19: enforce the caller-supplied timeout instead of ignoring it
        await asyncio.wait_for(
            db.execute(text("SELECT 1")),
            timeout=timeout_ms / 1000,
        )
        return True
    except TimeoutError:
        logger.warning("Database connectivity check timed out after %.0fms", timeout_ms)
        return False
    except Exception as e:  # RZ-22-01-JUSTIFIED: health probe — reports connectivity failure for any error (reviewed TD-27-04)
        logger.warning("Database connectivity check failed: %s", e)
        return False


async def check_spicedb_health(timeout_s: float = 2.0) -> tuple[str, float]:
    """
    Perform a reachability probe for SpiceDB.

    Returns:
        tuple[status, latency_ms]
    """
    from app.core.spicedb import get_async_spicedb_channel

    start = time.perf_counter()
    try:
        channel = await anext(get_async_spicedb_channel())
        if channel is None:
            return "disabled", 0.0

        import grpc

        # Perform a low-level check (e.g. check channel state or hit local health if exists)
        # Authzed SpiceDB usually mirrors gRPC Health Checking Protocol
        # But for absolute perfection, we just check if we can at least ping the channel.
        # We'll use the 'experimental' watch or just check ready state to avoid side effects.
        try:
            await asyncio.wait_for(
                channel.channel_ready(),  # type: ignore[attr-defined]
                timeout=timeout_s,
            )
            status = "ok"
        except (TimeoutError, grpc.RpcError):  # RZ-28-01 + TD-25-06
            status = "error"

        latency_ms = (time.perf_counter() - start) * 1000.0
        return status, latency_ms
    except Exception:  # RZ-22-01-JUSTIFIED: health probe — SpiceDB probe reports error for any failure (reviewed TD-27-04)
        latency_ms = (time.perf_counter() - start) * 1000.0
        return "error", latency_ms


__all__ = [
    "DatabaseHealthResult",
    "HealthStatus",
    "check_database_connectivity",
    "check_database_health",
    "check_spicedb_health",
]
