from __future__ import annotations

import base64
import re

from tests.helpers.synthetic_credentials import (
    make_test_marker,
    make_test_password,
    make_test_totp_secret,
    make_test_url_password,
)


def test_password_factory_preserves_requested_classes_and_distinctness() -> None:
    first = make_test_password(length=27)
    second = make_test_password(length=27, excluding=(first,))
    assert len(first) == len(second) == 27
    for value in (first, second):
        assert any(character.islower() for character in value)
        assert any(character.isupper() for character in value)
        assert any(character.isdigit() for character in value)
        assert any(not character.isalnum() for character in value)
    assert first != second


def test_url_password_factory_keeps_userinfo_safe_shape() -> None:
    value = make_test_url_password(
        length=12, required_classes=frozenset({"lower", "symbol"})
    )
    assert len(value) == 12
    assert re.fullmatch(r"[A-Za-z0-9_-]+", value)
    assert any(character.islower() for character in value)
    assert any(not character.isalnum() for character in value)
    assert not any(character.isupper() for character in value)
    assert not any(character.isdigit() for character in value)


def test_totp_factory_returns_decodable_base32_secret() -> None:
    value = make_test_totp_secret()
    assert len(value) == 32
    assert value == value.upper()
    assert len(base64.b32decode(value)) == 20
    assert make_test_totp_secret() != value


def test_marker_factory_keeps_requested_sentinel_shape() -> None:
    value = make_test_marker(length=9)
    assert len(value) == 9
    assert any(character.islower() for character in value)
    assert any(not character.isalnum() for character in value)
    assert not any(character.isupper() for character in value)
    assert not any(character.isdigit() for character in value)
