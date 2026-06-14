# syntax=docker/dockerfile:1.12

# Build stage
FROM golang:1.26.4-alpine3.22@sha256:cff7cf3120cd74bf0960cfe19a3efb6631161148d8e070f76976f73a13b2e3d4 AS builder

WORKDIR /app

RUN apk add --no-cache git ca-certificates

# Copy required dependencies for the replace directive
COPY go.mod go.sum ./
COPY gen/go ./gen/go
COPY services/file-processor/go.mod services/file-processor/go.sum* ./services/file-processor/

WORKDIR /app/services/file-processor
# Retry to tolerate transient "unexpected EOF" from proxy.golang.org under
# bandwidth contention with parallel compose builds (Go does not retry zip
# fetches; partial downloads persist within the RUN, so retries resume).
RUN n=0; until go mod download; do \
      n=$((n + 1)); \
      if [ "$n" -ge 5 ]; then echo "go mod download failed after $n attempts" >&2; exit 1; fi; \
      echo "go mod download failed, retry $n/5 in 5s..."; \
      sleep 5; \
    done

# Copy source
COPY services/file-processor .

# Build
RUN CGO_ENABLED=0 GOOS=linux go build \
  -trimpath \
  -ldflags="-w -s -buildid=" \
  -o file-processor ./cmd/file-processor

# Wave 137 SW5 — health-probe binary stage
# Fetches grpc_health_probe binary for compose-level healthcheck of distroless
# runtime. file-processor's main.go already registers grpc_health_v1 server
# (services/file-processor/cmd/file-processor/main.go:277-280) but distroless
# images lack any HTTP/gRPC client. Same pattern as authzed/spicedb image
# (used at docker-compose.full.yml:435).
FROM alpine:3.20 AS health-probe
ARG GRPC_HEALTH_PROBE_VERSION=v0.4.27
# Retry to tolerate transient network errors from the GitHub release CDN under
# bandwidth contention with parallel compose builds. -O truncates on retry, so
# no stale partial; the until loop hard-fails after 5 attempts.
RUN apk add --no-cache wget && \
    n=0; until wget -qO /grpc_health_probe \
      "https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/${GRPC_HEALTH_PROBE_VERSION}/grpc_health_probe-linux-amd64"; do \
      n=$((n + 1)); \
      if [ "$n" -ge 5 ]; then echo "grpc_health_probe download failed after $n attempts" >&2; exit 1; fi; \
      echo "grpc_health_probe download failed, retry $n/5 in 5s..."; \
      sleep 5; \
    done && \
    chmod +x /grpc_health_probe

# Runtime stage
# SEC-04 (audit 2026-03-14): Using Distroless to minimize attack surface
FROM gcr.io/distroless/static-debian12:latest@sha256:20bc6c0bc4d625a22a8fde3e55f6515709b32055ef8fb9cfbddaa06d1760f838

WORKDIR /app

# Copy binary from builder
COPY --from=builder /app/services/file-processor/file-processor .

# Wave 137 SW5: copy grpc_health_probe for compose-level healthcheck.
COPY --from=health-probe /grpc_health_probe /usr/local/bin/grpc_health_probe

# Wave 140 SW2: copy GraphQL schema. main.go:286 reads it via
# os.ReadFile("schema.graphql") relative to WORKDIR /app. Without this COPY
# the runtime exits at step 9 with "schema.graphql not found", which blocks
# the gRPC bind in step 10 → healthcheck fails → restart loop
# (W139 §Honesty #7). Mirrors the binary + grpc_health_probe COPY pattern.
COPY --from=builder /app/services/file-processor/schema.graphql ./schema.graphql

USER nonroot:nonroot

CMD ["/app/file-processor"]
