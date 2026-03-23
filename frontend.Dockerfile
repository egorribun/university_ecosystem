# syntax=docker/dockerfile:1.7

# Stage 1: Base
FROM node:22-alpine@sha256:8094c002d08262dba12645a3b4a15cd6cd627d30bc782f53229a2ec13ee22a00 AS base
WORKDIR /app

# Stage 2: Dependencies
FROM base AS deps
COPY frontend/package.json frontend/package-lock.json ./
COPY frontend/scripts ./scripts/
RUN --mount=type=cache,target=/root/.npm \
  npm ci --legacy-peer-deps

# Stage 3: Builder
FROM base AS builder
ARG VITE_BACKEND_ORIGIN=""
ENV VITE_BACKEND_ORIGIN=$VITE_BACKEND_ORIGIN
COPY --from=deps /app/node_modules ./node_modules
COPY frontend ./
RUN npm run build

# Stage 4: Runtime
FROM nginxinc/nginx-unprivileged:1.28.2-alpine@sha256:7377697a821c131a924a7105fafbe7414db4e9fcc77a6f08f776f33f141ec3f8 AS runtime

# Copy custom nginx config
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

# Copy build artifacts to nginx public directory
COPY --from=builder --chown=101:101 /app/dist /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=5 \
  CMD wget -qO- http://127.0.0.1:8080/ >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]
