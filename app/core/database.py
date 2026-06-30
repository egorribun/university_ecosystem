from __future__ import annotations

import asyncio
import logging
import sqlite3
import threading
import time
from collections.abc import AsyncGenerator, Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Engine, event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import Settings, settings
from app.core.logging import get_logger, is_logger_enabled
from app.core.protocols import AsyncDatabaseSession


# Fix for aiosqlite/sqlite3 deprecation warning
def adapt_datetime(val: datetime) -> str:
    return val.isoformat()


def configure_database() -> None:
    """
    Configure database adapters and global settings.
    Must be called at application startup.
    """
    sqlite3.register_adapter(datetime, adapt_datetime)


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection: Any, connection_record: Any) -> None:
    """Enable WAL mode and foreign keys for SQLite."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


logger = get_logger(__name__)
slow_query_logger = get_logger("slow_queries")
pool_health_logger = get_logger("pool_health")

# Context variable to store query start time (async-safe)
_query_start_time: ContextVar[float | None] = ContextVar(
    "query_start_time", default=None
)


@dataclass
class PoolHealthMetrics:
    """
    Connection pool health metrics.

    PERF-W5-03 (audit 2026-03-14): Optimized locking strategy.
    Monotonic counters (checkouts, checkins, etc.) are mutated directly.
    A threading.Lock is used ONLY for the active_connections and
    peak_active_connections pair to ensure consistency between them.
    """

    # Protected pair: active ↔ peak must stay consistent.
    _active_connections: int = field(default=0, init=False)
    _peak_active_connections: int = field(default=0, init=False)

    # Lock is excluded from __init__ and __repr__ via field metadata
    _lock: threading.Lock = field(
        default_factory=threading.Lock, init=False, repr=False, compare=False
    )
    _total_checkouts: int = field(default=0, init=False)
    _total_checkins: int = field(default=0, init=False)
    _total_invalidations: int = field(default=0, init=False)
    _failed_checkouts: int = field(default=0, init=False)

    @property
    def active_connections(self) -> int:
        """TD-27-02: Lock-free read — may lag by one cycle. For metrics only."""
        return self._active_connections  # PERF-24-01

    @property
    def peak_active_connections(self) -> int:
        """TD-27-02: Lock-free read — may lag by one cycle. For metrics only."""
        return self._peak_active_connections  # PERF-24-01

    @property
    def total_checkouts(self) -> int:
        """TD-27-02: Lock-free read — may lag by one cycle. For metrics only."""
        return self._total_checkouts  # PERF-24-01

    @property
    def total_checkins(self) -> int:
        """TD-27-02: Lock-free read — may lag by one cycle. For metrics only."""
        return self._total_checkins  # PERF-24-01

    @property
    def total_invalidations(self) -> int:
        """TD-27-02: Lock-free read — may lag by one cycle. For metrics only."""
        return self._total_invalidations  # PERF-24-01

    @property
    def failed_checkouts(self) -> int:
        """TD-27-02: Lock-free read — may lag by one cycle. For metrics only."""
        return self._failed_checkouts  # PERF-24-01

    def record_checkout(self) -> None:
        # TD-NEW-006 (audit 2026-03-19): Use lock for all counters.
        # `+= 1` is NOT atomic in Python 3.13+ free-threading (PEP 703).
        with self._lock:
            self._total_checkouts += 1
            self._active_connections += 1
            if self._active_connections > self._peak_active_connections:
                self._peak_active_connections = self._active_connections

    def record_checkin(self) -> None:
        with self._lock:
            self._total_checkins += 1
            self._active_connections = max(0, self._active_connections - 1)

    def record_invalidation(self) -> None:
        with self._lock:
            self._total_invalidations += 1
            self._active_connections = max(0, self._active_connections - 1)

    def record_failed_checkout(self) -> None:
        with self._lock:
            self._failed_checkouts += 1

    def reset_peak_active_connections(self) -> None:
        """Reset the peak active connections counter to current active count. (TD-008)"""
        with self._lock:
            self._peak_active_connections = self._active_connections

    def get_snapshot(self) -> dict[str, int]:
        """Return a consistent point-in-time copy of all counters.

        TD-NEW-006 (audit 2026-03-19): All counters are read inside a single
        lock acquisition to ensure true point-in-time consistency.
        """
        with self._lock:
            return {
                "total_checkouts": self._total_checkouts,
                "total_checkins": self._total_checkins,
                "total_invalidations": self._total_invalidations,
                "active_connections": self._active_connections,
                "peak_active_connections": self._peak_active_connections,
                "failed_checkouts": self._failed_checkouts,
            }


# Global pool metrics instance
_pool_metrics = PoolHealthMetrics()


def get_pool_health_metrics() -> dict[str, int]:
    """Get current pool health metrics snapshot."""
    return _pool_metrics.get_snapshot()


def _build_engine_kwargs(current_settings: Settings) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "pool_pre_ping": True,
        "echo": False,
    }
    if current_settings.database_url.startswith("sqlite"):
        kwargs["poolclass"] = NullPool
        kwargs["connect_args"] = {"timeout": 30.0}
    else:
        # PERF-009 (audit 2026-03-04): Optimize Postgres pool efficiency and safety
        # PERF-01 (audit 2026-03-14): Fast-fail pool defaults — see comment below.
        kwargs["connect_args"] = {
            # RZ-20-06 (audit 2026-03-24): Now configurable via DATABASE_STATEMENT_CACHE_SIZE.
            # Default 0 for PgBouncer compatibility; set to 1024 (asyncpg default)
            # for direct PostgreSQL connections to avoid ~10-20% parsing overhead.
            "statement_cache_size": current_settings.database_statement_cache_size,
            # TD-24-02: Consider auto-detecting PgBouncer at startup to set cache to 1024
            # for direct PostgreSQL connections (10-20% parsing overhead reduction).
            # PERF-01: reduced from 30 s → 15 s. Hard per-statement PG timeout so a
            # runaway query does not block the asyncpg connection for half a minute.
            "command_timeout": 15.0,
            # Visible in pg_stat_activity — makes it easy to attribute load.
            "server_settings": {"application_name": "university-backend"},
        }
        if current_settings.database_pool_size is not None:
            kwargs["pool_size"] = current_settings.database_pool_size
        if current_settings.database_max_overflow is not None:
            kwargs["max_overflow"] = current_settings.database_max_overflow
        # PERF-W14-01 (audit 2026-03-23 Wave 14): raised from 5 s to 30 s.
        # Rationale: a 5 s timeout was originally chosen for fast-fail under
        # steady-state overload, but it also fires during planned PostgreSQL
        # primary failovers (RDS Multi-AZ switchover ~30–60 s, Patroni ~15–30 s).
        # During failover all requests hit QueuePool.checkout(); at 5 s they all
        # fail, creating a hard outage window instead of queuing and recovering.
        # At 30 s, requests queue during the failover and drain cleanly when the
        # new primary comes up, matching user-visible "retry" behaviour.
        # Per-statement timeouts (command_timeout=15 s) remain unchanged — they
        # guard against individual slow queries, which is a separate concern.
        # Operators can still override via DATABASE_POOL_TIMEOUT env var.
        # PERF-20-02 (audit 2026-03-24): Removed dead-code None-check fallbacks.
        # Both fields are typed ``int``/``float`` with Pydantic defaults — they
        # are never None.  The stale ``else 300`` / ``else 30.0`` branches were
        # unreachable and inconsistent with the config default of 540 / 30.0.
        kwargs["pool_timeout"] = current_settings.database_pool_timeout
        kwargs["pool_recycle"] = current_settings.database_pool_recycle
    return kwargs


def _before_cursor_execute(
    conn: Any,
    cursor: Any,
    statement: str,
    parameters: Any,
    context: Any,
    executemany: bool,
) -> None:
    """Store the start time before query execution."""
    _query_start_time.set(time.perf_counter())


def _log_slow_query(
    statement: str, elapsed_ms: float, threshold_ms: float, executemany: bool
) -> None:
    """Consolidated slow query warning logger. (TD-001)"""
    # PERF-20-03 (audit 2026-03-24): Increased from 500 → 1500 chars.
    # Complex JOINs with 3+ selectinload() produce 800-1200 char statements;
    # 500 chars truncated the critical WHERE clause needed for diagnosis.
    truncated_statement = (
        statement[:1500] + "..." if len(statement) > 1500 else statement
    )
    slow_query_logger.warning(
        "Slow query detected: %.2fms",
        elapsed_ms,
        extra={
            "elapsed_ms": elapsed_ms,
            "statement": truncated_statement.replace("\n", " ").strip(),
            "statement_length": len(statement),
            "executemany": executemany,
            "threshold_ms": threshold_ms,
        },
    )


def _after_cursor_execute(
    conn: Any,
    cursor: Any,
    statement: str,
    parameters: Any,
    context: Any,
    executemany: bool,
) -> None:
    """Middleware-level slow query detection (uses global settings)."""
    start_time = _query_start_time.get()
    if start_time is None:
        return

    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
    _query_start_time.set(None)

    # TD-24-07: Future — split into READ (200ms) and WRITE (500ms) thresholds
    # for better OLTP monitoring granularity.
    threshold = getattr(settings, "slow_query_threshold_ms", 500.0)
    if elapsed_ms >= threshold:
        _log_slow_query(statement, elapsed_ms, threshold, executemany)


def _setup_slow_query_logging(engine: AsyncEngine, current_settings: Settings) -> None:
    """
    Set up slow query logging for the given engine.

    Now enabled in all environments when slow_query_logging_enabled is True.
    Uses configurable threshold from settings.

    PERF-2 (audit 2026-02-26): The threshold is captured once in a closure at
    engine-setup time rather than reading ``settings.slow_query_threshold_ms``
    on every single SQL query (which at 10K rps = 10K redundant getattr calls/s).
    """
    if not getattr(current_settings, "slow_query_logging_enabled", False):
        return

    # Capture threshold once — changes require application restart (acceptable).
    _threshold_ms: float = float(
        getattr(current_settings, "slow_query_threshold_ms", 500.0) or 500.0
    )

    def _after_cursor_execute_closure(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        """Closure-based slow query detection (uses captured threshold)."""
        start_time = _query_start_time.get()
        if start_time is None:
            return
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        _query_start_time.set(None)
        if elapsed_ms >= _threshold_ms:
            _log_slow_query(statement, elapsed_ms, _threshold_ms, executemany)

    sync_engine = engine.sync_engine

    # PERF-002 (audit 2026-03-10): Guard against double-registration.
    # Multiple calls to _setup_slow_query_logging() (e.g. from test fixtures or
    # lifespan reinit) would stack duplicate listeners, doubling the perf_counter
    # overhead on every query. event.contains() is the canonical check.
    if event.contains(sync_engine, "before_cursor_execute", _before_cursor_execute):
        return  # Already registered — idempotent, no-op.

    event.listen(sync_engine, "before_cursor_execute", _before_cursor_execute)
    # PERF-2: Use the closure that captured _threshold_ms at setup time,
    # replacing the module-level _after_cursor_execute which called
    # getattr(settings, ...) on every single query execution.
    event.listen(sync_engine, "after_cursor_execute", _after_cursor_execute_closure)
    logger.info(
        "Slow query logging enabled",
        threshold_ms=_threshold_ms,
    )


def _on_checkout(
    dbapi_connection: Any,
    connection_record: Any,
    connection_proxy: Any,
) -> None:
    """Handle connection checkout from pool."""
    _pool_metrics.record_checkout()
    # PERF-6 (audit 2026-03-05): Guard behind is_logger_enabled so the
    # _pool_metrics.active_connections lock access is skipped at 1000+ RPS
    # when DEBUG logging is disabled (the common production case).
    if is_logger_enabled(pool_health_logger, logging.DEBUG):
        pool_health_logger.debug(
            "Connection checkout: active=%d",
            _pool_metrics.active_connections,
        )


def _on_checkin(dbapi_connection: Any, connection_record: Any) -> None:
    """Handle connection checkin to pool."""
    _pool_metrics.record_checkin()
    if is_logger_enabled(pool_health_logger, logging.DEBUG):
        pool_health_logger.debug(
            "Connection checkin: active=%d",
            _pool_metrics.active_connections,
        )


def _on_invalidate(
    dbapi_connection: Any, connection_record: Any, exception: Exception | None
) -> None:
    """Handle connection invalidation."""
    _pool_metrics.record_invalidation()
    pool_health_logger.warning(
        "Connection invalidated",
        active_connections=_pool_metrics.active_connections,
        exception=type(exception).__name__ if exception else "None",
    )


def _on_checkout_failed(exception: Exception, pool: Any) -> None:
    """Handle failed checkout (pool exhausted)."""
    _pool_metrics.record_failed_checkout()
    pool_health_logger.error(
        "Pool checkout failed (exhausted)",
        failed_total=_pool_metrics.failed_checkouts,
        pool_size=pool.size(),
    )


def _setup_pool_health_monitoring(engine: AsyncEngine) -> None:
    """Set up connection pool health monitoring."""
    sync_engine = engine.sync_engine
    pool = sync_engine.pool

    event.listen(pool, "checkout", _on_checkout)
    event.listen(pool, "checkin", _on_checkin)
    event.listen(pool, "invalidate", _on_invalidate)
    # checkout_failed is not a standard SA pool event; guard to avoid
    # InvalidRequestError on NullPool or older SA versions.
    if hasattr(pool.dispatch, "checkout_failed"):
        event.listen(pool, "checkout_failed", _on_checkout_failed)

    logger.info(
        "Pool health monitoring enabled (size=%s, overflow=%s)",
        getattr(pool, "size", lambda: "N/A")(),
        getattr(pool, "overflow", lambda: "N/A")(),
    )


def create_session_factory(
    current_settings: Settings = settings,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession], AsyncEngine | None]:
    engine_kwargs = _build_engine_kwargs(current_settings)
    # RZ-33-02: Mask credentials — log only the host/db portion after '@'.
    _masked = (
        str(current_settings.database_url).split("@")[-1]
        if "@" in str(current_settings.database_url)
        else "<configured>"
    )
    logger.debug("Creating engine for URL: ...@%s", _masked)
    engine = create_async_engine(current_settings.database_url, **engine_kwargs)

    # Enable slow query logging
    _setup_slow_query_logging(engine, current_settings)

    # Enable pool health monitoring
    _setup_pool_health_monitoring(engine)

    # Create read replica engine if configured
    read_replica_engine: AsyncEngine | None = None
    replica_url = getattr(current_settings, "database_read_replica_url", None)
    if replica_url:
        read_replica_engine = create_async_engine(replica_url, **engine_kwargs)
        _setup_pool_health_monitoring(read_replica_engine)
        logger.info("Read replica engine configured")

    session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    return engine, session_factory, read_replica_engine


# RZ-NEW-005 / TD-NEW-001 (audit 2026-03-19): Explicit whitelist of dunder attributes
# that the _LazyProxy is allowed to set on itself. A broad startswith/endswith(__)
# guard allowed ANY __dunder__ to be set including __class__, enabling type-confusion.
_PROXY_ALLOWED_DUNDER_SETATTR: frozenset[str] = frozenset(
    {
        "__class__",  # Required by SQLAlchemy ORM mapper initialization
        "__wrapped__",  # Required by functools.wraps decorators
        "__dict__",  # Required by Pydantic model cloning internals
    }
)


class _LazyProxy:
    """A proxy that delegates all attribute access and calls to an underlying
    object that is initialized later. (TD-4)

    Implements the full Python data model: attribute access, calls, async
    context manager (__aenter__/__aexit__), container protocols (__len__,
    __iter__, __contains__). (TD-NEW-001: LSP compliance, audit 2026-03-19)
    """

    __slots__ = ("_get_target", "_name")

    def __init__(self, get_target: Callable[[], Any], name: str):
        object.__setattr__(self, "_get_target", get_target)
        object.__setattr__(self, "_name", name)

    def _get_current_object(self) -> Any:
        obj = self._get_target()
        if obj is None:
            # TD-5: Automatic lazy initialization with default settings if not
            # explicitly initialized. This prevents RuntimeError in simple scripts
            # or shell environments while maintaining explicit control in the
            # main application lifespan.
            init_database()
            obj = self._get_target()

        if obj is None:
            raise RuntimeError(
                f"Database {self._name} could not be initialized. "
                "Ensure Settings are correctly configured."
            )
        return obj

    def __getattr__(self, name: str) -> Any:
        return getattr(self._get_current_object(), name)

    def __setattr__(self, name: str, value: object) -> None:
        # RZ-NEW-005 (audit 2026-03-19): Use module-level _PROXY_ALLOWED_DUNDER_SETATTR
        # constant — avoids recreating the frozenset on every __setattr__ call.
        if name in _PROXY_ALLOWED_DUNDER_SETATTR:
            setattr(self._get_current_object(), name, value)
            return

        raise AttributeError(
            f"Direct attribute mutation on '{self._name}' database proxy is prohibited. "
            "Configure the engine through Settings before calling init_database()."
        )

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._get_current_object()(*args, **kwargs)

    async def __aenter__(self) -> Any:
        """TD-NEW-001 (audit 2026-03-19): Delegate async context manager entry.

        Allows ``async with engine.connect() as conn`` to work when ``engine``
        is a _LazyProxy. Previously this fell through to __getattr__ which
        worked at runtime but broke async type inference in static analysers.
        """
        return await self._get_current_object().__aenter__()

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Any:
        """TD-NEW-001: Delegate async context manager exit to the underlying object."""
        return await self._get_current_object().__aexit__(exc_type, exc_val, exc_tb)

    def __iter__(self) -> Any:
        """TD-NEW-001: Delegate iteration to the underlying object."""
        return iter(self._get_current_object())

    def __len__(self) -> int:
        """TD-NEW-001: Delegate len() to the underlying object."""
        return len(self._get_current_object())

    def __bool__(self) -> bool:
        """RZ-NEW-005 (audit 2026-03-19): Explicit truthiness check.
        Prevents AsyncSession(bind=proxy) from falling through to __len__
        when bind is truth-tested, which fails on non-container proxies (Engine).
        """
        return bool(self._get_current_object())

    def __contains__(self, item: Any) -> bool:
        """TD-NEW-001: Delegate 'in' operator to the underlying object."""
        return item in self._get_current_object()

    def __repr__(self) -> str:
        try:
            return repr(self._get_current_object())
        except RuntimeError:
            return f"<_LazyProxy for {self._name} (uninitialized)>"


# ── Private storage for actual engines/factories ───────────────────────────
_engine: AsyncEngine | None = None
_async_session: async_sessionmaker[AsyncSession] | None = None
_read_replica_engine: AsyncEngine | None = None
_read_session_factory: async_sessionmaker[AsyncSession] | None = None
# PERF-W19-07: threading lock to prevent concurrent engine creation
# (init_database is sync; asyncio.Lock cannot be awaited here)
_init_lock = threading.Lock()

# ── Public module-level proxies ──────────────────────────────────────────────
# These proxies allow direct imports (from app.core.database import engine) to
# work even if imported before init_database() is called.
engine: Any = _LazyProxy(lambda: _engine, "engine")
async_session: Any = _LazyProxy(lambda: _async_session, "async_session")
read_replica_engine: Any = _LazyProxy(
    lambda: _read_replica_engine, "read_replica_engine"
)
read_session_factory: Any = _LazyProxy(
    lambda: _read_session_factory, "read_session_factory"
)

if TYPE_CHECKING:
    # Tell type checkers these are the real types for better IDE support
    engine: AsyncEngine  # type: ignore[no-redef]
    async_session: async_sessionmaker[AsyncDatabaseSession]  # type: ignore[no-redef]
    read_replica_engine: AsyncEngine | None  # type: ignore[no-redef]
    read_session_factory: async_sessionmaker[AsyncDatabaseSession]  # type: ignore[no-redef]


def init_database(current_settings: Settings | None = None) -> None:
    """Initialise database engines from *current_settings* (defaults to the global
    ``settings`` singleton).

    Idempotent when called without explicit settings and the engine is already
    initialised.  This prevents the test suite from creating a fresh connection
    pool on every test that uses the app lifespan (LifespanManager), which would
    exhaust PostgreSQL's max_connections limit after only a handful of tests.
    """
    global _engine, _async_session, _read_replica_engine, _read_session_factory

    # PERF-W19-07: fast-path check before acquiring the lock to avoid
    # unnecessary contention on the common (already-initialised) code path.
    if _engine is not None and current_settings is None:
        return

    with _init_lock:
        # Re-check inside the lock (double-checked locking) so that a second
        # concurrent caller that passed the fast-path does not create a second
        # engine after the first caller already finished initialisation.
        if _engine is not None and current_settings is None:
            return

        s = current_settings or settings
        _engine, _async_session, _read_replica_engine = create_session_factory(s)

        _read_session_factory = async_sessionmaker(
            _read_replica_engine if _read_replica_engine is not None else _engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

        # RZ-33-02: Mask credentials in database URL before logging.
        _masked_url = (
            str(s.database_url).split("@")[-1]
            if "@" in str(s.database_url)
            else "<configured>"
        )
        _masked_replica = (
            str(s.database_read_replica_url).split("@")[-1]
            if getattr(s, "database_read_replica_url", None)
            and "@" in str(s.database_read_replica_url)
            else "none"
        )
        logger.info(
            "Database initialised: %s (replica: %s)", _masked_url, _masked_replica
        )


def get_read_engine() -> AsyncEngine:
    """Get the engine for read operations (replica if available, otherwise primary)."""
    return _read_replica_engine if _read_replica_engine is not None else _engine  # type: ignore[return-value]


class Base(DeclarativeBase):
    """Declarative Base for all models. (TD-002: id is per-model or mixin)"""


async def get_db() -> AsyncGenerator[AsyncDatabaseSession]:
    # PERF-05 (audit 2026-03-04): Removed the `for _ in range(3)` retry loop.
    # FastAPI generator dependencies yield exactly once — the loop body after
    # `yield` is never re-entered, so all three retry iterations were dead code.
    # Stale connections are already handled by pool_pre_ping=True at engine level.
    async with async_session() as session:
        yield session


async def get_read_db() -> AsyncGenerator[AsyncDatabaseSession]:
    """Get a read-only session (uses replica if configured, otherwise primary)."""
    # Use the pre-allocated read_session_factory for efficiency
    async with read_session_factory() as session:
        yield session


async def check_replication_lag() -> float | None:
    """Query the read-replica replication lag in bytes.

    TD-24-01: Exposes replication lag for monitoring. Returns None if no
    read replica is configured or if the query fails.
    """
    if _read_replica_engine is None:
        return None
    try:
        async with _read_replica_engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT pg_wal_lsn_diff("
                    "  pg_last_wal_receive_lsn(), pg_last_wal_replay_lsn()"
                    ") AS lag_bytes"
                )
            )
            row = result.one_or_none()
            return float(row[0]) if row and row[0] is not None else 0.0
    except (
        OSError,
        ConnectionError,
    ):  # RZ-25-01 + RZ-22-01: narrowed — DB/network errors
        logger.warning("Failed to check replication lag", exc_info=True)
        return None


async def wait_db(
    max_attempts: int = 5,
    base_delay: float = 0.5,
    max_delay: float = 30.0,
) -> None:
    """Ensure the database is reachable before continuing.

    PERF-NEW-004 (audit 2026-03-19): Uses exponential backoff with full jitter
    instead of a fixed delay.  Full jitter formula:
        sleep = random(0, min(max_delay, base_delay * 2^attempt))
    Prevents thundering herd when multiple workers restart simultaneously.
    Reference: https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
    """
    import random  # stdlib — import inside function to avoid polluting module namespace

    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return
        except Exception as exc:  # pragma: no cover - defensive logging  # RZ-22-01-JUSTIFIED: health probe — DB wait retries on any error (reviewed TD-27-04)
            last_exc = exc
            log_func = logger.error if attempt == max_attempts else logger.warning
            log_func(
                "Database unavailable on attempt %s/%s: %s",
                attempt,
                max_attempts,
                exc,
                exc_info=attempt == max_attempts,
            )
            if attempt < max_attempts:
                # Full jitter: sleep in [0, min(max_delay, base * 2^attempt)]
                cap = min(max_delay, base_delay * (2**attempt))
                sleep_time = random.uniform(0, cap)  # nosec B311 — not crypto use  # noqa: S311
                await asyncio.sleep(sleep_time)
    if last_exc is not None:
        raise RuntimeError(
            f"Database connection failed after {max_attempts} attempts: {last_exc}"
        ) from last_exc
