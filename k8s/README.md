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
- `gateway-api/gatewayclass.yaml` - Explicit Envoy GatewayClass bootstrap for the opt-in Helm route mode
- `secrets-example.yaml` - Example secrets (do not commit real secrets)
- `backend/` - Backend API deployment and service
- `frontend/` - Frontend SSR deployment and service
- `outbox-worker/` - Transactional outbox event processor worker
- `flagd/` - OpenFeature feature flag daemon
- `kyverno/` - Kyverno admission control and security policies
- `logging/` - Centralized logging (Fluent Bit / Loki)
- `monitoring/` - Prometheus monitoring, metrics, and dashboards
- `chaos/` - Chaos Mesh fault injection and resilience tests
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

The parameterized ingress, GatewayClass bootstrap, Vault store and development
Deployments must be rendered through the repository wrapper. It allowlists the
manifest path, requires every placeholder, rejects unresolved variables and
empty/`:latest` image tags, requires `IMAGE_REGISTRY` and accepts `IMAGE_TAG`
only as a 40-character commit SHA or semver (semantic version):

```bash
IMAGE_REGISTRY=registry.example.com IMAGE_TAG="$GIT_COMMIT_SHA" \
bash scripts/apply_raw_k8s.sh k8s/backend/deployment.yaml
IMAGE_REGISTRY=registry.example.com IMAGE_TAG="$GIT_COMMIT_SHA" \
bash scripts/apply_raw_k8s.sh k8s/frontend/deployment.yaml
CERT_MANAGER_ISSUER_NAME=letsencrypt-prod \
FRONTEND_HOST=university.example.com API_HOST=api.university.example.com \
TLS_SECRET_NAME=university-tls \
bash scripts/apply_raw_k8s.sh k8s/ingress.yaml
VAULT_URL=https://vault.example.com \
bash scripts/apply_raw_k8s.sh k8s/backend/secret-store.yaml
```

The chart's opt-in `gatewayApi` route mode needs a cluster-scoped
`GatewayClass`; it does not install controller or CRDs. Install Envoy Gateway
and its CRDs from the upstream pinned charts first. When this project owns the
Gateway API CRDs, the upstream split install uses the Standard channel and
disables CRD installation in the controller chart:

```bash
helm template eg-crds oci://docker.io/envoyproxy/gateway-crds-helm \
  --version v1.9.2 \
  --set crds.gatewayAPI.enabled=true \
  --set crds.gatewayAPI.channel=standard \
  --set crds.envoyGateway.enabled=true \
  | kubectl apply --server-side -f -
helm install eg oci://docker.io/envoyproxy/gateway-helm \
  --version v1.9.2 \
  --namespace envoy-gateway-system --create-namespace \
  --set crds.enabled=false
```

If a cluster provider already owns compatible Gateway API CRDs, do not install
a second Gateway API bundle; follow the upstream provider-managed CRD flow and
keep one owner for each cluster-scoped CRD. Install cert-manager separately.
For the currently reviewed pair, the read-only preflight accepts Kubernetes
1.33–1.36, Gateway API Standard bundle v1.6.1, Envoy Gateway v1.9.2, and the
served `ClientTrafficPolicy` and cert-manager `Certificate` versions required
by the chart. The wrapper runs this preflight before creating the class:

```bash
GATEWAY_CLASS_NAME=eg \
bash scripts/apply_raw_k8s.sh k8s/gateway-api/gatewayclass.yaml
```

Set `GATEWAY_CLASS_NAME` to the same value as
`gatewayApi.gatewayClassName` in the Helm values. The manifest is explicitly
allowlisted and creates only that one GatewayClass, with a management
annotation. If the named class already exists, the wrapper checks that its
controller is Envoy Gateway and leaves the object unchanged; it refuses to
take over a class bound to another controller. The preflight and bootstrap do
not install, update, or delete CRDs, controllers, or other cluster resources.
They do not replace the Helm chart as the application release artifact.

The checked compatibility values follow the upstream [Envoy Gateway
compatibility matrix](https://gateway.envoyproxy.io/news/releases/matrix/)
and [Helm installation guide](https://gateway.envoyproxy.io/docs/install/install-helm/).

Do not call `envsubst | kubectl apply` directly and do not use this wrapper for
staging or production releases; those environments must use the Helm chart.

Create real secrets from `secrets-example.yaml` through the configured secret
manager; never commit or apply the example file as production credentials.

## Environment Requirements

- Kubernetes 1.25+
- PostgreSQL database (external or as StatefulSet)
- Redis instance (external or as Deployment)
