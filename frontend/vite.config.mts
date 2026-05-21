import { mkdirSync, readFileSync, writeFileSync } from "node:fs"
import { resolve } from "node:path"
import { fileURLToPath } from "node:url"
import { defineConfig, loadEnv, type PluginOption } from "vite"
import react from "@vitejs/plugin-react"
import babel from "@rolldown/plugin-babel"
import wasm from "vite-plugin-wasm"
import { VitePWA } from "vite-plugin-pwa"
// Wave 125 Phase 1+2 — replaced @tanstack/router-vite-plugin with
// @tanstack/react-start/plugin/vite. tanstackStart() includes the file-based
// router codegen functionality (via `router.routesDirectory`) that
// TanStackRouterVite() previously provided, plus SPA-mode shell prerender,
// custom client/server entry binding, and future SSR/RSC infrastructure.
//
// Plugin order constraint per Context7 docs (build-from-scratch.md):
// "react's vite plugin must come after start's vite plugin" — see plugins
// array below where tanstackStart() stays at index 0 and react() is at
// index 3 (after wasm + withGeneratedManifests, both order-neutral).
import { tanstackStart } from "@tanstack/react-start/plugin/vite"
// Wave 131 Phase 4 — Nitro plugin (`nitro/vite`) was evaluated as the canonical
// TanStack Start production deploy path. SW1 execution found that adopting
// `nitro()` restructures Vite output from `dist/client/` → `.output/public/` and
// `dist/server/server.js` → `.output/server/index.mjs`. That cascade breaks
// vite-plugin-pwa's `injectManifest` glob (asset list goes empty because PWA
// runs before Nitro restructures), plus orphans the LHCI `staticDistDir`,
// wave127-build-x3.sh detection, and frontend.Dockerfile COPY paths.
//
// We chose the documented fallback: a thin Node wrapper at
// `scripts/server-prod.mjs` (~50 lines) that imports the existing
// `dist/server/server.js` handler emitted by tanstackStart's spa-mode build
// and binds it to a Node `http.createServer` listening on `process.env.PORT`.
// Custom wrapper bypasses Nitro entirely while still delivering per-request
// Node SSR runtime to production. All pre-W131 build pipeline paths are
// preserved (post-build-shell.mjs, wave127-build-x3.sh, PWA manifest,
// LHCI staticDistDir, frontend.Dockerfile COPY).
//
// `nitro` package stays in package.json for forward-compat (when Nitro
// integrates more cleanly with PWA + LHCI in a future TanStack Start version,
// this comment can be revisited and the plugin re-introduced).
import { visualizer } from "rollup-plugin-visualizer"
import { MASKABLE_ICON_BASE64 } from "./pwa-maskable-icons"
import { generateManifests } from "./scripts/generate-manifests.mjs"
// W136 SW6: shared Workbox config — eliminates drift between vite.config.mts
// (full pipeline via vite-plugin-pwa) and scripts/build-orchestrated.mjs
// (Windows local standalone workbox-build per W135 SW3 strategy).
import { PWA_INJECT_CONFIG } from "./scripts/workbox-config.mjs"

const srcDir = fileURLToPath(new URL("./src", import.meta.url))
const publicDir = fileURLToPath(new URL("./public", import.meta.url))
// W156 SW1 Tier 1 #1 — direct file path to react-dom dev bundle. Package's
// `exports` field at react-dom/package.json:48-112 does NOT expose `./cjs/*`
// subpaths under any condition, so a package-style alias
// (`"react-dom/client": "react-dom/cjs/react-dom-client.development.js"`)
// gets blocked by rolldown:vite-resolve with "is not exported under the
// conditions" error. Resolving via absolute file path bypasses the exports
// field gate — Vite's resolve.alias accepts both package specifiers and
// absolute paths; the absolute-path branch skips package.json exports check.
const reactDomDevClient = fileURLToPath(
  new URL("./node_modules/react-dom/cjs/react-dom-client.development.js", import.meta.url)
)
const manifestSourcePath = resolve(publicDir, "manifest.source.json")

const ensureMaskableIcons = () => {
  for (const [filename, base64] of Object.entries(MASKABLE_ICON_BASE64)) {
    const destination = resolve(publicDir, filename)
    const expected = Buffer.from(base64.replace(/\s+/g, ""), "base64")
    let writeFile = true
    try {
      const current = readFileSync(destination)
      if (current.equals(expected)) writeFile = false
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error
    }
    if (writeFile) {
      mkdirSync(publicDir, { recursive: true })
      writeFileSync(destination, expected)
    }
  }
}
ensureMaskableIcons()
generateManifests({ publicDir, sourcePath: manifestSourcePath })

