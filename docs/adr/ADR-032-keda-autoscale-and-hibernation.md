# ADR-032: KEDA Event-Driven Auto-Scaling and Off-Peak Resource Hibernation

## Status
Proposed — Vector 17 (2026-07-26)

## Context

The `university-ecosystem` platform relies on both synchronous HTTP services (`frontend`, `gateway`, `backend`) and asynchronous background queue workers (`outbox-worker`, `file-processor`, `backend` task consumers).

Prior to Vector 17:
1. **Resource Inefficiency in Non-Production Environments**: Non-production clusters (`dev`, `staging`) maintained static baseline pod replica counts 24 hours a day, 7 days a week. During off-peak hours (nights and weekends), zero developer or testing activity occurred, yet containers continuously consumed compute requests (CPU and RAM allocations), driving up cloud infrastructure costs.
2. **Coarse-Grained Workload Auto-Scaling**: Background event workers operated under fixed replica limits or legacy metric adapters that reacted slowly to sudden event stream spikes (e.g. outbox CDC bursts or file processing backlogs), causing transient message lag.
3. **Controller Deadlock Risk**: Native Kubernetes `HorizontalPodAutoscaler` (HPA) resources and hardcoded `spec.replicas` counts in Helm deployment manifests risked conflicting with external autoscaling controllers if replica fields were not properly guarded during Helm release upgrades.

## Decision

We adopt **KEDA** (Kubernetes Event-driven Autoscaling, `keda.sh/v1alpha1`) and an **Off-Peak Resource Hibernation** (scale-to-zero) strategy for the `university-ecosystem` microservices platform.

Key technical choices:
1. **Event-Driven Workload Scalers**:
   - `outbox-worker`: KEDA `postgresql` scaler monitoring unprocessed rows in `stored_events` (`targetQueryValue: 50`).
   - `file-processor`: Native KEDA `nats-jetstream` scaler monitoring `FILES_PROCESS` stream lag (`lagThreshold: 10`).
   - `backend` task workers: Dual KEDA triggers — `redis` scaler monitoring queue depth (`backend_tasks`, `listLength: 20`) and `nats-jetstream` scaler monitoring `TASK_QUEUE` stream lag (`lagThreshold: 25`).
2. **Off-Peak Resource Hibernation**:
   - Introduce KEDA `cron` scalers for non-critical workloads (`frontend`, `backend`, `gateway`, `fileProcessor`, `outboxWorker`) in non-production environments (`hibernation.enabled: true`).
3. **Decoupled Secret Authentication**:
   - Use `TriggerAuthentication` custom resources referencing standard Kubernetes Secrets (`redis-credentials`, `backend-secrets` / `nats-credentials`) to eliminate plaintext secret exposure in scaling manifests.
4. **Helm & Deployment Guard Architecture**:
   - Suppress `replicas:` in `backend-deployment.yaml`, `frontend-deployment.yaml`, and `gateway-deployment.yaml` when KEDA or hibernation is enabled.
   - Suppress native `HorizontalPodAutoscaler` in `hpa.yaml` when KEDA backend scaling is active to prevent dual-controller reconciliation deadlocks.

## FinOps Strategy & Economic Objectives

### Non-Production Off-Peak Compute Savings
- **Off-Peak Window**: Weekdays 20:00 to 07:00 UTC (`0 20 * * 1-5` to `0 7 * * 1-5`) and Weekends (Saturday 00:00 to Monday 07:00 UTC).
- **FinOps Calculation**:
  - Total hours in a calendar week = 168 hours.
  - Active operational hours = 13 hours/day × 5 weekdays = 65 hours.
  - Off-peak hibernation hours = 103 hours/week (~61.3% of total weekly time).
- **Impact**: Automatically scaling non-production workload pod replicas to 0 during off-peak windows reduces requested CPU core-hours and memory allocations by **~60%**, yielding substantial cloud compute cost savings.

### Dynamic Scale-from-Zero for Queued Workloads
For event-driven background workers (`outbox-worker`, `file-processor`, `backend`), even during off-peak hibernation, if an asynchronous message enters NATS JetStream or Redis, KEDA activates the queue trigger, scales the worker from 0 to 1+ replicas to drain the backlog, and returns to 0 when idle.

## Technical Architecture & Scaler Specifications

### 1. TriggerAuthentication (`keda-trigger-auth.yaml`)
- `TriggerAuthentication/university-ecosystem-trigger-auth-redis`: References secret `redis-credentials`, key `redis-password`.
- `TriggerAuthentication/university-ecosystem-trigger-auth-nats`: References secret `nats-credentials` (or `backend-secrets`), key `nats-token` (or `NATS_AUTH_TOKEN`).

### 2. ScaledObjects (`keda-scaledobjects.yaml` & `k8s/outbox-worker/scaledobject.yaml`)

