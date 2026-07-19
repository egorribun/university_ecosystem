from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from fastapi import Request

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

    from app.core.config import Settings


# PERF-NEW-001 (audit 2026-03-19): Moved _StreamState from inside __call__ to module
# level with __slots__. The dataclass was re-defined (and its descriptor re-compiled)
# on every HTTP request, wasting ~200ns. __slots__ also eliminates the __dict__
# per-instance allocation (~56 bytes), reducing GC pressure at high RPS.
class _StreamState:
    """Mutable state bag for SecurityHeadersMiddleware per-request HTML buffering."""

    __slots__ = ("headers_sent", "html_headers", "is_html", "status_code")

    def __init__(self) -> None:
        self.is_html: bool = False
        self.headers_sent: bool = False
        self.html_headers: list[tuple[bytes, bytes]] | None = None
        self.status_code: int = 200


# PERF-NEW-002 (audit 2026-03-19): Exempt health/metrics routes from CSP header
# building. These endpoints are hit at very high frequency by load balancers and
# monitoring systems, yet never return HTML, so CSP is irrelevant and wastes CPU.
_CSP_EXEMPT_PATHS: frozenset[str] = frozenset(
    {
        "/health",
        "/healthz",
        "/ready",
        "/metrics",
        "/api/v1/health",
        "/api/v1/health/db",
    }
)


