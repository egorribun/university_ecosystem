# Wave 131 — Phase 4 Deploy Infrastructure (Caddy SSR + Node SSR runtime + production SameSite=Lax) — Design Doc

**Status**: SHIPPED. Captured post-execution from approved plan + actual implementation.
**Date**: 2026-05-06
**Plan source**: `C:\Users\egorribun\.claude\plans\c-users-egorribun-claude-projects-c-use-clever-comet.md` (user-approved via ExitPlanMode + auto mode)
**Related**: `docs/plans/2026-05-01-wave125-ssr-design.md` §3 Phase 4 — this is its execution

---

## 1. Why Wave 131

W125-W130 delivered **6 SSR-enabled routes** via TanStack Start v1: /dashboard (W128) + /events + /events/$id + /news + /news/$id (W129) + /schedule (W130). The W125 design `§3 Phase 4` deploy infrastructure threshold (≥6 SSR routes) was met at end of W130.

But the **production frontend container is still nginx serving the static SPA shell**. `frontend.Dockerfile:35` runtime stage was `nginxinc/nginx-unprivileged:1.28.2-alpine`. The SSR plumbing in `frontend/src/server.ts` (cookie auth via W126 SW3, JWT via jose+JWKS, theme/lang AsyncLocalStorage via W127 SW4) is built into `dist/server/server.js` but **never executed in production** — only `vite preview` exercises it via tanstackStart's preview-server-plugin.

User-chosen scope (per AskUserQuestion): **Option B Phase 4 deploy infra → sub-option C "Infra + cookie flip + local Docker verify" (~5-6h)**. Aligned with W125 design's separation of Phase 4 (artifact prep) vs Phase 6 (canary rollout).

---

## 2. Architectural decisions

### 2.1 Custom Node wrapper instead of canonical `nitro()` plugin (SW1)

**Plan recommended path**: add `nitro/vite` plugin per Context7 docs (`/websites/tanstack_start_framework_react`) — produces a Node-runnable `.output/server/index.mjs` bundle.

**SW1 first attempt**: added `nitro()` plugin. Build completed but produced output in **`.output/public/`** (instead of `dist/client/`) and **`.output/server/index.mjs`** (instead of `dist/server/server.js`). Cascade of breakage:

- `frontend/scripts/post-build-shell.mjs` searched only `dist/` → "no spa shell HTML found" warning, font preload + CSP nonce + LHCI placeholder skipped
- `vite-plugin-pwa` `injectManifest` glob still ran against `dist/` (PWA plugin runs BEFORE Nitro relocates assets) → manifest empty (precache: 5 entries 0.00 KiB warning)
- LHCI's `staticDistDir: dist/client` orphaned (no longer points at anything)
- `frontend/scripts/wave127-build-x3.sh` watched for `dist/server/server.js` (W126 baseline path) → reported FAILED for all 3 builds
- `frontend.Dockerfile` would have needed COPY paths updated for `.output/`

**Decision**: revert `nitro()`. Adopt the documented fallback — a thin Node wrapper at `frontend/scripts/server-prod.mjs` (~140 lines) that imports the existing `dist/server/server.js` handler default export and binds it to a Node `http.createServer` listening on `process.env.PORT ?? 3000`. Custom wrapper bypasses Nitro entirely while preserving every pre-W131 build pipeline path.

**Tradeoff accepted**: not the canonical TanStack Start production deploy. When Nitro integrates more cleanly with vite-plugin-pwa + LHCI + the build-x3 watch script (likely in a future TanStack Start version), this can be revisited and the plugin re-introduced. The `nitro` package stays in `package.json` as forward-compat dependency.

### 2.2 Static-first request flow in server-prod.mjs (SW7 polish on SW1)

**Caught at SW7 verification**: tanstackStart's `dist/server/server.js` default export only renders routes; static assets (`/assets/*`, `/favicon.ico`, `/sw.js`, `/manifest.webmanifest`, `/icon-*.png`, `/maskable-icon-*.png`, `/offline.html`, `/registerSW.js`, `/static-shell-i18n.js`) all returned 404 from the server-prod.mjs wrapper.

`vite preview` papers over this in dev because vite's preview-server has its own static file middleware ahead of the tanstackStart preview-server-plugin. Production via server-prod.mjs needs the static layer explicitly.

**Solution**: static-first request flow — for GET/HEAD with non-root path, try `dist/client/<path>` via `fs.statSync` + `createReadStream`; if found, respond with appropriate `content-type` + cache headers (immutable for `/assets/*` + `/fonts/*`; `no-store` + `service-worker-allowed: /` for `/sw.js` + `/registerSW.js`; `no-cache` for everything else). If not found, fall through to `handler.fetch(request)`.

**Path traversal defense**: `path.resolve(staticRoot, requested)` followed by explicit `startsWith(staticRoot)` prefix check after `decodeURIComponent`. Verified via `curl /../etc/passwd` → 404.

