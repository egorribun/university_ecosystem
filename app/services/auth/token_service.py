from typing import Any, NoReturn
from uuid import UUID

from fastapi import Request

from app.api.validation import raise_unauthorized
from app.auth.security import decode_token


def fail_auth(locale: str) -> NoReturn:
    raise_unauthorized(
        locale,
        "errors.auth.credentials_invalid",
        headers={"WWW-Authenticate": "Bearer"},
    )


class AuthTokenService:
    @staticmethod
    def extract_and_decode_token(
        request: Request, token: str | None, locale: str
    ) -> dict[str, Any]:
        raw_token = token or request.cookies.get("access_token_v2")
        if not raw_token:
            fail_auth(locale)

        payload = decode_token(raw_token)
        if payload is None:
            fail_auth(locale)

        return payload

    @staticmethod
    def validate_payload(payload: dict[str, Any], locale: str) -> tuple[UUID, str]:
        sub = payload.get("sub")
        jti = payload.get("jti")

        if not sub or not jti:
            fail_auth(locale)

        try:
            user_id = UUID(str(sub))
        except TypeError, ValueError:
            fail_auth(locale)

        return user_id, str(jti)
