from collections.abc import Callable, Sequence
from typing import Any, Protocol, TypeVar

from dishka import AsyncContainer

from app.core.logging import get_logger
from app.cqrs.base import Command, CommandHandler, Query, QueryHandler

TQuery = TypeVar("TQuery", bound=Query)
TResult = TypeVar("TResult")
TCommand = TypeVar("TCommand", bound=Command)

logger = get_logger(__name__)


class Middleware(Protocol):
    """Protocol for CQRS bus middleware."""

    async def __call__(
        self,
        message: Query | Command,
        next_handler: Callable[[Query | Command], Any],
    ) -> Any: ...  # pragma: no branch


# LOW-W19: DRY — extracted shared middleware chain builder used by both buses.
# Defined after Middleware Protocol to avoid a forward reference.
def _build_chain(
    middleware: Sequence[Middleware],
    handler: Callable[[Any], Any],
) -> Callable[[Any], Any]:
    """Wrap *handler* in the middleware stack, outermost first."""
    chain: Callable[[Any], Any] = handler
    for m in reversed(middleware):

        def wrap(
            current_m: Middleware, next_h: Callable[[Any], Any]
        ) -> Callable[[Any], Any]:
            async def _wrapper(msg: Any) -> Any:
                return await current_m(msg, next_h)

            return _wrapper

        chain = wrap(m, chain)
    return chain


class LoggingMiddleware:
    """Standard middleware for logging CQRS operations."""

    async def __call__(
        self,
        message: Query | Command,
        next_handler: Callable[[Query | Command], Any],
    ) -> Any:
        msg_type = "Command" if isinstance(message, Command) else "Query"
        name = type(message).__name__
        logger.debug("Executing %s: %s", msg_type, name)  # LOW-W19: lazy logging
        try:
            result = await next_handler(message)
            logger.debug("Finished %s: %s", msg_type, name)
            return result
        except Exception as e:  # RZ-22-01-JUSTIFIED: re-raise-after-cleanup — logs then re-raises (reviewed TD-27-04)
            logger.error("Error executing %s %s: %s", msg_type, name, e, exc_info=True)
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
            handler = await self._container.get(handler_type)
            return await handler.handle(msg)

        # LOW-W19: middleware chain construction delegated to shared _build_chain helper
        chain = _build_chain(self._middleware, _handle)
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
            handler = await self._container.get(handler_type)
            return await handler.handle(msg)

        # LOW-W19: middleware chain construction delegated to shared _build_chain helper
        chain = _build_chain(self._middleware, _handle)
        return await chain(command)
