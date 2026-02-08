# syntax=docker/dockerfile:1.7

# Build stage
FROM golang:1.25.5-alpine3.21 AS builder

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
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-w -s" -o file-processor ./cmd/file-processor

# Runtime stage
FROM alpine:3.21.2

RUN apk add --no-cache ca-certificates tzdata \
  && addgroup -S app && adduser -S app -G app

WORKDIR /app

COPY --from=builder --chown=app:app /app/services/file-processor/file-processor .

USER app

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD ps | grep file-processor || exit 1

CMD ["./file-processor"]
