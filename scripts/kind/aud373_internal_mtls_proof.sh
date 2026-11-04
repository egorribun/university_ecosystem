#!/usr/bin/env bash
# AUD-373 proof: the gateway-to-backend hop and the backend listener use SPIFFE mTLS.
#
# Creates a uniquely named disposable kind cluster, installs SPIRE from k8s/spire
# plus the upstream SPIFFE CSI driver, installs the university-ecosystem chart with
# internalHttpMTLS.enabled=true, and proves:
#   gateway-hop      gateway -> backend request succeeds over mTLS (JWKS relayed through the gateway)
#   no-svid-tls      a pod without an SVID is rejected by the backend TLS listener
#   plaintext-http   a plaintext HTTP request to the backend TLS port is rejected
# Every check prints one PASS or FAIL line. The script exits non-zero on any failure.
# Diagnostics (no Secret objects, no helm values, no environment dumps) are collected
# on every exit, and the cluster is deleted in the EXIT trap.
#
# Usage: scripts/kind/aud373_internal_mtls_proof.sh
# Requires Linux amd64 with a running Docker daemon. Tools are downloaded at the pinned
# versions below and checked against their version-specific official checksum files.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
readonly ROOT_DIR

# Pinned external tools, verified against the official files for those exact versions.
readonly KIND_VERSION="v0.31.0"
readonly KIND_URL="https://github.com/kubernetes-sigs/kind/releases/download/${KIND_VERSION}/kind-linux-amd64"
readonly KUBECTL_VERSION="v1.36.4"
readonly KUBECTL_URL="https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl"
readonly HELM_VERSION="v4.2.4"
readonly HELM_URL="https://get.helm.sh/helm-${HELM_VERSION}-linux-amd64.tar.gz"
# Upstream SPIRE chart 0.30.4 (SPIRE 1.15.5). Only its spiffe-csi-driver subchart is installed.
readonly SPIRE_CHART_URL="https://github.com/spiffe/helm-charts-hardened/releases/download/spire-0.30.4/spire-0.30.4.tgz"
readonly SPIRE_CHART_SHA256="a0a442d8b03fa9b7ba733326700e64a6184a466a84ae5a07eda4332a0afd69ae"
# Must equal socket_path in k8s/spire/spire-agent.yaml; operators use the same value (k8s/spire/README.md).
readonly AGENT_SOCKET_PATH="/run/spire/sockets/agent.sock"
# Existing WIP pin: Docker Official Image registry 2.8.3, resolved by digest.
readonly REGISTRY_IMAGE="registry:2.8.3@sha256:a3d8aaa63ed8681a604f1dea0aa03f100d5895b6a58ace528858a7b332415373"

RUN_SUFFIX="$(openssl rand -hex 6)"
readonly RUN_SUFFIX
readonly CLUSTER_NAME="ue-r9-aud373-${RUN_SUFFIX}"
readonly NAMESPACE="university-ecosystem"
readonly SPIRE_NAMESPACE="spire"
readonly RELEASE="ue"
readonly BACKEND_SVC="${RELEASE}-university-ecosystem-backend"
readonly GATEWAY_SVC="${RELEASE}-university-ecosystem-gateway"
readonly BACKEND_PORT="8000"
readonly GATEWAY_PORT="8080"
readonly TRUST_DOMAIN="university.ecosystem"
readonly BACKEND_SPIFFE_ID="spiffe://${TRUST_DOMAIN}/ns/${NAMESPACE}/sa/${RELEASE}-backend"
readonly GATEWAY_SPIFFE_ID="spiffe://${TRUST_DOMAIN}/ns/${NAMESPACE}/sa/${RELEASE}-gateway"
readonly WS_HUB_SPIFFE_ID="spiffe://${TRUST_DOMAIN}/ns/${NAMESPACE}/sa/${RELEASE}-ws-hub"
readonly FILE_PROCESSOR_SPIFFE_ID="spiffe://${TRUST_DOMAIN}/ns/${NAMESPACE}/sa/${RELEASE}-file-processor"
readonly IMAGE_TAG="ue-r9-aud373-${RUN_SUFFIX}"
readonly LOCAL_REGISTRY_NAME="ue-r9-aud373-registry-${RUN_SUFFIX}"
LOCAL_REGISTRY_ADDRESS=""
BACKEND_IMAGE=""
GATEWAY_IMAGE=""

