"""The locked Caddy build preserves upstream dependency security floors."""

import re
from pathlib import Path

import pytest

_CADDY_BUILD = Path(__file__).resolve().parents[1] / "services/caddy"

# Requirements from github.com/caddyserver/caddy/v2 v2.11.7/go.mod.
# Keep these release-scoped values synchronized when the pinned Caddy release changes.
_UPSTREAM_REQUIREMENTS = {
    "github.com/go-jose/go-jose/v4": "v4.1.5",
    "golang.org/x/net": "v0.59.0",
    "golang.org/x/text": "v0.42.0",
    "google.golang.org/grpc": "v1.83.2",
}

# Treat the selected dependency versions as minimum security floors.
# Future higher replacements remain compatible with these floors.
_SELECTED_VERSION_FLOORS = {
    "github.com/go-jose/go-jose/v4": "v4.1.6",
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


def _go_mod_replacements() -> dict[str, str]:
    """Return the locked replacement targets from the committed build module."""
    go_mod = (_CADDY_BUILD / "go.mod").read_text(encoding="utf-8")
    block = re.search(r"^replace \(\n(.*?)^\)", go_mod, re.M | re.S)
    assert block is not None, "the Caddy build module must replace in one block"
    return {
        module: version
        for module, version in re.findall(
            r"^\s*(\S+) => \S+ (v\S+)\s*$", block.group(1), re.M
        )
    }


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
    replacement_version = _go_mod_replacements()[module]
    assert _version_tuple(replacement_version) >= _version_tuple(upstream_version)
    assert _version_tuple(replacement_version) >= _version_tuple(selected_version)
    # A replacement pins the graph; it must never be compiled in as a plugin.
    main_package = (_CADDY_BUILD / "main.go").read_text(encoding="utf-8")
    assert f'"{module}' not in main_package


@pytest.mark.parametrize("module", _NO_REPLACEMENT_MODULES)
def test_caddy_does_not_override_upstream_crypto_or_otel_versions(
    module: str,
) -> None:
    assert module not in _go_mod_replacements()
