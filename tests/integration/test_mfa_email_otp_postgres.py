from __future__ import annotations

import asyncio
import os
import re
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pyotp
import pytest
from alembic.config import Config
from fastapi import HTTPException
from psycopg import sql
from sqlalchemy import MetaData, Table, create_engine, insert, inspect, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from alembic import command
from app.auth import mfa
from app.auth.mfa.email_otp import EmailOtpService, MfaOtpRejected
from app.models import User


def _acceptance_requested() -> bool:
    return bool(os.getenv("MFA_TEST_POSTGRES_DSN")) or (
        os.getenv("RUN_INTEGRATION_TESTS") == "1"
    )


pytestmark = [
    pytest.mark.skipif(
        "not _acceptance_requested()",
        reason="requires PostgreSQL integration lane or dedicated MFA test DSN",
    ),
    pytest.mark.filterwarnings("error:.*autoincrement.*only make sense for MySQL.*"),
]
ROOT = Path(__file__).resolve().parents[2]
USER_ID = uuid4()
FINGERPRINT = "f" * 64
SESSION_ID = "postgres-two-connection-session"
NOW = datetime(2026, 8, 25, 10, 0, tzinfo=UTC)
LEGACY_CREDENTIAL_ID = UUID("00000000-0000-4000-8000-000000000002")


class _Limiter:
    async def enforce(self, *, action: str, identifier: str) -> None:
        return None


def _urls(dsn: str) -> tuple[str, str]:
    if not dsn:
        raise ValueError("PostgreSQL acceptance requires an explicit test database URL")
    parsed = make_url(dsn)
    if (
        parsed.get_backend_name() != "postgresql"
        or not parsed.host
        or not parsed.username
    ):
        raise ValueError("PostgreSQL acceptance requires explicit host and user")
    if not re.search(r"(?:^test|[-_]test(?:[-_]|$))", parsed.database or "", re.I):
        raise ValueError("PostgreSQL acceptance must name a dedicated test database")
    return (
        parsed.set(drivername="postgresql+asyncpg").render_as_string(
            hide_password=False
        ),
        parsed.set(drivername="postgresql+psycopg").render_as_string(
            hide_password=False
        ),
    )


@contextmanager
def _postgres_acceptance_urls() -> Iterator[tuple[str, str]]:
    """Own only a newly created database, never the suite or manual database."""
    manual_dsn = os.getenv("MFA_TEST_POSTGRES_DSN")
    if manual_dsn:
        yield _urls(manual_dsn)
        return
    if os.getenv("RUN_INTEGRATION_TESTS") != "1":
        raise RuntimeError("PostgreSQL acceptance requires the integration opt-in")
    if os.getenv("ENVIRONMENT") != "testing":
        raise RuntimeError("PostgreSQL acceptance provisioning requires testing")
    if os.getenv("UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET") != "1":
        raise RuntimeError("PostgreSQL acceptance provisioning requires reset opt-in")

    source_async, _ = _urls(os.getenv("DATABASE_URL", ""))
    source = make_url(source_async)
    database_name = f"test_mfa_{uuid4().hex}"
    if database_name == source.database:
        raise RuntimeError("owned acceptance target must differ from source database")
    target_urls = _urls(
        source.set(database=database_name).render_as_string(hide_password=False)
    )
    maintenance_dsn = source.set(
        drivername="postgresql", database="postgres"
    ).render_as_string(hide_password=False)
    with psycopg.connect(
        maintenance_dsn,
        autocommit=True,
        connect_timeout=10,
        options="-c lock_timeout=10000 -c statement_timeout=30000",
    ) as admin:
        # A failed CREATE (including a name collision) confers no ownership.
        # Never use DROP IF EXISTS or retry by deleting another run's database.
        admin.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name))
        )
        try:
            yield target_urls
        finally:
            # FORCE closes remaining connections only to this owned disposable
            # database if an assertion interrupted normal session disposal.
            admin.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
                    sql.Identifier(database_name)
                )
            )


