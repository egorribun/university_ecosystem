"""Regression tests for the Argon2id-only password verifier contract."""

from __future__ import annotations

import secrets
from unittest.mock import patch

from argon2 import PasswordHasher, Type

from app.auth import security


def _low_cost_hasher(hash_type: Type) -> PasswordHasher:
    return PasswordHasher(
        time_cost=1,
        memory_cost=8,
        parallelism=1,
        type=hash_type,
    )


def test_only_valid_argon2id_hashes_are_accepted_by_both_verifiers() -> None:
    password = secrets.token_urlsafe(24)
    hash_types = (Type.ID, Type.I, Type.D)
    hashers = {hash_type: _low_cost_hasher(hash_type) for hash_type in hash_types}
    hashes = {hash_type: hasher.hash(password) for hash_type, hasher in hashers.items()}

    assert hashes[Type.ID].startswith("$argon2id$")
    assert hashes[Type.I].startswith("$argon2i$")
    assert hashes[Type.D].startswith("$argon2d$")

    with patch.object(security, "argon2_hasher", hashers[Type.ID]):
        assert security.verify_password_sync(password, hashes[Type.ID]) is True
        assert security.verify_and_update_password_sync(password, hashes[Type.ID]) == (
            True,
            None,
        )

        for unsupported_type in (Type.I, Type.D):
            variant_hash = hashes[unsupported_type]
            # Prove each fixture is valid before asserting policy rejection.
            assert hashers[unsupported_type].verify(variant_hash, password) is True
            assert security.verify_password_sync(password, variant_hash) is False
            assert security.verify_and_update_password_sync(password, variant_hash) == (
                False,
                None,
            )


def test_malformed_argon2id_and_legacy_bcrypt_shapes_fail_closed() -> None:
    password = secrets.token_urlsafe(24)
    unsupported_hashes = (
        "$argon2id$not-a-valid-hash",
        "$2b$12$" + "A" * 53,
        "legacy-hash-structure",
    )
    with patch.object(security, "argon2_hasher", _low_cost_hasher(Type.ID)):
        for hashed_password in unsupported_hashes:
            assert security.verify_password_sync(password, hashed_password) is False
            assert security.verify_and_update_password_sync(
                password, hashed_password
            ) == (
                False,
                None,
            )
