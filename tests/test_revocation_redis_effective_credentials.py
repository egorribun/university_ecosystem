"""Exercise the deployment validator CLI with both secret-file descriptors."""

from __future__ import annotations

import base64
import importlib.util
import io
import secrets
from pathlib import Path
from urllib.parse import quote_from_bytes

import pytest

_VALIDATOR_PATH = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "scripts"
    / "verify_revocation_redis_target.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "verify_revocation_redis_target_candidate", _VALIDATOR_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("revocation target validator candidate is unavailable")
_VALIDATOR = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_VALIDATOR)


def _password() -> bytes:
    return secrets.token_urlsafe(24).encode("ascii")


def _url(
    password: bytes, *, scheme: str = "redis", host: str = "revocation.test"
) -> str:
    encoded = quote_from_bytes(password, safe="")
    return f"{scheme}://:{encoded}@{host}:6379/0"


def _run_cli(
    monkeypatch: pytest.MonkeyPatch,
    *,
    url: str,
    revocation_password: bytes,
    cache_password: bytes,
    expected_host: str = "revocation.test",
) -> int:
    inputs = {
        3: io.BytesIO(base64.b64encode(revocation_password)),
        4: io.BytesIO(base64.b64encode(cache_password)),
    }

    def open_descriptor(descriptor: int, mode: str) -> io.BytesIO:
        assert mode == "rb"
        return inputs[descriptor]

    monkeypatch.setattr(_VALIDATOR, "argv", ["validator", expected_host])
    monkeypatch.setattr(_VALIDATOR, "stdin", io.StringIO(url))
    monkeypatch.setattr(_VALIDATOR, "fdopen", open_descriptor)
    return _VALIDATOR.main()


def test_deployment_cli_rejects_distinct_secret_bytes_with_same_effective_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    password = _password()

    result = _run_cli(
        monkeypatch,
        url=_url(password),
        revocation_password=password + b"\n",
        cache_password=password,
    )

    assert result == 1


def test_deployment_cli_accepts_distinct_effective_passwords(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revocation_password = _password()
    cache_password = _password()
    while cache_password == revocation_password:
        cache_password = _password()

    result = _run_cli(
        monkeypatch,
        url=_url(revocation_password),
        revocation_password=revocation_password,
        cache_password=cache_password,
    )

    assert result == 0


def test_deployment_cli_strips_trailing_lf_but_preserves_carriage_return(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revocation_password = _password()
    cache_password = _password()
    while cache_password in (revocation_password, revocation_password + b"\r"):
        cache_password = _password()

    result = _run_cli(
        monkeypatch,
        url=_url(revocation_password + b"\r"),
        revocation_password=revocation_password + b"\r\n",
        cache_password=cache_password,
    )

    assert result == 0


@pytest.mark.parametrize(
    "invalid_password",
    [b"", b"\xff", b"invalid\0credential"],
)
@pytest.mark.parametrize("target", ["cache", "revocation"])
def test_deployment_cli_rejects_empty_nul_or_non_utf8_passwords(
    monkeypatch: pytest.MonkeyPatch,
    invalid_password: bytes,
    target: str,
) -> None:
    revocation_password = _password()
    cache_password = _password()
    while cache_password == revocation_password:
        cache_password = _password()
    if target == "cache":
        cache_password = invalid_password
        url_password = revocation_password
    else:
        revocation_password = invalid_password
        url_password = invalid_password

    result = _run_cli(
        monkeypatch,
        url=_url(url_password),
        revocation_password=revocation_password,
        cache_password=cache_password,
    )

    assert result == 1


@pytest.mark.parametrize(
    "url",
    [
        "rediss://:opaque@revocation.test:6379/0",
        "redis://:opaque@unexpected.test:6379/0",
    ],
)
def test_deployment_cli_keeps_scheme_and_exact_host_checks(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
) -> None:
    revocation_password = _password()
    cache_password = _password()
    while cache_password == revocation_password:
        cache_password = _password()

    result = _run_cli(
        monkeypatch,
        url=url,
        revocation_password=revocation_password,
        cache_password=cache_password,
    )

    assert result == 1


def test_deploy_caller_passes_both_password_sources_by_file_descriptor() -> None:
    workflow_path = _VALIDATOR_PATH.parents[1] / "workflows" / "deploy.yml"
    workflow = workflow_path.read_text(encoding="utf-8")

    assert (
        "python3 -I .github/scripts/verify_revocation_redis_target.py "
        '"$revocation_redis_service_host" \\\n'
        "                3< <(printf '%s' \"$revocation_redis_password_b64\") \\\n"
        "                4< <(printf '%s' \"$cache_redis_password_b64\"); then"
    ) in workflow
