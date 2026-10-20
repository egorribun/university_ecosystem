"""Exercise generic VectorService score filtering against real pgvector."""

from __future__ import annotations

import math
import os
from datetime import UTC, datetime

import pytest
from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Column, DateTime, Integer, MetaData, Table, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import registry

from app.core.config import settings
from app.services.vector_service import VectorService

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="Set RUN_INTEGRATION_TESTS=1 for the owned PostgreSQL regression",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("limit", "min_score", "expected_ids", "expected_scores"),
    [
        (2, 0.5, [10, 11], [0.8, 0.6]),
        (10, 0.75, [10], [0.8]),
        (10, -0.75, [10, 11, 12, 13, 14], [0.8, 0.6, 2 / math.sqrt(13), 0.0, -0.6]),
    ],
    ids=["fills-limit", "preserves-threshold", "keeps-finite-zero-and-negative"],
)
async def test_vector_service_filters_nan_before_limit(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    limit: int,
    min_score: float,
    expected_ids: list[int],
    expected_scores: list[float],
) -> None:
    assert db_session.get_bind().dialect.name == "postgresql"
    monkeypatch.setattr(settings, "semantic_search_enabled", True)
    monkeypatch.setattr(settings, "embedding_api_base", "http://localhost")
    monkeypatch.setattr(settings, "embedding_api_key", "")

    table = Table(
        "aud257_vector_items",
        MetaData(),
        Column("id", Integer, primary_key=True),
        Column("embedding", Vector(2), nullable=False),
        Column("is_active", Boolean, nullable=False),
        Column("deleted_at", DateTime(timezone=True)),
        prefixes=["TEMPORARY"],
        postgresql_on_commit="DROP",
    )
    class_registry = registry()

    class VectorItem:
        pass

    try:
        class_registry.map_imperatively(VectorItem, table)
        connection = await db_session.connection()
        await connection.run_sync(table.create)
        rows = [
            (1, [0.0, 0.0], True, None),
            (2, [0.0, 0.0], True, None),
            (10, [4.0, 3.0], True, None),
            (11, [3.0, 4.0], True, None),
            (12, [2.0, 3.0], True, None),
            (13, [0.0, 1.0], True, None),
            (14, [-3.0, 4.0], True, None),
            (20, [1.0, 0.0], False, None),
            (21, [1.0, 0.0], True, datetime(2026, 1, 1, tzinfo=UTC)),
        ]
        await db_session.execute(
            table.insert(),
            [
                {
                    "id": item_id,
                    "embedding": embedding,
                    "is_active": is_active,
                    "deleted_at": deleted_at,
                }
                for item_id, embedding, is_active, deleted_at in rows
            ],
        )

        # A legal zero vector yields a NaN cosine score. Without the finite SQL
        # predicates, PostgreSQL admits it through the threshold and ranks it first.
        distance = table.c.embedding.cosine_distance([1.0, 0.0])
        score = (1.0 - distance).label("similarity_score")
        unguarded = (
            await db_session.execute(
                select(table.c.id, score)
                .where(
                    score >= min_score,
                    table.c.is_active.is_(True),
                    table.c.deleted_at.is_(None),
                )
                .order_by(score.desc())
                .limit(2)
            )
        ).all()
        assert {row[0] for row in unguarded} == {1, 2}
        assert all(math.isnan(float(row[1])) for row in unguarded)

        async with VectorService(db_session) as service:
            results = await service.search_similar_with_scores(
                VectorItem, [1.0, 0.0], limit=limit, min_score=min_score
            )

        assert [item.id for item, _ in results] == expected_ids
        assert [score for _, score in results] == pytest.approx(expected_scores)
        assert all(math.isfinite(score) for _, score in results)
    finally:
        try:
            await db_session.rollback()
        finally:
            class_registry.dispose()
