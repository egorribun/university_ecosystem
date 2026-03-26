from __future__ import annotations

import base64
import json
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
from app.core.logging import get_logger
from app.models import User, WebAuthnCredential
from app.repositories.auth_repository import AuthRepository
from app.schemas.dtos import UserDTO

if TYPE_CHECKING:
    from app.core.protocols import AsyncDatabaseSession

logger = get_logger(__name__)


class WebAuthnService:
    def __init__(self, db: AsyncDatabaseSession) -> None:
        self.db = db
        self.repo = AuthRepository(db)

    def _get_rp_id(self) -> str:
        return settings.webauthn_rp_id

    def _get_rp_name(self) -> str:
        return settings.webauthn_rp_name

    def _get_origin(self) -> str:
        return settings.webauthn_origin

    async def get_registration_options(self, user: User | UserDTO) -> dict[str, Any]:
        """Generate options for a new WebAuthn credential registration."""
        if not user.webauthn_id:
            new_id = (
                base64.urlsafe_b64encode(generate_user_handle())
                .decode("utf-8")
                .rstrip("=")
            )
            if not isinstance(user, User):
                # We can't persist a new webauthn_id on a DTO in this flow
                # without the DB. In practice, this should be ORM.
                # However, for type safety, we handle it.
                user = user.model_copy(update={"webauthn_id": new_id})
            else:
                user.webauthn_id = new_id
                await self.db.flush()

        # Ensure webauthn_id is non-None for concatenation
        wid = user.webauthn_id
        if not wid:
            raise ValueError("WebAuthn ID missing after generation attempt")

        user_id_bytes = base64.urlsafe_b64decode(wid + "==")

        # Get existing credentials to exclude them
        result = await self.repo.list_user_webauthn_credentials(user.id)
        exclude_credentials = [
            PublicKeyCredentialDescriptor(
                id=base64.urlsafe_b64decode(cre.credential_id + "=="),
                type=PublicKeyCredentialType.PUBLIC_KEY,
            )
            for cre in result
        ]

        profile = getattr(user, "profile", None)
        display_name = (
            getattr(user, "full_name", None)
            or (getattr(profile, "full_name", None) if profile else None)
            or str(user.email)
        )
        options = generate_registration_options(
            rp_id=self._get_rp_id(),
            rp_name=self._get_rp_name(),
            user_id=user_id_bytes,
            user_name=str(user.email),
            user_display_name=display_name,
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
        # TD-6 (audit 2026-02-26): Read from config instead of hardcoding False.
        # PREFERRED means we ask for UV but don't fail if the authenticator can't
        # provide it (hardware keys without PIN). Setting
        # WEBAUTHN_REQUIRE_USER_VERIFICATION=true in .env enforces PIN/biometric
        # for passkey-grade security (FIDO2 Level 2).
        _require_uv = getattr(settings, "webauthn_require_user_verification", False)
        verification = verify_registration_response(
            credential=response,
            expected_challenge=base64.urlsafe_b64decode(challenge + "=="),
            expected_origin=settings.frontend_origins_list,
            expected_rp_id=self._get_rp_id(),
            require_user_verification=_require_uv,
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

    async def get_authentication_options(self, user: User | UserDTO) -> dict[str, Any]:
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
        self, user: User | UserDTO, challenge: str, response: dict[str, Any]
    ) -> WebAuthnCredential:
        """Verify the authentication response."""
        credential_id = response.get("id")
        db_credential = await self.repo.get_webauthn_credential(
            user.id, str(credential_id)
        )
        if not db_credential:
            raise ValueError("Credential not found")

        # HIGH-W19: read UV requirement from config instead of hardcoding False so
        # deployments can enforce PIN/biometric (FIDO2 Level 2) via settings.
        _require_uv = getattr(settings, "webauthn_require_user_verification", True)
        verification = verify_authentication_response(
            credential=response,
            expected_challenge=base64.urlsafe_b64decode(challenge + "=="),
            expected_origin=settings.frontend_origins_list,
            expected_rp_id=self._get_rp_id(),
            credential_public_key=base64.urlsafe_b64decode(
                db_credential.public_key + "=="
            ),
            credential_current_sign_count=int(str(db_credential.sign_count)),
            require_user_verification=_require_uv,
        )

        db_credential.sign_count = verification.new_sign_count
        db_credential.last_used_at = datetime.now(UTC)
        await self.db.flush()

        return db_credential


def json_to_dict(json_str: str) -> dict[str, Any]:
    return json.loads(json_str)  # type: ignore[no-any-return]
