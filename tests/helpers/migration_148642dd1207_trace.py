"""Test-only, source-bound observation of five nested migration DDL sites.

This is not a migration runner or a Squawk disposition. Only fixture-owned
databases may install its trace table. Trace rows commit/roll back with the
migration; negative-test evidence must come from separate fresh connections.
"""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from psycopg import sql

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic/versions/148642dd1207_fix_missing_tables.py"
)
SOURCE_GIT_BLOB = "bfab2a8f19a660fcc1f71288e735b0a327448037"
_SITE_SPECS = (
    (
        "groups_drop_id",
        "_postgresql_groups_id_upgrade",
        "'ALTER TABLE groups DROP COLUMN id';",
    ),
    (
        "groups_drop_shadow",
        "_postgresql_groups_id_upgrade",
        "'ALTER TABLE groups DROP COLUMN id__integer';",
    ),
    (
        "child_fk_drop",
        "_capture_groups_foreign_keys",
        "'ALTER TABLE %s DROP CONSTRAINT %I'",
    ),
    (
        "child_key_type",
        "_convert_captured_fk_columns",
        "'ALTER TABLE %s ALTER COLUMN %I TYPE INTEGER USING %I::INTEGER'",
    ),
    (
        "child_fk_restore",
        "_restore_groups_foreign_keys",
        "'ALTER TABLE %s ADD CONSTRAINT %I FOREIGN KEY (%s) '",
    ),
)


class TraceContractError(RuntimeError):
    """The diagnostic no longer matches its reviewed source or fixture."""


def git_blob_id(source: bytes) -> str:
    header = b"blob " + str(len(source)).encode("ascii") + b"\0"
    return hashlib.sha1(header + source, usedforsecurity=False).hexdigest()


@dataclass(frozen=True)
class DdlSite:
    name: str
    outer_sql: str
    executable: str

    def instrument(self, outer_ordinal: int) -> tuple[str, str]:
        """Insert one observation before, without replacing, the real EXECUTE."""
        if outer_ordinal < 0:
            raise TraceContractError("Trace ordinals must be nonnegative")
        expression = self.executable.removeprefix("EXECUTE ").removesuffix(";")
        observation = (
            sql.SQL(
                "INSERT INTO aud148_diag.executed_ddl "
                "(outer_ordinal, site, ddl) VALUES ({ordinal}, {site}, {expression});\n"
            )
            .format(
                ordinal=sql.Literal(outer_ordinal),
                site=sql.Literal(self.name),
                expression=sql.SQL(expression),
            )
            .as_string()
        )
        transformed = self.outer_sql.replace(
            self.executable, observation + self.executable, 1
        )
        return transformed, observation


def _extract_sites(source: str) -> tuple[DdlSite, ...]:
    """Read only known Python string constants, never arbitrary PL/pgSQL."""
    functions = {
        node.name: node
        for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef)
    }
    sites = []
    for name, function_name, marker in _SITE_SPECS:
        function = functions.get(function_name)
        if function is None:
            raise TraceContractError("Missing reviewed migration function")
        candidates = [
            node.value.replace("__TARGET_TYPE__", "INTEGER")
            for node in ast.walk(function)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value.lstrip().startswith("DO $$")
            and marker in node.value.replace("__TARGET_TYPE__", "INTEGER")
        ]
        if len(candidates) != 1:
            raise TraceContractError("Expected exactly one reviewed DDL constant")
        outer_sql = candidates[0]
        marker_position = outer_sql.index(marker)
        start = outer_sql.rfind("EXECUTE ", 0, marker_position + 1)
        if start < 0:
            raise TraceContractError("Reviewed DDL must remain an EXECUTE")
        end = outer_sql.find(";", marker_position)
        if end < 0:
            raise TraceContractError("Reviewed EXECUTE terminator is missing")
        executable = outer_sql[start : end + 1]
        if outer_sql.count(executable) != 1:
            raise TraceContractError("Reviewed EXECUTE must occur exactly once")
        sites.append(DdlSite(name, outer_sql, executable))
    return tuple(sites)


def reviewed_sites(source: bytes) -> tuple[DdlSite, ...]:
    if git_blob_id(source) != SOURCE_GIT_BLOB:
        raise TraceContractError(
            "Migration source changed: review the five sites and source binding first"
        )
    return _extract_sites(source.decode("utf-8"))


