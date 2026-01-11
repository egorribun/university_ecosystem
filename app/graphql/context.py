"""GraphQL context for request handling.

The context is created for each GraphQL request and provides access to:
- Database session
- DataLoaders (for N+1 prevention)
- Current user (if authenticated)
- Request metadata
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from starlette.requests import Request

    from app.graphql.dataloaders import DataLoaderRegistry
    from app.models import User


@dataclass
class GraphQLContext:
    """Context object available in all GraphQL resolvers via info.context."""

    request: Request
    session: AsyncSession
    loaders: DataLoaderRegistry
    current_user: User | None = None

    @property
    def is_authenticated(self) -> bool:
        return self.current_user is not None