WORK_DIR="$(mktemp -d)"
readonly WORK_DIR
readonly DIAG_DIR="${UE_KIND_DIAG_DIR:-${RUNNER_TEMP:-${TMPDIR:-/tmp}}/aud373-diagnostics}"
export KUBECONFIG="${WORK_DIR}/kubeconfig"
export PATH="${WORK_DIR}/bin:${PATH}"
FAILURES=0
CLUSTER_CREATED=0
REGISTRY_CREATED=0

log() {
  printf '%s\n' "$*" >&2
}

require_platform() {
  if [[ "$(uname -s)" != "Linux" || "$(uname -m)" != "x86_64" ]]; then
    log "this proof runs on Linux x86_64 only (CI ubuntu-24.04)"
    exit 2
  fi
  docker info >/dev/null
}

verify_checksum() {
  local checksum_file="$1" artifact="$2" expected_name="$3" checksum digest
  checksum="$(cat "$checksum_file")" || return 1
  digest="${checksum%% *}"
  [[ "$digest" =~ ^[0-9a-f]{64}$ ]] || return 1
  [[ "$checksum" == "$digest" || "$checksum" == "$digest  $expected_name" ||
     "$checksum" == "$digest *$expected_name" ]] || return 1
  printf '%s  %s\n' "$digest" "$artifact" | sha256sum --check --status
}

download_verified() {
  local url="$1" checksum_url="$2" dest="$3" expected_name="$4"
  curl --fail --silent --show-error --location --retry 3 --output "$dest" "$url" || return 1
  curl --fail --silent --show-error --location --retry 3 --output "${dest}.sha256" "$checksum_url" || return 1
  verify_checksum "${dest}.sha256" "$dest" "$expected_name"
}

download_pinned() {
  local url="$1" sha256="$2" dest="$3"
  curl --fail --silent --show-error --location --retry 3 --output "$dest" "$url" || return 1
  printf '%s  %s\n' "$sha256" "$dest" | sha256sum --check --status
}

install_tools() {
  mkdir -p "${WORK_DIR}/bin"
  download_verified "$KIND_URL" "${KIND_URL}.sha256sum" "${WORK_DIR}/bin/kind" kind-linux-amd64
  download_verified "$KUBECTL_URL" "${KUBECTL_URL}.sha256" "${WORK_DIR}/bin/kubectl" kubectl
  download_verified "$HELM_URL" "${HELM_URL}.sha256sum" "${WORK_DIR}/helm.tar.gz" "helm-${HELM_VERSION}-linux-amd64.tar.gz"
  tar -xzf "${WORK_DIR}/helm.tar.gz" -C "${WORK_DIR}" linux-amd64/helm
  mv "${WORK_DIR}/linux-amd64/helm" "${WORK_DIR}/bin/helm"
  chmod 0755 "${WORK_DIR}/bin/kind" "${WORK_DIR}/bin/kubectl" "${WORK_DIR}/bin/helm"
  kind version | grep -q "^kind ${KIND_VERSION} "
  test "$(helm version --template '{{.Version}}')" = "$HELM_VERSION"
}

# Random material is generated per run. Nothing here is a committed or reusable credential.
random_hex() {
  openssl rand -hex 32
}

random_fernet() {
  openssl rand -base64 32 | tr '+/' '-_'
}

write_secret_file() {
  local name="$1" value="$2"
  mkdir -p "${WORK_DIR}/secret-files"
  printf '%s' "$value" > "${WORK_DIR}/secret-files/${name}"
}

