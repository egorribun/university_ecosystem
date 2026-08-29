import { mkdirSync, readFileSync, writeFileSync } from "node:fs"
import { resolve } from "node:path"
import { fileURLToPath } from "node:url"
import { defineConfig, loadEnv, type PluginOption } from "vite"
import react from "@vitejs/plugin-react"
import babel from "@rolldown/plugin-babel"
import wasm from "vite-plugin-wasm"
import { VitePWA } from "vite-plugin-pwa"
// TanStack Start owns route generation and the client/server entry points.
// Its plugin must remain before React's Vite plugin.
import { tanstackStart } from "@tanstack/react-start/plugin/vite"
import { visualizer } from "rollup-plugin-visualizer"
import { MASKABLE_ICON_BASE64 } from "./pwa-maskable-icons.ts"
import { generateManifests } from "./scripts/generate-manifests.mjs"
import { BUNDLE_BUDGETS } from "./scripts/check-bundle-budget.mjs"
import { mapLibreWorkerAssets } from "./scripts/maplibre-worker-assets.mjs"
// Shared with the Windows-safe standalone build orchestrator.
import { PWA_INJECT_CONFIG } from "./scripts/workbox-config.mjs"

const srcDir = fileURLToPath(new URL("./src", import.meta.url))
const publicDir = fileURLToPath(new URL("./public", import.meta.url))
// Resolve the diagnostic client bundle by absolute path because react-dom does
// not export its cjs internals as package subpaths.
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
// These transforms protect a conventional Vite index. TanStack's generated
// shell receives the same transformations in post-build-shell.mjs.
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
const FONT_PRELOAD_PATTERN =
  /^assets\/(inter-cyrillic-wght-normal-|outfit-latin-wght-normal-)[^/]*\.woff2$/
