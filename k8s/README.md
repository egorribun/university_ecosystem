# Kubernetes Manifests

The raw files in this directory are supporting Kubernetes manifests for the
University Ecosystem platform. They are **not** a complete application
deployment artifact.

## Deployment ownership

The `charts/university-ecosystem` Helm chart is the sole canonical producer
and single canonical deployment artifact for application workloads in staging
and production. It renders and owns the
complete first-party workload set: `backend`, `gateway`, `ws-hub`,
`file-processor`, `frontend`, and `outbox-worker`. Use the chart's reviewed
values, digest-pinned images, and release gates for those environments.

The raw `k8s/` tree intentionally does not duplicate the Go service
Deployments or Services for `gateway`, `ws-hub`, and `file-processor`.
Applying `k8s/backend/` or `k8s/frontend/` by itself therefore cannot produce
a routable platform and must not be used as a staging or production release
path. Individual raw files are limited to explicitly approved supporting or
development/diagnostic operations; they do not replace the Helm release.

## Structure

- `namespace.yaml` - Application namespace
- `ingress.yaml` - Edge ingress routing and TLS configuration
- `secrets-example.yaml` - Example secrets (do not commit real secrets)
- `backend/` - Backend API deployment and service
- `frontend/` - Frontend SSR deployment and service
- `outbox-worker/` - Transactional outbox event processor worker
- `flagd/` - OpenFeature feature flag daemon
- `kyverno/` - Kyverno admission control and security policies
- `logging/` - Centralized logging (Fluent Bit / Loki)
- `monitoring/` - Prometheus monitoring, metrics, and dashboards
- `chaos/` - Chaos Mesh fault injection and resilience tests
- `jobs/` - Database migrations and batch jobs
- `spire/` - SPIFFE/SPIRE zero-trust workload attestation

## Usage

### Canonical staging/production deployment

Render and install the complete application through the Helm chart. Follow
[`charts/university-ecosystem/README.md`](../charts/university-ecosystem/README.md)
for the immutable-image, Secret, TLS, policy, and rollback gates:

```bash
helm dependency build charts/university-ecosystem
helm lint charts/university-ecosystem --strict \
  --values charts/university-ecosystem/values-staging.yaml \
  --values .staging-resolved-nonsecret-values.yaml
helm upgrade --install university charts/university-ecosystem \
  --namespace university-ecosystem \
  --values charts/university-ecosystem/values-staging.yaml \
  --values .staging-resolved-nonsecret-values.yaml \
  --atomic --wait --timeout 20m --history-max 10
```

### Supporting raw manifests

Use raw files only for an explicitly approved supporting operation, such as
creating the namespace or applying a separately reviewed policy bundle. The
following example does **not** deploy the application and must not be used as
a release shortcut:

```bash
kubectl apply -f namespace.yaml
```

Create real secrets from `secrets-example.yaml` through the configured secret
manager; never commit or apply the example file as production credentials.

## Environment Requirements

- Kubernetes 1.25+
- PostgreSQL database (external or as StatefulSet)
- Redis instance (external or as Deployment)
