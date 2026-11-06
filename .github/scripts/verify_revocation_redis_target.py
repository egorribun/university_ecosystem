from __future__ import annotations

import re
from base64 import b64decode
from hmac import compare_digest
from os import fdopen
from sys import argv, stdin
from unicodedata import category
from urllib.parse import unquote_to_bytes, urlsplit


def _decode_effective_credential(encoded_credential: bytes) -> bytes:
    """Decode the password as Redis sees it; command substitution strips LF only."""
    credential = b64decode(encoded_credential, validate=True).rstrip(b"\n")
    credential.decode("utf-8", errors="strict")
    if not credential or b"\0" in credential:
        raise ValueError("empty or NUL-containing Redis credential")
    return credential


def is_valid_revocation_redis_url(
    raw_url: str,
    expected_host: str,
    encoded_credential: bytes,
    encoded_cache_credential: bytes,
) -> bool:
    try:
        parsed = urlsplit(raw_url)
        expected_credential = _decode_effective_credential(encoded_credential)
        cache_credential = _decode_effective_credential(encoded_cache_credential)
        valid = (
            parsed.scheme == "redis"
            and parsed.hostname == expected_host
            and parsed.port == 6379
            and parsed.path == "/0"
            and not parsed.query
            and not parsed.fragment
            and not re.search(r"%(?![0-9a-fA-F]{2})", raw_url)
            and not any(category(char) == "Cc" for char in raw_url)
            and parsed.username is not None
            and unquote_to_bytes(parsed.username) in (b"", b"default")
            and parsed.password is not None
            and not compare_digest(cache_credential, expected_credential)
            and compare_digest(unquote_to_bytes(parsed.password), expected_credential)
        )
        return valid
    except (OSError, UnicodeError, ValueError):
        return False


def main() -> int:
    expected_host = argv[1]
    try:
        raw_url = stdin.read().strip()
        with fdopen(3, "rb") as credential_input:
            encoded_credential = credential_input.read()
        with fdopen(4, "rb") as cache_credential_input:
            encoded_cache_credential = cache_credential_input.read()
        valid = is_valid_revocation_redis_url(
            raw_url, expected_host, encoded_credential, encoded_cache_credential
        )
    except (OSError, UnicodeError, ValueError):
        valid = False
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
