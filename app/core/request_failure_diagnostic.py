"""Finite request-failure metadata; never inspect exception messages or payloads."""

from __future__ import annotations

import re

import asyncpg
from fastapi.exceptions import ResponseValidationError
from pydantic import ValidationError as PydanticValidationError
from redis.exceptions import RedisError
from sqlalchemy import exc
from sqlalchemy.dialects.postgresql.asyncpg import AsyncAdapt_asyncpg_dbapi

from app.core.logging import get_logger

_SQLSTATE = re.compile(r"[A-Z0-9]{5}", re.ASCII)
# Ids assigned by RequestIDMiddleware: 1-64 characters from this alphabet.
_REQUEST_ID = re.compile(r"[A-Za-z0-9_-]{1,64}", re.ASCII)
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
# Allowlisted non-database failure classes, matched by actual type. Anything else
# is the closed ("other", "other") classification.
_OTHER_KINDS: tuple[tuple[type[BaseException], str], ...] = (
    (RuntimeError, "runtime_error"),
    (PydanticValidationError, "pydantic_validation"),
    (RedisError, "redis"),
    (asyncpg.PostgresError, "driver"),
    (asyncpg.InterfaceError, "driver"),
)
_UNCLASSIFIED = ("other", "other", "UNKNOWN")
# Reads the members slot of the stdlib group type, so a subclass property cannot
# run while the request failure is being classified.
_GROUP_MEMBERS = BaseExceptionGroup.exceptions


def _sqlstate(error: BaseException) -> str:
    if type(error) not in _DBAPI_WRAPPERS:
        return "UNKNOWN"
    original = vars(error).get("orig")
    if type(original) not in _ASYNCPG_ERRORS:
        return "UNKNOWN"
    value = vars(original).get("sqlstate")
    if type(value) is str and _SQLSTATE.fullmatch(value) is not None:
        return value
    return "UNKNOWN"


def _classify_leaf(error: BaseException) -> tuple[str, str, str] | None:
    """Return the closed classification of one leaf, or None when unmatched."""
    error_type = type(error)
    if issubclass(error_type, exc.SQLAlchemyError):
        kind = "database"
        for database_type, token in _DATABASE_KINDS:
            if issubclass(error_type, database_type):
                kind = token
                break
        return ("database", kind, _sqlstate(error))
    if issubclass(error_type, ResponseValidationError):
        return ("response_validation", "response_validation", "UNKNOWN")
    for other_type, token in _OTHER_KINDS:
        if issubclass(error_type, other_type):
            return ("other", token, "UNKNOWN")
    return None


def _classify(error: BaseException) -> tuple[str, str, str]:
    """Classify an unhandled failure by its first allowlisted leaf, depth first.

    Exception groups are walked through their stdlib members in declaration order.
    Nothing else about an exception is read: no message, repr, chain or traceback.
    """
    pending: list[BaseException] = [error]
    while pending:
        current = pending.pop()
        if issubclass(type(current), BaseExceptionGroup):
            pending.extend(
                reversed(_GROUP_MEMBERS.__get__(current, BaseExceptionGroup))
            )
            continue
        classified = _classify_leaf(current)
        if classified is not None:
            return classified
    return _UNCLASSIFIED


def _diagnostic_request_id(request_id: str) -> str:
    """Return the exact assigned id, or the closed token for anything else."""
    return request_id if _REQUEST_ID.fullmatch(request_id) is not None else "invalid"


def log_request_failure(error: Exception, request_id: str) -> None:
    """Log a finite event without error/SQL/params/validation-body rendering.

    ``request_id`` must be the exact id RequestIDMiddleware assigned to the
    response, so the record joins the response header and the request's logs.
    Any value outside the middleware alphabet is recorded as the closed token
    ``invalid`` rather than echoed.

    Called before the request context resets. Native structlog fields survive the
    central JSON formatter (which renames event to message). Unknown exception
    subclasses are classified by actual type only, with no property discovery,
    repr, str, exception chaining or traceback traversal.
    """
    category, kind, sqlstate = _classify(error)
    get_logger(__name__).error(
        "request_failure_diagnostic",
        exc_info=False,
        stack_info=False,
        diagnostic_request_id=_diagnostic_request_id(request_id),
        diagnostic_category=category,
        diagnostic_kind=kind,
        diagnostic_sqlstate=sqlstate,
    )
