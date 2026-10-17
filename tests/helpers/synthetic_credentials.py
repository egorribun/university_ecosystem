from __future__ import annotations

import base64
import secrets
import string
from collections.abc import Iterable

_CLASS_POOLS = {
    "lower": string.ascii_lowercase,
    "upper": string.ascii_uppercase,
    "digit": string.digits,
    "symbol": "!#$%&()*+,-./:;<=>?@[]^_{|}~",
}
_URL_CLASS_POOLS = {**_CLASS_POOLS, "symbol": "-_"}
_DEFAULT_CLASSES = frozenset(_CLASS_POOLS)


def _generate(
    length: int,
    required_classes: frozenset[str],
    excluded: Iterable[str],
    pools: dict[str, str],
) -> str:
    unknown = required_classes.difference(pools)
    if unknown:
        raise ValueError("unsupported character class")
    if length < max(1, len(required_classes)):
        raise ValueError("credential length is too short")
    selected = tuple(pools[name] for name in sorted(required_classes))
    alphabet = "".join(selected)
    excluded_values = frozenset(excluded)
    while True:
        characters = [secrets.choice(pool) for pool in selected]
        characters.extend(
            secrets.choice(alphabet) for _ in range(length - len(characters))
        )
        secrets.SystemRandom().shuffle(characters)
        value = "".join(characters)
        if value not in excluded_values:
            return value


def make_test_password(
    *,
    length: int = 32,
    required_classes: frozenset[str] = _DEFAULT_CLASSES,
    excluding: Iterable[str] = (),
) -> str:
    """Create a fresh, shape-controlled password for isolated test inputs."""
    if length < 8:
        raise ValueError("password length is too short")
    return _generate(length, required_classes, excluding, _CLASS_POOLS)


def make_test_url_password(
    *, length: int = 32, required_classes: frozenset[str] = _DEFAULT_CLASSES
) -> str:
    """Create URL-userinfo-safe test data without percent-encoding ambiguity."""
    return _generate(length, required_classes, (), _URL_CLASS_POOLS)


def make_test_totp_secret() -> str:
    """Create a valid Base32 TOTP secret from fresh random bytes."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def make_test_marker(
    *,
    length: int,
    required_classes: frozenset[str] = frozenset({"lower", "symbol"}),
) -> str:
    """Create a non-credential sentinel for preservation-only test fields."""
    return _generate(length, required_classes, (), _CLASS_POOLS)
