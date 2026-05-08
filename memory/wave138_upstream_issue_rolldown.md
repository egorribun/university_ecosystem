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

Reference implementation: `frontend/scripts/build-orchestrated.mjs` in our repo (MIT, link on request).

### Environment

- OS: Windows 11 IoT Enterprise 10.0.26200 + Docker Desktop with WSL2 backend
- Node: 24.x (linux-amd64 alpine in container, but issue reproduces on host Win Node 22+ too)
- Vite: 8.0.6+
- Rolldown: latest as bundled with Vite 8.x
- Reproduces identically on Linux CI containers (i.e., it's NOT a Windows-only issue, but discovered on Windows)

### Trace data

Available on request — `process._getActiveHandles()` JSON dumps + post-prerender event-loop state.

### Why I think it's rolldown's worker pool

Diagnostic process narrowed candidates to:
- Rolldown native worker pool (most likely — MessagePort + Pipe pattern matches Worker_threads IPC)
- @rolldown/plugin-babel (less likely — babel doesn't typically spawn workers in this config)
- vite-plugin-pwa workbox-build (separate hang on injectManifest, but different signature — that one is filesystem glob, not worker IPC)

If you can confirm by adding explicit `worker.terminate()` in rolldown's cleanup hook, would resolve.