write_values_file() {
  local postgres_password redis_password nats_token
  local backend_fields
  postgres_password="$(random_hex)"
  redis_password="$(random_hex)"
  nats_token="$(random_hex)"
  write_secret_file "postgres-password" "$postgres_password"
  write_secret_file "redis-password" "$redis_password"
  write_secret_file "database-url" "postgresql+asyncpg://ue_app:${postgres_password}@ue-postgres:5432/university"
  write_secret_file "migration-database-url" "postgresql+asyncpg://ue_app:${postgres_password}@ue-postgres:5432/university"
  write_secret_file "redis-backend-url" "redis://:${redis_password}@${RELEASE}-redis-master:6379/0"
  write_secret_file "redis-gateway-url" "redis://:${redis_password}@${RELEASE}-redis-master:6379/3"
  write_secret_file "rate-limit-storage-uri" "redis://:${redis_password}@${RELEASE}-redis-master:6379/1"
  write_secret_file "redis-revocation-url" "redis://:${redis_password}@${RELEASE}-redis-master:6379/0"
  write_secret_file "nats-url" "nats://${RELEASE}-nats:4222"
  write_secret_file "nats-auth-token" "$nats_token"
  write_secret_file "keda-postgresql-url" "postgresql://ue_app:${postgres_password}@ue-postgres:5432/university"
  write_secret_file "backup-database-url" "postgresql://ue_app:${postgres_password}@ue-postgres:5432/university"
  write_secret_file "gateway-jwt" "$(random_hex)"
  openssl genrsa -out "${WORK_DIR}/jwt-private.pem" 2048 2>/dev/null
  backend_fields="$(cat <<EOF
backend:
  image:
    repository: "${LOCAL_REGISTRY_ADDRESS}/university-backend"
  config:
    internalHMACSecret: "$(random_hex)"
    wsHubInternalSecret: "$(random_hex)"
    csrfHMACSecret: "$(random_hex)"
    spotifyTokenSecret: "$(random_hex)"
    elasticsearchPassword: "$(random_hex)"
    spicedbPresharedKey: "$(random_hex)"
    auditLogSecret: "$(random_hex)"
    tokenHMACSecret: "$(random_hex)"
    idempotencyHMACSecret: "$(random_hex)"
    mfaTotpEncryptionKeys: "kid1:$(random_fernet)"
    mfaTotpActiveEncryptionKeyId: "kid1"
    mfaEmailOtpHMACKeys: "kid1:$(random_hex)"
    mfaEmailOtpActiveHMACKeyId: "kid1"
    mfaEmailDeliveryKEKs: "kid1:$(random_fernet)"
    mfaEmailDeliveryActiveKEKId: "kid1"
    mfaTrustedDeviceHMACKeys: "kid1:$(random_hex)"
    mfaTrustedDeviceActiveHMACKeyId: "kid1"
EOF
)"
  cat > "${WORK_DIR}/values.yaml" <<EOF
global:
  environment: development
  imageTag: "${IMAGE_TAG}"
fileProcessor:
  enabled: false
wsHub:
  enabled: false
migrations:
  enabled: false
outboxWorker:
  enabled: false
internalHttpMTLS:
  enabled: true
  trustDomain: "${TRUST_DOMAIN}"
  backendSpiffeID: "${BACKEND_SPIFFE_ID}"
  gatewaySpiffeID: "${GATEWAY_SPIFFE_ID}"
  wsHubSpiffeID: "${WS_HUB_SPIFFE_ID}"
  fileProcessorSpiffeID: "${FILE_PROCESSOR_SPIFFE_ID}"
gateway:
  image:
    repository: "${LOCAL_REGISTRY_ADDRESS}/university-gateway"
redis:
  metrics:
    passwordFileInitImage:
      repository: "${LOCAL_REGISTRY_ADDRESS}/university-backend"
${backend_fields}
EOF
}

# Read the existing reviewed pins rather than maintaining independent copies. Refuse
# missing, malformed, or ambiguous sources instead of silently selecting a match.
read_tracked_pin() {
  local file="$1" expression="$2"
  local -a matches=()
  mapfile -t matches < <(sed -nE "$expression" "$file")
  if [[ "${#matches[@]}" != "1" ]]; then
    log "expected exactly one matching image pin in $file"
    return 1
  fi
  printf '%s' "${matches[0]}"
}

