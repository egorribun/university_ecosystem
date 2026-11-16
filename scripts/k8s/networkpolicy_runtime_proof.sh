#!/usr/bin/env bash
# AUD-169, AUD-188, AUD-189 and AUD-438 runtime NetworkPolicy proof.
#
# Creates a uniquely named disposable kind cluster with the default CNI disabled
# and Calico (a pinned, sha256-verified manifest) enforcing NetworkPolicy, then runs
# scripts/k8s/networkpolicy_runtime_probe.py against the rendered chart policies.
# The probe writes a JSON receipt with one verdict per probe. The script exits
# non-zero on any mismatch, inconclusive row or failed setup step. The cluster is
# deleted in the EXIT trap.
#
# Usage: scripts/k8s/networkpolicy_runtime_proof.sh
# Requires Linux x86_64 with a running Docker daemon and uv. Tools are downloaded at
# the pinned versions below and checked against their official checksum files.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
readonly ROOT_DIR

# Pinned tools, same versions and checksum policy as scripts/kind/aud373_internal_mtls_proof.sh.
readonly KIND_VERSION="v0.31.0"
readonly KIND_URL="https://github.com/kubernetes-sigs/kind/releases/download/${KIND_VERSION}/kind-linux-amd64"
readonly KUBECTL_VERSION="v1.36.4"
readonly KUBECTL_URL="https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl"
readonly HELM_VERSION="v4.2.4"
readonly HELM_URL="https://get.helm.sh/helm-${HELM_VERSION}-linux-amd64.tar.gz"
# Kubernetes 1.36.4 node image (>= 1.33), pinned by digest as in k8s/README.md.
readonly NODE_IMAGE="kindest/node:v1.36.4@sha256:099e049362a1526b2db71494e1947aae99bd16290d7c895f2b7ea312e3cbfaed"
readonly KUBERNETES_VERSION="v1.36.4"
# Calico v3.30.3 manifest; the sha256 below was computed from the exact file.
readonly CALICO_URL="https://raw.githubusercontent.com/projectcalico/calico/v3.30.3/manifests/calico.yaml"
readonly CALICO_SHA256="9382d2b27a76f40c170454b408653e6d71e2205ef0aef069e942bb690e7381d0"
# Link-local listener address (169.254.0.0/16) added to the kind node's eth0. The
# probe's host-network listener binds here; it must match LINK_LOCAL_ADDRESS in
# scripts/k8s/networkpolicy_runtime_rows.py (contract-tested).
readonly LINK_LOCAL_ADDRESS="169.254.10.10"

RUN_SUFFIX="$(openssl rand -hex 6)"
readonly RUN_SUFFIX
readonly CLUSTER_NAME="ue-netpol-${RUN_SUFFIX}"
WORK_DIR="$(mktemp -d)"
readonly WORK_DIR
readonly DIAG_DIR="${UE_NETPOL_DIAG_DIR:-${RUNNER_TEMP:-${TMPDIR:-/tmp}}/aud169-188-189-netpol}"
export KUBECONFIG="${WORK_DIR}/kubeconfig"
export PATH="${WORK_DIR}/bin:${PATH}"
CLUSTER_CREATED=0
WS_IMAGE_CREATED=0
BACKUP_BRIDGE_INTENT=0
BACKUP_SERVER_INTENT=0
BACKUP_PROXY_INTENT=0
BACKUP_NODE_INTENT=0
BACKUP_BRIDGE_ID=''
BACKUP_SERVER_ID=''
BACKUP_PROXY_ID=''
BACKUP_NODE_ID=''
BACKUP_IMAGE=''
BACKUP_PROXY_IMAGE=''
BACKUP_BUCKET=''
BACKUP_TLS_DIR=''
readonly BACKUP_SERVER_NAME="ue-netpol-backup-${RUN_SUFFIX}"
readonly BACKUP_PROXY_NAME="ue-netpol-backup-proxy-${RUN_SUFFIX}"

