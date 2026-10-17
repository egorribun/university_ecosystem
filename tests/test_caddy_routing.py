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


def _caddy_uri_filter_blocks(content: str) -> list[list[tuple[str, str]]]:
    """Read configured sequential URI redactors for static contract checks."""
    blocks = re.findall(
        r"request>uri\s+multi_regexp\s*\{(.*?)(?=\n[ \t]*\})",
        content,
        re.DOTALL,
    )
    assert len(blocks) == 2, "Expected separate runtime-error and access URI filters"
    parsed = [
        re.findall(r"^\s*regexp\s+(\S+)\s+(\S+)\s*$", block, re.MULTILINE)
        for block in blocks
    ]
    assert all(len(operations) == 5 for operations in parsed)
    return parsed


def _apply_caddy_uri_filter(operations: list[tuple[str, str]], uri: str) -> str:
    """Apply the RE2-compatible rules as a static config test, not a Caddy proof."""
    result = uri
    for pattern, replacement in operations:
        python_replacement = re.sub(
            r"\$\{(\d+)\}",
            lambda match: rf"\g<{match.group(1)}>",
            replacement,
        )
        result = re.sub(pattern, python_replacement, result)
    return result


def _one_encoded_character(word: str, index: int) -> str:
    char = word[index]
    return f"{word[:index]}%{ord(char):02x}{word[index + 1 :]}"


def test_reset_password_uri_filter_covers_encoded_route_characters_and_separators() -> (
    None
):
    """Configured rules must hide reset tokens across supported URL spellings."""
    from uuid import uuid4

    marker = f"audit-redaction-{uuid4().hex}"
    encoded_routes = [
        _one_encoded_character("reset-password", index)
        for index in range(len("reset-password"))
    ]
    route_paths = [
        f"/reset-password/{marker}",
        f"/app/reset-password/{marker}",
        *(f"/app/{route}/{marker}" for route in encoded_routes),
        f"/app/%2f%72eset-password%2f{marker}",
        f"/app\\reset-password\\{marker}",
        f"/app%5creset-password%5c{marker}",
        f"/app\\reset-password%5c{marker}",
        f"/app%5creset-password\\{marker}",
        f"\\app\\reset-password\\{marker}",
        f"/reset-password//{marker}",
        f"/reset-password/%2F/{marker}",
        f"/reset-password%2/{marker}",
        f"/app/reset-password?token={marker}",
    ]
    for relative_path in ("infrastructure/Caddyfile", "services/caddy/Caddyfile"):
        content = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        for operations in _caddy_uri_filter_blocks(content):
            for uri in route_paths:
                assert marker not in _apply_caddy_uri_filter(operations, uri), (
                    f"Reset marker leaked for {uri!r} in {relative_path}"
                )


def test_query_uri_filter_redacts_each_encoded_credential_key_character() -> None:
    """Configured rules redact known query credentials despite malformed siblings."""
    from uuid import uuid4

    marker = f"audit-redaction-{uuid4().hex}"
    cases: list[tuple[str, str]] = []
    for name in ("token", "ticket", "code", "password"):
        variants = [_one_encoded_character(name, index) for index in range(len(name))]
        variants.append("".join(f"%{ord(char):02x}" for char in name))
        for encoded_name in variants:
            uri = f"/dashboard?tab=calendar&{encoded_name}={marker}&theme=dark&bad=%2"
            expected = f"/dashboard?tab=calendar&{name}=REDACTED&theme=dark&bad=%2"
            cases.append((uri, expected))
    cases.extend(
        (
            (
                f"/ws/chat?token={marker}&token={marker}",
                "/ws/chat?token=REDACTED&token=REDACTED",
            ),
            (
                f"/dashboard?not_token={marker}&tab=calendar",
                f"/dashboard?not_token={marker}&tab=calendar",
            ),
        )
    )
    for relative_path in ("infrastructure/Caddyfile", "services/caddy/Caddyfile"):
        content = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        for operations in _caddy_uri_filter_blocks(content):
            for uri, expected in cases:
                assert _apply_caddy_uri_filter(operations, uri) == expected, (
                    f"Unexpected query redaction for {uri!r} in {relative_path}"
                )


def test_uri_filter_preserves_ordinary_non_reset_diagnostics() -> None:
    """Ordinary navigation URIs and similarly named non-reset routes stay useful."""
    from uuid import uuid4

    marker = f"ordinary-uri-{uuid4().hex}"
    safe_uris = (
        f"/dashboard?tab=events&marker={marker}",
        f"/reset-password-help/{marker}?tab=events",
    )
    for relative_path in ("infrastructure/Caddyfile", "services/caddy/Caddyfile"):
        content = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        for operations in _caddy_uri_filter_blocks(content):
            for uri in safe_uris:
                assert _apply_caddy_uri_filter(operations, uri) == uri


def test_tls_edge_sets_the_shared_browser_security_headers() -> None:
    """The public TLS edge must protect frontend SSR and proxied responses."""
    content = (REPO_ROOT / "services" / "caddy" / "Caddyfile").read_text(
        encoding="utf-8"
    )
    _global_options, separator, site_config = content.partition("\n}\n")
    assert separator, "Expected the TLS site after Caddy's global options"

    required_headers = (
        r"^\s*header\s+X-Content-Type-Options\s+nosniff\s*$",
        r"^\s*header\s+X-Frame-Options\s+DENY\s*$",
        r'^\s*header\s+X-XSS-Protection\s+"0"\s*$',
        r"^\s*header\s+Referrer-Policy\s+no-referrer\s*$",
    )
    for pattern in required_headers:
        assert re.search(pattern, site_config, re.MULTILINE), (
            f"TLS Caddy site is missing required browser security header matching {pattern!r}"
        )

    for relative_path in ("services/caddy/Caddyfile", "infrastructure/Caddyfile"):
        edge_config = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert re.search(
            r"^\s*(?:header\s+)?Referrer-Policy\s+no-referrer\s*$",
            edge_config,
            re.MULTILINE,
        ), f"{relative_path} must not override the reset page's no-referrer policy"

    assert re.search(
        r'^\s*header\s+Strict-Transport-Security\s+"max-age=31536000; includeSubDomains; preload"\s*$',
        site_config,
        re.MULTILINE,
    ), "TLS Caddy site must retain its HSTS policy"


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


def test_caddy_uri_redaction_rules_keep_path_first_and_sensitive_keys_ordered() -> None:
    """Both log filters redact reset paths before each known query credential."""
    expected_replacements = (
        "${1}token=REDACTED",
        "${1}ticket=REDACTED",
        "${1}code=REDACTED",
        "${1}password=REDACTED",
    )
    for relative_path in ("infrastructure/Caddyfile", "services/caddy/Caddyfile"):
        content = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        for operations in _caddy_uri_filter_blocks(content):
            path_pattern, path_replacement = operations[0]
            assert path_pattern.startswith("(?i)^")
            assert path_replacement == "[REDACTED]"

            query_operations = operations[1:]
            assert (
                tuple(replacement for _, replacement in query_operations)
                == expected_replacements
            )
            for pattern, _replacement in query_operations:
                assert pattern.startswith("(?i)([?&])")
                assert pattern.endswith("=[^&]*")
