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
import { visualizer } from "rollup-plugin-visualizer"
import { MASKABLE_ICON_BASE64 } from "./pwa-maskable-icons"
import { generateManifests } from "./scripts/generate-manifests.mjs"

const srcDir = fileURLToPath(new URL("./src", import.meta.url))
const publicDir = fileURLToPath(new URL("./public", import.meta.url))
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
      router: { quoteStyle: "double" },
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
      injectManifest: {
        globPatterns: ["**/*.{js,css,html,ico,png,svg,webp,json}"],
        // Wave 122 SW2: exclude PDF export libs from PWA precache. The chunks
        // (jspdf, html2canvas, purify) are used ONLY by Activity export +
        // Schedule export via dynamic `await import()`. Including them in
        // __WB_MANIFEST forced the SW to fetch them on install on every page
        // load — Lighthouse `unused-javascript` counted those bytes as wasted
        // on /news, /events, and 5+ other routes. The dynamic imports still
        // resolve on demand at click; first-export-attempt-while-offline is
        // the only loss (acceptable — users rarely trigger PDF export offline
        // and online round-trip restores capability after first cache).
        globIgnores: [
          "**/bundle-stats.*",
          "**/offline.html",
          "**/jspdf*.js",
          "**/html2canvas*.js",
          "**/purify*.js",
        ],
        // Wave 116 SW-Stretch — Storybook builds route through this same
        // plugin and ship `sb-manager/globals-runtime.js` (3.25 MB) which
        // exceeds Workbox's default 2 MB cache limit, failing
        // `build-storybook`. The prod bundle's largest precache entry is
        // `maplibre-gl-*.js` (~1.03 MB), well under 5 MB. Raising the cap
        // unblocks Chromatic baseline setup without weakening prod caching.
        maximumFileSizeToCacheInBytes: 5_000_000,
      },
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
    optimizeDeps: {
      exclude: ["qrcode"],
    },
    oxc: {
      define:
        mode === "production" ? { "console.log": "(() => {})", "console.debug": "(() => {})" } : {},
    },
    build: {
      minify: true,
      // P0-05 (audit 2026-03-06): "hidden" generates .map files for Sentry
      // symbolication but does NOT add //# sourceMappingURL= to .js bundles,
      // so browsers and attackers cannot download the full TypeScript source.
      sourcemap: mode === "production" ? "hidden" : true,
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
