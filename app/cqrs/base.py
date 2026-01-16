from abc import ABC, abstractmethod
from typing import Generic, TypeVar

TQuery = TypeVar("TQuery")
TResult = TypeVar("TResult")


class Query(ABC):
    """Base class for all queries."""

    pass


class QueryHandler(Generic[TQuery, TResult], ABC):
    """Base class for all query handlers."""

    @abstractmethod
    async def handle(self, query: TQuery) -> TResult:
        """Process the query and return a result."""
        pass
