import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import ActiveSession, User
from app.services.auth.graphql_token_validator import GraphQLTokenValidator


@pytest.mark.asyncio
async def test_session_load_failure_keeps_only_safe_diagnostics(
    caplog: pytest.LogCaptureFixture,
) -> None:
    detail = "private-database-diagnostic"
    database = AsyncMock()
    database.execute.side_effect = ConnectionError(detail)
    validator = GraphQLTokenValidator(MagicMock(), database)

    assert await validator._load_db_session("demo-session-marker") is None
    assert detail not in caplog.text
    assert "GraphQL: DB session load failed; denying request" in caplog.text
    assert "ConnectionError" in caplog.text


@pytest.mark.asyncio
async def test_fingerprint_failure_logs_no_session_or_user_identifier(
    caplog: pytest.LogCaptureFixture,
) -> None:
    detail = "private-fingerprint-diagnostic"
    session = MagicMock(
        spec=ActiveSession, fingerprint_hash="hash", jti="demo-session-marker"
    )
    user = MagicMock(spec=User, id=uuid.uuid4())
    validator = GraphQLTokenValidator(MagicMock(), AsyncMock())

    with patch(
        "app.services.auth.fingerprint_service.AuthFingerprintService"
    ) as service:
        service.return_value.validate_fingerprint = AsyncMock(
            side_effect=RuntimeError(detail)
        )
        assert await validator._check_fingerprint(user, session) is False

    assert str(user.id) not in caplog.text
    assert session.jti not in caplog.text
    assert detail not in caplog.text
    assert "GraphQL: fingerprint validation failed; denying request" in caplog.text
    assert "RuntimeError" in caplog.text
