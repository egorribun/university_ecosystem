import json
import uuid
from typing import cast
from unittest.mock import MagicMock

import pytest
from fastapi import status
from sqlalchemy import select

import app.models as models
from app.auth import mfa
from app.auth.security import get_password_hash

# Mock data needed for WebAuthn responses
MOCK_CHALLENGE = "mock_challenge_token_base64"
MOCK_CREDENTIAL_ID = "mock_credential_id"
MOCK_PUBLIC_KEY = "mock_public_key"


@pytest.fixture(autouse=True)
def _set_query_budget(async_client):
    async_client.headers["X-Query-Budget"] = "15"


@pytest.fixture
def mock_webauthn(monkeypatch):
    """Mock the underlying webauthn library functions.

    Each test invocation gets a unique credential ID to prevent
    UniqueViolationError when tests run in shared database context.
    """
    # Generate unique credential ID for this test run
    unique_suffix = uuid.uuid4().hex[:16]
    unique_credential_id = f"mock_credential_id_{unique_suffix}".encode()
    unique_public_key = f"mock_public_key_{unique_suffix}".encode()

    def fake_options_to_json(opts):
        return json.dumps(
            {
                "challenge": MOCK_CHALLENGE,
                "rp": {"name": "Test RP"},
                "user": {
                    "id": "user_id_bytes",
                    "name": "test@example.com",
                    "displayName": "Test User",
                },
                "pubKeyCredParams": [],
                "timeout": 60000,
                "attestation": "none",
            }
        )

    monkeypatch.setattr("app.services.webauthn.options_to_json", fake_options_to_json)

    # 2. verify_registration_response - uses unique credential ID
    mock_reg_verification = MagicMock()
    mock_reg_verification.credential_id = unique_credential_id
    mock_reg_verification.credential_public_key = unique_public_key
    mock_reg_verification.sign_count = 0
    mock_reg_verification.credential_device_type = "single_device"
    mock_reg_verification.credential_backed_up = False

    monkeypatch.setattr(
        "app.services.webauthn.verify_registration_response",
        MagicMock(return_value=mock_reg_verification),
    )

    # 3. generate_authentication_options
    def fake_auth_options_to_json(opts):
        return json.dumps(
            {
                "challenge": MOCK_CHALLENGE,
                "timeout": 60000,
                "allowCredentials": [],
            }
        )

    # Note: options_to_json is already mocked above if it's the same import

    monkeypatch.setattr(
        "app.services.webauthn.generate_authentication_options", MagicMock()
    )

    # 4. verify_authentication_response
    mock_auth_verification = MagicMock()
    mock_auth_verification.new_sign_count = 1

    monkeypatch.setattr(
        "app.services.webauthn.verify_authentication_response",
        MagicMock(return_value=mock_auth_verification),
    )

    # Also need to mock generate_registration_options so it doesn't fail on args
    monkeypatch.setattr(
        "app.services.webauthn.generate_registration_options", MagicMock()
    )


