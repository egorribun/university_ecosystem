from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.models import User, WebAuthnCredential
from app.services.webauthn import WebAuthnService


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def service(mock_db):
    return WebAuthnService(mock_db)


@pytest.fixture
def user():
    from app.models.users import UserProfile

    return User(
        id=uuid4(),
        email="test@example.com",
        webauthn_id=None,
        profile=UserProfile(full_name="Test User"),
    )


@pytest.mark.asyncio
async def test_get_registration_options_new_user(service, mock_db, user):
    # Mock database result for exclude_credentials
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_db.execute.return_value = mock_result

    with (
        patch("app.services.webauthn.generate_registration_options"),
        patch("app.services.webauthn.options_to_json", return_value='{"foo": "bar"}'),
    ):
        options = await service.get_registration_options(user)

        assert user.webauthn_id is not None
        mock_db.flush.assert_called()
        assert options == {"foo": "bar"}


@pytest.mark.asyncio
async def test_verify_registration(service, mock_db, user):
    mock_verify = MagicMock()
    mock_verify.credential_id = b"cred123"
    mock_verify.credential_public_key = b"pubkey123"
    mock_verify.sign_count = 0
    mock_verify.credential_device_type = "single_device"
    mock_verify.credential_backed_up = False

    with patch(
        "app.services.webauthn.verify_registration_response", return_value=mock_verify
    ):
        credential = await service.verify_registration(
            user=user,
            challenge="challenge_token",
            response={"id": "id123", "response": {}},
        )

        assert credential.user_id == user.id
        # cred123 -> Y3JlZDEyMw== -> Y3JlZDEyMw
        assert credential.credential_id == "Y3JlZDEyMw"
        mock_db.add.assert_called_with(credential)
        mock_db.flush.assert_called()


@pytest.mark.asyncio
async def test_get_authentication_options(service, mock_db, user):
    mock_result = MagicMock()
    mock_result.all.return_value = [("Y3JlZDEyMw",)]
    mock_db.execute.return_value = mock_result

    with (
        patch("app.services.webauthn.generate_authentication_options") as mock_gen,
        patch(
            "app.services.webauthn.options_to_json", return_value='{"auth": "options"}'
        ),
    ):
        options = await service.get_authentication_options(user)
        assert options == {"auth": "options"}
        mock_gen.assert_called()


def test_get_dummy_authentication_options(service):
    with (
        patch("app.services.webauthn.generate_authentication_options"),
        patch(
            "app.services.webauthn.options_to_json", return_value='{"dummy": "options"}'
        ),
    ):
        options = service.get_dummy_authentication_options()
        assert options == {"dummy": "options"}


@pytest.mark.asyncio
async def test_verify_authentication_success(service, mock_db, user):
    db_credential = WebAuthnCredential(
        id=uuid4(),
        user_id=user.id,
        credential_id="Y3JlZDEyMw",
        public_key="cHVia2V5MTIz",  # pubkey123
        sign_count=10,
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = db_credential
    mock_db.execute.return_value = mock_result

    mock_verify = MagicMock()
    mock_verify.new_sign_count = 11

    with patch(
        "app.services.webauthn.verify_authentication_response", return_value=mock_verify
    ):
        res = await service.verify_authentication(
            user=user, challenge="challenge_token", response={"id": "Y3JlZDEyMw"}
        )

        assert res == db_credential
        assert db_credential.sign_count == 11
        mock_db.flush.assert_called()


@pytest.mark.asyncio
async def test_verify_authentication_not_found(service, mock_db, user):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    with pytest.raises(ValueError, match="Credential not found"):
        await service.verify_authentication(user, "challenge", {"id": "wrong"})
