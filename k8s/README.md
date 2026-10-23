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

**Approved dependency identities:** on 2026-10-23 the owner approved exactly the
three rendered Docker Hub references below for `k8s/kyverno/cluster-policies.yaml`.
Admission compares complete image strings; other repositories, digests and tag
forms remain denied. Deployment environment digest variables must resolve to
these same references. A mismatch keeps deployment on hold pending a separate
exact-reference review; this approval does not authorize deployment.

- Chart value: `docker.io/redis:7.4.11-alpine@sha256:858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499`; rendered Pod: `docker.io/redis@sha256:858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499`.
- Chart value: `docker.io/oliver006/redis_exporter:v1.93.0@sha256:6ca518a72f30f7f576ef92963de1b91d3c3f5fd3aeac949f878bfda183587820`; rendered Pod: `docker.io/oliver006/redis_exporter@sha256:6ca518a72f30f7f576ef92963de1b91d3c3f5fd3aeac949f878bfda183587820`.
- Chart value: `docker.io/nats:2.15.0-alpine@sha256:ac8f88a6494bffc2c2a5289a0ca61cb28a9145c11ba5677cf24265d07f46d8d4`; rendered Pod: `docker.io/nats@sha256:ac8f88a6494bffc2c2a5289a0ca61cb28a9145c11ba5677cf24265d07f46d8d4`.

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

Rendering and admission are separate trust decisions. The wrapper checks that
`IMAGE_REGISTRY` is syntactically valid; it does not authorize that publisher.
In `university-ecosystem`, the registry policy allows the exact first-party
publisher path `ghcr.io/egorribun/university_ecosystem/` for only `backend`,
`frontend`, `gateway`, `ws-hub`, and `file-processor`, plus the exact pinned
`ghcr.io/open-feature/flagd:v0.17.0@sha256:c9f21380dfe51d3ad662a116bc350c7692dead7a8d1e640aa0f6b40cd3d966df`
image, the three owner-approved Docker Hub references above and the existing
digest-pinned Bitnami dependency patterns. The release
workflow builds `caddy`, but the application chart does not deploy it into this
namespace. The chart's default `university-*` image names are development/test
references and are not trusted by this policy. The `registry.example.com` values
above are placeholders: the wrapper can render them, but Kyverno rejects them at
pod admission. Other custom registry
or repository paths require an administrator-reviewed update naming the exact
publisher and workload images; an application workload cannot opt itself into
trust by setting pod or namespace metadata.

The chart's opt-in `gatewayApi` route mode needs a cluster-scoped
`GatewayClass`; the application chart itself does not install Gateway API
controllers or CRDs. For the repository's local kind acceptance path, use the
run-owned helper, which installs the pinned Gateway API/Envoy Gateway
components and cert-manager, then creates a run-specific local CA:

```bash
python scripts/kind_gateway_api.py create \
  --node-image kindest/node:v1.36.4@sha256:099e049362a1526b2db71494e1947aae99bd16290d7c895f2b7ea312e3cbfaed
python scripts/kind_gateway_api.py prepare --run-id <printed-run-id>
python scripts/kind_gateway_api.py preflight --run-id <printed-run-id>
python scripts/kind_gateway_api.py smoke --run-id <printed-run-id>
python scripts/kind_gateway_api.py ca-export --run-id <printed-run-id>
# only after the acceptance evidence has been saved and verified:
python scripts/kind_gateway_api.py teardown --run-id <printed-run-id>
```

The pinned cert-manager v1.21.2 Helm release installs its CRDs and enables
Gateway API integration after the Gateway API CRDs are present. The helper
creates a run-owned self-signed `ClusterIssuer` for local acceptance. The
export command writes only the public CA certificate under the local run-state
directory. Pass that file explicitly to a client, for example with
`curl --cacert <path-to-exported-ca.crt>`; it does not modify the operating
system trust store or export the CA private key. This CA is only for disposable
local kind acceptance and is not a production or public trust root.

`teardown` is a destructive, explicit command: it deletes the complete
run-owned kind cluster and its Kubernetes data after rechecking the local run
record, kube context, owner markers, the single control-plane node, its Docker
cluster label, recorded node image, and matching full Docker container ID in a
fresh pre-delete inspection. The Kubernetes Node need not carry kind's Docker
cluster label; if present on the Node, that label must match. It keeps the
local run record and does not delete a separately managed local-registry
container or volume. If a run-owned registry should be stopped, use
`registry-stop` before teardown; its
volume remains available. If the cluster is already absent, teardown reports
that fact without issuing a delete. Stopped or unreachable clusters fail closed
and require their identity to be restored before teardown.

For another cluster, the cluster owner must install and manage compatible
Gateway API, Envoy Gateway, and cert-manager resources. Do not run this
run-owned kind installer against a provider-managed cluster. When this project
owns the Gateway API CRDs, the upstream split install uses the Standard channel
and disables CRD installation in the controller chart:

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
keep one owner for each cluster-scoped CRD. For the currently reviewed pair,
the read-only preflight accepts Kubernetes 1.33–1.36, Gateway API Standard
bundle v1.6.1, Envoy Gateway v1.9.2, and the served `ClientTrafficPolicy` and
cert-manager `Certificate` versions required by the chart. The raw-manifest
wrapper runs this preflight before creating the class:

```bash
GATEWAY_CLASS_NAME=eg \
bash scripts/apply_raw_k8s.sh k8s/gateway-api/gatewayclass.yaml
```

Set `GATEWAY_CLASS_NAME` to the same value as
`gatewayApi.gatewayClassName` in the Helm values. The manifest is explicitly
allowlisted and creates only that one GatewayClass, with a management
annotation. If the named class already exists, the wrapper checks that its
controller is Envoy Gateway and leaves the object unchanged; it refuses to
take over a class bound to another controller. The raw-manifest preflight and
bootstrap do not install, update, or delete CRDs, controllers, or other cluster
resources. The kind helper's `prepare` workflow is separate and run-owned;
neither path replaces the Helm chart as the application release artifact.

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
