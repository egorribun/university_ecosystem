import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException, Request, status

from app.core.exceptions.domain import (
    BusinessRuleViolation,
    EntityAlreadyExists,
    EntityNotFound,
    PermissionDenied,
)
from app.core.exceptions.handlers import (
    _loc_to_pointer,
    asgi_json_problem,
    domain_exception_handler,
    http_exception_handler,
)


def _make_request(path: str = "/") -> Request:
    return Request(
        scope={
            "type": "http",
            "method": "GET",
            "scheme": "http",
            "server": ("testserver", 80),
            "path": path,
            "headers": [],
            "query_string": b"",
        }
    )


def test_loc_to_pointer():
    assert _loc_to_pointer(()) == ""
    assert _loc_to_pointer(("body", "user", "email")) == "/body/user/email"
    assert _loc_to_pointer(("path/to~something",)) == "/path~1to~0something"
    assert _loc_to_pointer((123,)) == "/123"


@pytest.mark.asyncio
async def test_asgi_json_problem_detail_text():
    send = AsyncMock()
    await asgi_json_problem(
        send,
        status_code=400,
        title_key="titles.bad_request",
        detail_text="Explicit detail",
        headers={"X-Test": "1"},
    )
    assert send.call_count == 2
    start_call = send.call_args_list[0][0][0]
    assert start_call["type"] == "http.response.start"
    assert start_call["status"] == 400
    headers = {name.lower(): value for name, value in start_call["headers"]}
    assert headers[b"x-test"] == b"1"

    body_call = send.call_args_list[1][0][0]
    body = json.loads(body_call["body"].decode("utf-8"))
    assert body["detail"] == "Explicit detail"


@pytest.mark.asyncio
async def test_asgi_json_problem_detail_key(monkeypatch):
    monkeypatch.setattr(
        "app.core.exceptions.handlers.translate",
        lambda k, locale, **kwargs: f"tr_{k}_{kwargs.get('foo', '')}",
    )
    send = AsyncMock()
    await asgi_json_problem(
        send,
        status_code=404,
        title_key="titles.not_found",
        detail_key="errors.not_found",
        foo="bar",
    )
    body_call = send.call_args_list[1][0][0]
    body = json.loads(body_call["body"].decode("utf-8"))
    assert body["detail"] == "tr_errors.not_found_bar"


@pytest.mark.asyncio
async def test_asgi_json_problem_no_detail():
    send = AsyncMock()
    with patch(
        "app.core.exceptions.handlers.translate", return_value="Translated Title"
    ):
        await asgi_json_problem(
            send,
            status_code=500,
            title_key="titles.internal_server_error",
        )
    body_call = send.call_args_list[1][0][0]
    body = json.loads(body_call["body"].decode("utf-8"))
    assert body["detail"] == "Translated Title"


@pytest.mark.parametrize(
    "exception_cls, kwargs, expected_status, expected_type",
    [
        (
            EntityNotFound,
            {"entity_name": "User", "identifier": "1"},
            status.HTTP_404_NOT_FOUND,
            "https://api.university.edu/probs/not-found",
        ),
        (
            EntityAlreadyExists,
            {"entity_name": "User", "identifier": "1"},
            status.HTTP_409_CONFLICT,
            "https://api.university.edu/probs/conflict",
        ),
        (
            PermissionDenied,
            {},
            status.HTTP_403_FORBIDDEN,
            "https://api.university.edu/probs/forbidden",
        ),
        (
            BusinessRuleViolation,
            {"message": "Invalid rule"},
            status.HTTP_400_BAD_REQUEST,
            "https://api.university.edu/probs/business-rule",
        ),
    ],
)
@pytest.mark.asyncio
async def test_domain_exception_handler(
    monkeypatch, exception_cls, kwargs, expected_status, expected_type
):
    monkeypatch.setattr(
        "app.core.exceptions.handlers.resolve_locale", lambda **kwargs: "en"
    )
    monkeypatch.setattr(
        "app.core.exceptions.handlers.translate", lambda k, locale, **kw: f"tr_{k}"
    )
    monkeypatch.setattr("app.core.exceptions.handlers.get_trace_id", lambda: "trace123")

    request = _make_request()
    exc = (
        exception_cls(**kwargs)
        if kwargs and exception_cls is not PermissionDenied
        else exception_cls()
    )

    response = await domain_exception_handler(request, exc)
    assert response.status_code == expected_status
    body = json.loads(response.body.decode("utf-8"))
    assert body["type"] == expected_type
    assert body["trace_id"] == "trace123"


@pytest.mark.asyncio
async def test_domain_exception_handler_fallback(monkeypatch):
    # Test fallback if it's a generic Exception or some other domain exception not explicitly handled
    monkeypatch.setattr(
        "app.core.exceptions.handlers.resolve_locale", lambda **kwargs: "en"
    )
    monkeypatch.setattr(
        "app.core.exceptions.handlers.translate", lambda k, locale, **kw: f"tr_{k}"
    )

    class CustomDomainException(Exception):
        pass

    request = _make_request()
    response = await domain_exception_handler(
        request, CustomDomainException("some error")
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    body = json.loads(response.body.decode("utf-8"))
    assert body["detail"] == "some error"
    assert body["type"] == "about:blank"


@pytest.mark.parametrize(
    "status_code, expected_title_key",
    [
        (status.HTTP_400_BAD_REQUEST, "titles.bad_request"),
        (status.HTTP_401_UNAUTHORIZED, "titles.unauthorized"),
        (status.HTTP_403_FORBIDDEN, "titles.forbidden"),
        (status.HTTP_404_NOT_FOUND, "titles.not_found"),
        (status.HTTP_405_METHOD_NOT_ALLOWED, "titles.method_not_allowed"),
        (status.HTTP_409_CONFLICT, "titles.conflict"),
        (status.HTTP_422_UNPROCESSABLE_CONTENT, "titles.validation_error"),
        (status.HTTP_429_TOO_MANY_REQUESTS, "titles.rate_limit_exceeded"),
        (status.HTTP_500_INTERNAL_SERVER_ERROR, "titles.internal_server_error"),
        (status.HTTP_418_IM_A_TEAPOT, "titles.http_error"),
    ],
)
@pytest.mark.asyncio
async def test_http_exception_handler(monkeypatch, status_code, expected_title_key):
    monkeypatch.setattr(
        "app.core.exceptions.handlers.resolve_locale", lambda **kwargs: "en"
    )
    monkeypatch.setattr(
        "app.core.exceptions.handlers.translate", lambda k, locale: f"tr_{k}"
    )

    request = _make_request()
    exc = HTTPException(
        status_code=status_code, detail="some detail", headers={"X-A": "B"}
    )

    response = await http_exception_handler(request, exc)
    assert response.status_code == status_code
    body = json.loads(response.body.decode("utf-8"))
    assert body["title"] == f"tr_{expected_title_key}"
    assert body["detail"] == "some detail"
    assert "x-a" in response.headers
    assert response.headers["x-a"] == "B"