log() {
  printf '%s\n' "$*" >&2
}

require_backup_opt_in() {
  case "${UE_NETPOL_REAL_BACKUP:-0}" in
    0) return 0 ;;
    1) ;;
    *) log "real backup proof requires UE_NETPOL_REAL_BACKUP=1"; return 1 ;;
  esac
  if [[ "${UE_NETPOL_REAL_FP:-0}" != 1 || "${GITHUB_ACTIONS:-}" != true ||
        "${RUNNER_ENVIRONMENT:-}" != github-hosted ]]; then
    log "real backup proof requires the real processor and a GitHub-hosted runner"
    return 1
  fi
}

require_backup_local_docker() {
  [[ "${UE_NETPOL_REAL_BACKUP:-0}" == 1 ]] || return 0
  local context endpoint
  if [[ -n "${DOCKER_HOST:-}" || -n "${DOCKER_CONTEXT:-}" ||
        -n "${DOCKER_TLS_VERIFY:-}" || -n "${DOCKER_CERT_PATH:-}" ]]; then
    log "real backup proof requires the default local Docker daemon"
    return 1
  fi
  context="$(docker context show)" || return 1
  [[ "$context" == default ]] || return 1
  endpoint="$(docker context inspect --format '{{.Endpoints.docker.Host}}' default)" || return 1
  [[ "$endpoint" == unix:///var/run/docker.sock ]]
}

backup_bridge_cli() {
  uv run --frozen python "${SCRIPT_DIR}/networkpolicy_runtime_backup_bridge.py" "$@"
}

backup_network_inventory() {
  local listed snapshot identity
  local -a identities=()
  listed="$(docker network ls --no-trunc --quiet)" || return 1
  if [[ -n "$listed" ]]; then
    mapfile -t identities <<< "$listed"
    for identity in "${identities[@]}"; do
      [[ "$identity" =~ ^[0-9a-f]{64}$ ]] || return 1
    done
    snapshot="$(docker network inspect "${identities[@]}")" || return 1
  else
    snapshot='[]'
  fi
  printf '%s' "$snapshot" | backup_bridge_cli "$@" "${identities[@]}"
}

backup_preflight_networks() {
  backup_network_inventory preflight-networks
}

backup_preflight_routes() {
  local routes
  routes="$(ip -j -4 route show table all)" || return 1
  printf '%s' "$routes" | backup_bridge_cli preflight-routes
}

backup_inspect_container() {
  local role="$1" identity="$2" name="$3" image
  case "$role" in
    server) image="${BACKUP_IMAGE:-}" ;;
    proxy) image="${BACKUP_PROXY_IMAGE:-}" ;;
    node) image="${NODE_IMAGE:-}" ;;
    *) return 1 ;;
  esac
  [[ "$identity" =~ ^[0-9a-f]{64}$ ]] || return 1
  docker container inspect "$identity" | backup_bridge_cli inspect-container \
    "$role" "$identity" "$name" "$BACKUP_BRIDGE_ID" "$RUN_SUFFIX" "$CLUSTER_NAME" "$image"
}

backup_find_bridge() {
  backup_network_inventory find-bridge "$1"
}

backup_find_container() {
  local role="$1" recorded="$2" name="$3" listing
  [[ "$role" == server || "$role" == proxy || "$role" == node ]] || return 1
  listing="$(docker container ls --all --no-trunc --format '{{.ID}} {{.Names}}')" || return 1
  printf '%s\n' "$listing" | backup_bridge_cli find-container "$recorded" "$name"
}

backup_validate_bridge() {
  docker network inspect "$BACKUP_BRIDGE_ID" | \
    backup_bridge_cli validate-bridge "$BACKUP_BRIDGE_ID" "$RUN_SUFFIX" "$@"
}

