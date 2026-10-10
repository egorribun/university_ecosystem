"""The custom Caddy build is independent of the application Go workspace."""

import re
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("module", "version"),
    [
        ("golang.org/x/crypto", "v0.56.0"),
        ("go.opentelemetry.io/otel/sdk", "v1.45.0"),
        ("go.opentelemetry.io/otel/sdk/log", "v0.21.0"),
        (
            "go.opentelemetry.io/otel/exporters/otlp/otlplog/otlploggrpc",
            "v0.21.0",
        ),
        (
            "go.opentelemetry.io/otel/exporters/otlp/otlplog/otlploghttp",
            "v0.21.0",
        ),
        ("go.opentelemetry.io/otel/exporters/stdout/stdoutlog", "v0.21.0"),
        ("go.opentelemetry.io/otel/exporters/otlp/otlptrace", "v1.45.0"),
        (
            "go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc",
            "v1.45.0",
        ),
        (
            "go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp",
            "v1.45.0",
        ),
    ],
)
def test_caddy_pins_patched_dependencies_in_its_own_build(
    module: str, version: str
) -> None:
    dockerfile = (
        Path(__file__).resolve().parents[1] / "services/caddy/Dockerfile"
    ).read_text(encoding="utf-8")
    replacements = dict(re.findall(r"--replace ([^=\s]+)=([^\s\\]+)", dockerfile))
    assert replacements[module] == f"{module}@{version}"
    assert f"--with {module}@" not in dockerfile
