from abc import ABC, abstractmethod


class Query:
    """Base class for all queries."""

    pass


class QueryHandler[TQuery, TResult](ABC):
    """Base class for all query handlers."""

    @abstractmethod
    async def handle(self, query: TQuery) -> TResult:
        """Process the query and return a result."""
        pass


class Command(ABC):  # noqa: B024
    """Base class for all commands."""

    pass


class CommandHandler[TCommand: Command, TResult](ABC):
    """Base class for all command handlers."""

    @abstractmethod
    async def handle(self, command: TCommand) -> TResult:
        """Process the command and return a result."""
        pass
