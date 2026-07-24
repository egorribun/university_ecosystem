#!/usr/bin/env bash
set -euo pipefail

# SPIRE Workload Registration Script
# Trust Domain: spiffe://university.ecosystem

AGENT_PARENT_ID="spiffe://university.ecosystem/spire/agent/k8s_psat/university-cluster"

echo "Registering SPIFFE workloads in SPIRE Server..."

# 1. Gateway Workload
kubectl exec -n spire spire-server-0 -- /opt/spire/bin/spire-server entry create \
    -spiffeID spiffe://university.ecosystem/ns/default/sa/gateway \
    -parentID "${AGENT_PARENT_ID}" \
    -selector k8s:ns:default \
    -selector k8s:sa:gateway \
    -ttl 3600

# 2. WS-Hub Workload
kubectl exec -n spire spire-server-0 -- /opt/spire/bin/spire-server entry create \
    -spiffeID spiffe://university.ecosystem/ns/default/sa/ws-hub \
    -parentID "${AGENT_PARENT_ID}" \
    -selector k8s:ns:default \
    -selector k8s:sa:ws-hub \
    -ttl 3600

# 3. File-Processor Workload
kubectl exec -n spire spire-server-0 -- /opt/spire/bin/spire-server entry create \
    -spiffeID spiffe://university.ecosystem/ns/default/sa/file-processor \
    -parentID "${AGENT_PARENT_ID}" \
    -selector k8s:ns:default \
    -selector k8s:sa:file-processor \
    -ttl 3600

# 4. App Workload (Python FastAPI Backend)
kubectl exec -n spire spire-server-0 -- /opt/spire/bin/spire-server entry create \
    -spiffeID spiffe://university.ecosystem/ns/default/sa/app \
    -parentID "${AGENT_PARENT_ID}" \
    -selector k8s:ns:default \
    -selector k8s:sa:app \
    -ttl 3600

echo "Workload registration completed successfully!"
