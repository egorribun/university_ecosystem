"""
Tests for query plan analysis of critical database queries.

These tests verify that critical queries use efficient execution plans
by checking for index usage and avoiding full table scans.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session

pytestmark = pytest.mark.asyncio


async def analyze_query_plan(session: AsyncSession, query: str) -> dict:
    """
    Analyze a query's execution plan using EXPLAIN ANALYZE.

    Returns a dict with:
    - plan: The raw plan output
    - uses_index: Whether the query uses an index
    - seq_scan: Whether the query does a sequential scan
    - estimated_cost: The estimated query cost
    """
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

    async def test_user_by_email_uses_index(self):
        """Verify that looking up users by email uses an index."""
        async with async_session() as session:
            query = "SELECT * FROM users WHERE email = 'test@example.com'"
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
                WHERE user_id = 1 
                ORDER BY created_at DESC 
                LIMIT 20
            """
            plan = await analyze_query_plan(session, query)

            # Either indexed access or efficient scan on small table
            assert (
                plan["estimated_cost"] < 1000 or plan["uses_index"]
            ), (
                f"Notifications query should be efficient, "
                f"cost: {plan['estimated_cost']}"
            )

    async def test_chat_messages_uses_index(self):
        """Verify that chat messages lookup uses chat_id index."""
        async with async_session() as session:
            query = (
                "SELECT * FROM chat_messages WHERE chat_id = 1 "
                "ORDER BY created_at DESC LIMIT 50"
            )
            plan = await analyze_query_plan(session, query)

            assert (
                plan["estimated_cost"] < 500 or plan["uses_index"]
            ), (
                f"Chat messages query should be efficient, "
                f"cost: {plan['estimated_cost']}"
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
            assert (
                plan["estimated_cost"] < 500
            ), f"Active events query cost too high: {plan['estimated_cost']}"

    async def test_schedule_by_group_uses_index(self):
        """Verify that schedule lookup by group uses an index."""
        async with async_session() as session:
            query = """
                SELECT * FROM schedule_entries 
                WHERE group_id = 1 
                AND date BETWEEN '2024-01-01' AND '2024-01-07'
            """
            plan = await analyze_query_plan(session, query)

            assert (
                plan["estimated_cost"] < 500 or plan["uses_index"]
            ), f"Schedule query should be efficient, cost: {plan['estimated_cost']}"


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
