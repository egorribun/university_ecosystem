"""HIBP response parsing honors the configured lookup failure policy."""

from __future__ import annotations

import secrets

import httpx
import pytest

from app.auth import security
from app.core.config import settings

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.fixture
def candidate() -> str:
    return secrets.token_urlsafe(32)


def _suffixes(candidate: str) -> tuple[str, str]:
    suffix = security._calculate_lookup_hash(candidate)[5:]
    other = "0" * 35 if suffix != "0" * 35 else "F" * 35
    return suffix, other


async def _check_response(
    monkeypatch: pytest.MonkeyPatch,
    candidate: str,
    body: str,
    *,
    fail_open: bool,
) -> None:
    monkeypatch.setattr(settings, "password_hibp_fail_open", fail_open)
    monkeypatch.setattr(security, "translate", lambda key, **_: key)
    transport = httpx.MockTransport(
        lambda _: httpx.Response(status_code=200, text=body)
    )
    async with httpx.AsyncClient(transport=transport, trust_env=False) as client:

        async def get_client() -> httpx.AsyncClient:
            return client

        monkeypatch.setattr(security, "_get_hibp_client", get_client)
        await security.validate_password_hibp(candidate)


@pytest.mark.parametrize("fail_open", [False, True])
async def test_valid_clean_and_padded_records_are_accepted(
    monkeypatch: pytest.MonkeyPatch, candidate: str, fail_open: bool
) -> None:
    suffix, other = _suffixes(candidate)
    body = f"{other.lower()}:12\r\n{suffix.lower()}:0\r\n"
    await _check_response(monkeypatch, candidate, body, fail_open=fail_open)


@pytest.mark.parametrize("fail_open", [False, True])
async def test_valid_positive_record_is_rejected(
    monkeypatch: pytest.MonkeyPatch, candidate: str, fail_open: bool
) -> None:
    suffix, other = _suffixes(candidate)
    body = f"{other}:0\n{suffix.lower()}:0007\n"
    with pytest.raises(ValueError, match="password_policy_compromised"):
        await _check_response(monkeypatch, candidate, body, fail_open=fail_open)


@pytest.mark.parametrize(
    "case",
    [
        "empty",
        "missing_separator",
        "missing_count",
        "nondigit_count",
        "negative_count",
        "decimal_count",
        "unicode_count",
        "extra_separator",
        "short_suffix",
        "nonhex_suffix",
        "blank_record",
        "invalid_after_zero_match",
    ],
)
@pytest.mark.parametrize("fail_open", [False, True])
async def test_malformed_response_obeys_existing_failure_policy(
    monkeypatch: pytest.MonkeyPatch,
    candidate: str,
    case: str,
    fail_open: bool,
) -> None:
    suffix, other = _suffixes(candidate)
    bodies = {
        "empty": "",
        "missing_separator": other,
        "missing_count": f"{suffix}:\n",
        "nondigit_count": f"{suffix}:invalid\n",
        "negative_count": f"{suffix}:-1\n",
        "decimal_count": f"{suffix}:1.0\n",
        "unicode_count": f"{suffix}:{chr(0x0661)}\n",
        "extra_separator": f"{suffix}:0:1\n",
        "short_suffix": f"{other[:-1]}:1\n",
        "nonhex_suffix": f"{other[:-1]}G:1\n",
        "blank_record": f"{other}:1\n\n{suffix}:0\n",
        "invalid_after_zero_match": f"{suffix}:0\n{other}:invalid\n",
    }
    if fail_open:
        await _check_response(monkeypatch, candidate, bodies[case], fail_open=True)
    else:
        with pytest.raises(ValueError, match="password_policy_hibp_unavailable"):
            await _check_response(monkeypatch, candidate, bodies[case], fail_open=False)


@pytest.mark.parametrize("fail_open", [False, True])
async def test_duplicate_zero_does_not_hide_positive_record(
    monkeypatch: pytest.MonkeyPatch, candidate: str, fail_open: bool
) -> None:
    suffix, _ = _suffixes(candidate)
    body = f"{suffix}:0\n{suffix}:2\n"
    with pytest.raises(ValueError, match="password_policy_compromised"):
        await _check_response(monkeypatch, candidate, body, fail_open=fail_open)


@pytest.mark.parametrize("fail_open", [False, True])
async def test_invalid_matching_count_does_not_hide_later_positive_record(
    monkeypatch: pytest.MonkeyPatch, candidate: str, fail_open: bool
) -> None:
    suffix, _ = _suffixes(candidate)
    body = f"{suffix}:invalid\n{suffix}:2\n"
    with pytest.raises(ValueError, match="password_policy_compromised"):
        await _check_response(monkeypatch, candidate, body, fail_open=fail_open)


@pytest.mark.parametrize("fail_open", [False, True])
async def test_large_decimal_count_still_identifies_a_positive_record(
    monkeypatch: pytest.MonkeyPatch, candidate: str, fail_open: bool
) -> None:
    suffix, _ = _suffixes(candidate)
    body = f"{suffix}:{'0' * 5000}1\n"
    with pytest.raises(ValueError, match="password_policy_compromised"):
        await _check_response(monkeypatch, candidate, body, fail_open=fail_open)


@pytest.mark.parametrize("fail_open", [False, True])
@pytest.mark.parametrize("malformed_first", [False, True])
async def test_valid_positive_record_wins_over_malformed_response(
    monkeypatch: pytest.MonkeyPatch,
    candidate: str,
    fail_open: bool,
    malformed_first: bool,
) -> None:
    suffix, other = _suffixes(candidate)
    records = [f"{suffix}:3", f"{other}:invalid"]
    if malformed_first:
        records.reverse()
    with pytest.raises(ValueError, match="password_policy_compromised"):
        await _check_response(
            monkeypatch, candidate, "\n".join(records), fail_open=fail_open
        )
