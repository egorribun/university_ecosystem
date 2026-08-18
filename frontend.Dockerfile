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
# Copy built WASM packages so local file: dependencies exist and satisfy ensure-wasm preinstall check
COPY --from=wasm-builder /wasm/rust-crypto/pkg ./rust-crypto/pkg
COPY --from=wasm-builder /wasm/wasm-sanitizer/pkg ./wasm-sanitizer/pkg
# Retry to tolerate transient ECONNRESET / "network aborted" from the npm
# registry under bandwidth contention with parallel compose builds (npm does
# not reliably retry a mid-stream socket reset). The /root/.npm cache mount
# means already-fetched tarballs resume from cache on retry.
RUN --mount=type=cache,target=/root/.npm \
  n=0; until npm ci --legacy-peer-deps; do \
    n=$((n + 1)); \
    if [ "$n" -ge 5 ]; then echo "npm ci failed after $n attempts" >&2; exit 1; fi; \
    echo "npm ci failed (network), retry $n/5 in 5s..."; \
    sleep 5; \
  done

# Stage 4: Builder
FROM base AS builder
ENV SKIP_WASM_BUILD=1
ARG VITE_BACKEND_ORIGIN=""
ENV VITE_BACKEND_ORIGIN=$VITE_BACKEND_ORIGIN
# W153 SW1 — opt-in unminified bundle + linked source maps so the wedged
# renderer error becomes readable in Chrome DevTools via stack traces.
# Defaults to empty (production minified) so CI / prod deploys are
# untouched. Only the dev compose (docker-compose.full.yml) should set
# this to "true". KEEPS mode=production to preserve JSX transform
# (jsx() not jsxDEV()) so SSR runtime stays compatible with production
# react-dom-server. Initial SW1 attempt used FRONTEND_BUILD_MODE=development
# which broke SSR with jsxDEV runtime mismatch — see commit history.
ARG FRONTEND_BUILD_UNMINIFIED=""
ENV FRONTEND_BUILD_UNMINIFIED=$FRONTEND_BUILD_UNMINIFIED
# W156 SW1 Tier 1 #1 — opt-in development React for /login wedge diagnosis.
# Aliases react-dom/client → cjs/react-dom-client.development.js +
# scopes NODE_ENV=development to client environment in vite.config.mts.
# Captures FULL React #418 error message in Firefox DevTools (Windows
# wedge persists post-W155 across Chrome regular/Incognito/Firefox).
# Same scope/safety as FRONTEND_BUILD_UNMINIFIED: dev compose only,
# NEVER set in CI / production deploys (would ship dev React bundle
# ~150 KB larger + slower runtime checks).
ARG FRONTEND_REACT_DEV_MODE=""
ENV FRONTEND_REACT_DEV_MODE=$FRONTEND_REACT_DEV_MODE
COPY --from=deps /app/node_modules ./node_modules
COPY frontend ./
# Copy pre-built WASM packages (FIX-44-02: prevents silent WASM build failure)
COPY --from=wasm-builder /wasm/rust-crypto/pkg ./rust-crypto/pkg
COPY --from=wasm-builder /wasm/wasm-sanitizer/pkg ./wasm-sanitizer/pkg

