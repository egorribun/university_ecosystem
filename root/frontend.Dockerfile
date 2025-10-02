# syntax=docker/dockerfile:1.6

FROM node:20-alpine AS base
WORKDIR /app

FROM base AS deps
COPY root/frontend/package*.json ./
RUN npm ci

FROM base AS development
COPY --from=deps /app/node_modules ./node_modules
COPY root/frontend ./
RUN addgroup -S app && adduser -S app -G app \
    && chown -R app:app /app
USER app
EXPOSE 5173
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 CMD wget -qO- http://localhost:5173/ >/dev/null || exit 1
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
