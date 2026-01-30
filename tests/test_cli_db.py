from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from app.cli.db import app

runner = CliRunner()


@pytest.fixture
def mock_db_session():
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None
    return mock_session


@pytest.fixture
def mock_engine():
    mock_conn = AsyncMock()
    mock_conn.__aenter__.return_value = mock_conn
    mock_conn.__aexit__.return_value = None
    mock_eng = MagicMock()
    mock_eng.begin.return_value = mock_conn
    return mock_eng


def test_create_admin_success(mock_db_session, mock_engine):
    """Test creating a new admin user."""
    with (
        patch("app.cli.db.async_session", return_value=mock_db_session),
        patch("app.cli.db.engine", mock_engine),
        patch("app.cli.db.get_password_hash", return_value="hashed_secret"),
    ):
        # Mock query result to return None (user not found)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        result = runner.invoke(
            app, ["create-admin", "--email", "new@admin.com", "--password", "secret"]
        )

        assert result.exit_code == 0
        assert "Created admin user: new@admin.com" in result.stdout
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()


def test_create_admin_existing(mock_db_session, mock_engine):
    """Test updating password for existing admin."""
    with (
        patch("app.cli.db.async_session", return_value=mock_db_session),
        patch("app.cli.db.engine", mock_engine),
        patch("app.cli.db.get_password_hash", return_value="hashed_secret"),
    ):
        # Mock query result to return existing user
        existing_user = MagicMock()
        existing_user.id = 1
        existing_user.email = "existing@admin.com"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_user
        mock_db_session.execute.return_value = mock_result

        result = runner.invoke(
            app,
            ["create-admin", "--email", "existing@admin.com", "--password", "newpass"],
        )

        assert result.exit_code == 0
        assert "Admin user already exists" in result.stdout
        assert "Password reset" in result.stdout
        assert existing_user.hashed_password == "hashed_secret"
        mock_db_session.commit.assert_called_once()


def test_create_invite_success(mock_db_session):
    """Test creating an invite code."""
    with patch("app.cli.db.async_session", return_value=mock_db_session):
        result = runner.invoke(app, ["create-invite", "teacher"])

        assert result.exit_code == 0
        assert "Invite code for teacher:" in result.stdout
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()


def test_create_invite_invalid_role():
    """Test creating invite with invalid role."""
    result = runner.invoke(app, ["create-invite", "superhero"])
    assert result.exit_code == 1
    assert "Error: Only 'teacher' or 'admin' roles are supported." in result.stdout