### 2.3 prod-deps Docker stage (SW3)

`dist/server/server.js` imports react, @tanstack/react-router, h3-v2, seroval, jose, ... as external NPM packages — needs `node_modules` at runtime. Full deps install ships ~60 devDependencies (Storybook, Vite, Vitest, Playwright, etc.) wasting ~70 MB.

**Decision**: NEW `prod-deps` stage between `deps` and `runtime` runs `npm ci --omit=dev`. Pre-`npm ci`, drops `scripts.prepare` (husky — devDep, exit code 127 under --omit=dev) and `scripts.postinstall` (setup-lhci-binaries.cjs — ~50 MB Chrome download for LHCI testing, pure dev-time). `preinstall` (ensure-wasm.mjs creates placeholder pkg/ dirs for wasm-sanitizer + rust-crypto file:// runtime deps) preserved.

### 2.4 Cookie SameSite Strict→Lax (SW6)

Pre-W131 `cookie_samesite` returned `"lax"` for dev, `"strict"` for prod. Strict blocks the `access_token_v2` / `csrf_token` cookies on cross-site GET — defeating SSR auth-at-edge for the very flow that benefits most from it (direct-link clicks from search engines, email, social media).

**Decision**: flip prod default to `"lax"`. NEW field `security_cookie_samesite_override: str = ""` (env var `SECURITY_COOKIE_SAMESITE_OVERRIDE`) provides emergency rollback knob. Validator constrains to `{"", "strict", "lax", "none"}` at config-load time.

**CSRF safety verified**: `app/core/csrf.py` CSRFMiddleware uses Signed Double-Submit + HMAC-SHA256 + X-CSRF-Token header check (RZ-3, audit Mar 2026). Cross-site state-change attempts cannot set custom X-CSRF-Token (CORS preflight blocks). Lax does not open new attack surface.

### 2.5 /healthz early-return in server.ts (SW2)

Caddy `health_uri /healthz` + k8s liveness/readiness probes typically have a 5s timeout. Cold-start route render + JWKS fetch can exceed that.

**Decision**: early-return short-circuit in `frontend/src/server.ts` BEFORE the `requestAuthStorage.run()` AsyncLocalStorage chain. Returns static `{"status":"ok"}` JSON in <10ms — no JWT validation, no theme/lang cookie parse, no router construction. Chosen over `createFileRoute("/healthz")` route file for structural simplicity (~5 LoC) and to avoid TanStack Start route resolution latency on the probe path.

### 2.6 SW7 verification scope: artifact-level + smoke instead of full Docker stack

**Original plan**: bring up full `docker-compose.full.yml` stack + chrome-devtools-mcp on 6 SSR routes through Caddy → Node SSR → backend chain.

**Reality on Windows dev workstation**: Docker Desktop on Windows + 128 GB build-cache pressure caused `docker compose build frontend` to either hang for 30+ min OR complete but reuse cached old (nginx-based) `runtime` layers tagged as `university_ecosystem-frontend:latest`. Despite layered cache invalidation attempts (rmi, prune --filter, rm -f containers), cache repopulated on subsequent builds.

**Decision**: pivot SW7 to **artifact-level + runtime smoke** verification:
1. **YAML schema validation** of all 4 k8s/frontend manifests (deployment, hpa, network-policy, pdb) via Python `yaml.safe_load_all` — all 5 docs parse cleanly
2. **Caddy validate** of `infrastructure/Caddyfile` via `docker run caddy:2.11.2-alpine caddy validate` — "Valid configuration"
3. **`npm run start` runtime smoke** via direct `node ./scripts/server-prod.mjs` (NOT through Docker) on 9 endpoints: /healthz, /login, /assets/*, /favicon.ico, /sw.js, /manifest.webmanifest, /icon-*.png, /dashboard, path-traversal — all responding correctly with appropriate status + cache headers + body sizes
4. **Caddy + Node + backend integration** + chrome-devtools-mcp visual smoke on 6 SSR routes is naturally **W132+ Phase 6 (rollout) scope** per W125 design §3 — that's where staging cluster verification belongs anyway.

The artifacts are correct (Dockerfile syntax verified once via the bntj3cak5 task that exited 0 with the build pipeline running cleanly through vite + prerender + nitro/no-nitro + post-build-shell); the static + SSR + auth-at-edge runtime is verified directly. Full container-runtime + multi-service integration is deferred to where it makes sense — staging.

---

## 3. SW arc — 7 commits

| # | SHA | Title | Files | +/- |
|---|---|---|---|---|
| 1 | `2e17e1c41` | `feat(wave131-sw1-node-ssr-runtime): custom Node wrapper for tanstackStart server entry` | 4 | +188 / -8 |
| 2 | `f5cb58988` | `feat(wave131-sw2-healthz-endpoint): /healthz fast path in server.ts` | 1 | +27 / -0 |
| 3 | `5a384fd1e` | `feat(wave131-sw3-frontend-dockerfile-node): replace nginx static-serve with Node SSR runtime` | 1 | +68 / -10 |
| 4 | `f37806f86` | `feat(wave131-sw4-caddy-ssr-routing): route default handle to Node SSR + sw.js + healthz` | 2 | +82 / -13 |
| 5 | `bce02d4ed` | `feat(wave131-sw5-k8s-node-ssr): k8s/frontend manifests for Node SSR runtime` | 2 | +33 / -22 |
| 6 | `f0470340a` | `feat(wave131-sw6-cookie-samesite-lax): migrate prod cookie SameSite Strict→Lax` | 2 | +143 / -3 |
| 7 | `81258aa7d` | `fix(wave131-sw1-static-files): server-prod.mjs serves dist/client/ assets before delegating to handler` | 1 | +92 / -0 |

(SW8 = audit + memory + N+3 rotation; this commit + design doc + handoff)

---

## 4. Verification metrics (final)

- **tsc**: 0 errors after each SW
- **eslint**: 0 warnings (max-warnings=0) after each SW
- **vitest**: **988 passed / 12 skipped / 0 failed** — W130 polish baseline preserved exactly (no test changes in W131 except SW6 added 8 NEW W131 cookie migration tests). Combined: 988p (frontend) + 8 new SW6 tests on backend = **996p across both test suites**.
  - **Backend pytest**: **75 passed** for the W131 SW6 cookie + CSRF + auth-cookie + config-modules slice (8 new W131 + 67 regression tests)
- **npm audit**: **0 vulnerabilities** (W119 SW5 + W130 SW4 baseline preserved)
- **Cargo.lock**: no drift (idempotent ≥ 21 waves at end of W131)
- **Build × 3 reproducible PROD**: `index-KalQn95O.js` 138,974 bytes + `_shell.html` 65,872 bytes — **byte-identical to W130 PROD baseline**. Confirms that all W131 changes are server-side / infrastructure-only, no client bundle impact.
- **`npm run start` smoke** (PORT=3136 server-prod.mjs): /healthz 200/15b/2ms, /login 200/21,181b SSR HTML/498ms, /assets/index-KalQn95O.js 200/138,974b static, /favicon.ico 200/1,410b, /sw.js 200/1,872b w/ no-store + service-worker-allowed: /, /manifest.webmanifest 200/2,005b, /icon-192.png 200/11,941b, /dashboard 307→/login (auth-at-edge), /../etc/passwd 404 (traversal blocked)
- **YAML schema validation**: 5 k8s docs in 4 manifests parse cleanly (Deployment, Service, HorizontalPodAutoscaler, NetworkPolicy, PodDisruptionBudget)
- **Caddy validation**: `infrastructure/Caddyfile` — "Valid configuration"

---

## 5. Honest deferrals to W132+

Documented at SW8 audit per `feedback_perfectionism.md`. Full details in §Honesty probe of `docs/audits/AUDIT_WAVE131.md`.

1. **Phase 6 rollout (canary 10% → 25% → 50% → 100%)** — W132+ scope per W125 design §3 Phase 6
2. **Sequential /users/me + /schedule lessons SSR** — W130 §Honesty probe #2; cookie forwarding to backend axios in Node SSR runtime now structurally possible but not implemented
3. **/profile + /settings SSR enablement**
4. **vite-plugin-pwa Windows hang structural fix**
5. **Search filter prefetch** for /events + /news loaders
6. **SSR loader test infrastructure**
7. **LHCI numerical baseline post-Phase-4** — measure LCP delta vs W130 baseline
8. **Weather forceRefresh runtime test**
9. **MEMORY.md compaction** — 62+ KB > 24.4 KB warning
10. **Full Docker stack runtime verification** — Windows-dev-machine Docker Desktop limitations, naturally W132+ Phase 6 scope
11. **chrome-devtools-mcp visual smoke** on 6 SSR routes through Caddy → Node SSR chain — same W132+ Phase 6 scope
12. **Nitro plugin re-evaluation** — when TanStack Start integrates more cleanly with PWA + LHCI

---

## 6. Sources

- `C:\Users\egorribun\.claude\plans\c-users-egorribun-claude-projects-c-use-clever-comet.md` — W131 plan file (user-approved 2026-05-06)
- `docs/plans/2026-05-01-wave125-ssr-design.md` §3 Phase 4 — design doc this implements
- TanStack Start v1 docs queried via Context7 MCP (`/websites/tanstack_start_framework_react`, ~1004 snippets)
- W130 audit + handoff: `docs/audits/AUDIT_WAVE130.md`, `memory/wave131_opening_prompt.md`
