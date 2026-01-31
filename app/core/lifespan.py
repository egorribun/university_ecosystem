import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import settings
from app.core.database import Base, engine, wait_db
from app.core.events import register_event_listeners
from app.core.observability import shutdown_observability
from app.core.rate_limit import (
    start_memory_cleanup_task,
    stop_memory_cleanup_task,
)
from app.core.tkq import broker
from app.deps.cache import shutdown_cache
from app.services import notification_queue, webpush
from app.services.cache_warmup import warm_cache
from app.services.partition_manager import (
    ensure_partitions_exist,
    start_partition_management_scheduler,
)
from app.tasks.cleanups import setup_periodic_cleanups
from app.workers.outbox import OutboxWorker


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Configure database adapters (remove global side effects)
    from app.core.database import configure_database

    configure_database()

    from app.api.websocket import start_presence_pubsub, stop_presence_pubsub
    from app.core.feature_flags import feature_flags

    await broker.startup()
    await feature_flags.initialize()
    await start_presence_pubsub()
    await wait_db(max_attempts=10, delay=0.5)

    # Register domain event persistence listeners
    register_event_listeners()

    # Configure domain event handlers
    from app.services.event_handlers import configure_event_handlers

    configure_event_handlers()

    if settings.auto_create_schema:
        import logging

        from sqlalchemy import text

        logger = logging.getLogger(__name__)

        async with engine.begin() as conn:
            if conn.dialect.name == "postgresql":
                try:
                    await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                except Exception as e:
                    logger.warning(
                        f"Could not create 'vector' extension: {e}. "
                        "Semantic search will be disabled."
                    )
                    # Patch metadata to avoid using Vector type if extension is missing
                    from pgvector.sqlalchemy import Vector
                    from sqlalchemy import Text

                    for table in Base.metadata.tables.values():
                        for column in table.columns:
                            # Check for direct Vector or Variant containing Vector
                            is_vector = isinstance(column.type, Vector)
                            is_variant_vector = False

                            if hasattr(column.type, "_variant_mapping"):
                                # If Variant, check if PG variant is Vector
                                pg_utils = column.type._variant_mapping
                                pg_variant = pg_utils.get("postgresql")
                                if pg_variant and isinstance(pg_variant, Vector):
                                    is_variant_vector = True

                            if is_vector:
                                column.type = Text()
                            elif is_variant_vector:
                                # Use base type as fallback
                                column.type = getattr(column.type, "base_type", Text())

                    # Disable semantic search in settings
                    try:
                        # Attempt to disable semantic search since extension is missing
                        object.__setattr__(settings, "semantic_search_enabled", False)
                    except Exception:
                        logger.error(
                            "Failed to disable semantic_search_enabled setting"
                        )

        async with engine.begin() as conn:
            await conn.run_sync(
                lambda sync_conn: Base.metadata.create_all(
                    bind=sync_conn, checkfirst=True
                )
            )

    await setup_periodic_cleanups()

    if settings.partition_management_enabled:
        await ensure_partitions_exist()
        stop_partitions = await start_partition_management_scheduler(
            settings.partition_management_interval_seconds
        )

    # Start OutboxWorker
    outbox_worker = OutboxWorker()
    outbox_task = asyncio.create_task(outbox_worker.run_forever())

    # Start in-memory rate limit cleanup (for fallback mode)
    start_memory_cleanup_task()

    await warm_cache()
    try:
        yield
    finally:
        await stop_presence_pubsub()
        await notification_queue.shutdown_notification_queue()
        webpush.cleanup()
        await shutdown_cache()
        if settings.partition_management_enabled:
            await stop_partitions()

        await outbox_worker.stop()
        await outbox_task
        await feature_flags.shutdown()
        await broker.shutdown()
        await stop_memory_cleanup_task()
        shutdown_observability()
