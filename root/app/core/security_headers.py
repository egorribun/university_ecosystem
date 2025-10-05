from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import FileResponse, Response
from starlette.types import ASGIApp

from app.core.config import Settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, settings: Settings):
        super().__init__(app)
        self._settings = settings

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:  # type: ignore[override]
        nonce: str | None = None
        if self._settings.strict_security_headers_enabled:
            nonce = secrets.token_urlsafe(16)
            request.state.csp_nonce = nonce
        response = await call_next(request)
        if not self._settings.strict_security_headers_enabled:
            return response
        if nonce:
            response = self._inject_nonce_into_html(response, nonce)
        self._apply_hsts(response)
        self._apply_csp(response, nonce=nonce)
        self._apply_frame_options(response)
        self._apply_permissions_policy(response)
        self._apply_content_type_options(response)
        self._apply_referrer_policy(response)
        self._apply_cross_origin_policies(response)
        return response

    def _apply_hsts(self, response: Response) -> None:
        headers = response.headers
        if not self._settings.security_hsts_enabled:
            try:
                del headers["Strict-Transport-Security"]
            except KeyError:
                pass
            return
        value = f"max-age={int(self._settings.security_hsts_max_age)}"
        if self._settings.security_hsts_include_subdomains:
            value += "; includeSubDomains"
        if self._settings.security_hsts_preload:
            value += "; preload"
        headers["Strict-Transport-Security"] = value

    def _apply_csp(self, response: Response, *, nonce: str | None) -> None:
        headers = response.headers
        policy_template = self._settings.strict_security_csp
        policy = policy_template
        if nonce:
            policy = policy.replace("{nonce}", nonce)
        else:
            policy = (
                policy.replace("'nonce-{nonce}'", "")
                .replace("  ", " ")
                .replace(" ;", ";")
                .strip(" ;")
            )
        header_name = "Content-Security-Policy"
        if self._settings.security_csp_report_only:
            header_name = "Content-Security-Policy-Report-Only"
            try:
                del headers["Content-Security-Policy"]
            except KeyError:
                pass
        headers[header_name] = policy
        other_header = (
            "Content-Security-Policy"
            if header_name == "Content-Security-Policy-Report-Only"
            else "Content-Security-Policy-Report-Only"
        )
        try:
            del headers[other_header]
        except KeyError:
            pass

    def _inject_nonce_into_html(self, response: Response, nonce: str) -> Response:
        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type.lower():
            return response
        body_bytes: bytes | None = None
        if isinstance(response, FileResponse):
            path = Path(response.path)
            try:
                body_bytes = path.read_bytes()
            except OSError:
                return response
            charset = getattr(response, "charset", "utf-8") or "utf-8"
        else:
            body = getattr(response, "body", b"")
            if isinstance(body, memoryview):
                body_bytes = body.tobytes()
            elif isinstance(body, bytes):
                body_bytes = body
            else:
                body_bytes = bytes(body or b"")
            charset = getattr(response, "charset", "utf-8") or "utf-8"
        if not body_bytes:
            return response
        placeholder = "__CSP_NONCE__"
        try:
            html = body_bytes.decode(charset)
        except (LookupError, UnicodeDecodeError):
            return response
        if placeholder not in html:
            return response
        updated_html = html.replace(placeholder, nonce)
        if updated_html == html:
            return response
        updated_body = updated_html.encode(charset)
        media_type = content_type or response.media_type or "text/html"
        new_response = Response(
            content=updated_body,
            status_code=response.status_code,
            media_type=media_type,
            background=response.background,
        )
        new_response.charset = charset
        raw_headers = [
            (name, value)
            for name, value in getattr(response, "raw_headers", [])
            if name.lower() not in {b"content-length", b"content-type"}
        ]
        new_response.raw_headers.extend(raw_headers)
        return new_response

    def _apply_cross_origin_policies(self, response: Response) -> None:
        headers = response.headers
        headers["Cross-Origin-Opener-Policy"] = "same-origin"
        headers["Cross-Origin-Embedder-Policy"] = "require-corp"

    def _apply_frame_options(self, response: Response) -> None:
        headers = response.headers
        value = self._settings.security_x_frame_options.strip()
        if value:
            headers["X-Frame-Options"] = value
        else:
            try:
                del headers["X-Frame-Options"]
            except KeyError:
                pass

    def _apply_permissions_policy(self, response: Response) -> None:
        headers = response.headers
        value = self._settings.security_permissions_policy.strip()
        if value:
            headers["Permissions-Policy"] = value
        else:
            try:
                del headers["Permissions-Policy"]
            except KeyError:
                pass

    def _apply_content_type_options(self, response: Response) -> None:
        headers = response.headers
        value = self._settings.security_x_content_type_options.strip()
        if value:
            headers["X-Content-Type-Options"] = value
        else:
            try:
                del headers["X-Content-Type-Options"]
            except KeyError:
                pass

    def _apply_referrer_policy(self, response: Response) -> None:
        headers = response.headers
        value = self._settings.security_referrer_policy.strip()
        if value:
            headers["Referrer-Policy"] = value
        else:
            try:
                del headers["Referrer-Policy"]
            except KeyError:
                pass
