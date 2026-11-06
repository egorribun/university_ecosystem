"""Alembic plugin for PostgreSQL JSON server-default comparison."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from alembic.runtime.plugins import Plugin
from alembic.util import DispatchPriority, PriorityDispatchResult

if TYPE_CHECKING:
    from alembic.autogenerate.api import AutogenContext
    from alembic.operations.ops import AlterColumnOp
    from sqlalchemy.sql.schema import Column

PLUGIN_NAME = "university_ecosystem.alembic_json_server_defaults"


def _render_default(
    default: sa.schema.DefaultClause | None, dialect: Any
) -> str | None:
    if default is None:
        return None
    if isinstance(default.arg, str):
        return default.arg
    return str(
        default.arg.compile(
            dialect=dialect,
            compile_kwargs={"literal_binds": True},
        )
    )


def compare_json_server_default(
    autogen_context: AutogenContext,
    alter_column_op: AlterColumnOp,
    _schema: str | None,
    table_name: str,
    column_name: str,
    inspected_column: Column[Any],
    metadata_column: Column[Any],
) -> PriorityDispatchResult:
    """Compare only the canonical push-topic JSON default expression."""
    if (
        autogen_context.dialect.name != "postgresql"
        or table_name != "push_subscriptions"
        or column_name != "topics"
        or not isinstance(inspected_column.type, sa.JSON)
        or not isinstance(metadata_column.type, sa.JSON)
    ):
        return PriorityDispatchResult.CONTINUE

    inspected_default = inspected_column.server_default
    metadata_default = metadata_column.server_default
    supported_defaults = (sa.schema.DefaultClause, type(None))
    if not isinstance(inspected_default, supported_defaults) or not isinstance(
        metadata_default, supported_defaults
    ):
        # Let Alembic's native Computed/Identity comparators handle these cases.
        return PriorityDispatchResult.CONTINUE

    alter_column_op.existing_server_default = inspected_default
    if _render_default(inspected_default, autogen_context.dialect) != _render_default(
        metadata_default, autogen_context.dialect
    ):
        alter_column_op.modify_server_default = metadata_default

    # PostgreSQL JSON has no equality operator; the rendered default expressions
    # above are the intended comparison for this one model-owned column.
    return PriorityDispatchResult.STOP


def setup(plugin: Plugin) -> None:
    plugin.add_autogenerate_comparator(
        compare_json_server_default,
        "column",
        "server_default",
        qualifier="postgresql",
        priority=DispatchPriority.FIRST,
    )


_registered = False


def register() -> None:
    global _registered
    if _registered:
        return
    Plugin.setup_plugin_from_module(sys.modules[__name__], PLUGIN_NAME)
    _registered = True