@pytest.fixture
def mfa_postgres_urls() -> Iterator[tuple[str, str]]:
    with _postgres_acceptance_urls() as urls:
        yield urls


def _upgrade(sync_url: str, revision: str) -> None:
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = sync_url
    try:
        config = Config(str(ROOT / "alembic.ini"))
        config.set_main_option("sqlalchemy.url", sync_url.replace("%", "%%"))
        command.upgrade(config, revision)
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def _service() -> EmailOtpService:
    return EmailOtpService(
        hmac_keys={"pg-hmac": b"h" * 32},
        active_hmac_key_id="pg-hmac",
        delivery_keks={"pg-kek": b"k" * 32},
        active_kek_id="pg-kek",
        rate_limiter=_Limiter(),
    )


def _assert_contract_abort_and_lock(sync_url: str) -> None:
    engine = create_engine(sync_url)
    try:
        _assert_contract_on_engine(sync_url, engine)
    finally:
        engine.dispose()


def _assert_contract_on_engine(sync_url: str, engine: Engine) -> None:
    with engine.connect() as connection:
        if inspect(connection).has_table("alembic_version"):
            pytest.fail("dedicated PostgreSQL acceptance database must start empty")
    _upgrade(sync_url, "202607280001")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users "
                "(id,email,hashed_password,role,is_active,mfa_required,mfa_default_method) "
                "VALUES (:id,:email,:password,'student',true,true,'webauthn')"
            ),
            {
                "id": USER_ID,
                "email": "mfa-pg@example.test",
                "password": "not-used-in-acceptance",  # pragma: allowlist secret
            },
        )
    _upgrade(sync_url, "202608250001")
    digest_challenge_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO mfa_challenges "
                "(id,user_id,challenge_type,expires_at,flow,session_identifier,"
                "client_fingerprint,method,token_digest,token_key_id,recipient_digest) "
                "VALUES (:id,:user_id,'email_otp',:expires_at,'login',:session_id,"
                ":fingerprint,'email_otp',:token_digest,:token_key_id,:recipient_digest)"
            ),
            {
                "id": digest_challenge_id,
                "user_id": USER_ID,
                "expires_at": NOW,
                "session_id": f"digest-{SESSION_ID}",
                "fingerprint": FINGERPRINT,
                "token_digest": "a" * 64,
                "token_key_id": "pg-hmac",
                "recipient_digest": "e" * 64,
            },
        )
        digest_row = connection.execute(
            text("SELECT token,payload FROM mfa_challenges WHERE id=:id"),
            {"id": digest_challenge_id},
        ).one()
        assert digest_row.token.startswith("__mfa_digest_only__:")
        assert digest_row.payload is None
    with pytest.raises(RuntimeError, match="Unsafe MFA retirement"):
        _upgrade(sync_url, "202608250002")
    with engine.connect() as connection:
        legacy_tables = [
            name
            for name in ("webauthn_credentials", "mfa_webauthn_credentials")
            if inspect(connection).has_table(name)
        ]
        assert legacy_tables
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            "202608250001"
        )
        assert connection.execute(
            text("SELECT mfa_default_method,email_verified_at FROM users WHERE id=:id"),
            {"id": USER_ID},
        ).one() == ("webauthn", None)
        assert "token" in {
            column["name"]
            for column in inspect(connection).get_columns("mfa_challenges")
        }

    legacy_name = legacy_tables[0]
    credential_table = Table(legacy_name, MetaData(), autoload_with=engine)
    values = {
        key: value
        for key, value in {
            "id": LEGACY_CREDENTIAL_ID,
            "user_id": USER_ID,
            "credential_id": f"acceptance-{uuid4()}",
            "public_key": "acceptance-public-key",
            "sign_count": 0,
            "backed_up": False,
            "clone_warning": False,
            "is_active": True,
        }.items()
        if key in credential_table.c
    }

    def contended_insert() -> str | None:
        try:
            with engine.begin() as connection:
                connection.exec_driver_sql("SET LOCAL statement_timeout = '500ms'")
                connection.execute(insert(credential_table).values(**values))
        except DBAPIError as exc:
            return getattr(exc.orig, "sqlstate", None)
        return "inserted"

    locker = engine.connect()
    transaction = locker.begin()
    try:
        locker.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": 824_250_002},
        )
        quoted = locker.dialect.identifier_preparer.quote(legacy_name)
        locker.exec_driver_sql(f"LOCK TABLE users, {quoted} IN ACCESS EXCLUSIVE MODE")
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(contended_insert).result(timeout=5) == "57014"
    finally:
        transaction.rollback()
        locker.close()

    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE users SET email_verified_at=:now, "
                "email_mfa_enabled_at=:now WHERE id=:id"
            ),
            {"now": NOW, "id": USER_ID},
        )
    _upgrade(sync_url, "202608250002")
    with engine.connect() as connection:
        assert not any(inspect(connection).has_table(name) for name in legacy_tables)
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            "202608250002"
        )
        assert "token" not in {
            column["name"]
            for column in inspect(connection).get_columns("mfa_challenges")
        }
        assert (
            connection.execute(
                text("SELECT token_digest FROM mfa_challenges WHERE id=:id"),
                {"id": digest_challenge_id},
            ).scalar_one()
            == "a" * 64
        )


