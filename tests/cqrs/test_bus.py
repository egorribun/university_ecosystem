"""Unit tests for the CQRS bus, middleware chain, and handler contract.

The CQRS module ships only the dispatcher + middleware infrastructure;
true write-side idempotency is the responsibility of individual command
handlers (which call into ORM/UoW layers tested elsewhere). We pin the
dispatcher contract:

* ``CommandBus.execute`` and ``QueryBus.execute`` route to registered
  handlers and raise ``ValueError`` for unregistered types;
* the same command/query type can be dispatched repeatedly (re-entrant);
* the middleware chain wraps the handler outermost-first;
* middleware can short-circuit and bypass the handler entirely;
* ``LoggingMiddleware`` logs success and re-raises on error;
* ``CommandHandler`` / ``QueryHandler`` are abstract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.cqrs.base import Command, CommandHandler, Query, QueryHandler
from app.cqrs.bus import CommandBus, LoggingMiddleware, QueryBus, _build_chain

# ── Test doubles ─────────────────────────────────────────────────────────────


@dataclass
class _PingCmd(Command):
    payload: int = 0


@dataclass
class _PongCmd(Command):
    pass


@dataclass
class _PingQuery(Query):
    name: str = ""


class _RecordingCommandHandler(CommandHandler[_PingCmd, int]):
    """Handler that records each invocation for assertion."""

    def __init__(self) -> None:
        self.calls: list[_PingCmd] = []

    async def handle(self, command: _PingCmd) -> int:
        self.calls.append(command)
        return command.payload * 2


class _RecordingQueryHandler(QueryHandler[_PingQuery, str]):
    def __init__(self) -> None:
        self.calls: list[_PingQuery] = []

    async def handle(self, query: _PingQuery) -> str:
        self.calls.append(query)
        return f"hello {query.name}"


def _container_with(*pairs: tuple[type, Any]) -> Any:
    """Build a Dishka-shaped async container that returns specific instances."""
    container = MagicMock()
    mapping = dict(pairs)

    async def _get(handler_type: type) -> Any:
        return mapping[handler_type]

    container.get = AsyncMock(side_effect=_get)
    return container


# ── 1. Abstract base classes ─────────────────────────────────────────────────


class TestAbstractBaseClasses:
    def test_command_handler_is_abstract(self) -> None:
        """``CommandHandler.handle`` is abstract — instantiating fails."""
        with pytest.raises(TypeError):
            CommandHandler()  # type: ignore[abstract]

    def test_query_handler_is_abstract(self) -> None:
        with pytest.raises(TypeError):
            QueryHandler()  # type: ignore[abstract]

    @pytest.mark.asyncio
    async def test_base_handler_pass_coverage(self) -> None:
        """Call super().handle to execute abstract base passes under coverage."""

        class ConcreteQueryHandler(QueryHandler[_PingQuery, None]):
            async def handle(self, query: _PingQuery) -> None:
                await super().handle(query)

        class ConcreteCommandHandler(CommandHandler[_PingCmd, None]):
            async def handle(self, command: _PingCmd) -> None:
                await super().handle(command)

        await ConcreteQueryHandler().handle(_PingQuery())
        await ConcreteCommandHandler().handle(_PingCmd(42))

    def test_command_subclass_can_be_instantiated(self) -> None:
        """``Command`` itself is not strict-abstract — subclasses work."""
        cmd = _PingCmd(payload=5)
        assert isinstance(cmd, Command)


# ── 2. CommandBus.execute ────────────────────────────────────────────────────


class TestCommandBusExecute:
    @pytest.mark.asyncio
    async def test_routes_registered_command(self) -> None:
        handler = _RecordingCommandHandler()
        container = _container_with((_RecordingCommandHandler, handler))
        bus = CommandBus(container)
        bus.register(_PingCmd, _RecordingCommandHandler)

        result = await bus.execute(_PingCmd(payload=21))

        assert result == 42
        assert len(handler.calls) == 1

    @pytest.mark.asyncio
    async def test_unregistered_command_raises_value_error(self) -> None:
        bus = CommandBus(_container_with())
        with pytest.raises(ValueError, match="No handler registered"):
            await bus.execute(_PingCmd(payload=0))

    @pytest.mark.asyncio
    async def test_dispatching_same_command_twice_invokes_handler_twice(self) -> None:
        """The bus is reentrant — repeated dispatch is not deduplicated."""
        handler = _RecordingCommandHandler()
        container = _container_with((_RecordingCommandHandler, handler))
        bus = CommandBus(container)
        bus.register(_PingCmd, _RecordingCommandHandler)

        await bus.execute(_PingCmd(payload=1))
        await bus.execute(_PingCmd(payload=2))

        assert [c.payload for c in handler.calls] == [1, 2]

    @pytest.mark.asyncio
    async def test_distinct_command_types_route_independently(self) -> None:
        ping = _RecordingCommandHandler()

        class _PongHandler(CommandHandler[_PongCmd, str]):
            async def handle(self, command: _PongCmd) -> str:
                return "pong"

        pong = _PongHandler()
        container = _container_with(
            (_RecordingCommandHandler, ping),
            (_PongHandler, pong),
        )
        bus = CommandBus(container)
        bus.register(_PingCmd, _RecordingCommandHandler)
        bus.register(_PongCmd, _PongHandler)

        assert await bus.execute(_PingCmd(payload=3)) == 6
        assert await bus.execute(_PongCmd()) == "pong"


# ── 3. QueryBus.execute ──────────────────────────────────────────────────────


class TestQueryBusExecute:
    @pytest.mark.asyncio
    async def test_routes_registered_query(self) -> None:
        handler = _RecordingQueryHandler()
        container = _container_with((_RecordingQueryHandler, handler))
        bus = QueryBus(container)
        bus.register(_PingQuery, _RecordingQueryHandler)

        result = await bus.execute(_PingQuery(name="world"))

        assert result == "hello world"

    @pytest.mark.asyncio
    async def test_unregistered_query_raises(self) -> None:
        bus = QueryBus(_container_with())
        with pytest.raises(ValueError, match="No handler registered"):
            await bus.execute(_PingQuery(name="x"))


# ── 4. Middleware chain ──────────────────────────────────────────────────────


class TestMiddlewareChain:
    @pytest.mark.asyncio
    async def test_empty_middleware_list_calls_handler_directly(self) -> None:
        seen: list[str] = []

        async def handler(msg: Any) -> str:
            seen.append("handler")
            return "ok"

        chain = _build_chain([], handler)
        assert await chain(_PingCmd()) == "ok"
        assert seen == ["handler"]

    @pytest.mark.asyncio
    async def test_outermost_middleware_runs_first(self) -> None:
        """Order: m1 → m2 → handler → m2 (after) → m1 (after)."""
        seen: list[str] = []

        class _M1:
            async def __call__(self, msg, next_handler):  # type: ignore[no-untyped-def]
                seen.append("m1-before")
                result = await next_handler(msg)
                seen.append("m1-after")
                return result

        class _M2:
            async def __call__(self, msg, next_handler):  # type: ignore[no-untyped-def]
                seen.append("m2-before")
                result = await next_handler(msg)
                seen.append("m2-after")
                return result

        async def handler(msg: Any) -> str:
            seen.append("handler")
            return "ok"

        chain = _build_chain([_M1(), _M2()], handler)
        assert await chain(_PingCmd()) == "ok"
        assert seen == [
            "m1-before",
            "m2-before",
            "handler",
            "m2-after",
            "m1-after",
        ]

    @pytest.mark.asyncio
    async def test_middleware_can_short_circuit(self) -> None:
        """A middleware may return without calling next — handler is skipped."""
        seen: list[str] = []

        class _ShortCircuit:
            async def __call__(self, msg, next_handler):  # type: ignore[no-untyped-def]
                seen.append("short")
                return "intercepted"

        async def handler(msg: Any) -> str:
            seen.append("handler")
            return "ok"

        chain = _build_chain([_ShortCircuit()], handler)
        assert await chain(_PingCmd()) == "intercepted"
        assert seen == ["short"]

    @pytest.mark.asyncio
    async def test_middleware_observes_handler_exception(self) -> None:
        """Middleware can intercept exceptions from inner handler."""
        observed: list[BaseException] = []

        class _Catcher:
            async def __call__(self, msg, next_handler):  # type: ignore[no-untyped-def]
                try:
                    return await next_handler(msg)
                except RuntimeError as exc:
                    observed.append(exc)
                    raise

        async def failing_handler(msg: Any) -> str:
            raise RuntimeError("boom")

        chain = _build_chain([_Catcher()], failing_handler)
        with pytest.raises(RuntimeError, match="boom"):
            await chain(_PingCmd())
        assert len(observed) == 1


# ── 5. LoggingMiddleware ─────────────────────────────────────────────────────


class TestLoggingMiddleware:
    @pytest.mark.asyncio
    async def test_passes_through_success(self) -> None:
        async def handler(msg: Any) -> int:
            return 7

        result = await LoggingMiddleware()(_PingCmd(), handler)
        assert result == 7

    @pytest.mark.asyncio
    async def test_re_raises_on_error(self) -> None:
        async def handler(msg: Any) -> int:
            raise ValueError("nope")

        with pytest.raises(ValueError, match="nope"):
            await LoggingMiddleware()(_PingCmd(), handler)

    @pytest.mark.asyncio
    async def test_works_for_query_message(self) -> None:
        """LoggingMiddleware works for both Command and Query payloads."""

        async def handler(msg: Any) -> str:
            return "queried"

        result = await LoggingMiddleware()(_PingQuery(name="x"), handler)
        assert result == "queried"


# ── 6. End-to-end bus + middleware ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_bus_executes_with_logging_middleware() -> None:
    """A CommandBus with LoggingMiddleware logs but otherwise behaves identically."""
    handler = _RecordingCommandHandler()
    container = _container_with((_RecordingCommandHandler, handler))
    bus = CommandBus(container, middleware=[LoggingMiddleware()])
    bus.register(_PingCmd, _RecordingCommandHandler)

    result = await bus.execute(_PingCmd(payload=10))

    assert result == 20
    assert len(handler.calls) == 1
