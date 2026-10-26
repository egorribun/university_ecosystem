import argparse
import asyncio
import hashlib
import logging
import math
import os
import re
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

# Set up logging with a clear format
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("db_perf_gate")


class UnsupportedPlaceholderError(ValueError):
    """Raised when SQL text cannot be safely classified for rewriting.

    The analyzer fails closed instead of guessing how a marker or quote behaves.
    """


class IneligibleQueryError(ValueError):
    """Raised for transaction-control statements intentionally skipped by the gate."""


_SAFE_TABLE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
_EXPLAINABLE_STATEMENT_RE = re.compile(
    r"^(?:SELECT|WITH|INSERT|UPDATE|DELETE)\b", re.IGNORECASE
)
_INELIGIBLE_TRANSACTION_RE = re.compile(
    r"^(?:BEGIN|START\s+TRANSACTION|COMMIT|END|ROLLBACK|ABORT|SAVEPOINT|RELEASE)\b",
    re.IGNORECASE,
)


def normalize_explainable_query(query: str) -> str:
    """Return one bounded SQL statement suitable for planner-only EXPLAIN.

    Query logs are diagnostic input, not a trusted SQL channel. DDL, empty
    statements, NUL bytes, and stacked statements are rejected before the
    driver sees them. A single optional trailing semicolon is removed.
    """

    normalized = query.strip()
    if not normalized or "\x00" in normalized:
        raise ValueError("query is not a single explainable DML statement")

    separators = [
        start
        for kind, start, _, _ in _sql_placeholder_tokens(normalized)
        if kind == "separator"
    ]
    if separators:
        if len(separators) != 1 or separators[0] != len(normalized.rstrip()) - 1:
            raise ValueError("query contains multiple SQL statements")
        normalized = normalized[: separators[0]].rstrip()

    if _INELIGIBLE_TRANSACTION_RE.match(normalized) is not None:
        raise IneligibleQueryError("transaction-control statement is not analyzed")
    if _EXPLAINABLE_STATEMENT_RE.match(normalized) is None:
        raise ValueError("query is not a single explainable DML statement")
    return normalized


_QMARK_BIND_KEYWORDS = {
    "AS",
    "AND",
    "BETWEEN",
    "BY",
    "ELSE",
    "FROM",
    "ILIKE",
    "IN",
    "IS",
    "LIKE",
    "LIMIT",
    "NOT",
    "OFFSET",
    "OR",
    "RETURNING",
    "SELECT",
    "SET",
    "THEN",
    "VALUES",
    "WHEN",
    "WHERE",
}

_QMARK_CLAUSE_KEYWORDS = _QMARK_BIND_KEYWORDS | {
    "GROUP",
    "HAVING",
    "ORDER",
    "UNION",
}

_SQL_OPERATOR_CHARS = frozenset("~!@#%^&|`?+-*/<>=")
_QUESTION_MARK = "?"
_KNOWN_QMARK_OPERATORS = {"@?", "?|", "?&"}


def _previous_non_whitespace(query: str, position: int) -> int:
    previous = position - 1
    while previous >= 0 and query[previous].isspace():
        previous -= 1
    return previous


def _operator_token_at(query: str, position: int) -> str:
    start = position
    while start > 0 and query[start - 1] in _SQL_OPERATOR_CHARS:
        start -= 1
    end = position + 1
    while end < len(query) and query[end] in _SQL_OPERATOR_CHARS:
        end += 1
    return query[start:end]


def _previous_operator_token(query: str, position: int) -> str | None:
    previous = _previous_non_whitespace(query, position)
    if previous < 0 or query[previous] not in _SQL_OPERATOR_CHARS:
        return None

    start = previous
    while start > 0 and query[start - 1] in _SQL_OPERATOR_CHARS:
        start -= 1
    token = query[start : previous + 1]
    return None if token.endswith("*/") else token


