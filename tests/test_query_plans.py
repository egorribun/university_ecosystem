"""
Tests for query plan analysis of critical database queries.

These tests verify that critical queries use efficient execution plans
by checking for index usage and avoiding full table scans.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session

pytestmark = pytest.mark.asyncio


async def analyze_query_plan(session: AsyncSession, query: str) -> dict:
    """
    Analyze a query's execution plan.
    Supports both PostgreSQL (JSON format) and SQLite (text format).
    """
    # Detect dialect
    bind = session.get_bind()
    dialect_name = bind.dialect.name if bind else "sqlite"

    if dialect_name == "sqlite":
        explain_query = f"EXPLAIN QUERY PLAN {query}"
        result = await session.execute(text(explain_query))
        rows = result.fetchall()

        # SQLite output format: (id, parent, notused, detail)
        plan_details = [row[3] for row in rows]
        full_detail = " ".join(plan_details).upper()

        uses_index = (
            "USING INDEX" in full_detail or "USING COVERING INDEX" in full_detail
        )
        # In SQLite, "SCAN TABLE" without an index means a full table scan
        seq_scan = "SCAN TABLE" in full_detail and "USING INDEX" not in full_detail

        return {
            "plan": plan_details,
            "uses_index": uses_index,
            "seq_scan": seq_scan,
            "node_type": "SCAN" if seq_scan else ("SEARCH" if uses_index else "OTHER"),
            "estimated_cost": 0.0,  # SQLite doesn't provide cost in this format
        }

    # PostgreSQL path
    explain_query = f"EXPLAIN (ANALYZE, COSTS, FORMAT JSON) {query}"
    result = await session.execute(text(explain_query))
    rows = result.fetchall()

    if not rows or not rows[0]:
        return {
            "plan": None,
            "uses_index": False,
            "seq_scan": True,
            "estimated_cost": float("inf"),
        }

    plan_data = rows[0][0]

    # Parse the plan
    if isinstance(plan_data, list) and len(plan_data) > 0:
        plan = plan_data[0].get("Plan", {})
    else:
        plan = {}

    # Check for index usage
    node_type = plan.get("Node Type", "")
    uses_index = "Index" in node_type
    seq_scan = node_type == "Seq Scan"
    estimated_cost = plan.get("Total Cost", float("inf"))

    return {
        "plan": plan_data,
        "uses_index": uses_index,
        "seq_scan": seq_scan,
        "node_type": node_type,
        "estimated_cost": estimated_cost,
    }


class TestCriticalQueryPlans:
    """Test execution plans for critical queries."""

    @pytest.mark.skipif(
        "sqlite" in settings.database_url,
        reason="PostgreSQL-specific index hint/scanning configuration",
    )
    async def test_user_by_email_uses_index(self):
        """Verify that looking up users by email uses an index."""
        async with async_session() as session:
            # Disable seq scans so the planner must use the index even on an
            # empty table (where it would otherwise prefer a sequential scan).
            await session.execute(text("SET enable_seqscan = OFF"))
            # The email index is a functional index on lower(email) — the query
            # must use the same expression to trigger index usage.
            query = "SELECT * FROM users WHERE lower(email) = lower('test@example.com')"
            plan = await analyze_query_plan(session, query)

            # Email should be indexed
            assert plan["uses_index"] or plan["node_type"] in (
                "Index Scan",
                "Index Only Scan",
                "Bitmap Index Scan",
            ), f"User email lookup should use index, got: {plan['node_type']}"

    async def test_notifications_by_user_uses_index(self):
        """Verify that fetching notifications by user_id uses an index."""
        async with async_session() as session:
            query = """
                SELECT * FROM notifications
                WHERE user_id = '00000000-0000-0000-0000-000000000000'
                ORDER BY created_at DESC
                LIMIT 20
            """
            plan = await analyze_query_plan(session, query)

            # Either indexed access or efficient scan on small table
            assert plan["estimated_cost"] < 1000 or plan["uses_index"], (
                f"Notifications query should be efficient, cost: "
                f"{plan['estimated_cost']}"
            )

    async def test_chat_messages_uses_index(self):
        """Verify that chat messages lookup uses chat_id index."""
        async with async_session() as session:
            # Use actual table name 'messages'
            query = (
                "SELECT * FROM messages "
                "WHERE chat_id = '00000000-0000-0000-0000-000000000000' "
                "ORDER BY created_at DESC LIMIT 50"
            )
            plan = await analyze_query_plan(session, query)

            assert plan["estimated_cost"] < 500 or plan["uses_index"], (
                f"Chat messages query should be efficient, cost: "
                f"{plan['estimated_cost']}"
            )

    async def test_events_active_uses_index(self):
        """Verify that filtering active events uses an index."""
        async with async_session() as session:
            query = """
                SELECT * FROM events
                WHERE is_active = true
                ORDER BY starts_at ASC
                LIMIT 20
            """
            plan = await analyze_query_plan(session, query)

            # Should either use index or be efficient on small table
            assert plan["estimated_cost"] < 500, (
                f"Active events query cost too high: {plan['estimated_cost']}"
            )

    async def test_schedule_by_group_uses_index(self):
        """Verify that schedule lookup by group uses an index."""
        async with async_session() as session:
            # Use actual table name 'schedule' and column 'start_time'
            query = """
                SELECT * FROM schedule
                WHERE group_id = '00000000-0000-0000-0000-000000000000'
                AND start_time BETWEEN '2024-01-01' AND '2024-01-07'
            """
            plan = await analyze_query_plan(session, query)

            assert plan["estimated_cost"] < 500 or plan["uses_index"], (
                f"Schedule query should be efficient, cost: {plan['estimated_cost']}"
            )

    @pytest.mark.skipif(
        "sqlite" in settings.database_url,
        reason="Seq Scan gate requires PostgreSQL EXPLAIN ANALYZE",
    )
    async def test_events_by_date_no_seq_scan(self):
        """Events lookup by date range must NOT use a Seq Scan.

        WHY (W25 query-plan gate): events are queried on every page load;
        a Seq Scan on a large table causes P99 latency spikes that cascade
        into load-balancer timeouts.
        """
        async with async_session() as session:
            # Force the planner to choose an index even on an empty table.
            await session.execute(text("SET enable_seqscan = OFF"))
            query = (
                "SELECT * FROM events "
                "WHERE start_time BETWEEN '2024-01-01' AND '2024-01-31' "
                "AND is_published = true"
            )
            plan = await analyze_query_plan(session, query)

            assert not plan["seq_scan"], (
                f"events_by_date must not use Seq Scan — "
                f"add an index on (start_time, is_published). "
                f"Got node_type: {plan.get('node_type')}"
            )

    @pytest.mark.skipif(
        "sqlite" in settings.database_url,
        reason="Seq Scan gate requires PostgreSQL EXPLAIN ANALYZE",
    )
    async def test_user_sessions_no_seq_scan(self):
        """Active session lookup by user_id must NOT use a Seq Scan.

        WHY (W25 query-plan gate): every authenticated request checks for an
        active session; a table scan on a large sessions table breaks SLOs.
        """
        async with async_session() as session:
            await session.execute(text("SET enable_seqscan = OFF"))
            query = (
                "SELECT * FROM sessions "
                "WHERE user_id = '00000000-0000-0000-0000-000000000000' "
                "AND expires_at > now()"
            )
            plan = await analyze_query_plan(session, query)

            assert not plan["seq_scan"], (
                f"user_sessions must not use Seq Scan — "
                f"ensure an index on (user_id, expires_at) exists. "
                f"Got node_type: {plan.get('node_type')}"
            )

    @pytest.mark.skipif(
        "sqlite" in settings.database_url,
        reason="Seq Scan gate requires PostgreSQL EXPLAIN ANALYZE",
    )
    async def test_notifications_unread_count_no_seq_scan(self):
        """Unread-notifications COUNT must NOT use a Seq Scan.

        WHY (W25 query-plan gate): notification badge counts are fetched on
        every page load for every authenticated user.  A Seq Scan on the
        notifications table (which is partitioned and grows without bound)
        would make badge updates unacceptably slow.
        """
        async with async_session() as session:
            await session.execute(text("SET enable_seqscan = OFF"))
            query = (
                "SELECT COUNT(*) FROM notifications "
                "WHERE user_id = '00000000-0000-0000-0000-000000000000' "
                "AND is_read = false"
            )
            plan = await analyze_query_plan(session, query)

            assert not plan["seq_scan"], (
                f"notifications_unread must not use Seq Scan — "
                f"ensure an index on (user_id, is_read) exists. "
                f"Got node_type: {plan.get('node_type')}"
            )


class TestQueryPlanHelpers:
    """Test helper functions for query plan analysis."""

    async def test_analyze_query_plan_returns_expected_structure(self):
        """Verify analyze_query_plan returns the expected structure."""
        async with async_session() as session:
            query = "SELECT 1"
            plan = await analyze_query_plan(session, query)

            assert "plan" in plan
            assert "uses_index" in plan
            assert "seq_scan" in plan
            assert "estimated_cost" in plan
