# Kubernetes Manifests

Kubernetes deployment manifests for the University Ecosystem application.

## Structure

- `namespace.yaml` - Application namespace
- `backend/` - Backend API deployment and service
- `frontend/` - Frontend deployment and service
- `secrets-example.yaml` - Example secrets (do not commit real secrets)

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
