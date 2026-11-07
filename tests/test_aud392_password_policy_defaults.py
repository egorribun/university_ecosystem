"""AUD-392: password policy defaults are 12 characters and zxcvbn score 2.

The policy is enforced on set, change, reset and registration through
``get_password_hash``.  Login verifies stored hashes without re-checking the
policy, so accounts created under the former 8/1 defaults are not locked out.
"""

from __future__ import annotations

import secrets

import pytest
from sqlalchemy import select
from zxcvbn import zxcvbn

import app.models as models
from app.auth import security
from app.auth.security import get_password_hash, verify_and_update_password
from app.core.config.mixins.mfa_settings import MfaSettingsMixin
from tests.fixtures.auth.auth_fixtures import create_access_token

# Strong by zxcvbn and character classes: each fixture isolates one rule.
ELEVEN_CHARACTERS = "Xk9#pLq2!Zm"  # 11 characters, zxcvbn score 4
TWELVE_CHARACTERS = "Qw8!zXc4Vb7@"  # 12 characters, zxcvbn score 4
WEAK_SCORE_ONE = "Password1234!"  # 13 characters, zxcvbn score 1
LEGACY_SHORT = "Legacy#42"  # accepted under the former 8/1 defaults only


def test_mixin_defaults_are_twelve_characters_and_zxcvbn_score_two() -> None:
    assert MfaSettingsMixin.password_min_length == 12
    assert MfaSettingsMixin.password_zxcvbn_min_score == 2
    assert MfaSettingsMixin.password_min_character_classes == 3


def test_effective_runtime_defaults_match_the_policy_decision() -> None:
    assert security.settings.password_min_length == 12
    assert security.settings.password_zxcvbn_min_score == 2


def test_fixtures_isolate_the_length_and_strength_rules() -> None:
    assert len(ELEVEN_CHARACTERS) == 11
    assert zxcvbn(ELEVEN_CHARACTERS)["score"] >= 2
    assert len(TWELVE_CHARACTERS) == 12
    assert zxcvbn(TWELVE_CHARACTERS)["score"] >= 2
    assert len(WEAK_SCORE_ONE) >= 12
    assert zxcvbn(WEAK_SCORE_ONE)["score"] == 1


def test_policy_rejects_eleven_characters_under_the_defaults() -> None:
    with pytest.raises(ValueError, match="12"):
        security._validate_password_policy(ELEVEN_CHARACTERS)


def test_policy_rejects_zxcvbn_score_below_two_under_the_defaults() -> None:
    with pytest.raises(ValueError, match="too weak"):
        security._validate_password_policy(WEAK_SCORE_ONE)


def test_policy_accepts_a_twelve_character_strong_password() -> None:
    assert (security._validate_password_policy(TWELVE_CHARACTERS)) is None


async def test_set_and_change_paths_hash_only_policy_compliant_passwords() -> None:
    with pytest.raises(ValueError, match="12"):
        await get_password_hash(ELEVEN_CHARACTERS)
    with pytest.raises(ValueError):
        await get_password_hash(WEAK_SCORE_ONE)

    hashed = await get_password_hash(TWELVE_CHARACTERS)

    assert hashed.startswith("$argon2")


async def test_legacy_short_hash_still_verifies_without_a_policy_check() -> None:
    legacy_hash = await get_password_hash(LEGACY_SHORT, validate_policy=False)

    verified, rehashed = await verify_and_update_password(LEGACY_SHORT, legacy_hash)

    assert verified is True
    assert rehashed is None


async def test_existing_user_with_legacy_password_can_still_log_in(
    async_client, user_factory
) -> None:
    user = await user_factory(
        email=f"legacy-{secrets.token_hex(4)}@example.com",
        hashed_password=await get_password_hash(LEGACY_SHORT, validate_policy=False),
    )

    response = await async_client.post(
        "/auth/login",
        data={"username": user.email, "password": LEGACY_SHORT},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 200
    assert response.json()["user"]["id"] == str(user.id)


async def test_registration_rejects_eleven_characters(async_client) -> None:
    response = await async_client.post(
        "/auth/register",
        json={
            "email": f"short-{secrets.token_hex(4)}@example.com",
            "password": ELEVEN_CHARACTERS,
            "full_name": "Short Password",
        },
    )

    assert response.status_code == 400
    assert "12" in response.json()["detail"]


async def test_registration_accepts_a_twelve_character_strong_password(
    async_client, db_session
) -> None:
    email = f"strong-{secrets.token_hex(4)}@example.com"
    response = await async_client.post(
        "/auth/register",
        json={
            "email": email,
            "password": TWELVE_CHARACTERS,
            "full_name": "Strong Password",
        },
    )

    assert response.status_code == 200
    user = (
        await db_session.execute(select(models.User).where(models.User.email == email))
    ).scalar_one()
    assert user.hashed_password.startswith("$argon2")


async def test_admin_create_rejects_eleven_characters_with_bad_request(
    async_client, user_factory, db_session
) -> None:
    admin = await user_factory(
        email=f"admin-{secrets.token_hex(4)}@example.com", role="admin"
    )
    token, _session = await create_access_token(str(admin.id), db_session)

    response = await async_client.post(
        "/users",
        json={
            "email": f"created-{secrets.token_hex(4)}@example.com",
            "password": ELEVEN_CHARACTERS,
            "full_name": "Created By Admin",
            "role": "student",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert "12" in response.json()["detail"]


async def test_admin_create_rejects_weak_score_with_bad_request(
    async_client, user_factory, db_session
) -> None:
    admin = await user_factory(
        email=f"admin-{secrets.token_hex(4)}@example.com", role="admin"
    )
    token, _session = await create_access_token(str(admin.id), db_session)

    response = await async_client.post(
        "/users",
        json={
            "email": f"weak-{secrets.token_hex(4)}@example.com",
            "password": WEAK_SCORE_ONE,
            "full_name": "Weak Admin Create",
            "role": "student",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400


async def test_admin_create_accepts_a_twelve_character_strong_password(
    async_client, user_factory, db_session
) -> None:
    admin = await user_factory(
        email=f"admin-{secrets.token_hex(4)}@example.com", role="admin"
    )
    token, _session = await create_access_token(str(admin.id), db_session)
    email = f"created-{secrets.token_hex(4)}@example.com"

    response = await async_client.post(
        "/users",
        json={
            "email": email,
            "password": TWELVE_CHARACTERS,
            "full_name": "Created By Admin",
            "role": "student",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["email"] == email
