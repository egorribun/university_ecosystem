from abc import ABC, abstractmethod
from typing import Generic, TypeVar

TQuery = TypeVar("TQuery")
TResult = TypeVar("TResult")


class Query:
    """Base class for all queries."""

    pass


class QueryHandler(ABC, Generic[TQuery, TResult]):
    """Base class for all query handlers."""

    @abstractmethod
    async def handle(self, query: TQuery) -> TResult:
        """Process the query and return a result."""
        pass


class Command(ABC):  # noqa: B024
    """Base class for all commands."""
    pass


TCommand = TypeVar("TCommand", bound=Command)


class CommandHandler(ABC, Generic[TCommand, TResult]):
    """Base class for all command handlers."""

    @abstractmethod
    async def handle(self, command: TCommand) -> TResult:
        """Process the command and return a result."""
        pass