backup_cleanup_resources() {
  [[ "$BACKUP_BRIDGE_INTENT" == 1 ]] || return 0
  local found role current intent recorded name address failed=0
  local -A ids=([server]='' [proxy]='' [node]='')
  local -A addresses=([server]='-' [proxy]='-' [node]='-')
  local -a members=()
  found="$(backup_find_bridge "$BACKUP_BRIDGE_ID")" || return 1
  if [[ -z "$found" ]]; then
    [[ "$BACKUP_SERVER_INTENT" == 0 && "$BACKUP_PROXY_INTENT" == 0 && "$BACKUP_NODE_INTENT" == 0 ]]
    return
  fi
  BACKUP_BRIDGE_ID="$found"
  for role in server proxy node; do
    case "$role" in
      server) intent="$BACKUP_SERVER_INTENT"; recorded="$BACKUP_SERVER_ID"; name="$BACKUP_SERVER_NAME" ;;
      proxy) intent="$BACKUP_PROXY_INTENT"; recorded="$BACKUP_PROXY_ID"; name="$BACKUP_PROXY_NAME" ;;
      node) intent="$BACKUP_NODE_INTENT"; recorded="$BACKUP_NODE_ID"; name="${CLUSTER_NAME}-control-plane" ;;
    esac
    if [[ "$intent" == 1 ]]; then
      found="$(backup_find_container "$role" "$recorded" "$name")" || return 1
      if [[ -n "$found" ]]; then
        address="$(backup_inspect_container "$role" "$found" "$name")" || return 1
        ids[$role]="$found"; addresses[$role]="$address"
      fi
    fi
  done
  for role in node proxy server; do
    members=()
    for current in server proxy node; do
      [[ "${addresses[$current]}" == '-' ]] || members+=("${ids[$current]}" "${addresses[$current]}")
    done
    backup_validate_bridge "${members[@]}" || return 1
    if [[ -n "${ids[$role]}" ]]; then
      if docker container rm --force --volumes "${ids[$role]}" >/dev/null 2>&1; then
        ids[$role]=''; addresses[$role]='-'
      else
        failed=1
      fi
    fi
  done
  members=()
  for current in server proxy node; do
    [[ "${addresses[$current]}" == '-' ]] || members+=("${ids[$current]}" "${addresses[$current]}")
  done
  if [[ "$failed" == 0 ]] && backup_validate_bridge "${members[@]}"; then
    docker network rm "$BACKUP_BRIDGE_ID" >/dev/null 2>&1 || failed=1
  else
    failed=1
  fi
  [[ "$failed" == 0 ]]
}

backup_source_image() {
  backup_bridge_cli compose-image "$1"
}

backup_write_credentials() {
  local access secret file="${WORK_DIR}/backup-credentials.env"
  [[ ! -e "$file" && ! -L "$file" ]] || return 1
  access="$(openssl rand -hex 24)" || return 1
  secret="$(openssl rand -hex 32)" || return 1
  [[ "$access" =~ ^[0-9a-f]{48}$ && "$secret" =~ ^[0-9a-f]{64}$ && "$access" != "$secret" ]] || return 1
  printf 'AWS_ACCESS_KEY_ID=%s\nAWS_SECRET_ACCESS_KEY=%s\n' "$access" "$secret" > "$file"
}

backup_create_bridge() {
  local created
  BACKUP_BRIDGE_INTENT=1
  created="$(docker network create --driver bridge --subnet 198.18.42.0/24 \
    --gateway 198.18.42.1 --label "org.university-ecosystem.netpol-owner=${RUN_SUFFIX}" kind)" || return 1
  [[ "$created" =~ ^[0-9a-f]{64}$ ]] || return 1
  BACKUP_BRIDGE_ID="$created"
  backup_validate_bridge
}

