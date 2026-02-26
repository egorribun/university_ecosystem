from typing import Any, TypeVar

from dishka import AsyncContainer

from app.cqrs.base import Command, CommandHandler, Query, QueryHandler

TQuery = TypeVar("TQuery", bound=Query)
TResult = TypeVar("TResult")
TCommand = TypeVar("TCommand", bound=Command)


class QueryBus:
    """Dispatches queries to their respective handlers using the Dishka DI container."""

    def __init__(self, container: AsyncContainer) -> None:
        self._container = container
        self._registry: dict[type[Query], type[QueryHandler[Any, Any]]] = {}

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

        # Resolve the handler instance from the Dishka container
        handler = await self._container.get(handler_type)
        return await handler.handle(query)


class CommandBus:
    """Dispatches commands to their respective handlers using the Dishka DI container."""

    def __init__(self, container: AsyncContainer) -> None:
        self._container = container
        self._registry: dict[type[Command], type[CommandHandler[Any, Any]]] = {}

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

        # Resolve the handler instance from the Dishka container
        handler = await self._container.get(handler_type)
        return await handler.handle(command)
