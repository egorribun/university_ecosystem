// Wave 125 Phase 2 — TanStack Start v1 server entry.
//
// This file is the SSR / build-time prerender handler for our SPA shell.
// `createServerEntry` produces a `{ fetch }` interface that:
//   - During build: tanstackStart's prerender pipeline calls
//     `handler.fetch(new Request("/"))` to generate `dist/client/_shell.html`
//   - During preview / production deploy: tanstackStart's preview-server
//     plugin (and Caddy SSR forwarding rules from Phase 4) routes
//     incoming HTTP requests through this handler, which delegates to
//     `@tanstack/react-start/server-entry`'s default `handler.fetch`
//     (renders the matched route via `renderRouterToStream`).
//
// `defaultSsr: false` is set on the router (see `src/router.ts`),
// meaning route `component`s are NOT executed during SSR — only the
// `shellComponent` from `__root.tsx` runs server-side. This gives us a
// minimal `<html>` scaffold + mount point during SSR, with all
// provider-dependent application code running exclusively on the client
// after hydration. Phase 3 (W126+) may flip per-route SSR back on once
// auth-at-edge and provider hoisting are stable in the SSR context.
import handler, { createServerEntry } from "@tanstack/react-start/server-entry"

export default createServerEntry({
  fetch(request) {
    return handler.fetch(request)
  },
})
