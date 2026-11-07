"""Public route and manifest isolation for the ws-hub metrics endpoint (AUD-438).

ws-hub serves an unauthenticated Prometheus endpoint. The Go tests prove the
public WebSocket mux does not register it and that the metrics listener is a
separate socket. These checks prove the deployment surfaces do not expose that
listener or path: both Caddy edges, the chart ingress and Gateway API routes,
the chart metrics port, and the compose port publications.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EDGE_CADDYFILES = (
    REPOSITORY_ROOT / "services" / "caddy" / "Caddyfile",
    REPOSITORY_ROOT / "infrastructure" / "Caddyfile",
)
CHART_VALUES = REPOSITORY_ROOT / "charts" / "university-ecosystem" / "values.yaml"
CHART_TEMPLATES = REPOSITORY_ROOT / "charts" / "university-ecosystem" / "templates"
COMPOSE_FILES = tuple(sorted(REPOSITORY_ROOT.glob("docker-compose*.yml")))
WS_HUB_METRICS_PORT = 9108
WS_HUB_PUBLIC_PORT = 8081


def _uncommented_lines(path: Path) -> list[str]:
    lines: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if stripped and not stripped.startswith("#"):
            lines.append(stripped)
    return lines


def _ingress_paths(values: dict) -> list[tuple[str, str, str]]:
    """Return (host-scoped path, pathType, service) for every chart ingress rule."""
    rules: list[tuple[str, str, str]] = []
    for host in values["ingress"]["hosts"]:
        for path in host["paths"]:
            rules.append((path["path"], path["pathType"], path["service"]))
    return rules


def _gateway_api_paths(values: dict) -> list[tuple[str, str, str]]:
    rules: list[tuple[str, str, str]] = []
    gateway_api = values.get("gatewayApi", {})
    for host in gateway_api.get("hosts", []):
        for path in host.get("paths", []):
            rules.append((path["path"], path["pathType"], path["service"]))
    return rules


def test_edge_caddyfiles_never_name_the_metrics_path_or_port() -> None:
    for caddyfile in EDGE_CADDYFILES:
        for line in _uncommented_lines(caddyfile):
            assert "/metrics" not in line, f"{caddyfile} routes metrics: {line}"
            assert str(WS_HUB_METRICS_PORT) not in line, (
                f"{caddyfile} references the ws-hub metrics port: {line}"
            )


def test_edge_caddyfiles_send_ws_hub_only_the_websocket_prefix() -> None:
    """Every ws-hub upstream sits under a /ws matcher, never a catch-all handle."""
    for caddyfile in EDGE_CADDYFILES:
        lines = _uncommented_lines(caddyfile)
        upstream_lines = [
            index for index, line in enumerate(lines) if "reverse_proxy ws-hub:" in line
        ]
        assert upstream_lines, f"{caddyfile} must still route the WebSocket tunnel"
        for index in upstream_lines:
            matcher = _enclosing_handle(lines, index)
            assert matcher is not None and matcher.startswith("/ws"), (
                f"{caddyfile} sends ws-hub traffic from a non-/ws matcher: {matcher!r}"
            )
            assert f"ws-hub:{WS_HUB_PUBLIC_PORT}" in lines[index]


def _enclosing_handle(lines: list[str], upstream_index: int) -> str | None:
    """Return the path matcher of the `handle`/`handle_path` block holding a line.

    Caddy blocks nest, so scanning upward counts closing braces as entering a
    nested block and opening braces as leaving one. The first enclosing block
    that opens with a handle directive supplies the matcher.
    """
    depth = 0
    for index in range(upstream_index - 1, -1, -1):
        line = lines[index]
        depth += line.count("}") - line.count("{")
        if depth < 0:
            match = re.match(r"^handle(?:_path)?(?:\s+(\S+))?\s*\{", line)
            if match is not None:
                return match.group(1) or ""
            depth = 0
    return None


def test_chart_ingress_and_gateway_api_never_route_metrics() -> None:
    values = yaml.safe_load(CHART_VALUES.read_text(encoding="utf-8"))
    rules = _ingress_paths(values) + _gateway_api_paths(values)
    assert rules, "the chart must declare its public routes"
    for path, path_type, service in rules:
        assert "metrics" not in path, f"chart route exposes metrics: {path}"
        if service == "ws-hub":
            assert (path, path_type) == ("/ws/chat", "Exact"), (
                f"ws-hub may be reached only through /ws/chat, not {path} {path_type}"
            )


def test_chart_ingress_and_gateway_api_templates_name_no_metrics_path() -> None:
    """Pod scrape annotations may name /metrics; routing objects may not."""
    for template in ("ingress.yaml", "gateway-api.yaml"):
        content = (CHART_TEMPLATES / template).read_text(encoding="utf-8")
        assert "/metrics" not in content, f"{template} routes the metrics path"


def test_chart_metrics_port_is_separate_from_the_public_websocket_port() -> None:
    values = yaml.safe_load(CHART_VALUES.read_text(encoding="utf-8"))
    ws_hub = values["wsHub"]
    assert ws_hub["service"]["port"] == WS_HUB_PUBLIC_PORT
    assert ws_hub["metrics"]["port"] == WS_HUB_METRICS_PORT
    assert ws_hub["metrics"]["port"] != ws_hub["service"]["port"]


def test_compose_files_never_publish_the_ws_hub_metrics_port() -> None:
    published = re.compile(
        r"^-\s*[\"']?(?:[\d.]+:)?(?:\d+:)?"
        + str(WS_HUB_METRICS_PORT)
        + r"(?::\d+)?[\"']?\s*$"
    )
    for compose in COMPOSE_FILES:
        for line in _uncommented_lines(compose):
            assert not published.match(line), (
                f"{compose.name} publishes the ws-hub metrics port: {line}"
            )
