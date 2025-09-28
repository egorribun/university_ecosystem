from __future__ import annotations

from app.core.config import Settings
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from starlette.types import ASGIApp


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, settings: Settings):
        super().__init__(app)
        self._settings = settings

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:  # type: ignore[override]
        response = await call_next(request)
        if not self._settings.strict_security_headers_enabled:
            return response
        self._apply_hsts(response)
        self._apply_csp(response)
        self._apply_frame_options(response)
        self._apply_permissions_policy(response)
        self._apply_content_type_options(response)
        self._apply_referrer_policy(response)
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

    def _apply_csp(self, response: Response) -> None:
        headers = response.headers
        policy = (self._settings.strict_security_csp or "default-src 'self'").strip()
        headers["Content-Security-Policy"] = policy
        try:
            del headers["Content-Security-Policy-Report-Only"]
        except KeyError:
            pass

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
