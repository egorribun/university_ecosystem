---
name: Wave 137 SW7 — upstream issue templates
description: 3 upstream issue stubs for the user to file via `gh issue create` post-W137 wave-close. Closes W136 §Honesty #4 (build-orchestrated upstream hang) at issue-filing level + chrome-devtools Windows wall + tempo/loki distroless healthcheck.
type: reference
originSessionId: f44b4354-9b90-488e-8d34-32a19da959a3
---
# Wave 137 SW7 — upstream issue templates

User files these 3 issues via `gh issue create --repo OWNER/REPO --title "..." --body-file <file>` (or copy-paste to GitHub web UI) post-W137 wave-close. The issue text below is ready for direct submission with minor adjustments to title formatting per upstream conventions.

---

## Issue 1 — vitejs/rolldown OR rolldown/rolldown

**Title**: Build hangs post-prerender on Windows: dangling MessagePort + Worker thread

**Recommended repo**: `rolldown/rolldown` (likely the right home — the worker thread is from rolldown's native worker pool, not vite-plugin-pwa or @rolldown/plugin-babel as initially hypothesized in W136 SW5 trace data analysis).

**Labels**: `bug`, `windows`, `worker`, `build-hang`

**Issue body**:

```
### Summary

After `vite build` (with `@tanstack/react-start` + `@vitejs/plugin-react` + `vite-plugin-pwa` + `@rolldown/plugin-babel`) successfully emits all artifacts (client bundle, prerendered HTML shell, server entry, sw.js), the Node process does NOT exit cleanly on Windows. Active handle dump after artifact emission shows:

- 1 × `MessagePort`
- 1 × `Pipe` (IPC)
- 2 × `Socket`
- 0 × active requests

The `MessagePort` is the smoking gun — a Worker thread spawned by rolldown's native worker pool (or possibly @rolldown/plugin-babel) is not being terminated after the main bundle work completes. The event loop stays alive indefinitely.

### Reproduction

1. Use this minimal repro project structure (will provide repo if requested):
   - vite 8.0.6+
   - @vitejs/plugin-react 6.x (Oxc)
   - @rolldown/plugin-babel 0.2.x (React Compiler)
   - @tanstack/react-start 1.167.x with `spa: { enabled: true }` mode
   - vite-plugin-pwa 1.3.x with `injectManifest` strategy

2. Run `WAVE136_HANG_TRACE=1 npm run build` (or equivalent — instrumentation sets `NODE_OPTIONS=--require ./scripts/wave136-hang-trace-agent.cjs` to dump `process._getActiveHandles()` + `_getActiveRequests()` after artifact emission detected).

3. Observe build process hangs after `[prerender] Prerendered N pages` log line. Trace agent reports MessagePort + Pipe + Socket × 2 still active.

### Workaround

Spawn `vite build` as a child process, poll for artifact emission (`dist/server/server.js` exists + recent mtime), then `kill -9` the child. Tradeoff: must be done OUTSIDE the build process; can't be a graceful exit hook.

Reference implementation: `frontend/scripts/build-orchestrated.mjs` in our repo (https://github.com/EXAMPLE/repo, MIT).

### Environment

- OS: Windows 11 IoT Enterprise 10.0.26200 + Docker Desktop with WSL2 backend
- Node: 24.x (linux-amd64 alpine in container, but issue reproduces on host Win Node 22+ too)
- Vite: 8.0.6+
- Rolldown: latest as bundled with Vite 8.x
- Reproduces identically on Linux CI containers (i.e., it's NOT a Windows-only issue, but discovered on Windows)

### Trace data

Available on request — `process._getActiveHandles()` JSON dumps + post-prerender event-loop state.

### Why I think it's rolldown's worker pool

W136 SW5's diagnostic process narrowed candidates to:
- Rolldown native worker pool (most likely — MessagePort + Pipe pattern matches Worker_threads IPC)
- @rolldown/plugin-babel (less likely — babel doesn't typically spawn workers in this config)
- vite-plugin-pwa workbox-build (separate hang on injectManifest, but different signature — that one is filesystem glob, not worker IPC)

If you can confirm by adding explicit `worker.terminate()` in rolldown's cleanup hook, would resolve.
```

---

## Issue 2 — chromedevtools/chrome-devtools-mcp

**Title**: `Accessibility.getFullAXTree` + `Runtime.evaluate` timeout family on Windows + headless Chrome

**Recommended repo**: `chromedevtools/chrome-devtools-mcp`

**Labels**: `bug`, `windows`, `headless`, `cdp`, `timeout`

**Issue body**:

```
### Summary

When using chrome-devtools-mcp on Windows with headless Chrome to inspect heavy-DOM authenticated routes, the `Accessibility.getFullAXTree` and `Runtime.evaluate` CDP commands time out within their default windows (often 30-60s).

The timeout reproduces specifically:
- Windows host (not WSL)
- Headless mode
- Heavy DOM (e.g., > 500 elements, complex Framer Motion + glass shadow CSS, ParticleAuthBackground 1000-particle canvas)
- AXTree traversal OR JS evaluation

It does NOT reproduce on:
- Linux host (same routes work fine)
- macOS (same routes work fine)
- Windows + non-headless real Chrome (chromium playwright `channel: 'chrome'` works)

### Reproduction

1. Project structure (full repo on request):
   - React 19 + Framer Motion `domAnimation` LazyMotion config
   - 8 SSR routes (TanStack Start v1)
   - JWT auth with HttpOnly cookie + JWKS endpoint

2. Open chrome-devtools-mcp, navigate to authed dashboard route.

3. Try `take_snapshot()` (calls `Accessibility.getFullAXTree`) → timeout after default window.

4. Try `evaluate_script("document.body.innerText")` → timeout if DOM is heavy enough.

### Workaround

Use Playwright with `channel: 'chrome'` (real Chrome via WebSocket protocol layer, NOT chrome-devtools-mcp's CDP backchannel):

```js
const browser = await chromium.launch({ channel: 'chrome', headless: true })
```

Bypasses the CDP wall entirely. Documented in our repo at `frontend/scripts/playwright-visual-smoke.mjs` (W136 SW3) and `frontend/scripts/wave137-authed-smoke.mjs` (W137 SW4).

### Environment

- OS: Windows 11 IoT Enterprise 10.0.26200
- Chrome: latest stable (139.x at time of writing)
- chrome-devtools-mcp: latest as of 2026-05-08

### Why this is hard

The CDP backchannel that chrome-devtools-mcp uses internally has different protocol semantics than the direct WebSocket DevTools connection Playwright opens. Some commands serialize through a proxy layer that adds round-trips → timeouts compound.

A "fix" would likely require chrome-devtools-mcp to either:
1. Expose a "raw CDP" mode that bypasses the proxy
2. Increase default timeouts for AXTree + Runtime.evaluate (they're often defaulted at 30s but heavy DOM needs 90s+)
3. Document the Windows + headless limitation and recommend Playwright as alternative
```

---

## Issue 3 — grafana/tempo + grafana/loki distroless healthcheck

**Title**: Add CLI subcommand for `--check-ready` to support distroless healthcheck

**Recommended repo**: file at BOTH `grafana/tempo` AND `grafana/loki` (separate but identical-content issues).

**Labels**: `feature-request`, `distroless`, `docker`, `healthcheck`

**Issue body**:

```
### Summary

The official `grafana/tempo:2.x` (and `grafana/loki:3.x`) Docker images use distroless bases that lack any HTTP client (`wget`, `curl`, `nc`, `bash`, `/dev/tcp` shell builtin). This means `docker-compose.yml` `healthcheck` blocks cannot probe the existing `/ready` HTTP endpoint without either:

1. **Custom Dockerfile**: `FROM grafana/tempo:2.x` + `RUN apk add --no-cache curl` (broken — distroless doesn't have apk; needs `FROM ... AS source` + multi-stage `COPY --from=alpine`).
2. **Sidecar pattern**: separate `curlimages/curl:latest` container with `network_mode: service:tempo`. Works but adds container, breaks `depends_on: condition: service_healthy` semantics for downstream consumers (sidecar healthiness ≠ tempo container healthiness in `docker compose ps`).
3. **gRPC health probe**: `grpc_health_probe` binary (used by the spicedb image and similar) requires gRPC health protocol registered in the binary; tempo + loki don't expose gRPC health endpoints AFAICT.

### Feature request

Add a CLI subcommand to the `tempo` (and `loki`) binary that checks readiness without needing an HTTP client:

```sh
tempo --check-ready  # exits 0 if ready, non-zero otherwise
```

Or a similar subcommand. This would let docker-compose users write:

```yaml
healthcheck:
  test: ["CMD", "tempo", "--check-ready"]
  interval: 10s
  timeout: 5s
  retries: 3
  start_period: 20s
```

Same pattern as `imgproxy health` (which we use successfully — imgproxy distroless image has CLI built in).

### Reproduction (current pain point)

In our `docker-compose.full.yml`:

```yaml
tempo:
  image: grafana/tempo:2.10.3
  command: ["-config.file=/etc/tempo/tempo.yaml"]
  # NO healthcheck possible without sidecar
  # ...

# Sidecar workaround (W137 SW6):
tempo-healthprobe:
  image: curlimages/curl:8.10.1
  network_mode: "service:tempo"
  depends_on: [tempo]
  command: ["sleep", "infinity"]
  healthcheck:
    test: ["CMD", "curl", "-fsS", "http://localhost:3200/ready"]
    interval: 10s
    # ...
```

This works but doesn't make `docker compose ps tempo` show `(healthy)` — only the sidecar shows that. So we can't use `depends_on: condition: service_healthy` for downstream services that depend on tempo.

### Suggested implementation

A `--check-ready` subcommand that just calls the existing `/ready` HTTP handler internally (no separate process or HTTP client needed since binary already implements the handler logic). Exit 0 if `/ready` would respond 200, non-zero otherwise.

### Use case

- Local dev via docker-compose (most common)
- Kubernetes runs alpine sidecars or uses `httpGet` probe (different API), so this is less critical there
- CI pipelines that bring up tempo + loki for integration tests
```

---

## Filing instructions for user

After Wave 137 wave-close, run from `C:\Users\egorribun\Documents\university_ecosystem`:

```bash
# Issue 1 (rolldown):
gh issue create \
  --repo rolldown/rolldown \
  --title "Build hangs post-prerender on Windows: dangling MessagePort + Worker thread" \
  --body-file memory/wave137_upstream_issues_rolldown.md

# Issue 2 (chrome-devtools-mcp):
gh issue create \
  --repo chromedevtools/chrome-devtools-mcp \
  --title "Accessibility.getFullAXTree + Runtime.evaluate timeout on Windows headless heavy DOM" \
  --body-file memory/wave137_upstream_issues_chromedevtools.md

# Issue 3 — file at BOTH repos:
gh issue create \
  --repo grafana/tempo \
  --title "Add CLI subcommand for --check-ready to support distroless healthcheck" \
  --body-file memory/wave137_upstream_issues_tempo_loki.md

gh issue create \
  --repo grafana/loki \
  --title "Add CLI subcommand for --check-ready to support distroless healthcheck" \
  --body-file memory/wave137_upstream_issues_tempo_loki.md
```

The `--body-file` requires extracting each issue body to a separate `.md` file. The user can either:
- Extract bodies manually from this template
- Copy-paste from this file directly into GitHub web UI's issue body field

---

## End of W137 SW7 upstream issue templates
