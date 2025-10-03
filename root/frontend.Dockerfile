# syntax=docker/dockerfile:1.6

FROM node:20-alpine AS base
WORKDIR /app

FROM base AS deps
COPY root/frontend/package.json root/frontend/package-lock.json ./
RUN npm ci

FROM base AS runner
RUN addgroup -S app && adduser -S -G app app
COPY --from=deps /app/node_modules ./node_modules
COPY root/frontend ./
USER app
EXPOSE 5173
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=5 CMD wget -qO- http://127.0.0.1:5173/ >/dev/null || exit 1
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
