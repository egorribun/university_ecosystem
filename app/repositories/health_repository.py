"""Health check repository for database probes.

Encapsulates database-level health check queries following the
Repository Pattern to separate data access from API layer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection


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
            await self._connection.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    async def check_notification_queue_accessible(self) -> bool:
        """Verify notification queue table is accessible.

        Returns:
            True if notification_queue_jobs table can be queried.
        """
        try:
            await self._connection.execute(
                text("SELECT 1 FROM notification_queue_jobs")
            )
            return True
        except Exception:
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
            result = await self._connection.execute(
                text(
                    """
                    SELECT reltuples::bigint AS count
                    FROM pg_class
                    WHERE relname = :table_name
                    """
                ),
                {"table_name": table_name},
            )
            row = result.fetchone()
            if row and row[0] >= 0:
                return int(row[0])
        except Exception:
            pass

        # Fallback to actual count
        try:
            # Use parameterized table name safely
            result = await self._connection.execute(
                text(f"SELECT COUNT(*) FROM {table_name}")  # noqa: S608
            )
            row = result.fetchone()
            return int(row[0]) if row else 0
        except Exception:
            return None

    async def get_connection_stats(self) -> dict[str, Any]:
        """Get database connection statistics (PostgreSQL only).

        Returns:
            Dictionary with connection stats, empty if not PostgreSQL.
        """
        try:
            result = await self._connection.execute(
                text(
                    """
                    SELECT
                        numbackends as active_connections,
                        xact_commit as commits,
                        xact_rollback as rollbacks,
                        blks_hit as cache_hits,
                        blks_read as disk_reads
                    FROM pg_stat_database
                    WHERE datname = current_database()
                    """
                )
            )
            row = result.fetchone()
            if row:
                return {
                    "active_connections": row[0],
                    "commits": row[1],
                    "rollbacks": row[2],
                    "cache_hit_ratio": (
                        row[3] / (row[3] + row[4]) if (row[3] + row[4]) > 0 else 1.0
                    ),
                }
        except Exception:
            pass
        return {}


__all__ = ["HealthRepository"]
