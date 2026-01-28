"""GraphQL Schema and Router for FastAPI integration.

This module creates the Strawberry GraphQL schema and router that can be
included in the FastAPI application.
"""

from __future__ import annotations

import logging

import strawberry
from fastapi import Request
from strawberry.fastapi import GraphQLRouter

from app.graphql.context import GraphQLContext
from app.graphql.dataloaders import DataLoaderRegistry
from app.graphql.queries import Query

logger = logging.getLogger(__name__)


async def get_context(
    request: Request,
) -> GraphQLContext:
    """Create GraphQL context for each request.

    This function is called by Strawberry for each GraphQL request.
    It sets up the database session and DataLoaders.
    """
    from app.core.database import async_session

    # Create a new session for this request
    async with async_session() as session:
        # Try to get current user from auth header
        current_user = None
        try:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
                from app.auth.security import decode_token

                payload = decode_token(token)
                if payload:
                    user_id = payload.get("sub")
                    if user_id:
                        from sqlalchemy import select

                        from app.models import User

                        result = await session.execute(
                            select(User).where(User.id == int(user_id))
                        )
                        current_user = result.scalar_one_or_none()
        except Exception as exc:
            # Note: Auth failures are acceptable for public queries,
            # but we should log them for debugging
            from app.auth.security import SecurityError

            if not isinstance(exc, SecurityError):
                logger.debug("GraphQL auth fail: %s", exc)
            pass

        context = GraphQLContext(
            session=session,
            loaders=DataLoaderRegistry(session),
            current_user=current_user,
        )
        context.request = request
        yield context


# Create the schema
schema = strawberry.Schema(
    query=Query,
    # mutation=Mutation,  # Add when mutations are implemented
)

# Create the router for FastAPI
graphql_router = GraphQLRouter(
    schema,
    context_getter=get_context,
    graphql_ide="graphiql",  # Enable GraphiQL IDE at /graphql
)


__all__ = ["schema", "graphql_router"]
