"""Shared identity policy for global and sensitive-route rate limiting."""

# Credential guessing and account recovery keep the IP budget even when callers
# present valid access tokens. Keep this identical in both limiters.
# Entries are route roots: a path matches an entry exactly or as a path segment
# prefix, so ``/api/v1/auth/login/json`` is covered while ``/api/v1/auth/loginx``
# is not.
_IP_BUCKETED_ROUTE_ROOTS: tuple[str, ...] = (
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/password",
)


def uses_ip_bucket(path: str) -> bool:
    """Return True when ``path`` belongs to an IP-bucketed route family.

    Matching is case-insensitive so that an alternate spelling of a
    credential-guessing route can never move it into a per-user budget.
    """
    normalized = path.lower()
    return any(
        normalized == root or normalized.startswith(f"{root}/")
        for root in _IP_BUCKETED_ROUTE_ROOTS
    )