# Wave 132 polish — vite-plugin-pwa injectManifest hangs post-prerender on
# Linux Docker (BuildKit + Docker Desktop on Windows + WSL2 virtualized
# filesystem makes workbox-build's glob scan over 200+ chunks effectively
# infinite). Same root cause as W126 polish #3 / W127 SW7 Windows-host
# hang documented in CLAUDE.md. Local workaround is `wave127-build-x3.sh`
# watch+kill — applying the same pattern here:
#   1. Spawn `npm run build` in background → log to /tmp/build.log
#   2. Wait up to 240s for `dist/server/server.js` (signals vite client
#      build + ssr build + tanstackStart prerender all done — visible in
#      log as "[prerender] Prerendered 1 pages")
#   3. Brief 5s settle, then SIGKILL the npm chain (which would otherwise
#      hang on injectManifest → workbox-build glob scan)
#   4. Run `npm run build:shell` standalone — emits `_shell.html` with CSP
#      nonce + font preload injection + mirrors to `index.html` for
#      static-serve compat
# Trade-off: vite-plugin-pwa's `dist/client/sw.js` may be missing or
# unresolved (`__WB_MANIFEST` placeholder unreplaced) → browser /sw.js
# fetch may 404 → service worker registration fails → no PWA precache.
# Runtime caching strategies handled at app code level still work via
# Caddy. Acceptable for Docker dev runtime; production CI Linux build
# (`frontend-tests.yml`) runs without this workaround + emits full sw.js.
# post-build-shell.mjs is idempotent for CSP nonce + LHCI placeholder
# (regex skip already-applied) + mirror; font preloads may double-inject
# but browser dedupes by href — safe.
RUN set -e; \
    echo "=== Build with watch+kill workaround (vite-plugin-pwa hang mitigation) ==="; \
    # Wave 137 SW4 fix: clear dist/ before build so watch+kill detects FRESH
    # artifacts (not stale copy from host frontend/dist/). The .dockerignore
    # `dist/` pattern only matches top-level, not `frontend/dist/`, so stale
    # host dist/ leaks into the build context via `COPY frontend ./`.
    # Pre-W137 SW4 this masked W134-W136 "byte-identical reproducibility"
    # claims because the watch+kill exited immediately on the copied dist.
    rm -rf dist; \
    npm run build > /tmp/build.log 2>&1 & \
    BUILD_PID=$!; \
    i=0; \
    while [ $i -lt 240 ]; do \
      if [ -f dist/server/server.js ]; then break; fi; \
      sleep 1; \
      i=$((i+1)); \
    done; \
    if [ ! -f dist/server/server.js ]; then \
      echo "BUILD FAILED — dist/server/server.js missing after 240s"; \
      tail -100 /tmp/build.log; \
      kill -9 $BUILD_PID 2>/dev/null || true; \
      exit 1; \
    fi; \
    echo "=== dist/server/server.js detected, settling 5s before kill ==="; \
    sleep 5; \
    kill -9 $BUILD_PID 2>/dev/null || true; \
    ps -ef 2>/dev/null | awk '/node.*(vite|run-build|build:shell)/ && !/awk/ {print $2}' | xargs -r kill -9 2>/dev/null || true; \
    sleep 1; \
    echo "=== running build:shell standalone (post-build-shell.mjs) ==="; \
    npm run build:shell 2>&1 | tee /tmp/build-shell.log; \
    echo "=== Build watch+kill complete ==="; \
    ls -la dist/server/server.js dist/client/_shell.html dist/client/index.html 2>&1 || true; \
    ls dist/client/assets/index-*.js 2>&1 | head -3 || true

# Stage 5: Production-only dependencies (Wave 131 SW3 — Node SSR runtime)
# Mirrors the `deps` stage but with `--omit=dev` so the runtime image does
# not ship Storybook / Vite / Vitest / Playwright / etc. (~60 devDependencies).
# `dist/server/server.js` imports external runtime deps (react, @tanstack/*,
# h3-v2, seroval, jose, ...) that must be resolvable at runtime.
FROM base AS prod-deps
COPY frontend/package.json frontend/package-lock.json ./
COPY frontend/scripts ./scripts/
# Copy built WASM packages so local file: dependencies exist and satisfy ensure-wasm preinstall check
COPY --from=wasm-builder /wasm/rust-crypto/pkg ./rust-crypto/pkg
COPY --from=wasm-builder /wasm/wasm-sanitizer/pkg ./wasm-sanitizer/pkg
# Drop dev-only lifecycle scripts before `npm ci`:
#   - `prepare` runs `husky ../.husky` (Git hooks setup); husky lives in
#     devDependencies so it's missing under `--omit=dev` → exit code 127.
#   - `postinstall` runs `setup-lhci-binaries.cjs` which downloads Chrome
#     (~50 MB) for LHCI testing; pure dev-time, not needed in runtime.
# `preinstall` (ensure-wasm.mjs that creates placeholder pkg/ dirs for the
# wasm-sanitizer + rust-crypto file:// deps) is preserved and still runs.
RUN npm pkg delete scripts.prepare scripts.postinstall
# Retry to tolerate transient ECONNRESET / "network aborted" from the npm
# registry under bandwidth contention with parallel compose builds (this step
# failed exactly that way). The /root/.npm cache mount resumes from cache.
RUN --mount=type=cache,target=/root/.npm \
  n=0; until npm ci --omit=dev --legacy-peer-deps; do \
    n=$((n + 1)); \
    if [ "$n" -ge 5 ]; then echo "npm ci failed after $n attempts" >&2; exit 1; fi; \
    echo "npm ci failed (network), retry $n/5 in 5s..."; \
    sleep 5; \
  done

