"""Prove exclusive news image claims and migration preservation on PostgreSQL."""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.models as models
from app.core import database
from app.repositories.news_repository import NewsRepository

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION_PATH = (
    _PROJECT_ROOT
    / "alembic"
    / "versions"
    / "202610120002_add_news_media_asset_ownership.py"
)
_RUN_INTEGRATION_TESTS = os.getenv("RUN_INTEGRATION_TESTS") == "1"
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _RUN_INTEGRATION_TESTS,
        reason="Set RUN_INTEGRATION_TESTS=1 for the owned PostgreSQL integration",
    ),
]


def _load_ownership_migration():
    spec = importlib.util.spec_from_file_location(
        "news_media_asset_ownership_migration", _MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_two_concurrent_news_claims_serialize_on_one_asset(
    db_session, user_factory
):
    assert db_session.bind.dialect.name == "postgresql"
    owner = await user_factory(role="admin")
    image_url = "/static/news_images/news_0123456789abcdef0123456789abcdef.jpg"
    news_a = models.News(title="Concurrent A", content="Body")
    news_b = models.News(title="Concurrent B", content="Body")
    asset = models.NewsMediaAsset(storage_url=image_url, owner_user_id=owner.id)
    db_session.add_all([news_a, news_b, asset])
    await db_session.commit()

    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    start_claims = asyncio.Barrier(2)

    async def claim(news_id):
        async with session_factory() as session:
            await start_claims.wait()
            claimed = await NewsRepository(session).claim_news_media_asset(
                image_url,
                owner_user_id=owner.id,
                news_id=news_id,
            )
            if claimed:
                await session.commit()
            else:
                await session.rollback()
            return claimed

    outcomes = await asyncio.gather(claim(news_a.id), claim(news_b.id))
    assert sorted(outcomes) == [False, True]

    async with session_factory() as reader:
        stored_asset = await reader.scalar(
            select(models.NewsMediaAsset).where(
                models.NewsMediaAsset.storage_url == image_url
            )
        )
        assert stored_asset is not None
        assert stored_asset.owner_user_id == owner.id
        assert stored_asset.news_id in {news_a.id, news_b.id}


@pytest.mark.asyncio
async def test_migration_keeps_populated_claim_across_downgrade_and_reupgrade():
    assert database.engine.dialect.name == "postgresql"
    migration = _load_ownership_migration()
    schema = f"aud180_media_{uuid4().hex}"
    owner_id = uuid4()
    news_id = uuid4()
    other_news_id = uuid4()
    asset_id = uuid4()
    image_url = "/static/news_images/news_0123456789abcdef0123456789abcdef.jpg"

    def exercise(connection: sa.Connection) -> None:
        connection.execute(sa.schema.CreateSchema(schema))
        connection.execute(
            sa.text("SELECT set_config('search_path', :schema, true)"),
            {"schema": schema},
        )
        connection.exec_driver_sql("CREATE TABLE users (id UUID PRIMARY KEY)")
        connection.exec_driver_sql("CREATE TABLE news (id UUID PRIMARY KEY)")
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            connection.execute(
                sa.text("INSERT INTO users (id) VALUES (:id)"), {"id": owner_id}
            )
            connection.execute(
                sa.text("INSERT INTO news (id) VALUES (:id)"), {"id": news_id}
            )
            connection.execute(
                sa.text("INSERT INTO news (id) VALUES (:id)"),
                {"id": other_news_id},
            )
            connection.execute(
                sa.text(
                    "INSERT INTO news_media_assets "
                    "(id, storage_url, owner_user_id, news_id) "
                    "VALUES (:id, :url, :owner, :news)"
                ),
                {
                    "id": asset_id,
                    "url": image_url,
                    "owner": owner_id,
                    "news": news_id,
                },
            )

            migration.downgrade()
            assert sa.inspect(connection).has_table("news_media_assets", schema=schema)
            migration.upgrade()

            stored = connection.execute(
                sa.text(
                    "SELECT id, storage_url, owner_user_id, news_id "
                    "FROM news_media_assets WHERE id = :id"
                ),
                {"id": asset_id},
            ).one()
            assert stored == (asset_id, image_url, owner_id, news_id)

            duplicate_claims = (
                {
                    "id": uuid4(),
                    "url": (
                        "/static/news_images/news_11111111111111111111111111111111.jpg"
                    ),
                    "owner": owner_id,
                    "news": news_id,
                },
                {
                    "id": uuid4(),
                    "url": image_url,
                    "owner": owner_id,
                    "news": other_news_id,
                },
            )
            insert = sa.text(
                "INSERT INTO news_media_assets "
                "(id, storage_url, owner_user_id, news_id) "
                "VALUES (:id, :url, :owner, :news)"
            )
            for values in duplicate_claims:
                with pytest.raises(sa.exc.IntegrityError):
                    with connection.begin_nested():
                        connection.execute(insert, values)

        connection.execute(sa.schema.DropSchema(schema, cascade=True))

    async with database.engine.begin() as connection:
        await connection.run_sync(exercise)


@pytest.mark.asyncio
async def test_migration_rejects_malformed_existing_table_before_schema_writes():
    assert database.engine.dialect.name == "postgresql"
    migration = _load_ownership_migration()
    schema = f"aud180_bad_media_{uuid4().hex}"

    def exercise(connection: sa.Connection) -> None:
        connection.execute(sa.schema.CreateSchema(schema))
        connection.execute(
            sa.text("SELECT set_config('search_path', :schema, true)"),
            {"schema": schema},
        )
        connection.exec_driver_sql(
            "CREATE TABLE news_media_assets "
            "(id UUID PRIMARY KEY, storage_url TEXT NOT NULL)"
        )
        before_tables = set(sa.inspect(connection).get_table_names(schema=schema))
        with Operations.context(MigrationContext.configure(connection)):
            with pytest.raises(RuntimeError, match="unexpected columns"):
                migration.upgrade()

        inspector = sa.inspect(connection)
        assert set(inspector.get_table_names(schema=schema)) == before_tables
        assert [
            column["name"]
            for column in inspector.get_columns("news_media_assets", schema=schema)
        ] == ["id", "storage_url"]
        assert inspector.get_indexes("news_media_assets", schema=schema) == []
        connection.execute(sa.schema.DropSchema(schema, cascade=True))

    async with database.engine.begin() as connection:
        await connection.run_sync(exercise)


@pytest.mark.parametrize(
    ("storage_url_unique", "index_sql", "message"),
    [
        (
            "UNIQUE (storage_url) DEFERRABLE INITIALLY IMMEDIATE",
            None,
            "deferrable constraints",
        ),
        (
            "UNIQUE (storage_url) DEFERRABLE INITIALLY DEFERRED",
            None,
            "deferrable constraints",
        ),
        (
            "UNIQUE NULLS NOT DISTINCT (storage_url)",
            None,
            "modified unique constraints",
        ),
        (
            "",
            "CREATE INDEX ix_news_media_assets_owner_user_id "
            "ON news_media_assets (owner_user_id) "
            "WHERE owner_user_id IS NOT NULL",
            "modified indexes",
        ),
        (
            "",
            "CREATE INDEX ix_news_media_assets_owner_user_id "
            "ON news_media_assets (owner_user_id) INCLUDE (storage_url)",
            "modified indexes",
        ),
        (
            "",
            "CREATE INDEX ix_news_media_assets_owner_user_id "
            "ON news_media_assets ((owner_user_id::text))",
            "modified indexes",
        ),
        (
            "",
            "CREATE INDEX ix_news_media_assets_owner_user_id "
            "ON news_media_assets (owner_user_id) WITH (fillfactor=80)",
            "modified indexes",
        ),
        (
            "",
            "CREATE INDEX ix_news_media_assets_owner_user_id "
            "ON news_media_assets (owner_user_id DESC)",
            "modified indexes",
        ),
    ],
    ids=(
        "deferrable-initially-immediate",
        "deferrable-initially-deferred",
        "nulls-not-distinct",
        "partial-index",
        "include-index",
        "expression-index",
        "storage-option-index",
        "sort-option-index",
    ),
)
@pytest.mark.asyncio
async def test_migration_rejects_noncanonical_constraint_or_index_options(
    storage_url_unique: str, index_sql: str | None, message: str
):
    assert database.engine.dialect.name == "postgresql"
    migration = _load_ownership_migration()
    schema = f"aud180_bad_options_{uuid4().hex}"

    def exercise(connection: sa.Connection) -> None:
        connection.execute(sa.schema.CreateSchema(schema))
        connection.execute(
            sa.text("SELECT set_config('search_path', :schema, true)"),
            {"schema": schema},
        )
        connection.exec_driver_sql("CREATE TABLE users (id UUID PRIMARY KEY)")
        connection.exec_driver_sql("CREATE TABLE news (id UUID PRIMARY KEY)")
        connection.exec_driver_sql(
            "CREATE TABLE news_media_assets ("
            "id UUID NOT NULL, "
            "storage_url VARCHAR(2048) NOT NULL, "
            "owner_user_id UUID NULL, "
            "news_id UUID NULL, "
            "created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, "
            "CONSTRAINT news_media_assets_pkey PRIMARY KEY (id), "
            "CONSTRAINT uq_news_media_asset_storage_url "
            + (storage_url_unique or "UNIQUE (storage_url)")
            + ", "
            "CONSTRAINT uq_news_media_asset_news_id UNIQUE (news_id), "
            "CONSTRAINT news_media_assets_owner_user_id_fkey "
            "FOREIGN KEY (owner_user_id) REFERENCES users (id) ON DELETE SET NULL, "
            "CONSTRAINT news_media_assets_news_id_fkey "
            "FOREIGN KEY (news_id) REFERENCES news (id) ON DELETE SET NULL"
            ")"
        )
        effective_index_sql = index_sql
        if effective_index_sql is None:
            effective_index_sql = (
                "CREATE INDEX ix_news_media_assets_owner_user_id "
                "ON news_media_assets (owner_user_id)"
            )
        connection.exec_driver_sql(effective_index_sql)

        inspector = sa.inspect(connection)
        before = (
            tuple(inspector.get_table_names(schema=schema)),
            tuple(
                column["name"]
                for column in inspector.get_columns("news_media_assets", schema=schema)
            ),
            inspector.get_pk_constraint("news_media_assets", schema=schema),
            tuple(inspector.get_unique_constraints("news_media_assets", schema=schema)),
            tuple(inspector.get_foreign_keys("news_media_assets", schema=schema)),
            tuple(
                (
                    index["name"],
                    index.get("column_names"),
                    index.get("unique"),
                    index.get("include_columns"),
                    index.get("dialect_options"),
                    index.get("column_sorting"),
                    index.get("expressions"),
                )
                for index in inspector.get_indexes("news_media_assets", schema=schema)
            ),
        )
        with Operations.context(MigrationContext.configure(connection)):
            with pytest.raises(RuntimeError, match=message):
                migration.upgrade()

        inspector = sa.inspect(connection)
        after = (
            tuple(inspector.get_table_names(schema=schema)),
            tuple(
                column["name"]
                for column in inspector.get_columns("news_media_assets", schema=schema)
            ),
            inspector.get_pk_constraint("news_media_assets", schema=schema),
            tuple(inspector.get_unique_constraints("news_media_assets", schema=schema)),
            tuple(inspector.get_foreign_keys("news_media_assets", schema=schema)),
            tuple(
                (
                    index["name"],
                    index.get("column_names"),
                    index.get("unique"),
                    index.get("include_columns"),
                    index.get("dialect_options"),
                    index.get("column_sorting"),
                    index.get("expressions"),
                )
                for index in inspector.get_indexes("news_media_assets", schema=schema)
            ),
        )
        assert after == before
        connection.execute(sa.schema.DropSchema(schema, cascade=True))

    async with database.engine.begin() as connection:
        await connection.run_sync(exercise)


@pytest.mark.asyncio
async def test_concurrent_news_image_swaps_reject_without_lock_deadlock(
    db_session, user_factory, monkeypatch
):
    assert db_session.bind.dialect.name == "postgresql"

    from unittest.mock import AsyncMock

    from app.repositories.unit_of_work import uow_from_session
    from app.schemas import schemas
    from app.services.news_service import NewsImageOwnershipError, NewsService

    owner = await user_factory(role="admin")
    image_a = f"/static/news_images/news_{uuid4().hex}.jpg"
    image_b = f"/static/news_images/news_{uuid4().hex}.jpg"
    news_a = models.News(title="Swap A", content="Body", image_url=image_a)
    news_b = models.News(title="Swap B", content="Body", image_url=image_b)
    asset_a = models.NewsMediaAsset(storage_url=image_a, owner_user_id=owner.id)
    asset_b = models.NewsMediaAsset(storage_url=image_b, owner_user_id=owner.id)
    db_session.add_all([news_a, news_b, asset_a, asset_b])
    await db_session.flush()
    asset_a.news_id = news_a.id
    asset_b.news_id = news_b.id
    await db_session.commit()

    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    start_updates = asyncio.Barrier(2)
    released_asset_barrier = asyncio.Barrier(2)
    original_release = NewsRepository.release_news_media_asset

    async def release_then_wait(repository, news_id):
        await original_release(repository, news_id)
        await released_asset_barrier.wait()

    monkeypatch.setattr(NewsRepository, "release_news_media_asset", release_then_wait)

    async def replace_image(news_id, requested_image_url):
        async with session_factory() as session:
            await session.execute(sa.text("SET LOCAL statement_timeout = '5s'"))
            await start_updates.wait()
            service = NewsService(uow_from_session(session), AsyncMock())
            return await service.update_news(
                news_id,
                schemas.NewsUpdate(image_url=requested_image_url),
                owner_user_id=owner.id,
            )

    outcomes = await asyncio.wait_for(
        asyncio.gather(
            replace_image(news_a.id, image_b),
            replace_image(news_b.id, image_a),
            return_exceptions=True,
        ),
        timeout=12,
    )
    assert len(outcomes) == 2
    assert all(isinstance(outcome, NewsImageOwnershipError) for outcome in outcomes), [
        (
            type(outcome).__name__,
            getattr(getattr(outcome, "orig", None), "sqlstate", None),
        )
        for outcome in outcomes
    ]

    async with session_factory() as reader:
        stored_news = dict(
            (
                await reader.execute(
                    select(models.News.id, models.News.image_url).where(
                        models.News.id.in_([news_a.id, news_b.id])
                    )
                )
            ).all()
        )
        stored_assets = {
            storage_url: (owner_user_id, news_id)
            for storage_url, owner_user_id, news_id in (
                await reader.execute(
                    select(
                        models.NewsMediaAsset.storage_url,
                        models.NewsMediaAsset.owner_user_id,
                        models.NewsMediaAsset.news_id,
                    ).where(models.NewsMediaAsset.storage_url.in_([image_a, image_b]))
                )
            ).all()
        }

    assert stored_news == {news_a.id: image_a, news_b.id: image_b}
    assert stored_assets == {
        image_a: (owner.id, news_a.id),
        image_b: (owner.id, news_b.id),
    }
