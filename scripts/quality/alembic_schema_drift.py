"""Fail-closed handling for PostgreSQL's validated-check nullability contract.

The MFA contract migration deliberately uses validated ``CHECK`` constraints
while the destructive WebAuthn retirement is deployed.  PostgreSQL reports
those columns as ``nullable`` in information_schema even though the check
rejects every NULL write.  Alembic's normalizer therefore needs one narrowly
scoped semantic adapter: it may discard *only* a nullable-only diff for the
known MFA columns, and only after the exact named check is proven validated.
Any type, default, comment, table, or unrelated nullable change remains a
hard drift failure.
"""

from __future__ import annotations

import logging
import re
from collections.abc import MutableSequence, Sequence
from typing import Any

import sqlalchemy as sa
from alembic.operations import ops

logger = logging.getLogger(__name__)

_CHECK_BACKED_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("mfa_challenges", "flow", "ck_mfa_challenges_flow_not_null"),
    (
        "mfa_challenges",
        "session_identifier",
        "ck_mfa_challenges_session_identifier_not_null",
    ),
    (
        "mfa_challenges",
        "client_fingerprint",
        "ck_mfa_challenges_client_fingerprint_not_null",
    ),
    ("mfa_challenges", "method", "ck_mfa_challenges_method_not_null"),
    ("mfa_challenges", "revision", "ck_mfa_challenges_revision_not_null"),
    (
        "mfa_challenges",
        "token_digest",
        "ck_mfa_challenges_token_digest_not_null",
    ),
    ("mfa_challenges", "token_key_id", "ck_mfa_challenges_token_key_id_not_null"),
    ("trusted_devices", "token_key_id", "ck_trusted_devices_token_key_id_not_null"),
    (
        "trusted_devices",
        "binding_digest",
        "ck_trusted_devices_binding_digest_not_null",
    ),
)
_CHECK_BACKED_KEYS = frozenset(
    (table, column) for table, column, _ in _CHECK_BACKED_COLUMNS
)


def _normalize_constraint_definition(definition: str) -> str:
    """Normalize pg_get_constraintdef output without changing its meaning."""

    return re.sub(r"[\s()\"]+", "", definition).upper()


def _is_validated_not_null_check(
    connection: Any,
    table: str,
    column: str,
    constraint_name: str,
) -> bool:
    row = connection.execute(
        sa.text(
            """
            SELECT convalidated, pg_get_constraintdef(c.oid)
            FROM pg_constraint AS c
            WHERE c.conrelid = to_regclass(:table_name)
              AND c.conname = :constraint_name
              AND c.contype = 'c'
            """
        ),
        {"table_name": table, "constraint_name": constraint_name},
    ).first()
    if row is None or row[0] is not True:
        return False
    expected = f"CHECK{column.upper()}ISNOTNULL"
    return _normalize_constraint_definition(str(row[1])) == expected


def validated_mfa_check_columns(connection: Any) -> frozenset[tuple[str, str]]:
    """Return only exact MFA columns whose named PostgreSQL check is validated."""

    if connection is None or getattr(connection.dialect, "name", None) != "postgresql":
        return frozenset()
    validated: set[tuple[str, str]] = set()
    for table, column, constraint_name in _CHECK_BACKED_COLUMNS:
        if _is_validated_not_null_check(connection, table, column, constraint_name):
            validated.add((table, column))
    return frozenset(validated)


def _filter_container(
    container: Any,
    check_backed_columns: frozenset[tuple[str, str]],
) -> None:
    child_ops = getattr(container, "ops", None)
    if not isinstance(child_ops, MutableSequence):
        return
    retained: list[Any] = []
    for operation in child_ops:
        if isinstance(operation, ops.ModifyTableOps):
            _filter_container(operation, check_backed_columns)
            if operation.ops:
                retained.append(operation)
            continue
        if (
            isinstance(operation, ops.AlterColumnOp)
            and (operation.table_name, operation.column_name) in check_backed_columns
            and operation.modify_nullable is False
            and operation.modify_type is None
            and operation.modify_server_default is False
            and operation.modify_comment is False
        ):
            operation.modify_nullable = None
            logger.info(
                "Treating validated MFA check as NOT NULL: %s.%s",
                operation.table_name,
                operation.column_name,
            )
        keep_operation = (
            operation.has_changes()
            if isinstance(operation, ops.AlterColumnOp)
            else True
        )
        if keep_operation:
            retained.append(operation)
    child_ops[:] = retained


def filter_check_backed_nullable_diffs(
    migration_context: Any,
    _revision: Any,
    directives: Sequence[Any],
) -> None:
    """Strip only proven nullable-only MFA diffs from Alembic autogenerate."""

    connection = getattr(migration_context, "connection", None)
    check_backed_columns = validated_mfa_check_columns(connection)
    if not check_backed_columns:
        return
    for directive in directives:
        upgrade_ops = getattr(directive, "upgrade_ops_list", ())
        for container in upgrade_ops:
            _filter_container(container, check_backed_columns)


__all__ = [
    "filter_check_backed_nullable_diffs",
    "validated_mfa_check_columns",
]
