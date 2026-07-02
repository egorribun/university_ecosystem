"""Health check repository for database probes.

Encapsulates database-level health check queries following the
Repository Pattern to separate data access from API layer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, cast, column, func, select
from sqlalchemy.sql import table

from app.core.logging import get_logger
from app.schemas.dtos.analytics import HealthStatsDTO

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection

_logger = get_logger(__name__)


class HealthRepository:
    """Repository for health-related database operations."""

    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def check_connectivity(self) -> bool:
        """Verify basic database connectivity.

        Returns:
            True if database responds to simple query.
        """
        try:
            await self._connection.execute(select(1))
            return True
        except Exception:  # RZ-22-01-JUSTIFIED: health probe — connectivity check returns False on any error (reviewed TD-27-04)
            return False

    async def check_notification_queue_accessible(self) -> bool:
        """Verify notification queue table is accessible.

        Returns:
            True if notification_queue_jobs table can be queried.
        """
        try:
            from sqlalchemy.sql import table

            await self._connection.execute(
                select(1).select_from(table("notification_queue_jobs")).limit(1)
            )
            return True
        except Exception:  # RZ-22-01-JUSTIFIED: health probe — notification queue check returns False on any error (reviewed TD-27-04)
            return False

    async def get_table_count(self, table_name: str) -> int | None:
        """Get approximate row count for a table.

        Uses pg_class for PostgreSQL (faster), falls back to COUNT(*).

        Args:
            table_name: Name of the table to count.

        Returns:
            Approximate row count, or None on error.
        """
        try:
            # Try fast approximate count first (PostgreSQL)
            pg_class = table(
                "pg_class",
                column("reltuples"),
                column("relname"),
            )
            result = await self._connection.execute(
                select(cast(pg_class.c.reltuples, BigInteger).label("count")).where(
                    pg_class.c.relname == table_name
                )
            )
            row = result.fetchone()
            if row is not None and row[0] >= 0:
                return int(row[0])
        except Exception as exc:  # RZ-22-01-JUSTIFIED: health probe — fast count falls back to slower COUNT(*) (reviewed TD-27-04)
            _logger.debug("Fast table count check failed: %s", exc)  # nosec B110
            pass

        # Fallback to actual count
        try:
            # Use table/func for safe count expression
            query = select(func.count()).select_from(table(table_name))
            result = await self._connection.execute(query)
            row = result.fetchone()
            return int(row[0]) if row is not None else 0
        except Exception:  # RZ-22-01-JUSTIFIED: health probe — table count returns None on any error (reviewed TD-27-04)
            return None

    async def get_connection_stats(self) -> HealthStatsDTO:
        """Get database connection statistics (PostgreSQL only)."""
        try:
            pg_stat_database = table(
                "pg_stat_database",
                column("numbackends"),
                column("xact_commit"),
                column("xact_rollback"),
                column("blks_hit"),
                column("blks_read"),
                column("datname"),
            )
            result = await self._connection.execute(
                select(
                    pg_stat_database.c.numbackends.label("active_connections"),
                    pg_stat_database.c.xact_commit.label("commits"),
                    pg_stat_database.c.xact_rollback.label("rollbacks"),
                    pg_stat_database.c.blks_hit.label("cache_hits"),
                    pg_stat_database.c.blks_read.label("disk_reads"),
                ).where(pg_stat_database.c.datname == func.current_database())
            )
            row = result.fetchone()
            if row is not None:
                return HealthStatsDTO(
                    active_connections=row[0],
                    commits=row[1],
                    rollbacks=row[2],
                    cache_hit_ratio=(
                        row[3] / (row[3] + row[4]) if (row[3] + row[4]) > 0 else 1.0
                    ),
                )
        except Exception as exc:  # RZ-22-01-JUSTIFIED: health probe — connection stats returns defaults on error (reviewed TD-27-04)
            _logger.debug("Database connection stats probe failed: %s", exc)  # nosec B110
            pass
        return HealthStatsDTO(
            active_connections=0, commits=0, rollbacks=0, cache_hit_ratio=1.0
        )


__all__ = ["HealthRepository"]
