"""Finite diagnostics retain correlation, not exception data or HTTP control."""

from __future__ import annotations

import asyncio
import io
import json
import logging
from uuid import UUID, uuid4

import pytest
import structlog
from fastapi.exceptions import ResponseValidationError
from sqlalchemy import exc
from sqlalchemy.dialects.postgresql.asyncpg import AsyncAdapt_asyncpg_dbapi

import app.core.logging as logging_mod
from app.core.middleware.request_id import RequestIDMiddleware, request_id_ctx
from app.core.request_failure_diagnostic import log_request_failure

pytestmark = pytest.mark.usefixtures("preserve_logging_configuration")


@pytest.fixture(params=[True, False], ids=["json", "console"])
def diagnostic_stream(monkeypatch, request):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    monkeypatch.setattr(logging.getLogger(), "handlers", [handler])
    monkeypatch.setattr(logging.getLogger(), "level", logging.INFO)
    monkeypatch.setattr(
        logging.getLogger("app.core.request_failure_diagnostic"),
        "level",
        logging.NOTSET,
    )
    monkeypatch.setattr(logging_mod, "_configured", False)
    logging_mod.configure_logging(json_output=request.param)
    return stream


def _record(stream):
    lines = stream.getvalue().splitlines()
    assert len(lines) == 1
    result = json.loads(lines[0])
    assert result["message"] == "request_failure_diagnostic"
    assert result["logger"] == "app.core.request_failure_diagnostic"
    assert "exception" not in result
    assert "exc_info" not in result
    return result


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (exc.MissingGreenlet(), "missing_greenlet"),
        (exc.IntegrityError(None, None, Exception()), "integrity"),
        (exc.OperationalError(None, None, Exception()), "operational"),
        (exc.ProgrammingError(None, None, Exception()), "programming"),
        (exc.NoResultFound(), "no_result"),
        (exc.MultipleResultsFound(), "multiple_results"),
        (exc.InvalidRequestError(), "invalid_request"),
        (exc.StatementError("", None, None, Exception()), "statement"),
        (exc.SQLAlchemyError(), "database"),
    ],
)
def test_real_formatter_preserves_closed_database_kinds(diagnostic_stream, error, kind):
    identifier = uuid4()
    log_request_failure(error, str(identifier))
    record = _record(diagnostic_stream)
    assert record["diagnostic_request_id"] == str(identifier)
    assert record["diagnostic_category"] == "database"
    assert record["diagnostic_kind"] == kind
    assert record["diagnostic_sqlstate"] == "UNKNOWN"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("42501", "42501"),
        ("23505", "23505"),
        ("42P01", "42P01"),
        ("42p01", "UNKNOWN"),
        ("42501\n", "UNKNOWN"),
        ("425010", "UNKNOWN"),
        ("４２５０１", "UNKNOWN"),
        ("", "UNKNOWN"),
        (None, "UNKNOWN"),
        (12345, "UNKNOWN"),
    ],
)
def test_sqlstate_only_accepts_exact_driver_native_five_character_values(
    diagnostic_stream, value, expected
):
    original = AsyncAdapt_asyncpg_dbapi.ProgrammingError("private SQL")
    vars(original)["sqlstate"] = value
    error = exc.ProgrammingError("private statement", {"private": "params"}, original)
    log_request_failure(error, str(uuid4()))
    assert _record(diagnostic_stream)["diagnostic_sqlstate"] == expected
    assert "private" not in diagnostic_stream.getvalue()


class Hostile:
    @property
    def __class__(self):
        raise AssertionError("must not probe apparent class")

    @property
    def sqlstate(self):
        raise AssertionError("must not probe untrusted SQLSTATE")

    def __str__(self):
        raise AssertionError("must not stringify")

    def __repr__(self):
        raise AssertionError("must not represent")


class HostileDatabaseError(exc.SQLAlchemyError):
    @property
    def __dict__(self):
        raise AssertionError("must not inspect unknown exception storage")

    @property
    def orig(self):
        raise AssertionError("must not inspect unknown exception original")

    def __str__(self):
        raise AssertionError("must not stringify exception")

    def __repr__(self):
        raise AssertionError("must not represent exception")


