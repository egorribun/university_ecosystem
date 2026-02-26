"""Introduce multi-factor authentication tables."""

from __future__ import annotations


import sqlalchemy as sa

from alembic import op
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "202507300001"
down_revision: str | None = "202507200001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_USERS_TABLE = "users"
_ACTIVE_SESSIONS_TABLE = "active_sessions"
_TOTP_TABLE = "mfa_totp_enrollments"
_WEBAUTHN_TABLE = "mfa_webauthn_credentials"
_RECOVERY_TABLE = "mfa_recovery_codes"
_CHALLENGES_TABLE = "mfa_challenges"


def _table_names(inspector) -> set[str]:
    return set(inspector.get_table_names())


def _column_names(inspector, table: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table)}


def _index_names(inspector, table: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table)}


def _empty_names(inspector, table: str) -> set[str]:
    return set()


def upgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name
    is_sqlite = dialect_name == "sqlite"

    # Offline mode check
    try:
        inspector = sa.inspect(bind)
    except (sa.exc.NoInspectionAvailable, NameError):
        inspector = None

    # Implementation helpers - default to global functions
    get_cols = _column_names
    get_idxs = _index_names

    if inspector is None:
        tables: set[str] = {
            _USERS_TABLE,
            _ACTIVE_SESSIONS_TABLE,
        }
        # Mock inspector functions for offline mode
        get_cols = _empty_names
        get_idxs = _empty_names
        inspector = None
    else:
        tables = _table_names(inspector)

    if _USERS_TABLE in tables:
        user_columns = get_cols(inspector, _USERS_TABLE)
        user_indexes = get_idxs(inspector, _USERS_TABLE)

        if "mfa_required" not in user_columns:
            op.add_column(
                _USERS_TABLE,
                sa.Column(
                    "mfa_required",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                ),
            )
            if not is_sqlite:
                op.alter_column(_USERS_TABLE, "mfa_required", server_default=None)
        if "mfa_default_method" not in user_columns:
            op.add_column(
                _USERS_TABLE,
                sa.Column("mfa_default_method", sa.String(length=64), nullable=True),
            )
        if "mfa_last_verified_at" not in user_columns:
            op.add_column(
                _USERS_TABLE,
                sa.Column(
                    "mfa_last_verified_at",
                    sa.DateTime(timezone=True),
                    nullable=True,
                ),
            )
        if "mfa_recovery_codes_generated_at" not in user_columns:
            op.add_column(
                _USERS_TABLE,
                sa.Column(
                    "mfa_recovery_codes_generated_at",
                    sa.DateTime(timezone=True),
                    nullable=True,
                ),
            )

        if "ix_users_mfa_required" not in user_indexes and "mfa_required" in (
            get_cols(inspector, _USERS_TABLE) if inspector else set()
        ):
            op.create_index("ix_users_mfa_required", _USERS_TABLE, ["mfa_required"])
        if (
            "ix_users_mfa_last_verified_at" not in user_indexes
            and "mfa_last_verified_at"
            in (get_cols(inspector, _USERS_TABLE) if inspector else set())
        ):
            op.create_index(
                "ix_users_mfa_last_verified_at",
                _USERS_TABLE,
                ["mfa_last_verified_at"],
            )
        if (
            "ix_users_mfa_recovery_codes_generated_at" not in user_indexes
            and "mfa_recovery_codes_generated_at"
            in (get_cols(inspector, _USERS_TABLE) if inspector else set())
        ):
            op.create_index(
                "ix_users_mfa_recovery_codes_generated_at",
                _USERS_TABLE,
                ["mfa_recovery_codes_generated_at"],
            )

    if _ACTIVE_SESSIONS_TABLE in tables:
        session_columns = get_cols(inspector, _ACTIVE_SESSIONS_TABLE)
        session_indexes = get_idxs(inspector, _ACTIVE_SESSIONS_TABLE)

        if "mfa_required" not in session_columns:
            op.add_column(
                _ACTIVE_SESSIONS_TABLE,
                sa.Column(
                    "mfa_required",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                ),
            )
            if not is_sqlite:
                op.alter_column(
                    _ACTIVE_SESSIONS_TABLE,
                    "mfa_required",
                    server_default=None,
                )
        if "mfa_completed_at" not in session_columns:
            op.add_column(
                _ACTIVE_SESSIONS_TABLE,
                sa.Column(
                    "mfa_completed_at",
                    sa.DateTime(timezone=True),
                    nullable=True,
                ),
            )
        if "mfa_method" not in session_columns:
            op.add_column(
                _ACTIVE_SESSIONS_TABLE,
                sa.Column("mfa_method", sa.String(length=64), nullable=True),
            )

        if (
            "ix_active_sessions_mfa_required" not in session_indexes
            and "mfa_required"
            in (get_cols(inspector, _ACTIVE_SESSIONS_TABLE) if inspector else set())
        ):
            op.create_index(
                "ix_active_sessions_mfa_required",
                _ACTIVE_SESSIONS_TABLE,
                ["mfa_required"],
            )
        if (
            "ix_active_sessions_mfa_completed_at" not in session_indexes
            and "mfa_completed_at"
            in (get_cols(inspector, _ACTIVE_SESSIONS_TABLE) if inspector else set())
        ):
            op.create_index(
                "ix_active_sessions_mfa_completed_at",
                _ACTIVE_SESSIONS_TABLE,
                ["mfa_completed_at"],
            )

    if inspector:
        tables = _table_names(inspector)
    # else tables remains set from earlier

    if _TOTP_TABLE not in tables:
        op.create_table(
            _TOTP_TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey(f"{_USERS_TABLE}.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("secret", sa.Text(), nullable=False),
            sa.Column("label", sa.String(length=255), nullable=True),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        if not is_sqlite:
            op.alter_column(_TOTP_TABLE, "is_active", server_default=None)
        op.create_index(f"ix_{_TOTP_TABLE}_user_id", _TOTP_TABLE, ["user_id"])
        op.create_index(f"ix_{_TOTP_TABLE}_is_active", _TOTP_TABLE, ["is_active"])
        op.create_index(f"ix_{_TOTP_TABLE}_confirmed_at", _TOTP_TABLE, ["confirmed_at"])
        op.create_index(f"ix_{_TOTP_TABLE}_revoked_at", _TOTP_TABLE, ["revoked_at"])
        op.create_index(
            "ix_mfa_totp_enrollments_active",
            _TOTP_TABLE,
            ["user_id", "is_active"],
        )

    if _WEBAUTHN_TABLE not in tables:
        op.create_table(
            _WEBAUTHN_TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey(f"{_USERS_TABLE}.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "credential_id", sa.String(length=255), nullable=False, unique=True
            ),
            sa.Column("public_key", sa.Text(), nullable=False),
            sa.Column(
                "sign_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column("transports", sa.JSON(), nullable=True),
            sa.Column("device_name", sa.String(length=255), nullable=True),
            sa.Column(
                "backed_up",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column(
                "clone_warning",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
        )
        if not is_sqlite:
            op.alter_column(_WEBAUTHN_TABLE, "sign_count", server_default=None)
            op.alter_column(_WEBAUTHN_TABLE, "backed_up", server_default=None)
            op.alter_column(_WEBAUTHN_TABLE, "clone_warning", server_default=None)
            op.alter_column(_WEBAUTHN_TABLE, "is_active", server_default=None)
        op.create_index(f"ix_{_WEBAUTHN_TABLE}_user_id", _WEBAUTHN_TABLE, ["user_id"])
        op.create_index(
            f"ix_{_WEBAUTHN_TABLE}_is_active", _WEBAUTHN_TABLE, ["is_active"]
        )
        op.create_index(
            f"ix_{_WEBAUTHN_TABLE}_backed_up", _WEBAUTHN_TABLE, ["backed_up"]
        )
        op.create_index(
            f"ix_{_WEBAUTHN_TABLE}_last_used_at", _WEBAUTHN_TABLE, ["last_used_at"]
        )
        op.create_index(
            "ix_mfa_webauthn_user_active",
            _WEBAUTHN_TABLE,
            ["user_id", "is_active"],
        )

    if _RECOVERY_TABLE not in tables:
        op.create_table(
            _RECOVERY_TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey(f"{_USERS_TABLE}.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("code_hash", sa.String(length=255), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("label", sa.String(length=255), nullable=True),
            sa.UniqueConstraint(
                "user_id", "code_hash", name="uq_mfa_recovery_codes_hash"
            ),
        )
        op.create_index(f"ix_{_RECOVERY_TABLE}_user_id", _RECOVERY_TABLE, ["user_id"])
        op.create_index(f"ix_{_RECOVERY_TABLE}_used_at", _RECOVERY_TABLE, ["used_at"])

    if _CHALLENGES_TABLE not in tables:
        op.create_table(
            _CHALLENGES_TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey(f"{_USERS_TABLE}.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "session_id",
                sa.Integer(),
                sa.ForeignKey(f"{_ACTIVE_SESSIONS_TABLE}.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column("challenge_type", sa.String(length=64), nullable=False),
            sa.Column("token", sa.String(length=255), nullable=False, unique=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("payload", sa.JSON(), nullable=True),
        )
        op.create_index(
            f"ix_{_CHALLENGES_TABLE}_user_id", _CHALLENGES_TABLE, ["user_id"]
        )
        op.create_index(
            f"ix_{_CHALLENGES_TABLE}_session_id", _CHALLENGES_TABLE, ["session_id"]
        )
        op.create_index(
            "ix_mfa_challenges_user_expires",
            _CHALLENGES_TABLE,
            ["user_id", "expires_at"],
        )
        op.create_index(
            f"ix_{_CHALLENGES_TABLE}_challenge_type",
            _CHALLENGES_TABLE,
            ["challenge_type"],
        )
        op.create_index(
            f"ix_{_CHALLENGES_TABLE}_expires_at", _CHALLENGES_TABLE, ["expires_at"]
        )
        op.create_index(
            f"ix_{_CHALLENGES_TABLE}_consumed_at", _CHALLENGES_TABLE, ["consumed_at"]
        )


def downgrade() -> None:
    bind = op.get_bind()

    try:
        inspector = sa.inspect(bind)
    except (sa.exc.NoInspectionAvailable, NameError):
        inspector = None

    # Implementation helpers - default to global functions
    get_cols = _column_names
    get_idxs = _index_names

    if inspector is None:
        tables: set[str] = set()  # Skip drop checks in offline mode
        get_idxs = _empty_names
        get_cols = _empty_names
    else:
        tables = _table_names(inspector)

    if _CHALLENGES_TABLE in tables:
        existing_indexes = get_idxs(inspector, _CHALLENGES_TABLE)
        for index_name in [
            f"ix_{_CHALLENGES_TABLE}_consumed_at",
            f"ix_{_CHALLENGES_TABLE}_expires_at",
            "ix_mfa_challenges_user_expires",
            f"ix_{_CHALLENGES_TABLE}_challenge_type",
            f"ix_{_CHALLENGES_TABLE}_session_id",
            f"ix_{_CHALLENGES_TABLE}_user_id",
        ]:
            if index_name in existing_indexes:
                op.drop_index(index_name, table_name=_CHALLENGES_TABLE)
        op.drop_table(_CHALLENGES_TABLE)

    if _RECOVERY_TABLE in tables:
        existing_indexes = get_idxs(inspector, _RECOVERY_TABLE)
        for index_name in [
            f"ix_{_RECOVERY_TABLE}_used_at",
            f"ix_{_RECOVERY_TABLE}_user_id",
        ]:
            if index_name in existing_indexes:
                op.drop_index(index_name, table_name=_RECOVERY_TABLE)
        op.drop_table(_RECOVERY_TABLE)

    if _WEBAUTHN_TABLE in tables:
        existing_indexes = get_idxs(inspector, _WEBAUTHN_TABLE)
        for index_name in [
            "ix_mfa_webauthn_user_active",
            f"ix_{_WEBAUTHN_TABLE}_last_used_at",
            f"ix_{_WEBAUTHN_TABLE}_backed_up",
            f"ix_{_WEBAUTHN_TABLE}_is_active",
            f"ix_{_WEBAUTHN_TABLE}_user_id",
        ]:
            if index_name in existing_indexes:
                op.drop_index(index_name, table_name=_WEBAUTHN_TABLE)
        op.drop_table(_WEBAUTHN_TABLE)

    if _TOTP_TABLE in tables:
        existing_indexes = get_idxs(inspector, _TOTP_TABLE)
        for index_name in [
            "ix_mfa_totp_enrollments_active",
            f"ix_{_TOTP_TABLE}_revoked_at",
            f"ix_{_TOTP_TABLE}_confirmed_at",
            f"ix_{_TOTP_TABLE}_is_active",
            f"ix_{_TOTP_TABLE}_user_id",
        ]:
            if index_name in existing_indexes:
                op.drop_index(index_name, table_name=_TOTP_TABLE)
        op.drop_table(_TOTP_TABLE)

    if inspector:
        tables = _table_names(inspector)
    # else use previous tables (empty or from earlier)

    if _ACTIVE_SESSIONS_TABLE in tables:
        session_indexes = (
            get_idxs(inspector, _ACTIVE_SESSIONS_TABLE) if inspector else set()
        )
        if "ix_active_sessions_mfa_completed_at" in session_indexes:
            op.drop_index(
                "ix_active_sessions_mfa_completed_at",
                table_name=_ACTIVE_SESSIONS_TABLE,
            )
        if "ix_active_sessions_mfa_required" in session_indexes:
            op.drop_index(
                "ix_active_sessions_mfa_required",
                table_name=_ACTIVE_SESSIONS_TABLE,
            )
        session_columns = (
            get_cols(inspector, _ACTIVE_SESSIONS_TABLE) if inspector else set()
        )
        if "mfa_method" in session_columns:
            op.drop_column(_ACTIVE_SESSIONS_TABLE, "mfa_method")
        if "mfa_completed_at" in session_columns:
            op.drop_column(_ACTIVE_SESSIONS_TABLE, "mfa_completed_at")
        if "mfa_required" in session_columns:
            op.drop_column(_ACTIVE_SESSIONS_TABLE, "mfa_required")

    if inspector:
        tables = _table_names(inspector)
    # else keep previous

    if _USERS_TABLE in tables:
        user_indexes = get_idxs(inspector, _USERS_TABLE) if inspector else set()
        if "ix_users_mfa_recovery_codes_generated_at" in user_indexes:
            op.drop_index(
                "ix_users_mfa_recovery_codes_generated_at",
                table_name=_USERS_TABLE,
            )
        if "ix_users_mfa_last_verified_at" in user_indexes:
            op.drop_index("ix_users_mfa_last_verified_at", table_name=_USERS_TABLE)
        if "ix_users_mfa_required" in user_indexes:
            op.drop_index("ix_users_mfa_required", table_name=_USERS_TABLE)
        user_columns = get_cols(inspector, _USERS_TABLE) if inspector else set()
        if "mfa_recovery_codes_generated_at" in user_columns:
            op.drop_column(_USERS_TABLE, "mfa_recovery_codes_generated_at")
        if "mfa_last_verified_at" in user_columns:
            op.drop_column(_USERS_TABLE, "mfa_last_verified_at")
        if "mfa_default_method" in user_columns:
            op.drop_column(_USERS_TABLE, "mfa_default_method")
        if "mfa_required" in user_columns:
            op.drop_column(_USERS_TABLE, "mfa_required")
