from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    path = ROOT / "alembic" / "versions" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _legacy_database() -> tuple[sa.Engine, sa.Connection]:
    engine = sa.create_engine("sqlite://")
    conn = engine.connect()
    conn.exec_driver_sql(
        "CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT NOT NULL, "
        "email_verified_at DATETIME, email_mfa_enabled_at DATETIME, "
        "mfa_default_method TEXT, mfa_required BOOLEAN)"
    )
    conn.exec_driver_sql(
        "CREATE TABLE mfa_totp_enrollments (id TEXT, user_id TEXT, is_active BOOLEAN, "
        "confirmed_at DATETIME, revoked_at DATETIME)"
    )
    conn.exec_driver_sql("CREATE TABLE webauthn_credentials (id TEXT, user_id TEXT)")
    conn.exec_driver_sql(
        "CREATE TABLE recovery_codes (id TEXT, user_id TEXT, is_used BOOLEAN)"
    )
    return engine, conn


def test_preflight_classifies_totp_and_verified_email_paths() -> None:
    contract = _load("202608250002_contract_retire_webauthn.py")
    engine, conn = _legacy_database()
    try:
        conn.exec_driver_sql(
            "INSERT INTO users VALUES "
            "('totp-user','t@example.test',NULL,NULL,'webauthn',1),"
            "('email-user','e@example.test','2026-08-01',NULL,'webauthn',1)"
        )
        conn.exec_driver_sql(
            "INSERT INTO mfa_totp_enrollments VALUES "
            "('t','totp-user',1,'2026-08-01',NULL)"
        )
        conn.exec_driver_sql(
            "INSERT INTO webauthn_credentials VALUES "
            "('w1','totp-user'),('w2','email-user')"
        )
        conn.exec_driver_sql(
            "ALTER TABLE users ADD COLUMN mfa_epoch INTEGER NOT NULL DEFAULT 0"
        )
        conn.exec_driver_sql(
            "CREATE TABLE active_sessions (id TEXT, user_id TEXT, revoked_at DATETIME, "
            "mfa_method TEXT, mfa_verified_at DATETIME, mfa_completed_at DATETIME)"
        )
        conn.exec_driver_sql(
            "INSERT INTO active_sessions VALUES "
            "('s1','totp-user',NULL,'webauthn','2026-08-01','2026-08-01'),"
            "('s2','email-user',NULL,'webauthn','2026-08-01','2026-08-01')"
        )
        result = contract.run_preflight(conn)
        assert result == {
            "totp": 1,
            "email_otp": 1,
            "recovery_path": 0,
            "unresolved": 0,
        }
        assert (
            conn.exec_driver_sql("SELECT min(mfa_epoch) FROM users").scalar_one() == 1
        )
        session_rows = conn.exec_driver_sql(
            "SELECT revoked_at, mfa_method, mfa_verified_at, mfa_completed_at "
            "FROM active_sessions"
        ).all()
        assert all(
            row[0] is not None and row[1:] == (None, None, None) for row in session_rows
        )
    finally:
        conn.close()
        engine.dispose()


def test_preflight_aborts_with_non_pii_actionable_diagnostics() -> None:
    contract = _load("202608250002_contract_retire_webauthn.py")
    engine, conn = _legacy_database()
    try:
        conn.exec_driver_sql(
            "INSERT INTO users VALUES "
            "('unsafe-user','secret@example.test',NULL,NULL,'webauthn',1)"
        )
        conn.exec_driver_sql(
            "INSERT INTO webauthn_credentials VALUES ('w','unsafe-user')"
        )
        with pytest.raises(contract.MfaMigrationSafetyError) as exc_info:
            contract.run_preflight(conn)
        message = str(exc_info.value)
        assert "unresolved_count=1" in message
        assert "secret@example.test" not in message
        assert (
            "set email_verified_at, enroll TOTP, or provision a verified factor"
            in message
        )
    finally:
        conn.close()
        engine.dispose()


def test_expansion_remediation_marks_only_explicitly_verified_email() -> None:
    expansion = _load("202608250001_expand_email_otp_mfa.py")
    engine, conn = _legacy_database()
    try:
        conn.exec_driver_sql(
            "INSERT INTO users VALUES ('user-1','one@example.test',NULL,NULL,NULL,0)"
        )
        verified_at = datetime(2026, 8, 25, tzinfo=UTC)
        expansion.remediate_verified_email(
            conn, user_id="user-1", verified_at=verified_at
        )
        value = conn.exec_driver_sql(
            "SELECT email_verified_at FROM users WHERE id='user-1'"
        ).scalar_one()
        assert value is not None
        with pytest.raises(ValueError):
            expansion.remediate_verified_email(conn, user_id="user-1", verified_at=None)
    finally:
        conn.close()
        engine.dispose()


def test_contract_downgrade_is_explicitly_irreversible() -> None:
    contract = _load("202608250002_contract_retire_webauthn.py")
    with pytest.raises(RuntimeError, match="irreversible"):
        contract.downgrade()


def test_expansion_downgrade_is_explicitly_irreversible() -> None:
    expansion = _load("202608250001_expand_email_otp_mfa.py")
    with pytest.raises(RuntimeError, match="irreversible"):
        expansion.downgrade()


def test_recipient_digest_is_added_only_to_mfa_challenges() -> None:
    source = (
        ROOT / "alembic" / "versions" / "202608250001_expand_email_otp_mfa.py"
    ).read_text(encoding="utf-8")
    trusted_section, challenge_section = source.split("challenge_columns =", 1)
    assert "recipient_digest" not in trusted_section
    assert 'sa.Column("recipient_digest"' in challenge_section


