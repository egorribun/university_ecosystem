# Kubernetes Manifests

Kubernetes deployment manifests for the University Ecosystem application.

## Structure

- `namespace.yaml` - Application namespace
- `ingress.yaml` - Edge ingress routing and TLS configuration
- `secrets-example.yaml` - Example secrets (do not commit real secrets)
- `backend/` - Backend API deployment and service
- `frontend/` - Frontend SSR deployment and service
- `outbox-worker/` - Transactional outbox event processor worker
- `flagd/` - OpenFeature feature flag daemon
- `kyverno/` - Kyverno admission control and security policies
- `logging/` - Centralized logging (Fluent Bit / Loki)
- `monitoring/` - Prometheus monitoring, metrics, and dashboards
- `chaos/` - Chaos Mesh fault injection and resilience tests
- `jobs/` - Database migrations and batch jobs
- `spire/` - SPIFFE/SPIRE zero-trust workload attestation

## Usage

```bash
# Create namespace
kubectl apply -f namespace.yaml

# Apply secrets (create from secrets-example.yaml)
kubectl apply -f secrets.yaml

# Deploy backend
kubectl apply -f backend/

# Deploy frontend
kubectl apply -f frontend/
```

## Environment Requirements

- Kubernetes 1.25+
- PostgreSQL database (external or as StatefulSet)
- Redis instance (external or as Deployment)
