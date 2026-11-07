#!/usr/bin/env bash
# Private AUD-346 candidate: run a bounded live Chaos Mesh proof on one owned kind cluster.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
readonly ROOT_DIR
readonly KIND_VERSION="v0.31.0"
readonly KUBECTL_VERSION="v1.36.4"
readonly HELM_VERSION="v4.2.4"
readonly KIND_URL="https://github.com/kubernetes-sigs/kind/releases/download/${KIND_VERSION}/kind-linux-amd64"
readonly KUBECTL_URL="https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl"
readonly HELM_URL="https://get.helm.sh/helm-${HELM_VERSION}-linux-amd64.tar.gz"
readonly CHAOS_MESH_VERSION="2.8.7"
readonly TARGET_NAMESPACE="aud346"
readonly TARGET_SERVICE="aud346-chaos-target"
readonly RUN_ID="$(openssl rand -hex 6)"
readonly CLUSTER_NAME="ue-gw-${RUN_ID}"
readonly NODE_CONTAINER="${CLUSTER_NAME}-control-plane"
readonly CONTEXT="kind-${CLUSTER_NAME}"
readonly NODE_IMAGE_PATTERN='s|^[[:space:]]*--node-image (kindest/node:v1\.36\.4@sha256:[0-9a-f]{64})[[:space:]]*$|\1|p'

case "$(uname -s)/$(uname -m)" in
  Linux/x86_64) ;;
  *) printf 'AUD-346 kind proof requires Linux x86_64.\n' >&2; exit 2 ;;
esac

# This proof must use the ephemeral hosted runner's local Docker daemon. Refuse
# inherited remote Docker endpoints or named contexts before any Kind operation.
if [[ -n "${DOCKER_HOST:-}" && "${DOCKER_HOST}" != "unix:///var/run/docker.sock" ]]; then
  printf 'AUD-346 kind proof refuses a non-local Docker host.\n' >&2
  exit 2
fi
if [[ -n "${DOCKER_CONTEXT:-}" && "${DOCKER_CONTEXT}" != "default" ]]; then
  printf 'AUD-346 kind proof refuses a non-default Docker context.\n' >&2
  exit 2
fi

RUNNER_TMP="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
readonly RUN_BUDGET_SECONDS=480
readonly CLEANUP_RESERVE_SECONDS=60
readonly RUN_DEADLINE=$((SECONDS + RUN_BUDGET_SECONDS))
readonly WORK_DEADLINE=$((RUN_DEADLINE - CLEANUP_RESERVE_SECONDS))
readonly WORK_PREFIX="${RUNNER_TMP%/}/aud346-kind."
WORK_DIR="$(mktemp -d "${WORK_PREFIX}XXXXXX")"
readonly WORK_DIR
if [[ "$WORK_DIR" != "$WORK_PREFIX"* || "$WORK_DIR" == "$RUNNER_TMP" ]]; then
  printf 'refusing unexpected private work directory: %s\n' "$WORK_DIR" >&2
  exit 1
fi
chmod 0700 "$WORK_DIR"
readonly STATE_DIR="${WORK_DIR}/kind-state"
readonly KUBECONFIG="${WORK_DIR}/kubeconfig"
readonly STATE_FILE="${STATE_DIR}/${CLUSTER_NAME}.json"
readonly DIAG_DIR="${WORK_DIR}/diagnostics"
mkdir -m 0700 -p "$STATE_DIR" "$DIAG_DIR" "${WORK_DIR}/bin" \
  "${WORK_DIR}/uv-cache" \
  "${WORK_DIR}/helm/config" "${WORK_DIR}/helm/cache" "${WORK_DIR}/helm/data" \
  "${WORK_DIR}/docker"
export KUBECONFIG
export PATH="${WORK_DIR}/bin:${PATH}"
export UV_CACHE_DIR="${WORK_DIR}/uv-cache"
export HELM_CONFIG_HOME="${WORK_DIR}/helm/config"
export HELM_CACHE_HOME="${WORK_DIR}/helm/cache"
export HELM_DATA_HOME="${WORK_DIR}/helm/data"
export DOCKER_CONFIG="${WORK_DIR}/docker"
unset DOCKER_HOST DOCKER_TLS_VERIFY DOCKER_CERT_PATH
export DOCKER_CONTEXT=default

CLUSTER_CREATE_STARTED=0
CLUSTER_OWNED=0
KIND_CREATE_PID=""
PORT_FORWARD_PID=""

log() { printf '%s\n' "$*" >&2; }