const ensureAppReleaseEnv = () => {
  if (process.env.VITE_APP_RELEASE) return

  const fallbackKeys = [
    "SERVICE_VERSION",
    "SOURCE_VERSION",
    "APP_VERSION",
    "HEROKU_SLUG_COMMIT",
    "RENDER_GIT_COMMIT",
    "VERCEL_GIT_COMMIT",
    "GITHUB_SHA",
    "COMMIT_SHA",
  ] as const

  for (const key of fallbackKeys) {
    const candidate = process.env[key]
    if (candidate) {
      process.env.VITE_APP_RELEASE = candidate
      return
    }
  }
}

ensureAppReleaseEnv()

const withGeneratedManifests = (): PluginOption => ({
  name: "generate-localized-manifests",
  apply: () => true,
  buildStart() {
    generateManifests({ publicDir, sourcePath: manifestSourcePath })
  },
  hotUpdate(ctx) {
    if (ctx.file === manifestSourcePath) {
      generateManifests({ publicDir, sourcePath: manifestSourcePath })
      this.environment.hot.send({ type: "full-reload" })
    }
  },
})

const loadManifest = () => {
  const manifestPath = resolve(publicDir, "manifest.webmanifest")
  try {
    const raw = readFileSync(manifestPath, "utf-8")
    return JSON.parse(raw)
  } catch {
    return undefined
  }
}

const CSP_NONCE_PLACEHOLDER = "__CSP_NONCE__"
// Wave 125 Phase 2 — `transformIndexHtml` does NOT fire on TanStack Start's
// React-SSR-rendered `_shell.html` (the shell goes through React's renderer,
// not Vite's index.html pipeline). The CSP nonce + font preload injectors
// below are therefore EFFECTIVELY DEAD CODE in Phase 2 builds — they would
// only fire if Vite emitted a `dist/index.html`, which it no longer does
// once `tanstackStart()` is in the plugin chain.
//
// The equivalent functionality has migrated to
// `frontend/scripts/post-build-shell.mjs`, which runs after `vite build`
// (spawned by `run-build.mjs`) and operates on `dist/client/_shell.html`.
// Both plugins are kept here as harmless no-ops for two reasons:
//   1. Defensive — if a future tanstackStart version emits a Vite-compatible
//      `index.html` again, these plugins would resume working without
//      requiring a re-write of run-build.mjs.
//   2. Clear migration audit trail — the plugins are a touchstone showing
//      where the W124 SW2 (font preload) + DEBT-05 (CSP nonce) original
//      implementations lived; new contributors finding them via grep can
//      see the comment block + post-build-shell.mjs handover note.
const withStrictCspNonce = (): PluginOption => ({
  name: "strict-csp-nonce",
  enforce: "post",
  transformIndexHtml(html) {
    // PERF-W16-02: Added dotAll (s) flag to handle multiline script attributes.
    return html.replace(/<script\b(?![^>]*\bnonce=)[^>]*>/gis, (tag) => {
      const insertion = tag.indexOf("<script") + "<script".length
      const before = tag.slice(0, insertion)
      const after = tag.slice(insertion)
      return `${before} nonce="${CSP_NONCE_PLACEHOLDER}"${after}`
    })
  },
})

// Wave 124 SW2 — critical font preload injector.
//
// Inter + Outfit ship via fontsource as side-effect CSS imports in
// src/main.tsx. Their @font-face rules reference woff2 files which
// the browser only discovers AFTER CSS parse + text-render rule match.
// Audit of dist/index.html confirmed 0 font preload links → ~50-150 ms
// FOIT on cold cache.
//
// This plugin scans the build bundle for the two LCP-relevant variants
// and injects `<link rel="preload" as="font" type="font/woff2" crossorigin>`
// into dist/index.html. Hashes change per build, so we match by stable
// filename pattern and read the actual hashed name from the bundle.
//
// - inter-cyrillic-wght-normal-*.woff2 (~19 KB) — RU body text
// - outfit-latin-wght-normal-*.woff2 (~32 KB) — display headings
//
// Extended variants (cyrillic-ext, latin-ext) intentionally stay lazy —
// rare characters, not above-the-fold. EN-only inter-latin also stays
// lazy: browser still discovers it via @font-face matching when needed.
//
// Honest deferral: per-route image preload via TanStack Router head: API
// requires a route loader refactor that disrupts useQuery cache semantics
// (~2-3 h, beyond SW2's 1 h budget). Naturally addressed by SSR (W125+).
const FONT_PRELOAD_PATTERN =
  /^assets\/(inter-cyrillic-wght-normal-|outfit-latin-wght-normal-)[^/]*\.woff2$/
