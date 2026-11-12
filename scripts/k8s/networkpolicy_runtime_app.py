"""Application-level checks for AUD-169 (revocation Redis) and AUD-188 (JWKS).

The revocation Redis is the real store chart StatefulSet with a generated password
Secret. The file-processor image cannot reach its serving state in kind (startup
requires Temporal and NATS), so its Redis and JWKS steps run as stdlib clients in
pods that carry the rendered file-processor labels. Keys are generated and tokens
are signed in-process with the project's cryptography dependency. Private keys,
tokens and passwords never enter the receipt, only key identifiers and verdicts.
"""

from __future__ import annotations

import base64
import json
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from networkpolicy_runtime_kube import Pod, run_in_pod
from networkpolicy_runtime_rows import REDIS_PORT
from networkpolicy_runtime_standins import PROBE_SRC, PUBLISH_SRC, VERIFIER_SRC

PUBLIC_EXPONENT = 65537
RSA_BITS = 2048
APP_TIMEOUT = 5.0


@dataclass(frozen=True)
class SigningKey:
    kid: str
    private_key: rsa.RSAPrivateKey
    modulus_b64: str
    exponent_b64: str


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unsigned_bytes(value: int) -> bytes:
    return value.to_bytes((value.bit_length() + 7) // 8, "big")


def generate_signing_key(kid: str) -> SigningKey:
    private_key = rsa.generate_private_key(
        public_exponent=PUBLIC_EXPONENT, key_size=RSA_BITS
    )
    numbers = private_key.public_key().public_numbers()
    return SigningKey(
        kid=kid,
        private_key=private_key,
        modulus_b64=b64url(_unsigned_bytes(numbers.n)),
        exponent_b64=b64url(_unsigned_bytes(numbers.e)),
    )


def jwks_document(keys: list[SigningKey]) -> str:
    entries = [
        {
            "alg": "RS256",
            "e": key.exponent_b64,
            "kid": key.kid,
            "kty": "RSA",
            "n": key.modulus_b64,
            "use": "sig",
        }
        for key in keys
    ]
    return json.dumps({"keys": entries}, separators=(",", ":"), sort_keys=True)


def sign_rs256(signer: SigningKey, signing_input: bytes) -> bytes:
    return signer.private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())


def _segment(document: dict[str, Any]) -> str:
    return b64url(json.dumps(document, separators=(",", ":"), sort_keys=True).encode())


def make_token(signer: SigningKey, kid: str) -> str:
    """Return an RS256 token whose header names kid and whose signature uses signer."""
    header = _segment({"alg": "RS256", "kid": kid, "typ": "JWT"})
    payload = _segment({"aud": "probe", "exp": int(time.time()) + 600, "sub": "probe"})
    signing_input = f"{header}.{payload}".encode("ascii")
    return f"{header}.{payload}.{b64url(sign_rs256(signer, signing_input))}"


def unsigned_token(kid: str) -> str:
    header = _segment({"alg": "none", "kid": kid, "typ": "JWT"})
    payload = _segment({"aud": "probe", "exp": 4102444800, "sub": "probe"})
    return f"{header}.{payload}."


def new_redis_password() -> str:
    return secrets.token_urlsafe(32)


def check(
    finding: str, check_id: str, expected: dict[str, str], observed: dict[str, Any]
) -> dict[str, Any]:
    matches = all(observed.get(key) == value for key, value in expected.items())
    return {
        "check_id": check_id,
        "finding": finding,
        "expected": expected,
        "observed": observed,
        "verdict": "pass" if matches else "fail",
    }


def redis_ping(source: Pod, host: str, password: str) -> dict[str, Any]:
    return run_in_pod(
        source,
        PROBE_SRC,
        ["redis-ping", host, str(REDIS_PORT), str(APP_TIMEOUT)],
        stdin=password,
        timeout=APP_TIMEOUT,
    )


