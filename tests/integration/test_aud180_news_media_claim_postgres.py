"""Prove news image claims and the irreversible baseline's PostgreSQL contract."""

from __future__ import annotations

import asyncio
import importlib.util
import os
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.models as models
from app.repositories.news_repository import NewsRepository
from scripts.quality.render_live_alembic_sql import _owned_scratch_database
from tests.integration.test_migration_roundtrip import (
    migration_postgres as migration_postgres,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION_PATH = (
    _PROJECT_ROOT / "alembic" / "versions" / "202611020000_mvp_baseline.py"
)
_RUN_INTEGRATION_TESTS = os.getenv("RUN_INTEGRATION_TESTS") == "1"
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _RUN_INTEGRATION_TESTS,
        reason="Set RUN_INTEGRATION_TESTS=1 for the owned PostgreSQL integration",
    ),
]

_DOWNGRADE_REASON = (
    "The MVP baseline cannot be downgraded: reaching base or any earlier schema "
    "is not a supported recovery path. Restore a consistent backup set instead."
)
_MEDIA_CATALOG_QUERIES = {
    "columns": """
        SELECT attribute.attname,
               pg_catalog.format_type(attribute.atttypid, attribute.atttypmod),
               attribute.attnotnull,
               pg_catalog.pg_get_expr(default_row.adbin, default_row.adrelid),
               attribute.attidentity, attribute.attgenerated
        FROM pg_catalog.pg_attribute AS attribute
        LEFT JOIN pg_catalog.pg_attrdef AS default_row
          ON default_row.adrelid = attribute.attrelid
         AND default_row.adnum = attribute.attnum
        WHERE attribute.attrelid = 'public.news_media_assets'::regclass
          AND attribute.attnum > 0 AND NOT attribute.attisdropped
        ORDER BY attribute.attnum
    """,
    "constraints": """
        SELECT constraint_row.conname, constraint_row.contype::text,
               pg_catalog.pg_get_constraintdef(constraint_row.oid),
               constraint_row.condeferrable, constraint_row.condeferred,
               constraint_row.convalidated
        FROM pg_catalog.pg_constraint AS constraint_row
        WHERE constraint_row.conrelid = 'public.news_media_assets'::regclass
        ORDER BY constraint_row.conname
    """,
    "indexes": """
        SELECT index_relation.relname,
               pg_catalog.pg_get_indexdef(index_row.indexrelid),
               access_method.amname,
               index_row.indisunique, index_row.indisprimary,
               index_row.indisexclusion, index_row.indimmediate,
               index_row.indisvalid, index_row.indisready, index_row.indislive,
               index_row.indnullsnotdistinct,
               index_row.indnkeyatts, index_row.indnatts,
               COALESCE(array_to_string(index_relation.reloptions, ','), '')
        FROM pg_catalog.pg_index AS index_row
        JOIN pg_catalog.pg_class AS index_relation
          ON index_relation.oid = index_row.indexrelid
        JOIN pg_catalog.pg_am AS access_method
          ON access_method.oid = index_relation.relam
        WHERE index_row.indrelid = 'public.news_media_assets'::regclass
        ORDER BY index_relation.relname
    """,
}
# Independent ownership contract, not generated from the migration under test.
# These include the historical guard's rejected flags/options, plus validity.
_EXPECTED_MEDIA_CATALOG = {
    "columns": (
        ("id", "uuid", True, None, "", ""),
        ("storage_url", "character varying(2048)", True, None, "", ""),
        ("owner_user_id", "uuid", False, None, "", ""),
        ("news_id", "uuid", False, None, "", ""),
        ("created_at", "timestamp with time zone", True, "now()", "", ""),
    ),
    "constraints": (
        (
            "news_media_assets_news_id_fkey",
            "f",
            "FOREIGN KEY (news_id) REFERENCES news(id) ON DELETE SET NULL",
            False,
            False,
            True,
        ),
        (
            "news_media_assets_owner_user_id_fkey",
            "f",
            "FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE SET NULL",
            False,
            False,
            True,
        ),
        (
            "news_media_assets_pkey",
            "p",
            "PRIMARY KEY (id)",
            False,
            False,
            True,
        ),
        (
            "uq_news_media_asset_news_id",
            "u",
            "UNIQUE (news_id)",
            False,
            False,
            True,
        ),
        (
            "uq_news_media_asset_storage_url",
            "u",
            "UNIQUE (storage_url)",
            False,
            False,
            True,
        ),
    ),
    "indexes": (
        (
            "ix_news_media_assets_owner_user_id",
            "CREATE INDEX ix_news_media_assets_owner_user_id "
            "ON public.news_media_assets USING btree (owner_user_id)",
            "btree",
            False,
            False,
            False,
            True,
            True,
            True,
            True,
            False,
            1,
            1,
            "",
        ),
        (
            "news_media_assets_pkey",
            "CREATE UNIQUE INDEX news_media_assets_pkey "
            "ON public.news_media_assets USING btree (id)",
            "btree",
            True,
            True,
            False,
            True,
            True,
            True,
            True,
            False,
            1,
            1,
            "",
        ),
        (
            "uq_news_media_asset_news_id",
            "CREATE UNIQUE INDEX uq_news_media_asset_news_id "
            "ON public.news_media_assets USING btree (news_id)",
            "btree",
            True,
            False,
            False,
            True,
            True,
            True,
            True,
            False,
            1,
            1,
            "",
        ),
        (
            "uq_news_media_asset_storage_url",
            "CREATE UNIQUE INDEX uq_news_media_asset_storage_url "
            "ON public.news_media_assets USING btree (storage_url)",
            "btree",
            True,
            False,
            False,
            True,
            True,
            True,
            True,
            False,
            1,
            1,
            "",
        ),
    ),
}


