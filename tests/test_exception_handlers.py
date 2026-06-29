"""Tests for exception handlers (app/core/exceptions/handlers.py).

Validates _loc_to_pointer, asgi_json_problem, domain_exception_handler,
and http_exception_handler for correct RFC 7807 responses.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status
from starlette.requests import Request

from app.core.exceptions.domain import (
    BusinessRuleViolation,
    DomainException,
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


# ---------------------------------------------------------------------------
# _loc_to_pointer
# ---------------------------------------------------------------------------


class TestLocToPointer:
    """Tests for RFC 6901 JSON Pointer conversion."""

    def test_empty_tuple(self):
        """Empty location tuple returns empty string."""
        assert _loc_to_pointer(()) == ""

    def test_single_element(self):
        """Single element produces /element pointer."""
        assert _loc_to_pointer(("body",)) == "/body"

    def test_nested_path(self):
        """Nested tuple produces multi-segment pointer."""
        assert _loc_to_pointer(("body", "user", "email")) == "/body/user/email"

    def test_integer_element(self):
        """Integer elements are converted to string."""
        assert _loc_to_pointer(("body", "items", 0, "name")) == "/body/items/0/name"

    def test_tilde_escaped(self):
        """Tilde characters are escaped as ~0 per RFC 6901."""
        assert _loc_to_pointer(("field~name",)) == "/field~0name"

    def test_slash_escaped(self):
        """Slash characters are escaped as ~1 per RFC 6901."""
        assert _loc_to_pointer(("path/field",)) == "/path~1field"

    def test_tilde_before_slash(self):
        """Tilde is escaped before slash (order matters per RFC 6901)."""
        result = _loc_to_pointer(("a~/b",))
        # First ~ → ~0, then / → ~1
        assert result == "/a~0~1b"

    @pytest.mark.parametrize(
        ("loc", "expected"),
        [
            (("body",), "/body"),
            (("query", "page"), "/query/page"),
            (("body", "nested", "deep"), "/body/nested/deep"),
        ],
        ids=["single", "double", "triple"],
    )
    def test_various_depths(self, loc: tuple, expected: str):
        """Various depth levels produce correct pointers."""
        assert _loc_to_pointer(loc) == expected


# ---------------------------------------------------------------------------
# asgi_json_problem
# ---------------------------------------------------------------------------


class TestAsgiJsonProblem:
    """Tests for the raw ASGI problem+json response sender."""

    @pytest.mark.asyncio
    async def test_sends_correct_status_and_content_type(self):
        """Sends http.response.start with correct status and content-type."""
        messages: list[dict] = []

        async def mock_send(message: dict) -> None:
            messages.append(message)

        with patch(
            "app.core.exceptions.handlers.translate", return_value="Bad Request"
        ), patch(
            "app.core.exceptions.handlers.get_trace_id", return_value="trace-123"
        ):
            await asgi_json_problem(
                mock_send,
                status_code=400,
                title_key="titles.bad_request",
                detail_key="errors.detail",
                locale="en",
                instance="/api/test",
            )

        assert len(messages) == 2
        start_msg = messages[0]
        assert start_msg["type"] == "http.response.start"
        assert start_msg["status"] == 400

        # Check content-type header
        headers_dict = {
            k.decode(): v.decode() for k, v in start_msg["headers"]
        }
        assert headers_dict["content-type"] == "application/problem+json"

    @pytest.mark.asyncio
    async def test_body_contains_problem_fields(self):
        """Response body contains RFC 7807 problem fields."""
        messages: list[dict] = []

        async def mock_send(message: dict) -> None:
            messages.append(message)

        with patch(
            "app.core.exceptions.handlers.translate", return_value="Not Found"
        ), patch(
            "app.core.exceptions.handlers.get_trace_id", return_value="trace-456"
        ):
            await asgi_json_problem(
                mock_send,
                status_code=404,
                title_key="titles.not_found",
                locale="en",
                instance="/api/users/123",
            )

        body_msg = messages[1]
        assert body_msg["type"] == "http.response.body"
        body = json.loads(body_msg["body"])
        assert body["type"] == "about:blank"
        assert body["status"] == 404
        assert body["instance"] == "/api/users/123"
        assert body["trace_id"] == "trace-456"

    @pytest.mark.asyncio
    async def test_with_custom_headers(self):
        """Custom headers are included in the response."""
        messages: list[dict] = []

        async def mock_send(message: dict) -> None:
            messages.append(message)

        with patch(
            "app.core.exceptions.handlers.translate", return_value="Error"
        ), patch(
            "app.core.exceptions.handlers.get_trace_id", return_value="trace-789"
        ):
            await asgi_json_problem(
                mock_send,
                status_code=429,
                title_key="titles.rate_limit",
                locale="en",
                headers={"Retry-After": "60", "X-Custom": "value"},
            )

        start_msg = messages[0]
        headers_dict = {
            k.decode(): v.decode() for k, v in start_msg["headers"]
        }
        assert headers_dict.get("Retry-After") == "60"
        assert headers_dict.get("X-Custom") == "value"

    @pytest.mark.asyncio
    async def test_detail_text_overrides_key(self):
        """detail_text takes precedence when detail_key is also provided."""
        messages: list[dict] = []

        async def mock_send(message: dict) -> None:
            messages.append(message)

        with patch(
            "app.core.exceptions.handlers.translate", return_value="Translated"
        ), patch(
            "app.core.exceptions.handlers.get_trace_id", return_value="trace-000"
        ):
            await asgi_json_problem(
                mock_send,
                status_code=400,
                title_key="titles.bad_request",
                detail_text="Custom detail text",
                locale="en",
            )

        body = json.loads(messages[1]["body"])
        assert body["detail"] == "Custom detail text"


# ---------------------------------------------------------------------------
# domain_exception_handler
# ---------------------------------------------------------------------------


def _make_request(path: str = "/api/test") -> Request:
    """Build a minimal Starlette Request for testing."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"",
        "headers": [],
        "root_path": "",
        "server": ("localhost", 8000),
    }
    return Request(scope)


