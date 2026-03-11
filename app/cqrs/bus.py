import logging
from collections.abc import Callable, Sequence
from typing import Any, Protocol, TypeVar

from dishka import AsyncContainer

from app.cqrs.base import Command, CommandHandler, Query, QueryHandler

TQuery = TypeVar("TQuery", bound=Query)
TResult = TypeVar("TResult")
TCommand = TypeVar("TCommand", bound=Command)

logger = logging.getLogger(__name__)


class Middleware(Protocol):
    """Protocol for CQRS bus middleware."""

    async def __call__(
        self,
        message: Query | Command,
        next_handler: Callable[[Query | Command], Any],
    ) -> Any:
        ...


class LoggingMiddleware:
    """Standard middleware for logging CQRS operations."""

    async def __call__(
        self,
        message: Query | Command,
        next_handler: Callable[[Query | Command], Any],
    ) -> Any:
        msg_type = "Command" if isinstance(message, Command) else "Query"
        name = type(message).__name__
        logger.debug(f"Executing {msg_type}: {name}")
        try:
            result = await next_handler(message)
            logger.debug(f"Finished {msg_type}: {name}")
            return result
        except Exception as e:
            logger.error(f"Error executing {msg_type} {name}: {e}", exc_info=True)
            raise


class QueryBus:
    """Dispatches queries to their respective handlers using the Dishka DI container."""

    def __init__(
        self,
        container: AsyncContainer,
        middleware: Sequence[Middleware] | None = None,
    ) -> None:
        self._container = container
        self._registry: dict[type[Query], type[QueryHandler[Any, Any]]] = {}
        self._middleware = list(middleware) if middleware else []

    def register(
        self,
        query_type: type[TQuery],
        handler_type: type[QueryHandler[TQuery, TResult]],
    ) -> None:
        """Register a query type to its handler type."""
        self._registry[query_type] = handler_type

    async def execute(self, query: TQuery) -> Any:
        handler_type = self._registry.get(type(query))
        if not handler_type:
            raise ValueError(f"No handler registered for query: {type(query).__name__}")

        async def _handle(msg: Any) -> Any:
            handler = await self._container.get(handler_type)  # type: ignore[arg-type]
            return await handler.handle(msg)

        # Build middleware chain
        chain = _handle
        for m in reversed(self._middleware):

            def wrap(current_m: Middleware, next_h: Callable[[Any], Any]):
                async def _wrapper(msg: Any) -> Any:
                    return await current_m(msg, next_h)

                return _wrapper

            chain = wrap(m, chain)

        return await chain(query)


class CommandBus:
    """Dispatches commands to their respective handlers using the Dishka DI container."""

    def __init__(
        self,
        container: AsyncContainer,
        middleware: Sequence[Middleware] | None = None,
    ) -> None:
        self._container = container
        self._registry: dict[type[Command], type[CommandHandler[Any, Any]]] = {}
        self._middleware = list(middleware) if middleware else []

    def register(
        self,
        command_type: type[TCommand],
        handler_type: type[CommandHandler[TCommand, TResult]],
    ) -> None:
        """Register a command type to its handler type."""
        self._registry[command_type] = handler_type

    async def execute(self, command: TCommand) -> Any:
        handler_type = self._registry.get(type(command))
        if not handler_type:
            raise ValueError(
                f"No handler registered for command: {type(command).__name__}"
            )

        async def _handle(msg: Any) -> Any:
            handler = await self._container.get(handler_type)  # type: ignore[arg-type]
            return await handler.handle(msg)

        # Build middleware chain
        chain = _handle
        for m in reversed(self._middleware):

            def wrap(current_m: Middleware, next_h: Callable[[Any], Any]):
                async def _wrapper(msg: Any) -> Any:
                    return await current_m(msg, next_h)

                return _wrapper

            chain = wrap(m, chain)

        return await chain(command)
