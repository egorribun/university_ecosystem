"""Exercise the push-binding successor against the real PostgreSQL baseline."""

from __future__ import annotations

import os
import secrets
from collections.abc import Iterator
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

from alembic import command
from app.auth.security import get_password_hash_sync
from tests.fixtures import owned_baseline_postgres as owned
from tests.test_push_binding_version_migration import ROOT, _migration

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_INTEGRATION_TESTS") != "1",
        reason="Set RUN_INTEGRATION_TESTS=1 to run the owned PostgreSQL proof",
    ),
]


@pytest.fixture(scope="module", autouse=True)
def default_database_guard() -> Iterator[None]:
    with owned.forbid_default_database():
        yield


@pytest.fixture(scope="module", autouse=True)
def initialize_database_for_tests() -> None:
    pass


@pytest.fixture(scope="module", autouse=True)
def prepare_database() -> None:
    pass


@pytest.fixture(autouse=True)
def clean_database() -> None:
    pass


def test_real_baseline_rows_survive_upgrade_downgrade_and_reupgrade() -> None:
    migration = _migration()
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    scripts = ScriptDirectory.from_config(config)
    tenant_id, user_id = uuid4(), uuid4()
    # This non-login fixture needs a valid hash; password policy is not under test.
    hashed_password = get_password_hash_sync(
        secrets.token_urlsafe(32), validate_policy=False
    )
    rows = [
        {
            "id": uuid4(),
            "user_id": user_id,
            "endpoint": f"https://example.invalid/test-push/{index}",
            "p256dh": "synthetic-key",
            "auth": "synthetic-auth",
        }
        for index in range(501)
    ]
    with (
        owned.owned_postgres_server() as server,
        owned.committed_baseline(server) as baseline,
    ):
        engine = sa.create_engine(baseline.url, hide_parameters=True)
        try:
            with engine.begin() as connection:
                connection.execute(
                    sa.text(
                        "INSERT INTO public.tenants (id, name, slug) "
                        "VALUES (:id, 'binding migration test', :slug)"
                    ),
                    {"id": tenant_id, "slug": f"binding-{tenant_id.hex}"},
                )
                connection.execute(
                    sa.text(
                        "INSERT INTO public.users (id, email, hashed_password, tenant_id) "
                        "VALUES (:id, :email, :hashed_password, :tenant_id)"
                    ),
                    {
                        "id": user_id,
                        "email": f"binding-{user_id.hex}@example.invalid",
                        "hashed_password": hashed_password,
                        "tenant_id": tenant_id,
                    },
                )
                connection.execute(
                    sa.text(
                        "INSERT INTO public.push_subscriptions "
                        "(id, user_id, endpoint, p256dh, auth) "
                        "VALUES (:id, :user_id, :endpoint, :p256dh, :auth)"
                    ),
                    rows,
                )
                original = connection.execute(
                    sa.text(
                        "SELECT id, user_id, endpoint, p256dh, auth, created_at, "
                        "user_agent, last_seen_at, topics "
                        "FROM public.push_subscriptions ORDER BY id"
                    )
                ).all()
                MigrationContext.configure(connection).stamp(
                    scripts, migration.down_revision
                )

            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "ALTER TABLE public.push_subscriptions ADD COLUMN binding_version BIGINT"
                )
                connection.execute(
                    sa.text(
                        "UPDATE public.push_subscriptions SET binding_version = 37 "
                        "WHERE id = :id"
                    ),
                    {"id": rows[0]["id"]},
                )
                with pytest.raises(sa.exc.DBAPIError), connection.begin_nested():
                    with Operations.context(MigrationContext.configure(connection)):
                        migration.upgrade()
                assert (
                    connection.scalar(
                        sa.text(
                            "SELECT binding_version FROM public.push_subscriptions "
                            "WHERE id = :id"
                        ),
                        {"id": rows[0]["id"]},
                    )
                    == 37
                )
                assert (
                    MigrationContext.configure(connection).get_current_revision()
                    == migration.down_revision
                )
                retained = connection.execute(
                    sa.text(
                        "SELECT id, user_id, endpoint, p256dh, auth, created_at, "
                        "user_agent, last_seen_at, topics "
                        "FROM public.push_subscriptions ORDER BY id"
                    )
                ).all()
                assert retained == original
                connection.exec_driver_sql(
                    "ALTER TABLE public.push_subscriptions DROP COLUMN binding_version"
                )

            with engine.begin() as connection:
                config.attributes["connection"] = connection
                try:
                    command.upgrade(config, "head")
                finally:
                    config.attributes.pop("connection", None)
                assert (
                    MigrationContext.configure(connection).get_current_revision()
                    == migration.revision
                )
                assert (
                    connection.scalar(
                        sa.text(
                            "SELECT count(*) FROM public.push_subscriptions "
                            "WHERE binding_version IS NULL"
                        )
                    )
                    == 501
                )
                column = next(
                    column
                    for column in sa.inspect(connection).get_columns(
                        "push_subscriptions", schema="public"
                    )
                    if column["name"] == "binding_version"
                )
                assert isinstance(column["type"], sa.BigInteger)
                assert column["nullable"] is True
                assert column["default"] is None

                new_row = {
                    "id": uuid4(),
                    "user_id": user_id,
                    "endpoint": "https://example.invalid/test-push/new",
                    "p256dh": "synthetic-key",
                    "auth": "synthetic-auth",
                }
                insert = sa.text(
                    "INSERT INTO public.push_subscriptions "
                    "(id, user_id, endpoint, p256dh, auth) "
                    "VALUES (:id, :user_id, :endpoint, :p256dh, :auth) "
                    "RETURNING binding_version"
                )
                assert connection.execute(insert, new_row).scalar_one() is None
                assert (
                    connection.execute(
                        sa.text(
                            "UPDATE public.push_subscriptions SET binding_version = :version "
                            "WHERE id = :id RETURNING binding_version"
                        ),
                        {"id": new_row["id"], "version": 2**31 + 1},
                    ).scalar_one()
                    == 2**31 + 1
                )
                with Operations.context(MigrationContext.configure(connection)):
                    migration.upgrade()
                assert (
                    connection.scalar(
                        sa.text(
                            "SELECT binding_version FROM public.push_subscriptions "
                            "WHERE id = :id"
                        ),
                        {"id": new_row["id"]},
                    )
                    == 2**31 + 1
                )

            with engine.begin() as connection:
                with Operations.context(MigrationContext.configure(connection)):
                    migration.downgrade()
                assert "binding_version" not in {
                    column["name"]
                    for column in sa.inspect(connection).get_columns(
                        "push_subscriptions", schema="public"
                    )
                }
                retained = connection.execute(
                    sa.text(
                        "SELECT id, user_id, endpoint, p256dh, auth, created_at, "
                        "user_agent, last_seen_at, topics "
                        "FROM public.push_subscriptions WHERE id != :new_id ORDER BY id"
                    ),
                    {"new_id": new_row["id"]},
                ).all()
                assert retained == original
                assert (
                    connection.scalar(
                        sa.text("SELECT count(*) FROM public.push_subscriptions")
                    )
                    == 502
                )
                for shape, extra_sql in (
                    ("TEXT", None),
                    ("BIGINT DEFAULT 0", None),
                    ("BIGINT NOT NULL DEFAULT 0", None),
                    ("BIGINT CHECK (binding_version >= 0)", None),
                    (
                        "BIGINT",
                        "CREATE UNIQUE INDEX test_binding_version_unique "
                        "ON public.push_subscriptions (binding_version)",
                    ),
                ):
                    shape_savepoint = connection.begin_nested()
                    try:
                        connection.exec_driver_sql(
                            "ALTER TABLE public.push_subscriptions "
                            f"ADD COLUMN binding_version {shape}"
                        )
                        if extra_sql is not None:
                            connection.exec_driver_sql(extra_sql)
                        with (
                            pytest.raises(sa.exc.DBAPIError),
                            connection.begin_nested(),
                        ):
                            with Operations.context(
                                MigrationContext.configure(connection)
                            ):
                                migration.upgrade()
                    finally:
                        shape_savepoint.rollback()

            with engine.begin() as connection:
                with Operations.context(MigrationContext.configure(connection)):
                    migration.upgrade()
                assert (
                    connection.scalar(
                        sa.text(
                            "SELECT count(*) FROM public.push_subscriptions "
                            "WHERE binding_version IS NULL"
                        )
                    )
                    == 502
                )
        finally:
            engine.dispose()
