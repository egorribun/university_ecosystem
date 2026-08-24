import secrets
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ActiveSession, User
from app.services.session_cleanup import revoke_sessions_matching


@pytest.mark.asyncio
async def test_revoke_sessions_matching_calls_backend(db_session: AsyncSession):
    # 1. Create a dummy user and session
    db = db_session
    user = User(
        email=f"test_revoke_{secrets.token_hex(4)}@example.com",
        hashed_password="hash",
        role="student",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    jti = secrets.token_urlsafe(16)
    session = ActiveSession(
        user_id=user.id,
        jti=jti,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        signing_key=secrets.token_urlsafe(32),
    )
    db.add(session)
    await db.commit()

    # 2. Mock the session backend
    mock_backend = AsyncMock()
    expected_expires_at = session.expires_at

    with patch(
        "app.services.session_cleanup.get_session_backend", return_value=mock_backend
    ):
        # 3. Call revoke_sessions_matching
        revoked_count = await revoke_sessions_matching(
            db=db, whereclause=(ActiveSession.id == session.id)
        )
        await db.commit()

    # 4. Verify results
    assert revoked_count == 1

    # Reload session from DB
    await db.refresh(session)
    assert session.revoked_at is not None

    # Verify backend was called with correct JTI
    mock_backend.revoke_session.assert_called_once_with(
        jti, expires_at=expected_expires_at
    )
