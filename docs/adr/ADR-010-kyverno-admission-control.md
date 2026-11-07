# ADR-010: Kyverno Admission Control Policies

## Status
Accepted — initial ClusterPolicies switched from Audit to Enforce mode (Wave 13, 2026-03-17); current ValidatingPolicy implementation is documented below.

## Context

The Kubernetes cluster lacked policy enforcement at the admission layer. Deployments could:
- Run containers as root without restriction
- Omit resource limits (CPU/memory), risking noisy-neighbor OOM
- Use `latest` image tags, breaking reproducibility
- Mount host paths or escalate privileges

While `securityContext` was set in Helm chart templates, there was no cluster-level backstop if a chart was misconfigured or if developers applied ad-hoc manifests bypassing Helm.

## Decision

The initial Wave 13 deployment (2026-03-17) recorded **5 ClusterPolicies**:

1. **`disallow-privilege-escalation`** — Rejects any container with `allowPrivilegeEscalation: true`.
2. **`require-non-root`** — Requires `runAsNonRoot: true` in pod security context.
3. **`disallow-host-paths`** — Blocks hostPath volume mounts (prevents container escape via host filesystem).
4. **`require-readonly-root`** — Requires `readOnlyRootFilesystem: true`.
5. **`disallow-latest-tag`** — Blocks image references without an explicit tag or digest.

This five-policy list is the dated initial design and deployment record, not the
current policy resource inventory.

**Policy mode progression:**
- Wave 13 initial: all 5 policies deployed in `Audit` mode (violations logged, not blocked)
- Wave 13 final: confirmed zero violations over 48h monitoring window → switched all to `Enforce` mode

## Consequences

**Positive:**
- Defense-in-depth: cluster enforces security constraints independent of Helm chart correctness.
- Kyverno generates violation reports queryable via `kubectl get policyreport`.
- Audit mode allows zero-disruption policy rollout.

**Negative:**
- Any Enforce-mode policy blocks deployments that violate the policy — requires team awareness.
- Kyverno itself must be kept patched (runs as a cluster-critical component).
- Policy exceptions require explicit `PolicyException` resources (deliberate friction is the point).

## Alternatives Rejected

- **OPA/Gatekeeper** — More powerful but higher operational complexity; Rego learning curve steeper than Kyverno's YAML policies.
- **Pod Security Standards (PSS)** — Namespace-level only, less granular than per-policy control.
- **Manual chart review** — Does not prevent ad-hoc `kubectl apply` bypassing review.

## Implementation

- Current implementation: `k8s/kyverno/cluster-policies.yaml` defines 10 CEL-native Kyverno `ValidatingPolicy` resources. All are scoped to the `university-ecosystem` namespace and use `failurePolicy: Fail` with validation actions `Deny` and `Audit`:
  - Pod security and host access: `require-run-as-non-root`, `disallow-privilege-escalation`, `require-drop-all-capabilities`, `require-seccomp-profile`, `require-readonly-root-filesystem`, and `disallow-host-access`.
  - Image controls: `restrict-image-registries`, `require-always-pull-policy`, and `disallow-latest-tag`.
  - Resource limits: `require-resource-limits`.
- Kyverno installed via Helm: `helm install kyverno kyverno/kyverno --namespace kyverno`

## Resource-limits boundary decision, 2026-10-23

The owner approved limiting `require-resource-limits` to regular and init
containers. Kubernetes forbids `resources` on ephemeral containers, so requiring
those fields blocked ordinary Pod updates after adding a debugger. The other
nine container security policies continue to cover ephemeral containers through
the explicit `pods/ephemeralcontainers` subresource. Namespace scope, required
CPU/memory limits on regular/init containers and fail-closed actions are retained.
This decision grants no image exception or deployment authorization.

The normal Pod UPDATE regression failed before the correction and passed after
it; the candidate CLI suite passed 72 cases. Kyverno CLI 1.19.1 does not provide
counterfactual proof of CEL subresource matching: removing the explicit
subresource entries still passes its fixture suite. Live admission verification
remains separate from these CLI expression checks.

## Registry boundary decision, 2026-10-23

The owner approved exactly the three Redis, redis_exporter and NATS rendered
digest references recorded in [the Kubernetes deployment guide](../../k8s/README.md).
The registry policy compares their complete image strings. This approval does
not authorize other digests, tag forms or a registry-wide allowlist, and does not
authorize deployment. Release environment variables must match those exact
identities before the admission hold can be lifted for that environment.

First-party trust is restricted to the current release repository and its five
deployed workload image names; the pinned flagd identity and existing Bitnami
dependency patterns remain explicit. The current implementation uses ten
Kyverno ValidatingPolicies; the original ClusterPolicy inventory above records
the initial design.