def test_unknown_orig_is_never_probed_or_rendered(diagnostic_stream):
    error = exc.OperationalError(None, None, Exception())
    vars(error)["orig"] = Hostile()
    log_request_failure(error, str(uuid4()))
    assert _record(diagnostic_stream)["diagnostic_sqlstate"] == "UNKNOWN"


def test_unknown_sqlalchemy_subclass_is_never_probed(diagnostic_stream):
    log_request_failure(HostileDatabaseError(), str(uuid4()))
    record = _record(diagnostic_stream)
    assert record["diagnostic_kind"] == "database"
    assert record["diagnostic_sqlstate"] == "UNKNOWN"


def test_unknown_sqlstate_value_is_never_coerced(diagnostic_stream):
    original = AsyncAdapt_asyncpg_dbapi.Error()
    vars(original)["sqlstate"] = Hostile()
    error = exc.DBAPIError(None, None, Exception())
    vars(error)["orig"] = original
    log_request_failure(error, str(uuid4()))
    assert _record(diagnostic_stream)["diagnostic_sqlstate"] == "UNKNOWN"


def test_driver_subclasses_with_properties_are_not_inspected(diagnostic_stream):
    class DerivedDriver(AsyncAdapt_asyncpg_dbapi.Error):
        @property
        def __dict__(self):
            raise AssertionError("must not inspect driver subclass")

    error = exc.DBAPIError(None, None, Exception())
    vars(error)["orig"] = DerivedDriver()
    log_request_failure(error, str(uuid4()))
    assert _record(diagnostic_stream)["diagnostic_sqlstate"] == "UNKNOWN"


@pytest.mark.parametrize(
    "request_id", ["not-a-uuid", "", str(UUID(int=1)).upper().replace("-", "")]
)
def test_noncanonical_correlation_is_replaced_not_logged(diagnostic_stream, request_id):
    log_request_failure(exc.SQLAlchemyError(), request_id)
    value = _record(diagnostic_stream)["diagnostic_request_id"]
    assert value == str(UUID(value))
    assert value != request_id


def test_numeric_uuid_is_not_mistaken_for_phone_text(diagnostic_stream):
    identifier = UUID(int=123456789)
    log_request_failure(exc.SQLAlchemyError(), str(identifier))
    assert _record(diagnostic_stream)["diagnostic_request_id"] == str(identifier)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        HostileDatabaseError(),
        ResponseValidationError(
            [{"type": "private", "input": Hostile()}],
            body={"private": Hostile()},
        ),
    ],
)
async def test_middleware_logs_before_context_reset_and_reraises_identity(
    diagnostic_stream, error, monkeypatch
):
    identifier = str(uuid4())

    def emit_while_context_is_alive(exception, request_id):
        assert request_id_ctx.get() == identifier
        log_request_failure(exception, request_id)

    monkeypatch.setattr(
        "app.core.middleware.request_id.log_request_failure",
        emit_while_context_is_alive,
    )
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/private",
        "query_string": b"private=value",
        "headers": [(b"x-request-id", identifier.encode("ascii"))],
    }
    sent = []

    async def receive():
        raise AssertionError("diagnostic must not read body")

    async def send(message):
        sent.append(message)

    async def inner(scope, receive, send):
        assert request_id_ctx.get() == identifier
        raise error

    before = request_id_ctx.get()
    with pytest.raises(type(error)) as caught:
        await RequestIDMiddleware(inner)(scope, receive, send)
    assert caught.value is error
    assert request_id_ctx.get() == before
    assert sent == []
    record = _record(diagnostic_stream)
    assert record["diagnostic_request_id"] == identifier
    assert "request_id" not in record
    if type(error) is ResponseValidationError:
        assert record["diagnostic_category"] == "response_validation"
        assert record["diagnostic_kind"] == "response_validation"
        assert record["diagnostic_sqlstate"] == "UNKNOWN"
    assert "private" not in diagnostic_stream.getvalue()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        asyncio.CancelledError(),
        RuntimeError("private"),
        ExceptionGroup("private", [exc.SQLAlchemyError()]),
    ],
)
async def test_middleware_does_not_catch_cancellation_unknown_or_grouped_errors(
    diagnostic_stream, error
):
    async def inner(scope, receive, send):
        raise error

    before = request_id_ctx.get()
    with pytest.raises(type(error)) as caught:
        await RequestIDMiddleware(inner)({"type": "http", "headers": []}, None, None)
    assert caught.value is error
    assert request_id_ctx.get() == before
    assert diagnostic_stream.getvalue() == ""


