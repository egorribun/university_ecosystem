from __future__ import annotations

import logging
from typing import ClassVar

logger = logging.getLogger(__name__)


class ContentSecurityPolicy:
    """
    Generates Content Security Policy (CSP) headers.
    Decouples policy generation from configuration storage.
    """

    # Base policies for development and production
    _DEV_POLICY_TEMPLATE: ClassVar[str] = (
        "default-src 'self' http://localhost:5173; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' "
        "http://localhost:5173 https://accounts.google.com 'report-sample'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "img-src 'self' data: https: blob:; "
        "connect-src {connect_src}; "
        "font-src 'self' data: https://fonts.gstatic.com; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'self'; "
        "trusted-types app dompurify-news goog#html 'allow-duplicates'; "
        "{require_trusted_types}"
    )

    _PROD_POLICY_TEMPLATE: ClassVar[str] = (
        "default-src 'self'; "
        "script-src 'self' 'nonce-{nonce}' 'strict-dynamic' "
        "https://accounts.google.com 'report-sample'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "img-src 'self' data: https: blob:; "
        "connect-src {connect_src}; "
        "font-src 'self' data: https://fonts.gstatic.com; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "upgrade-insecure-requests; "
        "frame-ancestors 'self'; "
        "trusted-types app dompurify-news goog#html 'allow-duplicates'; "
        "{require_trusted_types}"
    )

    def __init__(
        self,
        is_development: bool = False,
        report_only: bool = False,
        report_uri: str = "",
        connect_src_extra: list[str] | None = None,
        custom_policy: str = "",
    ) -> None:
        self.is_development = is_development
        self.report_only = report_only
        self.report_uri = report_uri
        self.connect_src_extra = connect_src_extra or []
        self.custom_policy = custom_policy

    def generate(self, nonce: str | None = None) -> str:
        """
        Build the CSP header string.

        Args:
            nonce: Cryptographic nonce for script-src.
        """
        if self.custom_policy.strip():
            template = self.custom_policy.strip()
        else:
            template = (
                self._DEV_POLICY_TEMPLATE
                if self.is_development
                else self._PROD_POLICY_TEMPLATE
            )

        # 1. Require Trusted Types
        # Included in both dev and prod so developers see violations during local development.
        # In dev the dev CSP template uses 'unsafe-inline'/'unsafe-eval' for HMR compatibility,
        # but TT enforcement still catches innerHTML/eval without a policy — which is exactly
        # the signal we want. Omitted only when the entire CSP is in report_only mode (to
        # avoid sending the directive twice when the caller wraps it in CSPRO).
        require_trusted_types = (
            "require-trusted-types-for 'script'" if not self.report_only else ""
        )
        policy = template.replace("{require_trusted_types}", require_trusted_types)

        # 2. Connect Sources
        # Merge extra sources with 'self' and dedup
        sources = ["'self'", *self.connect_src_extra]
        # Add dev-specific overrides if needed
        # (though ideally these should be passed in)
        if self.is_development:
            sources.extend(self._get_dev_connect_overrides())

        connect_value = " ".join(sorted(list(set(s for s in sources if s)))).strip()
        policy = policy.replace("{connect_src}", connect_value or "'self'")

        # 3. Nonce Injection
        if nonce:
            policy = policy.replace("{nonce}", nonce)
        else:
            # Clean up nonce placeholders if no nonce provided
            policy = (
                policy.replace("'nonce-{nonce}'", "")
                .replace("{nonce}", "")
                .replace("  ", " ")
            )

        # 4. Clean and Format directives
        directives = [part.strip() for part in policy.split(";") if part.strip()]
        policy = "; ".join(directives)

        # Ensure default-src exists
        if "default-src" not in policy.lower():
            policy = f"default-src 'self'; {policy}"

        # 5. Report URI
        if self.report_uri.strip():
            policy = f"{policy}; report-uri {self.report_uri.strip()}"

        return policy

    def _get_dev_connect_overrides(self) -> list[str]:
        """Helper to allow local connections in dev mode."""
        return [
            "http://127.0.0.1:8000",
            "http://localhost:5173",
            "ws://localhost:5173",
            "http://localhost:8081",
        ]
