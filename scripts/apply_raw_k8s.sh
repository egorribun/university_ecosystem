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
case "$manifest" in
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
command -v envsubst >/dev/null 2>&1 || die "envsubst is required"
command -v kubectl >/dev/null 2>&1 || die "kubectl is required"

for name in "${required_variables[@]}"; do
  value="${!name:-}"
  [[ -n "$value" ]] || die "required variable '$name' is empty"
  [[ "$value" != *$'\n'* && "$value" != *$'\r'* && "$value" != *'$'* ]] || \
    die "required variable '$name' contains an unsafe character"
done

if [[ "$manifest" == "k8s/backend/secret-store.yaml" ]]; then
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

kubectl apply -f - < "$rendered"
