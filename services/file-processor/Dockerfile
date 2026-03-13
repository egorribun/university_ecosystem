# syntax=docker/dockerfile:1.7

# Build stage
FROM golang:1.26.3-alpine3.21 AS builder

WORKDIR /app

RUN apk add --no-cache git ca-certificates

# Copy required dependencies for the replace directive
COPY go.mod go.sum ./
COPY gen/go ./gen/go
COPY services/file-processor/go.mod services/file-processor/go.sum* ./services/file-processor/

WORKDIR /app/services/file-processor
RUN go mod download

# Copy source
COPY services/file-processor .

# Build
RUN CGO_ENABLED=0 GOOS=linux go build \
  -trimpath \
  -ldflags="-w -s -buildid=" \
  -o file-processor ./cmd/file-processor

# Runtime stage
# SEC-04 (audit 2026-03-14): Using Distroless to minimize attack surface
FROM gcr.io/distroless/static-debian12:latest

WORKDIR /app

# Copy binary from builder
COPY --from=builder /app/services/file-processor/file-processor .

# Note: Docker HEALTHCHECK removed in favor of Kubernetes liveness/readiness probes (TD-EXP-02)
USER nonroot:nonroot

CMD ["/app/file-processor"]
