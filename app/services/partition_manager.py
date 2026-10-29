import asyncio
import re
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.exc import OperationalError as SAOperationalError
from sqlalchemy.exc import ProgrammingError as SAProgrammingError
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import engine
from app.core.logging import get_logger

logger = get_logger(__name__)

# RZ-20-05 (audit 2026-03-24): Whitelist for partition/table identifiers.
# Prevents DDL injection through crafted names returned by rust_ext.
_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
_RANGE_PARTITION_BOUND_RE = re.compile(
    r"^FOR VALUES FROM \('([^']+)'\) TO \('([^']+)'\)$"
)

PARTITIONED_TABLES = [
    ("notifications", "created_at"),
    ("notification_deliveries", "attempted_at"),
    ("data_access_logs", "created_at"),
]


def _normalise_partition_timestamp(value: object) -> datetime | None:
    """Return a comparable UTC timestamp from PostgreSQL/Rust text values."""

    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _partition_bound_matches(
    bound: object,
    start_date_iso: object,
    end_date_iso: object,
) -> bool:
    """Whether one catalog RANGE bound covers exactly the requested month."""

    if not isinstance(bound, str):
        return False
    match = _RANGE_PARTITION_BOUND_RE.fullmatch(bound.strip())
    if match is None:
        return False

    existing_start = _normalise_partition_timestamp(match.group(1))
    existing_end = _normalise_partition_timestamp(match.group(2))
    requested_start = _normalise_partition_timestamp(start_date_iso)
    requested_end = _normalise_partition_timestamp(end_date_iso)
    return (
        existing_start is not None
        and existing_end is not None
        and requested_start is not None
        and requested_end is not None
        and existing_start == requested_start
        and existing_end == requested_end
    )


async def _range_partition_exists(
    conn: Any,
    table: str,
    start_date_iso: object,
    end_date_iso: object,
) -> bool:
    """Detect a monthly partition by bounds instead of its implementation name.

    Historical migrations use ``notifications_YYYY_MM`` while the runtime
    partition worker uses ``notifications_yYYYYmMM``. PostgreSQL rejects a
    second name for the same range, so catalog bounds—not a generated name—are
    the idempotency contract.
    """

    result = await conn.execute(
        text(
            """
            SELECT pg_get_expr(child.relpartbound, child.oid)
            FROM pg_inherits
            JOIN pg_class AS child ON pg_inherits.inhrelid = child.oid
            JOIN pg_class AS parent ON pg_inherits.inhparent = parent.oid
            JOIN pg_namespace AS parent_ns ON parent.relnamespace = parent_ns.oid
            WHERE parent.relname = :table_name
              AND parent_ns.nspname = current_schema()
              AND child.relispartition
            """
        ),
        {"table_name": table},
    )
    return any(
        _partition_bound_matches(bound, start_date_iso, end_date_iso)
        for bound in result.scalars().all()
    )


async def _lock_partition_ddl(conn: Any, table: str) -> None:
    """Serialize range creation per parent table across application nodes."""

    await conn.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:table_name))"),
        {"table_name": table},
    )


@dataclass(frozen=True, slots=True)
class _PartitionCandidate:
    parent_oid: int
    parent_schema: str
    child_oid: int
    child_schema: str
    partition_name: str
    partition_bound: str


@asynccontextmanager
async def _bounded_partition_statement(conn: Any) -> AsyncIterator[None]:
    """Bound catalog/DDL waits without changing the caller's timeout or transaction."""
    async with conn.begin_nested():
        timeout_result = await conn.execute(
            text(
                "SELECT setting FROM pg_catalog.pg_settings "
                "WHERE name = 'statement_timeout'"
            )
        )
        previous_timeout_ms = int(timeout_result.scalar_one())
        bounded_timeout_ms = min(previous_timeout_ms or 5000, 5000)
        await conn.execute(
            text("SELECT pg_catalog.set_config('statement_timeout', :timeout, true)"),
            {"timeout": f"{bounded_timeout_ms}ms"},
        )
        yield
        await conn.execute(
            text("SELECT pg_catalog.set_config('statement_timeout', :timeout, true)"),
            {"timeout": f"{previous_timeout_ms}ms"},
        )


