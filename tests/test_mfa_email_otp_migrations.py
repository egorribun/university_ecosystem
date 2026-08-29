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
from redis import Redis
from redis.backoff import NoBackoff
from redis.retry import Retry

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


def test_preflight_revokes_session_only_webauthn_legacy_state() -> None:
    """An active legacy session must not survive just because the user was remapped."""

    contract = _load("202608250002_contract_retire_webauthn.py")
    engine, conn = _legacy_database()
    try:
        conn.exec_driver_sql(
            "INSERT INTO users VALUES "
            "('session-only','s@example.test',NULL,NULL,'totp',1)"
        )
        conn.exec_driver_sql(
            "INSERT INTO mfa_totp_enrollments VALUES "
            "('t','session-only',1,'2026-08-01',NULL)"
        )
        conn.exec_driver_sql(
            "ALTER TABLE users ADD COLUMN mfa_epoch INTEGER NOT NULL DEFAULT 0"
        )
        conn.exec_driver_sql(
            "CREATE TABLE active_sessions (id TEXT, user_id TEXT, revoked_at DATETIME, "
            "mfa_method TEXT, mfa_verified_at DATETIME, mfa_completed_at DATETIME, "
            "mfa_epoch INTEGER NOT NULL DEFAULT 0)"
        )
        conn.exec_driver_sql(
            "INSERT INTO active_sessions "
            "VALUES ('s1','session-only',NULL,'webauthn','2026-08-01','2026-08-01',0)"
        )

        result = contract.run_preflight(conn)

        assert result == {
            "totp": 1,
            "email_otp": 0,
            "recovery_path": 0,
            "unresolved": 0,
        }
        assert (
            conn.exec_driver_sql(
                "SELECT mfa_epoch FROM users WHERE id='session-only'"
            ).scalar_one()
            == 1
        )
        session = conn.exec_driver_sql(
            "SELECT revoked_at, mfa_method, mfa_verified_at, mfa_completed_at "
            "FROM active_sessions WHERE id='s1'"
        ).one()
        assert session[0] is not None
        assert session[1:] == (None, None, None)
    finally:
        conn.close()
        engine.dispose()


def test_preflight_blocks_unsafe_session_only_webauthn_legacy_state() -> None:
    """A legacy session cannot be treated as a valid replacement MFA factor."""

    contract = _load("202608250002_contract_retire_webauthn.py")
    engine, conn = _legacy_database()
    try:
        conn.exec_driver_sql(
            "INSERT INTO users VALUES "
            "('unsafe-session','u@example.test',NULL,NULL,'totp',1)"
        )
        conn.exec_driver_sql(
            "CREATE TABLE active_sessions (id TEXT, user_id TEXT, revoked_at DATETIME, "
            "mfa_method TEXT, mfa_verified_at DATETIME, mfa_completed_at DATETIME)"
        )
        conn.exec_driver_sql(
            "INSERT INTO active_sessions "
            "VALUES ('s1','unsafe-session',NULL,'webauthn','2026-08-01','2026-08-01')"
        )

        with pytest.raises(
            contract.MfaMigrationSafetyError, match="unresolved_count=1"
        ):
            contract.run_preflight(conn)
    finally:
        conn.close()
        engine.dispose()


def test_preflight_does_not_mutate_safe_users_when_any_legacy_user_is_unresolved() -> (
    None
):
    """All legacy-factor remediation must pass before any local mutation starts."""

    contract = _load("202608250002_contract_retire_webauthn.py")
    engine, conn = _legacy_database()
    try:
        conn.exec_driver_sql(
            "INSERT INTO users VALUES "
            "('a-safe','safe@example.test',NULL,NULL,'webauthn',1),"
            "('z-unsafe','unsafe@example.test',NULL,NULL,'webauthn',1)"
        )
        conn.exec_driver_sql(
            "INSERT INTO mfa_totp_enrollments VALUES ('t','a-safe',1,'2026-08-01',NULL)"
        )
        conn.exec_driver_sql(
            "ALTER TABLE users ADD COLUMN mfa_epoch INTEGER NOT NULL DEFAULT 0"
        )

        with pytest.raises(
            contract.MfaMigrationSafetyError, match="unresolved_count=1"
        ):
            contract.run_preflight(conn)

        assert conn.exec_driver_sql(
            "SELECT mfa_default_method, mfa_epoch FROM users WHERE id='a-safe'"
        ).one() == ("webauthn", 0)
    finally:
        conn.close()
        engine.dispose()