class ExpandedDdlTrace:
    """Observe original cursor order; optionally instrument the five exact sites."""

    def __init__(self, source: bytes, *, instrument: bool) -> None:
        self.sites = reviewed_sites(source)
        self.instrument = instrument
        self.events: list[dict[str, Any]] = []
        self.replacements: list[dict[str, Any]] = []

    def on_begin(self, _connection: Any) -> None:
        self.events.append({"kind": "begin"})

    def on_commit(self, _connection: Any) -> None:
        self.events.append({"kind": "commit"})

    def on_rollback(self, _connection: Any) -> None:
        self.events.append({"kind": "rollback"})

    def before_cursor_execute(
        self,
        connection: Any,
        _cursor: Any,
        statement: str,
        parameters: Any,
        _context: Any,
        executemany: bool,
    ) -> tuple[str, Any]:
        if len(self.events) >= 10_000:
            raise TraceContractError("Bounded diagnostic statement limit exceeded")
        ordinal = len(self.events)
        # pyformat escapes literal percent signs for the driver, even without binds.
        logical_sql = (
            statement.replace("%%", "%")
            if connection.dialect.paramstyle == "pyformat"
            else statement
        )
        self.events.append(
            {
                "kind": "cursor",
                "sql": logical_sql,
                "has_parameters": bool(parameters) or executemany,
            }
        )
        for site in self.sites:
            original = str(sa.text(site.outer_sql).compile(dialect=connection.dialect))
            if statement != original:
                continue
            if parameters or executemany:
                raise TraceContractError("Reviewed DDL unexpectedly acquired binds")
            if not self.instrument:
                return statement, parameters
            transformed, observation = site.instrument(ordinal)
            # Exact removal must recover the original bytes, not equivalent SQL.
            if transformed.replace(observation, "", 1) != site.outer_sql:
                raise TraceContractError("Instrumentation changed original SQL")
            compiled = str(sa.text(transformed).compile(dialect=connection.dialect))
            self.replacements.append({"outer_ordinal": ordinal, "site": site.name})
            return compiled, parameters
        return statement, parameters

    def expanded_sql(self, rows: list[tuple[int, str, str]]) -> str:
        """Build lint-only SQL, not a replay script, from a successful trace."""
        if not self.instrument:
            raise TraceContractError("Only the instrumented run has nested evidence")
        if [event["kind"] for event in self.events].count("begin") != 1 or [
            event["kind"] for event in self.events
        ].count("commit") != 1:
            raise TraceContractError("Successful inventory requires one transaction")
        if any(event["kind"] == "rollback" for event in self.events):
            raise TraceContractError("Rolled-back trace is not successful evidence")
        expected = {row["outer_ordinal"]: row["site"] for row in self.replacements}
        grouped: dict[int, list[str]] = {}
        seen = set()
        for ordinal, site_name, statement in rows:
            if expected.get(ordinal) != site_name:
                raise TraceContractError("Nested DDL does not match its source site")
            grouped.setdefault(ordinal, []).append(statement)
            seen.add(site_name)
        if seen != {site.name for site in self.sites}:
            raise TraceContractError("Populated fixture did not execute all five sites")
        if set(grouped) != set(expected):
            raise TraceContractError("A reviewed outer command has no nested evidence")
        output = [
            "-- DIAGNOSTIC ONLY: expanded executed DDL, NOT a replay script.",
            "-- Guard DO bodies remain in the original-cursor JSON evidence.",
        ]
        for ordinal, event in enumerate(self.events):
            kind = event["kind"]
            if kind in {"begin", "commit"}:
                output.append(kind.upper() + ";")
                continue
            statement = event["sql"].strip().rstrip(";")
            if ordinal in grouped:
                output.extend(item.rstrip(";") + ";" for item in grouped[ordinal])
                continue
            operation = statement.split(None, 1)[0].upper()
            if operation == "DO":
                output.append("-- observed guard DO; body retained in JSON evidence")
            elif operation in {
                "CREATE",
                "ALTER",
                "DROP",
                "SET",
                "LOCK",
                "COMMENT",
                "GRANT",
                "REVOKE",
                "TRUNCATE",
                "RENAME",
            }:
                output.append(statement + ";")
            elif operation in {"INSERT", "UPDATE", "DELETE", "MERGE"}:
                if event["has_parameters"]:
                    output.append("-- observed parameterized DML; values omitted")
                else:
                    output.append(statement + ";")
            elif "pg_advisory_xact_lock" in statement:
                output.append(statement + ";")
        return "\n".join(output) + "\n"
