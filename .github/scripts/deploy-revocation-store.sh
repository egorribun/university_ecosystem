#!/usr/bin/env bash
set -euo pipefail

# Bootstrap the durable revocation store before the application release.  The
# application's migration remains a pre-install/pre-upgrade hook, so placing
# this StatefulSet in the application chart would be a lifecycle deadlock on
# the first deployment that needs it.
mode="${1:-}"
chart="charts/revocation-store"
vendor_archive="$chart/charts/redis-20.13.4.tgz"
vendor_checksum="$chart/redis-20.13.4.tgz.sha256"
vendor_sha256="4c83fd15af8cd755ef8984b8b089413b10dbed16da1a87859ea1a2b086e11e14" # pragma: allowlist secret - public vendored-chart integrity digest

verify_vendored_dependency() {
  test -s "$chart/Chart.lock" || {
    echo "Pinned Helm dependency lock is missing or empty: $chart/Chart.lock" >&2
    return 1
  }
  for vendored_file in "$vendor_archive" "$vendor_checksum"; do
    if [[ ! -f "$vendored_file" || -L "$vendored_file" ]]; then
      echo "Vendored Redis dependency must be a regular checked-in file: $vendored_file" >&2
      return 1
    fi
  done
  if [[ "$(sha256sum "$vendor_archive" | awk '{print $1}')" != "$vendor_sha256" ]]; then
    echo "Vendored Redis archive checksum does not match the reviewed dependency." >&2
    return 1
  fi
  if ! (
    cd "$chart"
    sha256sum --status --check "$(basename "$vendor_checksum")"
  ); then
    echo "Vendored Redis checksum manifest does not verify the archive." >&2
    return 1
  fi
  dependency_status="$(helm dependency list "$chart")"
  actual_dependencies="$(awk 'NR > 1 && NF {print $1 "|" $3 "|" $4}' <<< "$dependency_status")"
  expected_dependencies=$'redis|oci://registry-1.docker.io/bitnamicharts|ok'
  if [[ "$actual_dependencies" != "$expected_dependencies" ]]; then
    echo "Revocation-store dependencies do not match the reviewed Chart.lock contract." >&2
    printf '%s\n' "$dependency_status" >&2
    return 1
  fi
}

if [[ "$mode" == "verify-vendor" ]]; then
  verify_vendored_dependency
  exit 0
fi

required=(
  DEPLOY_ENVIRONMENT K8S_NAMESPACE HELM_RELEASE_NAME
  REVOCATION_REDIS_IMAGE_DIGEST REVOCATION_REDIS_METRICS_IMAGE_DIGEST
)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "Required revocation-store input '$name' is empty." >&2
    exit 1
  fi
done

if [[ ! "$HELM_RELEASE_NAME" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ || \
      "${#HELM_RELEASE_NAME}" -gt 36 ]]; then
  echo "HELM_RELEASE_NAME must be a DNS-1123 label of at most 36 characters." >&2
  exit 1
fi
if [[ ! "$REVOCATION_REDIS_IMAGE_DIGEST" =~ ^sha256:[0-9a-f]{64}$ || \
      ! "$REVOCATION_REDIS_METRICS_IMAGE_DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo "Revocation-store images must use immutable sha256 digests." >&2
  exit 1
fi

store_release="${HELM_RELEASE_NAME}-revocation-store"
store_fullname="${HELM_RELEASE_NAME}-revocation-redis"
# The store credential identity is immutable: permitting a caller to point it
# at redis-credentials would let every cache client authenticate to revocation
# Redis. ExternalSecrets/Vault own the values, while this fixed target name and
# key make the trust boundary auditable without copying a plaintext secret.
redis_secret_name="revocation-redis-credentials" # pragma: allowlist secret — identifier only; value is an ExternalSecret name
redis_secret_key="revocation-redis-password" # pragma: allowlist secret — identifier only; value is an ExternalSecret key
if [[ -n "${REVOCATION_REDIS_SECRET_NAME:-}" || -n "${REVOCATION_REDIS_SECRET_KEY:-}" ]]; then
  echo "REVOCATION_REDIS_SECRET_NAME and REVOCATION_REDIS_SECRET_KEY are immutable deployment-contract fields." >&2
  exit 1
fi

verify_vendored_dependency

environment_values=()
if [[ "$DEPLOY_ENVIRONMENT" == "staging" || "$DEPLOY_ENVIRONMENT" == "production" ]]; then
  environment_values=(--values "$chart/values-staging.yaml")
fi

# Helm uses dots as a path separator in --set.  Escaping the dot retains the
# literal Kubernetes label key expected by both the wrapper and app policies.
common_args=(
  "${environment_values[@]}"
  --set-string "applicationReleaseName=$HELM_RELEASE_NAME"
  --set-string "redis.fullnameOverride=$store_fullname"
  --set-string "redis.commonLabels.university-ecosystem\\.io/revocation-store-for=$HELM_RELEASE_NAME"
  --set-string "redis.commonLabels.app\\.kubernetes\\.io/instance=$HELM_RELEASE_NAME"
  --set-string "redis.auth.existingSecret=$redis_secret_name"
  --set-string "redis.auth.existingSecretPasswordKey=$redis_secret_key"
  --set-string "redis.image.registry=docker.io"
  --set-string "redis.image.repository=bitnami/redis"
  --set-string "redis.image.digest=$REVOCATION_REDIS_IMAGE_DIGEST"
  --set-string "redis.image.pullPolicy=Always"
  --set-string "redis.metrics.image.registry=docker.io"
  --set-string "redis.metrics.image.repository=bitnami/redis-exporter"
  --set-string "redis.metrics.image.digest=$REVOCATION_REDIS_METRICS_IMAGE_DIGEST"
  --set-string "redis.metrics.image.pullPolicy=Always"
)

case "$mode" in
  render)
    helm template "$store_release" "$chart" \
      --namespace "$K8S_NAMESPACE" \
      "${common_args[@]}"
    ;;
  render-contract)
    helm template "$store_release" "$chart" \
      --namespace "$K8S_NAMESPACE" \
      "${common_args[@]}" \
      --show-only templates/deployment-contract.yaml
    ;;
  lint)
    helm lint --strict "$chart" "${common_args[@]}"
    ;;
  upgrade)
    helm upgrade --install "$store_release" "$chart" \
      --namespace "$K8S_NAMESPACE" \
      "${common_args[@]}" \
      --atomic \
      --wait \
      --timeout 10m \
      --history-max 10
    ;;
  *)
    echo "Usage: $0 {verify-vendor|render|render-contract|lint|upgrade}" >&2
    exit 2
    ;;
esac
