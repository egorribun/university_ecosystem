"""Runtime checks for push subscription schema helpers."""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy import text

from app.core.database import Base, async_session, engine
from app.services import push_schema as push_schema_module
from app.services.push_schema import ensure_push_subscription_schema


def _reset_flags(monkeypatch):
    monkeypatch.setattr(push_schema_module, "_async_ready", False)
    monkeypatch.setattr(push_schema_module, "_sync_ready", False)


@pytest.mark.asyncio
async def test_ensure_push_subscription_schema_upgrades_existing_table(
    monkeypatch,
) -> None:
    _reset_flags(monkeypatch)

    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS push_subscriptions"))
        await conn.execute(
            text(
                """
                CREATE TABLE push_subscriptions (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    endpoint TEXT,
                    p256dh VARCHAR(200) NOT NULL,
                    auth VARCHAR(200) NOT NULL
                )
                """
            )
        )

    async with async_session() as session:
        await ensure_push_subscription_schema(session)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        def _assert_schema(sync_conn):
            inspector = sa.inspect(sync_conn)
            columns = {
                column["name"] for column in inspector.get_columns("push_subscriptions")
            }
            assert {
                "endpoint",
                "user_agent",
                "last_seen_at",
                "created_at",
                "topics",
            }.issubset(columns)
            created_at = next(
                (
                    col
                    for col in inspector.get_columns("push_subscriptions")
                    if col["name"] == "created_at"
                ),
                None,
            )
            assert created_at is not None
            assert created_at.get("default") is not None
            topics = next(
                (
                    col
                    for col in inspector.get_columns("push_subscriptions")
                    if col["name"] == "topics"
                ),
                None,
            )
            assert topics is not None
            assert topics.get("default") is not None

        await conn.run_sync(_assert_schema)
