"""Current-baseline MFA atomicity on acknowledged disposable PostgreSQL."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pyotp
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.auth import mfa
from app.auth.mfa.email_otp import EmailOtpService, MfaOtpRejected
from app.core.db.listeners import set_pg_tenant_context
from app.core.tenant import bypass_rls_ctx, tenant_id_ctx
from app.models import User
from tests.fixtures import owned_baseline_postgres as owned

initialize_database_for_tests = owned.initialize_database_for_tests
prepare_database = owned.prepare_database
clean_database = owned.clean_database
default_database_guard = owned.default_database_guard
owned_baseline_server = owned.owned_baseline_server

pytestmark = [
    pytest.mark.integration,
    pytest.mark.timeout(300, method="signal", func_only=False),
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="requires the owned PostgreSQL integration lane",
    ),
    pytest.mark.filterwarnings("error:.*autoincrement.*only make sense for MySQL.*"),
]
USER_ID = uuid4()
FINGERPRINT = "f" * 64
SESSION_ID = "postgres-two-connection-session"
NOW = datetime(2026, 8, 25, 10, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def mfa_watchdog(request: pytest.FixtureRequest) -> None:
    assert request.config.getoption("timeout_disable_debugger_detection", False), (
        "MFA tests require --timeout-disable-debugger-detection"
    )


class _Limiter:
    async def enforce(self, *, action: str, identifier: str) -> None:
        return None


def _service() -> EmailOtpService:
    return EmailOtpService(
        hmac_keys={"pg-hmac": b"h" * 32},
        active_hmac_key_id="pg-hmac",
        delivery_keks={"pg-kek": b"k" * 32},
        active_kek_id="pg-kek",
        rate_limiter=_Limiter(),
    )


@asynccontextmanager
async def _mfa_database(
    request: pytest.FixtureRequest,
    *,
    user_id: UUID,
    email: str,
    verified: bool,
) -> AsyncIterator[tuple[AsyncEngine, async_sessionmaker[AsyncSession]]]:
    """Provision privileged DDL only on an active lease; exercise MFA without bypass."""
    server = request.getfixturevalue("owned_baseline_server")
    with owned.committed_baseline(server) as baseline:
        tenant = uuid4()
        role = f"mfa_reader_writer_{uuid4().hex}"
        admin = create_engine(
            baseline.url, poolclass=NullPool, connect_args={"connect_timeout": 5}
        )
        try:
            with admin.begin() as connection:
                connection.execute(
                    text(f'CREATE ROLE "{role}" NOLOGIN NOSUPERUSER NOBYPASSRLS')
                )
                connection.execute(text(f'GRANT USAGE ON SCHEMA public TO "{role}"'))
                connection.execute(
                    text(
                        "GRANT SELECT, INSERT, UPDATE, DELETE ON "
                        "public.users, public.mfa_challenges, public.mfa_email_deliveries, "
                        "public.mfa_totp_enrollments, public.recovery_codes, public.trusted_devices, "
                        "public.active_sessions, public.stored_events "
                        f'TO "{role}"'
                    )
                )
                connection.execute(
                    text("INSERT INTO tenants (id,name,slug) VALUES (:id,:name,:slug)"),
                    {"id": tenant, "name": "MFA integration", "slug": uuid4().hex},
                )
                connection.execute(
                    text(
                        "INSERT INTO users (id,email,hashed_password,tenant_id,role,is_active,"
                        "email_verified_at,email_mfa_enabled_at,mfa_default_method) "
                        "VALUES (:id,:email,:credential,:tenant,'student',true,:verified,:verified,'email_otp')"
                    ),
                    {
                        "id": user_id,
                        "email": email,
                        "credential": f"!{uuid4()}",
                        "tenant": tenant,
                        "verified": NOW if verified else None,
                    },
                )
                inspector = inspect(connection)
                assert "token" not in {
                    item["name"] for item in inspector.get_columns("mfa_challenges")
                }
                assert not {"webauthn_credentials", "mfa_webauthn_credentials"} & set(
                    inspector.get_table_names()
                )
        finally:
            admin.dispose()

        # A private Session subclass scopes the hook to this factory. Every
        # transaction derives tenant authority from the production ContextVars,
        # including the empty scope restored by legacy outbox deliveries.
        # No global listener is installed or removed.
        class TenantSession(Session):
            pass

        @event.listens_for(TenantSession, "after_begin")
        def identity(_session, _transaction, connection) -> None:
            connection.execute(text(f'SET LOCAL ROLE "{role}"'))
            # Invoke after SET ROLE; even if the inherited Session listener ran
            # first, both read the same current task context, never a captured ID.
            set_pg_tenant_context(_session, _transaction, connection)
            connection.execute(
                text("SELECT set_config('app.current_user_id', :user, true)"),
                {"user": str(user_id)},
            )
            assert connection.execute(
                text(
                    "SELECT current_user, rolsuper, rolbypassrls, "
                    "pg_has_role(current_user, 'ue_rls_bypass', 'MEMBER') "
                    "FROM pg_roles WHERE rolname = current_user"
                )
            ).one() == (role, False, False, False)

        engine = create_async_engine(
            baseline.url.set(drivername="postgresql+asyncpg", query={}),
            poolclass=NullPool,
            hide_parameters=True,
            connect_args={
                "timeout": 5,
                "command_timeout": 65,
                "server_settings": {
                    "lock_timeout": "10s",
                    "statement_timeout": "60s",
                    "idle_in_transaction_session_timeout": "60s",
                },
            },
        )
        sessions = async_sessionmaker(
            engine, expire_on_commit=False, sync_session_class=TenantSession
        )
        tenant_token = tenant_id_ctx.set(str(tenant))
        bypass_token = bypass_rls_ctx.set(False)
        try:
            yield engine, sessions
        finally:
            try:
                await engine.dispose()
            finally:
                bypass_rls_ctx.reset(bypass_token)
                tenant_id_ctx.reset(tenant_token)


@pytest.mark.asyncio
async def test_postgres_baseline_two_connection_security_races(
    request: pytest.FixtureRequest,
) -> None:
    async with _mfa_database(
        request, user_id=USER_ID, email="mfa-pg@example.test", verified=True
    ) as (_, sessions):
        await _assert_security_races(sessions)
    assert request.getfixturevalue("default_database_guard") == []


async def _race(*operations: Coroutine[Any, Any, bool]) -> list[bool]:
    # TaskGroup cancels and joins every sibling on unexpected failure before
    # the caller can dispose the engine or drop its owned database. SQL/client
    # deadlines and the module signal watchdog also cover cancellation cleanup.
    async with asyncio.timeout(75):
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(operation) for operation in operations]
    return [task.result() for task in tasks]


async def _assert_security_races(sessions: async_sessionmaker[AsyncSession]) -> None:
    service = _service()
    barrier = asyncio.Barrier(2)
    backend_ids: set[int] = set()

    async def rendezvous(db: AsyncSession) -> None:
        backend_id = await db.scalar(text("SELECT pg_backend_pid()"))
        assert isinstance(backend_id, int)
        backend_ids.add(backend_id)
        await asyncio.wait_for(barrier.wait(), timeout=5)
        assert len(backend_ids) == 2

    async with sessions() as observer:
        assert await observer.get(User, USER_ID) is not None
        await observer.execute(
            text(
                "SELECT set_config('app.current_tenant', :tenant, true), "
                "set_config('app.bypass_rls', 'on', true)"
            ),
            {"tenant": str(uuid4())},
        )
        assert await observer.scalar(select(User.id).where(User.id == USER_ID)) is None
        await observer.rollback()
        assert (
            await observer.scalar(select(User.id).where(User.id == USER_ID)) == USER_ID
        )

    wrong_tenant_token = tenant_id_ctx.set(str(uuid4()))
    try:
        async with sessions() as observer:
            assert (
                await observer.scalar(select(User.id).where(User.id == USER_ID)) is None
            )
    finally:
        tenant_id_ctx.reset(wrong_tenant_token)

    async with sessions() as setup:
        # Use the current account epoch from the committed baseline fixture.
        user = await setup.get(User, USER_ID)
        assert user is not None
        issued = await service.issue(
            setup,
            user_id=USER_ID,
            expected_mfa_epoch=user.mfa_epoch,
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
            await rendezvous(db)
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

    assert sum(await _race(verify_email(), verify_email())) == 1

    async with sessions() as setup:
        user = await setup.get(User, USER_ID)
        assert user is not None
        verify_resend = await service.issue(
            setup,
            user_id=USER_ID,
            expected_mfa_epoch=user.mfa_epoch,
            flow="login",
            session_identifier=f"{SESSION_ID}-verify-resend",
            client_fingerprint=FINGERPRINT,
            client_ip="203.0.113.8",
            locale="en",
            now=NOW + timedelta(seconds=2),
        )
        await setup.commit()

    backend_ids.clear()

    async def verify_or_resend(operation: str) -> bool:
        async with sessions() as db:
            await rendezvous(db)
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

    assert sum(await _race(verify_or_resend("verify"), verify_or_resend("resend"))) == 1

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

    backend_ids.clear()

    async def consume_totp(
        token: str, session_identifier: str, *, race: bool = True
    ) -> bool:
        async with sessions() as db:
            if race:
                await rendezvous(db)
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

    # Both requests consume exactly the same challenge and OTP, not two
    # independent challenges that could each succeed legitimately.
    assert (
        sum(
            await _race(
                consume_totp(challenges[0].challenge_token, f"{SESSION_ID}-totp-0"),
                consume_totp(challenges[0].challenge_token, f"{SESSION_ID}-totp-0"),
            )
        )
        == 1
    )
    # Reusing the consumed timecode through another live challenge is also denied.
    assert not await consume_totp(
        challenges[1].challenge_token, f"{SESSION_ID}-totp-1", race=False
    )
    backend_ids.clear()

    async def consume_recovery() -> bool:
        async with sessions() as db:
            await rendezvous(db)
            user = await db.get(User, USER_ID)
            assert user is not None
            accepted = await mfa.verify_recovery_code(db, user=user, code=recovery_code)
            await db.commit()
            return accepted

    assert sum(await _race(consume_recovery(), consume_recovery())) == 1

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
        async with asyncio.timeout(75):
            async with asyncio.TaskGroup() as group:
                trusted_task = group.create_task(trusted_login())
                await asyncio.wait_for(trusted_started.wait(), timeout=5)
                await asyncio.sleep(0.1)
                assert not trusted_task.done()
                await mfa.reset_user_mfa(factor_db, user=factor_user)
                await factor_db.commit()
                assert await asyncio.wait_for(trusted_task, timeout=5) is None