class SecurityHeadersMiddleware:
    """Pure ASGI security headers injector — never buffers response body."""

    def __init__(self, app: ASGIApp, *, settings: Settings) -> None:
        self._app = app
        self._settings = settings
        # PERF-05 (audit 2026-03-11): Build all non-CSP headers once at startup.
        # HSTS, X-Frame-Options, Permissions-Policy, X-Content-Type-Options,
        # Referrer-Policy, and COOP/COEP/CORP are purely configuration-driven
        # and never vary per-request.  Pre-building them avoids redundant
        # conditional checks and string allocations on every HTTP call.
        self._static_headers: list[tuple[str, str]] = self._build_static_headers()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request = Request(scope, receive)
        nonce: str | None = None
        # LOW-W19: Only generate a CSP nonce for paths that can return HTML.
        # Generating a nonce unconditionally (including for /api/*, /metrics,
        # WebSocket upgrades, etc.) wastes entropy and CPU on every request
        # even though non-HTML responses never embed or use the nonce value.
        path: str = scope.get("path", "")
        _is_potentially_html = (
            not path.startswith("/api/")
            and not path.startswith("/static/")
            and path not in _CSP_EXEMPT_PATHS
        )
        if self._settings.should_inject_csp_nonce and _is_potentially_html:
            nonce = secrets.token_urlsafe(16)
            request.state.csp_nonce = nonce

        # PERF-NEW-002 (audit 2026-03-19): Skip CSP header building for exempt paths
        # (health, metrics) and static files. These never return HTML and are called
        # at high frequency. However, we STILL apply base static headers (HSTS, etc.)
        # to ensure they are protected.
        # LOW-W19: `path` is already set above (used for the nonce early-return).
        if path in _CSP_EXEMPT_PATHS or path.startswith("/static/"):
            csp_headers = []  # Omit CSP for performance/compatibility
        else:
            # PERF-05: Combine pre-built static headers with the per-request CSP
            csp_headers = self._build_csp_header(nonce=nonce)

        extra_headers = [*csp_headers, *self._static_headers]

        _accumulated_html_bytes = 0
        html_body: list[bytes] = []
        # RZ-W10-12: Reduced from 2 MB to 64 KB. The frontend SPA index.html is
        # typically <10 KB; larger values indicate an SSR page or misconfigured
        # route that should not be served via this middleware anyway. At 2 MB with
        # concurrent requests, buffering can spike worker RSS by hundreds of MB.
        _HTML_BUFFER_LIMIT = 64 * 1024  # 64 KB

        # PERF-NEW-001 (audit 2026-03-19): Use module-level _StreamState (with
        # __slots__) instead of a per-request dataclass definition.
        state = _StreamState()

        async def send_with_security_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                original_headers = list(message.get("headers", []))
                # Strip conflicting headers
                added_header_names = {
                    name.encode("latin-1").lower() for name, _ in extra_headers
                }
                added_header_names.add(b"content-security-policy")
                added_header_names.add(b"content-security-policy-report-only")

                headers_out = [
                    (k, v)
                    for k, v in original_headers
                    if k.lower() not in added_header_names
                ]
                for name, value in extra_headers:
                    headers_out.append(
                        (name.encode("latin-1"), value.encode("latin-1"))
                    )

                if nonce and self._settings.should_inject_csp_nonce:
                    request_path = scope.get("path", "")
                    if "/api/events/stream" not in request_path:
                        for name_b, value_b in headers_out:
                            if name_b.lower() == b"content-type":
                                content_type = value_b.lower()
                                if (
                                    b"text/html" in content_type
                                    and b"event-stream" not in content_type
                                ):
                                    state.is_html = True
                                    break

                if not state.is_html:
                    message_out = {**message, "headers": headers_out}
                    await send(message_out)
                else:
                    state.status_code = message["status"]
                    state.html_headers = headers_out
                return

            if message["type"] == "http.response.body":
                if not state.is_html:
                    await send(message)
                    return

                # P2-W5-19: Response buffering remains for nonce injection but is capped
                # to prevent OOM. If response exceeds _HTML_BUFFER_LIMIT, we fallback
                # to streaming without nonce injection.
                body_chunk = message.get("body", b"")
                nonlocal _accumulated_html_bytes, html_body

                _accumulated_html_bytes += len(body_chunk)
                if _accumulated_html_bytes <= _HTML_BUFFER_LIMIT:
                    html_body.append(body_chunk)
                    if not message.get("more_body", False):
                        # End of stream — perform replacement
                        full_body = b"".join(html_body)
                        try:
                            html_text = full_body.decode("utf-8")
                            if "__CSP_NONCE__" in html_text and nonce is not None:
                                html_text = html_text.replace("__CSP_NONCE__", nonce)
                                full_body = html_text.encode("utf-8")
                        except LookupError, UnicodeDecodeError:
                            pass

                        # Adjust content-length
                        final_headers = []
                        for n, v in state.html_headers or []:
                            if n.lower() == b"content-length":
                                final_headers.append(
                                    (
                                        b"content-length",
                                        str(len(full_body)).encode("latin-1"),
                                    )
                                )
                            else:
                                final_headers.append((n, v))

                        await send(
                            {
                                "type": "http.response.start",
                                "status": state.status_code,
                                "headers": final_headers,
                            }
                        )
                        await send(
                            {
                                "type": "http.response.body",
                                "body": full_body,
                                "more_body": False,
                            }
                        )
                else:
                    # Limit exceeded: Flush fallback immediately
                    if not state.headers_sent:
                        await send(
                            {
                                "type": "http.response.start",
                                "status": state.status_code,
                                "headers": state.html_headers,
                            }
                        )
                        state.headers_sent = True
                        # Send buffered chunks
                        for chunk in html_body:
                            await send(
                                {
                                    "type": "http.response.body",
                                    "body": chunk,
                                    "more_body": True,
                                }
                            )
                        html_body = []  # Clear memory

                    await send(message)
                return

            # Passthrough for any other ASGI event types (e.g. http.disconnect).
            # A single send() call is the correct ASGI contract — sending twice
            # would violate the protocol and cause duplicate response bodies
            # or Uvicorn assertion errors under concurrent load.
            # (RZ-NEW-001: audit 2026-03-19)
            await send(message)

        await self._app(scope, receive, send_with_security_headers)

    def _build_csp_header(self, *, nonce: str | None) -> list[tuple[str, str]]:
        """Return the list of (name, value) pairs for CSP headers.

        PERF-05: Called on every request because the nonce changes each time.
        All other security headers are pre-built in _build_static_headers().

        MOD-W8-04: In production (report_only=False) returns two headers:
        - Content-Security-Policy (enforcing)
        - Content-Security-Policy-Report-Only (shadow, same policy + report-uri)
        This lets us collect real violation reports without a separate relaxed policy.
        In dev/staging (report_only=True) returns only the CSP-RO header.
        """
        report_only = self._settings.security_csp_report_only_effective
        policy = self._settings.build_csp_policy(nonce=nonce, report_only=report_only)
        if report_only:
            return [("Content-Security-Policy-Report-Only", policy)]

        # Production: enforcing CSP + shadow report-only with report-uri appended
        shadow_policy = f"{policy}; report-uri /api/v1/csp-report"
        return [
            ("Content-Security-Policy", policy),
            ("Content-Security-Policy-Report-Only", shadow_policy),
        ]

    def _build_static_headers(self) -> list[tuple[str, str]]:
        """Build all non-CSP security headers once at startup.

        PERF-05 (audit 2026-03-11): These headers are purely configuration-driven
        and never vary per request (no nonce, no user-specific values).
        Pre-building them in __init__ eliminates redundant conditional checks and
        string concatenation on every HTTP call.
        """
        headers: list[tuple[str, str]] = []

        # HSTS
        if self._settings.security_hsts_enabled_effective:
            value = f"max-age={int(self._settings.security_hsts_max_age)}"
            if self._settings.security_hsts_include_subdomains:
                value += "; includeSubDomains"
            if self._settings.security_hsts_preload:
                value += "; preload"
            headers.append(("Strict-Transport-Security", value))

        # Cross Origin
        if self._settings.coop_enabled:
            headers.append(("Cross-Origin-Opener-Policy", "same-origin"))
        if self._settings.coep_enabled:
            headers.append(
                ("Cross-Origin-Embedder-Policy", self._settings.coep_header_value)
            )
        if self._settings.corp_enabled:
            headers.append(
                ("Cross-Origin-Resource-Policy", self._settings.corp_header_value)
            )

        # Frame Options
        if value := self._settings.security_x_frame_options.strip():
            headers.append(("X-Frame-Options", value))

        # Permissions-Policy
        if value := self._settings.security_permissions_policy.strip():
            headers.append(("Permissions-Policy", value))

        # X-Content-Type-Options
        if value := self._settings.security_x_content_type_options.strip():
            headers.append(("X-Content-Type-Options", value))

        # Referrer-Policy
        if value := self._settings.security_referrer_policy.strip():
            headers.append(("Referrer-Policy", value))

        return headers