def test_sqlstate_string_subclasses_are_not_inspected(diagnostic_stream):
    class HostileString(str):
        def __str__(self):
            raise AssertionError("must not stringify subclass")

    original = AsyncAdapt_asyncpg_dbapi.Error()
    vars(original)["sqlstate"] = HostileString("42501")
    error = exc.DBAPIError(None, None, Exception())
    vars(error)["orig"] = original
    log_request_failure(error, str(uuid4()))
    assert _record(diagnostic_stream)["diagnostic_sqlstate"] == "UNKNOWN"


def test_inherited_context_is_not_rendered(diagnostic_stream):
    with structlog.contextvars.bound_contextvars(
        uri="private-uri",
        body=Hostile(),
        headers={"Authorization": "private-header"},
        user_id="private-user",
        exc_info=HostileDatabaseError(),
        stack_info=True,
    ):
        log_request_failure(exc.SQLAlchemyError(), str(uuid4()))
    record = _record(diagnostic_stream)
    assert set(record) == {
        "message",
        "logger",
        "diagnostic_request_id",
        "diagnostic_category",
        "diagnostic_kind",
        "diagnostic_sqlstate",
    }
    assert "private" not in diagnostic_stream.getvalue()


@pytest.mark.parametrize(
    ("logger_name", "event"),
    [
        ("app.other", "request_failure_diagnostic"),
        ("app.core.request_failure_diagnostic", "another_event"),
    ],
)
def test_other_logger_or_event_keeps_default_rendering(
    diagnostic_stream, logger_name, event
):
    logging_mod.get_logger(logger_name).error(event, ordinary_field="kept")
    assert "ordinary_field" in diagnostic_stream.getvalue()
    assert "kept" in diagnostic_stream.getvalue()


def test_diagnostic_renderer_drops_unknown_fields_even_for_incomplete_event(
    diagnostic_stream,
):
    logging_mod.get_logger("app.core.request_failure_diagnostic").error(
        "request_failure_diagnostic", unknown_field="private-data"
    )
    assert _record(diagnostic_stream) == {
        "message": "request_failure_diagnostic",
        "logger": "app.core.request_failure_diagnostic",
    }


@pytest.mark.asyncio
async def test_request_id_whitelist_accepts_exactly_public_ascii_alphabet():
    from app.core.middleware.request_id import _REQUEST_ID_SAFE_CHARS

    allowed_codes = set(range(48, 58)) | set(range(65, 91)) | set(range(97, 123))
    allowed_codes.update((45, 95))
    expected = "".join(chr(code) for code in sorted(allowed_codes))
    assert _REQUEST_ID_SAFE_CHARS == frozenset(expected)
    assert len(_REQUEST_ID_SAFE_CHARS) == 64
    sent = []
    scope = {"type": "http", "headers": [(b"x-request-id", bytes(range(256)))]}

    async def send(message):
        sent.append(message)

    async def inner(scope, receive, send):
        assert request_id_ctx.get() == expected
        await send({"type": "http.response.start", "status": 204, "headers": []})

    before = request_id_ctx.get()
    await RequestIDMiddleware(inner)(scope, None, send)
    assert scope["state"]["request_id"] == expected
    assert sent[0]["status"] == 204
    assert sent[0]["headers"] == [(b"x-request-id", expected.encode("ascii"))]
    assert request_id_ctx.get() == before


def test_optional_context_clear_binding_keeps_public_callable():
    from app.core.middleware.request_id import clear_contextvars

    assert clear_contextvars is structlog.contextvars.clear_contextvars
