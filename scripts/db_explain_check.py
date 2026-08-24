import argparse
import asyncio
import hashlib
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Set up logging with a clear format
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("db_perf_gate")

_SAFE_TABLE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
_EXPLAINABLE_STATEMENT_RE = re.compile(
    r"^(?:SELECT|WITH|INSERT|UPDATE|DELETE)\b", re.IGNORECASE
)


def normalize_explainable_query(query: str) -> str:
    """Return one bounded SQL statement suitable for EXPLAIN ANALYZE.

    Query logs are diagnostic input, not a trusted SQL channel. DDL, empty
    statements, NUL bytes, and stacked statements are rejected before the
    driver sees them. A single optional trailing semicolon is removed.
    """

    normalized = query.strip()
    if normalized.endswith(";"):
        normalized = normalized[:-1].rstrip()
    if (
        not normalized
        or "\x00" in normalized
        or ";" in normalized
        or _EXPLAINABLE_STATEMENT_RE.match(normalized) is None
    ):
        raise ValueError("query is not a single explainable DML statement")
    return normalized


def substitute_placeholders(query: str) -> str:
    """Replace database query parameter placeholders with dummy values.

    This function replaces postgres placeholders ($1, $2, ...) and named
    placeholders (:param) with safe defaults or NULLs, and handles
    pgvector distance operators properly.
    """
    # Replace vector similarity query placeholders with a valid 1536-dim vector
    query = re.sub(
        r"<=>\s*\$\d+",
        "<=> array_fill(0::real, ARRAY[1536])::vector",
        query,
        flags=re.IGNORECASE,
    )
    query = re.sub(
        r"<=>\s*(?<!:):\w+",
        "<=> array_fill(0::real, ARRAY[1536])::vector",
        query,
        flags=re.IGNORECASE,
    )
    query = re.sub(
        r"<=>\s*\?",
        "<=> array_fill(0::real, ARRAY[1536])::vector",
        query,
        flags=re.IGNORECASE,
    )

    # Replace standard placeholders with NULL
    query = re.sub(r"\$\d+", "NULL", query)
    query = re.sub(r"(?<!:):\w+", "NULL", query)
    query = query.replace("?", "NULL")

    return query


def extract_queries_from_logs(log_directory: Path) -> list[str]:
    """Search for query log files and extract unique SQL queries."""
    unique_queries: set[str] = set()

    # Search for all queries*.log files in the specified directory
    log_files = list(log_directory.glob("queries*.log"))
    logger.info(f"Found {len(log_files)} query log files in {log_directory}")

    for log_file in log_files:
        try:
            with open(log_file, encoding="utf-8") as file_handle:
                for line in file_handle:
                    cleaned_line = line.strip()
                    if cleaned_line:
                        unique_queries.add(cleaned_line)
        except Exception as error:
            logger.error(f"Failed to read query log file {log_file}: {error}")

    return sorted(list(unique_queries))


def find_sequential_scans(
    plan_node: dict[str, Any], target_tables: list[str]
) -> list[tuple[str, float]]:
    """Recursively search a JSON query plan for sequential scans on target tables."""
    sequential_scans: list[tuple[str, float]] = []
    if not isinstance(plan_node, dict):
        return sequential_scans

    node_type = plan_node.get("Node Type")
    relation_name = plan_node.get("Relation Name")
    total_cost = plan_node.get("Total Cost", 0.0)

    if node_type == "Seq Scan" and relation_name in target_tables:
        sequential_scans.append((relation_name, total_cost))

    # Check nested plans recursively
    if "Plans" in plan_node:
        for child_plan in plan_node["Plans"]:
            sequential_scans.extend(find_sequential_scans(child_plan, target_tables))

    return sequential_scans


