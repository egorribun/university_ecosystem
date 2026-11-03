"""Finite request-failure metadata; never inspect exception messages or payloads."""

from __future__ import annotations

import re
from uuid import UUID, uuid4

from fastapi.exceptions import ResponseValidationError
from sqlalchemy import exc
from sqlalchemy.dialects.postgresql.asyncpg import AsyncAdapt_asyncpg_dbapi

from app.core.logging import get_logger

_SQLSTATE = re.compile(r"[A-Z0-9]{5}", re.ASCII)
# Exact framework classes only: subclasses can replace orig/__dict__ with
# descriptors. Unknown wrappers and drivers deliberately remain UNKNOWN.
_DBAPI_WRAPPERS = frozenset(
    {
        exc.DBAPIError,
        exc.DatabaseError,
        exc.DataError,
        exc.IntegrityError,
        exc.InterfaceError,
        exc.InternalError,
        exc.NotSupportedError,
        exc.OperationalError,
        exc.ProgrammingError,
    }
)
_ASYNCPG_ERRORS = frozenset(
    {
        AsyncAdapt_asyncpg_dbapi.Error,
        AsyncAdapt_asyncpg_dbapi.InterfaceError,
        AsyncAdapt_asyncpg_dbapi.DatabaseError,
        AsyncAdapt_asyncpg_dbapi.InternalError,
        AsyncAdapt_asyncpg_dbapi.OperationalError,
        AsyncAdapt_asyncpg_dbapi.ProgrammingError,
        AsyncAdapt_asyncpg_dbapi.IntegrityError,
        AsyncAdapt_asyncpg_dbapi.DataError,
        AsyncAdapt_asyncpg_dbapi.NotSupportedError,
        AsyncAdapt_asyncpg_dbapi.InternalServerError,
        AsyncAdapt_asyncpg_dbapi.InternalClientError,
        AsyncAdapt_asyncpg_dbapi.InvalidCachedStatementError,
    }
)
# Subtypes precede their bases; tokens are authored, never derived from names.
_DATABASE_KINDS: tuple[tuple[type[exc.SQLAlchemyError], str], ...] = (
    (exc.MissingGreenlet, "missing_greenlet"),
    (exc.IntegrityError, "integrity"),
    (exc.OperationalError, "operational"),
    (exc.ProgrammingError, "programming"),
    (exc.NoResultFound, "no_result"),
    (exc.MultipleResultsFound, "multiple_results"),
    (exc.InvalidRequestError, "invalid_request"),
    (exc.StatementError, "statement"),
)


def _sqlstate(error: exc.SQLAlchemyError | ResponseValidationError) -> str:
    if type(error) not in _DBAPI_WRAPPERS:
        return "UNKNOWN"
    original = vars(error).get("orig")
    if type(original) not in _ASYNCPG_ERRORS:
        return "UNKNOWN"
    value = vars(original).get("sqlstate")
    if type(value) is str and _SQLSTATE.fullmatch(value) is not None:
        return value
    return "UNKNOWN"


def _correlation_uuid(request_id: str) -> UUID:
    """Only canonical UUIDs can enter the private diagnostic correlation field."""
    try:
        identifier = UUID(request_id)
    except ValueError:
        return uuid4()
    return identifier if str(identifier) == request_id else uuid4()


def log_request_failure(
    error: exc.SQLAlchemyError | ResponseValidationError, request_id: str
) -> None:
    """Log a finite event without error/SQL/params/validation-body rendering.

    Called before the request context resets. Native structlog fields survive the
    central JSON formatter (which renames event to message). A concrete UUID
    avoids free-text phone redaction corrupting the private correlation value.
    Unknown exception subclasses are classified by actual type only, with no
    property discovery, repr, str, exception chaining or traceback traversal.
    """
    category = "response_validation"
    kind = "response_validation"
    sqlstate = "UNKNOWN"
    if issubclass(type(error), exc.SQLAlchemyError):
        category = "database"
        kind = "database"
        for error_type, token in _DATABASE_KINDS:
            if issubclass(type(error), error_type):
                kind = token
                break
        sqlstate = _sqlstate(error)
    get_logger(__name__).error(
        "request_failure_diagnostic",
        exc_info=False,
        stack_info=False,
        diagnostic_request_id=_correlation_uuid(request_id),
        diagnostic_category=category,
        diagnostic_kind=kind,
        diagnostic_sqlstate=sqlstate,
    )
