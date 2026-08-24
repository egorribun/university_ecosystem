# ADR-012: Centralized Logging with Grafana Loki + Fluent Bit

## Status
Accepted (Wave 32, 2026-03-26)

## Context
All services produce JSON-structured logs (backend: structlog/orjson, Go services: slog, frontend: nginx JSON access logs). Logs are currently only available via `kubectl logs`, making cross-service debugging time-consuming. PII redaction is already enforced at the application layer (RZ-29-02).

## Decision
Adopt **Grafana Loki** as the log aggregation backend with **Fluent Bit** as the Kubernetes DaemonSet-based log collector and **Grafana Alloy** as the Docker Compose collector.

### Why Loki + Fluent Bit
- **Loki**: Label-based indexing (not full-text) — 10x cheaper storage than Elasticsearch for our volume
- **Fluent Bit**: Lightweight (C-based, ~5 MB memory per node), native K8s metadata enrichment, direct Loki output plugin
- **Grafana Alloy**: Grafana's supported collector for Docker discovery and Loki forwarding; it replaces Promtail, which reached end-of-life on 2026-03-02
- **Grafana**: Already deployed for Prometheus dashboards — unified observability plane

### Architecture
```
Pod stdout → kubelet → /var/log/containers/*.log → Fluent Bit DaemonSet → Loki → Grafana
Docker stdout → Docker API → Grafana Alloy → Loki → Grafana
```

### Log Format
All services already emit JSON. Fluent Bit uses the `kubernetes` filter to enrich with pod/namespace/container labels. No application-side changes needed.

### Label Strategy
- `namespace`: `university-ecosystem`
- `app`: extracted from `app.kubernetes.io/name` pod label
- `component`: extracted from `app.kubernetes.io/component` pod label
- `level`: extracted from JSON `level` field (INFO, WARNING, ERROR)

### Retention
- **Hot**: 7 days (Loki default)
- **Cold**: 30 days (S3/MinIO backend, compressed)
- PII-redacted at application layer — safe for 30-day retention

### Sampling
No log sampling — all logs forwarded. Volume is manageable (~50 GB/day uncompressed at production scale). Loki's label-based indexing handles this without full-text indexing overhead.

## Consequences
- Operators can query logs via Grafana LogQL alongside metrics and traces
- Cross-service request tracing via `request_id` field (already present in structured logs)
- No application code changes required — logging format is already compliant
- Requires: Loki deployment (Helm chart: `grafana/loki`), Fluent Bit DaemonSet
- Docker Compose uses the pinned Alloy image and persists read positions in the `alloy-data` volume
