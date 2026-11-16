"""Closed, credential-free observations for the live email MFA scenario."""

import pytest

from scripts.live_stand_playwright_evidence import _live_playwright_http_operations


def _mfa_row(**changes: object) -> str:
    fields: dict[str, object] = {
        "project": "mobile",
        "source": "email-otp-mfa-login.live.spec.ts",
        "line": 378,
        "retry": 1,
        "ordinal": 1,
        "phase": "body",
        "operation": "email-mfa-verification-accept",
        "outcome": "response",
        "status": 429,
        "elapsed_ms": 12,
        "saturated": 0,
        "requests": 0,
        "responses": 1,
        "retry_after_seconds": 321,
        "limiter_signature": "domain-signature",
    }
    fields.update(changes)
    return (
        "UE_LIVE_HTTP_OPERATION_V3 "
        + " ".join(f"{key}={value}" for key, value in fields.items())
        + "\n"
    )


def test_mfa_operation_parser_retains_attempt_and_rate_limit_observation() -> None:
    result = _live_playwright_http_operations(_mfa_row())
    assert result["completeness"] == "unverified"
    assert result["correlation"] == "unambiguous"
    records = result["records"]
    assert isinstance(records, list)
    assert len(records) == 1
    assert records[0]["retry"] == 1
    assert records[0]["status"] == 429
    assert records[0]["retry_after_seconds"] == 321
    assert records[0]["limiter_signature"] == "domain-signature"


def test_mfa_operation_parser_rejects_unsupported_login_provenance() -> None:
    result = _live_playwright_http_operations(
        _mfa_row(operation="email-mfa-enabled-login")
    )
    assert result["records"] == []
    assert result["completeness"] == "incomplete"


@pytest.mark.parametrize(
    "operation",
    [
        "email-mfa-verification-start",
        "email-mfa-verification-accept",
        "email-mfa-enable-start",
        "email-mfa-enable-accept",
        "email-mfa-enabled-login",
        "email-mfa-login-accept",
    ],
)
def test_mfa_operation_parser_accepts_each_successful_operation(operation: str) -> None:
    result = _live_playwright_http_operations(
        _mfa_row(
            operation=operation,
            status=200,
            retry_after_seconds="none",
            limiter_signature="not-applicable",
        )
    )
    assert len(result["records"]) == 1
    assert result["records"][0]["operation"] == operation
    assert result["records"][0]["retry_after_seconds"] is None


@pytest.mark.parametrize(
    "changes",
    [
        {"project": "private-value"},
        {"source": "private-value"},
        {"line": 379},
        {"retry": 2},
        {"ordinal": 17},
        {"phase": "setup"},
        {"operation": "private-value"},
        {"status": 600},
        {"elapsed_ms": 120_001},
        {"saturated": 1},
        {"responses": 0},
        {"retry_after_seconds": 601},
        {"retry_after_seconds": 0},
        {"retry_after_seconds": "01"},
        {"retry_after_seconds": "none"},
        {"limiter_signature": "private-value"},
        {"limiter_signature": "not-applicable"},
        {"status": 200},
    ],
)
def test_mfa_operation_parser_rejects_malformed_or_inconsistent_values(
    changes: dict[str, object],
) -> None:
    result = _live_playwright_http_operations(_mfa_row(**changes))
    assert result["records"] == []
    assert result["completeness"] == "incomplete"
    assert "private-value" not in str(result)


def test_mfa_operation_parser_rejects_private_suffixes_and_partial_lines() -> None:
    row = _mfa_row()
    for candidate in (row[:-1], row[:-1] + " private-value\n", row[:-1] + "\x00\n"):
        result = _live_playwright_http_operations(candidate)
        assert result["records"] == []
        assert result["completeness"] == "incomplete"
        assert "private-value" not in str(result)


def test_mfa_operation_parser_keeps_v2_compatible_and_shares_attempt_ordinals() -> None:
    legacy = (
        "UE_LIVE_HTTP_OPERATION_V2 project=mobile "
        "source=email-otp-mfa-login.live.spec.ts line=378 retry=1 ordinal=1 "
        "phase=setup operation=auth-login outcome=response status=200 elapsed_ms=4 "
        "saturated=0 requests=1 responses=1\n"
    )
    mfa = _mfa_row(ordinal=2)
    result = _live_playwright_http_operations(legacy + mfa + mfa)
    assert len(result["records"]) == 2
    assert "retry_after_seconds" not in result["records"][0]
    assert result["records"][1]["retry_after_seconds"] == 321
    assert result["correlation"] == "unambiguous"

    collision = _live_playwright_http_operations(legacy + _mfa_row())
    assert len(collision["records"]) == 1
    assert collision["correlation"] == "ambiguous"
    assert collision["completeness"] == "incomplete"


def test_mfa_operation_parser_preserves_bounds_and_ambiguity_signals() -> None:
    no_response = _mfa_row(
        outcome="no-response",
        status="none",
        responses=0,
        retry_after_seconds="none",
        limiter_signature="not-applicable",
    )
    assert len(_live_playwright_http_operations(no_response)["records"]) == 1
    assert (
        len(
            _live_playwright_http_operations(_mfa_row(retry_after_seconds=600))[
                "records"
            ]
        )
        == 1
    )
    assert (
        _live_playwright_http_operations(_mfa_row(requests="many"))["correlation"]
        == "ambiguous"
    )
    rows = "".join(_mfa_row(ordinal=ordinal) for ordinal in range(1, 17))
    result = _live_playwright_http_operations(
        rows + _mfa_row(ordinal=1, retry_after_seconds=320)
    )
    assert len(result["records"]) == 16
    assert result["correlation"] == "ambiguous"
