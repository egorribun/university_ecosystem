"""Configuration mixin classes for SecuritySettings decomposition.

Each mixin addresses a single logical concern:
- JwtSettingsMixin: JWT signing keys, key rotation, token lifetime
- CorsSettingsMixin: CORS policy, trusted hosts, origin validation
- RateLimitSettingsMixin: Rate limit thresholds and storage backend
- MfaSettingsMixin: TOTP/email MFA, trusted devices, password policy
- CspSettingsMixin: CSP, HSTS, COOP, COEP, CORP, security headers
"""

from .cors_settings import CorsSettingsMixin
from .csp_settings import CspSettingsMixin
from .jwt_settings import JwtSettingsMixin
from .mfa_settings import MfaSettingsMixin
from .rate_limit_settings import RateLimitSettingsMixin

__all__ = [
    "CorsSettingsMixin",
    "CspSettingsMixin",
    "JwtSettingsMixin",
    "MfaSettingsMixin",
    "RateLimitSettingsMixin",
]