async def _list_prunable_partitions(
    conn: Any,
    table: str,
    partition_key: str,
    *,
    candidate: _PartitionCandidate | None = None,
) -> list[_PartitionCandidate]:
    """List leaf partitions attached to the expected parent in this schema."""
    parameters: dict[str, Any] = {
        "table_name": table,
        "partition_key": partition_key,
        "parent_oid": candidate.parent_oid if candidate is not None else None,
        "child_oid": candidate.child_oid if candidate is not None else None,
    }
    async with _bounded_partition_statement(conn):
        result = await conn.execute(
            text(
                """
            SELECT parent.oid AS parent_oid, parent_ns.nspname AS parent_schema,
                   child.oid AS child_oid, child_ns.nspname AS child_schema,
                   child.relname AS partition_name,
                   pg_catalog.pg_get_expr(child.relpartbound, child.oid) AS partition_bound
            FROM pg_catalog.pg_inherits AS inheritance
            JOIN pg_catalog.pg_class AS parent ON parent.oid = inheritance.inhparent
            JOIN pg_catalog.pg_namespace AS parent_ns ON parent_ns.oid = parent.relnamespace
            JOIN pg_catalog.pg_class AS child ON child.oid = inheritance.inhrelid
            JOIN pg_catalog.pg_namespace AS child_ns ON child_ns.oid = child.relnamespace
            JOIN pg_catalog.pg_partitioned_table AS partitioning ON partitioning.partrelid = parent.oid
            JOIN pg_catalog.pg_attribute AS partition_column
              ON partition_column.attrelid = parent.oid
             AND partition_column.attnum = partitioning.partattrs[0]
            WHERE parent.relname = :table_name
              AND parent_ns.nspname = pg_catalog.current_schema()
              AND child_ns.nspname = parent_ns.nspname
              AND parent.relkind = 'p' AND child.relkind = 'r' AND child.relispartition
              AND partitioning.partstrat = 'r' AND partitioning.partnatts = 1
              AND partition_column.attname = :partition_key
              AND partition_column.atttypid = CAST('pg_catalog.timestamptz' AS pg_catalog.regtype)
              AND (CAST(:parent_oid AS pg_catalog.oid) IS NULL OR parent.oid = CAST(:parent_oid AS pg_catalog.oid))
              AND (CAST(:child_oid AS pg_catalog.oid) IS NULL OR child.oid = CAST(:child_oid AS pg_catalog.oid))
                """
            ),
            parameters,
        )
        rows = result.all()
    return [
        _PartitionCandidate(
            parent_oid=row.parent_oid,
            parent_schema=row.parent_schema,
            child_oid=row.child_oid,
            child_schema=row.child_schema,
            partition_name=row.partition_name,
            partition_bound=row.partition_bound,
        )
        for row in rows
    ]


def _expired_partition_has_matching_bounds(
    table: str, candidate: _PartitionCandidate, retention_days: int
) -> bool:
    """Refuse to infer data retention from a name that disagrees with its bounds."""
    match = re.fullmatch(
        rf"{re.escape(table)}_(?:y([0-9]{{4}})m([0-9]{{2}})|([0-9]{{4}})_([0-9]{{2}}))",
        candidate.partition_name,
    )
    if match is None or retention_days <= 0:
        return False
    # Each alternative contains both year and month; the successful match
    # guarantees exactly one pair of capturing groups is populated.
    year = int(cast(str, match.group(1) or match.group(3)))
    month = int(cast(str, match.group(2) or match.group(4)))
    try:
        start = datetime(year, month, 1, tzinfo=UTC)
        end = datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=UTC)
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    except (OverflowError, ValueError):
        return False
    return end < cutoff and _partition_bound_matches(
        candidate.partition_bound, start.isoformat(), end.isoformat()
    )