backup_wait_bucket() {
  local attempt logs line marker="created bucket ${BACKUP_BUCKET}"
  for attempt in {1..30}; do
    logs="$(timeout --kill-after=2s 10s docker container logs "$BACKUP_SERVER_ID" 2>&1)" || {
      log "backup storage startup failed: logs"
      return 1
    }
    while IFS= read -r line; do
      [[ "$line" == "$marker" || "$line" == *[[:space:]]"$marker" ]] && return 0
    done <<< "$logs"
    if [[ "$attempt" -lt 30 ]]; then
      sleep 2
    fi
  done
  log "backup storage startup failed: bucket"
  return 1
}

backup_create_server() {
  local address created
  BACKUP_SERVER_INTENT=1
  created="$(docker container create --name "$BACKUP_SERVER_NAME" \
    --label "org.university-ecosystem.netpol-owner=${RUN_SUFFIX}" \
    --network "$BACKUP_BRIDGE_ID" --ip 198.18.42.11 \
    --env-file "${WORK_DIR}/backup-credentials.env" \
    --env "S3_BUCKET=${BACKUP_BUCKET}" \
    --mount "type=tmpfs,dst=/data,tmpfs-mode=0700" \
    "$BACKUP_IMAGE" mini -dir=/data -master.telemetry=false -s3.port=9000)" || return 1
  [[ "$created" =~ ^[0-9a-f]{64}$ ]] || return 1
  BACKUP_SERVER_ID="$created"
  docker container start "$BACKUP_SERVER_ID" >/dev/null || return 1
  address="$(backup_inspect_container server "$BACKUP_SERVER_ID" "$BACKUP_SERVER_NAME")" || return 1
  [[ "$address" == 198.18.42.11 ]] || return 1
  backup_validate_bridge "$BACKUP_SERVER_ID" "$address" || return 1
  backup_wait_bucket
}

backup_write_proxy_config() {
  [[ ! -e "${WORK_DIR}/backup.Caddyfile" && ! -L "${WORK_DIR}/backup.Caddyfile" ]] || return 1
  cat > "${WORK_DIR}/backup.Caddyfile" <<'EOF'
{
	admin off
	auto_https off
}

https://198.18.42.10:443 {
	tls /run/ue-backup/server.crt /run/ue-backup/server.key
	reverse_proxy http://198.18.42.11:9000
}
EOF
}

backup_wait_https() {
  local attempt curl_status=0 http_status status_file="${WORK_DIR}/backup-http-status"
  # The fixed Seaweed status endpoint must answer 200 through the private proxy.
  for attempt in {1..30}; do
    if curl --silent --output /dev/null --write-out '%{http_code}' --connect-timeout 2 --max-time 5 --noproxy '*' \
      --cacert "${BACKUP_TLS_DIR}/ca.crt" https://198.18.42.10:443/status > "$status_file" 2>/dev/null; then
      http_status="$(< "$status_file")" || return 1
      [[ "$http_status" != 200 ]] || return 0
      curl_status=0
    else
      curl_status=$?
    fi
    if [[ "$attempt" -lt 30 ]]; then
      sleep 2
    fi
  done
  case "$curl_status" in
    0) log "backup HTTPS readiness failed: http-status" ;;
    5|6) log "backup HTTPS readiness failed: dns" ;;
    7) log "backup HTTPS readiness failed: connect" ;;
    28) log "backup HTTPS readiness failed: timeout" ;;
    35) log "backup HTTPS readiness failed: tls-handshake" ;;
    51|60|77) log "backup HTTPS readiness failed: tls-verification" ;;
    *) log "backup HTTPS readiness failed: other" ;;
  esac
  return 1
}

