# syntax=docker/dockerfile:1.7

FROM rust:1.85.0-slim-bookworm AS builder

# Install build dependencies:
# - protobuf-compiler/libprotobuf-dev for gRPC/Protobuf
# - pkg-config/libssl-dev for OpenSSL (often used for telemetry/auth)
RUN apt-get update && apt-get install -y --no-install-recommends \
  protobuf-compiler \
  libprotobuf-dev \
  pkg-config \
  libssl-dev \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY proto proto
COPY services/rust-optimizer services/rust-optimizer
RUN cp -r /usr/include/google proto/ || echo "Google protos not found in /usr/include"

WORKDIR /app/services/rust-optimizer
RUN --mount=type=cache,target=/usr/local/cargo/registry \
  --mount=type=cache,target=/app/services/rust-optimizer/target \
  cargo build --release && \
  cp target/release/rust-optimizer /app/rust-optimizer

# Runtime stage
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
  libssl3 \
  ca-certificates \
  wget \
  && rm -rf /var/lib/apt/lists/* \
  && groupadd --system app && useradd --system --gid app app

WORKDIR /app

COPY --from=builder --chown=app:app /app/rust-optimizer .

USER app

# Basic healthcheck that checks if process is running
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1:8080/health >/dev/null || exit 1

CMD ["./rust-optimizer"]
