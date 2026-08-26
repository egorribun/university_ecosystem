# University Ecosystem Helm chart

This chart supports local development through `values.yaml` and a fail-closed,
production-like staging overlay through `values-staging.yaml`. The staging file
contains no credential material. Every `REQUIRED_*` marker must be replaced by
the release pipeline; Helm deliberately refuses to render while any marker is
unresolved.

## Staging prerequisites

Use the `university-ecosystem` namespace so the installed Kyverno and Pod
Security policies apply. Before rendering or installing the application:

1. Install pinned and healthy ingress, cert-manager, External Secrets, and
   Metrics Server controllers. Install KEDA only when `keda.enabled=true`.
2. Push signed, scanned images to an approved registry. Resolve every
   `REQUIRED_SHA256_DIGEST` to the verified `sha256:<64 lowercase hex>` digest;
   set `global.imageTag` to the exact Git SHA used to build those images.
3. Reconcile the existing Secrets below and validate names and key presence
   without printing values.
4. Make PostgreSQL, MinIO, Temporal, OTLP, Elasticsearch, SpiceDB, and flagd
   reachable over their production TLS contracts and permit the exact egress in
   NetworkPolicy.
5. Replace the required ingress hosts, verify DNS, and wait for the referenced
   TLS certificate to become Ready.

Mirrored Bitnami images require `global.security.allowInsecureImages=true`
because their original registry identity changes. This flag is acceptable only
when the release gate independently verifies the mirror digest, signature,
SBOM, and provenance. It does not permit mutable tags: staging validation still
requires immutable digests and `imagePullPolicy: Always`.

When backups are enabled, `backup.postgresImage` and
`backup.minioClientImage` must also use `repository@sha256:<digest>` and are
pulled with `Always`. Staging and production deliberately reject arbitrary
`backend.env`, `outboxWorker.env`, subchart `extraEnvVars`, sidecars,
initContainers, `extraDeploy`, and unreviewed helper containers. Add a typed,
reviewed chart field backed by an existing Secret instead of using those
escape hatches. Kubernetes Secret resource names must be DNS-1123 compliant;
Secret data keys retain the separate Kubernetes key syntax.

WS Hub is a first-party Helm workload, not an independently patched
Deployment. The release pins `wsHub.image.digest`, annotates its pod template
with the exact source SHA, and atomically owns its Deployment, Service, HPA,
PDB, ServiceAccount, ingress route, and NetworkPolicy. Its JWT/internal HMAC
keys come from `university-application`; Redis and NATS endpoints/tokens come
from `university-connections`. `/ws/ticket` terminates at the gateway and
`/ws/chat` terminates at WS Hub on port 8081.

Certificate issuer scope is typed. Staging must set `ingress.issuer.kind` to
`Issuer`, producing only the namespaced `cert-manager.io/issuer` annotation.
Production must set it to `ClusterIssuer`, producing only
`cert-manager.io/cluster-issuer`. Do not inject either annotation through the
free-form ingress annotation map.

CWV release metadata is configured only through the typed top-level `cwv`
tree. Its release SHA and frontend digest must exactly match the immutable
release inputs; `backend.env.CWV_*` overrides are not part of the deployment
contract.

## Existing Secret contract

`university-application` must contain:

- `jwt-secret`, `jwt-rsa-private-key`, `jwt-rsa-public-key`; <!-- pragma: allowlist secret -->
- `internal-hmac-secret`, `ws-hub-internal-secret`, `csrf-hmac-secret`; <!-- pragma: allowlist secret -->
- `spotify-token-secret`, `elasticsearch-password`, `spicedb-preshared-key`; <!-- pragma: allowlist secret -->
- `audit-log-secret`, `idempotency-hmac-secret`; <!-- pragma: allowlist secret -->
- `mfa-email-otp-hmac-keys`, `mfa-email-otp-active-hmac-key-id`;
- `mfa-email-delivery-keks`, `mfa-email-delivery-active-kek-id`;
- `mfa-trusted-device-hmac-keys`, `mfa-trusted-device-active-hmac-key-id`;
- `cwv-manual-tester-user-ids`, `minio-access-key`, `minio-secret-key`, and
  `temporal-api-key`.

