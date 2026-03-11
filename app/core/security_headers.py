from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from fastapi import Request

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

    from app.core.config import Settings


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
        if self._settings.should_inject_csp_nonce:
            nonce = secrets.token_urlsafe(16)
            request.state.csp_nonce = nonce

        # PERF-05 (audit 2026-03-11): Combine pre-built static headers with the
        # per-request CSP header (nonce changes every call).  Static headers are
        # computed once in __init__; only _build_csp_header() runs here.
        csp_header = self._build_csp_header(nonce=nonce)
        extra_headers = [csp_header, *self._static_headers]

        is_html = False
        html_body: list[bytes] = []
        html_status = 200
        html_headers: list[tuple[bytes, bytes]] = []
        # PERF-01 (audit 2026-03-04): Track accumulated buffer size with an O(1)
        # running counter instead of recomputing sum(len(c)) on every chunk.
        _accumulated_html_bytes = 0
        _HTML_BUFFER_LIMIT = 2 * 1024 * 1024  # 2 MB

        async def send_with_security_headers(message: Message) -> None:
            nonlocal is_html, html_body, html_status, html_headers

            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))

                # Strip conflicting headers and pre-calculate extra headers
                added_header_names = {
                    name.encode("latin-1").lower() for name, _ in extra_headers
                }
                # Prevent both CSP and CSP-Report-Only from upstream
                # being emitted simultaneously — only our version is sent.
                added_header_names.add(b"content-security-policy")
                added_header_names.add(b"content-security-policy-report-only")

                headers_out = [
                    (k, v) for k, v in headers if k.lower() not in added_header_names
                ]

                for name, value in extra_headers:
                    headers_out.append(
                        (name.encode("latin-1"), value.encode("latin-1"))
                    )

                # Determine if HTML needs nonce injection
                if nonce and self._settings.should_inject_csp_nonce:
                    # PERF-3: Do not attempt to buffer SSE streams or non-HTML responses
                    # for nonce injection. Buffering SSE causes latency and memory leaks.
                    request_path = scope.get("path", "")
                    if "/api/events/stream" not in request_path:
                        for name_b, value_b in headers_out:
                            if name_b.lower() == b"content-type":
                                content_type = value_b.lower()
                                # Only match explicit text/html, ignore event-stream
                                if (
                                    b"text/html" in content_type
                                    and b"event-stream" not in content_type
                                ):
                                    is_html = True
                                    html_status = message["status"]
                                    html_headers = headers_out
                                    break

                if not is_html:
                    message = {**message, "headers": headers_out}
                    await send(message)
                return

            if message["type"] == "http.response.body":
                if not is_html:
                    await send(message)
                    return

                # Accumulate HTML chunks for nonce injection.
                # PERF-5 (audit 2026-02-26): Guard against unbounded heap growth
                # from large HTML responses (SSR pages, error dumps).  At >2 MB
                # skip nonce injection and flush buffered chunks directly.
                body_chunk = message.get("body", b"")
                if body_chunk:
                    nonlocal _accumulated_html_bytes
                    _accumulated_html_bytes += len(body_chunk)
                    if _accumulated_html_bytes > _HTML_BUFFER_LIMIT:
                        # Exceed limit — disable buffering for this response.
                        is_html = False
                        await send(
                            {
                                "type": "http.response.start",
                                "status": html_status,
                                "headers": html_headers,
                            }
                        )
                        for buffered_chunk in html_body:
                            await send(
                                {
                                    "type": "http.response.body",
                                    "body": buffered_chunk,
                                    "more_body": True,
                                }
                            )
                        await send(message)
                        return
                    html_body.append(body_chunk)

                if not message.get("more_body", False):
                    # End of stream, process HTML
                    full_body = b"".join(html_body)

                    try:
                        # Attempt to replace nonce placeholder
                        # Will simply fallback to no-op on err/failure to decode
                        html_text = full_body.decode("utf-8")
                        if "__CSP_NONCE__" in html_text and nonce is not None:
                            html_text = html_text.replace("__CSP_NONCE__", nonce)
                            full_body = html_text.encode("utf-8")
                    except (LookupError, UnicodeDecodeError):
                        pass

                    # Compute new bounds
                    new_headers = []
                    for n, v in html_headers:
                        if n.lower() == b"content-length":
                            new_headers.append(
                                (
                                    b"content-length",
                                    str(len(full_body)).encode("latin-1"),
                                )
                            )
                        else:
                            new_headers.append((n, v))

                    # Transmit buffered output
                    await send(
                        {
                            "type": "http.response.start",
                            "status": html_status,
                            "headers": new_headers,
                        }
                    )
                    await send(
                        {
                            "type": "http.response.body",
                            "body": full_body,
                            "more_body": False,
                        }
                    )
                return

            # Passthrough for other events
            await send(message)

        await self._app(scope, receive, send_with_security_headers)

    def _build_csp_header(self, *, nonce: str | None) -> tuple[str, str]:
        """Return the (name, value) pair for the CSP/CSP-Report-Only header.

        PERF-05: Called on every request because the nonce changes each time.
        All other security headers are pre-built in _build_static_headers().
        """
        report_only = self._settings.security_csp_report_only_effective
        policy = self._settings.build_csp_policy(nonce=nonce, report_only=report_only)
        header_name = (
            "Content-Security-Policy-Report-Only"
            if report_only
            else "Content-Security-Policy"
        )
        return (header_name, policy)

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
