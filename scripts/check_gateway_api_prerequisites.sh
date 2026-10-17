#!/usr/bin/env bash
# Read-only prerequisite checks for the allowlisted GatewayClass bootstrap.
set -euo pipefail

die() {
  echo "check_gateway_api_prerequisites: $*" >&2
  exit 1
}

command -v kubectl >/dev/null 2>&1 || die "kubectl is required"

if ! server_version="$(kubectl version -o jsonpath='{.serverVersion.major}.{.serverVersion.minor}' 2>/dev/null)"; then
  die "could not read the Kubernetes server version"
fi
case "${server_version%%+*}" in
  1.33|1.34|1.35|1.36) ;;
  *) die "Kubernetes server version must be in the supported 1.33–1.36 range" ;;
esac

require_gateway_api_bundle() {
  local crd="$1"
  local gateway_bundle
  if ! gateway_bundle="$(kubectl get crd "$crd" \
    -o go-template='{{ index .metadata.annotations "gateway.networking.k8s.io/bundle-version" }}|{{ index .metadata.annotations "gateway.networking.k8s.io/channel" }}' \
    2>/dev/null)"; then
    die "Gateway API CRD '$crd' is unavailable"
  fi
  [[ "$gateway_bundle" == "v1.6.1|standard" ]] || \
    die "Gateway API bundle for CRD '$crd' must be v1.6.1 on the Standard channel"
}

require_gateway_api_bundle gatewayclasses.gateway.networking.k8s.io
require_gateway_api_bundle gateways.gateway.networking.k8s.io
require_gateway_api_bundle httproutes.gateway.networking.k8s.io

require_crd_version() {
  local crd="$1"
  local required_version="$2"
  local served_versions
  if ! served_versions="$(kubectl get crd "$crd" \
    -o go-template='{{range .spec.versions}}{{if .served}}{{.name}} {{end}}{{end}}' \
    2>/dev/null)"; then
    die "required CRD '$crd' is unavailable"
  fi
  case " $served_versions " in
    *" $required_version "*) ;;
    *) die "CRD '$crd' does not serve required version '$required_version'" ;;
  esac
}

require_crd_version gatewayclasses.gateway.networking.k8s.io v1
require_crd_version gateways.gateway.networking.k8s.io v1
require_crd_version httproutes.gateway.networking.k8s.io v1
require_crd_version clienttrafficpolicies.gateway.envoyproxy.io v1alpha1
require_crd_version backendtrafficpolicies.gateway.envoyproxy.io v1alpha1
require_crd_version certificates.cert-manager.io v1

if ! envoy_version="$(kubectl get deployment envoy-gateway -n envoy-gateway-system \
  -o go-template='{{ index .metadata.labels "app.kubernetes.io/version" }}' \
  2>/dev/null)"; then
  die "Envoy Gateway deployment is unavailable in envoy-gateway-system"
fi
[[ "$envoy_version" == "v1.9.2" ]] || \
  die "Envoy Gateway version must be v1.9.2"

echo "check_gateway_api_prerequisites: compatible Kubernetes, Gateway API, Envoy Gateway, and cert-manager APIs verified"
