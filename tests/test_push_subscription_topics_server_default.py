"""BE-02: the push subscription topics default must match the PostgreSQL catalog."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.models.notifications import PushSubscription


def test_push_subscription_topics_declares_the_catalog_json_default() -> None:
    """PostgreSQL reports the migrated default as '[]'::json, so the model must match."""
    server_default = PushSubscription.__table__.c.topics.server_default

    assert server_default is not None
    # Alembic compares server defaults by compiling the model expression for the
    # connected dialect, so the PostgreSQL rendering must equal the catalog text.
    compiled = server_default.arg.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    )
    assert str(compiled) == "'[]'::json"


def test_push_subscription_topics_default_applies_to_raw_sqlite_inserts() -> None:
    """Raw SQL that omits topics receives the DDL default, not the ORM list factory."""
    engine = sa.create_engine("sqlite://")
    try:
        PushSubscription.__table__.create(engine)
        user_id = str(uuid.uuid4())
        with engine.begin() as connection:
            # The foreign key target only needs its key column for this insert.
            connection.exec_driver_sql(
                "CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)"
            )
            connection.exec_driver_sql("INSERT INTO users (id) VALUES (?)", (user_id,))
            connection.exec_driver_sql(
                "INSERT INTO push_subscriptions "
                "(id, user_id, endpoint, p256dh, auth) VALUES (?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()),
                    user_id,
                    "https://push.example/subscription",
                    "p256dh-key",
                    "auth-secret",
                ),
            )
            stored = connection.exec_driver_sql(
                "SELECT topics FROM push_subscriptions"
            ).scalar_one()
    finally:
        engine.dispose()

    assert stored == "[]"


def test_push_subscription_topics_keeps_its_application_list_default() -> None:
    """The ORM still supplies a fresh list per row, not a shared mutable literal."""
    default = PushSubscription.__table__.c.topics.default

    assert default is not None
    assert default.is_callable


def test_push_subscription_topics_ddl_carries_the_json_default() -> None:
    ddl = str(
        CreateTable(PushSubscription.__table__).compile(dialect=postgresql.dialect())
    )

    assert "topics JSON DEFAULT '[]'::json NOT NULL" in ddl
