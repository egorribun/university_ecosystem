import { mkdirSync, readFileSync, writeFileSync } from "node:fs"
import { resolve } from "node:path"
import { fileURLToPath } from "node:url"
import { defineConfig, loadEnv, type PluginOption } from "vite"
import react from "@vitejs/plugin-react"
import babel from "@rolldown/plugin-babel"
import wasm from "vite-plugin-wasm"
import { VitePWA } from "vite-plugin-pwa"
import { TanStackRouterVite } from "@tanstack/router-vite-plugin"
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
    TanStackRouterVite({
      routesDirectory: resolve(srcDir, "routes"),
      generatedRouteTree: resolve(srcDir, "routeTree.gen.ts"),
      quoteStyle: "double",
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
        globIgnores: ["**/bundle-stats.*", "**/offline.html"],
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
    modulepreload: { polyfill: false },
    oxc: {
      define:
        mode === "production"
          ? { "console.log": "(() => {})", "console.debug": "(() => {})" }
          : {},
    },
    build: {
      minify: true,
      // P0-05 (audit 2026-03-06): "hidden" generates .map files for Sentry
      // symbolication but does NOT add //# sourceMappingURL= to .js bundles,
      // so browsers and attackers cannot download the full TypeScript source.
      sourcemap: mode === "production" ? "hidden" : true,
      chunkSizeWarningLimit: 768,
      // Vite 8: rollupOptions → rolldownOptions (Rolldown replaces Rollup)
      rolldownOptions: {
        output: {
          // Vite 8: object-form manualChunks removed — use function form
          manualChunks(id: string) {
            // Wave 115 SW5 — `react-router-dom` removed from manualChunks
            // alongside `npm uninstall react-router-dom`. TanStack Router
            // gets its own chunking (see below).
            if (id.includes("node_modules/react-dom") || id.includes("node_modules/react/"))
              return "vendor-react"
            if (id.includes("node_modules/framer-motion") || id.includes("node_modules/lucide-react"))
              return "vendor-ui"
            if (id.includes("node_modules/@tanstack/react-query")) return "vendor-query"
            // PERF-05: Sentry isolated from i18n — release bump won't re-download i18n.
            if (id.includes("node_modules/@sentry/react") || id.includes("node_modules/@sentry/core"))
              return "vendor-sentry"
            if (id.includes("node_modules/i18next") || id.includes("node_modules/react-i18next"))
              return "vendor-i18n"
            if (id.includes("node_modules/axios")) return "vendor-http"
            if (id.includes("node_modules/@simplewebauthn/browser")) return "vendor-security"
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