def test_preflight_ignores_revoked_webauthn_sessions() -> None:
    """Only sessions that could still authenticate may trigger retirement remediation."""

    contract = _load("202608250002_contract_retire_webauthn.py")
    engine, conn = _legacy_database()
    try:
        conn.exec_driver_sql(
            "INSERT INTO users VALUES "
            "('revoked-session','r@example.test',NULL,NULL,'totp',1)"
        )
        conn.exec_driver_sql(
            "CREATE TABLE active_sessions (id TEXT, user_id TEXT, revoked_at DATETIME, "
            "mfa_method TEXT, mfa_verified_at DATETIME, mfa_completed_at DATETIME)"
        )
        conn.exec_driver_sql(
            "INSERT INTO active_sessions "
            "VALUES ('s1','revoked-session','2026-08-02','webauthn',"
            "'2026-08-01','2026-08-01')"
        )

        assert contract.run_preflight(conn) == {
            "totp": 0,
            "email_otp": 0,
            "recovery_path": 0,
            "unresolved": 0,
        }
    finally:
        conn.close()
        engine.dispose()


def test_preflight_fails_closed_when_session_revocation_state_is_unavailable() -> None:
    """The historical fallback must invalidate the epoch when it cannot revoke a row."""

    contract = _load("202608250002_contract_retire_webauthn.py")
    engine, conn = _legacy_database()
    try:
        conn.exec_driver_sql(
            "INSERT INTO users VALUES "
            "('no-revocation-column','n@example.test',NULL,NULL,'totp',1)"
        )
        conn.exec_driver_sql(
            "INSERT INTO mfa_totp_enrollments VALUES "
            "('t','no-revocation-column',1,'2026-08-01',NULL)"
        )
        conn.exec_driver_sql(
            "ALTER TABLE users ADD COLUMN mfa_epoch INTEGER NOT NULL DEFAULT 0"
        )
        conn.exec_driver_sql(
            "CREATE TABLE active_sessions (id TEXT, user_id TEXT, mfa_method TEXT, "
            "mfa_verified_at DATETIME, mfa_completed_at DATETIME, "
            "mfa_epoch INTEGER NOT NULL DEFAULT 0)"
        )
        conn.exec_driver_sql(
            "INSERT INTO active_sessions "
            "VALUES ('s1','no-revocation-column','webauthn','2026-08-01',"
            "'2026-08-01',0)"
        )

        assert contract.run_preflight(conn)["totp"] == 1
        assert (
            conn.exec_driver_sql(
                "SELECT mfa_epoch FROM users WHERE id='no-revocation-column'"
            ).scalar_one()
            == 1
        )
        assert conn.exec_driver_sql(
            "SELECT mfa_epoch, mfa_method, mfa_verified_at, mfa_completed_at "
            "FROM active_sessions WHERE id='s1'"
        ).one() == (0, None, None, None)
    finally:
        conn.close()
        engine.dispose()


