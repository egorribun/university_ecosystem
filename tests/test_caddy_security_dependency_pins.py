"""The custom Caddy build preserves upstream dependency security floors."""

import re
from pathlib import Path

import pytest

# Direct requirements from github.com/caddyserver/caddy/v2 v2.11.7/go.mod.
# Keep these release-scoped values synchronized when the pinned Caddy release changes.
_UPSTREAM_REQUIREMENTS = {
    "golang.org/x/net": "v0.59.0",
    "golang.org/x/text": "v0.42.0",
    "google.golang.org/grpc": "v1.83.2",
}

# Treat the selected x/net, text, and grpc versions as minimum floors.
# Future higher replacements remain compatible with these floors.
_SELECTED_VERSION_FLOORS = {
    "golang.org/x/net": "v0.60.0",
    "golang.org/x/text": "v0.42.0",
    "google.golang.org/grpc": "v1.83.2",
}

# These were the old lower replacements; Caddy v2.11.7 must use its own
# upstream x/crypto and OpenTelemetry requirements instead.
_NO_REPLACEMENT_MODULES = (
    "golang.org/x/crypto",
    "go.opentelemetry.io/otel/sdk",
    "go.opentelemetry.io/otel/sdk/log",
    "go.opentelemetry.io/otel/exporters/otlp/otlplog/otlploggrpc",
    "go.opentelemetry.io/otel/exporters/otlp/otlplog/otlploghttp",
    "go.opentelemetry.io/otel/exporters/stdout/stdoutlog",
    "go.opentelemetry.io/otel/exporters/otlp/otlptrace",
    "go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc",
    "go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp",
)


def _version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.removeprefix("v").split("."))


@pytest.mark.parametrize(
    ("module", "upstream_version", "selected_version"),
    [
        (module, upstream_version, _SELECTED_VERSION_FLOORS[module])
        for module, upstream_version in _UPSTREAM_REQUIREMENTS.items()
    ],
)
def test_caddy_replacements_preserve_upstream_dependency_floors(
    module: str, upstream_version: str, selected_version: str
) -> None:
    dockerfile = (
        Path(__file__).resolve().parents[1] / "services/caddy/Dockerfile"
    ).read_text(encoding="utf-8")
    replacements = dict(re.findall(r"--replace ([^=\s]+)=([^\s\\]+)", dockerfile))

    replacement_version = replacements[module].rsplit("@", maxsplit=1)[1]
    assert _version_tuple(replacement_version) >= _version_tuple(upstream_version)
    assert _version_tuple(replacement_version) >= _version_tuple(selected_version)
    assert f"--with {module}@" not in dockerfile


@pytest.mark.parametrize("module", _NO_REPLACEMENT_MODULES)
def test_caddy_does_not_override_upstream_crypto_or_otel_versions(
    module: str,
) -> None:
    dockerfile = (
        Path(__file__).resolve().parents[1] / "services/caddy/Dockerfile"
    ).read_text(encoding="utf-8")
    replacements = dict(re.findall(r"--replace ([^=\s]+)=([^\s\\]+)", dockerfile))

    assert module not in replacements