async def _prune_expired_partition(
    conn: Any,
    table: str,
    partition_key: str,
    retention_days: int,
    rust: Any,
    candidate: _PartitionCandidate,
) -> bool:
    """Drop only a still-attached, expired monthly leaf; caller owns the transaction."""
    if not _expired_partition_has_matching_bounds(table, candidate, retention_days):
        return False
    if not rust.is_partition_expired(candidate.partition_name, table, retention_days):
        return False
    if not _SAFE_IDENTIFIER_RE.fullmatch(table) or len(candidate.partition_name) > 63:
        return False

    preparer = conn.dialect.identifier_preparer
    parent = (
        f"{preparer.quote_identifier(candidate.parent_schema)}."
        f"{preparer.quote_identifier(table)}"
    )
    child = (
        f"{preparer.quote_identifier(candidate.child_schema)}."
        f"{preparer.quote_identifier(candidate.partition_name)}"
    )
    try:
        # The savepoint lets a missing relation or NOWAIT conflict fail safely
        # without rolling back a transaction owned by the caller.
        async with _bounded_partition_statement(conn):
            isolation_result = await conn.execute(
                text("SELECT pg_catalog.current_setting('transaction_isolation')")
            )
            isolation = isolation_result.scalar_one()
            if not isinstance(isolation, str) or isolation.lower() not in {
                "read committed",
                "read uncommitted",
            }:
                # A fixed MVCC snapshot could re-read obsolete catalog bounds
                # even after the current relation has been locked.
                return False
            lock = await conn.execute(
                text(
                    "SELECT pg_catalog.pg_try_advisory_xact_lock("
                    "pg_catalog.hashtext(:table_name))"
                ),
                {"table_name": table},
            )
            if not lock.scalar_one():
                return False
            await conn.exec_driver_sql(
                f"LOCK TABLE ONLY {parent} IN ACCESS EXCLUSIVE MODE NOWAIT"
            )
            await conn.exec_driver_sql(
                f"LOCK TABLE ONLY {child} IN ACCESS EXCLUSIVE MODE NOWAIT"
            )
            current = await _list_prunable_partitions(
                conn, table, partition_key, candidate=candidate
            )
            valid = current == [candidate] and _expired_partition_has_matching_bounds(
                table, candidate, retention_days
            )
            if valid:
                await conn.exec_driver_sql(f"DROP TABLE {child}")
    except (OSError, ConnectionError, SQLAlchemyError, TypeError, ValueError) as exc:
        logger.warning(
            "Could not safely prune partition %s (%s)",
            candidate.partition_name,
            type(exc).__name__,
        )
        return False
    if valid:
        logger.info("Pruned old partition %s", candidate.partition_name)
    return valid


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
                await _lock_partition_ddl(conn, table)
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
                await conn.rollback()
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
                    datetime.fromisoformat(str(start_date_iso).replace("Z", "+00:00"))
                    datetime.fromisoformat(str(end_date_iso).replace("Z", "+00:00"))

                    # RZ-20-05: Date literals are pre-validated via
                    # datetime.fromisoformat() above — safe to interpolate.
                    # DDL statements (CREATE TABLE) do not support bind
                    # parameters in PostgreSQL; asyncpg rejects them with
                    # "the server expects 0 arguments".
                    safe_start = str(start_date_iso).replace("'", "''")
                    safe_end = str(end_date_iso).replace("'", "''")
                    await _lock_partition_ddl(conn, table)
                    if await _range_partition_exists(
                        conn,
                        table,
                        start_date_iso,
                        end_date_iso,
                    ):
                        await conn.commit()
                        continue
                    await conn.exec_driver_sql(
                        f"CREATE TABLE {safe_partition} "
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
                    await conn.rollback()
                    # RZ-20-04 + RZ-33-03: Broadened — DDL errors, rust_ext import,
                    # and asyncpg interface errors.
                    logger.error(
                        "Failed to create partition: %s", e
                    )  # LOW-W19: lazy logging

        # 2. Prune old partitions
        retention_days = settings.partition_retention_days
        if retention_days > 0:
            for table, partition_key in PARTITIONED_TABLES:
                try:
                    partitions = await _list_prunable_partitions(
                        conn, table, partition_key
                    )
                    await conn.commit()
                except (
                    OSError,
                    ConnectionError,
                    SQLAlchemyError,
                    TypeError,
                    ValueError,
                ) as exc:
                    await conn.rollback()
                    logger.warning(
                        "Could not inspect partitions for %s (%s)",
                        table,
                        type(exc).__name__,
                    )
                    continue
                for candidate in partitions:
                    try:
                        await _prune_expired_partition(
                            conn,
                            table,
                            partition_key,
                            retention_days,
                            rust_ext,
                            candidate,
                        )
                        # Release parent/child locks before examining the next candidate.
                        await conn.commit()
                    except (OSError, ConnectionError, SQLAlchemyError):
                        await conn.rollback()
                        raise


async def start_partition_management_scheduler(
    interval_seconds: int = 86400,
) -> Callable[[], Coroutine[Any, Any, None]]:
    """
    Simplistic scheduler for partition management.
    In a real production environment, this might be a Celery Beat task or a cron job.
    """
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be greater than zero")

    from app.core.task_registry import TaskRegistry

    registry = TaskRegistry()

    async def run_periodically() -> None:
        while True:
            try:
                await ensure_partitions_exist()
            except asyncio.CancelledError:
                raise
            except (OSError, SQLAlchemyError, RuntimeError) as exc:
                # Recoverable database, system, and Rust FFI failures must not
                # terminate the lifecycle-managed scheduler. Avoid logging error
                # text, which may contain SQL or connection details.
                logger.error(
                    "Partition management cycle failed (%s)",
                    type(exc).__name__,
                )
            await asyncio.sleep(interval_seconds)

    registry.create_task(run_periodically(), name="partition_manager")

    async def stop() -> None:
        await registry.shutdown(timeout=10.0)

    return stop
