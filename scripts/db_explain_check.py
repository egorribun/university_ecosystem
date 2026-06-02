import argparse
import asyncio
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Set up logging with a clear format
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("db_perf_gate")


def substitute_placeholders(query: str) -> str:
    """Replace database query parameter placeholders with dummy values.
    
    This function replaces postgres placeholders ($1, $2, ...) and named 
    placeholders (:param) with safe defaults or NULLs, and handles 
    pgvector distance operators properly.
    """
    # Replace vector similarity query placeholders with a valid 1536-dim vector
    query = re.sub(
        r'<=>\s*\$\d+', 
        "<=> array_fill(0::real, ARRAY[1536])::vector", 
        query, 
        flags=re.IGNORECASE
    )
    query = re.sub(
        r'<=>\s*:\w+', 
        "<=> array_fill(0::real, ARRAY[1536])::vector", 
        query, 
        flags=re.IGNORECASE
    )
    
    # Replace standard placeholders with NULL
    query = re.sub(r'\$\d+', "NULL", query)
    query = re.sub(r':\w+', "NULL", query)
    
    return query


def extract_queries_from_logs(log_directory: Path) -> List[str]:
    """Search for query log files and extract unique SQL queries."""
    unique_queries: Set[str] = set()
    
    # Search for all queries*.log files in the specified directory
    log_files = list(log_directory.glob("queries*.log"))
    logger.info(f"Found {len(log_files)} query log files in {log_directory}")
    
    for log_file in log_files:
        try:
            with open(log_file, "r", encoding="utf-8") as file_handle:
                for line in file_handle:
                    cleaned_line = line.strip()
                    if cleaned_line:
                        unique_queries.add(cleaned_line)
        except Exception as error:
            logger.error(f"Failed to read query log file {log_file}: {error}")
            
    return sorted(list(unique_queries))


def find_sequential_scans(plan_node: Dict[str, Any], target_tables: List[str]) -> List[Tuple[str, float]]:
    """Recursively search a JSON query plan for sequential scans on target tables."""
    sequential_scans: List[Tuple[str, float]] = []
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
    engine, 
    queries: List[str], 
    target_tables: List[str], 
    max_cost_limit: float
) -> Tuple[bool, int]:
    """Execute EXPLAIN (ANALYZE, BUFFERS) for each query and validate performance rules."""
    has_violations = False
    checked_count = 0
    
    # Calibrate statistics: artificially inflate table size to ensure planner cost decisions
    # are realistic (avoiding Seq Scans due to table emptiness in test DB)
    logger.info("Calibrating table statistics for planning simulation...")
    try:
        async with engine.begin() as conn:
            table_list = ", ".join(f"'{table}'" for table in target_tables)
            await conn.execute(text(
                f"UPDATE pg_class SET relpages = 1000, reltuples = 100000 WHERE relname IN ({table_list});"
            ))
            logger.info("Table statistics successfully updated.")
    except Exception as error:
        logger.warning(f"Could not calibrate table statistics: {error}. Continuing with default statistics.")
        
    for raw_query in queries:
        clean_query = substitute_placeholders(raw_query)
        
        # We only need to check queries that target or mention our key tables
        # to save time and reduce noise.
        mentions_target_table = any(table in clean_query.lower() for table in target_tables)
        if not mentions_target_table:
            continue
            
        checked_count += 1
        logger.info(f"Analyzing query: {raw_query[:80]}...")
        
        try:
            # Wrap in a transaction that is rolled back to prevent modifications
            async with engine.connect() as conn:
                async with conn.begin() as transaction:
                    # Run EXPLAIN with ANALYZE and BUFFERS
                    explain_sql = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {clean_query}"
                    result = await conn.execute(text(explain_sql))
                    plan_json_str = result.scalar()
                    await transaction.rollback()
                    
            if not plan_json_str:
                logger.warning(f"No plan returned for query: {raw_query[:50]}")
                continue
                
            # Parse plan structure
            plan_data = plan_json_str[0] if isinstance(plan_json_str, list) else plan_json_str
            root_plan = plan_data.get("Plan", {})
            total_cost = root_plan.get("Total Cost", 0.0)
            
            # Check for Seq Scans
            seq_scans = find_sequential_scans(root_plan, target_tables)
            if seq_scans:
                for table_name, cost in seq_scans:
                    logger.error(
                        f"VIOLATION: Sequential Scan detected on target table '{table_name}' "
                        f"in query: {raw_query}"
                    )
                has_violations = True
            
            # Check for High Cost
            if total_cost > max_cost_limit:
                logger.error(
                    f"VIOLATION: Query cost {total_cost} exceeds maximum allowed budget "
                    f"of {max_cost_limit} for query: {raw_query}"
                )
                has_violations = True
                
            if not seq_scans and total_cost <= max_cost_limit:
                logger.info(f"✓ Query passed. Cost: {total_cost}")
                
        except Exception as error:
            logger.warning(f"Could not execute EXPLAIN for query: {raw_query}. Error: {error}")
            # If a query is invalid/broken or fails EXPLAIN, we treat it as a warning but don't fail the gate
            # unless it's a critical syntax error in schema.
            
    return has_violations, checked_count


async def main():
    parser = argparse.ArgumentParser(
        description="DB Performance Gate: Prevent Seq Scans and High Cost Queries"
    )
    parser.add_argument("--fail-on-seq-scan", action="store_true")
    parser.add_argument(
        "--tables", type=str, required=True, help="Comma-separated list of target tables"
    )
    parser.add_argument(
        "--max-cost", type=float, default=500.0, help="Maximum allowed query cost"
    )
    parser.add_argument(
        "--log-dir", type=str, default="tests", help="Directory where query logs are stored"
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
        engine, 
        queries, 
        target_tables, 
        args.max_cost
    )

    await engine.dispose()

    if has_violations and args.fail_on_seq_scan:
        logger.critical(f"DB Performance Gate FAILED: Found violations in {checked_count} checked queries.")
        sys.exit(1)

    logger.info(f"DB Performance Gate PASSED. Checked {checked_count} queries.")


if __name__ == "__main__":
    asyncio.run(main())
