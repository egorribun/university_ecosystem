import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.core.database import engine

logger = logging.getLogger(__name__)

PARTITIONED_TABLES = [
    ("notifications", "created_at"),
    ("notification_deliveries", "attempted_at"),
    ("data_access_logs", "created_at"),
]


async def ensure_partitions_exist(months_ahead: int = 1):
    """
    Ensures that PostgreSQL partitions exist for the current and next few months.
    Only runs if the database is PostgreSQL.
    """
    async with engine.connect() as conn:
        if conn.dialect.name != "postgresql":
            logger.debug("Partition management skipped: not a PostgreSQL database")
            return

        now = datetime.now(UTC)
        for table, column in PARTITIONED_TABLES:
            for i in range(months_ahead + 1):
                target_date = now + timedelta(days=31 * i)
                year = target_date.year
                month = target_date.month

                # Start of month
                start_date = datetime(year, month, 1, tzinfo=UTC)
                # Start of next month
                if month == 12:
                    next_month_start = datetime(year + 1, 1, 1, tzinfo=UTC)
                else:
                    next_month_start = datetime(year, month + 1, 1, tzinfo=UTC)

                partition_name = f"{table}_y{year}m{month:02d}"

                logger.info(
                    f"Ensuring partition {partition_name} exists for table {table}"
                )

                try:
                    await conn.execute(
                        text(
                            f"""
                        CREATE TABLE IF NOT EXISTS {partition_name}
                        PARTITION OF {table}
                        FOR VALUES FROM ('{start_date.isoformat()}') TO ('{next_month_start.isoformat()}');
                    """
                        )
                    )
                    await conn.commit()
                except Exception as e:
                    logger.error(f"Failed to create partition {partition_name}: {e}")
                    # Don't rethrow, try other partitions


async def start_partition_management_scheduler(interval_seconds: int = 86400):
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

    async def stop():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    return stop