run_until() {
  local deadline="$1"; shift
  local remaining=$((deadline - SECONDS))
  if (( remaining <= 0 )); then
    log "AUD-346 deadline exhausted before: $*"
    return 124
  fi
  timeout --signal=TERM --kill-after=2s "${remaining}s" "$@"
}

run_bounded() { run_until "$WORK_DEADLINE" "$@"; }
run_cleanup_bounded() { run_until "$RUN_DEADLINE" "$@"; }

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
  run_bounded curl --fail --silent --show-error --location --retry 2 --max-time 120 \
    --output "$dest" "$url" || return 1
  run_bounded curl --fail --silent --show-error --location --retry 2 --max-time 120 \
    --output "${dest}.sha256" "$checksum_url" || return 1
  verify_checksum "${dest}.sha256" "$dest" "$expected_name"
}

uv_python_bounded() {
  run_bounded uv run --no-project --isolated \
    --with pyyaml==6.0.3 \
    --with cryptography==50.0.2 \
    python "$@"
}

uv_python_cleanup() {
  run_cleanup_bounded uv run --no-project --isolated \
    --with pyyaml==6.0.3 \
    --with cryptography==50.0.2 \
    python "$@"
}

run_kind_owner() {
  uv_python_bounded "${ROOT_DIR}/scripts/kind_gateway_api.py" \
    --state-dir "$STATE_DIR" "$@"
}

run_kind_owner_cleanup() {
  uv_python_cleanup "${ROOT_DIR}/scripts/kind_gateway_api.py" \
    --state-dir "$STATE_DIR" "$@"
}

apply_owned_node_limits() {
  local identity limits
  identity="$(run_bounded docker inspect \
    --format '{{.Name}}|{{.Config.Image}}|{{index .Config.Labels "io.x-k8s.kind.cluster"}}' \
    "$NODE_CONTAINER" 2>/dev/null)" || return 1
  [[ "$identity" == "/${NODE_CONTAINER}|${NODE_IMAGE}|${CLUSTER_NAME}" ]] || return 1
  run_bounded docker update --cpus=2 --memory=4g --memory-swap=4g "$NODE_CONTAINER" >/dev/null || return 1
  limits="$(run_bounded docker inspect \
    --format '{{.HostConfig.NanoCpus}}|{{.HostConfig.Memory}}|{{.HostConfig.MemorySwap}}' "$NODE_CONTAINER")" || return 1
  [[ "$limits" == "2000000000|4294967296|4294967296" ]]
}

cleanup() {
  local status=$? cleanup_failed=0
  set +e
  if [[ -n "$PORT_FORWARD_PID" ]]; then
    kill "$PORT_FORWARD_PID" >/dev/null 2>&1
    wait "$PORT_FORWARD_PID" >/dev/null 2>&1
  fi
  if [[ -n "$KIND_CREATE_PID" ]]; then
    if kill -0 "$KIND_CREATE_PID" >/dev/null 2>&1; then
      kill -TERM -- "-${KIND_CREATE_PID}" >/dev/null 2>&1 ||
        kill -TERM "$KIND_CREATE_PID" >/dev/null 2>&1
      wait "$KIND_CREATE_PID" >/dev/null 2>&1
    fi
    KIND_CREATE_PID=""
  fi
  if [[ "$CLUSTER_OWNED" == 1 ]]; then
    if ! run_kind_owner_cleanup teardown --run-id "$RUN_ID" >/dev/null; then
      log "cleanup failed: owned kind cluster ${CLUSTER_NAME}; private state preserved at ${WORK_DIR}"
      cleanup_failed=1
    fi
  elif [[ "$CLUSTER_CREATE_STARTED" == 1 && -f "$STATE_FILE" ]]; then
    if run_kind_owner_cleanup recover --run-id "$RUN_ID" >/dev/null; then
      if ! run_kind_owner_cleanup teardown --run-id "$RUN_ID" >/dev/null; then
        log "cleanup failed: recovered cluster ${CLUSTER_NAME}; private state preserved at ${WORK_DIR}"
        cleanup_failed=1
      fi
    else
      local clusters
      if clusters="$(run_cleanup_bounded kind get clusters 2>/dev/null)"; then
        if grep -Fxq "$CLUSTER_NAME" <<<"$clusters"; then
          log "cleanup failed: ownership recovery was refused for ${CLUSTER_NAME}; private state preserved at ${WORK_DIR}"
          cleanup_failed=1
        else
          log "partial create left no cluster named ${CLUSTER_NAME}; no cluster deletion was issued"
        fi
      else
        log "cleanup failed: cluster state is unknown for ${CLUSTER_NAME}; private state preserved at ${WORK_DIR}"
        cleanup_failed=1
      fi
    fi
  fi
  if [[ "$cleanup_failed" == 0 ]]; then
    if [[ "$WORK_DIR" == "$WORK_PREFIX"* && "$WORK_DIR" != "$RUNNER_TMP" ]]; then
      rm -rf -- "$WORK_DIR" || cleanup_failed=1
    else
      log "cleanup refused unexpected private work directory ${WORK_DIR}"
      cleanup_failed=1
    fi
  fi
  if [[ "$cleanup_failed" != 0 && "$status" == 0 ]]; then
    status=1
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ ! -S /var/run/docker.sock ]]; then
  log "AUD-346 kind proof requires the hosted runner's local Docker socket"
  exit 2