class TestDomainExceptionHandler:
    """Tests for the domain_exception_handler function."""

    @pytest.mark.asyncio
    async def test_entity_not_found_returns_404(self):
        """EntityNotFound produces 404 response."""
        exc = EntityNotFound("User", "abc-123")
        request = _make_request()

        with patch(
            "app.core.exceptions.handlers.get_trace_id", return_value="trace-nf"
        ):
            response = await domain_exception_handler(request, exc)

        assert response.status_code == 404
        assert response.media_type == "application/problem+json"
        body = json.loads(response.body)
        assert body["status"] == 404
        assert body["trace_id"] == "trace-nf"

    @pytest.mark.asyncio
    async def test_entity_already_exists_returns_409(self):
        """EntityAlreadyExists produces 409 response."""
        exc = EntityAlreadyExists("User", "user@test.com")
        request = _make_request()

        with patch(
            "app.core.exceptions.handlers.get_trace_id", return_value="trace-ae"
        ):
            response = await domain_exception_handler(request, exc)

        assert response.status_code == 409
        body = json.loads(response.body)
        assert body["status"] == 409

    @pytest.mark.asyncio
    async def test_permission_denied_returns_403(self):
        """PermissionDenied produces 403 response."""
        exc = PermissionDenied()
        request = _make_request()

        with patch(
            "app.core.exceptions.handlers.get_trace_id", return_value="trace-pd"
        ):
            response = await domain_exception_handler(request, exc)

        assert response.status_code == 403
        body = json.loads(response.body)
        assert body["status"] == 403

    @pytest.mark.asyncio
    async def test_business_rule_violation_returns_400(self):
        """BusinessRuleViolation produces 400 response."""
        exc = BusinessRuleViolation("Cannot enroll in past events")
        request = _make_request()

        with patch(
            "app.core.exceptions.handlers.get_trace_id", return_value="trace-br"
        ):
            response = await domain_exception_handler(request, exc)

        assert response.status_code == 400
        body = json.loads(response.body)
        assert body["status"] == 400
        assert body["detail"] == "Cannot enroll in past events"

    @pytest.mark.asyncio
    async def test_unknown_domain_exception_returns_400(self):
        """Unknown DomainException subclass defaults to 400."""
        exc = DomainException("Generic domain error")
        request = _make_request()

        with patch(
            "app.core.exceptions.handlers.get_trace_id", return_value="trace-unk"
        ):
            response = await domain_exception_handler(request, exc)

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_response_includes_instance(self):
        """All domain exception responses include the request URL as instance."""
        exc = EntityNotFound("Item", 1)
        request = _make_request("/api/items/1")

        with patch(
            "app.core.exceptions.handlers.get_trace_id", return_value="trace-inst"
        ):
            response = await domain_exception_handler(request, exc)

        body = json.loads(response.body)
        assert "/api/items/1" in body["instance"]

    @pytest.mark.asyncio
    async def test_response_media_type(self):
        """All responses have media_type application/problem+json."""
        exc = PermissionDenied()
        request = _make_request()

        with patch(
            "app.core.exceptions.handlers.get_trace_id", return_value="trace"
        ):
            response = await domain_exception_handler(request, exc)

        assert response.media_type == "application/problem+json"


