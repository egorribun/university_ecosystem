import asyncio
import re
from collections.abc import Callable, Coroutine
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import OperationalError as SAOperationalError
from sqlalchemy.exc import ProgrammingError as SAProgrammingError

from app.core.database import engine
from app.core.logging import get_logger

logger = get_logger(__name__)

# RZ-20-05 (audit 2026-03-24): Whitelist for partition/table identifiers.
# Prevents DDL injection through crafted names returned by rust_ext.
_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")

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

        # 1a. Ensure DEFAULT partition exists for notification tables.
        # Migration 148642dd1207 creates these tables with postgresql_partition_by
        # but no DEFAULT partition; without one, rows whose date falls outside
        # `partition_warmup_months` (e.g. older test data) fail with
        # "no partition of relation X found for row". Self-heal here so the fix
        # also covers production DBs that already ran the buggy migration.
        # Note: data_access_logs intentionally has no DEFAULT partition
        # (migration 202603280001 explicitly drops it as an "autogenerate artefact").
        _DEFAULT_PARTITION_TABLES = ("notifications", "notification_deliveries")
        for table in _DEFAULT_PARTITION_TABLES:
            if not _SAFE_IDENTIFIER_RE.match(table):
                logger.error(
                    "Table name %r failed identifier validation — skipping default partition",
                    table,
                )
                continue
            preparer = conn.dialect.identifier_preparer
            safe_table = preparer.quote(table)
            safe_default = preparer.quote(f"{table}_default")
            try:
                await conn.exec_driver_sql(
                    f"CREATE TABLE IF NOT EXISTS {safe_default} "
                    f"PARTITION OF {safe_table} DEFAULT"
                )
                await conn.commit()
            except (
                OSError,
                ConnectionError,
                SAOperationalError,
                SAProgrammingError,
            ) as e:
                logger.error("Failed to ensure default partition for %s: %s", table, e)

        # 1b. Ensure future partitions exist
        import rust_ext

        for table, _ in PARTITIONED_TABLES:
            for i in range(settings.partition_warmup_months + 1):
                try:
                    info = rust_ext.get_partition_info(table, i)
                    partition_name = info.name
                    start_date_iso = info.start_date
                    end_date_iso = info.end_date

                    logger.debug(  # LOW-W19: lazy logging
                        "Ensuring partition %s exists for table %s",
                        partition_name,
                        table,
                    )

                    # RZ-20-05 (audit 2026-03-24): Defence-in-depth for DDL identifiers.
                    # 1. Whitelist-validate names from rust_ext before quoting.
                    # 2. Use identifier_preparer.quote() for dialect-safe quoting.
                    # 3. Use text() bind parameters for date literals (CWE-89).
                    if not _SAFE_IDENTIFIER_RE.match(partition_name):
                        logger.error(
                            "Partition name %r failed identifier validation — skipping",
                            partition_name,
                        )
                        continue
                    if not _SAFE_IDENTIFIER_RE.match(table):
                        logger.error(
                            "Table name %r failed identifier validation — skipping",
                            table,
                        )
                        continue

                    preparer = conn.dialect.identifier_preparer
                    safe_partition = preparer.quote(partition_name)
                    safe_table = preparer.quote(table)

                    # Strict ISO-8601 validation to prevent date injection.
                    from datetime import datetime

                    datetime.fromisoformat(str(start_date_iso).replace("Z", "+00:00"))
                    datetime.fromisoformat(str(end_date_iso).replace("Z", "+00:00"))

                    # RZ-20-05: Date literals are pre-validated via
                    # datetime.fromisoformat() above — safe to interpolate.
                    # DDL statements (CREATE TABLE) do not support bind
                    # parameters in PostgreSQL; asyncpg rejects them with
                    # "the server expects 0 arguments".
                    safe_start = str(start_date_iso).replace("'", "''")
                    safe_end = str(end_date_iso).replace("'", "''")
                    await conn.exec_driver_sql(
                        f"CREATE TABLE IF NOT EXISTS {safe_partition} "
                        f"PARTITION OF {safe_table} "
                        f"FOR VALUES FROM ('{safe_start}') TO ('{safe_end}')"
                    )
                    await conn.commit()
                except (
                    OSError,
                    ConnectionError,
                    SAOperationalError,
                    SAProgrammingError,
                    RuntimeError,
                    ImportError,
                ) as e:
                    # RZ-20-04 + RZ-33-03: Broadened — DDL errors, rust_ext import,
                    # and asyncpg interface errors.
                    logger.error(
                        "Failed to create partition: %s", e
                    )  # LOW-W19: lazy logging

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
                        # RZ-20-05: Validate partition name from pg_class before DDL.
                        if not _SAFE_IDENTIFIER_RE.match(p_name):
                            logger.error(
                                "Partition name %r from pg_class failed validation — "
                                "skipping DROP to prevent DDL injection",
                                p_name,
                            )
                            continue
                        try:
                            logger.info(
                                "Pruning old partition %s", p_name
                            )  # LOW-W19: lazy logging
                            preparer = conn.dialect.identifier_preparer
                            safe_p_name = preparer.quote(p_name)
                            await conn.exec_driver_sql(f"DROP TABLE {safe_p_name}")
                            await conn.commit()
                        except (
                            OSError,
                            ConnectionError,
                            SAOperationalError,
                            SAProgrammingError,
                        ) as e:
                            # RZ-20-04 + RZ-33-03: Broadened — DDL errors include SA exceptions.
                            logger.error(
                                "Failed to prune partition %s: %s", p_name, e
                            )  # LOW-W19: lazy logging


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
            except (OSError, ConnectionError) as e:
                # RZ-20-04: Narrowed — partition scheduler catches infra errors only.
                logger.error(
                    "Error in partition management: %s", e
                )  # LOW-W19: lazy logging
            await asyncio.sleep(interval_seconds)

    registry.create_task(run_periodically(), name="partition_manager")

    async def stop() -> None:
        await registry.shutdown(timeout=10.0)

    return stop
