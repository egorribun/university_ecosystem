"""Emitted-log privacy proof for reset CSP reports."""

from __future__ import annotations

import json
import secrets
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytest_plugins = ("pytester",)


def _run_csp_report_probe(
    reports: list[dict[str, Any]], pytester: pytest.Pytester, *, unsafe: bool
) -> str:
    # Isolate the application's real logging configuration from pytest's handlers.
    # HTTPX's ASGI transport calls the actual report endpoint without a network.
    source = ROOT / "app" / "api" / "internal" / "csp_report.py"
    program = """
import asyncio
import json
import logging
import sys
from pathlib import Path

import httpx
from fastapi import FastAPI

from app.core.logging import configure_logging
configure_logging(level=logging.INFO, json_output=True)
from app.api.internal import csp_report
if Path(csp_report.__file__).resolve() != Path(sys.argv[1]).resolve():
    raise RuntimeError("the CSP report probe imported an unexpected module")

payload = json.load(sys.stdin)
if payload['unsafe']:
    csp_report._sanitize_uri_for_log = lambda value: value
app = FastAPI()
app.add_api_route('/api/v1/csp-report', csp_report.receive_csp_report, methods=['POST'])

async def main():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url='http://backend.test'
    ) as client:
        for report in payload['reports']:
            response = await client.post('/api/v1/csp-report', json={'csp-report': report})
            assert response.status_code == 204

asyncio.run(main())
"""
    # pytester launches the fixed interpreter and program without a shell.
    process = pytester.popen(
        [sys.executable, "-c", program, str(source)],
        stdin=json.dumps({"reports": reports, "unsafe": unsafe}).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=ROOT,
    )
    try:
        stdout, stderr = process.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        raise
    assert process.returncode == 0, "the CSP report probe failed"
    return (stdout + stderr).decode("utf-8", errors="replace")


def _assert_csp_report_emitted_logs_remove_legacy_tokens_from_all_uri_fields(
    pytester: pytest.Pytester,
) -> None:
    # Map each hex digit bijectively to a letter, keeping 96 random bits while
    # avoiding phone-shaped digit runs in the central PII log processor.
    alphabet = str.maketrans("0123456789", "ghijklmnop")
    query_marker = "querymarker" + secrets.token_hex(12).translate(alphabet)
    path_marker = "pathmarker" + secrets.token_hex(12).translate(alphabet)
    reports = [
        {
            "document-uri": f"https://portal.example.test/reset-password?token={query_marker}",
            "blocked-uri": f"https://portal.example.test/reset-password?token={query_marker}",
            "source-file": f"https://portal.example.test/reset-password?token={query_marker}",
            "referrer": f"https://portal.example.test/reset-password?token={query_marker}",
            "violated-directive": "connect-src",
        },
        {
            "document-uri": f"https://portal.example.test/reset-password/{path_marker}",
            "blocked-uri": f"https://portal.example.test/reset-password/{path_marker}",
            "source-file": f"https://portal.example.test/reset-password/{path_marker}",
            "violated-directive": "connect-src",
        },
    ]
    unsafe_log = _run_csp_report_probe(reports, pytester, unsafe=True)
    assert query_marker in unsafe_log and path_marker in unsafe_log

    emitted_log = _run_csp_report_probe(reports, pytester, unsafe=False)
    assert query_marker not in emitted_log and path_marker not in emitted_log
    events = [
        json.loads(line)
        for line in emitted_log.splitlines()
        if line.startswith("{") and '"csp_violation"' in line
    ]
    assert len(events) == 2
    fields = [event["extra"] for event in events]
    for field in ("document_uri", "blocked_uri", "source_file"):
        assert [event[field] for event in fields] == [
            "https://portal.example.test/reset-password",
            "https://portal.example.test/reset-password/[REDACTED]",
        ]


def test_csp_report_emitted_logs_remove_legacy_tokens_from_all_uri_fields(
    pytester: pytest.Pytester,
) -> None:
    # Do not let rewritten assertions or unexpected exceptions print the
    # positive-control markers and captured logs, including under -l.
    failed = False
    try:
        _assert_csp_report_emitted_logs_remove_legacy_tokens_from_all_uri_fields(
            pytester
        )
    except Exception:
        failed = True
    # Report outside the except block so pytest cannot render an exception chain.
    if failed:
        pytest.fail("the CSP emitted-log proof failed", pytrace=False)
