"""Production regressions for security-sensitive Caddy routing invariants.

Caddy `handle /path/*` blocks are MUTUALLY EXCLUSIVE and matched in
DECLARATION ORDER (per Caddy 2.x docs). Three exception routes MUST appear
BEFORE the general `handle /ws/*` block:

1. `handle /ws/ticket { reverse_proxy gateway:8080 }`.
   /ws/ticket is an HTTP POST endpoint on backend (issues OTT for
   WS upgrade per RZ-W14-01 + app/api/ws/ticket.py), NOT a WS upgrade.
   ws-hub Go service has no /ticket route. Without this exception,
   POST /ws/ticket → ws-hub:8081 → 404 → chat WS flow breaks.

2. `handle /ws/chat* { rewrite * /ws; reverse_proxy ws-hub:8081 }`.
   Frontend constructs `/ws/chat?ticket=<hex>`
   but ws-hub Go service serves WS at plain `/ws` (Go net/http
   Handle("/ws", ...) matches exact only — no trailing slash).
   Rewrite translates the frontend URL to ws-hub's canonical path.

3. `handle /.well-known/* { reverse_proxy backend:8000 }`.
   This keeps the JWKS endpoint (/.well-known/jwks.json) reachable from
   external clients per RFC 8615.

Together these tests protect OTT acquisition, chat WebSocket upgrades, and
public JWKS discovery whenever Caddy route ordering changes.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CADDYFILE = REPO_ROOT / "infrastructure" / "Caddyfile"


def _read_caddyfile() -> str:
    """Read the dev-compose-mounted Caddyfile. Returns full text content."""
    assert CADDYFILE.exists(), f"Expected Caddyfile at {CADDYFILE}"
    return CADDYFILE.read_text(encoding="utf-8")


def _line_of(content: str, pattern: str) -> int:
    """Return the 1-indexed line number of the FIRST match of pattern.
    Pattern is a regex; raises AssertionError if no match found."""
    rx = re.compile(pattern)
    for idx, line in enumerate(content.splitlines(), start=1):
        if rx.search(line):
            return idx
    raise AssertionError(f"Pattern {pattern!r} not found in Caddyfile")


def test_ws_ticket_handle_exists_and_routes_to_gateway() -> None:
    """W173 SW1 Fix A: handle /ws/ticket → gateway:8080 must exist."""
    content = _read_caddyfile()
    assert re.search(
        r"handle\s+/ws/ticket\s*\{[^}]*reverse_proxy\s+gateway:8080",
        content,
        re.DOTALL,
    ), "W173 SW1 Fix A regression: /ws/ticket must route to gateway:8080"


def test_ws_chat_handle_exists_with_rewrite_to_ws_hub() -> None:
    """W173 polish-v1 Fix A: handle /ws/chat* { rewrite * /ws; reverse_proxy ws-hub:8081 }."""
    content = _read_caddyfile()
    # Use DOTALL so . matches newlines inside the handle block
    assert re.search(
        r"handle\s+/ws/chat\*\s*\{[^}]*rewrite\s+\*\s+/ws[^}]*reverse_proxy\s+ws-hub:8081",
        content,
        re.DOTALL,
    ), (
        "W173 polish-v1 Fix A regression: /ws/chat* must rewrite to /ws + proxy to ws-hub:8081"
    )


def test_well_known_handle_exists_and_routes_to_backend() -> None:
    """W173 polish-v1 Fix C: handle /.well-known/* → backend:8000."""
    content = _read_caddyfile()
    assert re.search(
        r"handle\s+/\.well-known/\*\s*\{[^}]*reverse_proxy\s+backend:8000",
        content,
        re.DOTALL,
    ), (
        "W173 polish-v1 Fix C regression: /.well-known/* must route to backend:8000 (JWKS)"
    )


def test_general_ws_block_routes_to_ws_hub() -> None:
    """Sanity: the general /ws/* block (after exceptions) routes to ws-hub:8081."""
    content = _read_caddyfile()
    assert re.search(
        r"handle\s+/ws/\*\s*\{[^}]*reverse_proxy\s+ws-hub:8081",
        content,
        re.DOTALL,
    ), "General /ws/* must route to ws-hub:8081"


def test_s3_proxy_allows_only_public_media_prefixes() -> None:
    """Only public media prefixes reach S3; unknown/private keys fail closed.

    Caddy sorts top-level ``handle`` before ``respond`` regardless of source
    order, so the deny must be inside the ordered storage route.
    """
    for relative_path in ("infrastructure/Caddyfile", "services/caddy/Caddyfile"):
        content = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert re.search(
            r"handle\s+/storage/\*\s*\{\s*"
            r"@non_public_storage\s*\{\s*not\s*\{\s*"
            r"method\s+GET\s+HEAD\s+path\s+"
            r"/storage/uploads/avatars/\*\s+/storage/uploads/covers/\*\s+"
            r"/storage/uploads/news_images/\*\s+"
            r"/storage/uploads/story_covers/\*\s+"
            r"/storage/uploads/tmp/event_images/\*\s*\}\s*\}\s*"
            r"route\s*\{\s*respond\s+@non_public_storage\s+404\s*"
            r"uri\s+strip_prefix\s+/storage\s*"
            r"reverse_proxy\s+minio:9000\s*\}\s*\}",
            content,
        ), f"Public S3 allowlist must precede proxy in {relative_path}"


def test_websocket_ticket_is_redacted_from_access_logs() -> None:
    """One-time WS tickets must never be persisted as raw bearer credentials."""
    for relative_path in ("infrastructure/Caddyfile", "services/caddy/Caddyfile"):
        content = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert re.search(
            r"format\s+filter\s*\{[^}]*request>uri\s+query\s*\{[^}]*replace\s+ticket\s+REDACTED",
            content,
            re.DOTALL,
        ), f"Caddy access-log URI must redact ticket query values in {relative_path}"


def test_ws_ticket_precedes_general_ws_block() -> None:
    """W173 SW1 critical invariant: /ws/ticket exception MUST appear BEFORE /ws/*.

    Caddy matches handle blocks in declaration order; if /ws/* came
    first, /ws/ticket would never match (routed to ws-hub → 404).
    """
    content = _read_caddyfile()
    ticket_line = _line_of(content, r"handle\s+/ws/ticket")
    general_ws_line = _line_of(content, r"handle\s+/ws/\*")
    assert ticket_line < general_ws_line, (
        f"W173 SW1 invariant violated: /ws/ticket (line {ticket_line}) must "
        f"appear BEFORE /ws/* (line {general_ws_line})"
    )


def test_ws_chat_precedes_general_ws_block() -> None:
    """W173 polish-v1 invariant: /ws/chat* must appear BEFORE /ws/*."""
    content = _read_caddyfile()
    chat_line = _line_of(content, r"handle\s+/ws/chat\*")
    general_ws_line = _line_of(content, r"handle\s+/ws/\*")
    assert chat_line < general_ws_line, (
        f"W173 polish-v1 invariant violated: /ws/chat* (line {chat_line}) must "
        f"appear BEFORE /ws/* (line {general_ws_line})"
    )
