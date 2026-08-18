# ADR-009: OpenFeature Feature Flags

## Status

Accepted (2026-08-17)

## Context

The backend needs vendor-neutral boolean evaluation for gradual delivery, kill
switches, and targeted experiments. The repository already contained a flagd
Deployment and an OpenFeature wrapper, but the architecture record still called
the provider decision pending. More importantly, the runtime package for the
flagd provider and the in-cluster endpoint wiring were absent.

The administration API also exposed a `PATCH /admin/feature-flags/{name}` route.
That route returned a synthetic success object while logging that the
ConfigMap-managed value had not changed. The frontend then updated its cache
optimistically, so operators saw a state that neither flagd nor another backend
replica shared.

flagd is an evaluation engine, not a durable distributed flag-management API.
The authoritative definitions in this deployment are version-controlled in
[`k8s/flagd/flags.json`](../../k8s/flagd/flags.json). Kustomize generates the
Kubernetes ConfigMap from that same file, and Docker Compose mounts it directly.

## Decision Drivers

- Every successful write must represent durable, cluster-wide state.
- Flag changes require review, auditability, and rollback.
- Application code must remain independent of a particular evaluation engine.
- A flagd outage must not prevent application startup or hide the configured
  call-site fallback.
- Dependency and protocol versions must be explicit and reproducible.

## Considered Options

### Runtime mutation through the existing admin API

Rejected. Editing one process, a mounted file, or a Kubernetes ConfigMap from an
application pod would require privileged Kubernetes credentials and still needs
concurrency control, durable audit, rollout validation, and replica
synchronization. Returning success without those guarantees is incorrect.

### Add a separate persistent flag-management service

Deferred. A management plane such as Unleash or Flipt could provide audited
distributed writes, but it adds another stateful service and migration path that
the current requirements do not justify.

### Read-only diagnostics plus GitOps management

Accepted. Git is the authoritative management plane; flagd evaluates the
projected configuration; the application exposes only effective diagnostics.

## Decision

1. Use the Python OpenFeature SDK with
   `openfeature-provider-flagd>=0.5.0,<0.5.1` and the RPC resolver. Version
   0.5.0 is the newest provider compatible with the shared protobuf 6 line;
   0.5.1 and later require protobuf 7 while Authzed and OpenTelemetry require
   protobuf below 7. gRPC and its health stubs are held on the stable 1.81 line
   for the same reason; 1.82.0 was yanked and 1.82.1 moves the generated health
   stubs to protobuf 7.
2. Run the SHA-pinned `flagd:v0.16.1` image as a two-replica Kubernetes
   Deployment. Backend pods connect through the `flagd` Service using typed
   `FLAGD_HOST` and `FLAGD_PORT` settings.
3. Keep the registered boolean flag set synchronized with
   `k8s/flagd/flags.json`; a contract test rejects drift.
4. Manage definitions only through reviewed GitOps changes. flagd watches the
   projected file and applies valid definitions without a backend deployment.
5. Expose `GET /admin/feature-flags` as a read-only diagnostics endpoint. Each
   row reports the effective value, application fallback, provider, evaluation
   reason, management mode, and canonical configuration path. It does not invent
   rollout percentages or mutable statuses unavailable from OpenFeature.
6. Remove the mutation operation from OpenAPI and generated clients. A hidden
   compatibility handler returns HTTP 405 with `Allow: GET` for legacy PATCH
   callers, so no caller can interpret a no-op as success.
7. Use explicit `initialize_feature_flags()` and `shutdown_feature_flags()`
   lifecycle functions. The former installs the process-wide provider; the
   latter releases provider resources through the OpenFeature SDK.

## Failure Semantics

- `is_enabled()` and `is_enabled_sync()` return the caller-provided default if
  initialization or evaluation fails.
- The flagd provider reconnects after transport loss. Initialization errors are
  logged and do not prevent the rest of the application from starting.
- The diagnostics endpoint remains available during provider failures. A failed
  evaluation reports the registered fallback with reason `ERROR`, never a
  fabricated control-plane state.

## Consequences

### Positive

- No false-success mutation path or replica-local state.
- Reviewed, reversible, and auditable flag changes.
- Vendor-neutral evaluation API with a real flagd provider installed at runtime.
- Explicit K8s service discovery, network policy, lifecycle, and fallback
  behavior.

### Negative

- Operators cannot toggle flags directly from the application UI.
- GitOps propagation is slower than an imperative management API.
- Adding a true interactive control plane later requires a new ADR, persistent
  storage, authorization, audit logging, and distributed consistency guarantees.

## Implementation

- `app/core/feature_flags.py` — registry, evaluation, diagnostics, and lifecycle
- `app/core/config/integrations.py` — typed flagd connection settings
- `app/api/admin/feature_flags.py` — read-only admin API and legacy 405 guard
- `k8s/flagd/` — SHA-pinned flagd workload, definitions, and network policy
- `k8s/backend/configmap.yaml` — in-cluster flagd Service endpoint
- `docker-compose.full.yml` — local flagd service and readiness-probe sidecar
- `frontend/src/features/admin/AdminFeatureFlagsFeature.tsx` — read-only
  diagnostics surface
