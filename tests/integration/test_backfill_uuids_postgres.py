"""Real PostgreSQL rejection at the UUID backfill status boundary.

This synthetic transitional table is not the current application schema.
The owned server supplies disposable credentials; no operator URL is accepted.
"""

from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.scripts import backfill_uuids
from tests.fixtures import owned_baseline_postgres as owned

initialize_database_for_tests = owned.initialize_database_for_tests
prepare_database = owned.prepare_database
clean_database = owned.clean_database
default_database_guard = owned.default_database_guard
owned_baseline_server = owned.owned_baseline_server

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="Set RUN_INTEGRATION_TESTS=1 for owned PostgreSQL coverage",
    ),
    pytest.mark.timeout(240, method="signal"),
]


class _Base(DeclarativeBase):
    pass


class _TransitionRow(_Base):
    __tablename__ = "backfill_status_probe"
    __table_args__ = (
        sa.CheckConstraint("uuid_id IS NULL", name="backfill_reject_generated_uuid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    uuid_id: Mapped[UUID | None] = mapped_column(sa.Uuid, nullable=True)


@pytest.mark.asyncio
async def test_backfill_real_constraint_rejection_rolls_back_and_returns_failure(
    owned_baseline_server, default_database_guard, monkeypatch
):
    facts = {
        "attempted_update": 0,
        "constraint_rejection": 0,
        "rollback_completed": 0,
        "error_logged": 0,
    }

    class ObservedSession(AsyncSession):
        async def rollback(self):
            await super().rollback()
            facts["rollback_completed"] += 1

    def observe_update(_connection, _cursor, _statement, _parameters, context, _many):
        compiled = context.compiled
        if (
            compiled is not None
            and compiled.isupdate
            and compiled.statement.table.name == _TransitionRow.__tablename__
        ):
            facts["attempted_update"] += 1

    def observe_error(context):
        original = context.original_exception
        if (
            getattr(original, "sqlstate", None) == "23514"
            and getattr(getattr(original, "diag", None), "constraint_name", None)
            == "backfill_reject_generated_uuid"
        ):
            facts["constraint_rejection"] += 1

    def safe_error(_message, *_args):
        # Deliberately never format/store the driver's error or parameters.
        facts["error_logged"] += 1

    monkeypatch.setattr(backfill_uuids, "configure_logging", lambda: None)
    monkeypatch.setattr(
        backfill_uuids,
        "logger",
        SimpleNamespace(info=lambda *_args: None, error=safe_error),
    )
    monkeypatch.setattr(backfill_uuids, "TABLES_OWN_ID", [(_TransitionRow, None)])

    try:
        with owned.committed_baseline(owned_baseline_server) as database:
            engine = create_async_engine(
                database.url,
                poolclass=sa.pool.NullPool,
                hide_parameters=True,
                connect_args={"connect_timeout": 5},
            )
            try:
                async with engine.begin() as connection:
                    await connection.run_sync(_Base.metadata.create_all)
                    await connection.execute(
                        sa.insert(_TransitionRow).values(id=1, uuid_id=None)
                    )
                sa.event.listen(
                    engine.sync_engine, "before_cursor_execute", observe_update
                )
                sa.event.listen(engine.sync_engine, "handle_error", observe_error)
                factory = async_sessionmaker(
                    engine, class_=ObservedSession, expire_on_commit=False
                )
                monkeypatch.setattr(backfill_uuids, "async_session", factory)
                async with asyncio.timeout(30):
                    result = await backfill_uuids.main()
                assert result == 1
                assert facts == {
                    "attempted_update": 1,
                    "constraint_rejection": 1,
                    "rollback_completed": 1,
                    "error_logged": 1,
                }
                # NullPool makes this a fresh physical connection after main's
                # session/context exit, not a retained identity-map observation.
                async with engine.connect() as observer:
                    rows = (
                        await observer.execute(
                            sa.select(_TransitionRow.id, _TransitionRow.uuid_id)
                        )
                    ).all()
                    assert [tuple(row) for row in rows] == [(1, None)]
                assert default_database_guard == []
            finally:
                await engine.dispose()
    except sa.exc.SQLAlchemyError:
        # Setup/observer/cleanup failures must not print DSNs or driver payloads.
        raise AssertionError("Owned backfill PostgreSQL operation failed") from None