def test_preflight_rejects_noncanonical_live_session_jti_without_redis_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Equivalent UUID spellings cannot form a second revocation key."""

    contract = _load("202608250002_contract_retire_webauthn.py")
    engine, conn = _legacy_database()
    redis_called = False

    def unexpected_redis_client(_url: str) -> object:
        nonlocal redis_called
        redis_called = True
        return object()

    monkeypatch.setenv("REVOCATION_REDIS_URL", "redis://revocation.test:6379/0")
    monkeypatch.setattr(
        contract,
        "_get_migration_revocation_redis_client",
        unexpected_redis_client,
        raising=False,
    )
    monkeypatch.setattr(
        contract,
        "_requires_persistent_session_revocation",
        lambda _bind: True,
        raising=False,
    )
    try:
        conn.exec_driver_sql(
            "INSERT INTO users VALUES "
            "('canonical-user','canonical@example.test',NULL,NULL,'webauthn',1)"
        )
        conn.exec_driver_sql(
            "INSERT INTO mfa_totp_enrollments VALUES "
            "('totp','canonical-user',1,'2026-08-01',NULL)"
        )
        conn.exec_driver_sql(
            "ALTER TABLE users ADD COLUMN mfa_epoch INTEGER NOT NULL DEFAULT 0"
        )
        conn.exec_driver_sql(
            "CREATE TABLE active_sessions (id TEXT, user_id TEXT, jti TEXT, "
            "expires_at DATETIME, revoked_at DATETIME, mfa_method TEXT, "
            "mfa_verified_at DATETIME, mfa_completed_at DATETIME)"
        )
        noncanonical_jti = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa".upper()
        conn.exec_driver_sql(
            "INSERT INTO active_sessions VALUES "
            "('canonical-session','canonical-user',:jti,'2099-01-01T00:00:00+00:00',"
            "NULL,'webauthn','2026-08-01','2026-08-01')",
            {"jti": noncanonical_jti},
        )

        with pytest.raises(
            contract.MfaMigrationSafetyError,
            match="active session revocation data is invalid",
        ):
            contract.run_preflight(conn)

        assert redis_called is False
        assert conn.exec_driver_sql(
            "SELECT mfa_default_method, mfa_epoch FROM users WHERE id='canonical-user'"
        ).one() == ("webauthn", 0)
    finally:
        conn.close()
        engine.dispose()


def test_preflight_publishes_live_session_revocation_before_database_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A remediated bearer is tombstoned and broadcast before its DB state moves."""

    contract = _load("202608250002_contract_retire_webauthn.py")
    engine, conn = _legacy_database()
    calls: list[tuple[object, ...]] = []
    first_jti = "11111111-1111-4111-8111-111111111111"
    second_jti = "22222222-2222-4222-8222-222222222222"

    class RecordingRevocationRedis:
        def ping(self) -> bool:
            calls.append(("ping",))
            return True

        def set(self, key: str, value: str, *, ex: int) -> bool:
            # The external invalidation must complete before either the factor
            # remap or the local session state is mutated.
            assert conn.exec_driver_sql(
                "SELECT mfa_default_method, mfa_epoch FROM users WHERE id='live-user'"
            ).one() == ("webauthn", 0)
            assert conn.exec_driver_sql(
                "SELECT revoked_at, mfa_method FROM active_sessions WHERE id='live-session'"
            ).one() == (None, "webauthn")
            calls.append(("set", key, value, ex))
            return True

        def publish(self, channel: str, message: str) -> int:
            calls.append(("publish", channel, message))
            return 1

        def close(self) -> None:
            calls.append(("close",))

    redis = RecordingRevocationRedis()
    monkeypatch.setenv("REVOCATION_REDIS_URL", "redis://revocation.test:6379/0")
    monkeypatch.setattr(
        contract,
        "_get_migration_revocation_redis_client",
        lambda _url: redis,
        raising=False,
    )
    monkeypatch.setattr(
        contract,
        "_requires_persistent_session_revocation",
        lambda _bind: True,
        raising=False,
    )
    try:
        conn.exec_driver_sql(
            "INSERT INTO users VALUES "
            "('live-user','live@example.test',NULL,NULL,'webauthn',1)"
        )
        conn.exec_driver_sql(
            "INSERT INTO mfa_totp_enrollments VALUES "
            "('totp','live-user',1,'2026-08-01',NULL)"
        )
        conn.exec_driver_sql(
            "ALTER TABLE users ADD COLUMN mfa_epoch INTEGER NOT NULL DEFAULT 0"
        )
        conn.exec_driver_sql(
            "CREATE TABLE active_sessions (id TEXT, user_id TEXT, jti TEXT, "
            "expires_at DATETIME, revoked_at DATETIME, mfa_method TEXT, "
            "mfa_verified_at DATETIME, mfa_completed_at DATETIME)"
        )
        conn.exec_driver_sql(
            "INSERT INTO active_sessions VALUES "
            "('live-session','live-user',:first_jti,'2099-01-01T00:00:00+00:00',"
            "NULL,'webauthn','2026-08-01','2026-08-01'),"
            "('live-session-2','live-user',:second_jti,'2099-01-01T00:00:00+00:00',"
            "NULL,'webauthn','2026-08-01','2026-08-01')",
            {"first_jti": first_jti, "second_jti": second_jti},
        )

        assert contract.run_preflight(conn)["totp"] == 1

        assert [call[0] for call in calls] == [
            "ping",
            "set",
            "set",
            "publish",
            "publish",
            "close",
        ]
        assert set(calls[1:3]) == {
            ("set", f"revoked:jti:{first_jti}", "1", 86_400),
            ("set", f"revoked:jti:{second_jti}", "1", 86_400),
        }
        assert set(calls[3:5]) == {
            ("publish", "session:revocations", first_jti),
            ("publish", "session:revocations", second_jti),
        }
    finally:
        conn.close()
        engine.dispose()


