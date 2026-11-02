"""SQLAlchemy encryption types with runtime-only key consumers."""

from __future__ import annotations

from typing import Any

from sqlalchemy.types import Text, TypeDecorator


class TotpEncryptedString(TypeDecorator[str]):
    """TypeDecorator using the dedicated MFA TOTP encryption key ring."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Any) -> str | None:
        from app.utils.encryption import encrypt_totp_string

        return encrypt_totp_string(value)

    def process_result_value(self, value: str | None, dialect: Any) -> str | None:
        from app.utils.encryption import decrypt_totp_string

        return decrypt_totp_string(value)


class EncryptedString(TypeDecorator[str]):
    """TypeDecorator that transparently encrypts/decrypts string values."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Any) -> str | None:
        from app.utils.encryption import encrypt_string

        return encrypt_string(value)

    def process_result_value(self, value: str | None, dialect: Any) -> str | None:
        from app.utils.encryption import decrypt_string

        return decrypt_string(value)