`university-connections` must contain `database-url`, `redis-backend-url`,
`redis-gateway-url`, `redis-revocation-url`, `nats-url`, and
`nats-auth-token`. `redis-credentials` must contain `redis-password`.

`university-nats-config` must contain `nats-server.conf`. That externally
managed configuration is the canonical NATS authentication contract: it must
use the same token stored as `nats-auth-token`, enable JetStream, set
`store_dir: /data/jetstream`, and define the intended cluster routes. The chart
uses an existing Secret so the token never enters Helm release state.

The internal gateway-to-file-processor gRPC boundary uses conventional mTLS.
`university-internal-grpc-gateway-client`,
and `university-internal-grpc-file-processor-server` must each contain `tls.crt`,
`tls.key`, and `ca.crt`, issued by the same dedicated trusted CA. The server
certificate DNS SAN must match `internalGrpcMTLS.serverName` and its only TLS
extended key usage is `server auth`. The gateway leaf is a `client auth`-only
certificate whose exact canonical SPIFFE URI SAN is set as
`internalGrpcMTLS.gatewayIdentityURI`. `internalGrpcMTLS.allowedClientURIs` must
contain exactly that value, and the two referenced Secret names must be distinct. The file processor first verifies
the client chain and EKU, then rejects a valid same-CA certificate unless its URI
SAN exactly matches that allowlist. The file-processor Pod mounts only its server
key and client CA. Its Kubernetes probes are TCP-only; gateway `/health/ready`
provides the end-to-end authenticated gRPC readiness check without placing a
second client private key in the server Pod.

TLS credentials are loaded once at process startup, so rotate both Secrets
with CA overlap and perform a controlled rollout restart of gateway and
file-processor before retiring the old CA. Never set `InsecureSkipVerify` or
`-tls-no-verify`.

Render `deploymentContract.enabled=true` separately to obtain the machine-
readable Secret names and required key sets. Keep it false in the installed
release.

## Safe render and release sequence

Start from a clean, verified exact-SHA checkout and a database snapshot. Build
dependencies from `Chart.lock`, then supply the required values from an
ephemeral values file or CI environment; do not put secrets on the command line.

```powershell
helm dependency build charts/university-ecosystem
helm lint charts/university-ecosystem --strict `
  --values charts/university-ecosystem/values-staging.yaml `
  --values .staging-resolved-nonsecret-values.yaml
helm template university charts/university-ecosystem `
  --namespace university-ecosystem `
  --values charts/university-ecosystem/values-staging.yaml `
  --values .staging-resolved-nonsecret-values.yaml
```

Run schema validation, kubeconform, Kyverno policy tests, and a server-side dry
run against the rendered output. The release is admissible only when all images
are digest pinned, all containers use `Always`, all resources have CPU/memory
limits, no inline Secret is rendered, and policy reports contain no failures.

After the migration preflight and backup gate:

```powershell
helm upgrade --install university charts/university-ecosystem `
  --namespace university-ecosystem `
  --values charts/university-ecosystem/values-staging.yaml `
  --values .staging-resolved-nonsecret-values.yaml `
  --atomic --wait --timeout 20m --history-max 10
```

Gate the rollout on migration success, Deployments and StatefulSets becoming
ready, bound PVCs, working HPA metrics, a Ready TLS Certificate, zero failed
Kyverno reports, and end-to-end HTTPS/API/WebSocket/gRPC smoke journeys.

Record the previous Helm revision, image digests, and database snapshot before
upgrade. If migrations remain backward compatible, roll back with:

```powershell
helm rollback university <revision> --namespace university-ecosystem `
  --wait --timeout 20m
```

Helm rollback cannot undo a database migration. For an incompatible schema,
drain traffic, restore the verified database snapshot, and only then roll back
the application. Do not use uninstall or PVC deletion as a rollback mechanism.
