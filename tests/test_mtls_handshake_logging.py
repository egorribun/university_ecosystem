"""Finite server proof events preserve public nonce bits after normal redaction."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest

from app.core.logging import _handshake_diagnostic_event, _redact_pii

ROOT = Path(__file__).resolve().parents[1]


def event(nonce: str) -> dict[str, str]:
    return {
        "logger": "app.server.spiffe_transport",
        "message": "internal_mtls_handshake_rejected",
        "reason": "PEER_DID_NOT_RETURN_A_CERTIFICATE",
        "probe_id": str(UUID(hex=nonce)),
    }


@pytest.mark.parametrize("nonce", ["0" * 32, "f" * 32, "9161234567" + "a" * 22])
@pytest.mark.parametrize("json_output", [False, True])
def test_actual_renderer_keeps_nonce_and_drops_inherited_context(nonce, json_output):
    code = """
import sys, types
from uuid import UUID
sys.modules["app.core.config"] = types.SimpleNamespace(settings=types.SimpleNamespace(environment="development", service_name="backend"))
from app.core.logging import configure_logging, bind_context
from app.server.spiffe_transport import HandshakeDiagnostics
import ssl
configure_logging(json_output=sys.argv[2] == "True")
bind_context(email="private@example.test", token="private-token", exception="private-exception")
observer = HandshakeDiagnostics()
connection = observer.sslobject_class.__new__(observer.sslobject_class)
observer.client_hello(connection, "aud373-" + sys.argv[1] + ".invalid")
error = ssl.SSLError("private TLS details")
error.reason = "PEER_DID_NOT_RETURN_A_CERTIFICATE"
observer.record(connection, error)
"""
    environment = {
        key: os.environ[key]
        for key in ("PATH", "SYSTEMROOT", "WINDIR")
        if key in os.environ
    }
    environment["PYTHONPATH"] = str(ROOT)
    result = subprocess.run(  # noqa: S603  # Fixed interpreter and isolated diagnostic script.
        [sys.executable, "-c", code, nonce, str(json_output)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    payload = json.loads(result.stdout)
    assert payload == {
        "event": "internal_mtls_handshake_rejected",
        "logger": "app.server.spiffe_transport",
        "probe_id": str(UUID(hex=nonce)),
        "reason": "PEER_DID_NOT_RETURN_A_CERTIFICATE",
    }
    assert UUID(payload["probe_id"]).hex == nonce
    assert "private" not in result.stdout


@pytest.mark.parametrize(
    "key,value",
    [
        ("logger", "other"),
        ("message", "other"),
        ("reason", "OTHER"),
        ("probe_id", "f" * 32),
        ("probe_id", "[REDACTED]"),
        ("probe_id", "-".join("A" * n for n in (8, 4, 4, 4, 12))),
        ("probe_id", None),
        ("probe_id", "x" * 10000),
    ],
)
def test_noncanonical_or_wrong_producer_is_not_a_proof_record(key, value):
    payload = event("0" * 32)
    payload[key] = value
    assert _handshake_diagnostic_event(payload) is None


def test_phone_redaction_is_not_bypassed_for_compact_nonce():
    nonce = "9161234567" + "a" * 22
    payload = event(nonce)
    payload["probe_id"] = nonce
    redacted = _redact_pii(None, "warning", payload)
    assert redacted["probe_id"] != nonce
    assert _handshake_diagnostic_event(redacted) is None


@pytest.mark.parametrize("json_output", [False, True])
@pytest.mark.parametrize("nonce", ["0" * 32, "9161234567" + "a" * 22])
def test_configured_renderer_projects_only_canonical_handshake_fields(
    json_output, nonce
):
    import logging
    from unittest.mock import patch

    from app.core import logging as logging_module

    previous_logger_class = logging.getLoggerClass()
    handlers = [
        (handler, handler.formatter) for handler in logging.getLogger().handlers
    ]
    try:
        with (
            patch.object(logging_module, "_configured", False),
            patch("structlog.configure"),
            patch("logging.basicConfig"),
            patch.object(
                logging_module,
                "_RedactingProcessorFormatter",
                wraps=logging_module._RedactingProcessorFormatter,
            ) as formatter,
        ):
            logging_module.configure_logging(json_output=json_output)
        render = formatter.call_args.kwargs["processor"]
        payload = event(nonce)
        payload.update(
            email="private@example.test",
            token="private-token",
            exception="private-exception",
        )
        redacted = _redact_pii(None, "warning", payload)
        rendered = render(None, "warning", redacted)
        assert json.loads(rendered) == {
            "event": "internal_mtls_handshake_rejected",
            "logger": "app.server.spiffe_transport",
            "probe_id": str(UUID(hex=nonce)),
            "reason": "PEER_DID_NOT_RETURN_A_CERTIFICATE",
        }
        assert "private" not in rendered
    finally:
        logging.setLoggerClass(previous_logger_class)
        for handler, previous_formatter in handlers:
            handler.setFormatter(previous_formatter)
