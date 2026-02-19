from __future__ import annotations

import base64
import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import generate_user_handle, options_to_json
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    PublicKeyCredentialType,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.core.config import settings
from app.models.models import User, WebAuthnCredential
from app.repositories.auth_repository import AuthRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class WebAuthnService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = AuthRepository(db)

    def _get_rp_id(self) -> str:
        return settings.webauthn_rp_id

    def _get_rp_name(self) -> str:
        return settings.webauthn_rp_name

    def _get_origin(self) -> str:
        return settings.webauthn_origin

    async def get_registration_options(self, user: User) -> dict[str, Any]:
        """Generate options for a new WebAuthn credential registration."""
        if not user.webauthn_id:
            user.webauthn_id = (
                base64.urlsafe_b64encode(generate_user_handle())
                .decode("utf-8")
                .rstrip("=")
            )
            await self.db.flush()

        user_id_bytes = base64.urlsafe_b64decode(user.webauthn_id + "==")

        # Get existing credentials to exclude them
        result = await self.repo.list_user_webauthn_credentials(user.id)
        exclude_credentials = [
            {
                "id": base64.urlsafe_b64decode(cre.credential_id + "=="),
                "type": "public-key",
            }
            for cre in result
        ]

        options = generate_registration_options(
            rp_id=self._get_rp_id(),
            rp_name=self._get_rp_name(),
            user_id=user_id_bytes,
            user_name=user.email,
            user_display_name=user.full_name or user.email,
            exclude_credentials=exclude_credentials,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.PREFERRED,
                user_verification=UserVerificationRequirement.PREFERRED,
            ),
        )

        return json_to_dict(options_to_json(options))

    async def verify_registration(
        self,
        user: User,
        challenge: str,
        response: dict[str, Any],
        label: str | None = None,
    ) -> WebAuthnCredential:
        """Verify the registration response and save the new credential."""
        verification = verify_registration_response(
            credential=response,
            expected_challenge=base64.urlsafe_b64decode(challenge + "=="),
            expected_origin=settings.frontend_origins_list,
            expected_rp_id=self._get_rp_id(),
            require_user_verification=False,  # We use PREFERRED in options
        )

        credential = await self.repo.create_webauthn_credential(
            user_id=user.id,
            credential_id=base64.urlsafe_b64encode(verification.credential_id)
            .decode("utf-8")
            .rstrip("="),
            public_key=base64.urlsafe_b64encode(verification.credential_public_key)
            .decode("utf-8")
            .rstrip("="),
            sign_count=verification.sign_count,
            transports=response.get("response", {}).get("transports"),
            label=label or "WebAuthn Device",
            backing_up=verification.credential_device_type == "multi_device",
            backup_state=verification.credential_backed_up,
        )
        return credential

    async def get_authentication_options(self, user: User) -> dict[str, Any]:
        """Generate options for WebAuthn authentication."""
        result = await self.repo.list_user_webauthn_credentials(user.id)
        allow_credentials = [
            PublicKeyCredentialDescriptor(
                id=base64.urlsafe_b64decode(cre.credential_id + "=="),
                type=PublicKeyCredentialType.PUBLIC_KEY,
            )
            for cre in result
        ]

        options = generate_authentication_options(
            rp_id=self._get_rp_id(),
            allow_credentials=allow_credentials,
            user_verification=UserVerificationRequirement.PREFERRED,
        )

        return json_to_dict(options_to_json(options))

    def get_dummy_authentication_options(self) -> dict[str, Any]:
        """Generate fake authentication options to prevent user enumeration."""
        import secrets

        # Create a dummy challenge and a random fake credential ID
        dummy_credential_id = secrets.token_bytes(32)
        allow_credentials = [
            PublicKeyCredentialDescriptor(
                id=dummy_credential_id,
                type=PublicKeyCredentialType.PUBLIC_KEY,
            )
        ]

        # Use a random RP ID if needed, but usually we use the real one
        # to make the timing and behavior look standard.
        options = generate_authentication_options(
            rp_id=self._get_rp_id(),
            allow_credentials=allow_credentials,
            user_verification=UserVerificationRequirement.PREFERRED,
        )

        return json_to_dict(options_to_json(options))

    async def verify_authentication(
        self, user: User, challenge: str, response: dict[str, Any]
    ) -> WebAuthnCredential:
        """Verify the authentication response."""
        credential_id = response.get("id")
        db_credential = await self.repo.get_webauthn_credential(user.id, credential_id)
        if not db_credential:
            raise ValueError("Credential not found")

        verification = verify_authentication_response(
            credential=response,
            expected_challenge=base64.urlsafe_b64decode(challenge + "=="),
            expected_origin=settings.frontend_origins_list,
            expected_rp_id=self._get_rp_id(),
            credential_public_key=base64.urlsafe_b64decode(
                db_credential.public_key + "=="
            ),
            credential_current_sign_count=db_credential.sign_count,
            require_user_verification=False,
        )

        db_credential.sign_count = verification.new_sign_count
        db_credential.last_used_at = datetime.now(UTC)
        await self.db.flush()

        return db_credential


def json_to_dict(json_str: str) -> dict[str, Any]:
    return json.loads(json_str)
