#!/usr/bin/env bash
set -euo pipefail

# Bootstrap the durable revocation store before the application release.  The
# application's migration remains a pre-install/pre-upgrade hook, so placing
# this StatefulSet in the application chart would be a lifecycle deadlock on
# the first deployment that needs it.
mode="${1:-}"
chart="charts/revocation-store"
verify_first_party_chart() {
  local stale_path
  for stale_path in \
    "$chart/Chart.lock" \
    "$chart/charts/redis-20.13.4.tgz" \
    "$chart/redis-20.13.4.tgz.sha256"; do
    if [[ -e "$stale_path" || -L "$stale_path" ]]; then
      echo "Legacy Bitnami dependency artifact must be removed: $stale_path" >&2
      return 1
    fi
  done

  local required_file
  for required_file in \
    "$chart/Chart.yaml" \
    "$chart/values.yaml" \
    "$chart/values.schema.json" \
    "$chart/templates/validate-config.yaml" \
    "$chart/templates/redis-configmap.yaml" \
    "$chart/templates/redis-networkpolicy.yaml" \
    "$chart/templates/redis-pdb.yaml" \
    "$chart/templates/redis-serviceaccount.yaml" \
    "$chart/templates/redis-services.yaml" \
    "$chart/templates/redis-statefulset.yaml" \
    "$chart/templates/deployment-contract.yaml"; do
    if [[ ! -f "$required_file" || -L "$required_file" || ! -s "$required_file" ]]; then
      echo "Required first-party revocation chart file is missing or unsafe: $required_file" >&2
      return 1
    fi
  done

  dependency_status="$(helm dependency list "$chart" 2>&1)"
  actual_dependencies="$(awk 'NF >= 4 && $1 != "NAME" && $1 != "WARNING:" {print $1 "|" $2 "|" $3 "|" $4}' <<< "$dependency_status")"
  if [[ -n "$actual_dependencies" ]]; then
    echo "Revocation store must not install remote or vendored chart dependencies." >&2
    printf '%s\n' "$dependency_status" >&2
    return 1
  fi
}

if [[ "$mode" == "verify-vendor" || "$mode" == "verify-chart" ]]; then
  verify_first_party_chart
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

preflight_existing_datastore_image() {
  local statefulset_name="${store_fullname}-master"
  local claim_name="redis-data-${statefulset_name}-0"
  local statefulset_state
  if ! command -v timeout >/dev/null 2>&1; then
    echo "The timeout utility is required to inspect revocation storage safely." >&2
    return 1
  fi

  if ! statefulset_state="$(timeout --signal=TERM --kill-after=2s 10s \
    kubectl get statefulset "$statefulset_name" \
    --request-timeout=8s \
    --namespace "$K8S_NAMESPACE" \
    --ignore-not-found \
    --output='jsonpath={.metadata.name}|{.spec.template.spec.containers[?(@.name=="redis")].image}' \
    2>/dev/null)"; then
    echo "Unable to inspect the existing revocation StatefulSet; refusing to reuse its PVC." >&2
    return 1
  fi

  if [[ -z "$statefulset_state" ]]; then
    local existing_claim
    if ! existing_claim="$(timeout --signal=TERM --kill-after=2s 10s \
      kubectl get pvc "$claim_name" \
      --request-timeout=8s \
      --namespace "$K8S_NAMESPACE" \
      --ignore-not-found \
      --output='jsonpath={.metadata.name}' \
      2>/dev/null)"; then
      echo "Unable to inspect the retained revocation PVC; refusing first installation." >&2
      return 1
    fi
    if [[ -n "$existing_claim" ]]; then
      echo "A retained revocation PVC exists without its StatefulSet; refusing first installation." >&2
      return 1
    fi
    echo "No existing revocation StatefulSet or PVC found; first installation can proceed."
    return 0
  fi

  local actual_name="${statefulset_state%%|*}"
  local image="${statefulset_state#*|}"
  if [[ "$actual_name" != "$statefulset_name" || "$image" == "$statefulset_state" || -z "$image" ]]; then
    echo "Existing revocation StatefulSet is missing its expected Redis container identity; refusing to reuse its PVC." >&2
    return 1
  fi

  local image_ref="$image"
  local has_digest=false
  if [[ "$image" == *@* ]]; then
    if [[ ! "$image" =~ @sha256:[0-9a-f]{64}$ ]]; then
      echo "Existing revocation image digest is malformed; refusing to reuse its PVC." >&2
      return 1
    fi
    image_ref="${image%@sha256:*}"
    has_digest=true
  fi

  local image_repository="${image_ref%%:*}"
  if [[ "$image_repository" != "docker.io/bitnami/redis" && \
        "$image_repository" != "docker.io/redis" ]]; then
    echo "Existing revocation image is not from an identified Redis repository; refusing to reuse its PVC." >&2
    return 1
  fi

  # Keep the non-digest path narrow to stable 7.4 tags and known official
  # distro variants. Digest references always require verification of the
  # running binary because a digest, not its accompanying tag, is authoritative.
  local stable_redis_74_tag=false
  if [[ "$image_ref" =~ ^docker\.io/(bitnami/redis|redis):7\.4\.[0-9]+(-alpine([0-9]+(\.[0-9]+)?)?|-debian-[0-9]+-r[0-9]+)?$ ]]; then
    stable_redis_74_tag=true
  elif [[ "$image_ref" == *:* ]]; then
    echo "Existing revocation image tag is not a recognized stable Redis 7.4 variant; refusing to reuse its PVC." >&2
    return 1
  fi

  if [[ "$has_digest" != true && "$stable_redis_74_tag" == true ]]; then
    return 0
  fi

  # The published Bitnami deployment used a digest-only image reference, so
  # appVersion and the image string cannot prove the engine version. Inspect
  # the running binary with bounded, read-only access and never log its output.
  local version_output
  if ! version_output="$(timeout --signal=TERM --kill-after=2s 10s \
    kubectl exec --request-timeout=8s \
    --namespace "$K8S_NAMESPACE" \
    "${statefulset_name}-0" \
    --container redis -- redis-server --version 2>/dev/null)"; then
    echo "Unable to verify the existing Redis binary version; refusing to reuse its PVC." >&2
    return 1
  fi
  if [[ ! "$version_output" =~ ^Redis[[:space:]]server[[:space:]]v=7\.4\.[0-9]+([[:space:]]|$) ]]; then
    echo "Existing revocation binary is not verified as Redis 7.4; refusing to reuse its PVC." >&2
    return 1
  fi
}
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

verify_first_party_chart

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
  --set-string "redis.image.repository=redis"
  --set-string "redis.image.tag=7.4.11-alpine"
  --set-string "redis.image.digest=$REVOCATION_REDIS_IMAGE_DIGEST"
  --set-string "redis.image.pullPolicy=Always"
  --set-string "redis.metrics.image.registry=docker.io"
  --set-string "redis.metrics.image.repository=oliver006/redis_exporter"
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
    preflight_existing_datastore_image
    helm upgrade --install "$store_release" "$chart" \
      --namespace "$K8S_NAMESPACE" \
      "${common_args[@]}" \
      --rollback-on-failure \
      --wait=legacy \
      --timeout 10m \
      --history-max 10
    ;;
  *)
    echo "Usage: $0 {verify-vendor|verify-chart|render|render-contract|lint|upgrade}" >&2
    exit 2
    ;;
esac
