from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest

_MODULE_PATH = Path(__file__).parents[1] / "app" / "api" / "internal" / "csp_report.py"
_SPEC = importlib.util.spec_from_file_location(
    "app.api.internal.csp_report", _MODULE_PATH
)
assert _SPEC is not None and _SPEC.loader is not None
csp_report = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = csp_report
_SPEC.loader.exec_module(csp_report)


class _Request:
    def __init__(self, chunks: list[bytes], headers: dict[str, str] | None = None):
        self._chunks = chunks
        self.headers = headers or {}

    async def stream(self):
        for chunk in self._chunks:
            yield chunk


class _BrokenRequest(_Request):
    async def stream(self):
        raise OSError("stream is unavailable")
        yield b""


def test_truncate_and_body_limit_helpers():
    assert csp_report._truncate(None) is None
    assert csp_report._truncate(123) == "123"
    assert csp_report._truncate("abcdef", limit=3) == "abc"


@pytest.mark.asyncio
async def test_read_body_with_invalid_header_and_empty_chunks():
    request = _Request([b"", b"hello"], {"content-length": "not-an-int"})
    assert await csp_report._read_body_with_limit(request, 10) == b"hello"

    within_limit = _Request([b"hello"], {"content-length": "5"})
    assert await csp_report._read_body_with_limit(within_limit, 10) == b"hello"

    too_long = _Request([b"x"], {"content-length": "11"})
    assert await csp_report._read_body_with_limit(too_long, 10) is None

    streamed_too_long = _Request([b"123", b"456"])
    assert await csp_report._read_body_with_limit(streamed_too_long, 5) is None


@pytest.mark.asyncio
async def test_receive_csp_report_size_and_empty_paths():
    with patch.object(csp_report, "record_csp_report") as record:
        result = await csp_report.receive_csp_report(
            _Request(
                [b"x"], {"content-length": str(csp_report.MAX_CSP_REPORT_BYTES + 1)}
            )
        )
        assert result.status_code == 413
        record.assert_called_once_with("too_large")

    with patch.object(csp_report, "record_csp_report") as record:
        result = await csp_report.receive_csp_report(_Request([]))
        assert result.status_code == 204
        record.assert_called_once_with("empty")


@pytest.mark.asyncio
async def test_receive_csp_report_invalid_json():
    with patch.object(csp_report, "record_csp_report") as record:
        result = await csp_report.receive_csp_report(_Request([b"not-json"]))
    assert result.status_code == 400
    record.assert_called_once_with("invalid_json")


@pytest.mark.asyncio
async def test_receive_csp_report_accepts_wrapped_and_flat_payloads():
    wrapped = (
        b'{"csp-report":{"document-uri":"https://example.test","script-sample":"x"}}'
    )
    flat = b'{"document-uri":"https://example.test","blocked-uri":"data:"}'
    with (
        patch.object(csp_report, "record_csp_report") as record,
        patch.object(csp_report.logger, "warning") as warning,
    ):
        assert (
            await csp_report.receive_csp_report(_Request([wrapped]))
        ).status_code == 204
        assert (
            await csp_report.receive_csp_report(_Request([flat]))
        ).status_code == 204
    assert [call.args[0] for call in record.call_args_list] == ["accepted", "accepted"]
    assert warning.call_count == 2


@pytest.mark.asyncio
async def test_receive_csp_report_logs_only_sanitized_document_uri():
    marker = f"synthetic-{uuid4().hex}"
    document_uris = [
        f"https://portal.example.edu/app/reset-password/{marker}?token={marker}#{marker}",
        f"https://user:{marker}@portal.example.edu/settings?campaign={marker}#section",
        f"https://portal.example.edu:invalid/reset-password?token={marker}",
        f"https://portal.example.edu/reset-password//{marker}",
        f"https://portal.example.edu/reset-password/%2F/{marker}",
        f"https://portal.example.edu/reset-password%2/{marker}",
        "https://portal.example.edu/assets/app%20bundle.js",
    ]
    with (
        patch.object(csp_report, "record_csp_report"),
        patch.object(csp_report.logger, "warning") as warning,
    ):
        for document_uri in document_uris:
            body = json.dumps({"csp-report": {"document-uri": document_uri}}).encode()
            result = await csp_report.receive_csp_report(_Request([body]))
            assert result.status_code == 204

    logged_uris = [
        call.kwargs["extra"]["document_uri"] for call in warning.call_args_list
    ]
    assert logged_uris == [
        "https://portal.example.edu/app/reset-password/[REDACTED]",
        "https://portal.example.edu/settings",
        "[REDACTED]",
        "https://portal.example.edu/reset-password/[REDACTED]",
        "https://portal.example.edu/reset-password/[REDACTED]",
        "[REDACTED]",
        "https://portal.example.edu/assets/app%20bundle.js",
    ]
    assert marker not in repr(warning.call_args_list)


async def test_receive_csp_report_handles_unexpected_shapes_and_stream_errors():
    with patch.object(csp_report, "record_csp_report") as record:
        result = await csp_report.receive_csp_report(_Request([b"[]"]))
        assert result.status_code == 204
        record.assert_called_once_with("error")

    with patch.object(csp_report, "record_csp_report") as record:
        result = await csp_report.receive_csp_report(_BrokenRequest([]))
        assert result.status_code == 204
        record.assert_called_once_with("error")


@pytest.mark.asyncio
async def test_receive_csp_report_sanitizes_uri_edge_cases() -> None:
    cases = [
        ("document-uri", "document_uri", 123, "[REDACTED]"),
        ("blocked-uri", "blocked_uri", "inline", "inline"),
        (
            "document-uri",
            "document_uri",
            "https://portal.example.edu/reset-password",
            "https://portal.example.edu/reset-password",
        ),
        (
            "source-file",
            "source_file",
            "ftp://portal.example.edu/script.js",
            "[REDACTED]",
        ),
        (
            "document-uri",
            "document_uri",
            "https://bad host.example/path",
            "[REDACTED]",
        ),
        (
            "document-uri",
            "document_uri",
            "https://portal.example.edu:8443/assets/app.js",
            "https://portal.example.edu:8443/assets/app.js",
        ),
    ]
    with (
        patch.object(csp_report, "record_csp_report") as record,
        patch.object(csp_report.logger, "warning") as warning,
    ):
        for input_field, _log_field, uri, _expected in cases:
            body = json.dumps({"csp-report": {input_field: uri}}).encode()
            result = await csp_report.receive_csp_report(_Request([body]))
            assert result.status_code == 204

    logged = [
        call.kwargs["extra"][log_field]
        for call, (_input_field, log_field, _uri, _expected) in zip(
            warning.call_args_list, cases, strict=True
        )
    ]
    assert logged == [expected for _input_field, _log_field, _uri, expected in cases]
    assert [call.args[0] for call in record.call_args_list] == ["accepted"] * len(cases)