# Stage 6: Runtime — Node SSR (Wave 131 Phase 4)
# Replaces the prior `nginxinc/nginx-unprivileged:1.28.2-alpine` runtime
# that just served a static SPA shell. tanstackStart's server entry
# (`dist/server/server.js`, generated by `npm run build`) is bound to a
# standard Node `http.createServer` via the thin `scripts/server-prod.mjs`
# wrapper introduced in W131 SW1. Listens on PORT env (default 3000) on
# 0.0.0.0; Caddy `health_uri` + k8s livenessProbe / readinessProbe hit
# `/healthz` (W131 SW2 fast path that short-circuits before SSR).
#
# The obsolete nginx runtime and `frontend/nginx.conf` were removed after the
# SSR rollout. Edge routing is owned by `services/caddy/Caddyfile`.
FROM node:24-alpine@sha256:01743339035a5c3c11a373cd7c83aeab6ed1457b55da6a69e014a95ac4e4700b AS runtime

WORKDIR /app

# package.json is needed at runtime so Node resolves "type": "module"
# correctly and so the wasm-sanitizer / rust-crypto file:// references
# (declared as runtime dependencies) match the node_modules layout.
COPY --from=prod-deps --chown=node:node /app/package.json ./package.json

# Production-only node_modules — no devDependencies. ~150 MB → ~80 MB
# vs full deps (saves Storybook/Playwright/Vitest/etc.).
COPY --from=prod-deps --chown=node:node /app/node_modules ./node_modules

# Copy built WASM packages to runtime so Node resolves the file: dependencies at runtime
COPY --from=wasm-builder --chown=node:node /wasm/rust-crypto/pkg ./rust-crypto/pkg
COPY --from=wasm-builder --chown=node:node /wasm/wasm-sanitizer/pkg ./wasm-sanitizer/pkg

# server-prod.mjs Node wrapper (W131 SW1) — imports dist/server/server.js
# default export, adapts Web Standards Request <-> Node IncomingMessage,
# binds http.createServer on PORT/HOST.
#
# Wave 175 polish-followup: contentTypes.mjs is server-prod.mjs's sibling
# module (W175 SW8 extracted CONTENT_TYPES map for side-effect-free import
# in regression tests at frontend/src/__tests__/serverProdContentTypes.test.ts).
# server-prod.mjs does `import { CONTENT_TYPES } from "./contentTypes.mjs"`.
# Without copying both files, Node ESM resolver throws ERR_MODULE_NOT_FOUND
# at runtime startup → frontend container crashes → Caddy "no upstreams
# available" 503 cascade (caught via user Docker rebuild test).
# The `.d.mts` TypeScript declarations are NOT copied — runtime-only Node
# doesn't need them.
COPY --chown=node:node frontend/scripts/server-prod.mjs ./scripts/server-prod.mjs
COPY --chown=node:node frontend/scripts/contentTypes.mjs ./scripts/contentTypes.mjs

# Build artifacts:
#   dist/client/_shell.html + dist/client/index.html (mirror) + dist/client/assets/
#   dist/server/server.js (tanstackStart server entry — what wrapper imports)
#   dist/sw.js + dist/sw.js.map (PWA service worker)
COPY --from=builder --chown=node:node /app/dist ./dist

# Drop to non-root `node` user (UID/GID 1000, built into node:alpine images).
USER node

ENV NODE_ENV=production
ENV PORT=3000
ENV HOST=0.0.0.0

EXPOSE 3000

# Health check hits /healthz fast path. wget is provided by busybox in
# alpine images; --spider sends HEAD only (no body download).
# start-period 15s gives Node enough time to import server.js + bind port
# on cold start; subsequent intervals are 30s.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD wget --quiet --tries=1 --spider http://127.0.0.1:3000/healthz || exit 1

CMD ["node", "scripts/server-prod.mjs"]
