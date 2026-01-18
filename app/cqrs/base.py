from abc import ABC, abstractmethod


class Query(ABC):
    """Base class for all queries."""

    pass


class QueryHandler[TQuery, TResult](ABC):
    """Base class for all query handlers."""

    @abstractmethod
    async def handle(self, query: TQuery) -> TResult:
        """Process the query and return a result."""
        pass
