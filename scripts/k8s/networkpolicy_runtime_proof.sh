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

RUN_SUFFIX="$(openssl rand -hex 6)"
readonly RUN_SUFFIX
readonly CLUSTER_NAME="ue-netpol-${RUN_SUFFIX}"
WORK_DIR="$(mktemp -d)"
readonly WORK_DIR
readonly DIAG_DIR="${UE_NETPOL_DIAG_DIR:-${RUNNER_TEMP:-${TMPDIR:-/tmp}}/aud169-188-189-netpol}"
export KUBECONFIG="${WORK_DIR}/kubeconfig"
export PATH="${WORK_DIR}/bin:${PATH}"
CLUSTER_CREATED=0

log() {
  printf '%s\n' "$*" >&2
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

collect_diagnostics() {
  mkdir -p "$DIAG_DIR"
  if [[ "$CLUSTER_CREATED" -eq 1 ]]; then
    kubectl get pods --all-namespaces -o wide > "${DIAG_DIR}/pods.txt" 2>&1 || true
    kubectl get networkpolicies --all-namespaces -o yaml > "${DIAG_DIR}/networkpolicies.yaml" 2>&1 || true
    kubectl -n kube-system get pods -l k8s-app=calico-node -o wide > "${DIAG_DIR}/calico-node.txt" 2>&1 || true
  fi
}

cleanup() {
  local status=$?
  collect_diagnostics || true
  if [[ "$CLUSTER_CREATED" -eq 1 ]]; then
    kind delete cluster --name "$CLUSTER_NAME" >/dev/null 2>&1 || true
  fi
  rm -rf "$WORK_DIR"
  exit "$status"
}
trap cleanup EXIT

main() {
  require_platform
  install_tools
  write_kind_config

  CLUSTER_CREATED=1
  kind create cluster --name "$CLUSTER_NAME" --image "$NODE_IMAGE" \
    --config "${WORK_DIR}/kind-config.yaml" --wait 120s

  download_pinned "$CALICO_URL" "$CALICO_SHA256" "${WORK_DIR}/calico.yaml"
  kubectl apply --server-side --force-conflicts -f "${WORK_DIR}/calico.yaml"
  kubectl -n kube-system rollout status daemonset/calico-node --timeout=300s
  kubectl -n kube-system rollout status deployment/calico-kube-controllers --timeout=300s
  kubectl wait --for=condition=Ready nodes --all --timeout=300s
  kubectl -n kube-system rollout status deployment/coredns --timeout=300s

  mkdir -p "$DIAG_DIR"
  (
    cd "$ROOT_DIR"
    uv run --frozen python scripts/k8s/networkpolicy_runtime_probe.py \
      --receipt "${DIAG_DIR}/receipt.json" \
      --kubernetes-version "$KUBERNETES_VERSION" \
      --node-image "$NODE_IMAGE" \
      --calico-sha256 "$CALICO_SHA256"
  )
}

main "$@"
