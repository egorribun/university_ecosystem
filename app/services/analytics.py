"""Polars analytics service for high-performance data analysis.

This module provides a Polars-based analytics engine that is 10-100x faster
than pandas for aggregations and complex queries.

Features:
- Direct SQL queries against DataFrames
- Lazy evaluation for query optimization
- Async-friendly via thread pool
- Memory-efficient columnar storage
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import TYPE_CHECKING, Any

import polars as pl

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Thread pool for CPU-bound Polars operations
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="polars")


class AnalyticsService:
    """High-performance analytics using Polars DataFrames."""

    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = database_url

    async def get_news_stats(
        self,
        session: AsyncSession,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict[str, Any]:
        """Get news article statistics.

        Args:
            session: Database session
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Dictionary with news statistics
        """
        import asyncio

        from sqlalchemy import text

        # Build query
        query = """
            SELECT
                id, title, created_at, likes_count, comments_count,
                DATE_TRUNC('day', created_at) as date
            FROM news
            WHERE 1=1
        """
        params: dict[str, Any] = {}

        if start_date:
            query += " AND created_at >= :start_date"
            params["start_date"] = start_date
        if end_date:
            query += " AND created_at <= :end_date"
            params["end_date"] = end_date

        result = await session.execute(text(query), params)
        rows = result.fetchall()

        if not rows:
            return {"total": 0, "by_date": [], "top_liked": []}

        # Process with Polars in thread pool
        loop = asyncio.get_event_loop()
        stats = await loop.run_in_executor(
            _executor,
            partial(self._compute_news_stats, rows, result.keys()),
        )
        return stats

    def _compute_news_stats(
        self,
        rows: list,
        columns: list[str],
    ) -> dict[str, Any]:
        """Compute news statistics using Polars (runs in thread pool)."""
        df = pl.DataFrame(
            [dict(zip(columns, row, strict=False)) for row in rows],
        )

        # Daily aggregation
        by_date = (
            df.group_by("date")
            .agg(
                [
                    pl.len().alias("count"),
                    pl.col("likes_count").sum().alias("total_likes"),
                    pl.col("comments_count").sum().alias("total_comments"),
                ]
            )
            .sort("date")
        )

        # Top liked articles
        top_liked = (
            df.sort("likes_count", descending=True)
            .head(10)
            .select(["id", "title", "likes_count"])
        )

        return {
            "total": len(df),
            "total_likes": df["likes_count"].sum(),
            "total_comments": df["comments_count"].sum(),
            "by_date": by_date.to_dicts(),
            "top_liked": top_liked.to_dicts(),
        }

    async def get_events_stats(
        self,
        session: AsyncSession,
        start_date: datetime | None = None,
    ) -> dict[str, Any]:
        """Get event statistics with attendance analysis.

        Args:
            session: Database session
            start_date: Optional start date filter

        Returns:
            Dictionary with event statistics
        """
        import asyncio

        from sqlalchemy import text

        query = """
            SELECT
                e.id, e.title, e.start_time, e.location,
                COUNT(ea.user_id) as attendees_count,
                e.max_attendees
            FROM events e
            LEFT JOIN event_attendees ea ON e.id = ea.event_id
            WHERE e.is_active = true
        """
        params: dict[str, Any] = {}

        if start_date:
            query += " AND e.start_time >= :start_date"
            params["start_date"] = start_date

        query += " GROUP BY e.id, e.title, e.start_time, e.location, e.max_attendees"

        result = await session.execute(text(query), params)
        rows = result.fetchall()

        if not rows:
            return {"total": 0, "by_location": [], "popular": []}

        loop = asyncio.get_event_loop()
        stats = await loop.run_in_executor(
            _executor,
            partial(self._compute_events_stats, rows, result.keys()),
        )
        return stats

    def _compute_events_stats(
        self,
        rows: list,
        columns: list[str],
    ) -> dict[str, Any]:
        """Compute event statistics using Polars."""
        df = pl.DataFrame(
            [dict(zip(columns, row, strict=False)) for row in rows],
        )

        # By location
        by_location = (
            df.group_by("location")
            .agg(
                [
                    pl.len().alias("event_count"),
                    pl.col("attendees_count").sum().alias("total_attendees"),
                ]
            )
            .sort("total_attendees", descending=True)
            .head(10)
        )

        # Most popular events
        popular = (
            df.sort("attendees_count", descending=True)
            .head(10)
            .select(["id", "title", "attendees_count", "max_attendees"])
        )

        return {
            "total": len(df),
            "total_attendees": df["attendees_count"].sum(),
            "by_location": by_location.to_dicts(),
            "popular": popular.to_dicts(),
        }

    async def get_user_activity(
        self,
        session: AsyncSession,
        user_id: int,
    ) -> dict[str, Any]:
        """Get user activity summary.

        Args:
            session: Database session
            user_id: User ID

        Returns:
            Dictionary with user activity data
        """
        from sqlalchemy import text

        # Get user's activity in one query
        query = text(
            """
            SELECT
                'news_created' as type, COUNT(*) as count
            FROM news WHERE author_id = :user_id
            UNION ALL
            SELECT
                'events_attended' as type, COUNT(*) as count
            FROM event_attendees WHERE user_id = :user_id
            UNION ALL
            SELECT
                'messages_sent' as type, COUNT(*) as count
            FROM messages WHERE sender_id = :user_id
        """
        )

        result = await session.execute(query, {"user_id": user_id})
        rows = result.fetchall()

        return {row[0]: row[1] for row in rows}


# Singleton instance
_analytics_service: AnalyticsService | None = None


def get_analytics_service() -> AnalyticsService:
    """Get the configured analytics service instance."""
    global _analytics_service
    if _analytics_service is None:
        _analytics_service = AnalyticsService()
    return _analytics_service


__all__ = ["AnalyticsService", "get_analytics_service"]