def redis_checks(
    fp_pod: Pod,
    unrelated_pod: Pod,
    redis_ip: str,
    password: str,
    live_control: Callable[[], dict[str, Any]],
) -> list[dict[str, Any]]:
    """AUD-169 against the real revocation Redis, with file-processor labels.

    The unrelated-labels attempt carries the correct password, so a timeout is a
    network denial, not an authentication failure. It is bracketed by a live
    file-processor control to the same Redis.
    """
    wrong_password = new_redis_password()
    results = [
        check(
            "AUD-169",
            "aud169-redis-authenticated-ping",
            {"result": "redis-pong", "auth": "+OK"},
            redis_ping(fp_pod, redis_ip, password),
        ),
        check(
            "AUD-169",
            "aud169-redis-unauthenticated-denied",
            {"result": "redis-denied", "reply": "-NOAUTH"},
            redis_ping(fp_pod, redis_ip, ""),
        ),
        check(
            "AUD-169",
            "aud169-redis-wrong-password-denied",
            {"result": "redis-denied", "auth": "-WRONGPASS"},
            redis_ping(fp_pod, redis_ip, wrong_password),
        ),
    ]
    control_before = live_control()
    attempt = redis_ping(unrelated_pod, redis_ip, password)
    control_after = live_control()
    denied = (
        attempt.get("result") == "timeout"
        and control_before.get("result") == "redis-pong"
        and control_after.get("result") == "redis-pong"
    )
    results.append(
        {
            "check_id": "aud169-redis-unrelated-labels-denied",
            "finding": "AUD-169",
            "expected": {
                "attempt": "timeout",
                "control": "redis-pong before and after",
            },
            "observed": {
                "attempt": attempt,
                "control_before": control_before,
                "control_after": control_after,
            },
            "verdict": "pass" if denied else "fail",
        }
    )
    return results


def publish_jwks(publisher: Pod, document: str) -> dict[str, Any]:
    return run_in_pod(publisher, PUBLISH_SRC, [], stdin=document, timeout=APP_TIMEOUT)


def verify_token(consumer: Pod, jwks_url: str, token: str) -> dict[str, Any]:
    return run_in_pod(
        consumer,
        VERIFIER_SRC,
        [jwks_url, str(APP_TIMEOUT)],
        stdin=token,
        timeout=APP_TIMEOUT,
    )


def jwks_rotation_checks(
    consumer: Pod, publisher: Pod, jwks_url: str
) -> list[dict[str, Any]]:
    """AUD-188: RS256 acceptance across publication, dual-key rotation and retirement.

    Each verification fetches the JWKS from the publisher through the consumer's
    own network namespace, so the enforced policy applies to every step. The
    file-processor refresher (interval and last-known-good logic) is not exercised
    by this stand-in consumer; the receipt says so.
    """
    key1 = generate_signing_key("probe-key-1")
    key2 = generate_signing_key("probe-key-2")
    key3 = generate_signing_key("probe-key-3")
    results: list[dict[str, Any]] = []

    def step(check_id: str, token: str, expected: dict[str, str]) -> None:
        observed = verify_token(consumer, jwks_url, token)
        results.append(check("AUD-188", check_id, expected, observed))

    accepted = {"result": "accepted"}

    def rejected(reason: str) -> dict[str, str]:
        return {"result": "rejected", "reason": reason}

    publish_jwks(publisher, jwks_document([key1]))
    step("aud188-key1-accepted-after-publication", make_token(key1, key1.kid), accepted)
    step(
        "aud188-key2-rejected-before-publication",
        make_token(key2, key2.kid),
        rejected("unknown-kid"),
    )
    publish_jwks(publisher, jwks_document([key1, key2]))
    step("aud188-key2-accepted-after-rotation", make_token(key2, key2.kid), accepted)
    step("aud188-key1-accepted-during-transition", make_token(key1, key1.kid), accepted)
    step(
        "aud188-unpublished-key3-rejected",
        make_token(key3, key3.kid),
        rejected("unknown-kid"),
    )
    step(
        "aud188-forged-kid-rejected",
        make_token(key3, key1.kid),
        rejected("bad-signature"),
    )
    step("aud188-alg-none-rejected", unsigned_token(key1.kid), rejected("alg"))
    publish_jwks(publisher, jwks_document([key2]))
    step(
        "aud188-retired-key1-rejected",
        make_token(key1, key1.kid),
        rejected("unknown-kid"),
    )
    step("aud188-key2-accepted-after-retirement", make_token(key2, key2.kid), accepted)
    return results


def all_passed(checks: list[dict[str, Any]]) -> bool:
    return all(item.get("verdict") == "pass" for item in checks)