create_cluster() {
  local node_image clusters
  node_image="$(read_tracked_pin "${ROOT_DIR}/k8s/README.md" 's|^[[:space:]]*--node-image (kindest/node:v1\.36\.4@sha256:[0-9a-f]{64})[[:space:]]*$|\1|p')"
  cat > "${WORK_DIR}/kind-config.yaml" <<EOF
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
containerdConfigPatches:
  - |-
    [plugins."io.containerd.grpc.v1.cri".registry]
      config_path = "/etc/containerd/certs.d"
nodes:
  - role: control-plane
    image: ${node_image}
EOF
  clusters="$(kind get clusters)" || return 1
  if grep -Fxq "$CLUSTER_NAME" <<<"$clusters"; then
    log "refusing to reuse existing cluster $CLUSTER_NAME"
    return 1
  fi
  kind create cluster --name "$CLUSTER_NAME" --config "${WORK_DIR}/kind-config.yaml" \
    --kubeconfig "$KUBECONFIG" --wait 300s
  CLUSTER_CREATED=1
}

start_local_registry() {
  local endpoint node nodes
  if docker inspect --type container "$LOCAL_REGISTRY_NAME" >/dev/null 2>&1; then
    log "refusing to reuse existing container $LOCAL_REGISTRY_NAME"
    return 1
  fi
  docker run --detach --name "$LOCAL_REGISTRY_NAME" \
    --publish "127.0.0.1::5000" "$REGISTRY_IMAGE" >/dev/null
  REGISTRY_CREATED=1
  endpoint="$(docker port "$LOCAL_REGISTRY_NAME" 5000/tcp)" || return 1
  if [[ ! "$endpoint" =~ ^127\.0\.0\.1:([0-9]{1,5})$ ]]; then
    log "registry did not publish a single loopback port"
    return 1
  fi
  # Reuse the actual IPv4 binding: localhost may resolve to an unbound ::1.
  LOCAL_REGISTRY_ADDRESS="$endpoint"
  BACKEND_IMAGE="${LOCAL_REGISTRY_ADDRESS}/university-backend:${IMAGE_TAG}"
  GATEWAY_IMAGE="${LOCAL_REGISTRY_ADDRESS}/university-gateway:${IMAGE_TAG}"
  docker network connect kind "$LOCAL_REGISTRY_NAME"
  nodes="$(kind get nodes --name "$CLUSTER_NAME")" || return 1
  [[ -n "$nodes" ]] || return 1
  while read -r node; do
    docker exec "$node" mkdir -p "/etc/containerd/certs.d/${LOCAL_REGISTRY_ADDRESS}"
    printf '[host."http://%s:5000"]\n  capabilities = ["pull", "resolve"]\n' "$LOCAL_REGISTRY_NAME" |
      docker exec --interactive "$node" sh -c "cat > /etc/containerd/certs.d/${LOCAL_REGISTRY_ADDRESS}/hosts.toml"
  done <<<"$nodes"
}

build_and_push_images() {
  docker build --file "${ROOT_DIR}/backend.Dockerfile" \
    --tag "$BACKEND_IMAGE" "$ROOT_DIR"
  docker build --file "${ROOT_DIR}/services/gateway/Dockerfile" \
    --tag "$GATEWAY_IMAGE" "$ROOT_DIR"
  docker push "$BACKEND_IMAGE"
  docker push "$GATEWAY_IMAGE"
}

