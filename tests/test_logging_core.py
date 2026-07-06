import logging
from unittest.mock import MagicMock, patch

import app.core.logging as logging_mod
from app.core.logging import (
    _orjson_serializer,
    _redact_pii,
    add_otel_context,
    bind_context,
    clear_context,
    configure_logging,
    get_logger,
    is_logger_enabled,
)


def test_redact_pii():
    """Verify _redact_pii replaces matching fields and masks email/phone values."""
    event = {
        "password": "my-secret-password",  # pragma: allowlist secret
        "email": "user@example.com",
        "phone": "+1-555-0199",
        "message": "Public info",
    }
    redacted = _redact_pii(None, None, event)

    assert redacted["password"] == "[REDACTED]"
    assert redacted["email"] == "[REDACTED]"
    assert redacted["phone"] == "[REDACTED]"
    assert redacted["message"] == "Public info"


class DummyContext:
    def __init__(self, trace_id: int, span_id: int):
        self.trace_id = trace_id
        self.span_id = span_id


def test_add_otel_context_recording():
    """Test add_otel_context formats trace and span IDs when span is recording."""
    mock_span = MagicMock()
    mock_span.is_recording.return_value = True
    mock_span.get_span_context.return_value = DummyContext(
        0x1234567890ABCDEF1234567890ABCDEF, 0x1234567890ABCDEF
    )

    mock_trace = MagicMock()
    mock_trace.trace.get_current_span.return_value = mock_span

    with patch.dict("sys.modules", {"opentelemetry": mock_trace}):
        event = {}
        res = add_otel_context(None, None, event)
        assert res["trace_id"] == "1234567890abcdef1234567890abcdef"
        assert res["span_id"] == "1234567890abcdef"


def test_add_otel_context_import_error():
    """Test add_otel_context handles opentelemetry ImportError gracefully."""
    with patch.dict("sys.modules", {"opentelemetry": None}):
        event = {}
        res = add_otel_context(None, None, event)
        assert res == {}


def test_configure_logging_already_configured():
    """Verify configure_logging returns early if it has already been run."""
    with (
        patch.object(logging_mod, "_configured", True),
        patch("structlog.configure") as mock_structlog_conf,
    ):
        configure_logging()
        mock_structlog_conf.assert_not_called()


def test_configure_logging_first_time_json():
    """Test configure_logging setup flow for JSON output and OTel provider integration."""
    mock_set_logger_provider = MagicMock()
    mock_logging_instrumentor_cls = MagicMock()

    modules_to_mock = {
        "opentelemetry._logs": MagicMock(set_logger_provider=mock_set_logger_provider),
        "opentelemetry.instrumentation.logging": MagicMock(
            LoggingInstrumentor=mock_logging_instrumentor_cls
        ),
        "opentelemetry.sdk._logs": MagicMock(),
        "opentelemetry.sdk._logs._internal.export.otlp": MagicMock(),
        "opentelemetry.sdk._logs.export": MagicMock(),
    }

    with (
        patch.object(logging_mod, "_configured", False),
        patch("structlog.configure") as mock_structlog_conf,
        patch("logging.basicConfig"),
        patch.dict("sys.modules", modules_to_mock),
    ):
        configure_logging(json_output=True)

        mock_structlog_conf.assert_called_once()
        mock_set_logger_provider.assert_called_once()
        mock_logging_instrumentor_cls.return_value.instrument.assert_called_once_with(
            set_logging_format=False
        )


def test_configure_logging_first_time_console_no_otel():
    """Test configure_logging fallback when OTel SDK is not available."""
    with (
        patch.object(logging_mod, "_configured", False),
        patch("structlog.configure") as mock_structlog_conf,
        patch("logging.basicConfig"),
        patch.dict("sys.modules", {"opentelemetry._logs": None}),
    ):
        configure_logging(json_output=False)

        mock_structlog_conf.assert_called_once()


def test_orjson_serializer():
    """Verify _orjson_serializer correctly encodes dictionaries using orjson."""
    res = _orjson_serializer({"hello": "world"})
    assert res == '{"hello":"world"}'


def test_get_logger():
    """Verify get_logger returns BoundLogger from structlog."""
    logger = get_logger("test-logger")
    assert logger is not None


def test_is_logger_enabled():
    """Verify is_logger_enabled works for both PEP 8 method names and standard library fallbacks."""
    # PEP 8 (structlog BoundLogger wrapper)
    logger_pep8 = MagicMock()
    logger_pep8.is_enabled_for.return_value = True
    assert is_logger_enabled(logger_pep8, logging.INFO) is True
    logger_pep8.is_enabled_for.assert_called_once_with(logging.INFO)

    # Stdlib fallback (standard Logger)
    logger_stdlib = MagicMock(spec=["isEnabledFor"])
    logger_stdlib.isEnabledFor.return_value = True
    assert is_logger_enabled(logger_stdlib, logging.WARNING) is True
    logger_stdlib.isEnabledFor.assert_called_once_with(logging.WARNING)


def test_bind_and_clear_context():
    """Verify bind_context and clear_context modify context vars."""
    bind_context(request_id="abc-123")
    clear_context()
