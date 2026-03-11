# syntax=docker/dockerfile:1.7

# Stage 1: Base
FROM node:22-alpine AS base
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
FROM nginxinc/nginx-unprivileged:1.28.2-alpine AS runtime

# Copy custom nginx config
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

# Copy build artifacts to nginx public directory
COPY --from=builder --chown=101:101 /app/dist /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=5 \
  CMD wget -qO- http://127.0.0.1:8080/ >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]