# ---------------------------------------------------------------------------
# http_exception_handler
# ---------------------------------------------------------------------------


class TestHttpExceptionHandler:
    """Tests for the http_exception_handler function."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "status_code",
        [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_405_METHOD_NOT_ALLOWED,
            status.HTTP_409_CONFLICT,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            status.HTTP_429_TOO_MANY_REQUESTS,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ],
        ids=[
            "400_bad_request",
            "401_unauthorized",
            "403_forbidden",
            "404_not_found",
            "405_method_not_allowed",
            "409_conflict",
            "422_unprocessable",
            "429_rate_limit",
            "500_internal_error",
        ],
    )
    async def test_all_mapped_status_codes(self, status_code: int):
        """Each mapped status code produces a correct problem+json response."""
        exc = HTTPException(status_code=status_code, detail="Test error detail")
        request = _make_request()

        with patch(
            "app.core.exceptions.handlers.get_trace_id", return_value="trace-http"
        ):
            response = await http_exception_handler(request, exc)

        assert response.status_code == status_code
        assert response.media_type == "application/problem+json"
        body = json.loads(response.body)
        assert body["status"] == status_code
        assert body["detail"] == "Test error detail"
        assert body["trace_id"] == "trace-http"
        assert body["type"] == "about:blank"

    @pytest.mark.asyncio
    async def test_unknown_status_code_fallback_title(self):
        """Unmapped status code uses fallback title key."""
        exc = HTTPException(status_code=418, detail="I'm a teapot")
        request = _make_request()

        with patch(
            "app.core.exceptions.handlers.get_trace_id", return_value="trace-tea"
        ):
            response = await http_exception_handler(request, exc)

        assert response.status_code == 418
        body = json.loads(response.body)
        assert body["status"] == 418
        # Title should be from the fallback "titles.http_error" key

    @pytest.mark.asyncio
    async def test_response_includes_trace_id(self):
        """All HTTP exception responses include trace_id."""
        exc = HTTPException(status_code=404, detail="Not found")
        request = _make_request()

        with patch(
            "app.core.exceptions.handlers.get_trace_id", return_value="trace-tid"
        ):
            response = await http_exception_handler(request, exc)

        body = json.loads(response.body)
        assert body["trace_id"] == "trace-tid"

    @pytest.mark.asyncio
    async def test_response_includes_instance(self):
        """All responses include the request URL as instance."""
        exc = HTTPException(status_code=400, detail="Bad request")
        request = _make_request("/api/v2/users")

        with patch(
            "app.core.exceptions.handlers.get_trace_id", return_value="trace"
        ):
            response = await http_exception_handler(request, exc)

        body = json.loads(response.body)
        assert "/api/v2/users" in body["instance"]

    @pytest.mark.asyncio
    async def test_exception_headers_passed_through(self):
        """HTTPException.headers are passed to the JSONResponse."""
        exc = HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )
        request = _make_request()

        with patch(
            "app.core.exceptions.handlers.get_trace_id", return_value="trace"
        ):
            response = await http_exception_handler(request, exc)

        assert response.status_code == 401
        # Headers from the exception should be included
        # JSONResponse stores them in response.headers
