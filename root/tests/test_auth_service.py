"""
Tests for auth_service module.

Covers helper functions and AuthService methods.
"""

import hashlib
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import models
from app.services.auth_service import (
    _hash_token,
    _prepare_password_reset_token,
    _create_email_change_request,
    _get_active_email_change_request,
    attach_pending_email,
    AuthService,
)
from app.services.audit_service import AuditService


class TestHashToken:
    """Tests for _hash_token helper."""

    def test_returns_sha256_hex(self):
        """Should return SHA256 hash of token."""
        token = "test-token"
        expected = hashlib.sha256(token.encode()).hexdigest()
        assert _hash_token(token) == expected

    def test_different_tokens_produce_different_hashes(self):
        """Different tokens should produce different hashes."""
        hash1 = _hash_token("token1")
        hash2 = _hash_token("token2")
        assert hash1 != hash2

    def test_same_token_produces_same_hash(self):
        """Same token should always produce same hash."""
        token = "consistent-token"
        assert _hash_token(token) == _hash_token(token)


class TestPreparePasswordResetToken:
    """Tests for _prepare_password_reset_token helper."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock()
        db.add = MagicMock()
        return db

    @pytest.fixture
    def mock_user(self):
        """Create mock user."""
        user = MagicMock(spec=models.User)
        user.id = 1
        return user

    @pytest.mark.asyncio
    async def test_creates_new_token_when_no_existing(self, mock_db, mock_user):
        """Should create new token when none exist."""
        # Mock empty result
        mock_result = MagicMock()
        mock_result.scalars.return_value = []
        mock_db.execute.return_value = mock_result

        token_hash = "test_hash"
        expires_at = datetime.now(UTC) + timedelta(hours=1)

        await _prepare_password_reset_token(
            mock_db,
            mock_user,
            token_hash=token_hash,
            expires_at=expires_at,
        )

        # Should add a new token
        mock_db.add.assert_called_once()


class TestCreateEmailChangeRequest:
    """Tests for _create_email_change_request helper."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        return db

    @pytest.fixture
    def mock_user(self):
        """Create mock user."""
        user = MagicMock(spec=models.User)
        user.id = 1
        return user

    @pytest.mark.asyncio
    async def test_creates_email_change_request(self, mock_db, mock_user):
        """Should create email change request and return token."""
        new_email = "new@example.com"

        record, token = await _create_email_change_request(
            mock_db, mock_user, new_email
        )

        # Should add a record
        mock_db.add.assert_called_once()
        # Should flush
        mock_db.flush.assert_called_once()
        # Token should be non-empty
        assert len(token) > 0


class TestGetActiveEmailChangeRequest:
    """Tests for _get_active_email_change_request helper."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_returns_none_when_no_active_request(self, mock_db):
        """Should return None when no active request exists."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_db.execute.return_value = mock_result

        result = await _get_active_email_change_request(mock_db, user_id=1)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_active_request_when_exists(self, mock_db):
        """Should return active request when one exists."""
        mock_token = MagicMock(spec=models.EmailChangeToken)
        mock_token.new_email = "new@example.com"

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_token
        mock_db.execute.return_value = mock_result

        result = await _get_active_email_change_request(mock_db, user_id=1)
        assert result == mock_token


class TestAttachPendingEmail:
    """Tests for attach_pending_email helper."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_returns_none_for_none_user(self, mock_db):
        """Should return None when user is None."""
        result = await attach_pending_email(mock_db, None)
        assert result is None

    @pytest.mark.asyncio
    async def test_attaches_pending_email_when_exists(self, mock_db):
        """Should attach pending email when request exists."""
        mock_user = MagicMock(spec=models.User)
        mock_user.id = 1

        mock_token = MagicMock(spec=models.EmailChangeToken)
        mock_token.new_email = "pending@example.com"

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_token
        mock_db.execute.return_value = mock_result

        result = await attach_pending_email(mock_db, mock_user)

        assert result == mock_user
        assert mock_user.pending_email == "pending@example.com"

    @pytest.mark.asyncio
    async def test_attaches_none_when_no_pending(self, mock_db):
        """Should attach None when no pending request."""
        mock_user = MagicMock(spec=models.User)
        mock_user.id = 1

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_db.execute.return_value = mock_result

        result = await attach_pending_email(mock_db, mock_user)

        assert result == mock_user
        assert mock_user.pending_email is None


class TestAuthServiceInit:
    """Tests for AuthService initialization."""

    def test_init_stores_audit_service(self):
        """Should store audit service reference."""
        audit = MagicMock(spec=AuditService)
        service = AuthService(audit)
        assert service.audit == audit