| Workload | Target Deployment | Trigger Type(s) | Metric Target / Stream | Default Threshold | Scale Range (Min/Max) |
|---|---|---|---|---|---|
| `outbox-worker` | `outbox-worker` | `postgresql`, `cron` | Unprocessed `stored_events` rows | `targetQueryValue: 50` | 1 - 10 (0 in hibernation) |
| `file-processor` | `file-processor` | `nats-jetstream`, `cron` | `FILES_PROCESS` stream lag | `lagThreshold: 10` | 1 - 10 (0 in hibernation) |
| `backend` | `backend` | `redis`, `nats-jetstream`, `cron` | `backend_tasks` list len / `TASK_QUEUE` lag | `listLength: 20`, `lagThreshold: 25` | 2 - 8 (0 in hibernation) |
| `frontend` | `frontend` | `cron` (hibernation) | Time schedule (off-peak) | `desiredReplicas: 0` | 2 - 5 (0 in hibernation) |
| `gateway` | `gateway` | `cron` (hibernation) | Time schedule (off-peak) | `desiredReplicas: 0` | 2 - 5 (0 in hibernation) |

## Operational Safety Guarantees

1. **Production Safety Lock**:
   - `hibernation.enabled` defaults to `false` in `charts/university-ecosystem/values.yaml`.
   - Production releases MUST keep `hibernation.enabled: false` to guarantee 24/7 high availability for customer-facing production services.
2. **Kyverno Policy Compliance**:
   - Custom resources (`ScaledObject`, `TriggerAuthentication`) and spawned pods adhere strictly to cluster Kyverno policies (`disallow-latest-tag`, `require-run-as-non-root`, `disallow-privilege-escalation`, `require-readonly-root-filesystem`).
3. **Database Connection Pool Safeguards**:
   - `maxReplicaCount` limits (`outboxWorker: 10`, `fileProcessor: 10`, `backend: 8`) prevent worker replica explosions from exhausting PostgreSQL PgBouncer connection pools (`pool_size=10`).
4. **Flapping Prevention & Cooldown Windows**:
   - `cooldownPeriod` (60s - 300s) and `pollingInterval` (15s - 30s) prevent rapid scaling thrashing during transient load spikes.
   - HPA stabilization windows (`scaleUp: 30s`, `scaleDown: 300s`) dampen scaling oscillations.

## Alternatives Considered

1. **Native HPA with Custom Metrics Adapter (Prometheus Adapter)**:
   - *Rejected*: Required maintaining custom Prometheus adapter rules, complex metric query latency, and lacked native support for scale-to-zero hibernation.
2. **CronJobs with Manual `kubectl scale` Scripts**:
   - *Rejected*: Imperative shell scripts are fragile, hard to audit, lack declarative GitOps representation, and fail to scale back up if a deployment job crashes.
3. **Karpenter Node Autoscaling Only**:
   - *Rejected*: Node-level autoscaling cannot scale down nodes if pod replicas remain statically allocated. KEDA pod scale-to-zero is required to unlock node-level deprovisioning.

## Consequences

### Positive
- Direct reduction of ~60% in non-production compute infrastructure costs.
- Asynchronous workers scale rapidly during event backlog spikes, reducing end-to-end processing latency.
- Zero credential leakage in custom resources through standard `TriggerAuthentication` bindings.
- Fully declarative Helm and GitOps integration.

### Negative
- Requires KEDA operator CRDs (`keda.sh/v1alpha1`) to be installed in clusters where `keda.enabled=true`.
- Potential cold-start delay (~5-10 seconds) when off-peak event arrives while worker replica count is 0.

## Rollout Plan & Migration Strategy

1. **Phase 1 (Helm & Manifest Rollout)**: Deploy updated Helm chart (`charts/university-ecosystem`) and standalone manifests (`k8s/outbox-worker/scaledobject.yaml`).
2. **Phase 2 (Dev/Staging Activation)**: Enable `keda.enabled: true` and `hibernation.enabled: true` in non-production values overrides.
3. **Phase 3 (Production Scaling)**: Enable `keda.enabled: true` and `hibernation.enabled: false` in production values overrides for event-driven queue scaling while maintaining 24/7 baseline availability.

## Verification & Validation Method

1. **Helm Lint**: provide the gateway secret plus the file-processor RSA public key, MinIO credentials, and Temporal API key required by the chart.
2. **Helm Template Dry-Run (KEDA & Hibernation Enabled)**:
   `helm template test-rel charts/university-ecosystem -f values.dev-secrets.yaml --set keda.enabled=true --set hibernation.enabled=true`
3. **Helm Template Dry-Run (Production Baseline)**:
   `helm template test-rel charts/university-ecosystem -f values.prod-secrets.yaml --set keda.enabled=false --set hibernation.enabled=false`
4. **Standalone Manifest Check**:
   `kubectl apply --dry-run=client --validate=false -f k8s/outbox-worker/scaledobject.yaml`
