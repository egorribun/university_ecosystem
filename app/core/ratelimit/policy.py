"""Shared identity policy for global and sensitive-route rate limiting."""

# Credential guessing and account recovery retain the IP budget even when
# callers rotate valid access tokens. Keep this identical in both limiters.
_IP_BUCKETED_PATH_PREFIXES: tuple[str, ...] = (
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/password/",
)


def uses_ip_bucket(path: str) -> bool:
    return path.startswith(_IP_BUCKETED_PATH_PREFIXES)
