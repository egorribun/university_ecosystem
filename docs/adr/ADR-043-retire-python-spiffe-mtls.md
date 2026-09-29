# ADR-043: Retire the Python SPIFFE and mTLS Subsystem

## Status

Accepted

## Date

2026-09-29

## Context

The backend carried a SPIFFE Workload API integration in
`app/core/security/spiffe.py`: an `SVIDManager` that was meant to rotate X.509
SVIDs from a SPIRE agent socket, SSL-context builders, and a
`SPIFFEAuthMiddleware` registered in `app/main.py` for `/api/internal` and
`/api/v1/chat/check-participant`. `app/core/lifespan.py` started and stopped
the manager, and `SecuritySettings` exposed five `spiffe_*` settings.

A review of the subsystem (safe-pause handoff of 2026-09-29, section 10)
found that it could never work:

1. The module imports `pyspiffe`. That distribution does not exist on PyPI;
   the maintained Python client is published as `spiffe` and has a different
   API (`spiffe.workloadapi`, `spiffe.spiffe_id`). The import always failed,
   so `SVIDManager` never left its degraded mode and never held an SVID.
2. `pyspiffe` was not declared as a dependency. `deptry` only passed because
   `pyproject.toml` ignored `DEP001` for it.
3. `spiffe_enabled` defaults to `False`, and no Compose file, Helm value or
   environment template ever enabled it. With the flag off the middleware is
   a pass-through, so the code path was dead in every supported deployment.
4. The four Python test files exercised only this dead module, including two
   long concurrency stress suites (roughly 55 seconds of the shard budget) that
   could not prove workload identity in a real deployment.

## Decision

Remove the Python-side SPIFFE subsystem:

- delete `app/core/security/spiffe.py` and its four test modules;
- remove the middleware registration from `app/main.py`, the manager start and
  stop from `app/core/lifespan.py`, and the `spiffe_*` fields from
  `SecuritySettings`;
- remove the `DEP001 = ["pyspiffe"]` deptry ignore and the corresponding
  entries in `quality/ownership-mapping.json` and `quality/test-durations.json`.

Internal-route authentication is unchanged: `/api/internal/*` remains
protected by `InternalAccessMiddleware` (`app/core/internal_access.py`), which
checks the shared internal header token, and gateway-asserted identity keeps
using the `X-Internal-Signature` HMAC described in ADR-013.

The Go and infrastructure side is not part of this decision and stays as is:
`services/pkg/spiffe` and its consumers (gateway, file-processor), the SPIRE
manifests under `k8s/spire/`, the Helm `internalGrpcMTLS` values including
`gatewayIdentityURI`, and the Go coverage and mutation contracts that name
`services/pkg/spiffe`.

Reintroducing workload identity in the Python application requires a new ADR.
It must use the real `spiffe` package, declare it as a dependency, and prove
SVID issuance and rotation against a SPIRE agent before any middleware is
enabled.

## Consequences

- The `SPIFFE_*` and `SECURITY__SPIFFE_*` environment variables are no longer
  read. They were never documented or set in shipped configuration, and
  unknown environment variables do not fail settings loading.
- `/api/internal/*` and `/api/v1/chat/check-participant` are no longer wrapped
  by a second, always-disabled layer; the effective protection is identical to
  what was deployed before.
- Backend startup and shutdown no longer touch a SPIRE socket or temporary
  certificate files.
- The Python test suite loses about 1,500 lines of tests and roughly one minute
  of duration-balanced shard time.
- Go services keep verifying peer identity with `services/pkg/spiffe`; the
  backend is reached over the trusted internal network with header-token
  authentication rather than SPIFFE mTLS.

## Alternatives considered

- **Declare `spiffe` and port the module.** Rejected: the API differs, nothing
  enables the feature, and there is no SPIRE in the MVP deployment (kind runs
  without it), so a port could not be verified end to end.
- **Keep the module as documented dead code.** Rejected: it shipped a
  fail-closed middleware and a lifespan hook whose behaviour depended on a
  non-existent package, and it required a permanent deptry exception.

## References

- [ADR-013](ADR-013-secret-rotation.md)
- `app/core/internal_access.py` (`InternalAccessMiddleware`)
- `services/pkg/spiffe`
- `k8s/spire/`
