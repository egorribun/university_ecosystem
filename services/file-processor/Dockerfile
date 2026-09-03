# syntax=docker/dockerfile:1.12

# Build stage
FROM golang:1.26.6-alpine3.24@sha256:af8d6740070b8906d12eae1c3e3ea0957fb63f492051ea05e354c38ef9fe88df AS builder

WORKDIR /app

RUN apk add --no-cache git ca-certificates

# Copy required dependencies for the replace directive
COPY go.mod go.sum ./
COPY gen/go ./gen/go
COPY services/pkg/logging ./services/pkg/logging
COPY services/pkg/spiffe ./services/pkg/spiffe
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

# Build the health probe from checksum-verified source with the same patched Go
# toolchain as the service. Upstream release binaries can lag behind Go and
# transitive security patches even when the release itself is current.
FROM golang:1.26.6-alpine3.24@sha256:af8d6740070b8906d12eae1c3e3ea0957fb63f492051ea05e354c38ef9fe88df AS health-probe
ARG GRPC_HEALTH_PROBE_VERSION=v0.4.51
ENV GOTOOLCHAIN=local
WORKDIR /probe
RUN probe_module="github.com/grpc-ecosystem/grpc-health-probe@${GRPC_HEALTH_PROBE_VERSION}" && \
    n=0 && \
    until go mod download "$probe_module"; do \
      n=$((n + 1)); \
      if [ "$n" -ge 5 ]; then echo "grpc-health-probe source download failed after $n attempts" >&2; exit 1; fi; \
      echo "grpc-health-probe source download failed, retry $n/5 in 5s..."; \
      sleep 5; \
    done && \
    cp -R "$(go env GOMODCACHE)/${probe_module}/." . && \
    chmod -R u+w . && \
    go get \
      github.com/spiffe/go-spiffe/v2@v2.7.0 \
      google.golang.org/grpc@v1.83.1 \
      golang.org/x/net@v0.57.0 \
      golang.org/x/text@v0.40.0 && \
    go mod tidy && \
    CGO_ENABLED=0 GOOS=linux go build \
      -trimpath \
      -ldflags="-w -s -buildid= -X main.versionTag=${GRPC_HEALTH_PROBE_VERSION}" \
      -o /grpc_health_probe .

# Runtime stage
# SEC-04 (audit 2026-03-14): Using Distroless to minimize attack surface
FROM gcr.io/distroless/static-debian12@sha256:20bc6c0bc4d625a22a8fde3e55f6515709b32055ef8fb9cfbddaa06d1760f838

WORKDIR /app

# Copy binary from builder
COPY --from=builder /app/services/file-processor/file-processor .

# Copy the locally rebuilt probe for the compose-level healthcheck.
COPY --from=health-probe /grpc_health_probe /usr/local/bin/grpc_health_probe

# Copy the GraphQL schema. main.go reads it relative to WORKDIR /app.
# Without this COPY
# the runtime exits at step 9 with "schema.graphql not found", which blocks
# the gRPC bind and causes the healthcheck to fail.
COPY --from=builder /app/services/file-processor/schema.graphql ./schema.graphql

USER nonroot:nonroot

#checkov:skip=CKV_DOCKER_2:health is enforced by the Kubernetes probes and compose grpc-health-probe.

CMD ["/app/file-processor"]