fi
if ! DOCKER_ENDPOINT="$(run_bounded docker context inspect default --format '{{.Endpoints.docker.Host}}')"; then
  log "AUD-346 could not verify the default Docker context"
  exit 2
fi
if [[ "$DOCKER_ENDPOINT" != "unix:///var/run/docker.sock" ]]; then
  log "AUD-346 default Docker context is not the local runner socket"
  exit 2
fi
unset DOCKER_ENDPOINT
if ! run_bounded docker version --format '{{.Server.Version}}' >/dev/null 2>&1; then
  log "AUD-346 local Docker daemon is unavailable"
  exit 2
fi

if [[ -e "$KUBECONFIG" ]]; then
  log "refusing to reuse kubeconfig path ${KUBECONFIG}"
  exit 1
fi

NODE_IMAGES=()
mapfile -t NODE_IMAGES < <(sed -nE "$NODE_IMAGE_PATTERN" "${ROOT_DIR}/k8s/README.md")
if [[ "${#NODE_IMAGES[@]}" != 1 ]]; then
  log "expected exactly one tracked v1.36.4 kind node image pin"
  exit 1
fi
readonly NODE_IMAGE="${NODE_IMAGES[0]}"
readonly KIND_HELPER_CLUSTER_NAME="ue-gw-${RUN_ID}"

mkdir -p "${WORK_DIR}/bin"
download_verified "$KIND_URL" "${KIND_URL}.sha256sum" \
  "${WORK_DIR}/bin/kind" kind-linux-amd64
download_verified "$KUBECTL_URL" "${KUBECTL_URL}.sha256" \
  "${WORK_DIR}/bin/kubectl" kubectl
download_verified "$HELM_URL" "${HELM_URL}.sha256sum" \
  "${WORK_DIR}/helm.tar.gz" "helm-${HELM_VERSION}-linux-amd64.tar.gz"
tar -xzf "${WORK_DIR}/helm.tar.gz" -C "$WORK_DIR" linux-amd64/helm
mv "${WORK_DIR}/linux-amd64/helm" "${WORK_DIR}/bin/helm"
chmod 0755 "${WORK_DIR}/bin/kind" "${WORK_DIR}/bin/kubectl" "${WORK_DIR}/bin/helm"
run_bounded kind version | grep -q "^kind ${KIND_VERSION} "
run_bounded helm version --template '{{.Version}}' | grep -Fxq "$HELM_VERSION"
uv_python_bounded -c 'import cryptography, yaml'

# The reusable helper owns cluster identity, node-image validation, state and teardown.
CLUSTER_CREATE_STARTED=1
KIND_CREATE_BUDGET=$((WORK_DEADLINE - SECONDS))
if (( KIND_CREATE_BUDGET <= 0 )); then
  log "AUD-346 work deadline exhausted before owned kind create"
  exit 1
fi
setsid timeout --signal=TERM --kill-after=2s "${KIND_CREATE_BUDGET}s" \
  uv run --no-project --isolated \
  --with pyyaml==6.0.3 \
  --with cryptography==50.0.2 \
  python "${ROOT_DIR}/scripts/kind_gateway_api.py" \
  --state-dir "$STATE_DIR" create --run-id "$RUN_ID" --node-image "$NODE_IMAGE" \
  >"${DIAG_DIR}/kind-create.log" 2>&1 &
KIND_CREATE_PID=$!
NODE_LIMITS_APPLIED=0
for _attempt in $(seq 1 60); do
  if apply_owned_node_limits; then
    NODE_LIMITS_APPLIED=1
    log "applied 2 CPU and 4 GiB limits to the exact run-labeled kind node"
    break
  fi
  if ! kill -0 "$KIND_CREATE_PID" >/dev/null 2>&1; then
    break
  fi
  run_bounded sleep 1 || break
