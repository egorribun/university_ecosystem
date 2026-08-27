"""Restore failed-login indexes and its nullable user foreign key.

The range-partition conversion in ``202607020001`` intentionally copied only
columns and defaults.  PostgreSQL therefore lost the indexes and the
``ON DELETE SET NULL`` foreign key that are declared by
``FailedLoginAttempt``.  This additive reconciliation restores those runtime
contracts without changing data or relying on a naming convention for child
partitions.  Every operation is guarded so an interrupted deployment can be
retried safely.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "202608270002"
down_revision: str | None = "202608270001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "failed_login_attempts"
_FK_NAME = "fk_failed_login_attempts_user_id"
_INDEXES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ix_failed_login_attempts_attempted_at", ("attempted_at",)),
    ("ix_failed_login_attempts_email", ("email",)),
    ("ix_failed_login_attempts_email_attempted_at", ("email", "attempted_at")),
    ("ix_failed_login_attempts_ip_address", ("ip_address",)),
    ("ix_failed_login_attempts_ip_attempted_at", ("ip_address", "attempted_at")),
    ("ix_failed_login_attempts_user_id", ("user_id",)),
)


def _table_exists(inspector: Any) -> bool:
    return inspector.has_table(_TABLE)


def _foreign_key_matches(foreign_key: dict[str, Any]) -> bool:
    return (
        foreign_key.get("constrained_columns") == ["user_id"]
        and foreign_key.get("referred_table") == "users"
        and foreign_key.get("referred_columns") == ["id"]
        and str(foreign_key.get("options", {}).get("ondelete", "")).upper()
        == "SET NULL"
    )


def _index_matches(index: dict[str, Any], columns: tuple[str, ...]) -> bool:
    """Require an existing same-name index to implement the model contract."""

    return index.get("column_names") == list(columns) and not bool(
        index.get("unique", False)
    )


def _create_user_foreign_key(bind: Any, inspector: Any) -> None:
    foreign_keys = inspector.get_foreign_keys(_TABLE)
    if any(_foreign_key_matches(foreign_key) for foreign_key in foreign_keys):
        return

    if bind.dialect.name == "sqlite":
        # SQLite rebuilds tables for constraint changes.  Give reflected
        # unnamed foreign keys a deterministic temporary name so a legacy
        # CASCADE relation can be removed instead of being left alongside the
        # required SET NULL relation.  The rebuild runs in one transaction and
        # preserves all columns and rows through Alembic's batch copy.
        existing_user_fks = [
            foreign_key
            for foreign_key in foreign_keys
            if (
                foreign_key.get("constrained_columns") == ["user_id"]
                and foreign_key.get("referred_table") == "users"
            )
        ]
        naming_convention = {
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
        }
        with op.batch_alter_table(
            _TABLE,
            schema=None,
            recreate="always",
            naming_convention=naming_convention,
        ) as batch_op:
            for foreign_key in existing_user_fks:
                constraint_name = foreign_key.get("name") or (
                    f"fk_{_TABLE}_user_id_users"
                )
                batch_op.drop_constraint(constraint_name, type_="foreignkey")
            batch_op.create_foreign_key(
                _FK_NAME,
                "users",
                ["user_id"],
                ["id"],
                ondelete="SET NULL",
            )
    else:
        # A pre-existing relation with the same local/remote columns but
        # another delete action is not equivalent to the model contract.
        # PostgreSQL always assigns a name to an FK; fail closed if a driver
        # ever reports an unnamed relation rather than risking a duplicate
        # constraint with the wrong delete behavior.
        for foreign_key in foreign_keys:
            if (
                foreign_key.get("constrained_columns") == ["user_id"]
                and foreign_key.get("referred_table") == "users"
            ):
                if not foreign_key.get("name"):
                    raise RuntimeError(
                        "Cannot safely replace unnamed PostgreSQL user foreign key"
                    )
                op.drop_constraint(foreign_key["name"], _TABLE, type_="foreignkey")
        op.create_foreign_key(
            _FK_NAME,
            _TABLE,
            "users",
            ["user_id"],
            ["id"],
            ondelete="SET NULL",
        )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _table_exists(inspector):
        return

    existing_indexes = {
        index["name"]: index
        for index in inspector.get_indexes(_TABLE)
        if index.get("name")
    }
    for name, columns in _INDEXES:
        existing = existing_indexes.get(name)
        if existing is not None:
            if not _index_matches(existing, columns):
                raise RuntimeError(
                    f"Existing index {name!r} does not match failed-login schema contract"
                )
            continue
        op.create_index(name, _TABLE, list(columns), unique=False)

    _create_user_foreign_key(bind, inspector)


def downgrade() -> None:
    """Keep reconciliation objects when ownership cannot be proven.

    This migration is intentionally idempotent and may find indexes or an
    equivalent foreign key created by the ORM, an operator, or an earlier
    partially-applied revision.  Alembic does not retain object ownership, so
    deleting by name during downgrade could remove a baseline security/audit
    contract.  The parent revision remains valid with these additive objects;
    rollback therefore performs no destructive DDL.
    """

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _table_exists(inspector):
        return
