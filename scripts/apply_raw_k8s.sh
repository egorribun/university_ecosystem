#!/usr/bin/env bash
# Apply one explicitly approved supporting manifest.
#
# Helm is the only staging/production release path.  This wrapper exists for
# the few development/diagnostic manifests that intentionally retain
# envsubst placeholders.  It keeps the input surface allowlisted and fails
# closed before kubectl can receive an empty or mutable image reference.
set -euo pipefail

die() {
  echo "apply_raw_k8s: $*" >&2
  exit 1
}

[[ "$#" -eq 1 ]] || die "usage: $0 <allowlisted manifest>"

manifest="${1:-}"
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
gateway_class_manifest=false
case "$manifest" in
  k8s/gateway-api/gatewayclass.yaml)
    substitution_set="\$GATEWAY_CLASS_NAME"
    required_variables=(GATEWAY_CLASS_NAME)
    gateway_class_manifest=true
    ;;
  k8s/ingress.yaml)
    substitution_set="\$CERT_MANAGER_ISSUER_NAME \$FRONTEND_HOST \$API_HOST \$TLS_SECRET_NAME"
    required_variables=(CERT_MANAGER_ISSUER_NAME FRONTEND_HOST API_HOST TLS_SECRET_NAME)
    ;;
  k8s/backend/secret-store.yaml)
    substitution_set="\$VAULT_URL"
    required_variables=(VAULT_URL)
    ;;
  k8s/backend/deployment.yaml|k8s/frontend/deployment.yaml)
    substitution_set="\$IMAGE_REGISTRY \$IMAGE_TAG"
    required_variables=(IMAGE_REGISTRY IMAGE_TAG)
    ;;
  *)
    die "unsupported raw manifest: $manifest"
    ;;
esac

manifest_path="$repo_root/$manifest"
[[ -f "$manifest_path" && ! -L "$manifest_path" ]] || die "manifest is missing or symlinked: $manifest"
manifest_directory="${manifest_path%/*}"
resolved_manifest_directory="$(cd -- "$manifest_directory" 2>/dev/null && pwd -P)" || \
  die "manifest directory cannot be resolved: $manifest"
[[ "$resolved_manifest_directory" == "$manifest_directory" ]] || \
  die "manifest path resolves outside the repository or through a symlink: $manifest"
command -v envsubst >/dev/null 2>&1 || die "envsubst is required"
command -v kubectl >/dev/null 2>&1 || die "kubectl is required"

for name in "${required_variables[@]}"; do
  value="${!name:-}"
  [[ -n "$value" ]] || die "required variable '$name' is empty"
  [[ "$value" != *$'\n'* && "$value" != *$'\r'* && "$value" != *'$'* ]] || \
    die "required variable '$name' contains an unsafe character"
done

if [[ "$gateway_class_manifest" == true ]]; then
  [[ ${#GATEWAY_CLASS_NAME} -le 253 &&
     "$GATEWAY_CLASS_NAME" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$ ]] || \
    die "required variable 'GATEWAY_CLASS_NAME' is not a valid DNS name"
  IFS='.' read -r -a class_name_labels <<< "$GATEWAY_CLASS_NAME"
  for label in "${class_name_labels[@]}"; do
    [[ ${#label} -le 63 ]] || \
      die "required variable 'GATEWAY_CLASS_NAME' contains an overlong DNS label"
  done
elif [[ "$manifest" == "k8s/backend/secret-store.yaml" ]]; then
  [[ "$VAULT_URL" =~ ^https?://[A-Za-z0-9][A-Za-z0-9.-]*(\:[0-9]{1,5})?(/[^[:space:]]*)?$ ]] || \
    die "required variable 'VAULT_URL' is not a valid HTTP(S) URL"
elif [[ "$manifest" != "k8s/ingress.yaml" ]]; then
  [[ "$IMAGE_REGISTRY" =~ ^[A-Za-z0-9][A-Za-z0-9.-]*(\:[0-9]{1,5})?(/[A-Za-z0-9][A-Za-z0-9._-]*)*$ ]] || \
    die "required variable 'IMAGE_REGISTRY' is not a valid registry path"
  # Raw Deployment images use a tag placeholder, so only a full Git SHA or a
  # semantic version is valid.  Digest syntax belongs to the Helm artifact and
  # must not be transformed into the invalid ':sha256:...' form here.
  if [[ ! "$IMAGE_TAG" =~ ^[0-9a-fA-F]{40}$ &&
        ! "$IMAGE_TAG" =~ ^v?[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$ ]]; then
    die "IMAGE_TAG must be a 40-character commit SHA or semantic version"
  fi
else
  for name in CERT_MANAGER_ISSUER_NAME FRONTEND_HOST API_HOST TLS_SECRET_NAME; do
    [[ "${!name}" =~ ^[A-Za-z0-9][A-Za-z0-9.-]*$ ]] || \
      die "required variable '$name' is not a valid DNS-style value"
  done
fi

rendered="$(mktemp "${TMPDIR:-/tmp}/university-ecosystem-k8s.XXXXXX")"
trap 'rm -f -- "$rendered"' EXIT
envsubst "$substitution_set" < "$manifest_path" > "$rendered"

# envsubst replaces unset variables with an empty string.  Detect both that
# class of error and mutable/empty image tags before invoking the cluster API.
if grep -Eq '\$\{?[A-Za-z_][A-Za-z0-9_]*\}?' "$rendered"; then
  die "unresolved template variable in rendered manifest"
fi
if grep -Eq '^[[:space:]-]*image:[[:space:]]*[^[:space:]]+:(latest)?([[:space:]]|#|$)' "$rendered"; then
  die "rendered manifest contains an empty or mutable image tag"
fi

if [[ "$gateway_class_manifest" == true ]]; then
  bash "$repo_root/scripts/check_gateway_api_prerequisites.sh"

  if ! existing_name="$(kubectl get gatewayclass "$GATEWAY_CLASS_NAME" \
    --ignore-not-found -o name 2>/dev/null)"; then
    die "could not safely inspect the existing GatewayClass"
  fi
  if [[ -n "$existing_name" ]]; then
    if ! existing_controller="$(kubectl get gatewayclass "$GATEWAY_CLASS_NAME" \
      -o go-template='{{ .spec.controllerName }}' 2>/dev/null)"; then
      die "could not safely inspect the existing GatewayClass controller"
    fi
    [[ "$existing_controller" == "gateway.envoyproxy.io/gatewayclass-controller" ]] || \
      die "existing GatewayClass uses a different controller; refusing to modify it"
    echo "apply_raw_k8s: GatewayClass '$GATEWAY_CLASS_NAME' already uses Envoy Gateway; leaving it unchanged"
  else
    kubectl create -f - < "$rendered"
  fi
else
  kubectl apply -f - < "$rendered"
fi
