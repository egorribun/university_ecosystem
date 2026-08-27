"""Irreversibly retire legacy security-key storage after a locked preflight."""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "202608250002"
down_revision = "202608250001"
branch_labels = None
depends_on = None
downgrade_policy = "irreversible"
downgrade_reason = "MFA security-key retirement is irreversible"

_LOCK_ID = 824_250_002


class MfaMigrationSafetyError(RuntimeError):
    pass


def _tables(bind: Any) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def _columns(bind: Any, table: str) -> set[str]:
    return {item["name"] for item in sa.inspect(bind).get_columns(table)}


def _legacy_user_ids(bind: Any) -> set[str]:
    ids = {
        str(row[0])
        for row in bind.execute(
            sa.text(
                "SELECT id FROM users WHERE lower(coalesce(mfa_default_method, '')) = 'webauthn'"
            )
        )
    }
    for table in ("webauthn_credentials", "mfa_webauthn_credentials"):
        if table in _tables(bind):
            legacy_table = sa.table(table, sa.column("user_id"))
            ids.update(
                str(row[0])
                for row in bind.execute(sa.select(legacy_table.c.user_id).distinct())
            )
    return ids


def _has_confirmed_totp(bind: Any, user_id: str) -> bool:
    if "mfa_totp_enrollments" not in _tables(bind):
        return False
    columns = _columns(bind, "mfa_totp_enrollments")
    enrollment = sa.table(
        "mfa_totp_enrollments",
        sa.column("user_id"),
        sa.column("confirmed_at"),
        sa.column("is_active"),
        sa.column("revoked_at"),
    )
    predicates = [enrollment.c.user_id == _coerce_user_id(bind, user_id)]
    if "confirmed_at" in columns:
        predicates.append(enrollment.c.confirmed_at.is_not(None))
    else:
        return False
    if "is_active" in columns:
        predicates.append(enrollment.c.is_active.is_(True))
    if "revoked_at" in columns:
        predicates.append(enrollment.c.revoked_at.is_(None))
    query = sa.select(sa.literal(1)).select_from(enrollment).where(*predicates).limit(1)
    return bind.execute(query).first() is not None


def _coerce_user_id(bind: Any, user_id: str) -> str | uuid.UUID:
    if bind.dialect.name == "postgresql":
        return uuid.UUID(user_id)
    return user_id


def _invalidate_legacy_auth_state(bind: Any, user_id: str) -> None:
    bound_user_id = _coerce_user_id(bind, user_id)
    if "mfa_epoch" in _columns(bind, "users"):
        bind.execute(
            sa.text(
                "UPDATE users SET mfa_epoch=coalesce(mfa_epoch, 0) + 1 "
                "WHERE id=:user_id"
            ),
            {"user_id": bound_user_id},
        )
    if "active_sessions" not in _tables(bind):
        return
    columns = _columns(bind, "active_sessions")
    values: dict[str, Any] = {}
    if "revoked_at" in columns:
        values["revoked_at"] = sa.func.current_timestamp()
    for column in ("mfa_method", "mfa_verified_at", "mfa_completed_at"):
        if column in columns:
            values[column] = None
    if values:
        sessions = sa.table(
            "active_sessions",
            sa.column("user_id"),
            *(sa.column(column) for column in values),
        )
        bind.execute(
            sessions.update()
            .where(sessions.c.user_id == bound_user_id)
            .values(**values)
        )


