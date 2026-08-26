#!/usr/bin/env bash
set -euo pipefail

mode="${1:-}"
chart="charts/university-ecosystem"

test -s "$chart/Chart.lock" || {
  echo "Pinned Helm dependency lock is missing or empty: $chart/Chart.lock" >&2
  exit 1
}
dependency_status="$(helm dependency list "$chart")"
actual_dependencies="$(awk 'NR > 1 && NF {print $1 "|" $3 "|" $4}' <<< "$dependency_status")"
expected_dependencies=$'redis|oci://registry-1.docker.io/bitnamicharts|ok\nredis|oci://registry-1.docker.io/bitnamicharts|ok\nnats|oci://registry-1.docker.io/bitnamicharts|ok'
if [[ "$actual_dependencies" != "$expected_dependencies" ]]; then
  echo "Helm dependencies do not match the reviewed Chart.lock contract." >&2
  printf '%s\n' "$dependency_status" >&2
  exit 1
fi

required=(
  DEPLOY_ENVIRONMENT K8S_NAMESPACE HELM_RELEASE_NAME HELM_VALUES_FILE
  CONNECTIONS_SECRET_NAME APPLICATION_SECRETS_NAME REGISTRY GITHUB_REPOSITORY
  DEPLOY_VERSION
  BACKEND_IMAGE_DIGEST FRONTEND_IMAGE_DIGEST GATEWAY_IMAGE_DIGEST
  FILE_PROCESSOR_IMAGE_DIGEST WS_HUB_IMAGE_DIGEST
)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "Required Helm input '$name' is empty." >&2
    exit 1
  fi
done

cwv_enabled=false
release_args=()
if [[ "$DEPLOY_ENVIRONMENT" == "staging" || "$DEPLOY_ENVIRONMENT" == "production" ]]; then
  release_required=(
    DEPLOYMENT_URL CWV_EXPORT_OIDC_SUBJECT FRONTEND_HOST API_HOST
    TLS_SECRET_NAME CERT_MANAGER_ISSUER_NAME ELASTICSEARCH_URL FLAGD_HOST
    OTLP_ENDPOINT MINIO_ENDPOINT TEMPORAL_HOST REDIS_IMAGE_DIGEST
    REDIS_METRICS_IMAGE_DIGEST REVOCATION_REDIS_IMAGE_DIGEST
    REVOCATION_REDIS_METRICS_IMAGE_DIGEST NATS_IMAGE_DIGEST
  )
  for name in "${release_required[@]}"; do
    if [[ -z "${!name:-}" ]]; then
      echo "Required release Helm input '$name' is empty." >&2
      exit 1
    fi
  done
  issuer_kind="Issuer"
  if [[ "$DEPLOY_ENVIRONMENT" == "production" ]]; then
    issuer_kind="ClusterIssuer"
  fi
  release_args=(
    --set "global.security.allowInsecureImages=false"
    --set-string "redis.image.registry=docker.io"
    --set-string "redis.image.repository=bitnami/redis"
    --set-string "redis.metrics.image.registry=docker.io"
    --set-string "redis.metrics.image.repository=bitnami/redis-exporter"
    --set-string "revocationRedis.image.registry=docker.io"
    --set-string "revocationRedis.image.repository=bitnami/redis"
    --set-string "revocationRedis.metrics.image.registry=docker.io"
    --set-string "revocationRedis.metrics.image.repository=bitnami/redis-exporter"
    --set-string "nats.image.registry=docker.io"
    --set-string "nats.image.repository=bitnami/nats"
    --set-string "backend.config.elasticsearchURL=$ELASTICSEARCH_URL"
    --set-string "backend.config.flagdHost=$FLAGD_HOST"
    --set-string "gateway.config.otelEndpoint=$OTLP_ENDPOINT"
    --set-string "wsHub.config.allowedOrigins[0]=https://$FRONTEND_HOST"
    --set-string "wsHub.config.otelEndpoint=$OTLP_ENDPOINT"
    --set-string "fileProcessor.config.minioEndpoint=$MINIO_ENDPOINT"
    --set-string "fileProcessor.config.temporalHost=$TEMPORAL_HOST"
    --set-string "fileProcessor.config.otlpEndpoint=$OTLP_ENDPOINT"
    --set-string "ingress.issuer.kind=$issuer_kind"
    --set-string "ingress.issuer.name=$CERT_MANAGER_ISSUER_NAME"
    --set-string "ingress.hosts[0].host=$FRONTEND_HOST"
    --set-string "ingress.hosts[1].host=$API_HOST"
    --set-string "ingress.tls[0].secretName=$TLS_SECRET_NAME"
    --set-string "ingress.tls[0].hosts[0]=$FRONTEND_HOST"
    --set-string "ingress.tls[0].hosts[1]=$API_HOST"
    --set-string "redis.image.digest=$REDIS_IMAGE_DIGEST"
    --set-string "redis.metrics.image.digest=$REDIS_METRICS_IMAGE_DIGEST"
    --set-string "revocationRedis.image.digest=$REVOCATION_REDIS_IMAGE_DIGEST"
    --set-string "revocationRedis.metrics.image.digest=$REVOCATION_REDIS_METRICS_IMAGE_DIGEST"
    --set-string "nats.image.digest=$NATS_IMAGE_DIGEST"
  )
fi
if [[ "$DEPLOY_ENVIRONMENT" == "staging" ]]; then
  cwv_enabled=true
  for name in DEPLOY_VERSION DEPLOYMENT_URL GITHUB_RUN_ID GITHUB_RUN_ATTEMPT CWV_EXPORT_OIDC_SUBJECT; do
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
  --set-string "global.imageTag=$DEPLOY_VERSION"
  --set-string "backend.image.repository=$REGISTRY/$GITHUB_REPOSITORY/backend"
  --set-string "backend.image.digest=$BACKEND_IMAGE_DIGEST"
  --set "cwv.rumEnabled=$cwv_enabled"
  --set-string "cwv.releaseSHA=$cwv_release_sha"
  --set-string "cwv.frontendImageDigest=$FRONTEND_IMAGE_DIGEST"
  --set "cwv.deploymentRunID=$cwv_run_id"
  --set "cwv.deploymentRunAttempt=$cwv_run_attempt"
  --set-string "cwv.deploymentURL=$cwv_deployment_url"
  --set-string "cwv.deployedAt=$cwv_deployed_at"
  --set-string "cwv.allowedOrigins[0]=$cwv_deployment_url"
  --set "cwv.exportOIDC.enabled=$cwv_enabled"
  --set-string "cwv.exportOIDC.repository=$GITHUB_REPOSITORY"
  --set-string "cwv.exportOIDC.workflowRef=$GITHUB_REPOSITORY/.github/workflows/cwv-field-certification.yml@refs/heads/main"
  --set-string "cwv.exportOIDC.subject=${CWV_EXPORT_OIDC_SUBJECT:-disabled}"
  --set-string "frontend.image.repository=$REGISTRY/$GITHUB_REPOSITORY/frontend"
  --set-string "frontend.image.digest=$FRONTEND_IMAGE_DIGEST"
  --set-string "wsHub.image.repository=$REGISTRY/$GITHUB_REPOSITORY/ws-hub"
  --set-string "wsHub.image.digest=$WS_HUB_IMAGE_DIGEST"
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
  "${release_args[@]}"
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