@pytest.mark.asyncio
async def test_postgres_migration_and_two_connection_security_races(
    mfa_postgres_urls: tuple[str, str],
) -> None:
    async_url, sync_url = mfa_postgres_urls
    _assert_contract_abort_and_lock(sync_url)
    engine = create_async_engine(async_url)
    try:
        await _assert_security_races(engine)
    finally:
        await engine.dispose()


async def _assert_security_races(engine: AsyncEngine) -> None:
    sessions = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    service = _service()

    async with sessions() as setup:
        issued = await service.issue(
            setup,
            user_id=USER_ID,
            flow="login",
            session_identifier=SESSION_ID,
            client_fingerprint=FINGERPRINT,
            client_ip="203.0.113.8",
            locale="en",
            now=NOW,
        )
        await setup.commit()

    async def verify_email() -> bool:
        async with sessions() as db:
            try:
                await service.verify(
                    db,
                    challenge_token=issued.challenge_token,
                    code=issued.otp,
                    user_id=USER_ID,
                    flow="login",
                    session_identifier=SESSION_ID,
                    client_fingerprint=FINGERPRINT,
                    client_ip="203.0.113.8",
                    now=NOW + timedelta(seconds=1),
                )
                await db.commit()
                return True
            except MfaOtpRejected:
                await db.rollback()
                return False

    assert sum(await asyncio.gather(verify_email(), verify_email())) == 1

    async with sessions() as setup:
        verify_resend = await service.issue(
            setup,
            user_id=USER_ID,
            flow="login",
            session_identifier=f"{SESSION_ID}-verify-resend",
            client_fingerprint=FINGERPRINT,
            client_ip="203.0.113.8",
            locale="en",
            now=NOW + timedelta(seconds=2),
        )
        await setup.commit()

    async def verify_or_resend(operation: str) -> bool:
        async with sessions() as db:
            try:
                if operation == "verify":
                    await service.verify(
                        db,
                        challenge_token=verify_resend.challenge_token,
                        code=verify_resend.otp,
                        user_id=USER_ID,
                        flow="login",
                        session_identifier=f"{SESSION_ID}-verify-resend",
                        client_fingerprint=FINGERPRINT,
                        client_ip="203.0.113.8",
                        now=NOW + timedelta(seconds=63),
                    )
                else:
                    await service.resend(
                        db,
                        challenge_token=verify_resend.challenge_token,
                        user_id=USER_ID,
                        flow="login",
                        session_identifier=f"{SESSION_ID}-verify-resend",
                        client_fingerprint=FINGERPRINT,
                        client_ip="203.0.113.8",
                        locale="en",
                        now=NOW + timedelta(seconds=63),
                    )
                await db.commit()
                return True
            except MfaOtpRejected:
                await db.rollback()
                return False

    assert (
        sum(
            await asyncio.gather(verify_or_resend("verify"), verify_or_resend("resend"))
        )
        == 1
    )

    async with sessions() as setup:
        user = await setup.get(User, USER_ID)
        assert user is not None
        enrollment, secret, _ = await mfa.start_totp_enrollment(setup, user=user)
        totp = pyotp.TOTP(secret)
        await mfa.complete_totp_enrollment(
            setup, enrollment=enrollment, code=totp.now()
        )
        code = totp.now()
        challenges = [
            await mfa.issue_challenge(
                setup,
                user_id=USER_ID,
                challenge_type="totp-verify",
                flow="login",
                session_identifier=f"{SESSION_ID}-totp-{index}",
                client_fingerprint=FINGERPRINT,
                method="totp",
            )
            for index in range(2)
        ]
        recovery_code = (
            await mfa.generate_recovery_codes(
                setup,
                user=user,
                fresh_mfa_verified_at=datetime.now(UTC),
            )
        )[0]
        await setup.commit()

    async def consume_totp(token: str, session_identifier: str) -> bool:
        async with sessions() as db:
            user = await db.get(User, USER_ID)
            assert user is not None
            try:
                await mfa.verify_totp_for_user(
                    db,
                    user=user,
                    code=code,
                    challenge_token=token,
                    client_fingerprint=FINGERPRINT,
                    login_session_identifier=session_identifier,
                )
                await db.commit()
                return True
            except HTTPException:
                await db.rollback()
                return False

    assert (
        sum(
            await asyncio.gather(
                *(
                    consume_totp(
                        challenge.challenge_token,
                        f"{SESSION_ID}-totp-{index}",
                    )
                    for index, challenge in enumerate(challenges)
                )
            )
        )
        == 1
    )

    async def consume_recovery() -> bool:
        async with sessions() as db:
            user = await db.get(User, USER_ID)
            assert user is not None
            accepted = await mfa.verify_recovery_code(db, user=user, code=recovery_code)
            await db.commit()
            return accepted

    assert sum(await asyncio.gather(consume_recovery(), consume_recovery())) == 1

    trusted_ip = "203.0.113.44"
    trusted_ua = "mfa-postgres-concurrency-test"
    async with sessions() as setup:
        user = await setup.get(User, USER_ID)
        assert user is not None
        trusted_token, _ = await mfa.create_trusted_device_token(
            setup,
            user=user,
            ip_address=trusted_ip,
            user_agent=trusted_ua,
        )
        await setup.commit()

    trusted_started = asyncio.Event()

    async def trusted_login() -> str | None:
        async with sessions() as db:
            user = await db.get(User, USER_ID)
            assert user is not None
            trusted_started.set()
            rotated = await mfa.verify_and_rotate_trusted_device_token(
                db,
                user=user,
                token=trusted_token,
                request_ip=trusted_ip,
                request_ua=trusted_ua,
            )
            await db.commit()
            return rotated

    async with sessions() as factor_db:
        factor_user = await factor_db.get(User, USER_ID)
        assert factor_user is not None
        await factor_db.execute(
            select(User).where(User.id == USER_ID).with_for_update(nowait=False)
        )
        trusted_task = asyncio.create_task(trusted_login())
        await trusted_started.wait()
        await asyncio.sleep(0.1)
        assert not trusted_task.done()
        await mfa.reset_user_mfa(factor_db, user=factor_user)
        await factor_db.commit()

    assert await asyncio.wait_for(trusted_task, timeout=5) is None
