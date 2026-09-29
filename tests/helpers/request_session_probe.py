"""Real ``AsyncSession`` ownership probe used by BE-04 regression tests.

The probe deliberately keeps all engines and factories local to the test.  It
does not replace application dependencies with mocks: each observation runs a
real ``SELECT 1`` and records the session identity and pool lifecycle.  The
same utility can be reused while route domains are migrated from the legacy
FastAPI dependency to Dishka.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


@dataclass
class SessionObservation:
    """Lifecycle facts collected for one request probe."""

    session_ids: dict[str, int] = field(default_factory=dict)
    checkouts: int = 0
    checkins: int = 0
    begins: int = 0
    commits: int = 0
    rollbacks: int = 0
    exits: int = 0

    def record_session(self, owner: str, session: AsyncSession) -> None:
        self.session_ids[owner] = id(session)

    def assert_single_owner(self, *owners: str) -> None:
        """Assert that all named DB participants share one session identity."""

        ids = {self.session_ids[owner] for owner in owners}
        assert len(ids) == 1, f"duplicate request session owners: {self.session_ids!r}"


@dataclass(frozen=True)
class ProbeSessions:
    """Two independently-created factories used to reproduce split ownership."""

    legacy: async_sessionmaker[AsyncSession]
    dishka: async_sessionmaker[AsyncSession]


class RequestSessionProbe:
    """Own two real SQLite engines and observe request session lifecycle."""

    def __init__(self) -> None:
        self._temporary_directory = TemporaryDirectory(prefix="be04-session-")
        root = Path(self._temporary_directory.name)
        self._engines: tuple[AsyncEngine, AsyncEngine] = tuple(
            create_async_engine(
                f"sqlite+aiosqlite:///{root / name}",
                pool_pre_ping=True,
            )
            for name in ("legacy.db", "dishka.db")
        )
        self.sessions = ProbeSessions(
            legacy=async_sessionmaker(self._engines[0], expire_on_commit=False),
            dishka=async_sessionmaker(self._engines[1], expire_on_commit=False),
        )
        self.observation = SessionObservation()
        self._listeners: list[tuple[Engine, str, Callable[..., Any]]] = []
        for engine in self._engines:
            sync_engine = engine.sync_engine
            for event_name, callback in (
                ("checkout", self._on_checkout),
                ("checkin", self._on_checkin),
                ("begin", self._on_begin),
                ("commit", self._on_commit),
                ("rollback", self._on_rollback),
            ):
                event.listen(sync_engine, event_name, callback)
                self._listeners.append((sync_engine, event_name, callback))

    def _on_checkout(self, *_args: object) -> None:
        self.observation.checkouts += 1

    def _on_checkin(self, *_args: object) -> None:
        self.observation.checkins += 1

    def _on_begin(self, *_args: object) -> None:
        self.observation.begins += 1

    def _on_commit(self, *_args: object) -> None:
        self.observation.commits += 1

    def _on_rollback(self, *_args: object) -> None:
        self.observation.rollbacks += 1

    @asynccontextmanager
    async def request(self) -> AsyncIterator[ProbeSessions]:
        """Open both candidate owners and close them exactly once."""

        legacy = self.sessions.legacy()
        dishka = self.sessions.dishka()
        try:
            yield ProbeSessions(legacy=legacy, dishka=dishka)
        finally:
            await legacy.close()
            await dishka.close()
            self.observation.exits += 2

    async def execute(self, owner: str, session: AsyncSession) -> int:
        """Execute a real query and record the owner session identity."""

        self.observation.record_session(owner, session)
        await session.execute(text("SELECT 1"))
        return id(session)

    async def close(self) -> None:
        for sync_engine, event_name, callback in self._listeners:
            event.remove(sync_engine, event_name, callback)
        await self._engines[0].dispose()
        await self._engines[1].dispose()
        self._temporary_directory.cleanup()

    async def __aenter__(self) -> RequestSessionProbe:
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.close()