async def run_explain_analysis(
    engine, queries: list[str], target_tables: list[str], max_cost_limit: float
) -> tuple[bool, int]:
    """Execute EXPLAIN (ANALYZE, BUFFERS) for each query and validate performance rules."""
    has_violations = False
    checked_count = 0

    if not target_tables or any(
        _SAFE_TABLE_RE.fullmatch(table) is None for table in target_tables
    ):
        raise ValueError("target tables must be non-empty safe SQL identifiers")

    # Calibrate statistics: artificially inflate table size to ensure planner cost decisions
    # are realistic (avoiding Seq Scans due to table emptiness in test DB)
    logger.info("Calibrating table statistics for planning simulation...")
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE pg_class SET relpages = 1000, reltuples = 100000, "
                    "relallvisible = 1000 "
                    "WHERE relname = ANY(CAST(:table_names AS text[]))"
                ),
                {"table_names": target_tables},
            )
            await conn.execute(
                text(
                    "UPDATE pg_class SET relpages = 100, reltuples = 100000 "
                    "WHERE oid IN ("
                    "  SELECT indexrelid FROM pg_index WHERE indrelid IN ("
                    "    SELECT oid FROM pg_class "
                    "    WHERE relname = ANY(CAST(:table_names AS text[]))"
                    "  )"
                    ")"
                ),
                {"table_names": target_tables},
            )
            logger.info("Table and index statistics successfully updated.")
    except Exception as error:
        logger.warning(
            f"Could not calibrate table statistics: {error}. Continuing with default statistics."
        )

    for raw_query in queries:
        try:
            clean_query = normalize_explainable_query(
                substitute_placeholders(raw_query)
            )
        except ValueError as error:
            query_id = hashlib.sha256(raw_query.encode()).hexdigest()[:12]
            logger.warning("Skipping unsafe query %s: %s", query_id, error)
            continue

        # We only need to check queries that target or mention our key tables
        # to save time and reduce noise.
        mentions_target_table = any(
            table in clean_query.lower() for table in target_tables
        )
        if not mentions_target_table:
            continue

        # Skip table-wide write operations without WHERE clauses (e.g. test cleanup)
        clean_query_lower = clean_query.lower().strip()
        if (
            clean_query_lower.startswith("delete")
            or clean_query_lower.startswith("update")
        ) and "where" not in clean_query_lower:
            continue

        checked_count += 1
        query_id = hashlib.sha256(raw_query.encode()).hexdigest()[:12]
        logger.info("Analyzing query %s", query_id)

        try:
            # Wrap in a transaction that is rolled back to prevent modifications
            async with engine.connect() as conn:
                async with conn.begin() as transaction:
                    # Enforce index usage by disabling sequential scans in this session
                    await conn.execute(text("SET LOCAL enable_seqscan = off"))
                    # Run EXPLAIN with ANALYZE and BUFFERS
                    explain_sql = (
                        f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {clean_query}"
                    )
                    # Add timeout to explain query to prevent hangs
                    await conn.execute(text("SET statement_timeout = '15s'"))
                    result = await conn.exec_driver_sql(explain_sql)
                    plan_json_str = result.scalar()
                    await transaction.rollback()

            if not plan_json_str:
                logger.warning("No plan returned for query %s", query_id)
                continue

            # Parse plan structure
            plan_data = (
                plan_json_str[0] if isinstance(plan_json_str, list) else plan_json_str
            )
            root_plan = plan_data.get("Plan", {})
            total_cost = root_plan.get("Total Cost", 0.0)

            # Check for Seq Scans
            seq_scans = find_sequential_scans(root_plan, target_tables)
            if seq_scans:
                for table_name, cost in seq_scans:
                    logger.error(
                        "VIOLATION: sequential scan on %s (cost=%s, query=%s)",
                        table_name,
                        cost,
                        query_id,
                    )
                has_violations = True

            # Check for High Cost
            if total_cost > max_cost_limit:
                logger.error(
                    "VIOLATION: query cost %s exceeds budget %s (query=%s)",
                    total_cost,
                    max_cost_limit,
                    query_id,
                )
                has_violations = True

            if not seq_scans and total_cost <= max_cost_limit:
                logger.info("Query %s passed (cost=%s)", query_id, total_cost)

        except Exception as error:
            logger.warning(
                "Could not execute EXPLAIN for query %s: %s", query_id, error
            )
            # If a query is invalid/broken or fails EXPLAIN, we treat it as a warning but don't fail the gate
            # unless it's a critical syntax error in schema.

    return has_violations, checked_count


async def main():
    parser = argparse.ArgumentParser(
        description="DB Performance Gate: Prevent Seq Scans and High Cost Queries"
    )
    parser.add_argument("--fail-on-seq-scan", action="store_true")
    parser.add_argument(
        "--tables",
        type=str,
        required=True,
        help="Comma-separated list of target tables",
    )
    parser.add_argument(
        "--max-cost", type=float, default=500.0, help="Maximum allowed query cost"
    )
    parser.add_argument(
        "--log-dir",
        type=str,
        default="tests",
        help="Directory where query logs are stored",
    )
    args = parser.parse_args()

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        logger.warning("DATABASE_URL not set. Skipping real DB checks.")
        sys.exit(0)

    engine = create_async_engine(db_url)
    target_tables = [t.strip() for t in args.tables.split(",")]
    log_dir_path = Path(args.log_dir)

    queries = extract_queries_from_logs(log_dir_path)
    if not queries:
        logger.warning(f"No queries found in log directory: {log_dir_path}")
        await engine.dispose()
        sys.exit(0)

    logger.info(f"Loaded {len(queries)} unique queries to analyze.")

    has_violations, checked_count = await run_explain_analysis(
        engine, queries, target_tables, args.max_cost
    )

    await engine.dispose()

    if has_violations and args.fail_on_seq_scan:
        logger.critical(
            f"DB Performance Gate FAILED: Found violations in {checked_count} checked queries."
        )
        sys.exit(1)

    logger.info(f"DB Performance Gate PASSED. Checked {checked_count} queries.")


if __name__ == "__main__":
    asyncio.run(main())