def test_migration_revocation_client_uses_bounded_single_attempt_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Redis outage cannot indefinitely retain the migration's table locks."""

    contract = _load("202608250002_contract_retire_webauthn.py")
    captured: dict[str, object] = {}
    marker = object()

    def fake_from_url(_cls: type[Redis], url: str, **kwargs: object) -> object:
        captured["url"] = url
        captured.update(kwargs)
        return marker

    monkeypatch.setattr(Redis, "from_url", classmethod(fake_from_url))

    assert (
        contract._get_migration_revocation_redis_client(
            "redis://revocation.test:6379/0"
        )
        is marker
    )
    assert captured["url"] == "redis://revocation.test:6379/0"
    assert captured["decode_responses"] is True
    assert captured["socket_connect_timeout"] == 1.0
    assert captured["socket_timeout"] == 1.0
    assert captured["retry_on_timeout"] is False
    retry = captured["retry"]
    assert isinstance(retry, Retry)
    assert isinstance(retry._backoff, NoBackoff)
    assert retry._retries == 0


@pytest.mark.parametrize(
    "failure_point", ["ping_unacknowledged", "set", "set_unacknowledged", "publish"]
)
def test_preflight_fails_closed_when_live_revocation_delivery_fails(
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
) -> None:
    """Redis write or publication failure cannot partially retire an MFA factor."""

    contract = _load("202608250002_contract_retire_webauthn.py")
    engine, conn = _legacy_database()

    class FailingRevocationRedis:
        def ping(self) -> bool:
            if failure_point == "ping_unacknowledged":
                return False
            return True

        def set(self, _key: str, _value: str, *, ex: int) -> bool:
            if failure_point == "set":
                raise OSError("revocation store unavailable")
            if failure_point == "set_unacknowledged":
                return False
            return True

        def publish(self, _channel: str, _message: str) -> int:
            if failure_point == "set_unacknowledged":
                pytest.fail("A non-acknowledged tombstone must not be published")
            if failure_point == "publish":
                raise OSError("revocation publication unavailable")
            return 1

        def close(self) -> None:
            return None

    monkeypatch.setenv("REVOCATION_REDIS_URL", "redis://revocation.test:6379/0")
    monkeypatch.setattr(
        contract,
        "_get_migration_revocation_redis_client",
        lambda _url: FailingRevocationRedis(),
        raising=False,
    )
    monkeypatch.setattr(
        contract,
        "_requires_persistent_session_revocation",
        lambda _bind: True,
        raising=False,
    )
    try:
        conn.exec_driver_sql(
            "INSERT INTO users VALUES "
            "('failed-user','failed@example.test',NULL,NULL,'webauthn',1)"
        )
        conn.exec_driver_sql(
            "INSERT INTO mfa_totp_enrollments VALUES "
            "('totp','failed-user',1,'2026-08-01',NULL)"
        )
        conn.exec_driver_sql(
            "ALTER TABLE users ADD COLUMN mfa_epoch INTEGER NOT NULL DEFAULT 0"
        )
        conn.exec_driver_sql(
            "CREATE TABLE active_sessions (id TEXT, user_id TEXT, jti TEXT, "
            "expires_at DATETIME, revoked_at DATETIME, mfa_method TEXT, "
            "mfa_verified_at DATETIME, mfa_completed_at DATETIME)"
        )
        conn.exec_driver_sql(
            "INSERT INTO active_sessions VALUES "
            "('failed-session','failed-user','33333333-3333-4333-8333-333333333333','2099-01-01T00:00:00+00:00',"
            "NULL,'webauthn','2026-08-01','2026-08-01')"
        )

        with pytest.raises(
            contract.MfaMigrationSafetyError,
            match="session revocation delivery",
        ):
            contract.run_preflight(conn)

        assert conn.exec_driver_sql(
            "SELECT mfa_default_method, mfa_epoch FROM users WHERE id='failed-user'"
        ).one() == ("webauthn", 0)
        assert conn.exec_driver_sql(
            "SELECT revoked_at, mfa_method FROM active_sessions WHERE id='failed-session'"
        ).one() == (None, "webauthn")
    finally:
        conn.close()
        engine.dispose()


