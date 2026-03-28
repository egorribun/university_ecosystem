import argparse
import asyncio
import json
import logging
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("db_perf_gate")


async def check_seq_scans(engine, tables: list[str]) -> bool:
    has_seq_scan = False

    queries = {
        "news": "EXPLAIN (FORMAT JSON) SELECT * FROM news ORDER BY embedding <=> '[0]'::vector LIMIT 10;",
        "events": "EXPLAIN (FORMAT JSON) SELECT * FROM events WHERE is_active = true ORDER BY created_at DESC LIMIT 20;",
        "users": "EXPLAIN (FORMAT JSON) SELECT * FROM users WHERE lower(email) = 'test@example.com';",
    }

    for table in tables:
        if table not in queries:
            continue

        query = queries[table]
        logger.info(f"Analyzing {table}...")
        try:
            # Each query gets its own connection so a failed EXPLAIN
            # (e.g. missing table) does not poison subsequent queries.
            async with engine.connect() as conn:
                result = await conn.execute(text(query))
                plan = result.scalar()

            plan_str = json.dumps(plan)
            if "Seq Scan" in plan_str:
                logger.error(f"Sequential Scan detected on {table}!")
                logger.error(f"Plan: {plan_str}")
                has_seq_scan = True
            else:
                logger.info(f"✓ {table} uses proper indexing.")
        except Exception as e:
            # LOW-W19: treat EXPLAIN failure as a conservative positive to avoid
            # silently bypassing the seq-scan gate on a broken query/table.
            logger.warning(f"Could not execute EXPLAIN on {table}: {e}")
            has_seq_scan = True

    return has_seq_scan


async def main():
    parser = argparse.ArgumentParser(
        description="DB Performance Gate: Prevent Seq Scans"
    )
    parser.add_argument("--fail-on-seq-scan", action="store_true")
    parser.add_argument(
        "--tables", type=str, required=True, help="Comma-separated list of tables"
    )
    parser.add_argument("--min-rows", type=int, default=10000)
    args = parser.parse_args()

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        logger.warning("DATABASE_URL not set. Skipping real DB checks.")
        sys.exit(0)

    engine = create_async_engine(db_url)

    tables = [t.strip() for t in args.tables.split(",")]
    has_seq_scan = await check_seq_scans(engine, tables)

    await engine.dispose()

    if has_seq_scan and args.fail_on_seq_scan:
        logger.critical("DB Performance Gate FAILED: Sequential scans detected.")
        sys.exit(1)

    logger.info("DB Performance Gate PASSED.")


if __name__ == "__main__":
    asyncio.run(main())
