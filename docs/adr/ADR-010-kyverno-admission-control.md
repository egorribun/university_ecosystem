# ADR-010: Kyverno Admission Control Policies

## Status
Accepted — switched from Audit to Enforce mode (Wave 13, 2026-03-17)

## Context

The Kubernetes cluster lacked policy enforcement at the admission layer. Deployments could:
- Run containers as root without restriction
- Omit resource limits (CPU/memory), risking noisy-neighbor OOM
- Use `latest` image tags, breaking reproducibility
- Mount host paths or escalate privileges

While `securityContext` was set in Helm chart templates, there was no cluster-level backstop if a chart was misconfigured or if developers applied ad-hoc manifests bypassing Helm.

## Decision

Deployed **Kyverno** as the Kubernetes admission controller with **5 ClusterPolicies**:

1. **`disallow-privilege-escalation`** — Rejects any container with `allowPrivilegeEscalation: true`.
2. **`require-non-root`** — Requires `runAsNonRoot: true` in pod security context.
3. **`disallow-host-paths`** — Blocks hostPath volume mounts (prevents container escape via host filesystem).
4. **`require-readonly-root`** — Requires `readOnlyRootFilesystem: true`.
5. **`disallow-latest-tag`** — Blocks image references without an explicit tag or digest.

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

- `k8s/kyverno/cluster-policies.yaml` — 5 ClusterPolicies (all in Enforce mode)
- Kyverno installed via Helm: `helm install kyverno kyverno/kyverno --namespace kyverno`
