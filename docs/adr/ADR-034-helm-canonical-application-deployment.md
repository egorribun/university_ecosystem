# ADR-034: Helm as the Canonical Application Deployment Artifact

## Status

Accepted

## Date

2026-09-10

## Context

The repository contains both a `charts/university-ecosystem` Helm chart and a
raw `k8s/` tree. The raw tree intentionally contains supporting manifests for
the namespace, edge ingress, backend/frontend examples, policies,
observability, jobs and local diagnostics. It does not contain duplicate
Deployments or Services for the Go workloads (`gateway`, `ws-hub` and
`file-processor`). The Helm chart, however, renders the complete first-party
workload set and owns the release values, immutable image references, TLS,
secrets, policy and rollback configuration.

An independent platform audit correctly observed that applying only the raw
`k8s/` application manifests cannot produce a complete routable platform. The
same audit explicitly offered two valid remediations: add a second complete
set of raw Go manifests, or document one canonical deployment artifact. A
second set would create two sources of truth and make drift, security review
and image provenance harder to control.

## Decision Drivers

- One reviewed source of truth for staging and production application
  workloads.
- Immutable image, TLS, ExternalSecrets, Kyverno and rollback gates must be
  applied consistently.
- Avoid duplicated Go manifests and configuration drift.
- Keep raw manifests useful for approved supporting and development
  operations.
- Make the deployment boundary explicit to operators and automated tests.

## Considered Options

### Option 1: Add standalone Go Deployments and Services to raw `k8s/`

This would make the raw tree self-contained, but it would duplicate the Helm
templates and values. Every security, resource, image and probe change would
need two coordinated reviews, and a partial update could route traffic to a
different configuration than the Helm release.

### Option 2: Use Helm as the sole canonical producer (selected)

The chart remains the single canonical deployment artifact for staging and
production. The raw tree is explicitly supporting/development-only and must
not be used as a release shortcut. This preserves one source of truth while
making the audit finding and operational boundary unambiguous.

### Option 3: Keep the ambiguity undocumented

This avoids an immediate documentation change but leaves operators free to
apply an incomplete raw bundle, recreating the audited outage risk.

## Decision

Helm is the **sole canonical producer** and **single canonical deployment
artifact** for application workloads in staging and production. The chart
owns exactly these first-party workloads: `backend`, `frontend`, `gateway`,
`ws-hub`, `file-processor` and `outbox-worker`.

The raw k8s tree (`k8s/`) intentionally does not duplicate the Go service
Deployments or Services. It may be used only for explicitly approved
supporting, development or diagnostic operations (for example, creating a
namespace or applying a separately reviewed policy bundle). Applying the raw
application subdirectories is not a staging or production release path.

## Consequences

### Positive

- Workload identity, resources, probes, mTLS, image digests, TLS and
  autoscaling are reviewed and rendered from one chart.
- The absence of raw Go manifests is intentional and testable, rather than a
  hidden deployment gap.
- Operators have a single documented release command and rollback boundary.
- Raw supporting manifests remain available without competing with the
  production release artifact.

### Negative

- `kubectl apply -f k8s/` alone cannot deploy the platform; operators must use
  Helm for staging and production.
- Local diagnostic workflows need to state explicitly which supporting
  manifests they apply.
- Helm tooling and chart dependency validation are release prerequisites.

### Risks and Mitigations

- **Risk:** someone treats the raw tree as a complete release. **Mitigation:**
  the raw README, chart README and infrastructure contract tests state the
  boundary and reject contradictory documentation.
- **Risk:** the chart omits a workload. **Mitigation:** the contract test
  asserts the exact six-template inventory; Helm lint/template, kubeconform
  and Kyverno checks remain release gates.
- **Risk:** a chart release is not proven in a cluster. **Mitigation:** fresh
  current-SHA Helm render and production-like staging smoke remain required
  before release certification.

## Implementation and Verification

- `k8s/README.md` declares Helm the sole canonical producer and forbids raw
  staging/production release use.
- `tests/test_infra_audit_contract.py` asserts the scope wording, exact Helm
  workload inventory and absence of duplicate raw Go Deployments.
- `tests/test_helm_staging_contract.py` covers rendered gateway, ws-hub,
  file-processor, mTLS and ingress behavior.
- Every current-SHA certification must run `helm dependency build`,
  `helm lint --strict`, `helm template`, kubeconform/Kyverno validation and a
  staging smoke proving that all six workloads belong to one Helm release.

## Related Decisions

- [ADR-010: Kyverno Admission Control](ADR-010-kyverno-admission-control.md)
- [ADR-013: Secret Rotation](ADR-013-secret-rotation.md)
- [ADR-022: Go Services Integration Testing with Testcontainers](ADR-022-go-services-integration-testing-with-testcontainers.md)
- [ADR-032: KEDA Event-Driven Auto-Scaling and Off-Peak Resource Hibernation](ADR-032-keda-autoscale-and-hibernation.md)

## References

- [`k8s/README.md`](../../k8s/README.md)
- [`charts/university-ecosystem/README.md`](../../charts/university-ecosystem/README.md)
- [`tests/test_infra_audit_contract.py`](../../tests/test_infra_audit_contract.py)
- `docs/audits/AUDIT_PLATFORM_FULL.md`, Finding INFRA-02 (user-owned audit
  artifact; remains untracked and is not a release certificate)
