import json
from unittest.mock import MagicMock

import pytest
from fastapi import Request

from app.core.exceptions import (
    AppException,
    InvalidOperationException,
    PermissionDeniedException,
    ResourceNotFoundException,
    app_exception_handler,
)


@pytest.mark.anyio
async def test_app_exceptions_and_handler():
    # 1. Test AppException instantiation
    exc = AppException(
        "Test app exception",
        status_code=400,
        code="test_err",
        payload={"key": "val"},
    )
    assert exc.message == "Test app exception"
    assert exc.status_code == 400
    assert exc.code == "test_err"
    assert exc.payload == {"key": "val"}

    # 2. Test ResourceNotFoundException
    rnf = ResourceNotFoundException("Not found msg", {"detail": "lost"})
    assert rnf.message == "Not found msg"
    assert rnf.status_code == 404
    assert rnf.code == "resource_not_found"
    assert rnf.payload == {"detail": "lost"}

    # 3. Test PermissionDeniedException
    pd = PermissionDeniedException("Denied msg", {"detail": "no access"})
    assert pd.message == "Denied msg"
    assert pd.status_code == 403
    assert pd.code == "permission_denied"
    assert pd.payload == {"detail": "no access"}

    # 4. Test InvalidOperationException
    io = InvalidOperationException("Invalid msg", {"detail": "bad op"})
    assert io.message == "Invalid msg"
    assert io.status_code == 400
    assert io.code == "invalid_operation"
    assert io.payload == {"detail": "bad op"}

    # 5. Test app_exception_handler with AppException
    mock_request = MagicMock(spec=Request)
    response = await app_exception_handler(mock_request, exc)
    assert response.status_code == 400
    data = json.loads(response.body.decode())
    assert data["detail"] == "Test app exception"
    assert data["code"] == "test_err"
    assert data["payload"] == {"key": "val"}
    assert "trace_id" in data

    # 6. Test app_exception_handler with a generic Exception
    generic_exc = ValueError("Generic error")
    response_generic = await app_exception_handler(mock_request, generic_exc)
    assert response_generic.status_code == 500
    data_generic = json.loads(response_generic.body.decode())
    assert data_generic["detail"] == "Internal Server Error"
    assert "trace_id" in data_generic