def test_preflight_fails_closed_when_live_revocation_url_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The migration must not degrade to DB-only invalidation without Redis."""

    contract = _load("202608250002_contract_retire_webauthn.py")
    engine, conn = _legacy_database()
    monkeypatch.delenv("REVOCATION_REDIS_URL", raising=False)
    monkeypatch.setattr(
        contract,
        "_requires_persistent_session_revocation",
        lambda _bind: True,
    )
    try:
        conn.exec_driver_sql(
            "INSERT INTO users VALUES "
            "('no-url-user','no-url@example.test',NULL,NULL,'webauthn',1)"
        )
        conn.exec_driver_sql(
            "INSERT INTO mfa_totp_enrollments VALUES "
            "('totp','no-url-user',1,'2026-08-01',NULL)"
        )
        conn.exec_driver_sql(
            "ALTER TABLE users ADD COLUMN mfa_epoch INTEGER NOT NULL DEFAULT 0"
        )
        conn.exec_driver_sql(
            "CREATE TABLE active_sessions (id TEXT, user_id TEXT, jti TEXT, "
            "expires_at DATETIME, revoked_at DATETIME, mfa_method TEXT, "
            "mfa_verified_at DATETIME, mfa_completed_at DATETIME)"
        )
        conn.exec_driver_sql(
            "INSERT INTO active_sessions VALUES "
            "('no-url-session','no-url-user','44444444-4444-4444-8444-444444444444','2099-01-01T00:00:00+00:00',"
            "NULL,'webauthn','2026-08-01','2026-08-01')"
        )

        with pytest.raises(
            contract.MfaMigrationSafetyError,
            match="session revocation delivery is unavailable",
        ):
            contract.run_preflight(conn)

        assert conn.exec_driver_sql(
            "SELECT mfa_default_method, mfa_epoch FROM users WHERE id='no-url-user'"
        ).one() == ("webauthn", 0)
        assert conn.exec_driver_sql(
            "SELECT revoked_at, mfa_method FROM active_sessions WHERE id='no-url-session'"
        ).one() == (None, "webauthn")
    finally:
        conn.close()
        engine.dispose()


def test_revocation_delivery_error_hides_the_connection_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A malformed transport configuration must not expose a credential in its cause."""

    contract = _load("202608250002_contract_retire_webauthn.py")
    private_url = "redis://:migration-private-value@revocation.test:6379/0"
    monkeypatch.setenv("REVOCATION_REDIS_URL", private_url)

    def invalid_client(url: str) -> object:
        raise ValueError(f"unsupported Redis URL: {url}")

    monkeypatch.setattr(
        contract, "_get_migration_revocation_redis_client", invalid_client
    )

    with pytest.raises(contract.MfaMigrationSafetyError) as exc_info:
        contract._publish_session_revocations(
            [(str(uuid.uuid4()), datetime(2099, 1, 1, tzinfo=UTC))]
        )

    assert "migration-private-value" not in str(exc_info.value)
    assert "revocation.test" not in str(exc_info.value)
    assert exc_info.value.__cause__ is None