def _is_sql_operand_before(query: str, position: int) -> bool:
    previous = _previous_non_whitespace(query, position)
    if previous < 0:
        return False

    character = query[previous]
    if character in ")]'\"":
        return True
    if not (character.isalnum() or character in "_$"):
        return False

    previous_word = re.search(
        r"([A-Za-z_][A-Za-z0-9_]*)$",
        query[: previous + 1],
    )
    return (
        previous_word is None
        or previous_word.group(1).upper() not in _QMARK_BIND_KEYWORDS
    )


def _starts_sql_operand_after(query: str, position: int) -> bool:
    following = position + 1
    while following < len(query) and query[following].isspace():
        following += 1
    if following >= len(query):
        return False

    character = query[following]
    if character.isalpha() or character == "_":
        following_word = re.match(r"[A-Za-z_][A-Za-z0-9_]*", query[following:])
        return (
            following_word is not None
            and following_word.group(0).upper() not in _QMARK_CLAUSE_KEYWORDS
        )

    return character.isdigit() or character in "'\"$:?([+-"


def _is_qmark_placeholder(
    query: str,
    position: int,
    operator_positions: set[int],
    bind_positions: set[int],
) -> bool:
    """Classify qmark binds and PostgreSQL JSON operators without guessing."""
    operator_token = _operator_token_at(query, position)
    if operator_token in _KNOWN_QMARK_OPERATORS:
        operator_positions.add(position)
        return False
    if operator_token != _QUESTION_MARK:
        raise UnsupportedPlaceholderError(
            "question mark appears in an unsupported SQL operator token"
        )

    previous = _previous_non_whitespace(query, position)
    if previous < 0:
        return True

    previous_character = query[previous]
    if previous in operator_positions:
        return True
    if previous in bind_positions:
        if _starts_sql_operand_after(query, position):
            operator_positions.add(position)
            return False
        raise UnsupportedPlaceholderError(
            "question mark follows a bind but has no operator right operand"
        )
    if previous_character in "([,":
        return True

    if _previous_operator_token(query, position) is not None:
        return True

    previous_word = re.search(
        r"([A-Za-z_][A-Za-z0-9_]*)$",
        query[:position].rstrip(),
    )
    if (
        previous_word is not None
        and previous_word.group(1).upper() in _QMARK_BIND_KEYWORDS
    ):
        return True

    if _is_sql_operand_before(query, position) and _starts_sql_operand_after(
        query, position
    ):
        operator_positions.add(position)
        return False

    raise UnsupportedPlaceholderError(
        "question mark is neither a bind marker nor a supported PostgreSQL operator"
    )