def test_expansion_adds_nullable_totp_timecode_for_online_compatibility() -> None:
    source = (
        ROOT / "alembic" / "versions" / "202608250001_expand_email_otp_mfa.py"
    ).read_text(encoding="utf-8")
    assert '"mfa_totp_enrollments"' in source
    assert 'sa.Column("last_used_timecode", sa.BigInteger(), nullable=True)' in source


def test_expansion_renders_postgresql_offline_sql_with_lock_guards() -> None:
    """Alembic's offline MockConnection must render, not execute, lock guards."""

    env = os.environ.copy()
    env["DATABASE_URL"] = "postgresql+asyncpg://migration@localhost:5432/test"
    result = subprocess.run(  # noqa: S603 - fixed local Alembic module invocation
        [
            sys.executable,
            "-m",
            "alembic",
            "upgrade",
            "202607280001:202608250001",
            "--sql",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    sql = result.stdout.upper()
    normalized_sql = " ".join(sql.split())
    assert "SET LOCAL LOCK_TIMEOUT = '10S';" in sql
    assert "SELECT PG_ADVISORY_XACT_LOCK(824250001);" in sql
    assert (
        "LOCK TABLE USERS, ACTIVE_SESSIONS, TRUSTED_DEVICES, MFA_CHALLENGES "
        "IN SHARE ROW EXCLUSIVE MODE;"
    ) in sql
    assert "ALTER TABLE MFA_CHALLENGES ALTER COLUMN TOKEN DROP NOT NULL;" not in sql
    assert "CREATE SEQUENCE IF NOT EXISTS MFA_CHALLENGES_DIGEST_TOKEN_SEQ;" in sql
    assert (
        "ALTER SEQUENCE MFA_CHALLENGES_DIGEST_TOKEN_SEQ OWNED BY MFA_CHALLENGES.TOKEN;"
    ) in normalized_sql
    assert (
        "ALTER TABLE MFA_CHALLENGES ALTER COLUMN TOKEN SET DEFAULT "
        "'__MFA_DIGEST_ONLY__:' || NEXTVAL('MFA_CHALLENGES_DIGEST_TOKEN_SEQ')::TEXT;"
    ) in normalized_sql
    assert (
        "TOKEN='__MFA_DIGEST_ONLY__:' || "
        "NEXTVAL('MFA_CHALLENGES_DIGEST_TOKEN_SEQ') WHERE TOKEN_DIGEST IS NULL;"
    ) in normalized_sql
    assert "TOKEN=NULL WHERE TOKEN_DIGEST IS NULL;" not in normalized_sql


def test_contract_renders_postgresql_offline_sql_with_lock_guards() -> None:
    """The irreversible contract migration must render under Alembic offline mode."""

    env = os.environ.copy()
    env["DATABASE_URL"] = "postgresql+asyncpg://migration@localhost:5432/test"
    result = subprocess.run(  # noqa: S603 - fixed local Alembic module invocation
        [
            sys.executable,
            "-m",
            "alembic",
            "upgrade",
            "202608250001:202608250002",
            "--sql",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    sql = " ".join(result.stdout.upper().split())
    assert "SET LOCAL LOCK_TIMEOUT = '10S';" in sql
    assert "SELECT PG_ADVISORY_XACT_LOCK(824250002);" in sql
    assert "LOCK TABLE  IN ACCESS EXCLUSIVE MODE" not in sql
    assert " SET NOT NULL;" not in sql
    required_columns = (
        ("MFA_CHALLENGES", "FLOW"),
        ("MFA_CHALLENGES", "SESSION_IDENTIFIER"),
        ("MFA_CHALLENGES", "CLIENT_FINGERPRINT"),
        ("MFA_CHALLENGES", "METHOD"),
        ("MFA_CHALLENGES", "REVISION"),
        ("MFA_CHALLENGES", "TOKEN_DIGEST"),
        ("MFA_CHALLENGES", "TOKEN_KEY_ID"),
        ("TRUSTED_DEVICES", "TOKEN_KEY_ID"),
        ("TRUSTED_DEVICES", "BINDING_DIGEST"),
    )
    for table, column in required_columns:
        constraint_name = f"CK_{table}_{column}_NOT_NULL"
        assert (
            f"ADD CONSTRAINT {constraint_name} CHECK ({column} IS NOT NULL) NOT VALID;"
        ) in sql
        assert (f"ALTER TABLE {table} VALIDATE CONSTRAINT {constraint_name};") in sql


def test_contract_coerces_postgres_user_ids_to_uuid() -> None:
    contract = _load("202608250002_contract_retire_webauthn.py")
    bind = type(
        "Bind", (), {"dialect": type("Dialect", (), {"name": "postgresql"})()}
    )()
    value = "12345678-1234-5678-1234-567812345678"
    assert contract._coerce_user_id(bind, value) == uuid.UUID(value)


def test_unused_recovery_row_is_not_misclassified_as_a_usable_path() -> None:
    contract = _load("202608250002_contract_retire_webauthn.py")
    engine, conn = _legacy_database()
    try:
        conn.exec_driver_sql(
            "INSERT INTO users VALUES "
            "('recovery-only','r@example.test',NULL,NULL,'webauthn',1)"
        )
        conn.exec_driver_sql(
            "INSERT INTO webauthn_credentials VALUES ('w','recovery-only')"
        )
        conn.exec_driver_sql(
            "INSERT INTO recovery_codes VALUES ('r','recovery-only',0)"
        )
        with pytest.raises(contract.MfaMigrationSafetyError, match="Unused recovery"):
            contract.run_preflight(conn)
    finally:
        conn.close()
        engine.dispose()
