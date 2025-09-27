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
        self._apply_hsts(response)
        self._apply_csp(response)
        self._apply_frame_options(response)
        self._apply_permissions_policy(response)
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
        policy = self._settings.security_csp.strip()
        report_uri = self._settings.security_csp_report_uri.strip()
        header_name = "Content-Security-Policy"
        if self._settings.security_csp_report_only:
            header_name = "Content-Security-Policy-Report-Only"
        alternate = (
            "Content-Security-Policy"
            if header_name.endswith("Report-Only")
            else "Content-Security-Policy-Report-Only"
        )
        if not policy:
            for name in (
                "Content-Security-Policy",
                "Content-Security-Policy-Report-Only",
            ):
                try:
                    del headers[name]
                except KeyError:
                    pass
            return
        normalized = policy.rstrip("; ")
        if report_uri:
            normalized = f"{normalized}; report-uri {report_uri}"
        headers[header_name] = normalized
        try:
            del headers[alternate]
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