async def _login_for_token(async_client, email: str, password: str) -> str:
    response = await async_client.post(
        "/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == status.HTTP_200_OK
    return cast(str, response.cookies.get("access_token_v2"))


@pytest.mark.asyncio
async def test_webauthn_registration_flow(
    async_client, user_factory, db_session, mock_webauthn
):
    password = "WebAuthnPass123!"
    user = await user_factory(
        email="webauthn-flow@example.com",
        hashed_password=await get_password_hash(password),
    )

    token = await _login_for_token(async_client, user.email, password)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Start Registration
    start_resp = await async_client.post(
        "/auth/mfa/webauthn/register/start", headers=headers
    )
    assert start_resp.status_code == status.HTTP_200_OK
    start_data = start_resp.json()
    assert "publicKey" in start_data
    assert "challenge_token" in start_data
    challenge_token = start_data["challenge_token"]

    # 2. Confirm Registration
    # We send a fake response. Since we mocked verify_registration_response, the
    # content doesn't matter much
    # as long as it matches the schema.
    fake_response = {
        "id": "mock_cred_id_base64",
        "rawId": "mock_cred_id_base64",
        "response": {
            "attestationObject": "mock_attestation",
            "clientDataJSON": "mock_client_data",
            "transports": ["usb"],
        },
        "type": "public-key",
    }

    confirm_resp = await async_client.post(
        "/auth/mfa/webauthn/register/confirm",
        headers=headers,
        json={
            "challenge": challenge_token,
            "response": fake_response,
            "label": "My YubiKey",
        },
    )
    assert confirm_resp.status_code == status.HTTP_200_OK
    status_data = confirm_resp.json()
    assert status_data["disabled"] is False
    assert status_data["mfa_default_method"] == mfa.MFA_METHOD_WEBAUTHN
    assert status_data["mfa_required"] is True

    # 3. Verify it's in the DB
    stmt = select(models.WebAuthnCredential).where(
        models.WebAuthnCredential.user_id == user.id
    )
    result = await db_session.execute(stmt)
    creds = result.scalars().all()
    assert len(creds) == 1
    assert creds[0].label == "My YubiKey"
    assert "usb" in creds[0].transports

    return creds[0]


@pytest.mark.asyncio
async def test_webauthn_authentication_flow(
    async_client, user_factory, db_session, mock_webauthn
):
    # First enroll
    password = "WebAuthnAuth123!"
    user = await user_factory(
        email="webauthn-auth@example.com",
        hashed_password=await get_password_hash(password),
    )
    token = await _login_for_token(async_client, user.email, password)
    headers = {"Authorization": f"Bearer {token}"}

    # Enroll manually or via helper
    start_resp = await async_client.post(
        "/auth/mfa/webauthn/register/start", headers=headers
    )
    challenge_token = start_resp.json()["challenge_token"]

    confirm_resp = await async_client.post(
        "/auth/mfa/webauthn/register/confirm",
        headers=headers,
        json={
            "challenge": challenge_token,
            "response": {"id": "mock_id", "response": {}},
            "label": "Key",
        },
    )
    assert confirm_resp.status_code == status.HTTP_200_OK, (
        f"Registration failed: {confirm_resp.json()}"
    )

    # Fetch the actual credential_id from the database
    stmt = select(models.WebAuthnCredential).where(
        models.WebAuthnCredential.user_id == user.id
    )
    result = await db_session.execute(stmt)
    credential = result.scalars().first()
    assert credential is not None, "WebAuthn credential not found in database"
    expected_cred_id_b64 = credential.credential_id

    # Now try to login
    login_resp = await async_client.post(
        "/auth/login",
        data={"username": user.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert login_resp.status_code == status.HTTP_202_ACCEPTED
    login_data = login_resp.json()
    assert login_data["status"] == "mfa_required"

    # Find WebAuthn method
    webauthn_method = None
    for method in login_data["methods"]:
        if method["method"] == mfa.MFA_METHOD_WEBAUTHN:
            webauthn_method = method
            break
    assert webauthn_method is not None
    assert "options" in webauthn_method

    # Verify Authentication using the actual credential ID from database
    verify_resp = await async_client.post(
        "/auth/mfa/verify",
        json={
            "method": mfa.MFA_METHOD_WEBAUTHN,
            "challenge_token": webauthn_method["challenge_token"],
            # The structure of webauthn response from browser
            "webauthn_response": {
                "id": expected_cred_id_b64,
                "rawId": expected_cred_id_b64,
                "response": {
                    "authenticatorData": "mock_auth_data",
                    "clientDataJSON": "mock_client_data",
                    "signature": "mock_signature",
                },
                "type": "public-key",
            },
        },
    )
    assert verify_resp.status_code == status.HTTP_200_OK
    assert verify_resp.cookies.get("access_token_v2")


@pytest.mark.asyncio
async def test_list_and_delete_credentials(
    async_client, user_factory, db_session, mock_webauthn
):
    password = "WebAuthnList123!"
    user = await user_factory(
        email="webauthn-list@example.com",
        hashed_password=await get_password_hash(password),
    )
    token = await _login_for_token(async_client, user.email, password)
    headers = {"Authorization": f"Bearer {token}"}

    # Enroll
    start_resp = await async_client.post(
        "/auth/mfa/webauthn/register/start", headers=headers
    )
    challenge_token = start_resp.json()["challenge_token"]
    await async_client.post(
        "/auth/mfa/webauthn/register/confirm",
        headers=headers,
        json={
            "challenge": challenge_token,
            "response": {"id": "mock_id", "response": {}},
            "label": "My Key",
        },
    )

    # List (using pre-enrollment token is fine for read-only)
    list_resp = await async_client.get("/auth/mfa/webauthn", headers=headers)
    assert list_resp.status_code == status.HTTP_200_OK
    items = list_resp.json()
    assert len(items) == 1
    assert items[0]["label"] == "My Key"
    cred_id = items[0]["id"]

    # Step-up: after WebAuthn enrollment, delete requires fresh MFA token.
    step_up_login = await async_client.post(
        "/auth/login",
        data={"username": user.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert step_up_login.status_code == status.HTTP_202_ACCEPTED
    webauthn_method = next(
        m
        for m in step_up_login.json()["methods"]
        if m["method"] == mfa.MFA_METHOD_WEBAUTHN
    )
    # Fetch actual credential_id from DB for WebAuthn verify
    from sqlalchemy import select as sa_select

    stmt = sa_select(models.WebAuthnCredential).where(
        models.WebAuthnCredential.user_id == user.id
    )
    result = await db_session.execute(stmt)
    credential = result.scalars().first()
    fresh_verify = await async_client.post(
        "/auth/mfa/verify",
        json={
            "method": mfa.MFA_METHOD_WEBAUTHN,
            "challenge_token": webauthn_method["challenge_token"],
            "webauthn_response": {
                "id": credential.credential_id,
                "rawId": credential.credential_id,
                "response": {
                    "authenticatorData": "mock_auth_data",
                    "clientDataJSON": "mock_client_data",
                    "signature": "mock_signature",
                },
                "type": "public-key",
            },
        },
    )
    assert fresh_verify.status_code == status.HTTP_200_OK
    fresh_token = fresh_verify.cookies.get("access_token_v2")
    fresh_headers = {"Authorization": f"Bearer {fresh_token}"}

    # Test step-up (202)
    step_up_resp = await async_client.post("/auth/mfa/step-up", headers=headers)
    assert step_up_resp.status_code == status.HTTP_202_ACCEPTED

    # Generate recovery codes (200)
    codes_resp = await async_client.post(
        "/auth/mfa/recovery-codes", headers=fresh_headers
    )
    assert codes_resp.status_code == status.HTTP_200_OK
    assert "codes" in codes_resp.json()

    # Delete
    del_resp = await async_client.delete(
        f"/auth/mfa/webauthn/{cred_id}", headers=fresh_headers
    )
    assert del_resp.status_code == status.HTTP_200_OK
    del_data = del_resp.json()
    assert del_data["disabled"] is True  # No more creds
    assert del_data["mfa_required"] is False

    # Verify empty list
    list_resp = await async_client.get("/auth/mfa/webauthn", headers=headers)
    assert list_resp.json() == []


@pytest.mark.asyncio
async def test_webauthn_service_direct_coverage(db_session) -> None:
    import uuid
    from datetime import UTC, datetime
    from unittest.mock import patch

    from app.models import UserRole
    from app.schemas.dtos import UserDTO
    from app.services.webauthn import WebAuthnService

    service = WebAuthnService(db_session)

    assert service._get_origin() is not None

    user_dto = UserDTO(
        id=uuid.uuid4(),
        email="dto@example.com",
        role=UserRole.STUDENT,
        group_id=None,
        is_active=True,
        mfa_required=False,
        mfa_default_method=None,
        mfa_last_verified_at=None,
        created_at=datetime.now(UTC),
        webauthn_id=None,
    )
    with (
        patch("app.services.webauthn.generate_registration_options"),
        patch("app.services.webauthn.options_to_json", return_value="{}"),
    ):
        options = await service.get_registration_options(user_dto)
        assert options is not None

    from app.models import User

    class MockUser(User):
        webauthn_id = property(lambda self: None, lambda self, val: None)

    mock_user = MockUser()
    mock_user.id = uuid.uuid4()
    mock_user.email = "mock@example.com"
    with pytest.raises(ValueError, match="WebAuthn ID missing"):
        await service.get_registration_options(mock_user)

    user_dto_2 = UserDTO(
        id=uuid.uuid4(),
        email="dto@example.com",
        role=UserRole.STUDENT,
        group_id=None,
        is_active=True,
        mfa_required=False,
        mfa_default_method=None,
        mfa_last_verified_at=None,
        created_at=datetime.now(UTC),
        webauthn_id="some_id",
    )
    with (
        patch("app.services.webauthn.generate_registration_options"),
        patch("app.services.webauthn.options_to_json", return_value="{}"),
    ):
        options2 = await service.get_registration_options(user_dto_2)
        assert options2 is not None

    with pytest.raises(ValueError, match="Credential not found"):
        await service.verify_authentication(
            user_dto_2, "challenge", {"id": "non-existent"}
        )

    dummy_options = service.get_dummy_authentication_options()
    assert dummy_options is not None


@pytest.mark.asyncio
async def test_mfa_endpoints_edge_cases(
    async_client, user_factory, db_session, mock_webauthn
) -> None:
    import uuid
    from unittest.mock import MagicMock, patch

    from fastapi import HTTPException

    password = "MfaEdgePass123!"  # pragma: allowlist secret
    user = await user_factory(
        email="mfa-edge@example.com",
        hashed_password=await get_password_hash(password),
    )
    token = await _login_for_token(async_client, user.email, password)
    headers = {"Authorization": f"Bearer {token}"}

    confirm_resp = await async_client.post(
        "/auth/mfa/totp/confirm",
        headers=headers,
        json={"enrollment_id": str(uuid.uuid4()), "code": "123456"},
    )
    assert confirm_resp.status_code == status.HTTP_404_NOT_FOUND

    start_resp = await async_client.post("/auth/mfa/totp/start", headers=headers)
    enrollment_id = start_resp.json()["enrollment"]["id"]

    with patch(
        "app.auth.mfa.complete_totp_enrollment",
        side_effect=HTTPException(400, "Bad code"),
    ):
        confirm_resp = await async_client.post(
            "/auth/mfa/totp/confirm",
            headers=headers,
            json={"enrollment_id": enrollment_id, "code": "123456"},
        )
        assert confirm_resp.status_code == 400

    del_resp = await async_client.delete(
        f"/auth/mfa/totp/pending/{uuid.uuid4()}", headers=headers
    )
    assert del_resp.status_code == status.HTTP_404_NOT_FOUND

    # Start webauthn registration to get a valid challenge token
    start_webauthn = await async_client.post(
        "/auth/mfa/webauthn/register/start", headers=headers
    )
    challenge_token = start_webauthn.json()["challenge_token"]

    # verify_registration raises ValueError -> confirm endpoint returns 400
    with patch(
        "app.services.webauthn.WebAuthnService.verify_registration",
        side_effect=ValueError("Unexpected"),
    ):
        confirm_resp = await async_client.post(
            "/auth/mfa/webauthn/register/confirm",
            headers=headers,
            json={
                "challenge": challenge_token,
                "response": {"id": "mock_id", "response": {}},
                "label": "Key",
            },
        )
        assert confirm_resp.status_code == 400

    # mfa.get_challenge returns challenge with payload = None -> confirm endpoint returns 400
    mock_challenge = MagicMock()
    mock_challenge.payload = None
    with patch("app.auth.mfa.get_challenge", return_value=mock_challenge):
        confirm_resp = await async_client.post(
            "/auth/mfa/webauthn/register/confirm",
            headers=headers,
            json={
                "challenge": "challenge_token_of_at_least_32_chars_length",
                "response": {"id": "mock_id", "response": {}},
                "label": "Key",
            },
        )
        assert confirm_resp.status_code == 400

    del_resp = await async_client.delete(
        f"/auth/mfa/webauthn/{uuid.uuid4()}", headers=headers
    )
    assert del_resp.status_code == status.HTTP_404_NOT_FOUND

    verify_resp = await async_client.post(
        "/auth/mfa/verify",
        json={
            "method": "invalid_method",
            "challenge_token": "challenge_token_of_at_least_32_chars_length",
        },
    )
    assert verify_resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    with patch("app.auth.mfa.consume_challenge", side_effect=HTTPException(400, "Err")):
        verify_resp = await async_client.post(
            "/auth/mfa/verify",
            json={
                "method": "totp",
                "challenge_token": "challenge_token_of_at_least_32_chars_length",
                "totp_code": "123456",
            },
        )
        assert verify_resp.status_code == status.HTTP_400_BAD_REQUEST