backup_create_proxy() {
  local address created uid gid
  uid="$(id -u)" || return 1
  gid="$(id -g)" || return 1
  [[ "$uid" =~ ^[0-9]+$ && "$gid" =~ ^[0-9]+$ ]] || return 1
  BACKUP_PROXY_INTENT=1
  created="$(docker container create --name "$BACKUP_PROXY_NAME" \
    --label "org.university-ecosystem.netpol-owner=${RUN_SUFFIX}" \
    --user "${uid}:${gid}" --cap-drop ALL --cap-add NET_BIND_SERVICE \
    --env XDG_CONFIG_HOME=/tmp/caddy-config --env XDG_DATA_HOME=/tmp/caddy-data \
    --entrypoint /usr/bin/caddy \
    --network "$BACKUP_BRIDGE_ID" --ip 198.18.42.10 \
    --mount "type=bind,src=${BACKUP_TLS_DIR},dst=/run/ue-backup,readonly" \
    --mount "type=bind,src=${WORK_DIR}/backup.Caddyfile,dst=/etc/caddy/Caddyfile,readonly" \
    "$BACKUP_PROXY_IMAGE" run --config /etc/caddy/Caddyfile --adapter caddyfile)" || return 1
  [[ "$created" =~ ^[0-9a-f]{64}$ ]] || return 1
  BACKUP_PROXY_ID="$created"
  docker container start "$BACKUP_PROXY_ID" >/dev/null || return 1
  address="$(backup_inspect_container proxy "$BACKUP_PROXY_ID" "$BACKUP_PROXY_NAME")" || return 1
  [[ "$address" == 198.18.42.10 ]] || return 1
  backup_validate_bridge "$BACKUP_SERVER_ID" 198.18.42.11 "$BACKUP_PROXY_ID" "$address" || return 1
  backup_wait_https
}

backup_prepare_fixture() {
  local found
  backup_preflight_networks || return 1
  backup_preflight_routes || return 1
  found="$(backup_find_container server '' "$BACKUP_SERVER_NAME")" || return 1
  [[ -z "$found" ]] || return 1
  found="$(backup_find_container proxy '' "$BACKUP_PROXY_NAME")" || return 1
  [[ -z "$found" ]] || return 1
  found="$(backup_find_container node '' "${CLUSTER_NAME}-control-plane")" || return 1
  [[ -z "$found" ]] || return 1
  # The source archive and processor build share the same committed SOURCE_SHA.
  BACKUP_IMAGE="$(backup_source_image "${WORK_DIR}/source/docker-compose.yml")" || return 1
  BACKUP_PROXY_IMAGE="$(backup_bridge_cli caddy-image "${WORK_DIR}/source/services/caddy/Dockerfile")" || return 1
  BACKUP_BUCKET="$(backup_bridge_cli backup-bucket "${WORK_DIR}/source/charts/university-ecosystem/values.yaml")" || return 1
  backup_write_credentials || return 1
  BACKUP_TLS_DIR="$(backup_bridge_cli certificate "$WORK_DIR")" || return 1
  [[ -f "${BACKUP_TLS_DIR}/ca.crt" && -f "${BACKUP_TLS_DIR}/server.crt" &&
     -f "${BACKUP_TLS_DIR}/server.key" ]] || return 1
  backup_write_proxy_config || return 1
  backup_create_bridge || return 1
  backup_create_server || return 1
  backup_create_proxy
}

backup_verify_kind_node() {
  local node_address server_address proxy_address found
  found="$(backup_find_container node "$BACKUP_NODE_ID" "${CLUSTER_NAME}-control-plane")" || return 1
  [[ "$found" =~ ^[0-9a-f]{64}$ ]] || return 1
  BACKUP_NODE_ID="$found"
  node_address="$(backup_inspect_container node "$BACKUP_NODE_ID" "${CLUSTER_NAME}-control-plane")" || return 1
  server_address="$(backup_inspect_container server "$BACKUP_SERVER_ID" "$BACKUP_SERVER_NAME")" || return 1
  proxy_address="$(backup_inspect_container proxy "$BACKUP_PROXY_ID" "$BACKUP_PROXY_NAME")" || return 1
  [[ "$node_address" != '-' && "$server_address" == 198.18.42.11 && "$proxy_address" == 198.18.42.10 ]] || return 1
  backup_validate_bridge "$BACKUP_SERVER_ID" "$server_address" "$BACKUP_PROXY_ID" "$proxy_address" "$BACKUP_NODE_ID" "$node_address"
}

