"""GraphQL Schema and Router for FastAPI integration.

This module creates the Strawberry GraphQL schema and router that can be
included in the FastAPI application.
"""

from collections.abc import AsyncGenerator
from typing import Any

import strawberry
from dishka.integrations.fastapi import inject
from fastapi import Request
from strawberry.extensions import (
    AddValidationRules,
    MaxTokensLimiter,
    QueryDepthLimiter,
)
from strawberry.extensions.tracing import OpenTelemetryExtension
from strawberry.fastapi import GraphQLRouter

from app.core.config import settings
from app.core.logging import get_logger
from app.core.protocols import AsyncDatabaseSession
from app.graphql.context import GraphQLContext
from app.graphql.dataloaders import DataLoaderRegistry
from app.graphql.extensions import (
    PersistedQueryExtension,
    QueryCostExtension,
    RequestTimeoutExtension,
)
from app.graphql.queries import Query

logger = get_logger(__name__)


@inject
async def get_context(
    request: Request,
) -> AsyncGenerator[GraphQLContext]:
    """Create GraphQL context for each request.

    MOD-W9-01: Session and PermissionChecker obtained from Dishka container
    attached to the request state. This avoids dependency injection issues
    within Strawberry's context getter.
    """
    container = request.state.dishka_container
    try:
        session = await container.get(AsyncDatabaseSession)
    except Exception as exc:  # RZ-22-01-JUSTIFIED: convert-to-domain — converts DI resolution errors to HTTPException 503 (reviewed TD-27-04)
        logger.error("Failed to resolve AsyncDatabaseSession from container: %s", exc)
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="Database unavailable") from exc

    try:
        # TD-TEST: Respect legacy FastAPI overrides for PermissionChecker if present (e.g. mock_spicedb_permissions fixture)
        from app.auth.rbac import PermissionChecker

        if PermissionChecker in request.app.dependency_overrides:
            checker = request.app.dependency_overrides[PermissionChecker]()
        else:
            checker = await container.get(PermissionChecker)
    except Exception as exc:  # RZ-22-01-JUSTIFIED: optional dependency — PermissionChecker may not be available (reviewed TD-27-04)
        # P1: If PermissionChecker is missing (e.g. in tests without SpiceDB mock),
        # we MUST NOT crash. But we also MUST NOT allow access to protected resources.
        # Queries using 'checker' will catch exceptions and fail-closed.
        logger.warning("PermissionChecker not available in container: %s", exc)
        checker = None  # Resolver will handle None checker safely
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
    except Exception as exc:  # RZ-22-01-JUSTIFIED: fail-closed auth — re-raises non-SecurityError as 503 (reviewed TD-27-04)
        from fastapi import HTTPException

        from app.auth.security import SecurityError

        if isinstance(exc, SecurityError):
            # TD-27-01: Only exact SecurityError demotes to anonymous. Subclasses
            # with different semantics (e.g. AccountLocked) should be added to the
            # tuple explicitly to prevent silent escalation.
            if type(exc) is SecurityError:
                pass
            else:
                logger.warning(
                    "GraphQL context: unrecognized SecurityError subclass %s — "
                    "failing closed",
                    type(exc).__name__,
                    exc_info=exc,
                )
                raise HTTPException(
                    status_code=503,
                    detail="Service temporarily unavailable",
                ) from exc
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
        checker=checker,
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
        # RZ-21-01 (audit 2026-03-25 Wave 21): Per-query cost analysis blocks
        # list-field fan-out that evades depth and token limits.  The extension
        # weights list-returning fields (chats, messages, users, etc.) at 5×
        # scalar cost, rejects queries exceeding 200 cost, and enforces a
        # per-user budget of 1 000 cost/minute via Redis (in-memory fallback).
        QueryCostExtension,
        # RZ-21-04 (audit 2026-03-25 Wave 21): Hard 30-second deadline for the
        # entire GraphQL execution phase.  Individual SQL statements have a 15 s
        # timeout, but chained resolvers can accumulate multiple sequential DB
        # round-trips.  This caps the total request wall-clock time.
        RequestTimeoutExtension,
    ]

    # Disable introspection in production -- schema enumeration lets attackers
    # auto-generate targeted PoC queries.
    _is_prod = settings.environment not in {"development", "testing", "local"}
    if _is_prod:
        from graphql.validation import NoSchemaIntrospectionCustomRule

        extensions.append(AddValidationRules([NoSchemaIntrospectionCustomRule]))

        # MOD-21-02 (audit 2026-03-25 Wave 21): Persisted-query allowlist rejects
        # unknown queries in production.  Requires query-manifest.json alongside
        # the backend — generated by the frontend build process.  Gracefully
        # degrades to allow-all when the manifest is absent.
        extensions.append(PersistedQueryExtension)

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
