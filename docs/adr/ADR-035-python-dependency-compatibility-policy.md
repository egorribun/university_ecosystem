# ADR-035: Python Dependency Compatibility Policy

## Status

Accepted

## Date

2026-09-10

## Context

The backend is a Python 3.14 production service with security-sensitive
authentication, cryptography, database, WebSocket, observability and native
extension boundaries. An exact `uv.lock` makes one environment reproducible,
but a future lock refresh can still widen a direct requirement indefinitely
when `pyproject.toml` declares only a lower bound. That allows an unreviewed
major API or ABI change into the next build.

The independent platform audit reported 19 unbounded Python dependencies. A
current machine inventory found 32 external production requirements without
an upper bound (the older number is not reproducible on the current source).
The local workspace package `rust_ext` is not an external PyPI dependency and
is intentionally outside this policy.

## Decision Drivers

- Keep every external production dependency inside an explicitly reviewed
  compatibility range.
- Preserve security patch velocity and the existing seven-day maturity
  cooldown.
- Avoid arbitrary exact pins that prevent safe patch updates.
- Make range widening a deliberate, test-backed review event.
- Keep local workspace packages and any future exceptions machine-readable.

## Considered Options

### Option 1: Exact-pin every dependency

Exact pins maximize short-term reproducibility but block compatible security
patches and turn every update into a manual lockfile replacement. They also do
not express which future versions are expected to remain compatible.

### Option 2: Lower bounds only

Lower bounds preserve update velocity but permit silent major-version and ABI
breakage during a routine lock refresh. This is the condition identified by
SEC-09 and is rejected.

### Option 3: Reviewed lower-and-upper ranges (selected)

Declare a lower bound plus an upper bound for each external production
requirement. Renovate may update within the existing range according to its
cooldown and review rules; widening a cap is a separate compatibility change.

## Policy

1. Every external entry in `[project].dependencies` must contain a `<` upper
   bound. A local workspace member may be explicitly identified as an
   exception.
2. There are currently no reviewed unbounded external exceptions. Any future
   reviewed exception must be explicitly named and justified. The
   fail-closed contract lives in
   `tests/test_dependency_resolution_policy.py` and must fail when a new
   unbounded requirement is introduced.
3. Caps follow the currently tested major/API line, not a promise that all
   future releases are compatible. For 0.x packages, `<1` is intentional and
   must be widened only with API evidence.
4. Security vulnerability PRs are created immediately but remain manual;
   they must preserve the range unless a reviewed cap change is required.
5. Routine updates retain the repository's seven-day maturity window,
   `uv lock --check`, frozen lock/install verification, vulnerability audit,
   SBOM/provenance and the normal full test/mutation gates.
6. A cap change requires a compatibility matrix for the affected boundary
   (auth/JWKS/MFA, ASGI/WebSocket, database/migrations, native/ABI,
   observability or integrations), plus a focused regression test and review
   of the resulting lock diff.

## Implementation

The current source adds conservative upper bounds to the 32 previously
unbounded external requirements, including the crypto/auth, ASGI/runtime,
storage/data, native/ABI, observability and integration packages. The lockfile
records the same requirement metadata. No package version was artificially
upgraded or downgraded as part of the range-only change.

`tests/test_dependency_resolution_policy.py` verifies both the complete
upper-bound inventory and the existing Renovate/security cooldown contract.
`uv lock --check` is required after every edit; CI additionally runs frozen
installation, vulnerability, SBOM and provenance gates.

## Consequences

### Positive

- Routine lock refreshes cannot silently cross a major/API boundary.
- Security patches remain available inside a reviewed range.
- The policy is machine-enforced and reports the exact unbounded set if it
  regresses.
- Compatibility decisions become auditable instead of relying on the stale
  count from the external snapshot.

### Negative

- A new major release may require an explicit cap-widening change and extra
  testing before adoption.
- Some 0.x packages use `<1`, so a stable 1.0 release will require review.
- Range-only edits still need full CI because transitive resolution and ABI
  behavior are not proven by metadata alone.

## Verification Evidence

- Current inventory: 73 production requirement records, 40 already bounded,
  32 newly bounded, and one local workspace member (`rust_ext`).
- Policy test: passing after the range changes; the pre-change RED output
  enumerated all 32 unbounded packages.
- `uv lock --check`: passing with 258 resolved packages.
- Full compatibility, security and release evidence remains required on the
  next current-SHA CI run; this ADR is not a substitute for that evidence.

## Related Decisions

- [ADR-001: Password Hashing](ADR-001-password-hashing.md)
- [ADR-006: WebSocket Auth Tickets](ADR-006-websocket-auth-tickets.md)
- [ADR-010: Kyverno Admission Control](ADR-010-kyverno-admission-control.md)
- [ADR-012: Centralized Logging](ADR-012-centralized-logging.md)
- [ADR-013: Secret Rotation](ADR-013-secret-rotation.md)
- [ADR-034: Helm as the Canonical Application Deployment Artifact](ADR-034-helm-canonical-application-deployment.md)

## References

- [`pyproject.toml`](../../pyproject.toml)
- [`uv.lock`](../../uv.lock)
- [`tests/test_dependency_resolution_policy.py`](../../tests/test_dependency_resolution_policy.py)
- [`docs/DEPENDENCY_COOLDOWN_EMERGENCY.md`](../DEPENDENCY_COOLDOWN_EMERGENCY.md)
- `docs/audits/AUDIT_PLATFORM_FULL.md`, Finding SEC-09 (user-owned audit
  artifact; remains untracked and is not a release certificate)