def _load_baseline_migration():
    spec = importlib.util.spec_from_file_location(
        "aud180_mvp_baseline_migration", _MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _assert_canonical_media_catalog(
    connection: sa.Connection,
) -> dict[str, tuple[tuple[object, ...], ...]]:
    catalog = {
        kind: tuple(tuple(row) for row in connection.execute(sa.text(query)))
        for kind, query in _MEDIA_CATALOG_QUERIES.items()
    }
    for kind, expected in _EXPECTED_MEDIA_CATALOG.items():
        assert catalog[kind] == expected, f"noncanonical news media {kind}"
    return catalog


def _read_claim(
    connection: sa.Connection, claim: dict[str, UUID | str]
) -> tuple[object, ...]:
    row = connection.execute(
        sa.text(
            "SELECT id, storage_url, owner_user_id, news_id, created_at "
            "FROM public.news_media_assets WHERE id = :id"
        ),
        {"id": claim["id"]},
    ).one()
    assert row[:4] == (
        claim["id"],
        claim["url"],
        claim["owner"],
        claim["news"],
    )
    return tuple(row)


@pytest.fixture(scope="module")
def baseline_media_connection(migration_postgres) -> Iterator[sa.Connection]:
    """Run the actual baseline only on a new, identity-guarded template0 DB.

    The imported fixture owns its pinned container or validates the explicitly
    supplied root-owned, quiescent loopback test service. A URL is not ownership
    authority. The scratch helper requires CREATE acknowledgement, confirms the
    new DB's OID/name/owner/current role and empty catalog, and rechecks that exact
    identity before cleanup. It never migrates the source DB or either template.
    The baseline's outer transaction is never committed: even cluster-global role
    creation and optional cron catalog writes roll back before the scratch drop.
    """
    source_url = sa.engine.make_url(
        migration_postgres.get_connection_url(driver="psycopg")
    ).update_query_dict(
        {
            "options": (
                "-c statement_timeout=60000 -c lock_timeout=10000 "
                "-c idle_in_transaction_session_timeout=60000 -c search_path=public"
            )
        }
    )
    with _owned_scratch_database(
        source_url.render_as_string(hide_password=False)
    ) as scratch_url:
        engine = sa.create_engine(
            scratch_url, connect_args={"connect_timeout": 5}, poolclass=sa.pool.NullPool
        )
        try:
            with engine.connect() as connection:
                transaction = connection.begin()
                try:
                    assert connection.dialect.name == "postgresql"
                    with Operations.context(MigrationContext.configure(connection)):
                        _load_baseline_migration().upgrade()
                    _assert_canonical_media_catalog(connection)
                    yield connection
                finally:
                    transaction.rollback()
        finally:
            engine.dispose()


@pytest.fixture
def populated_baseline_media(
    baseline_media_connection: sa.Connection,
) -> Iterator[tuple[sa.Connection, dict[str, UUID | str]]]:
    """Each case starts with a real populated claim and rolls its writes back."""
    claim = {
        "id": uuid4(),
        "owner": uuid4(),
        "news": uuid4(),
        "other_news": uuid4(),
        "url": "/static/news_images/news_0123456789abcdef0123456789abcdef.jpg",
    }
    connection = baseline_media_connection
    savepoint = connection.begin_nested()
    try:
        connection.execute(
            sa.text(
                "INSERT INTO public.users (id, email, hashed_password) "
                "VALUES (:id, :email, :password)"
            ),
            {
                "id": claim["owner"],
                "email": f"{claim['owner']}@example.invalid",
                "password": "not-an-authentication-credential",
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO public.news (id, title, content) "
                "VALUES (:id, :title, :content)"
            ),
            [
                {"id": claim["news"], "title": "Claimed news", "content": "Body"},
                {"id": claim["other_news"], "title": "Other news", "content": "Body"},
            ],
        )
        connection.execute(
            sa.text(
                "INSERT INTO public.news_media_assets "
                "(id, storage_url, owner_user_id, news_id) "
                "VALUES (:id, :url, :owner, :news)"
            ),
            claim,
        )
        _assert_canonical_media_catalog(connection)
        _read_claim(connection, claim)
        yield connection, claim
    finally:
        savepoint.rollback()


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


def test_baseline_downgrade_refuses_without_changing_populated_claim(
    populated_baseline_media,
):
    connection, claim = populated_baseline_media
    before_catalog = _assert_canonical_media_catalog(connection)
    before_claim = _read_claim(connection, claim)
    statements: list[str] = []

    def record_sql(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    migration = _load_baseline_migration()
    sa.event.listen(connection, "before_cursor_execute", record_sql)
    try:
        with Operations.context(MigrationContext.configure(connection)):
            with pytest.raises(RuntimeError) as failure:
                migration.downgrade()
        assert str(failure.value) == _DOWNGRADE_REASON
        assert statements == []
    finally:
        sa.event.remove(connection, "before_cursor_execute", record_sql)

    assert _assert_canonical_media_catalog(connection) == before_catalog
    assert _read_claim(connection, claim) == before_claim

    duplicate_claims = (
        {
            "id": uuid4(),
            "url": "/static/news_images/news_11111111111111111111111111111111.jpg",
            "owner": claim["owner"],
            "news": claim["news"],
        },
        {
            "id": uuid4(),
            "url": claim["url"],
            "owner": claim["owner"],
            "news": claim["other_news"],
        },
    )
    insert = sa.text(
        "INSERT INTO public.news_media_assets "
        "(id, storage_url, owner_user_id, news_id) "
        "VALUES (:id, :url, :owner, :news)"
    )
    for values in duplicate_claims:
        with pytest.raises(sa.exc.IntegrityError):
            with connection.begin_nested():
                connection.execute(insert, values)
        assert _assert_canonical_media_catalog(connection) == before_catalog
        assert _read_claim(connection, claim) == before_claim


def test_baseline_media_catalog_rejects_missing_column(populated_baseline_media):
    connection, claim = populated_baseline_media
    before_catalog = _assert_canonical_media_catalog(connection)
    before_claim = _read_claim(connection, claim)
    savepoint = connection.begin_nested()
    try:
        connection.exec_driver_sql(
            "ALTER TABLE public.news_media_assets DROP COLUMN created_at"
        )
        with pytest.raises(AssertionError, match="noncanonical news media columns"):
            _assert_canonical_media_catalog(connection)
    finally:
        savepoint.rollback()
    assert _assert_canonical_media_catalog(connection) == before_catalog
    assert _read_claim(connection, claim) == before_claim


@pytest.mark.parametrize(
    ("storage_url_unique", "index_sql", "message"),
    [
        (
            "UNIQUE (storage_url) DEFERRABLE INITIALLY IMMEDIATE",
            None,
            "constraints",
        ),
        (
            "UNIQUE (storage_url) DEFERRABLE INITIALLY DEFERRED",
            None,
            "constraints",
        ),
        (
            "UNIQUE NULLS NOT DISTINCT (storage_url)",
            None,
            "constraints",
        ),
        (
            "",
            "CREATE INDEX ix_news_media_assets_owner_user_id "
            "ON public.news_media_assets (owner_user_id) "
            "WHERE owner_user_id IS NOT NULL",
            "indexes",
        ),
        (
            "",
            "CREATE INDEX ix_news_media_assets_owner_user_id "
            "ON public.news_media_assets (owner_user_id) INCLUDE (storage_url)",
            "indexes",
        ),
        (
            "",
            "CREATE INDEX ix_news_media_assets_owner_user_id "
            "ON public.news_media_assets ((owner_user_id::text))",
            "indexes",
        ),
        (
            "",
            "CREATE INDEX ix_news_media_assets_owner_user_id "
            "ON public.news_media_assets (owner_user_id) WITH (fillfactor=80)",
            "indexes",
        ),
        (
            "",
            "CREATE INDEX ix_news_media_assets_owner_user_id "
            "ON public.news_media_assets (owner_user_id DESC)",
            "indexes",
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
def test_baseline_media_catalog_rejects_noncanonical_constraint_or_index_options(
    populated_baseline_media,
    storage_url_unique: str,
    index_sql: str | None,
    message: str,
):
    connection, claim = populated_baseline_media
    before_catalog = _assert_canonical_media_catalog(connection)
    before_claim = _read_claim(connection, claim)
    savepoint = connection.begin_nested()
    try:
        if index_sql is None:
            connection.exec_driver_sql(
                "ALTER TABLE public.news_media_assets "
                "DROP CONSTRAINT uq_news_media_asset_storage_url"
            )
            connection.exec_driver_sql(
                "ALTER TABLE public.news_media_assets "
                "ADD CONSTRAINT uq_news_media_asset_storage_url " + storage_url_unique
            )
        else:
            connection.exec_driver_sql(
                "DROP INDEX public.ix_news_media_assets_owner_user_id"
            )
            connection.exec_driver_sql(index_sql)
        with pytest.raises(AssertionError, match=f"noncanonical news media {message}"):
            _assert_canonical_media_catalog(connection)
    finally:
        savepoint.rollback()
    assert _assert_canonical_media_catalog(connection) == before_catalog
    assert _read_claim(connection, claim) == before_claim


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
