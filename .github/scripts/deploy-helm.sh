#!/usr/bin/env bash
set -euo pipefail

mode="${1:-}"
chart="charts/university-ecosystem"

required=(
  DEPLOY_ENVIRONMENT K8S_NAMESPACE HELM_RELEASE_NAME HELM_VALUES_FILE
  CONNECTIONS_SECRET_NAME APPLICATION_SECRETS_NAME REGISTRY GITHUB_REPOSITORY
  BACKEND_IMAGE_DIGEST FRONTEND_IMAGE_DIGEST GATEWAY_IMAGE_DIGEST
  FILE_PROCESSOR_IMAGE_DIGEST
)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "Required Helm input '$name' is empty." >&2
    exit 1
  fi
done

common_args=(
  --values "$HELM_VALUES_FILE"
  --set-string "global.environment=$DEPLOY_ENVIRONMENT"
  --set-string "global.imageRegistry="
  --set-string "backend.image.repository=$REGISTRY/$GITHUB_REPOSITORY/backend"
  --set-string "backend.image.digest=$BACKEND_IMAGE_DIGEST"
  --set-string "frontend.image.repository=$REGISTRY/$GITHUB_REPOSITORY/frontend"
  --set-string "frontend.image.digest=$FRONTEND_IMAGE_DIGEST"
  --set-string "gateway.image.repository=$REGISTRY/$GITHUB_REPOSITORY/gateway"
  --set-string "gateway.image.digest=$GATEWAY_IMAGE_DIGEST"
  --set-string "fileProcessor.image.repository=$REGISTRY/$GITHUB_REPOSITORY/file-processor"
  --set-string "fileProcessor.image.digest=$FILE_PROCESSOR_IMAGE_DIGEST"
  --set-string "outboxWorker.image.repository=$REGISTRY/$GITHUB_REPOSITORY/backend"
  --set-string "outboxWorker.image.digest=$BACKEND_IMAGE_DIGEST"
  --set-string "connections.existingSecret=$CONNECTIONS_SECRET_NAME"
  --set-string "applicationSecrets.existingSecret=$APPLICATION_SECRETS_NAME"
  --set fileProcessor.enabled=true
  --set outboxWorker.enabled=true
  --set deploymentContract.enabled=false
)

case "$mode" in
  render)
    helm template "$HELM_RELEASE_NAME" "$chart" \
      --namespace "$K8S_NAMESPACE" \
      "${common_args[@]}"
    ;;
  render-secret-contract)
    helm template "$HELM_RELEASE_NAME" "$chart" \
      --namespace "$K8S_NAMESPACE" \
      "${common_args[@]}" \
      --set deploymentContract.enabled=true \
      --show-only templates/deployment-contract.yaml
    ;;
  lint)
    helm lint --strict "$chart" "${common_args[@]}"
    ;;
  upgrade)
    helm upgrade --install "$HELM_RELEASE_NAME" "$chart" \
      --namespace "$K8S_NAMESPACE" \
      "${common_args[@]}" \
      --atomic \
      --wait \
      --wait-for-jobs \
      --timeout 15m \
      --history-max 10
    ;;
  *)
    echo "Usage: $0 {render|render-secret-contract|lint|upgrade}" >&2
    exit 2
    ;;
esac
