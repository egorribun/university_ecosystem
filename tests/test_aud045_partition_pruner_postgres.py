"""Exercise partition pruning only in a coordinator-owned disposable database.

The external launcher supplies an isolated database and role; this module does
not start containers, create databases, or run historical migrations.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import os
import re
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine

_RUN = os.environ.get("AUD045_DISPOSABLE") == "1"
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _RUN, reason="Requires owned AUD-045 disposable PostgreSQL"),
]


@pytest.fixture(scope="session", autouse=True)
def prepare_database() -> None:
    """Do not let shared application fixtures initialize the probe database."""


@pytest.fixture(autouse=True)
def clean_database() -> None:
    """The owner removes the disposable database after this module finishes."""


@pytest.fixture(scope="session", autouse=True)
def source_bound_native_extension() -> None:
    """Reject an old installed extension in place of the reviewed private wheel."""
    raw_root = os.environ.get("AUD045_RUST_WHEEL_ROOT", "")
    expected_hash = os.environ.get("AUD045_RUST_BINARY_SHA256", "")
    if not raw_root or re.fullmatch(r"[0-9a-f]{64}", expected_hash) is None:
        pytest.fail("AUD-045 Rust extension identity is incomplete")
    root = Path(raw_root).resolve(strict=True)
    binaries = list((root / "rust_ext").glob("rust_ext*.pyd"))
    if len(binaries) != 1 or binaries[0].is_symlink():
        pytest.fail("AUD-045 private wheel binary is ambiguous")
    expected_binary = binaries[0].resolve(strict=True)
    if expected_binary.parent != root / "rust_ext":
        pytest.fail("AUD-045 private wheel binary escaped its directory")
    if hashlib.sha256(expected_binary.read_bytes()).hexdigest() != expected_hash:
        pytest.fail("AUD-045 Rust extension binary hash does not match")

    rust_ext = importlib.import_module("rust_ext")
    native = importlib.import_module("rust_ext.rust_ext")
    binary = Path(native.__file__).resolve(strict=True)
    if binary != expected_binary or binary.suffix.lower() != ".pyd":
        pytest.fail("AUD-045 Rust extension is not loaded from the private wheel")
    if hashlib.sha256(binary.read_bytes()).hexdigest() != expected_hash:
        pytest.fail("AUD-045 Rust extension binary hash does not match")
    assert rust_ext.is_partition_expired is native.is_partition_expired


@pytest.fixture
async def owned_postgres() -> AsyncIterator[SimpleNamespace]:
    raw_url = os.environ.get("AUD045_DISPOSABLE_PG_URL", "")
    run_id = os.environ.get("AUD045_DISPOSABLE_RUN_ID", "")
    if not raw_url or re.fullmatch(r"[0-9a-f]{32}", run_id) is None:
        pytest.fail("AUD-045 disposable PostgreSQL identity is incomplete")
    url = make_url(raw_url)
    if (
        url.drivername != "postgresql+asyncpg"
        or url.host != "127.0.0.1"
        or url.port is None
        or url.port == 5432
        or url.database != "audit_partition_pruner"
        or url.username != "audit_partition_owner"
    ):
        pytest.fail("AUD-045 disposable PostgreSQL identity does not match")

    suffix = uuid.uuid4().hex
    schema = f"aud045_{suffix}"
    shadow = f"aud045_shadow_{suffix}"
    bootstrap = create_async_engine(url, pool_size=1, max_overflow=0)
    engine = None
    try:
        async with bootstrap.begin() as connection:
            role = (
                await connection.execute(
                    text(
                        "SELECT pg_catalog.current_database(), current_user, "
                        "rolsuper, rolbypassrls FROM pg_catalog.pg_roles "
                        "WHERE rolname = current_user"
                    )
                )
            ).one()
            if tuple(role) != (
                "audit_partition_pruner",
                "audit_partition_owner",
                False,
                False,
            ):
                pytest.fail("AUD-045 disposable PostgreSQL role does not match")
            marker = (
                (
                    await connection.execute(
                        text("SELECT run_id FROM public.aud045_owner_marker")
                    )
                )
                .scalars()
                .all()
            )
            if marker != [run_id]:
                pytest.fail("AUD-045 disposable PostgreSQL owner marker differs")
            for name in (schema, shadow):
                await connection.execute(text(f'CREATE SCHEMA "{name}"'))

        engine = create_async_engine(
            url,
            pool_size=3,
            max_overflow=0,
            pool_timeout=3,
            connect_args={"server_settings": {"search_path": f"{schema},pg_catalog"}},
        )
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "CREATE TABLE notifications (created_at timestamptz, marker text) "
                    "PARTITION BY RANGE (created_at)"
                )
            )
            await connection.execute(
                text(
                    "CREATE TABLE notification_deliveries (attempted_at timestamptz, marker text) "
                    "PARTITION BY RANGE (attempted_at)"
                )
            )
            await connection.execute(
                text(
                    "CREATE TABLE data_access_logs (created_at timestamptz, marker text) "
                    "PARTITION BY RANGE (created_at)"
                )
            )
            await connection.execute(
                text(
                    "CREATE TABLE other_parent (created_at timestamptz) "
                    "PARTITION BY RANGE (created_at)"
                )
            )
            await connection.execute(
                text(
                    f'CREATE TABLE "{shadow}".notifications '
                    "(created_at timestamptz, marker text) PARTITION BY RANGE (created_at)"
                )
            )
        yield SimpleNamespace(engine=engine, schema=schema, shadow=shadow)
    finally:
        if engine is not None:
            await engine.dispose()
        # Retain the synthetic schemas for the coordinator's exact-ID
        # disposable-container cleanup; never resolve and drop schema names here.
        await bootstrap.dispose()


async def _create_month(
    connection, name: str, start: str, end: str, *, parent: str = "notifications"
) -> None:
    await connection.execute(
        text(
            f"CREATE TABLE {name} PARTITION OF {parent} "
            f"FOR VALUES FROM ('{start}') TO ('{end}')"
        )
    )


async def _exists(connection, schema: str, name: str) -> bool:
    return (
        await connection.execute(
            text("SELECT to_regclass(format('%I.%I', :schema, :name)) IS NOT NULL"),
            {"schema": schema, "name": name},
        )
    ).scalar_one()


async def _candidate(connection, name: str):
    from app.services import partition_manager

    candidates = await partition_manager._list_prunable_partitions(
        connection, "notifications", "created_at"
    )
    return next(
        candidate for candidate in candidates if candidate.partition_name == name
    )


async def _prune(connection, candidate) -> bool:
    import rust_ext

    from app.services import partition_manager

    return await partition_manager._prune_expired_partition(
        connection, "notifications", "created_at", 365, rust_ext, candidate
    )


async def test_worker_prunes_only_exact_expired_monthly_partitions(
    owned_postgres: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    import rust_ext

    from app.core.config import settings
    from app.services import partition_manager

    # Prove this Python process loaded a Rust extension with both name formats.
    assert rust_ext.is_partition_expired("notifications_2001_01", "notifications", 365)
    assert rust_ext.is_partition_expired("notifications_y2001m02", "notifications", 365)

    schema, shadow, engine = (
        owned_postgres.schema,
        owned_postgres.shadow,
        owned_postgres.engine,
    )
    month_end = datetime.now(UTC).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    month_start = (month_end - timedelta(days=1)).replace(day=1)
    recent_name = f"notifications_y{month_start.year:04}m{month_start.month:02}"
    async with engine.begin() as connection:
        await _create_month(
            connection, "notifications_2001_01", "2001-01-01", "2001-02-01"
        )
        await _create_month(
            connection, "notifications_y2001m02", "2001-02-01", "2001-03-01"
        )
        # An old-looking name cannot authorize deletion of this future range.
        await _create_month(
            connection, "notifications_2001_03", "2099-03-01", "2099-04-01"
        )
        await _create_month(
            connection, "notifications_2001_1", "2001-04-01", "2001-05-01"
        )
        await _create_month(
            connection, "notifications_y2099m05", "2099-05-01", "2099-06-01"
        )
        await _create_month(
            connection, recent_name, month_start.isoformat(), month_end.isoformat()
        )
        await _create_month(
            connection,
            "notification_deliveries_2001_07",
            "2001-07-01",
            "2001-08-01",
            parent="notification_deliveries",
        )
        await _create_month(
            connection,
            "data_access_logs_y2001m08",
            "2001-08-01",
            "2001-09-01",
            parent="data_access_logs",
        )
        await _create_month(
            connection,
            "notifications_2001_05",
            "2001-05-01",
            "2001-06-01",
            parent="other_parent",
        )
        await _create_month(
            connection, f'"{shadow}".notifications_2001_06', "2001-06-01", "2001-07-01"
        )
        await _create_month(
            connection,
            f'"{shadow}".notifications_2001_01',
            "2001-01-01",
            "2001-02-01",
            parent=f'"{shadow}".notifications',
        )
        await connection.execute(
            text(
                "CREATE TABLE notifications_default PARTITION OF notifications DEFAULT"
            )
        )
        await connection.execute(
            text("INSERT INTO notifications VALUES ('2099-03-15', 'retain-future')")
        )
        await connection.execute(
            text(
                "INSERT INTO notifications VALUES "
                "('2001-01-15', 'expire-legacy'), "
                "('2001-02-15', 'expire-current')"
            )
        )
        await connection.execute(
            text("INSERT INTO notifications VALUES (:created_at, 'retain-recent')"),
            {"created_at": month_start + timedelta(days=1)},
        )
        await connection.execute(
            text(
                "INSERT INTO notification_deliveries VALUES ('2001-07-15', 'expire-delivery')"
            )
        )
        await connection.execute(
            text("INSERT INTO data_access_logs VALUES ('2001-08-15', 'expire-access')")
        )
        expired_count = await connection.execute(
            text("SELECT count(*) FROM notifications WHERE marker LIKE 'expire-%'")
        )
        assert expired_count.scalar_one() == 2

    monkeypatch.setattr(partition_manager, "engine", engine)
    monkeypatch.setattr(
        partition_manager,
        "PARTITIONED_TABLES",
        [
            ("notifications", "created_at"),
            ("notification_deliveries", "attempted_at"),
            ("data_access_logs", "created_at"),
        ],
    )
    monkeypatch.setattr(settings, "partition_warmup_months", -1)
    monkeypatch.setattr(settings, "partition_retention_days", 365)
    await partition_manager.ensure_partitions_exist()

    async with engine.connect() as connection:
        assert not await _exists(connection, schema, "notifications_2001_01")
        assert not await _exists(connection, schema, "notifications_y2001m02")
        assert not await _exists(connection, schema, "notification_deliveries_2001_07")
        assert not await _exists(connection, schema, "data_access_logs_y2001m08")
        for name in (
            "notifications_2001_03",
            "notifications_2001_1",
            "notifications_y2099m05",
            "notifications_2001_05",
            "notifications_default",
            recent_name,
        ):
            assert await _exists(connection, schema, name)
        for name in ("notifications_2001_01", "notifications_2001_06"):
            assert await _exists(connection, shadow, name)
        assert (
            await connection.execute(
                text("SELECT marker FROM notifications WHERE marker = 'retain-future'")
            )
        ).scalar_one() == "retain-future"
        expired_count = await connection.execute(
            text("SELECT count(*) FROM notifications WHERE marker LIKE 'expire-%'")
        )
        assert expired_count.scalar_one() == 0
        assert (
            await connection.execute(
                text("SELECT marker FROM notifications WHERE marker = 'retain-recent'")
            )
        ).scalar_one() == "retain-recent"
        for query in (
            "SELECT count(*) FROM notification_deliveries",
            "SELECT count(*) FROM data_access_logs",
        ):
            assert (await connection.execute(text(query))).scalar_one() == 0


async def test_schema_function_shadow_cannot_forge_expired_partition_bounds(
    owned_postgres: SimpleNamespace,
) -> None:
    engine = owned_postgres.engine
    name = "notifications_2001_01"
    async with engine.begin() as connection:
        await _create_month(connection, name, "2099-01-01", "2099-02-01")
        await connection.execute(
            text(
                "CREATE FUNCTION pg_get_expr(pg_catalog.pg_node_tree, pg_catalog.oid) "
                "RETURNS text LANGUAGE sql IMMUTABLE AS $$ "
                "SELECT 'FOR VALUES FROM (''2001-01-01 00:00:00+00'') "
                "TO (''2001-02-01 00:00:00+00'')'::text $$"
            )
        )
        row = (
            await connection.execute(
                text(
                    "SELECT pg_get_expr(c.relpartbound, c.oid), "
                    "pg_catalog.pg_get_expr(c.relpartbound, c.oid) "
                    "FROM pg_catalog.pg_class c WHERE c.oid = to_regclass(:name)"
                ),
                {"name": name},
            )
        ).one()
        assert "2001-01-01" in row[0] and "2099-01-01" in row[1]

    async with engine.connect() as connection:
        candidate = await _candidate(connection, name)
        await connection.commit()
        assert not await _prune(connection, candidate)
        await connection.commit()
        assert await _exists(connection, owned_postgres.schema, name)


async def test_prune_preserves_caller_timeout_and_rollback(
    owned_postgres: SimpleNamespace,
) -> None:
    engine = owned_postgres.engine
    name = "notifications_2001_01"
    async with engine.begin() as connection:
        await _create_month(connection, name, "2001-01-01", "2001-02-01")
    async with engine.connect() as worker:
        await worker.execute(text("SET LOCAL statement_timeout = '1000ms'"))
        candidate = await _candidate(worker, name)
        assert await _prune(worker, candidate)
        assert not await _exists(worker, owned_postgres.schema, name)
        timeout = await worker.execute(
            text(
                "SELECT setting FROM pg_catalog.pg_settings WHERE name = 'statement_timeout'"
            )
        )
        assert timeout.scalar_one() == "1000"
        await worker.rollback()
    async with engine.connect() as connection:
        assert await _exists(connection, owned_postgres.schema, name)


async def test_busy_parent_fails_closed_without_changing_caller_timeout(
    owned_postgres: SimpleNamespace,
) -> None:
    engine = owned_postgres.engine
    name = "notifications_2001_01"
    async with engine.begin() as connection:
        await _create_month(connection, name, "2001-01-01", "2001-02-01")
    async with engine.connect() as worker:
        candidate = await _candidate(worker, name)
        await worker.commit()
        await worker.execute(text("SET LOCAL statement_timeout = '1000ms'"))
        async with engine.connect() as blocker:
            await blocker.execute(
                text("LOCK TABLE ONLY notifications IN ACCESS EXCLUSIVE MODE")
            )
            assert not await asyncio.wait_for(_prune(worker, candidate), timeout=3)
            timeout = await worker.execute(
                text(
                    "SELECT setting FROM pg_catalog.pg_settings "
                    "WHERE name = 'statement_timeout'"
                )
            )
            assert timeout.scalar_one() == "1000"
            await blocker.rollback()
        await worker.commit()
        assert await _exists(worker, owned_postgres.schema, name)


async def test_busy_child_discovery_is_bounded_and_preserves_caller_transaction(
    owned_postgres: SimpleNamespace,
) -> None:
    from app.services import partition_manager

    engine = owned_postgres.engine
    name = "notifications_2001_01"
    async with engine.begin() as connection:
        await _create_month(connection, name, "2001-01-01", "2001-02-01")
    async with engine.connect() as blocker:
        await blocker.execute(text(f"LOCK TABLE ONLY {name} IN ACCESS EXCLUSIVE MODE"))
        async with engine.connect() as canary:
            await canary.execute(text("SET LOCAL statement_timeout = '250ms'"))
            with pytest.raises(SQLAlchemyError) as caught:
                await canary.execute(
                    text(
                        "SELECT pg_catalog.pg_get_expr(c.relpartbound, c.oid) "
                        "FROM pg_catalog.pg_class AS c "
                        "WHERE c.oid = pg_catalog.to_regclass(:name)"
                    ),
                    {"name": name},
                )
            assert getattr(caught.value.orig, "sqlstate", None) == "57014"
            await canary.rollback()

        async with engine.connect() as worker:
            await worker.execute(text("SET LOCAL statement_timeout = '500ms'"))
            with pytest.raises(SQLAlchemyError):
                await asyncio.wait_for(
                    partition_manager._list_prunable_partitions(
                        worker, "notifications", "created_at"
                    ),
                    timeout=3,
                )
            timeout = await worker.execute(
                text(
                    "SELECT setting FROM pg_catalog.pg_settings "
                    "WHERE name = 'statement_timeout'"
                )
            )
            assert timeout.scalar_one() == "500"
            assert (await worker.execute(text("SELECT 1"))).scalar_one() == 1
            await worker.rollback()
        await blocker.rollback()


@pytest.mark.parametrize(
    "isolation", ["READ COMMITTED", "REPEATABLE READ", "SERIALIZABLE"]
)
async def test_preexisting_snapshot_cannot_prune_reattached_future_partition(
    owned_postgres: SimpleNamespace, isolation: str
) -> None:
    engine = owned_postgres.engine
    name = "notifications_2001_01"
    async with engine.begin() as connection:
        await _create_month(connection, name, "2001-01-01", "2001-02-01")
    async with engine.connect() as connection:
        worker = await connection.execution_options(isolation_level=isolation)
        # Keep this transaction open: stronger isolation retains this snapshot.
        candidate = await _candidate(worker, name)
        async with engine.begin() as concurrent:
            await concurrent.execute(
                text(f"ALTER TABLE notifications DETACH PARTITION {name}")
            )
            await concurrent.execute(
                text(
                    f"ALTER TABLE notifications ATTACH PARTITION {name} "
                    "FOR VALUES FROM ('2099-01-01') TO ('2099-02-01')"
                )
            )
            await concurrent.execute(
                text("INSERT INTO notifications VALUES ('2099-01-15', 'retained')")
            )
        assert not await _prune(worker, candidate)
        await worker.commit()
    async with engine.connect() as connection:
        assert await _exists(connection, owned_postgres.schema, name)
        assert (
            await connection.execute(
                text("SELECT marker FROM notifications WHERE marker = 'retained'")
            )
        ).scalar_one() == "retained"


@pytest.mark.parametrize(
    "mutation", ["rename", "detach", "replacement", "bounds", "parent"]
)
async def test_stale_catalog_candidate_cannot_remove_changed_partition(
    owned_postgres: SimpleNamespace, mutation: str
) -> None:
    engine = owned_postgres.engine
    name = "notifications_2001_01"
    async with engine.begin() as connection:
        await _create_month(connection, name, "2001-01-01", "2001-02-01")
    async with engine.connect() as worker:
        candidate = await _candidate(worker, name)
        await worker.commit()
        async with engine.begin() as concurrent:
            if mutation == "rename":
                await concurrent.execute(
                    text(f"ALTER TABLE {name} RENAME TO notifications_renamed")
                )
            else:
                await concurrent.execute(
                    text(f"ALTER TABLE notifications DETACH PARTITION {name}")
                )
                if mutation == "replacement":
                    await concurrent.execute(
                        text(f"ALTER TABLE {name} RENAME TO notifications_detached")
                    )
                    await _create_month(concurrent, name, "2001-01-01", "2001-02-01")
                elif mutation == "bounds":
                    await concurrent.execute(
                        text(
                            f"ALTER TABLE notifications ATTACH PARTITION {name} FOR VALUES FROM ('2099-01-01') TO ('2099-02-01')"
                        )
                    )
                elif mutation == "parent":
                    await concurrent.execute(
                        text(
                            f"ALTER TABLE other_parent ATTACH PARTITION {name} FOR VALUES FROM ('2001-01-01') TO ('2001-02-01')"
                        )
                    )
        assert not await _prune(worker, candidate)
        await worker.commit()
        expected = "notifications_renamed" if mutation == "rename" else name
        assert await _exists(worker, owned_postgres.schema, expected)
        if mutation == "replacement":
            assert await _exists(
                worker, owned_postgres.schema, "notifications_detached"
            )
