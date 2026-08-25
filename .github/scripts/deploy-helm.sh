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

cwv_enabled=false
if [[ "$DEPLOY_ENVIRONMENT" == "staging" ]]; then
  cwv_enabled=true
  for name in DEPLOY_VERSION DEPLOYMENT_URL GITHUB_RUN_ID GITHUB_RUN_ATTEMPT CWV_DEPLOYED_AT CWV_EXPORT_OIDC_SUBJECT; do
    if [[ -z "${!name:-}" ]]; then
      echo "Required staging CWV input '$name' is empty." >&2
      exit 1
    fi
  done
fi
cwv_release_sha="${DEPLOY_VERSION:-0000000000000000000000000000000000000000}"
cwv_deployment_url="${DEPLOYMENT_URL:-https://disabled.invalid}"
cwv_run_id="${GITHUB_RUN_ID:-1}"
cwv_run_attempt="${GITHUB_RUN_ATTEMPT:-1}"
cwv_deployed_at="${CWV_DEPLOYED_AT:-1970-01-01T00:00:00Z}"

common_args=(
  --values "$HELM_VALUES_FILE"
  --set-string "global.environment=$DEPLOY_ENVIRONMENT"
  --set-string "global.imageRegistry="
  --set-string "backend.image.repository=$REGISTRY/$GITHUB_REPOSITORY/backend"
  --set-string "backend.image.digest=$BACKEND_IMAGE_DIGEST"
  --set-string "backend.env.CWV_RUM_ENABLED=$cwv_enabled"
  --set-string "backend.env.CWV_RELEASE_SHA=$cwv_release_sha"
  --set-string "backend.env.CWV_FRONTEND_IMAGE_DIGEST=$FRONTEND_IMAGE_DIGEST"
  --set-string "backend.env.CWV_DEPLOYMENT_RUN_ID=$cwv_run_id"
  --set-string "backend.env.CWV_DEPLOYMENT_RUN_ATTEMPT=$cwv_run_attempt"
  --set-string "backend.env.CWV_DEPLOYMENT_URL=$cwv_deployment_url"
  --set-string "backend.env.CWV_DEPLOYED_AT=$cwv_deployed_at"
  --set-string "backend.env.CWV_ALLOWED_ORIGINS=$cwv_deployment_url"
  --set-string "backend.env.CWV_EXPORT_OIDC_ENABLED=$cwv_enabled"
  --set-string "backend.env.CWV_EXPORT_OIDC_REPOSITORY=$GITHUB_REPOSITORY"
  --set-string "backend.env.CWV_EXPORT_OIDC_WORKFLOW_REF=$GITHUB_REPOSITORY/.github/workflows/cwv-field-certification.yml@refs/heads/main"
  --set-string "backend.env.CWV_EXPORT_OIDC_SUBJECT=${CWV_EXPORT_OIDC_SUBJECT:-disabled}"
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
