import pytest
from sqlalchemy import select

import app.models as models
from scripts.seed_admin_data import AUDIT_ACTIONS, seed_audit_logs

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_seed_audit_logs_is_idempotent(db_session, user_factory, monkeypatch):
    monkeypatch.setenv("AUDIT_LOG_SECRET", "test-audit-signing-key")
    admin = await user_factory(role="admin")
    other = await user_factory(role="student")

    async def demo_seed_logs():
        result = await db_session.scalars(select(models.DataAccessLog))
        return [
            row
            for row in result.all()
            if row.context and row.context.get("demo_seed") is True
        ]

    await seed_audit_logs(db_session, admin, [other])
    first_run_logs = await demo_seed_logs()
    assert len(first_run_logs) == len(AUDIT_ACTIONS)
    await db_session.commit()

    await seed_audit_logs(db_session, admin, [other])
    second_run_logs = await demo_seed_logs()

    assert len(second_run_logs) == len(first_run_logs)
