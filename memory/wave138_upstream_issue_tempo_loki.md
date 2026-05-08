### Summary

The official `grafana/tempo:2.x` (and `grafana/loki:3.x`) Docker images use distroless bases that lack any HTTP client (`wget`, `curl`, `nc`, `bash`, `/dev/tcp` shell builtin). This means `docker-compose.yml` `healthcheck` blocks cannot probe the existing `/ready` HTTP endpoint without either:

1. **Custom Dockerfile**: `FROM grafana/tempo:2.x` + `RUN apk add --no-cache curl` (broken — distroless doesn't have apk; needs `FROM ... AS source` + multi-stage `COPY --from=alpine`).
2. **Sidecar pattern**: separate `curlimages/curl:latest` container with `network_mode: service:tempo`. Works but adds container, breaks `depends_on: condition: service_healthy` semantics for downstream consumers (sidecar healthiness ≠ tempo container healthiness in `docker compose ps`).
3. **gRPC health probe**: `grpc_health_probe` binary (used by the spicedb image and similar) requires gRPC health protocol registered in the binary; tempo + loki don't expose gRPC health endpoints AFAICT.

### Feature request

Add a CLI subcommand to the `tempo` (and `loki`) binary that checks readiness without needing an HTTP client:

```sh
tempo --check-ready  # exits 0 if ready, non-zero otherwise
```

Or a similar subcommand. This would let docker-compose users write:

```yaml
healthcheck:
  test: ["CMD", "tempo", "--check-ready"]
  interval: 10s
  timeout: 5s
  retries: 3
  start_period: 20s
```

Same pattern as `imgproxy health` (which we use successfully — imgproxy distroless image has CLI built in).

### Reproduction (current pain point)

In our `docker-compose.full.yml`:

```yaml
tempo:
  image: grafana/tempo:2.10.3
  command: ["-config.file=/etc/tempo/tempo.yaml"]
  # NO healthcheck possible without sidecar
  # ...

# Sidecar workaround:
tempo-healthprobe:
  image: curlimages/curl:8.10.1
  network_mode: "service:tempo"
  depends_on: [tempo]
  command: ["sleep", "infinity"]
  healthcheck:
    test: ["CMD", "curl", "-fsS", "http://localhost:3200/ready"]
    interval: 10s
    # ...
```

This works but doesn't make `docker compose ps tempo` show `(healthy)` — only the sidecar shows that. So we can't use `depends_on: condition: service_healthy` for downstream services that depend on tempo.

### Suggested implementation

A `--check-ready` subcommand that just calls the existing `/ready` HTTP handler internally (no separate process or HTTP client needed since binary already implements the handler logic). Exit 0 if `/ready` would respond 200, non-zero otherwise.

### Use case

- Local dev via docker-compose (most common)
- Kubernetes runs alpine sidecars or uses `httpGet` probe (different API), so this is less critical there
- CI pipelines that bring up tempo + loki for integration tests
