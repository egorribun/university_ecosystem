# syntax=docker/dockerfile:1.6

FROM node:22-alpine AS base
WORKDIR /app

FROM base AS deps
COPY frontend/package.json frontend/package-lock.json ./
COPY frontend/scripts ./scripts/
RUN --mount=type=cache,target=/root/.npm npm ci --legacy-peer-deps

FROM base AS builder
ARG VITE_BACKEND_ORIGIN=http://localhost:8000
ENV VITE_BACKEND_ORIGIN=$VITE_BACKEND_ORIGIN
COPY --from=deps /app/node_modules ./node_modules
COPY frontend ./
RUN npm run build

FROM nginx:1.27-alpine AS runtime
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=5 CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1
CMD ["nginx", "-g", "daemon off;"]