const FONT_PRELOAD_ANCHOR = /(\n\s*<!--\n\s*External image fallback connection hints)/
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
  // Diagnostic builds stay in production mode so server/client JSX runtimes match.
  const isUnminified =
    env.FRONTEND_BUILD_UNMINIFIED === "true" || process.env.FRONTEND_BUILD_UNMINIFIED === "true"
  // The React diagnostic flag affects only the client bundle. The server must
  // retain production react-dom/server to avoid a jsx/jsxDEV runtime mismatch.
  const isReactDevMode =
    env.FRONTEND_REACT_DEV_MODE === "true" || process.env.FRONTEND_REACT_DEV_MODE === "true"
  const isLhci = env.VITE_LHCI === "true" || process.env.VITE_LHCI === "true"
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
    // SPA mode emits the static fallback shell; server.ts and main.tsx handle
    // request rendering and client hydration/mounting respectively.
    tanstackStart({
      spa: { enabled: true },
      // This option is a regular expression, not a glob. Neither co-located
      // tests nor the shared guard helpers export a Route.
      router: { quoteStyle: "double", routeFileIgnorePattern: "__tests__|guards" },
      client: { entry: "main.tsx" },
      server: { entry: "server.ts" },
    }),
    wasm(),
    withGeneratedManifests(),
    mapLibreWorkerAssets(),
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
      // The Windows-safe orchestrator keeps the plugin in the graph but runs
      // service-worker bundling and manifest injection after Vite exits.
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
      // One source of truth for both the plugin and standalone orchestrator.
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
    // Build-only preloads for the critical RU body and display-font subsets.
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
        // Only main.tsx consumes react-dom/client; server.ts is intentionally unaliased.
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
    // Scope development NODE_ENV to the client diagnostic environment only.
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
      // Unminified diagnostics keep production mode for SSR runtime compatibility.
      minify: isUnminified ? false : mode === "production",
      // P0-05 (audit 2026-03-06): "hidden" generates .map files for Sentry
      // symbolication but does NOT add //# sourceMappingURL= to .js bundles,
      // so browsers and attackers cannot download the full TypeScript source.
      sourcemap: isUnminified ? true : mode === "production" ? "hidden" : true,
      // Vite applies one raw-size threshold to every chunk, including the
      // intentionally lazy language dictionaries. The analyzer separately
      // enforces the stricter 500 KiB main-chunk limit and compressed lazy
      // budgets; this threshold is therefore the largest machine-enforced raw
      // exception, not a relaxation of the initial-load contract.
      chunkSizeWarningLimit: BUNDLE_BUDGETS.passwordDictionaryRawKb,
      // Vite auto-injects `<link rel="modulepreload">` for every
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
          // Vite also emits preload helpers inside JS chunks for dynamic
          // imports. Password-strength locale imports are selected at runtime;
          // preloading their generated dependency graph can otherwise fetch the
          // opposite locale dictionary. The import() target remains untouched
          // and loads the selected analyzer normally.
          if (hostType === "js") {
            return deps.filter((dep) => !dep.includes("vendor-password-strength-"))
          }
          if (hostType !== "html") return deps
          // The LHCI bundle is served through the production SSR wrapper.  Its
          // HTML already contains the route's meaningful content, so eager
          // preloading every shared and feature chunk only competes with the
          // critical stylesheet on the emulated mobile connection (the
          // dashboard response otherwise advertises >1 MiB of JavaScript
          // before first paint).  Keep the application entry discoverable and
          // let its normal ESM imports schedule hydration dependencies after
          // CSS/HTML have painted.  Production builds retain the complete
          // route manifest preload policy.
          if (isLhci) {
            return deps.filter((dep) => /(?:^|[\\/])index-[^/]+\.js$/u.test(dep))
          }
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
            // Password strength is requested only from auth/password forms.
            // Keep the engine, common data and each locale in deterministic
            // independent chunks so opening an English form does not download
            // the Russian dictionary (or vice versa). Workbox intentionally
            // omits these optional chunks from install-time precaching.
            if (id.includes("node_modules/@zxcvbn-ts/core")) return "vendor-password-strength-core"
            if (id.includes("node_modules/@zxcvbn-ts/language-common"))
              return "vendor-password-strength-common"
            if (id.includes("node_modules/@zxcvbn-ts/language-en"))
              return "vendor-password-strength-en"
            if (id.includes("node_modules/@zxcvbn-ts/language-ru"))
              return "vendor-password-strength-ru"
            // React and ReactDOM form the shared framework chunk.
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
            // OTEL loads after the critical path through main.tsx dynamic imports.
            if (id.includes("node_modules/@opentelemetry")) return "vendor-otel"
            if (
              id.includes("node_modules/i18next") ||
              id.includes("node_modules/react-i18next") ||
              id.includes("/src/i18n/locales/") ||
              id.includes("\\src\\i18n\\locales\\")
            )
              return "vendor-i18n"
            if (id.includes("node_modules/axios")) return "vendor-http"
            // Keep the offline database implementation out of the application
            // entry chunk. RxDB pulls Dexie, AJV and its query/storage helpers
            // into a feature-loaded vendor chunk; the application shell opts
            // out of background initialization and offline-capable hooks load
            // it on demand.
            if (id.includes("node_modules/rxdb") || id.includes("node_modules/dexie"))
              return "vendor-rxdb"
            // focus-trap is used by modal components but is imported through a
            // shared hook. Isolate it together with tabbable so those helpers
            // do not inflate the application entry chunk.
            if (id.includes("node_modules/focus-trap") || id.includes("node_modules/tabbable"))
              return "vendor-a11y"
            // TanStack Router core is shared by every route, but it is still a
            // separate cacheable dependency and should not count as app code.
            if (
              id.includes("node_modules/@tanstack/router-core") ||
              id.includes("node_modules/@tanstack/history")
            )
              return "vendor-router"
            // RxDB's validation path and other shared schemas use AJV. Keep
            // the validator and its URI helper together for stable caching.
            if (
              id.includes("node_modules/ajv") ||
              id.includes("node_modules/ajv-formats") ||
              id.includes("node_modules/fast-uri")
            )
              return "vendor-validation"
            // Seroval is required by TanStack Start's client runtime. It is
            // stable framework code and should not be charged to index.js.
            if (id.includes("node_modules/seroval") || id.includes("node_modules/seroval-plugins"))
              return "vendor-start"
            // Address large chunks identified in LHCI build warnings
            if (id.includes("node_modules/maplibre-gl")) return "vendor-map"
            // Leave PDF libraries to Rolldown's dynamic-import chunking; a
            // manual vendor group makes them reachable from the entry graph.
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