require_platform() {
  if [[ "$(uname -s)" != "Linux" || "$(uname -m)" != "x86_64" ]]; then
    log "this proof runs on Linux x86_64 only (CI ubuntu-24.04)"
    exit 2
  fi
  docker info >/dev/null
  command -v uv >/dev/null
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
  curl --fail --silent --show-error --location --retry 3 --max-time 300 --output "$dest" "$url" || return 1
  curl --fail --silent --show-error --location --retry 3 --max-time 300 --output "${dest}.sha256" "$checksum_url" || return 1
  verify_checksum "${dest}.sha256" "$dest" "$expected_name"
}

download_pinned() {
  local url="$1" sha256="$2" dest="$3"
  curl --fail --silent --show-error --location --retry 3 --max-time 300 --output "$dest" "$url" || return 1
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

write_kind_config() {
  cat > "${WORK_DIR}/kind-config.yaml" <<'EOF'
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
networking:
  # The default kindnet CNI does not enforce NetworkPolicy; Calico is installed below.
  disableDefaultCNI: true
  ipFamily: ipv4
nodes:
  - role: control-plane
EOF
}

add_link_local_address() {
  # The kind node is a privileged container; its eth0 carries the link-local /32
  # that the host-network listener binds. Fail closed if the address is absent.
  local addresses
  docker exec "${CLUSTER_NAME}-control-plane" ip addr add "${LINK_LOCAL_ADDRESS}/32" dev eth0
  addresses="$(docker exec "${CLUSTER_NAME}-control-plane" ip -4 addr show dev eth0)"
  [[ "$addresses" == *"inet ${LINK_LOCAL_ADDRESS}/32"* ]]
}

collect_diagnostics() {
  mkdir -p "$DIAG_DIR"
  if [[ "$CLUSTER_CREATED" -eq 1 ]]; then
    kubectl get pods --all-namespaces -o wide > "${DIAG_DIR}/pods.txt" 2>&1 || true
    kubectl get networkpolicies --all-namespaces -o yaml > "${DIAG_DIR}/networkpolicies.yaml" 2>&1 || true
    kubectl -n kube-system get pods -l k8s-app=calico-node -o wide > "${DIAG_DIR}/calico-node.txt" 2>&1 || true
  fi
}

cleanup() {
  local status=$? cleanup_failed=0
  trap - EXIT
  collect_diagnostics || true
  if [[ "${UE_NETPOL_REAL_BACKUP:-0}" == 1 ]]; then
    if ! backup_cleanup_resources; then
      log "cleanup failed: owned backup fixture"
      cleanup_failed=1
    fi
  elif [[ "$CLUSTER_CREATED" -eq 1 ]]; then
    kind delete cluster --name "$CLUSTER_NAME" >/dev/null 2>&1 || true
  fi
  if [[ "$WS_IMAGE_CREATED" -eq 1 ]]; then
    docker image rm "$WS_IMAGE" >/dev/null 2>&1 || true
  fi
  rm -rf "$WORK_DIR" || cleanup_failed=1
  if [[ "$status" == 0 && "$cleanup_failed" != 0 ]]; then
    status=1
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Opt-in private real-process phase. Uses existing FP Dockerfile builder and the
# tracked Python base; never publishes images or changes the forty-row matrix.
require_clean_source() {
  local untracked
  # No filenames or diffs are printed: ignored caches/secrets never become
  # provenance data. The build context below is a Git archive, not the worktree.
  if ! git -C "$ROOT_DIR" diff --quiet HEAD -- || ! git -C "$ROOT_DIR" diff --cached --quiet HEAD --; then
    log "real-process proof requires a committed clean source tree"
    return 1
  fi
  untracked="$(git -C "$ROOT_DIR" ls-files --others --exclude-standard)" || return 1
  if [[ -n "$untracked" ]]; then
    log "real-process proof requires a committed clean source tree"
    return 1
  fi
}

build_real_processor_images() {
  [[ "${UE_NETPOL_REAL_FP:-0}" == 1 ]] || return 0
  local base_image build_source
  require_clean_source
  SOURCE_SHA="$(git -C "$ROOT_DIR" rev-parse HEAD)"
  [[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]]
  build_source="${WORK_DIR}/source"
  mkdir -p "$build_source"
  # Preserve committed source modes under the private 0700 context; keep secret umask 077.
  git -C "$ROOT_DIR" archive --format=tar "$SOURCE_SHA" | tar --same-permissions -xf - -C "$build_source"
  FP_IMAGE="ue-netpol-fp:${SOURCE_SHA}"
  DIAGNOSTIC_IMAGE="ue-netpol-diagnostic:${SOURCE_SHA}"
  base_image="$(cd "$ROOT_DIR" && uv run --frozen python -c 'import sys; sys.path.insert(0,sys.argv[1]+"/scripts/k8s"); from networkpolicy_runtime_probe import runtime_base_image; print(runtime_base_image())' "$build_source")"
  docker build -f "${build_source}/services/file-processor/Dockerfile" -t "$FP_IMAGE" "$build_source"
  # Reuse the existing builder stage so Go/module pins and native source agree.
  sed '/^FROM .* AS health-probe/,$d' "${build_source}/services/file-processor/Dockerfile" > "${WORK_DIR}/diagnostic.Dockerfile"
  printf '\nRUN CGO_ENABLED=0 GOOS=linux go build -trimpath -o /networkpolicy-probe ./cmd/networkpolicy-probe\nFROM %s\nCOPY --from=builder /networkpolicy-probe /usr/local/bin/networkpolicy-probe\n' "$base_image" >> "${WORK_DIR}/diagnostic.Dockerfile"
  docker build -f "${WORK_DIR}/diagnostic.Dockerfile" -t "$DIAGNOSTIC_IMAGE" "$build_source"
  if [[ "${UE_NETPOL_REAL_WS:-0}" == 1 ]]; then
    WS_IMAGE="ue-netpol-ws:${SOURCE_SHA}-${RUN_SUFFIX}"
    docker build -f "${build_source}/services/ws-hub/Dockerfile" -t "$WS_IMAGE" "$build_source"
    WS_IMAGE_CREATED=1
  fi
}


load_real_processor_images() {
  local archive="${WORK_DIR}/real-processor-images.tar" image expected observed attempt
  local -a images=("$FP_IMAGE" "$DIAGNOSTIC_IMAGE")
  if [[ "${UE_NETPOL_REAL_WS:-0}" == 1 ]]; then
    images+=("$WS_IMAGE")
  fi
  # kind v0.31.0 rejects config v4 before import (nodeutils/util.go).
  # Use the pinned node's native ctr instead, including unpack into overlayfs,
  # the rootful kind node's snapshotter. Do not mutate containerd configuration.
  docker save --output "$archive" "${images[@]}"
  docker exec -i "${CLUSTER_NAME}-control-plane" ctr --namespace=k8s.io images import \
    --local --all-platforms --digests --snapshotter=overlayfs - < "$archive"
  # The CRI must resolve each exact tag to the locally built image config ID.
  # Successful tar ingestion alone is not evidence that kubelet can use it.
  for image in "${images[@]}"; do
    expected="$(docker image inspect --format '{{.Id}}' "$image")"
    [[ "$expected" =~ ^sha256:[0-9a-f]{64}$ ]]
    # Image-created events reach the CRI cache asynchronously. Wait only for a
    # missing tag (at most 29 one-second sleeps/image); malformed output, command errors or
    # an already visible wrong identity must fail immediately, never be retried.
    for attempt in {1..30}; do
      observed="$(docker exec "${CLUSTER_NAME}-control-plane" crictl images --output json |
        uv run --frozen python -c 'import json,sys
matches = [item["id"] for item in json.load(sys.stdin)["images"] if sys.argv[1] in item.get("repoTags", [])]
if len(matches) > 1: raise ValueError("ambiguous imported image reference")
print(matches[0] if matches else "")' "docker.io/library/${image}")"
      [[ -z "$observed" || "$observed" == "$expected" ]]
      [[ "$observed" != "$expected" ]] || break
      [[ "$attempt" -lt 30 ]]
      sleep 1
    done
    observed="$(docker exec "${CLUSTER_NAME}-control-plane" crictl inspecti --output json "$image" |
      uv run --frozen python -c 'import json,sys; print(json.load(sys.stdin)["status"]["id"])')"
    [[ "$observed" == "$expected" ]]
  done
  rm "$archive"
}

main() {
  require_backup_opt_in
  require_backup_local_docker
  if [[ "${UE_NETPOL_REAL_WS:-0}" == 1 && "${UE_NETPOL_REAL_FP:-0}" != 1 ]]; then
    log "real ws-hub proof requires the real-processor phase"
    return 1
  fi
  require_platform
  install_tools
  write_kind_config
  build_real_processor_images
  if [[ "${UE_NETPOL_REAL_BACKUP:-0}" == 1 ]]; then
    backup_prepare_fixture
    BACKUP_NODE_INTENT=1
  fi

  CLUSTER_CREATED=1
  kind create cluster --name "$CLUSTER_NAME" --image "$NODE_IMAGE" \
    --config "${WORK_DIR}/kind-config.yaml" --wait 120s
  if [[ "${UE_NETPOL_REAL_BACKUP:-0}" == 1 ]]; then
    backup_verify_kind_node
  fi
  add_link_local_address
  local -a real_processor_args=()
  if [[ "${UE_NETPOL_REAL_FP:-0}" == 1 ]]; then
    load_real_processor_images
    real_processor_args=(--real-processor-image "$FP_IMAGE" --diagnostic-image "$DIAGNOSTIC_IMAGE" --source-sha "$SOURCE_SHA")
    if [[ "${UE_NETPOL_REAL_WS:-0}" == 1 ]]; then
      real_processor_args+=(--real-ws-image "$WS_IMAGE")
    fi
    if [[ "${UE_NETPOL_REAL_BACKUP:-0}" == 1 ]]; then
      real_processor_args+=(--backup-endpoint 'https://198.18.42.10:443'
        --backup-ca-file "${BACKUP_TLS_DIR}/ca.crt"
        --backup-credentials-file "${WORK_DIR}/backup-credentials.env")
    fi
  fi

  download_pinned "$CALICO_URL" "$CALICO_SHA256" "${WORK_DIR}/calico.yaml"
  kubectl apply --server-side --force-conflicts -f "${WORK_DIR}/calico.yaml"
  kubectl -n kube-system rollout status daemonset/calico-node --timeout=300s
  kubectl -n kube-system rollout status deployment/calico-kube-controllers --timeout=300s
  kubectl wait --for=condition=Ready nodes --all --timeout=300s
  kubectl -n kube-system rollout status deployment/coredns --timeout=300s

  if [[ "${UE_NETPOL_REAL_BACKUP:-0}" == 1 ]]; then
    backup_verify_kind_node
  fi
  mkdir -p "$DIAG_DIR"
  (
    cd "$ROOT_DIR"
    uv run --frozen python scripts/k8s/networkpolicy_runtime_probe.py \
      --receipt "${DIAG_DIR}/receipt.json" \
      --kubernetes-version "$KUBERNETES_VERSION" \
      --node-image "$NODE_IMAGE" \
      --calico-sha256 "$CALICO_SHA256" "${real_processor_args[@]}"
  )
}

main "$@"
