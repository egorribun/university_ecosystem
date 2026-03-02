"""GraphQL Schema and Router for FastAPI integration.

This module creates the Strawberry GraphQL schema and router that can be
included in the FastAPI application.
"""

import logging
from collections.abc import AsyncGenerator

import strawberry
from fastapi import Request
from strawberry.extensions import (
    AddValidationRules,
    MaxTokensLimiter,
    QueryDepthLimiter,
)
from strawberry.fastapi import GraphQLRouter

from app.core.config import settings
from app.graphql.context import GraphQLContext
from app.graphql.dataloaders import DataLoaderRegistry
from app.graphql.queries import Query

logger = logging.getLogger(__name__)


async def get_context(
    request: Request,
) -> AsyncGenerator[GraphQLContext]:
    """Create GraphQL context for each request.

    This function is called by Strawberry for each GraphQL request.
    It sets up the database session and DataLoaders.
    """
    from app.core.database import async_session

    # Create a new session for this request
    async with async_session() as session:
        # Try to get current user from auth header.
        # P1-fix (audit 2026-02-26): Use GraphQLTokenValidator which applies the
        # same five-layer security check as the REST get_current_user dependency
        # (Redis revocation → DB session → expiry → fingerprint → user active).
        current_user = None
        try:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
                from app.auth.security import decode_token

                payload = decode_token(token)
                if payload:
                    user_id = payload.get("sub")
                    jti = payload.get("jti")

                    if user_id and jti:
                        from app.services.auth.graphql_token_validator import (
                            GraphQLTokenValidator,
                        )

                        validator = GraphQLTokenValidator(request, session)
                        current_user = await validator.validate(str(user_id), str(jti))
        except Exception as exc:
            # Auth failures are acceptable for public queries; log for debugging.
            from app.auth.security import SecurityError

            if not isinstance(exc, SecurityError):
                logger.debug("GraphQL auth fail: %s", exc)

        context = GraphQLContext(
            session=session,
            loaders=DataLoaderRegistry(session),
            current_user=current_user,
        )
        context.request = request
        yield context


def _build_schema_extensions() -> list:
    """Build the list of Strawberry schema extensions based on environment.

    RZ-5 (audit 2026-02-26): Without depth and token limits an attacker can craft
    deeply-nested or extremely wide queries (GraphQL DoS / query amplification).
    In production, schema introspection is also disabled to prevent automated
    schema enumeration and PoC generation by attackers.
    """
    extensions: list = [
        # Prevent deeply-nested query DoS (OWASP API8:2023).
        # max_depth=8 is generous for this read-heavy schema while blocking abuse.
        QueryDepthLimiter(max_depth=8),
        # Prevent query amplification via extremely wide selections.
        # 1000 tokens ≈ ~50 medium-complexity fields with aliases.
        MaxTokensLimiter(max_token_count=1000),
    ]

    # Disable introspection in production — schema enumeration lets attackers
    # auto-generate targeted PoC queries. The GraphiQL IDE is already hidden
    # from OpenAPI in non-dev environments.
    _is_prod = settings.environment not in {"development", "testing", "local"}
    if _is_prod:
        from graphql.validation import NoSchemaIntrospectionCustomRule

        extensions.append(AddValidationRules([NoSchemaIntrospectionCustomRule]))

    return extensions


# Create the schema with DoS protection extensions.
schema = strawberry.Schema(
    query=Query,
    # mutation=Mutation,  # Add when mutations are implemented
    extensions=_build_schema_extensions(),
)

# RZ-5 (audit 2026-02-26): GraphQL IDE (GraphiQL) must not be exposed in
# production — it provides a convenient attack surface for ad-hoc query
# crafting and leaks schema shape even when introspection is disabled.
_is_dev_env = settings.environment in {"development", "testing", "local"}
graphql_router = GraphQLRouter(
    schema,
    context_getter=get_context,
    graphql_ide="graphiql" if _is_dev_env else None,
)


__all__ = ["graphql_router", "schema"]
