"""Real baseline and ordinary-role auth scope; no operator database is accepted."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import jwt
import pytest
import sqlalchemy as sa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import BackgroundTasks, HTTPException, Request
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.db.listeners import register_tenant_listeners
from app.core.tenant import bypass_rls_ctx, require_mvp_tenant, tenant_id_ctx
from app.models import User
from app.repositories.unit_of_work import uow_from_session
from app.schemas.users import UserCreate
from app.services.auth.credential_validator import CredentialValidator
from app.services.auth.lockout import LockoutService
from app.services.session_service import SessionService
from app.services.user.compliance_service import UserComplianceService
from app.services.user.profile_service import UserProfileService
from tests.fixtures.owned_baseline_postgres import clean_database as clean_database
from tests.fixtures.owned_baseline_postgres import (
    committed_baseline,
    owned_postgres_server,
)
from tests.fixtures.owned_baseline_postgres import (
    default_database_guard as default_database_guard,
)
from tests.fixtures.owned_baseline_postgres import (
    initialize_database_for_tests as initialize_database_for_tests,
)
from tests.fixtures.owned_baseline_postgres import prepare_database as prepare_database

pytestmark = [pytest.mark.integration, pytest.mark.timeout(300, method="signal")]


@pytest.mark.asyncio
async def test_owned_registration_login_token_and_rls_isolation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant, foreign, foreign_user, null_user = (uuid4() for _ in range(4))
    monkeypatch.setattr(settings, "mvp_tenant_id", tenant)
    monkeypatch.setattr(settings, "password_hibp_check_enabled", False)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    kid = uuid4().hex
    monkeypatch.setattr(settings, "jwt_signing_keys", [f"{kid}:{pem}"])
    monkeypatch.setattr(settings, "jwt_active_kid", kid)
    monkeypatch.setattr(settings, "algorithm", "RS256")
    register_tenant_listeners()
    with owned_postgres_server() as server, committed_baseline(server) as baseline:
        role_password = uuid4().hex
        admin = sa.create_engine(baseline.url, hide_parameters=True)
        try:
            with admin.begin() as connection:
                connection.exec_driver_sql(
                    "CREATE ROLE mvp_auth_test LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD "
                    + f"'{role_password}'"
                )
                connection.exec_driver_sql(
                    "GRANT USAGE ON SCHEMA public TO mvp_auth_test"
                )
                connection.exec_driver_sql(
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO mvp_auth_test"
                )
                connection.exec_driver_sql(
                    "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO mvp_auth_test"
                )
                connection.execute(
                    sa.text(
                        "INSERT INTO tenants(id, name, slug) VALUES (:a, 'A', 'owned-a'), (:b, 'B', 'owned-b')"
                    ),
                    {"a": tenant, "b": foreign},
                )
                for identity, scope in ((foreign_user, foreign), (null_user, None)):
                    connection.execute(
                        sa.text(
                            "INSERT INTO users(id, email, hashed_password, tenant_id) VALUES (:id, :email, :hash, :tenant)"
                        ),
                        {
                            "id": identity,
                            "email": f"{identity.hex}@example.com",
                            "hash": "unusable",
                            "tenant": scope,
                        },
                    )
            engine = create_async_engine(
                baseline.url.set(username="mvp_auth_test", password=role_password),
                hide_parameters=True,
                pool_size=1,
                max_overflow=0,
                connect_args={"connect_timeout": 5},
            )
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            token = tenant_id_ctx.set(str(tenant))
            bypass = bypass_rls_ctx.set(False)
            try:
                async with sessions() as db:
                    authority = (
                        await db.execute(
                            sa.text(
                                "SELECT rolsuper, rolbypassrls, pg_has_role(current_user, 'ue_rls_bypass', 'MEMBER') FROM pg_roles WHERE rolname=current_user"
                            )
                        )
                    ).one()
                    assert tuple(authority) == (False, False, False)
                    assert await require_mvp_tenant(db) == tenant
                    uow = uow_from_session(db)
                    audit = MagicMock()
                    compliance = UserComplianceService(uow=uow, audit=audit)
                    password = f"{uuid4().hex}!{uuid4().hex}"
                    registered = await compliance.register_user(
                        UserCreate(email="owned@example.com", password=password)
                    )
                    stored = await db.get(User, registered.id)
                    assert stored is not None and stored.tenant_id == tenant
                    assert await db.get(User, foreign_user) is None
                    assert await db.get(User, null_user) is None
                    profile = UserProfileService(
                        uow=uow, audit=audit, notifications=MagicMock()
                    )
                    history = MagicMock()
                    history.extract_client_info.return_value = (
                        "127.0.0.1",
                        "owned-test",
                    )
                    validator = CredentialValidator(
                        uow=uow,
                        user_repo=uow.users,
                        profile_service=profile,
                        lockout_service=LockoutService(db),
                        audit=audit,
                        session_manager=history,
                    )
                    request = Request(
                        {
                            "type": "http",
                            "headers": [],
                            "client": ("127.0.0.1", 1),
                            "method": "POST",
                            "path": "/login",
                        }
                    )
                    user = await validator.validate_credentials(
                        email="OWNED@example.com",
                        password=password,
                        request=request,
                        locale="en",
                        bg_tasks=BackgroundTasks(),
                    )
                    assert user.id == registered.id
                    failures = []
                    for email, attempted in (
                        ("owned@example.com", "incorrect"),
                        ("absent@example.com", "incorrect"),
                        (f"{foreign_user.hex}@example.com", "incorrect"),
                    ):
                        with pytest.raises(HTTPException) as rejected:
                            await validator.validate_credentials(
                                email=email,
                                password=attempted,
                                request=request,
                                locale="en",
                                bg_tasks=BackgroundTasks(),
                            )
                        failures.append(
                            (rejected.value.status_code, rejected.value.detail)
                        )
                    assert failures[0] == failures[1] == failures[2]
                    assert failures[0][0] == 401
                    service = SessionService(uow)
                    # External Redis is outside this owned DB test; persistence,
                    # row locking, real password verification and RSA JWT are real.
                    monkeypatch.setattr(service, "_sync_to_redis", AsyncMock())
                    encoded, active_session = await service.create_access_token(
                        user.id,
                        metadata={"mfa_epoch": user.mfa_epoch},
                        extra_claims={"tenant_id": str(foreign)},
                    )
                    claims = jwt.decode(
                        encoded,
                        private_key.public_key(),
                        algorithms=["RS256"],
                        audience=settings.jwt_audience,
                        issuer=settings.jwt_issuer,
                    )
                    assert claims["tenant_id"] == str(tenant)
                    assert claims["sub"] == str(registered.id)
                    assert claims["jti"] == str(active_session.jti)
                # Actual middleware and current-user resolver on a fresh app
                # session. Only external Redis storage is replaced.
                import hashlib
                import hmac

                import httpx
                from fastapi import FastAPI

                from app.api.deps import auth as auth_deps
                from app.core.middleware.tenant import TenantContextMiddleware

                key = uuid4().hex
                monkeypatch.setattr(settings, "internal_hmac_secret", key)
                revocations = MagicMock(exists=AsyncMock(return_value=0))
                monkeypatch.setattr(
                    auth_deps,
                    "get_revocation_redis_client",
                    AsyncMock(return_value=revocations),
                )
                redis_cache = MagicMock(
                    get_session=AsyncMock(return_value=None), create_session=AsyncMock()
                )
                app = FastAPI()
                app.add_middleware(
                    TenantContextMiddleware,
                    mvp_tenant_id=tenant,
                    internal_hmac_secret=key,
                )

                @app.get("/me")
                async def me(request: Request) -> dict[str, str]:
                    async with sessions() as db:
                        await require_mvp_tenant(db)
                        bearer = (
                            request.headers.get("authorization", "").removeprefix(
                                "Bearer "
                            )
                            or None
                        )
                        current = await auth_deps._resolve_current_user(
                            request, bearer, db, redis_cache
                        )
                        return {"id": str(current.id)}

                signature = hmac.new(
                    key.encode(),
                    f"{registered.id}:{active_session.jti}:{tenant}".encode(),
                    hashlib.sha256,
                ).hexdigest()
                gateway_headers = {
                    "x-user-id": str(registered.id),
                    "x-session-id": str(active_session.jti),
                    "x-tenant-id": str(tenant),
                    "x-internal-signature": signature,
                }
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://owned.test"
                ) as client:
                    response = await client.get("/me", headers=gateway_headers)
                    assert response.status_code == 200
                    assert response.json() == {"id": str(registered.id)}
                    direct = await client.get(
                        "/me", headers={"authorization": f"Bearer {encoded}"}
                    )
                    assert direct.status_code == 200
                    assert direct.json() == response.json()
                    assert (await client.get("/me")).status_code == 401
                    assert (
                        await client.get("/me", headers={"x-tenant-id": str(foreign)})
                    ).status_code == 401
                    altered = dict(gateway_headers, **{"x-tenant-id": str(foreign)})
                    assert (await client.get("/me", headers=altered)).status_code == 401
                    foreign_claims = dict(claims, tenant_id=str(foreign))
                    foreign_token = jwt.encode(
                        foreign_claims, pem, algorithm="RS256", headers={"kid": kid}
                    )
                    assert (
                        await client.get(
                            "/me", headers={"authorization": f"Bearer {foreign_token}"}
                        )
                    ).status_code == 401
                # Reuse the sole pooled connection with no task tenant. GUC from
                # registration/session commits must not retain the prior scope.
                tenant_id_ctx.set("")
                async with sessions() as db:
                    assert await db.scalar(sa.text("SELECT count(*) FROM users")) == 0
                    with pytest.raises(HTTPException):
                        await require_mvp_tenant(db)
                tenant_id_ctx.set(str(tenant))
                with admin.begin() as connection:
                    connection.execute(
                        sa.text("UPDATE tenants SET is_active=false WHERE id=:id"),
                        {"id": tenant},
                    )
                async with sessions() as db:
                    with pytest.raises(HTTPException) as inactive:
                        await require_mvp_tenant(db)
                    assert inactive.value.status_code == 503
            finally:
                bypass_rls_ctx.reset(bypass)
                tenant_id_ctx.reset(token)
                await engine.dispose()
        finally:
            admin.dispose()