done
if [[ "$NODE_LIMITS_APPLIED" != 1 ]]; then
  if wait "$KIND_CREATE_PID"; then
    CREATE_STATUS=0
  else
    CREATE_STATUS=$?
    KIND_CREATE_PID=""
    cat "${DIAG_DIR}/kind-create.log" >&2
    exit "$CREATE_STATUS"
  fi
  KIND_CREATE_PID=""
  if apply_owned_node_limits; then
    NODE_LIMITS_APPLIED=1
  fi
else
  if wait "$KIND_CREATE_PID"; then
    KIND_CREATE_PID=""
  else
    CREATE_STATUS=$?
    KIND_CREATE_PID=""
    cat "${DIAG_DIR}/kind-create.log" >&2
    exit "$CREATE_STATUS"
  fi
fi
if [[ "$NODE_LIMITS_APPLIED" != 1 ]]; then
  cat "${DIAG_DIR}/kind-create.log" >&2
  log "failed to verify resource limits on the exact run-owned kind node"
  exit 1
fi
CLUSTER_OWNED=1
run_kind_owner status --run-id "$RUN_ID" >/dev/null
KIND_NODES="$(run_bounded kind get nodes --name "$CLUSTER_NAME")"
[[ "$KIND_NODES" == "${CLUSTER_NAME}-control-plane" ]]
apply_owned_node_limits
run_bounded kubectl config use-context "$CONTEXT" >/dev/null
CONTEXTS="$(run_bounded kubectl config get-contexts --output=name)"
[[ "$CONTEXTS" == "$CONTEXT" ]]
[[ "$(run_bounded kubectl config current-context)" == "$CONTEXT" ]]
run_bounded kubectl config set-context "$CONTEXT" --namespace="$TARGET_NAMESPACE" >/dev/null

run_bounded kubectl create namespace chaos-mesh --context "$CONTEXT"
run_bounded kubectl apply --context "$CONTEXT" -f "${ROOT_DIR}/k8s/chaos/fixtures/aud346-target.yaml"
run_bounded helm repo add chaos-mesh https://charts.chaos-mesh.org
run_bounded helm upgrade --install chaos-mesh chaos-mesh/chaos-mesh \
  --version "$CHAOS_MESH_VERSION" \
  --kubeconfig "$KUBECONFIG" \
  --kube-context "$CONTEXT" \
  --namespace chaos-mesh \
  --create-namespace \
  --set images.tag="v${CHAOS_MESH_VERSION}" \
  --set controllerManager.enableFilterNamespace=true \
  --set controllerManager.replicaCount=1 \
  --set controllerManager.podChaos.podFailure.pauseImage=registry.k8s.io/pause:3.10.1 \
  --set dashboard.create=false \
  --set dnsServer.create=false \
  --set chaosDaemon.runtime=containerd \
  --set chaosDaemon.socketPath=/run/containerd/containerd.sock \
  --wait \
  --timeout 5m
run_bounded kubectl wait --context "$CONTEXT" \
  --for=condition=Established crd/podchaos.chaos-mesh.org --timeout=60s
run_bounded kubectl rollout status --context "$CONTEXT" --namespace "$TARGET_NAMESPACE" \
  deployment/aud346-chaos-target --timeout=90s

PORT="$(run_bounded python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
kubectl --context "$CONTEXT" --namespace "$TARGET_NAMESPACE" \
  port-forward --address 127.0.0.1 "service/${TARGET_SERVICE}" "${PORT}:80" \
  >"${DIAG_DIR}/port-forward.log" 2>&1 &
PORT_FORWARD_PID=$!
for _attempt in $(seq 1 30); do
  run_bounded true || exit 1
  if ! kill -0 "$PORT_FORWARD_PID" >/dev/null 2>&1; then
    cat "${DIAG_DIR}/port-forward.log" >&2
    exit 1
  fi
  if curl --noproxy '*' --fail --silent --show-error --max-time 2 \
      "http://127.0.0.1:${PORT}/health" >/dev/null; then
    break
  fi
  sleep 1
done
run_bounded true
curl --noproxy '*' --fail --silent --show-error --max-time 2 \
  "http://127.0.0.1:${PORT}/health" >/dev/null

# Preserve the nightly offline validation; this second phase is the bounded live proof.
uv_python_bounded "${ROOT_DIR}/scripts/chaos/run_chaos_loadtest.py" \
  --manifest "${ROOT_DIR}/k8s/chaos/aud346-pod-failure.yaml" \
  --duration 5 \
  --target-url "http://127.0.0.1:${PORT}/health" \
  --require-fault-impact
curl --noproxy '*' --fail --silent --show-error --max-time 2 \
  "http://127.0.0.1:${PORT}/health" >/dev/null
log "AUD-346 live fault and recovery assertions passed for run ${RUN_ID}"