const FONT_PRELOAD_ANCHOR = /(\n\s*<!--\n\s*Wave 117 SW5)/
const withFontPreload = (): PluginOption => ({
  name: "critical-font-preload",
  enforce: "post",
  apply: "build",
  transformIndexHtml: {
    order: "post",
    handler(html, ctx) {
      if (!ctx.bundle) return html
      const criticalFonts: string[] = []
      for (const fileName of Object.keys(ctx.bundle)) {
        if (FONT_PRELOAD_PATTERN.test(fileName)) {
          criticalFonts.push(fileName)
        }
      }
      if (criticalFonts.length === 0) return html
      criticalFonts.sort()
      const preloadLinks = criticalFonts
        .map(
          (font) =>
            `  <link rel="preload" as="font" type="font/woff2" crossorigin href="/${font}" />`
        )
        .join("\n")
      return html.replace(FONT_PRELOAD_ANCHOR, `\n${preloadLinks}\n$1`)
    },
  },
})

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "")
  // Use null coalescing to properly detect explicitly empty string
  // When VITE_BACKEND_ORIGIN is "", we disable proxy (used during E2E tests)
  // Check both loadEnv result and process.env since Playwright sets via subprocess env
  const rawBackendOrigin = env.VITE_BACKEND_ORIGIN ?? process.env.VITE_BACKEND_ORIGIN
  const backendOrigin = rawBackendOrigin ?? "http://127.0.0.1:8000"
  const target = backendOrigin ? backendOrigin.replace(/\/$/, "") : ""
  const disableProxy = backendOrigin === ""
  const buildReport = process.env.BUILD_REPORT === "1"
  const analyze = mode === "analyze" || process.env.ANALYZE === "1" || buildReport
  // W153 SW1 — opt-in flag to disable minify + emit linked source maps while
  // KEEPING mode=production (so JSX transform stays at production runtime
  // and SSR works correctly). Set via dev compose build arg only; CI / prod
  // omit it. See `build.minify` + `build.sourcemap` blocks below for usage.
  const isUnminified =
    env.FRONTEND_BUILD_UNMINIFIED === "true" || process.env.FRONTEND_BUILD_UNMINIFIED === "true"
  // W156 SW1 Tier 1 #1 — opt-in development React for /login wedge diagnosis.
  //
  // Mirrors W153 SW1 FRONTEND_BUILD_UNMINIFIED pattern. When set,
  // vite.config.mts adds resolve.alias mapping `react-dom/client` to the
  // development cjs bundle directly + an environments.client.define for
  // `process.env.NODE_ENV = "development"` so the dev bundle's internal
  // IIFE gate at `cjs/react-dom-client.development.js:15`
  // (`"production" !== process.env.NODE_ENV && (function () { ... })()`)
  // evaluates true and the React module loads.
  //
  // Server bundle is UNAFFECTED: server.ts imports
  // @tanstack/react-start/server-entry → handler.fetch uses react-dom/server
  // (NOT aliased), tanstackStart keeps top-level process.env.NODE_ENV at
  // "production" for server environment, so react-dom-server.node.production.js
  // loads as today → no jsxDEV trap (W152 SW1 regression history).
  //
  // Set ONLY in dev compose (docker-compose.full.yml) via Docker build ARG.
  // CI / prod builds omit the flag → byte-identical to current production
  // bundle. Tree-shake-safe at build time (flag read in Node at config-load,
  // never ships to client bundle).
  const isReactDevMode =
    env.FRONTEND_REACT_DEV_MODE === "true" || process.env.FRONTEND_REACT_DEV_MODE === "true"
  const manifest = loadManifest()

  const mk = (rewrite = false) => ({
    target,
    changeOrigin: true,
    secure: false,
    ws: true,
    ...(rewrite ? { rewrite: (p: string) => p.replace(/^\/api/, "") } : {}),
  })

  // API v1 routes are proxied directly (no rewrite needed)
  // Backend now serves all endpoints under /api/v1
  // When disableProxy is true (E2E tests), don't configure proxy - Playwright handles mocking
  const proxy = disableProxy
    ? undefined
    : {
        "/api/v1": mk(false), // New versioned API - no rewrite
        "/api": mk(false), // Legacy endpoints (healthz, static, etc.)
        "/auth": mk(),
        "/static/": mk(),
        "/media/": mk(),
        "/spotify": mk(),
        "/notifications": mk(),
        "/push": mk(),
        "/ws": { ...mk(), ws: true }, // WebSocket support for future
      }

  const plugins: PluginOption[] = [
    // Wave 125 Phase 1+2 — TanStack Start v1 plugin in SPA mode.
    // Replaces the prior TanStackRouterVite() plugin call (file-based
    // router codegen is now bundled into tanstackStart). Routes still
    // live in src/routes/ and routeTree.gen.ts is regenerated at the
    // same path (defaults: src is srcDirectory, routes is
    // router.routesDirectory).
    //
    // Wave 125 Phase 2 — SPA mode (`spa: { enabled: true }`) generates
    // a static `_shell.html` at build time via React SSR through the
    // root route's `shellComponent`. The shell HTML is then served as
    // the SPA fallback for all client-side routes.
    //
    // The combination that makes this work:
    //   1. `__root.tsx` defines `shellComponent: RootShell` — a
    //      minimal HTML scaffold that renders `<html>…<body><div
    //      id="root">{children}</div><Scripts /></body></html>` with
    //      no provider dependencies (only `<HeadContent />` from the
    //      route's `head:()` registration).
    //   2. `defaultSsr: false` on the router (see `src/router.ts`) —
    //      route `component`s do NOT render server-side; only the
    //      shell does. `beforeLoad` guards still run, but they see a
    //      stub auth context that lets them redirect cleanly without
    //      crashing on `undefined.loading`.
    //   3. Stub router context — see `SSR_STUB_AUTH` /
    //      `SSR_STUB_QUERY_CLIENT` in `src/router.ts`. App.tsx's
    //      `<RouterProvider context={...}>` overrides these with the
    //      live `useAuth()` values once the client mounts.
    //
    // Server + client entries both point at our existing files:
    //   - `server.ts` (NEW) — minimal `createServerEntry` wrapper,
    //     used by tanstackStart's prerender + preview-server +
    //     dev-server middleware.
    //   - `main.tsx` (preserved from pre-W125 SPA setup) — uses
    //     `createRoot().render(<App />)`, the App tree drives the
    //     router via `<RouterProvider context={...} />` with real
    //     auth state. Phase 3 (W126+) may switch to `<StartClient />`
    //     + `hydrateRoot` + auth-at-edge.
    //
    // `router.quoteStyle: "double"` preserves the project formatting
    // convention for the auto-generated `routeTree.gen.ts`.
    tanstackStart({
      spa: { enabled: true },
      // Wave 178 SW1 — `routeFileIgnorePattern: "__tests__"` so
      // `src/routes/__tests__/*.test.tsx` (W178 added the first one,
      // _public.test.tsx) doesn't trigger the TanStack Router generator's
      // "does not export a Route" warning on every build. Tests live
      // co-located with routes for clarity; the prefix-with-"-" workaround
      // (default `routeFileIgnorePrefix: "-"`) would clash with vitest's
      // `*.test.tsx` glob. The pattern is a REGEX (NOT a glob — empirically
      // verified W178 SW1 build attempt: "**/__tests__/**" → `new RegExp`
      // throws "Nothing to repeat" because `**` isn't valid regex). A bare
      // path substring matches paths containing `/__tests__/`.
      // Wave 179 SW8 — extend pattern to also ignore `guards.ts` pure-function
      // module at src/routes/guards.ts (W174 §Honesty #4-routeGuards closure).
      // Like __tests__/, this file doesn't export a Route — it's the extracted
      // beforeLoad helpers for _auth.tsx / _public.tsx / _admin.tsx. Pattern
      // is REGEX (per W178 SW1 (z) #1) — alternation matches either folder
      // segment "__tests__" OR file basename "guards".
      router: { quoteStyle: "double", routeFileIgnorePattern: "__tests__|guards" },
      client: { entry: "main.tsx" },
      server: { entry: "server.ts" },
    }),
    wasm(),
    withGeneratedManifests(),
    react(),
    // MOD-W5-08: React Compiler via @rolldown/plugin-babel (plugin-react v6 uses Oxc,
    // no longer bundles Babel). Stable mode — compiler validates React rules and
    // auto-memoizes; build fails on rule violations rather than silently skipping.
    babel({
      plugins: [
        [
          "babel-plugin-react-compiler",
          {
            compilationMode: "infer",
            panicThreshold: "CRITICAL_ERRORS",
          },
        ],
      ],
    }),
    VitePWA({
      // Wave 135 SW3 — `BUILD_SKIP_PWA=true` env flag (set by
      // `frontend/scripts/build-orchestrated.mjs` only) disables the
      // vite-plugin-pwa lifecycle without removing the plugin from the
      // chain. tanstackStart's prerender + server-build steps depend on
      // the plugin chain shape, so dropping the plugin object entirely
      // skips `_shell.html` + `dist/server/server.js` emission. With
      // `disable: true` the plugin is a no-op (skips `transformIndexHtml`
      // injection AND the hanging `closeBundle._generateSW(ctx)` call),
      // letting build-orchestrated.mjs do the SW compile + manifest
      // injection itself in steps 4 + 5. Closes W126 polish #3
      // (vite-plugin-pwa Windows hang) without disturbing dev mode or
      // CI Linux builds (where `BUILD_SKIP_PWA` is unset and the plugin
      // runs normally).
      disable: process.env.BUILD_SKIP_PWA === "true",
      registerType: "autoUpdate",
      injectRegister: "script",
      strategies: "injectManifest",
      srcDir: "src",
      filename: "sw.ts",
      includeAssets: [],
      workbox: {
        clientsClaim: true,
        skipWaiting: true,
        runtimeCaching: [
          {
            urlPattern: ({ request }) => request.mode === "navigate",
            handler: "NetworkFirst",
            options: {
              cacheName: "app-shell",
              networkTimeoutSeconds: 5,
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          {
            urlPattern: ({ url, request }) =>
              request.method === "GET" && /\/api\/(news|schedule|events)/.test(url.pathname),
            handler: "StaleWhileRevalidate",
            options: {
              cacheName: "api-cache",
              // MOD-07 (audit 2026-03-06): 304 must NOT be cached by Workbox.
              // Workbox stores an empty body for 304, returning blank content on cache-first hit.
              cacheableResponse: { statuses: [0, 200] },
              expiration: { maxEntries: 100, maxAgeSeconds: 60 * 60 },
            },
          },
          {
            urlPattern: ({ url }) => url.pathname.endsWith("/offline.html"),
            handler: "CacheFirst",
            options: {
              cacheName: "offline-fallback",
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          {
            urlPattern: ({ url }) =>
              url.pathname.startsWith("/static/") || url.pathname.startsWith("/media/"),
            handler: "NetworkFirst",
            options: {
              cacheName: "backend-static",
              expiration: { maxEntries: 200, maxAgeSeconds: 24 * 60 * 60 },
            },
          },
        ],
      },
      ...(manifest ? { manifest } : {}),
      // W136 SW6: injectManifest config imported from
      // ./scripts/workbox-config.mjs — single source of truth shared with
      // build-orchestrated.mjs to prevent drift (closes W135 §Honesty #5).
      // See workbox-config.mjs for rationale on glob ignores + size cap.
      injectManifest: PWA_INJECT_CONFIG,
      devOptions: {
        enabled:
          process.env.VITE_PWA_DEV === "true" ||
          process.env.NODE_ENV === "test" ||
          process.env.VITEST === "true",
        type: "module",
      },
    }),
    // DEBT-05 (audit 2026-03-06): CSP nonce always applied. Disabling enforcement
    // in LHCI mode creates a precedent for bypassing security headers in any mode.
    // If LHCI tests fail: use --chrome-flags='--disable-web-security' in lhci config.
    withStrictCspNonce(),
    // Wave 124 SW2 — inject <link rel="preload" as="font"> for critical font
    // subset (RU cyrillic body + Outfit latin display) into dist/index.html.
    // Build-time only (apply: "build"), no-op in dev. See plugin definition
    // above for design rationale + honest deferrals.
    withFontPreload(),
  ]

  if (analyze) {
    plugins.push(
      visualizer({
        filename: "dist/bundle-stats.html",
        template: "treemap",
        gzipSize: true,
        brotliSize: true,
        open: false,
      })
    )
    plugins.push(
      visualizer({
        filename: "dist/bundle-stats.json",
        template: "sunburst",
        json: true,
        gzipSize: true,
        brotliSize: true,
      })
    )
  }

  return {
    base: "/",
    plugins,
    resolve: {
      alias: {
        "@": srcDir,
        // W156 SW1 Tier 1 #1 — alias react-dom/client → development cjs
        // bundle when FRONTEND_REACT_DEV_MODE=true. Bypasses the client.js
        // module-eval gate (line 31 `if (process.env.NODE_ENV === 'production')`).
        // main.tsx is the SOLE consumer of react-dom/client; server.ts uses
        // react-dom/server (NOT aliased). The alias destination is the absolute
        // file path resolved at config-load time (`reactDomDevClient` constant
        // above) because react-dom's `exports` field at package.json blocks
        // `./cjs/*` subpaths under all conditions — package-specifier aliases
        // fail with "is not exported under the conditions" via rolldown:vite-
        // resolve. Absolute file paths skip the exports field gate.
        // See isReactDevMode comment block above for full rationale.
        ...(isReactDevMode
          ? {
              "react-dom/client": reactDomDevClient,
            }
          : {}),
      },
    },
    server: {
      host: true,
      cors: true,
      headers: { "Service-Worker-Allowed": "/" },
      proxy,
    },
    preview: {
      host: true,
      headers: { "Service-Worker-Allowed": "/" },
      proxy,
    },
    // W156 SW1 Tier 1 #1 — scope NODE_ENV=development to CLIENT environment
    // only. tanstackStart's planning.js writes top-level
    // process.env.NODE_ENV define globally (as "production" by default). Our
    // environments.client override layers on top for client bundle ONLY, so
    // the dev react-dom bundle's internal gate at line 15 evaluates true and
    // the React module loads. Server environment keeps "production" via
    // tanstackStart's top-level define + no override here (avoids W152 SW1
    // jsxDEV trap regression).
    //
    // Verification: post-build, `grep -c "process.env.NODE_ENV"`
    //   dist/client/assets/index-*.js → 0 (replaced with "development" literal)
    //   dist/server/server.js → 0 (replaced with "production" literal)
    // If client check shows raw process.env.NODE_ENV → environments override
    // stomped by tanstackStart; escalate honest defer to W157+ Option D
    // POST-plugin approach per W141 anti-pattern #1.
    environments: isReactDevMode
      ? {
          client: {
            define: {
              "process.env.NODE_ENV": JSON.stringify("development"),
            },
          },
        }
      : undefined,
    optimizeDeps: {
      exclude: ["qrcode"],
    },
    oxc: {
      define:
        mode === "production" ? { "console.log": "(() => {})", "console.debug": "(() => {})" } : {},
    },
    build: {
      // W153 SW1 — opt-in unminified bundle + linked source maps for /login
      // wedge diagnosis. FRONTEND_BUILD_UNMINIFIED=true (dev compose only):
      //   - minify: false
      //   - sourcemap: true (with //# sourceMappingURL= trailer)
      //   - mode STAYS at "production" so JSX transform emits `jsx()` calls
      //     (NOT `jsxDEV()`), keeping SSR runtime compatible with the
      //     production react-dom-server.node.production.js loaded at runtime
      //     (Dockerfile:NODE_ENV=production baked in runtime stage).
      // SW1 fixup history: initial attempt used `--mode development` which
      // broke SSR with `TypeError: jsxDEV is not a function` at RootShell —
      // see post-build-shell.mjs:126 + this comment block. Keeping
      // mode=production trades React DEV warnings for SSR-correctness; the
      // unminified bundle + source maps remain useful for client-side stack
      // trace resolution.
      minify: isUnminified ? false : mode === "production",
      // P0-05 (audit 2026-03-06): "hidden" generates .map files for Sentry
      // symbolication but does NOT add //# sourceMappingURL= to .js bundles,
      // so browsers and attackers cannot download the full TypeScript source.
      sourcemap: isUnminified ? true : mode === "production" ? "hidden" : true,
      chunkSizeWarningLimit: 768,
      // Wave 122 SW2: Vite auto-injects `<link rel="modulepreload">` for every
      // chunk reachable from the entry import graph — including chunks loaded
      // only via dynamic `await import()` at user click. PDF-export libs
      // (jspdf, html2canvas, dompurify) are used ONLY by Activity export +
      // Schedule export but were preloaded on every page (LHCI
      // `unused-javascript`: 162 KB / 90.6% wasted on /news, /events, and 5+
      // other routes). resolveDependencies filters them out of the HTML
      // preload list. The chunks still exist in dist/assets/ — `await
      // import()` resolves them on demand. Defense-in-depth alongside the
      // PWA `globIgnores` (see below) which keeps them out of SW precache.
      modulePreload: {
        polyfill: false,
        resolveDependencies(_filename, deps, { hostType }) {
          if (hostType !== "html") return deps
          return deps.filter(
            (dep) =>
              !dep.includes("jspdf") && !dep.includes("html2canvas") && !dep.includes("purify")
          )
        },
      },
      rolldownOptions: {
        onwarn(warning, warn) {
          if (warning.code === "EVAL" && warning.id?.includes("@protobufjs/inquire")) return
          warn(warning)
        },
        output: {
          // Vite 8: object-form manualChunks removed — use function form
          manualChunks(id: string) {
            // Wave 115 SW5 — `react-router-dom` removed from manualChunks
            // alongside `npm uninstall react-router-dom`. TanStack Router
            // gets its own chunking (see below).
            if (id.includes("node_modules/react-dom") || id.includes("node_modules/react/"))
              return "vendor-react"
            if (
              id.includes("node_modules/framer-motion") ||
              id.includes("node_modules/lucide-react")
            )
              return "vendor-ui"
            if (id.includes("node_modules/@tanstack/react-query")) return "vendor-query"
            // PERF-05: Sentry isolated from i18n — release bump won't re-download i18n.
            if (
              id.includes("node_modules/@sentry/react") ||
              id.includes("node_modules/@sentry/core")
            )
              return "vendor-sentry"
            // Wave 117 SW3 — split @opentelemetry/* into its own async chunk.
            // Previously OTEL's 50+ KB of instrumentation + SDK code lived in
            // the main chunk (verified via Plan-agent grep: 8 @opentelemetry
            // markers in main-232KB minified). Paired with the dynamic-import
            // of `./app/observability` + `./app/telemetry` in `main.tsx`, this
            // moves all OTEL runtime off the critical path to an idle-callback
            // load. Main chunk drops accordingly; prod Sentry init still works
            // because Sentry package is in vendor-sentry (loaded sync).
            if (id.includes("node_modules/@opentelemetry")) return "vendor-otel"
            if (id.includes("node_modules/i18next") || id.includes("node_modules/react-i18next"))
              return "vendor-i18n"
            if (id.includes("node_modules/axios")) return "vendor-http"
            if (id.includes("node_modules/@simplewebauthn/browser")) return "vendor-security"
            // Address large chunks identified in LHCI build warnings
            if (id.includes("node_modules/maplibre-gl")) return "vendor-map"
            // Wave 122 SW2: vendor-pdf manualChunks rule REMOVED. The original
            // grouping (jspdf + html2canvas + dompurify) caused rolldown to
            // emit `vendor-pdf` as a chunk reachable from the entry import
            // graph — even though scheduleExport.ts + activityExport.ts use
            // `await import()`. Some shared util chain pulled the chunk into
            // News + EventCardView + 8 other route bundles statically (LHCI
            // `unused-javascript` 162 KB / 91% wasted on /news + /events).
            // Without the manual rule, rolldown auto-creates per-call dynamic
            // chunks. Activity + Schedule will each get their own jspdf shard
            // (acceptable — duplicated jspdf is ~180 KB but lazy-loaded only
            // when user clicks Export).
            if (id.includes("node_modules/protobufjs")) return "vendor-protobuf"
          },
        },
      },
    },
    test: {
      globals: true,
      environment: "jsdom",
      setupFiles: "./src/test/setup.ts",
      css: true,
      restoreMocks: true,
      include: ["src/**/*.{test,spec}.{ts,tsx}", "src/**/__tests__/**/*.{ts,tsx}"],
      exclude: ["node_modules", "tests", "dist"],
      reporters: ["default", "junit"],
      outputFile: { junit: "vitest-report.xml" },
      snapshotFormat: {
        escapeString: true,
        printBasicPrototype: true,
      },
    },
  }
})