def run_preflight(bind: Any) -> dict[str, int]:
    """Classify under caller-held table locks and apply only safe remaps."""
    result = {"totp": 0, "email_otp": 0, "recovery_path": 0, "unresolved": 0}
    unresolved: list[str] = []
    for user_id in sorted(_legacy_user_ids(bind)):
        bound_user_id = _coerce_user_id(bind, user_id)
        row = bind.execute(
            sa.text("SELECT email_verified_at FROM users WHERE id = :user_id"),
            {"user_id": bound_user_id},
        ).first()
        if row is None:
            continue
        if _has_confirmed_totp(bind, user_id):
            result["totp"] += 1
            bind.execute(
                sa.text(
                    "UPDATE users SET mfa_default_method='totp', mfa_required=true "
                    "WHERE id=:user_id"
                ),
                {"user_id": bound_user_id},
            )
        elif row[0] is not None:
            result["email_otp"] += 1
            bind.execute(
                sa.text(
                    "UPDATE users SET mfa_default_method='email_otp', "
                    "email_mfa_enabled_at=CURRENT_TIMESTAMP, mfa_required=true "
                    "WHERE id=:user_id"
                ),
                {"user_id": bound_user_id},
            )
        else:
            result["unresolved"] += 1
            unresolved.append(hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:12])
            continue
        _invalidate_legacy_auth_state(bind, user_id)
    if unresolved:
        raise MfaMigrationSafetyError(
            "Unsafe MFA retirement: "
            f"unresolved_count={len(unresolved)} refs={','.join(unresolved)}; "
            "set email_verified_at, enroll TOTP, or provision a verified factor. "
            "Unused recovery rows alone are not a usable login path."
        )
    return result


def _drop_column_constraints(bind: Any, table: str, column: str) -> None:
    inspector = sa.inspect(bind)
    for constraint in inspector.get_unique_constraints(table):
        if column in constraint.get("column_names", []):
            op.drop_constraint(constraint["name"], table, type_="unique")
    for index in inspector.get_indexes(table):
        if column in index.get("column_names", []):
            op.drop_index(index["name"], table_name=table)


def _contract_body(bind: Any) -> None:
    run_preflight(bind)
    # Remove only legacy rows. Digest-bound challenges created during the
    # expand/contract deployment interval remain valid.
    bind.execute(
        sa.text(
            "DELETE FROM mfa_challenges WHERE token_digest IS NULL "
            "OR flow IS NULL OR method IS NULL "
            "OR (method='email_otp' AND recipient_digest IS NULL)"
        )
    )
    bind.execute(
        sa.text(
            "DELETE FROM trusted_devices WHERE token_key_id IS NULL "
            "OR binding_digest IS NULL"
        )
    )
    tables = _tables(bind)
    for table in ("webauthn_credentials", "mfa_webauthn_credentials"):
        if table in tables:
            op.drop_table(table)
    if "webauthn_id" in _columns(bind, "users"):
        _drop_column_constraints(bind, "users", "webauthn_id")
        op.drop_column("users", "webauthn_id")
    if "token" in _columns(bind, "mfa_challenges"):
        _drop_column_constraints(bind, "mfa_challenges", "token")
        op.drop_column("mfa_challenges", "token")
    for column in (
        "flow",
        "session_identifier",
        "client_fingerprint",
        "method",
        "revision",
        "token_digest",
        "token_key_id",
    ):
        op.alter_column("mfa_challenges", column, nullable=False)
    op.alter_column("trusted_devices", "token_key_id", nullable=False)
    op.alter_column("trusted_devices", "binding_digest", nullable=False)
    op.create_check_constraint(
        "ck_mfa_challenges_email_recipient_digest",
        "mfa_challenges",
        "method != 'email_otp' OR recipient_digest IS NOT NULL",
    )
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("mfa_challenges")}
    if "ix_mfa_challenges_binding" not in indexes:
        op.create_index(
            "ix_mfa_challenges_binding",
            "mfa_challenges",
            ["user_id", "flow", "session_identifier", "method"],
        )
    if "ix_mfa_challenges_token_digest" not in indexes:
        op.create_index(
            "ix_mfa_challenges_token_digest",
            "mfa_challenges",
            ["token_digest"],
            unique=True,
        )


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    if is_postgres:
        bind.exec_driver_sql("SET LOCAL lock_timeout = '10s'")
        bind.execute(
            sa.text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": _LOCK_ID}
        )
        lock_tables = [
            table
            for table in (
                "users",
                "mfa_totp_enrollments",
                "recovery_codes",
                "mfa_challenges",
                "active_sessions",
                "trusted_devices",
                "webauthn_credentials",
                "mfa_webauthn_credentials",
            )
            if table in _tables(bind)
        ]
        bind.exec_driver_sql(
            "LOCK TABLE " + ", ".join(lock_tables) + " IN ACCESS EXCLUSIVE MODE"
        )
    _contract_body(bind)


def downgrade() -> None:
    raise RuntimeError(downgrade_reason)
