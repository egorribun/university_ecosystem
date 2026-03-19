import logging
from collections.abc import Callable, Coroutine
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

        # 1. Ensure future partitions exist
        import rust_ext

        for table, _ in PARTITIONED_TABLES:
            for i in range(settings.partition_warmup_months + 1):
                try:
                    info = rust_ext.get_partition_info(table, i)
                    partition_name = info.name
                    start_date_iso = info.start_date
                    end_date_iso = info.end_date

                    logger.debug(
                        f"Ensuring partition {partition_name} exists for table {table}"
                    )

                    # RZ-2 Fix (audit 2026-03-12): Safely handle identifiers and literals
                    preparer = conn.dialect.identifier_preparer
                    safe_partition = preparer.quote(partition_name)
                    safe_table = preparer.quote(table)

                    # Strict validation to prevent State Date Injection
                    from datetime import datetime

                    datetime.fromisoformat(str(start_date_iso).replace("Z", "+00:00"))
                    datetime.fromisoformat(str(end_date_iso).replace("Z", "+00:00"))

                    safe_start = str(start_date_iso).replace("'", "''")
                    safe_end = str(end_date_iso).replace("'", "''")

                    await conn.execute(
                        text(
                            f"""
                        CREATE TABLE IF NOT EXISTS {safe_partition}
                        PARTITION OF {safe_table}
                        FOR VALUES FROM ('{safe_start}')
                        TO ('{safe_end}');
                    """
                        )
                    )
                    await conn.commit()
                except Exception as e:
                    logger.error(f"Failed to create partition: {e}")

        # 2. Prune old partitions
        retention_days = settings.partition_retention_days
        if retention_days > 0:
            for table, _ in PARTITIONED_TABLES:
                result = await conn.execute(
                    text(
                        """
                    SELECT child.relname AS partition_name
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
                    if rust_ext.is_partition_expired(p_name, table, retention_days):
                        try:
                            logger.info(f"Pruning old partition {p_name}")
                            preparer = conn.dialect.identifier_preparer
                            safe_p_name = preparer.quote(p_name)
                            await conn.execute(text(f"DROP TABLE {safe_p_name}"))
                            await conn.commit()
                        except Exception as e:
                            logger.error(f"Failed to prune partition {p_name}: {e}")


async def start_partition_management_scheduler(
    interval_seconds: int = 86400,
) -> Callable[[], Coroutine[Any, Any, None]]:
    """
    Simplistic scheduler for partition management.
    In a real production environment, this might be a Celery Beat task or a cron job.
    """
    from app.core.task_registry import TaskRegistry

    registry = TaskRegistry()

    async def run_periodically() -> None:
        while True:
            try:
                await ensure_partitions_exist()
            except Exception as e:
                logger.error(f"Error in partition management: {e}")
            await asyncio.sleep(interval_seconds)

    registry.create_task(run_periodically(), name="partition_manager")

    async def stop() -> None:
        await registry.shutdown(timeout=10.0)

    return stop
