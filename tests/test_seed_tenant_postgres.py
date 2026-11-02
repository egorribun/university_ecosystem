"""Owned PostgreSQL proof that seed writes need scope, not elevated roles."""

from __future__ import annotations

from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.db.listeners import register_tenant_listeners
from app.core.tenant import bypass_rls_ctx, get_current_tenant, tenant_id_ctx
from app.models.tenant import Tenant
from scripts import seed_tenant
from scripts.seed_demo_data import seed_group
from scripts.seed_tenant import ensure_seed_tenant, seed_tenant_context
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
PROJECT = "ue-live-0123456789abcdef"


@pytest.mark.parametrize("configured", [None, uuid4()])
def test_live_seed_configuration_must_match_owned_identity(
    monkeypatch, configured
) -> None:
    monkeypatch.setattr(seed_tenant.settings, "mvp_tenant_id", configured)
    with pytest.raises(RuntimeError, match="MVP_TENANT_ID"):
        seed_tenant.validate_seed_tenant_configuration(PROJECT)


def test_live_seed_configuration_accepts_exact_identity(monkeypatch) -> None:
    with seed_tenant_context(PROJECT) as identity:
        monkeypatch.setattr(seed_tenant.settings, "mvp_tenant_id", identity)
        seed_tenant.validate_seed_tenant_configuration(PROJECT)


def test_unconfigured_smoke_does_not_enable_runtime_routing(monkeypatch) -> None:
    monkeypatch.setattr(seed_tenant.settings, "mvp_tenant_id", None)
    seed_tenant.validate_seed_tenant_configuration("ci-admin-smoke")
    assert seed_tenant.settings.mvp_tenant_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["id", "slug", "name", "domain", "is_active"])
async def test_reserved_tenant_drift_is_not_adopted(field: str) -> None:
    with seed_tenant_context(PROJECT) as identity:
        existing = Tenant(
            id=identity,
            slug=PROJECT,
            name=f"Owned seed tenant: {PROJECT}",
            is_active=True,
        )
        setattr(
            existing,
            field,
            {
                "id": uuid4(),
                "slug": "occupied",
                "name": "foreign",
                "domain": "example.com",
                "is_active": False,
            }[field],
        )

        class ReadOnlySession:
            async def scalar(self, statement):
                return existing

        with pytest.raises(RuntimeError, match="occupied or drifted"):
            await ensure_seed_tenant(ReadOnlySession(), PROJECT, identity)


def test_seed_context_restores_ambient_identity_on_failure() -> None:
    outer = tenant_id_ctx.set(str(uuid4()))
    bypass = bypass_rls_ctx.set(True)
    previous = get_current_tenant()
    try:
        with pytest.raises(RuntimeError, match="sentinel"):
            with seed_tenant_context(PROJECT) as identity:
                assert get_current_tenant() == str(identity)
                assert not bypass_rls_ctx.get()
                raise RuntimeError("sentinel")
        assert get_current_tenant() == previous
        assert bypass_rls_ctx.get()
    finally:
        bypass_rls_ctx.reset(bypass)
        tenant_id_ctx.reset(outer)


@pytest.mark.parametrize("project", ["", "production", "ue-live-123", "ci-other"])
def test_seed_context_rejects_unrecognized_project(project: str) -> None:
    with pytest.raises(ValueError, match="seed project"):
        with seed_tenant_context(project):
            pytest.fail("invalid project entered seed scope")


@pytest.mark.asyncio
async def test_owned_seed_group_as_nonprivileged_role_is_scoped_and_repeatable() -> (
    None
):
    register_tenant_listeners()
    with owned_postgres_server() as server, committed_baseline(server) as baseline:
        password = uuid4().hex
        admin = sa.create_engine(baseline.url, hide_parameters=True)
        try:
            with admin.begin() as connection:
                # UUID hex is generated in this test; no operator SQL or credential.
                connection.exec_driver_sql(
                    "CREATE ROLE seed_test LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD "
                    f"'{password}'"
                )
                connection.exec_driver_sql("GRANT USAGE ON SCHEMA public TO seed_test")
                connection.exec_driver_sql(
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO seed_test"
                )
            engine = create_async_engine(
                baseline.url.set(username="seed_test", password=password),
                hide_parameters=True,
                connect_args={"connect_timeout": 5},
            )
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            try:
                with seed_tenant_context(PROJECT) as identity:
                    async with sessions() as db:
                        authority = (
                            await db.execute(
                                sa.text(
                                    "SELECT rolsuper, rolbypassrls, "
                                    "pg_has_role(current_user, 'ue_rls_bypass', 'MEMBER') "
                                    "FROM pg_roles WHERE rolname = current_user"
                                )
                            )
                        ).one()
                        assert tuple(authority) == (False, False, False)
                        await ensure_seed_tenant(db, PROJECT, identity)
                        group = await seed_group(db)
                        group_id = group.id
                        await db.commit()
                    async with sessions() as db:
                        await ensure_seed_tenant(db, PROJECT, identity)
                        assert (await seed_group(db)).id == group_id
                        assert (
                            await db.scalar(sa.text("SELECT tenant_id FROM groups"))
                            == identity
                        )
                        await db.commit()
                with seed_tenant_context("ue-live-fedcba9876543210"):
                    async with sessions() as db:
                        assert (
                            await db.scalar(sa.text("SELECT count(*) FROM groups")) == 0
                        )
                token = tenant_id_ctx.set("")
                try:
                    async with sessions() as db:
                        with pytest.raises(sa.exc.DBAPIError) as denied:
                            await db.execute(
                                sa.text(
                                    "INSERT INTO groups (id, name) VALUES (:id, 'unscoped')"
                                ),
                                {"id": uuid4()},
                            )
                        assert denied.value.orig.sqlstate == "42501"
                        await db.rollback()
                finally:
                    tenant_id_ctx.reset(token)
            finally:
                await engine.dispose()
        finally:
            admin.dispose()
