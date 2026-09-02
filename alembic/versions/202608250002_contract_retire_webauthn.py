"""Irreversibly retire legacy security-key storage after a locked preflight."""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from alembic import op
from redis.exceptions import RedisError

from app.auth.revocation import calculate_revocation_tombstone_ttl

revision = "202608250002"
down_revision = "202608250001"
branch_labels = None
depends_on = None
downgrade_policy = "irreversible"
downgrade_reason = "MFA security-key retirement is irreversible"

_LOCK_ID = 824_250_002
_REVOCATION_TOMBSTONE_PREFIX = "revoked:jti:"
_SESSION_REVOCATIONS_CHANNEL = "session:revocations"
# ``upgrade`` owns ACCESS EXCLUSIVE locks while it retires the legacy factor.
# A dedicated fail-closed store must therefore never wait on Redis defaults or
# transport retries: each delivery operation gets one bounded attempt.
_REVOCATION_REDIS_CONNECT_TIMEOUT_SECONDS = 1.0
_REVOCATION_REDIS_SOCKET_TIMEOUT_SECONDS = 1.0

# Keep the logical NOT NULL contract while avoiding a table-wide validating
# lock during this destructive migration.  PostgreSQL validates each check in
# a separate pass after the metadata-only ``ADD CONSTRAINT ... NOT VALID``;
# the constraint then rejects future NULL writes just like a NOT NULL column.
_REQUIRED_COLUMNS = (
    ("mfa_challenges", "flow"),
    ("mfa_challenges", "session_identifier"),
    ("mfa_challenges", "client_fingerprint"),
    ("mfa_challenges", "method"),
    ("mfa_challenges", "revision"),
    ("mfa_challenges", "token_digest"),
    ("mfa_challenges", "token_key_id"),
    ("trusted_devices", "token_key_id"),
    ("trusted_devices", "binding_digest"),
)


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
    if "active_sessions" in _tables(bind):
        session_columns = _columns(bind, "active_sessions")
        if {"user_id", "mfa_method"}.issubset(session_columns):
            session = sa.table(
                "active_sessions",
                sa.column("user_id"),
                sa.column("mfa_method"),
                *(
                    (sa.column("revoked_at"),)
                    if "revoked_at" in session_columns
                    else ()
                ),
            )
            predicates = [
                sa.func.lower(sa.func.coalesce(session.c.mfa_method, "")) == "webauthn"
            ]
            if "revoked_at" in session_columns:
                predicates.append(session.c.revoked_at.is_(None))
            # A legacy table without ``revoked_at`` cannot prove that a
            # WebAuthn-marked session is inactive.  Include it for safe
            # remediation rather than preserving a potentially valid bearer.
            ids.update(
                str(row[0])
                for row in bind.execute(
                    sa.select(session.c.user_id).where(*predicates).distinct()
                )
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


def _requires_persistent_session_revocation(bind: Any) -> bool:
    """Production bearer retirement needs live delivery, unlike SQLite fixtures."""
    return bind.dialect.name == "postgresql"


def _active_session_revocations(
    bind: Any,
    user_id: str,
) -> list[tuple[str, datetime]]:
    """Collect still-live bearer IDs without changing local database state."""
    if not _requires_persistent_session_revocation(bind):
        return []
    if "active_sessions" not in _tables(bind):
        return []

    columns = _columns(bind, "active_sessions")
    bound_user_id = _coerce_user_id(bind, user_id)
    required_columns = {"user_id", "jti", "expires_at"}
    if not required_columns.issubset(columns):
        probe = sa.table(
            "active_sessions",
            sa.column("user_id"),
            *(sa.column("revoked_at"),) if "revoked_at" in columns else (),
        )
        predicates = [probe.c.user_id == bound_user_id]
        if "revoked_at" in columns:
            predicates.append(probe.c.revoked_at.is_(None))
        if (
            bind.execute(
                sa.select(sa.literal(1)).select_from(probe).where(*predicates).limit(1)
            ).first()
            is not None
        ):
            raise MfaMigrationSafetyError(
                "Unsafe MFA retirement: active session tombstone fields are unavailable"
            )
        return []

    session = sa.table(
        "active_sessions",
        sa.column("user_id"),
        sa.column("jti"),
        sa.column("expires_at", sa.DateTime(timezone=True)),
        *(sa.column("revoked_at"),) if "revoked_at" in columns else (),
    )
    predicates = [session.c.user_id == bound_user_id]
    if "revoked_at" in columns:
        predicates.append(session.c.revoked_at.is_(None))

    revocations: list[tuple[str, datetime]] = []
    seen_jtis: set[str] = set()
    for jti, expires_at in bind.execute(
        sa.select(session.c.jti, session.c.expires_at).where(*predicates)
    ):
        if (
            not isinstance(jti, str)
            or not jti.strip()
            or not isinstance(expires_at, datetime)
        ):
            raise MfaMigrationSafetyError(
                "Unsafe MFA retirement: active session revocation data is invalid"
            )
        try:
            # The revocation key and pub/sub payload must have one canonical
            # byte representation.  Otherwise semantically equivalent UUID
            # spellings could create different tombstones and allow a bearer
            # whose verifier uses a different spelling to escape revocation.
            if str(uuid.UUID(jti)) != jti:
                raise ValueError("non-canonical UUID")
        except ValueError as exc:
            raise MfaMigrationSafetyError(
                "Unsafe MFA retirement: active session revocation data is invalid"
            ) from exc
        if jti not in seen_jtis:
            seen_jtis.add(jti)
            revocations.append((jti, expires_at))
    return revocations


def _get_migration_revocation_redis_client(url: str) -> Any:
    """Create the synchronous dedicated Redis client used only by this hook."""
    from redis import Redis
    from redis.backoff import NoBackoff
    from redis.retry import Retry

    return Redis.from_url(
        url,
        decode_responses=True,
        socket_connect_timeout=_REVOCATION_REDIS_CONNECT_TIMEOUT_SECONDS,
        socket_timeout=_REVOCATION_REDIS_SOCKET_TIMEOUT_SECONDS,
        retry=Retry(NoBackoff(), retries=0),
        retry_on_timeout=False,
    )


def _publish_session_revocations(
    revocations: list[tuple[str, datetime]],
) -> None:
    """Durably deny then broadcast every retired bearer before DB mutation."""
    if not revocations:
        return

    redis_url = os.environ.get("REVOCATION_REDIS_URL", "").strip()
    if not redis_url:
        raise MfaMigrationSafetyError(
            "Unsafe MFA retirement: session revocation delivery is unavailable"
        )

    client: Any | None = None
    try:
        client = _get_migration_revocation_redis_client(redis_url)
        if client.ping() is not True:
            raise MfaMigrationSafetyError(
                "Unsafe MFA retirement: session revocation delivery failed"
            )
        for jti, expires_at in revocations:
            written = client.set(
                f"{_REVOCATION_TOMBSTONE_PREFIX}{jti}",
                "1",
                ex=calculate_revocation_tombstone_ttl(expires_at),
            )
            if written is not True:
                raise MfaMigrationSafetyError(
                    "Unsafe MFA retirement: session revocation delivery failed"
                )
        for jti, _expires_at in revocations:
            client.publish(_SESSION_REVOCATIONS_CHANNEL, jti)
    except (OSError, RedisError, ValueError):
        raise MfaMigrationSafetyError(
            "Unsafe MFA retirement: session revocation delivery failed"
        ) from None
    finally:
        if client is not None:
            try:
                client.close()
            except (OSError, RedisError):
                # Delivery already completed; a client-close failure cannot
                # resurrect a tombstoned bearer and must not leak a secret URL.
                pass


def _invalidate_legacy_auth_state(bind: Any, user_id: str) -> None:
    """Apply the local half after ``_publish_session_revocations`` succeeds."""
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
    remediations: list[tuple[str, str]] = []
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
            remediations.append((user_id, "totp"))
        elif row[0] is not None:
            result["email_otp"] += 1
            remediations.append((user_id, "email_otp"))
        else:
            result["unresolved"] += 1
            unresolved.append(hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:12])
    if unresolved:
        raise MfaMigrationSafetyError(
            "Unsafe MFA retirement: "
            f"unresolved_count={len(unresolved)} refs={','.join(unresolved)}; "
            "set email_verified_at, enroll TOTP, or provision a verified factor. "
            "Unused recovery rows alone are not a usable login path."
        )

    revocations_by_user = {
        user_id: _active_session_revocations(bind, user_id)
        for user_id, _method in remediations
    }
    _publish_session_revocations(
        [
            revocation
            for user_id, _method in remediations
            for revocation in revocations_by_user[user_id]
        ]
    )

    for user_id, method in remediations:
        bound_user_id = _coerce_user_id(bind, user_id)
        _invalidate_legacy_auth_state(bind, user_id)
        if method == "totp":
            bind.execute(
                sa.text(
                    "UPDATE users SET mfa_default_method='totp', mfa_required=true "
                    "WHERE id=:user_id"
                ),
                {"user_id": bound_user_id},
            )
        else:
            bind.execute(
                sa.text(
                    "UPDATE users SET mfa_default_method='email_otp', "
                    "email_mfa_enabled_at=CURRENT_TIMESTAMP, mfa_required=true "
                    "WHERE id=:user_id"
                ),
                {"user_id": bound_user_id},
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


def _enforce_required_columns(bind: Any) -> None:
    """Enforce required fields without a blocking PostgreSQL table scan.

    PostgreSQL's direct ``ALTER COLUMN ... SET NOT NULL`` takes an
    ``ACCESS EXCLUSIVE`` lock while scanning the full table.  A validated
    ``CHECK (column IS NOT NULL)`` has the same write-time semantics, while
    ``NOT VALID`` lets the constraint be attached quickly and ``VALIDATE``
    performs the scan under a weaker lock.  The non-PostgreSQL branch keeps
    the existing SQLite development behavior, where PostgreSQL's ``NOT VALID``
    and ``VALIDATE CONSTRAINT`` syntax is unavailable.
    """

    if bind.dialect.name != "postgresql":
        for table, column in _REQUIRED_COLUMNS:
            op.alter_column(table, column, nullable=False)
        return

    for table, column in _REQUIRED_COLUMNS:
        constraint_name = f"ck_{table}_{column}_not_null"
        op.create_check_constraint(
            constraint_name,
            table,
            f"{column} IS NOT NULL",
            postgresql_not_valid=True,
        )
        op.execute(
            sa.text(f"ALTER TABLE {table} VALIDATE CONSTRAINT {constraint_name}")
        )


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
    _enforce_required_columns(bind)
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
        # Use Alembic operations rather than ``exec_driver_sql`` so the same
        # lock guards render through the offline MockConnection used by CI.
        op.execute(sa.text("SET LOCAL lock_timeout = '10s'"))
        op.execute(
            sa.text("SELECT pg_advisory_xact_lock(:lock_id)").bindparams(
                sa.bindparam("lock_id", value=_LOCK_ID, literal_execute=True)
            )
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
        if lock_tables:
            lock_sql = (
                "LOCK TABLE " + ", ".join(lock_tables) + " IN ACCESS EXCLUSIVE MODE"
            )
            op.execute(sa.text(lock_sql))
    _contract_body(bind)


def downgrade() -> None:
    raise RuntimeError(downgrade_reason)
