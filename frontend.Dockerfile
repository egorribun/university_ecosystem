# syntax=docker/dockerfile:1.12

# Stage 1: Base
FROM node:24-alpine@sha256:01743339035a5c3c11a373cd7c83aeab6ed1457b55da6a69e014a95ac4e4700b AS base
WORKDIR /app

# Stage 2: WASM — build Rust WASM packages (rust-crypto + wasm-sanitizer)
FROM rust:1.94.1-slim-bookworm@sha256:5ae2d2ef9875c9c2407bf9b5678e6375304f7ecf8ea46b23e403a5690ec357ec AS wasm-builder
RUN cargo install wasm-pack --locked
WORKDIR /wasm
COPY frontend/rust-crypto ./rust-crypto
COPY frontend/wasm-sanitizer ./wasm-sanitizer
RUN wasm-pack build rust-crypto --target web \
 && wasm-pack build wasm-sanitizer --target web

# Stage 3: Dependencies
FROM base AS deps
COPY frontend/package.json frontend/package-lock.json ./
COPY frontend/scripts ./scripts/
RUN --mount=type=cache,target=/root/.npm \
  npm ci --legacy-peer-deps

# Stage 4: Builder
FROM base AS builder
ARG VITE_BACKEND_ORIGIN=""
ENV VITE_BACKEND_ORIGIN=$VITE_BACKEND_ORIGIN
COPY --from=deps /app/node_modules ./node_modules
COPY frontend ./
# Copy pre-built WASM packages (FIX-44-02: prevents silent WASM build failure)
COPY --from=wasm-builder /wasm/rust-crypto/pkg ./rust-crypto/pkg
COPY --from=wasm-builder /wasm/wasm-sanitizer/pkg ./wasm-sanitizer/pkg
RUN npm run build

# Stage 5: Runtime
FROM nginxinc/nginx-unprivileged:1.28.2-alpine@sha256:7377697a821c131a924a7105fafbe7414db4e9fcc77a6f08f776f33f141ec3f8 AS runtime

# Copy custom nginx config
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

# Copy build artifacts to nginx public directory
COPY --from=builder --chown=101:101 /app/dist /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=5 \
  CMD wget -qO- http://127.0.0.1:8080/ >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]
