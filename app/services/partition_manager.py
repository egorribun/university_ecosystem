import contextlib
import logging
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text

from app.core.database import engine

logger = logging.getLogger(__name__)

PARTITIONED_TABLES = [
    ("notifications", "created_at"),
    ("notification_deliveries", "attempted_at"),
    ("data_access_logs", "created_at"),
]


async def ensure_partitions_exist() -> None:
    """
    Ensures that PostgreSQL partitions exist for the current and next few months,
    and prunes old partitions based on retention settings.
    """
    from app.core.config import settings

    async with engine.connect() as conn:
        if conn.dialect.name != "postgresql":
            logger.debug("Partition management skipped: not a PostgreSQL database")
            return

        now = datetime.now(UTC)

        # 1. Ensure future partitions exist
        for table, column in PARTITIONED_TABLES:
            for i in range(settings.partition_warmup_months + 1):
                # Calculate month and year for the partition
                month_offset = i
                target_month = now.month + month_offset
                target_year = now.year + (target_month - 1) // 12
                target_month = (target_month - 1) % 12 + 1

                # Start of month
                start_date = datetime(target_year, target_month, 1, tzinfo=UTC)
                # Start of next month
                if target_month == 12:
                    next_month_start = datetime(target_year + 1, 1, 1, tzinfo=UTC)
                else:
                    next_month_start = datetime(
                        target_year, target_month + 1, 1, tzinfo=UTC
                    )

                partition_name = f"{table}_y{target_year}m{target_month:02d}"

                logger.debug(
                    f"Ensuring partition {partition_name} exists for table {table}"
                )

                try:
                    # RZ-2 Fix (audit 2026-03-04): Safely handle identifiers to strictly prevent SQLi
                    safe_partition = str(partition_name).replace('"', '""')
                    safe_table = str(table).replace('"', '""')

                    await conn.execute(
                        text(
                            f"""
                        CREATE TABLE IF NOT EXISTS "{safe_partition}"
                        PARTITION OF "{safe_table}"
                        FOR VALUES FROM ('{start_date.isoformat()}')
                        TO ('{next_month_start.isoformat()}');
                    """
                        )
                    )
                    await conn.commit()
                except Exception as e:
                    logger.error(f"Failed to create partition {partition_name}: {e}")
                    # Don't rethrow, try other partitions

        # 2. Prune old partitions
        retention_days = settings.partition_retention_days
        if retention_days > 0:
            cutoff_date = now - timedelta(days=retention_days)
            for table, _ in PARTITIONED_TABLES:
                # Find partitions for this table
                result = await conn.execute(
                    text(
                        """
                    SELECT
                        child.relname AS partition_name
                    FROM pg_inherits
                        JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
                        JOIN pg_class child ON pg_inherits.inhrelid = child.oid
                    WHERE parent.relname = :table_name
                """
                    ),
                    {"table_name": table},
                )
                partitions = result.scalars().all()

                for p_name in partitions:
                    # Expecting format table_yYYYYmMM
                    if not p_name.startswith(f"{table}_y"):
                        continue

                    try:
                        # Extract year and month from name
                        parts = p_name.split("_y")[1].split("m")
                        p_year = int(parts[0])
                        p_month = int(parts[1])

                        # Partition covers [p_year, p_month, 1] to [next_month, 1]
                        # We prune if the END of the partition is before cutoff
                        if p_month == 12:
                            p_end_date = datetime(p_year + 1, 1, 1, tzinfo=UTC)
                        else:
                            p_end_date = datetime(p_year, p_month + 1, 1, tzinfo=UTC)

                        if p_end_date < cutoff_date:
                            logger.info(f"Pruning old partition {p_name}")

                            # RZ-2 Fix (audit 2026-03-04): Prevent SQLi in DROP TABLE
                            safe_p_name = str(p_name).replace('"', '""')
                            await conn.execute(text(f'DROP TABLE "{safe_p_name}"'))
                            await conn.commit()

                    except (ValueError, IndexError):
                        continue
                    except Exception as e:
                        logger.error(f"Failed to prune partition {p_name}: {e}")


async def start_partition_management_scheduler(
    interval_seconds: int = 86400,
) -> Callable[[], Coroutine[Any, Any, None]]:
    """
    Simplistic scheduler for partition management.
    In a real production environment, this might be a Celery Beat task or a cron job.
    """
    import asyncio

    async def run_periodically():
        while True:
            try:
                await ensure_partitions_exist()
            except Exception as e:
                logger.error(f"Error in partition management: {e}")
            await asyncio.sleep(interval_seconds)

    task = asyncio.create_task(run_periodically())

    async def stop() -> None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    return stop