def test_preflight_fails_closed_when_postgres_session_tombstone_fields_are_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PostgreSQL must not silently rely on DB-only invalidation for a live bearer."""

    contract = _load("202608250002_contract_retire_webauthn.py")
    engine, conn = _legacy_database()
    monkeypatch.setattr(
        contract,
        "_requires_persistent_session_revocation",
        lambda _bind: True,
        raising=False,
    )
    try:
        conn.exec_driver_sql(
            "INSERT INTO users VALUES "
            "('missing-jti','missing@example.test',NULL,NULL,'webauthn',1)"
        )
        conn.exec_driver_sql(
            "INSERT INTO mfa_totp_enrollments VALUES "
            "('totp','missing-jti',1,'2026-08-01',NULL)"
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
            "('missing-session','missing-jti',NULL,'webauthn','2026-08-01','2026-08-01')"
        )

        with pytest.raises(
            contract.MfaMigrationSafetyError,
            match="session tombstone fields",
        ):
            contract.run_preflight(conn)

        assert conn.exec_driver_sql(
            "SELECT mfa_default_method, mfa_epoch FROM users WHERE id='missing-jti'"
        ).one() == ("webauthn", 0)
        assert conn.exec_driver_sql(
            "SELECT revoked_at, mfa_method FROM active_sessions WHERE id='missing-session'"
        ).one() == (None, "webauthn")
    finally:
        conn.close()
        engine.dispose()


def test_preflight_fails_closed_for_malformed_live_session_jti_before_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An invalid stored JTI cannot bypass ws-hub's strict revocation parser."""

    contract = _load("202608250002_contract_retire_webauthn.py")
    engine, conn = _legacy_database()
    calls: list[str] = []

    class UnexpectedRedisCall:
        def ping(self) -> bool:
            calls.append("ping")
            return True

    monkeypatch.setenv("REVOCATION_REDIS_URL", "redis://revocation.test:6379/0")
    monkeypatch.setattr(
        contract,
        "_get_migration_revocation_redis_client",
        lambda _url: UnexpectedRedisCall(),
    )
    monkeypatch.setattr(
        contract, "_requires_persistent_session_revocation", lambda _bind: True
    )
    try:
        conn.exec_driver_sql(
            "INSERT INTO users VALUES "
            "('invalid-jti','invalid-jti@example.test',NULL,NULL,'webauthn',1)"
        )
        conn.exec_driver_sql(
            "INSERT INTO mfa_totp_enrollments VALUES "
            "('totp','invalid-jti',1,'2026-08-01',NULL)"
        )
        conn.exec_driver_sql(
            "ALTER TABLE users ADD COLUMN mfa_epoch INTEGER NOT NULL DEFAULT 0"
        )
        conn.exec_driver_sql(
            "CREATE TABLE active_sessions (id TEXT, user_id TEXT, jti TEXT, "
            "expires_at DATETIME, revoked_at DATETIME, mfa_method TEXT, "
            "mfa_verified_at DATETIME, mfa_completed_at DATETIME)"
        )
        conn.exec_driver_sql(
            "INSERT INTO active_sessions VALUES "
            "('invalid-jti-session','invalid-jti','not-a-uuid',"
            "'2099-01-01T00:00:00+00:00',NULL,'webauthn','2026-08-01','2026-08-01')"
        )

        with pytest.raises(
            contract.MfaMigrationSafetyError, match="session revocation data is invalid"
        ) as exc_info:
            contract.run_preflight(conn)

        assert "not-a-uuid" not in str(exc_info.value)
        assert calls == []
        assert conn.exec_driver_sql(
            "SELECT mfa_default_method, mfa_epoch FROM users WHERE id='invalid-jti'"
        ).one() == ("webauthn", 0)
        assert conn.exec_driver_sql(
            "SELECT revoked_at, mfa_method FROM active_sessions "
            "WHERE id='invalid-jti-session'"
        ).one() == (None, "webauthn")
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


def test_schema_reconciliation_migration_closes_model_drift() -> None:
    """The post-contract migration must materialize ORM indexes and nullability."""

    migration = _load("202608270001_reconcile_mfa_schema.py")
    assert migration.down_revision == "202608250003"

    env = os.environ.copy()
    env["DATABASE_URL"] = "postgresql+asyncpg://migration@localhost:5432/test"
    result = subprocess.run(  # noqa: S603 - fixed local Alembic module invocation
        [
            sys.executable,
            "-m",
            "alembic",
            "upgrade",
            "202608250003:202608270001",
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
    assert "ALTER TABLE MFA_CHALLENGES ALTER COLUMN FLOW SET NOT NULL" not in sql
    for index, table in (
        ("IX_MFA_CHALLENGES_FLOW", "MFA_CHALLENGES"),
        ("IX_MFA_CHALLENGES_METHOD", "MFA_CHALLENGES"),
        ("IX_MFA_CHALLENGES_RESEND_AVAILABLE_AT", "MFA_CHALLENGES"),
        ("IX_MFA_CHALLENGES_SESSION_IDENTIFIER", "MFA_CHALLENGES"),
        ("IX_USERS_EMAIL_MFA_ENABLED_AT", "USERS"),
        ("IX_USERS_EMAIL_VERIFIED_AT", "USERS"),
    ):
        assert f"CREATE INDEX {index} ON {table}" in sql


def test_schema_reconciliation_downgrade_preserves_indexes_offline() -> None:
    """Offline rollback must not delete indexes it cannot prove it owns."""

    env = os.environ.copy()
    env["DATABASE_URL"] = "postgresql+asyncpg://migration@localhost:5432/test"
    result = subprocess.run(  # noqa: S603 - fixed local Alembic module invocation
        [
            sys.executable,
            "-m",
            "alembic",
            "downgrade",
            "202608270001:202608250003",
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
    for index in (
        "IX_MFA_CHALLENGES_FLOW",
        "IX_MFA_CHALLENGES_METHOD",
        "IX_MFA_CHALLENGES_RESEND_AVAILABLE_AT",
        "IX_MFA_CHALLENGES_SESSION_IDENTIFIER",
        "IX_USERS_EMAIL_MFA_ENABLED_AT",
        "IX_USERS_EMAIL_VERIFIED_AT",
    ):
        assert f"DROP INDEX {index}" not in sql
        assert f"DROP INDEX IF EXISTS {index}" not in sql
