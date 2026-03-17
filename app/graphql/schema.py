"""GraphQL Schema and Router for FastAPI integration.

This module creates the Strawberry GraphQL schema and router that can be
included in the FastAPI application.
"""

import logging
from collections.abc import AsyncGenerator
from typing import Any

import strawberry
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Request
from strawberry.extensions import (
    AddValidationRules,
    MaxTokensLimiter,
    QueryComplexityLimiter,
    QueryDepthLimiter,
)
from strawberry.extensions.tracing import OpenTelemetryExtension
from strawberry.fastapi import GraphQLRouter

from app.core.config import settings
from app.core.protocols import AsyncDatabaseSession
from app.graphql.context import GraphQLContext
from app.graphql.dataloaders import DataLoaderRegistry
from app.graphql.queries import Query

logger = logging.getLogger(__name__)


@inject
async def get_context(
    request: Request,
    session: FromDishka[AsyncDatabaseSession],
) -> AsyncGenerator[GraphQLContext]:
    """Create GraphQL context for each request.

    MOD-W9-01 (audit 2026-03-16): Session obtained from Dishka DI container
    (Scope.REQUEST) instead of creating a second session via async_session().
    Strawberry calls context_getter as a FastAPI dependency so @inject resolves
    FromDishka[AsyncDatabaseSession] through the same middleware-managed scope
    as every other route.  This eliminates the redundant second connection and
    ensures consistent lifecycle management across REST and GraphQL layers.
    """
    # Try to get current user from auth header.
    # P1-fix (audit 2026-02-26): Use GraphQLTokenValidator which applies the
    # same five-layer security check as the REST get_current_user dependency.
    current_user = None
    try:
        from app.services.auth.graphql_token_validator import GraphQLTokenValidator

        validator = GraphQLTokenValidator(request, session)

        x_user_id = request.headers.get("X-User-ID")
        x_session_id = request.headers.get("X-Session-ID")

        if x_user_id and x_session_id:
            current_user = await validator.validate(x_user_id, x_session_id)
        else:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
                from app.auth.security import decode_token

                payload = decode_token(token)
                if payload:
                    user_id = payload.get("sub")
                    jti = payload.get("jti")

                    if user_id and jti:
                        current_user = await validator.validate(str(user_id), str(jti))
    except Exception as exc:
        from app.auth.security import SecurityError

        if isinstance(exc, SecurityError):
            # Expected auth failures (bad token, revoked session, inactive user)
            # are acceptable for public queries -- silently anonymous.
            pass
        else:
            # RZ-W9-03: Non-auth exceptions (DB timeout, pool exhaustion,
            # asyncpg.TooManyConnectionsError) must NOT silently demote the
            # request to anonymous.  Fail-closed: return 503 so the client
            # retries and the operator sees the real error in logs.
            logger.error(
                "GraphQL context: unexpected error during authentication -- "
                "aborting request to avoid silent anonymous escalation",
                exc_info=exc,
            )
            from fastapi import HTTPException

            raise HTTPException(
                status_code=503,
                detail="Service temporarily unavailable",
            ) from exc

    context = GraphQLContext(
        session=session,
        loaders=DataLoaderRegistry(session),
        current_user=current_user,
    )
    context.request = request
    yield context


def _build_schema_extensions() -> list[Any]:
    """Build the list of Strawberry schema extensions based on environment.

    RZ-5 (audit 2026-02-26): Without depth and token limits an attacker can craft
    deeply-nested or extremely wide queries (GraphQL DoS / query amplification).
    In production, schema introspection is also disabled to prevent automated
    schema enumeration and PoC generation by attackers.
    """

    extensions: list[Any] = [
        # P-02 (audit 2026-03-08): Automatic OTel spans for every GraphQL
        # operation and resolver.
        OpenTelemetryExtension,
        # Prevent deeply-nested query DoS (OWASP API8:2023).
        # max_depth=8 is generous for this read-heavy schema while blocking abuse.
        QueryDepthLimiter(max_depth=8),
        # Prevent query amplification via extremely wide selections.
        # 1000 tokens approx 50 medium-complexity fields with aliases.
        MaxTokensLimiter(max_token_count=1000),
        # TD-W8-06 (re-enabled): Complexity analysis prevents width-based N+1
        # amplification. max_complexity=100: nested list resolvers cost 100 units.
        QueryComplexityLimiter(max_complexity=100),  # type: ignore[call-arg]
    ]

    # Disable introspection in production -- schema enumeration lets attackers
    # auto-generate targeted PoC queries.
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
# production -- it provides a convenient attack surface for ad-hoc query
# crafting and leaks schema shape even when introspection is disabled.
_is_dev_env = settings.environment in {"development", "testing", "local"}
graphql_router = GraphQLRouter(
    schema,
    context_getter=get_context,
    graphql_ide="graphiql" if _is_dev_env else None,
)


__all__ = ["graphql_router", "schema"]