install_spire() {
  # The repo manifests are the SPIRE contract. Only the agent ConfigMap changes, and only
  # for kind: its kubelet serving certificate is self-signed, so the k8s workload attestor
  # needs skip_kubelet_verification. Production keeps the manifest unchanged.
  kubectl apply -f "${ROOT_DIR}/k8s/spire/spire-rbac.yaml"
  kubectl apply -f "${ROOT_DIR}/k8s/spire/spire-server.yaml"
  awk '
    /WorkloadAttestor "k8s" \{/ { in_attestor = 1 }
    in_attestor && /plugin_data \{\}/ {
      sub(/plugin_data \{\}/, "plugin_data { skip_kubelet_verification = true }")
      in_attestor = 0
    }
    { print }
  ' "${ROOT_DIR}/k8s/spire/spire-agent.yaml" > "${WORK_DIR}/spire-agent-kind.yaml"
  test "$(grep -c 'skip_kubelet_verification = true' "${WORK_DIR}/spire-agent-kind.yaml")" = "1"
  kubectl apply -f "${WORK_DIR}/spire-agent-kind.yaml"
  kubectl -n "$SPIRE_NAMESPACE" rollout status statefulset/spire-server --timeout=300s
  kubectl -n "$SPIRE_NAMESPACE" rollout status daemonset/spire-agent --timeout=300s
  # Install only the SPIFFE CSI driver from the pinned chart. Every other subchart is off,
  # and the driver socket path is the agent socket written by spire-agent.yaml.
  download_pinned "$SPIRE_CHART_URL" "$SPIRE_CHART_SHA256" "${WORK_DIR}/spire-chart.tgz"
  mkdir -p "${WORK_DIR}/spire-chart"
  tar -xzf "${WORK_DIR}/spire-chart.tgz" -C "${WORK_DIR}/spire-chart"
  helm upgrade --install spire-csi "${WORK_DIR}/spire-chart/spire" \
    --namespace "$SPIRE_NAMESPACE" \
    --set spire-server.enabled=false \
    --set spire-agent.enabled=false \
    --set spiffe-oidc-discovery-provider.enabled=false \
    --set spire-identity-exchange.enabled=false \
    --set spike-keeper.enabled=false \
    --set spike-nexus.enabled=false \
    --set spike-pilot.enabled=false \
    --set tornjak-frontend.enabled=false \
    --set "spiffe-csi-driver.agentSocketPath=${AGENT_SOCKET_PATH}" \
    --wait --timeout 300s
}

wait_for_agent_id() {
  local output agent_id
  for _ in $(seq 1 60); do
    output="$(kubectl -n "$SPIRE_NAMESPACE" exec spire-server-0 -- /opt/spire/bin/spire-server agent list 2>/dev/null || true)"
    agent_id="$(printf '%s\n' "$output" | awk -F': ' '/SPIFFE ID/ { print $2; exit }')"
    if [[ -n "$agent_id" ]]; then
      printf '%s' "$agent_id"
      return 0
    fi
    sleep 5
  done
  log "no attested SPIRE agent appeared"
  return 1
}

create_spire_entry() {
  local agent_id="$1" spiffe_id="$2" service_account="$3"
  kubectl -n "$SPIRE_NAMESPACE" exec spire-server-0 -- /opt/spire/bin/spire-server entry create \
    -parentID "$agent_id" \
    -spiffeID "$spiffe_id" \
    -selector "k8s:ns:${NAMESPACE}" \
    -selector "k8s:sa:${service_account}" >/dev/null
}

register_workloads() {
  local agent_id
  agent_id="$(wait_for_agent_id)"
  create_spire_entry "$agent_id" "$BACKEND_SPIFFE_ID" "${RELEASE}-backend"
  create_spire_entry "$agent_id" "$GATEWAY_SPIFFE_ID" "${RELEASE}-gateway"
}

deploy_stack() {
  local postgres_image
  postgres_image="$(read_tracked_pin "${ROOT_DIR}/charts/university-ecosystem/values.yaml" 's|^[[:space:]]*postgresImage:[[:space:]]*"(pgvector/pgvector:pg17@sha256:[0-9a-f]{64})"[[:space:]]*$|\1|p')"
  kubectl create namespace "$NAMESPACE" --dry-run=client --output=yaml | kubectl apply -f -
  write_values_file
  kubectl -n "$NAMESPACE" create secret generic redis-credentials \
    --from-file="redis-password=${WORK_DIR}/secret-files/redis-password" \
    --dry-run=client --output=yaml | kubectl apply -f -
  kubectl -n "$NAMESPACE" create secret generic ue-postgres-credentials \
    --from-file="postgres-password=${WORK_DIR}/secret-files/postgres-password" \
    --dry-run=client --output=yaml | kubectl apply -f -
  kubectl -n "$NAMESPACE" create secret generic university-connections \
    --from-file="database-url=${WORK_DIR}/secret-files/database-url" \
    --from-file="migration-database-url=${WORK_DIR}/secret-files/migration-database-url" \
    --from-file="redis-backend-url=${WORK_DIR}/secret-files/redis-backend-url" \
    --from-file="redis-gateway-url=${WORK_DIR}/secret-files/redis-gateway-url" \
    --from-file="rate-limit-storage-uri=${WORK_DIR}/secret-files/rate-limit-storage-uri" \
    --from-file="redis-revocation-url=${WORK_DIR}/secret-files/redis-revocation-url" \
    --from-file="nats-url=${WORK_DIR}/secret-files/nats-url" \
    --from-file="nats-auth-token=${WORK_DIR}/secret-files/nats-auth-token" \
    --from-file="keda-postgresql-url=${WORK_DIR}/secret-files/keda-postgresql-url" \
    --from-file="backup-database-url=${WORK_DIR}/secret-files/backup-database-url" \
    --dry-run=client --output=yaml | kubectl apply -f -
  cat > "${WORK_DIR}/postgres.yaml" <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ue-postgres
  namespace: ${NAMESPACE}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ue-postgres
  template:
    metadata:
      labels:
        app: ue-postgres
    spec:
      automountServiceAccountToken: false
      containers:
        - name: postgres
          image: ${postgres_image}
          env:
            - name: POSTGRES_USER
              value: ue_app
            - name: POSTGRES_DB
              value: university
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: ue-postgres-credentials
                  key: postgres-password
          ports:
            - containerPort: 5432
          readinessProbe:
            exec:
              command: ["pg_isready", "-U", "ue_app", "-d", "university"]
            periodSeconds: 5
          volumeMounts:
            - name: data
              mountPath: /var/lib/postgresql/data
      volumes:
        - name: data
          emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: ue-postgres
  namespace: ${NAMESPACE}
spec:
  selector:
    app: ue-postgres
  ports:
    - port: 5432
      targetPort: 5432
EOF
  kubectl apply -f "${WORK_DIR}/postgres.yaml"
  kubectl -n "$NAMESPACE" rollout status deployment/ue-postgres --timeout=300s
  register_workloads
  # Not --wait: the frontend Deployment has no image in this cluster by design, and the
  # proof only needs the backend and gateway Deployments to become Available.
  helm upgrade --install "$RELEASE" "${ROOT_DIR}/charts/university-ecosystem" \
    --namespace "$NAMESPACE" \
    --values "${WORK_DIR}/values.yaml" \
    --set-file "backend.config.jwtPrivateKeyPEM=${WORK_DIR}/jwt-private.pem" \
    --set-file "gateway.config.jwtSecret=${WORK_DIR}/secret-files/gateway-jwt"
  kubectl -n "$NAMESPACE" rollout status "deployment/${BACKEND_SVC}" --timeout=600s
  kubectl -n "$NAMESPACE" rollout status "deployment/${GATEWAY_SVC}" --timeout=600s
}

run_probe() {
  local name="$1" script="$2"
  timeout 300 kubectl -n "$NAMESPACE" run "ue-r9-aud373-probe-${name}-${RUN_SUFFIX}" \
    --image="$BACKEND_IMAGE" --image-pull-policy=IfNotPresent \
    --restart=Never --rm --attach --quiet --pod-running-timeout=180s \
    --env="TARGET_BACKEND=${BACKEND_SVC}" --env="TARGET_GATEWAY=${GATEWAY_SVC}" \
    --env="TARGET_BACKEND_PORT=${BACKEND_PORT}" --env="TARGET_GATEWAY_PORT=${GATEWAY_PORT}" \
    --command -- python -c "$script" 2>&1
}

GATEWAY_HOP_PY='
import os, urllib.error, urllib.request
url = "http://%s:%s/.well-known/jwks.json" % (os.environ["TARGET_GATEWAY"], os.environ["TARGET_GATEWAY_PORT"])
try:
    with urllib.request.urlopen(url, timeout=20) as response:
        body = response.read(65536)
        print("STATUS=%d" % response.status)
        print("BODY_HAS_KEYS=%s" % (b"\"keys\"" in body))
except urllib.error.HTTPError as error:
    print("STATUS=%d" % error.code)
    print("BODY_HAS_KEYS=False")
except Exception as error:
    print("ERROR=%s" % type(error).__name__)
'

NO_SVID_TLS_PY='
import os, socket, ssl
host = os.environ["TARGET_BACKEND"]
port = int(os.environ["TARGET_BACKEND_PORT"])
context = ssl.create_default_context()
context.check_hostname = False
context.verify_mode = ssl.CERT_NONE
context.minimum_version = ssl.TLSVersion.TLSv1_3
context.maximum_version = ssl.TLSVersion.TLSv1_3
result = "ERROR"
try:
    raw = socket.create_connection((host, port), timeout=10)
except OSError:
    pass
else:
    with raw:
        try:
            with context.wrap_socket(raw, server_hostname=host) as tls:
                # TLS 1.3 may report a missing-certificate alert after the client
                # handshake has returned. Read it before sending application data.
                tls.settimeout(2)
                try:
                    data = tls.recv(1)
                except TimeoutError:
                    tls.settimeout(10)
                    tls.sendall(("GET /health/live HTTP/1.1\r\nHost: %s\r\nConnection: close\r\n\r\n" % host).encode())
                    data = tls.recv(64)
                if data:
                    result = "ANSWERED"
        except ssl.SSLError as error:
            if error.reason == "TLSV13_ALERT_CERTIFICATE_REQUIRED":
                result = "REJECTED"
        except OSError:
            pass
print("NO_SVID_TLS=%s" % result)
'

PLAINTEXT_PY='
import http.client, os
host = os.environ["TARGET_BACKEND"]
port = int(os.environ["TARGET_BACKEND_PORT"])
result = "ERROR"
connection = http.client.HTTPConnection(host, port, timeout=10)
try:
    connection.connect()
except OSError:
    pass
else:
    try:
        connection.request("GET", "/health/live")
        connection.getresponse()
        result = "ANSWERED"
    except (ConnectionResetError, BrokenPipeError, http.client.RemoteDisconnected):
        result = "REJECTED"
    except (OSError, http.client.HTTPException):
        pass
finally:
    connection.close()
print("PLAINTEXT=%s" % result)
'

record() {
  local name="$1" passed="$2"
  if [[ "$passed" == "yes" ]]; then
    printf 'PASS %s\n' "$name"
  else
    printf 'FAIL %s\n' "$name"
    FAILURES=$((FAILURES + 1))
  fi
}

# Every backend replica is searched: the gateway request may be served by any of them.
# The structured event carries only the peer SPIFFE ID; the exact gateway ID must appear.
backend_logged_gateway_peer() {
  local pod
  for _ in 1 2 3 4 5; do
    while read -r pod; do
      if kubectl -n "$NAMESPACE" logs "$pod" --all-containers --tail=-1 2>/dev/null |
        grep -F 'internal_mtls_peer_authorized' |
        grep -qF "$GATEWAY_SPIFFE_ID"; then
        return 0
      fi
    done < <(kubectl -n "$NAMESPACE" get pods -o name | grep "^pod/${BACKEND_SVC}-" | sed 's#^pod/##')
    sleep 2
  done
  return 1
}

run_proofs() {
  local output
  if output="$(run_probe gateway-hop "$GATEWAY_HOP_PY")" &&
    grep -qx 'STATUS=200' <<<"$output" && grep -qx 'BODY_HAS_KEYS=True' <<<"$output"; then
    record "a-gateway-to-backend-mtls-hop" yes
  else
    record "a-gateway-to-backend-mtls-hop" no
  fi

  if backend_logged_gateway_peer; then
    record "d-backend-logs-gateway-peer-spiffe-id" yes
  else
    record "d-backend-logs-gateway-peer-spiffe-id" no
  fi

  if output="$(run_probe no-svid-tls "$NO_SVID_TLS_PY")" &&
    grep -qx 'NO_SVID_TLS=REJECTED' <<<"$output"; then
    record "b-no-svid-tls-client-rejected" yes
  else
    record "b-no-svid-tls-client-rejected" no
  fi

  if output="$(run_probe plaintext "$PLAINTEXT_PY")" &&
    grep -qx 'PLAINTEXT=REJECTED' <<<"$output"; then
    record "c-plaintext-http-rejected" yes
  else
    record "c-plaintext-http-rejected" no
  fi
}

collect_diagnostics() {
  local namespace pod verb
  mkdir -p "$DIAG_DIR"
  if [[ ! -s "$KUBECONFIG" ]]; then
    return 0
  fi
  for namespace in "$NAMESPACE" "$SPIRE_NAMESPACE"; do
    kubectl -n "$namespace" get all,serviceaccounts -o wide >"${DIAG_DIR}/${namespace}-get.txt" 2>&1 || true
    kubectl -n "$namespace" describe pods >"${DIAG_DIR}/${namespace}-describe-pods.txt" 2>&1 || true
    kubectl -n "$namespace" get events --sort-by=.lastTimestamp >"${DIAG_DIR}/${namespace}-events.txt" 2>&1 || true
    while read -r pod; do
      [[ -n "$pod" ]] || continue
      kubectl -n "$namespace" logs "$pod" --all-containers --prefix --tail=400 \
        >"${DIAG_DIR}/${namespace}-${pod}.log" 2>&1 || true
    done < <(kubectl -n "$namespace" get pods -o name 2>/dev/null | sed 's#^pod/##' || true)
  done
  kubectl get nodes -o wide >"${DIAG_DIR}/nodes.txt" 2>&1 || true
  if [[ "$REGISTRY_CREATED" == "1" ]]; then
    docker logs "$LOCAL_REGISTRY_NAME" >"${DIAG_DIR}/registry.log" 2>&1 || true
  fi
  # AUD-251: record API-server authorization observations for this kind cluster.
  # They do not establish fine-grained kubelet authorization on other clusters.
  {
    printf 'agent get nodes/proxy: '
    kubectl auth can-i get nodes --subresource=proxy \
      --as=system:serviceaccount:spire:spire-agent || true
    for verb in list watch; do
      printf 'agent %s pods across namespaces: ' "$verb"
      kubectl auth can-i "$verb" pods --all-namespaces \
        --as=system:serviceaccount:spire:spire-agent || true
      printf 'agent %s nodes: ' "$verb"
      kubectl auth can-i "$verb" nodes \
        --as=system:serviceaccount:spire:spire-agent || true
    done
  } >"${DIAG_DIR}/spire-agent-api-authorization.txt" 2>&1
}

cleanup() {
  local status=$?
  set +e
  collect_diagnostics
  if [[ "$CLUSTER_CREATED" == "1" ]]; then
    kind delete cluster --name "$CLUSTER_NAME" --kubeconfig "$KUBECONFIG" >/dev/null 2>&1
  fi
  if [[ "$REGISTRY_CREATED" == "1" ]]; then
    docker rm --force --volumes "$LOCAL_REGISTRY_NAME" >/dev/null 2>&1
  fi
  rm -rf "$WORK_DIR"
  exit "$status"
}

main() {
  trap cleanup EXIT
  require_platform
  install_tools
  create_cluster
  start_local_registry
  build_and_push_images
  install_spire
  deploy_stack
  run_proofs
  if [[ "$FAILURES" -ne 0 ]]; then
    printf 'RESULT=FAIL failures=%s\n' "$FAILURES"
    exit 1
  fi
  printf 'RESULT=PASS\n'
}

main "$@"