def _sql_placeholder_tokens(
    query: str,
) -> list[tuple[str, int, int, int | str | None]]:
    """Find bind markers and separators outside SQL strings and comments."""
    tokens: list[tuple[str, int, int, int | str | None]] = []
    operator_positions: set[int] = set()
    bind_positions: set[int] = set()
    index = 0

    while index < len(query):
        if query.startswith("--", index):
            line_end = query.find("\n", index + 2)
            index = len(query) if line_end < 0 else line_end + 1
            continue

        if query.startswith("/*", index):
            index += 2
            depth = 1
            while index < len(query) and depth:
                if query.startswith("/*", index):
                    depth += 1
                    index += 2
                elif query.startswith("*/", index):
                    depth -= 1
                    index += 2
                else:
                    index += 1
            continue

        if query[index] == "'":
            escape_string = (
                index > 0
                and query[index - 1] in "eE"
                and (
                    index < 2
                    or not (query[index - 2].isalnum() or query[index - 2] == "_")
                )
            )
            index += 1
            while index < len(query):
                if escape_string and query[index] == "\\":
                    index += 2
                elif not escape_string and query[index] == "\\":
                    raise UnsupportedPlaceholderError(
                        "ordinary string with backslash is ambiguous without "
                        "standard_conforming_strings evidence"
                    )
                elif query[index] == "'":
                    if index + 1 < len(query) and query[index + 1] == "'":
                        index += 2
                    else:
                        index += 1
                        break
                else:
                    index += 1
            continue

        if query[index] == ";":
            tokens.append(("separator", index, index + 1, None))
            index += 1
            continue

        if query[index] == '"':
            index += 1
            while index < len(query):
                if query[index] == '"':
                    if index + 1 < len(query) and query[index + 1] == '"':
                        index += 2
                    else:
                        index += 1
                        break
                else:
                    index += 1
            continue

        if query[index] == "$":
            identifier_suffix = index > 0 and (
                query[index - 1].isalnum() or query[index - 1] in "_$"
            )
            dollar_quote = (
                None
                if identifier_suffix
                else re.match(r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$", query[index:])
            )
            if dollar_quote is not None:
                delimiter = dollar_quote.group(0)
                closing = query.find(delimiter, index + len(delimiter))
                index = len(query) if closing < 0 else closing + len(delimiter)
                continue

            positional = (
                None if identifier_suffix else re.match(r"\$(\d+)", query[index:])
            )
            if positional is not None:
                end = index + len(positional.group(0))
                tokens.append(("positional", index, end, int(positional.group(1))))
                index = end
                continue

        if (
            query[index] == ":"
            and (index == 0 or query[index - 1] != ":")
            and index + 1 < len(query)
            and (query[index + 1].isalpha() or query[index + 1] == "_")
        ):
            end = index + 2
            while end < len(query) and (query[end].isalnum() or query[end] == "_"):
                end += 1
            tokens.append(("named", index, end, query[index + 1 : end]))
            index = end
            continue

        if query[index] == "?":
            if _is_qmark_placeholder(query, index, operator_positions, bind_positions):
                tokens.append(("anonymous", index, index + 1, None))
                bind_positions.add(index)
            index += 1
            continue

        index += 1

    return tokens


def _is_vector_distance_placeholder(query: str, position: int) -> bool:
    return query[:position].rstrip().endswith("<=>")


def substitute_placeholders(query: str) -> str:
    """Normalize bind markers to PostgreSQL parameters for generic EXPLAIN.

    Named and anonymous binds become numbered parameters, so a bound NULL cannot
    fold a filter into a constant-false predicate. Vector-distance binds retain
    the existing valid synthetic vector literal.
    """
    tokens = _sql_placeholder_tokens(query)
    slots: dict[tuple[str, int | str | None], int] = {}
    next_slot = 1

    for kind, start, _, value in tokens:
        if kind == "separator":
            continue
        if _is_vector_distance_placeholder(query, start):
            continue
        key = (kind, value if kind != "anonymous" else start)
        if key not in slots:
            slots[key] = next_slot
            next_slot += 1

    vector_literal = "array_fill(0::real, ARRAY[1536])::vector"
    parts: list[str] = []
    previous_end = 0
    for kind, start, end, value in tokens:
        parts.append(query[previous_end:start])
        if kind == "separator":
            parts.append(query[start:end])
            previous_end = end
            continue
        if _is_vector_distance_placeholder(query, start):
            parts.append(vector_literal)
        else:
            key = (kind, value if kind != "anonymous" else start)
            parts.append(f"${slots[key]}")
        previous_end = end
    parts.append(query[previous_end:])
    return "".join(parts)


def _sql_parameter_count(query: str) -> int:
    """Return the highest live positional bind number outside SQL literals."""
    return max(
        (
            int(value)
            for kind, _, _, value in _sql_placeholder_tokens(query)
            if kind == "positional" and isinstance(value, int)
        ),
        default=0,
    )


def _plan_statement_name(query: str) -> str:
    return "db_perf_gate_" + hashlib.sha256(query.encode()).hexdigest()[:12]


async def explain_plan(conn: Any, query: str) -> object:
    """Plan one statement without executing it and return the JSON plan.

    Bind markers are normalized to $n and planned under force_generic_plan.
    Generic plans do not use the synthetic NULL arguments to fold predicates,
    so the planner can still expose scans that the gate must catch (AUD-461).
    """
    parameter_count = _sql_parameter_count(query)
    if parameter_count == 0:
        result = await conn.exec_driver_sql(f"EXPLAIN (FORMAT JSON) {query}")
        return result.scalar()

    # PREPARE is session-scoped, while a failed EXPLAIN aborts its transaction.
    # A savepoint restores the outer transaction before the finally block removes
    # this named statement; DEALLOCATE ALL would drop asyncpg's cached statements.
    statement_name = _plan_statement_name(query)
    await conn.execute(text("SET LOCAL plan_cache_mode = force_generic_plan"))
    prepare_attempted = False
    try:
        async with conn.begin_nested():
            prepare_attempted = True
            await conn.exec_driver_sql(f"PREPARE {statement_name} AS {query}")
            arguments = ", ".join("NULL" for _ in range(parameter_count))
            result = await conn.exec_driver_sql(
                f"EXPLAIN (FORMAT JSON) EXECUTE {statement_name}({arguments})"
            )
            plan = result.scalar()
    finally:
        if prepare_attempted:
            try:
                await conn.exec_driver_sql(f"DEALLOCATE {statement_name}")
            except DBAPIError as cleanup_error:
                # A savepoint rollback may already have removed PREPARE.
                if getattr(cleanup_error.orig, "sqlstate", None) != "26000":
                    raise
    return plan


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


def _usable_plan_node(plan_node: object) -> bool:
    """Return whether a PostgreSQL plan node has the fields the gate consumes."""
    if not isinstance(plan_node, dict):
        return False

    node_type = plan_node.get("Node Type")
    if (
        not isinstance(node_type, str)
        or not node_type
        or node_type != node_type.strip()
    ):
        return False

    total_cost = plan_node.get("Total Cost")
    if isinstance(total_cost, bool) or not isinstance(total_cost, (int, float)):
        return False
    try:
        if not math.isfinite(total_cost) or total_cost < 0:
            return False
    except OverflowError:
        return False

    if node_type == "Seq Scan":
        relation_name = plan_node.get("Relation Name")
        if (
            not isinstance(relation_name, str)
            or not relation_name
            or relation_name != relation_name.strip()
        ):
            return False

    if "Plans" not in plan_node:
        return True
    children = plan_node["Plans"]
    return isinstance(children, list) and all(
        _usable_plan_node(child) for child in children
    )


def _extract_usable_explain_plan(plan_json: object) -> dict[str, Any] | None:
    """Accept the single JSON EXPLAIN document only when its plan is usable."""
    if isinstance(plan_json, list):
        if len(plan_json) != 1:
            return None
        document = plan_json[0]
    else:
        document = plan_json

    if not isinstance(document, dict):
        return None
    plan = document.get("Plan")
    if not _usable_plan_node(plan):
        return None
    return plan


async def _calibrate_statistics(conn: Any, target_tables: list[str]) -> None:
    """Keep both synthetic catalog updates within one recoverable savepoint."""
    async with conn.begin_nested():
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


async def run_explain_analysis(
    engine,
    queries: list[str],
    target_tables: list[str],
    max_cost_limit: float,
    *,
    fail_on_analysis_error: bool = False,
) -> tuple[bool, int]:
    """Plan logged statements and optionally fail when analysis is incomplete."""
    has_violations = False
    checked_count = 0

    if not target_tables or any(
        _SAFE_TABLE_RE.fullmatch(table) is None for table in target_tables
    ):
        raise ValueError("target tables must be non-empty safe SQL identifiers")

    for raw_query in queries:
        try:
            clean_query = normalize_explainable_query(
                substitute_placeholders(raw_query)
            )
        except IneligibleQueryError as error:
            logger.info("Skipping ineligible transaction-control query: %s", error)
            continue
        except UnsupportedPlaceholderError as error:
            query_id = hashlib.sha256(raw_query.encode()).hexdigest()[:12]
            logger.warning(
                "Skipping query with unsupported SQL syntax %s: %s",
                query_id,
                error,
            )
            if fail_on_analysis_error and any(
                table in raw_query.lower() for table in target_tables
            ):
                has_violations = True
            continue
        except ValueError as error:
            query_id = hashlib.sha256(raw_query.encode()).hexdigest()[:12]
            logger.warning("Skipping unsafe query %s: %s", query_id, error)
            if fail_on_analysis_error and any(
                table in raw_query.lower() for table in target_tables
            ):
                has_violations = True
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
            # Scope planner settings and timeout to this query analysis.
            async with engine.connect() as conn:
                async with conn.begin() as transaction:
                    # Enforce index usage by disabling sequential scans in this session
                    await conn.execute(text("SET LOCAL enable_seqscan = off"))
                    # Query logs omit bind values; planner-only EXPLAIN keeps
                    # synthetic placeholders from executing DML or DML CTEs.
                    # Add timeout to explain query to prevent hangs
                    await conn.execute(text("SET statement_timeout = '15s'"))
                    # AUD-504: calibration and EXPLAIN share this rollback-only
                    # transaction. A savepoint restores both catalog updates if
                    # calibration fails, so optional analysis can use defaults.
                    logger.info(
                        "Calibrating table statistics for planning simulation..."
                    )
                    try:
                        await _calibrate_statistics(conn, target_tables)
                        logger.info("Table and index statistics successfully updated.")
                    except Exception as error:
                        logger.warning(
                            "Could not calibrate table statistics: %s. "
                            "Continuing with default statistics.",
                            error,
                        )
                        if fail_on_analysis_error:
                            has_violations = True
                    plan_json_str = await explain_plan(conn, clean_query)
                    await transaction.rollback()

            if fail_on_analysis_error:
                root_plan = _extract_usable_explain_plan(plan_json_str)
                if root_plan is None:
                    logger.warning("No usable plan returned for query %s", query_id)
                    has_violations = True
                    continue
                total_cost = root_plan["Total Cost"]
            else:
                if not plan_json_str:
                    logger.warning("No plan returned for query %s", query_id)
                    continue

                # Preserve the legacy optional-mode parsing behavior.
                plan_data = (
                    plan_json_str[0]
                    if isinstance(plan_json_str, list)
                    else plan_json_str
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
            if fail_on_analysis_error:
                has_violations = True

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
        if args.fail_on_seq_scan:
            logger.error(
                "DATABASE_URL not set. DB Performance Gate cannot verify query plans."
            )
            sys.exit(1)
        logger.warning("DATABASE_URL not set. Skipping real DB checks.")
        sys.exit(0)

    engine = create_async_engine(db_url)
    target_tables = [t.strip() for t in args.tables.split(",")]
    log_dir_path = Path(args.log_dir)

    queries = extract_queries_from_logs(log_dir_path)
    if not queries:
        if args.fail_on_seq_scan:
            logger.error(
                "No queries found in log directory: %s. "
                "DB Performance Gate cannot verify query plans.",
                log_dir_path,
            )
            exit_code = 1
        else:
            logger.warning(f"No queries found in log directory: {log_dir_path}")
            exit_code = 0
        await engine.dispose()
        sys.exit(exit_code)

    logger.info(f"Loaded {len(queries)} unique queries to analyze.")

    has_violations, checked_count = await run_explain_analysis(
        engine,
        queries,
        target_tables,
        args.max_cost,
        # Preserve analysis failures in the result even for the optional mode,
        # so that it cannot print PASSED after an incomplete plan check. The CLI
        # flag controls whether that result changes the process exit status.
        fail_on_analysis_error=True,
    )

    await engine.dispose()

    if args.fail_on_seq_scan and (has_violations or checked_count == 0):
        if checked_count == 0:
            logger.critical(
                "DB Performance Gate FAILED: No eligible target queries were checked."
            )
        else:
            logger.critical(
                "DB Performance Gate FAILED: Violation or analysis failure "
                "in %s checked queries.",
                checked_count,
            )
        sys.exit(1)

    # AUD-225: optional (non-gating) mode may log violations, but it must not
    # claim a pass after them.
    if has_violations:
        logger.warning(
            "DB Performance Gate reported violations or analysis failures "
            "in optional mode; "
            "pass --fail-on-seq-scan to enforce them."
        )
        return

    if checked_count == 0:
        logger.warning(
            "DB Performance Gate: No eligible target queries were checked in optional mode; "
            "no pass was established."
        )
        return

    logger.info(f"DB Performance Gate PASSED. Checked {checked_count} queries.")


if __name__ == "__main__":
    asyncio.run(main())
