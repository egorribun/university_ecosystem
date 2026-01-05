import { mkdirSync, readFileSync, writeFileSync } from "node:fs"
import { resolve } from "node:path"
import { fileURLToPath } from "node:url"
import { defineConfig, loadEnv, PluginOption } from "vite"
import react from "@vitejs/plugin-react"
import { VitePWA } from "vite-plugin-pwa"
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
  handleHotUpdate(ctx) {
    if (ctx.file === manifestSourcePath) {
      generateManifests({ publicDir, sourcePath: manifestSourcePath })
      ctx.server?.ws.send({ type: "full-reload" })
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
    return html.replace(/<script\b(?![^>]*\bnonce=)[^>]*>/gi, (tag) => {
      const insertion = tag.indexOf("<script") + "<script".length
      const before = tag.slice(0, insertion)
      const after = tag.slice(insertion)
      return `${before} nonce="${CSP_NONCE_PLACEHOLDER}"${after}`
    })
  },
})

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "")
  const target = (env.VITE_BACKEND_ORIGIN || "http://127.0.0.1:8000").replace(/\/$/, "")
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
  const proxy = {
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
    withGeneratedManifests(),
    react(),
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
              cacheableResponse: { statuses: [0, 200, 304] },
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

  const toPosix = (value: string) => value.replace(/\\/g, "/")
  const routeChunks = [
    {
      name: "map",
      patterns: [
        toPosix(resolve(srcDir, "pages/Map.tsx")),
        toPosix(resolve(srcDir, "pages/MapContent.tsx")),
      ],
    },
    {
      name: "schedule",
      patterns: [
        toPosix(resolve(srcDir, "pages/Schedule.tsx")),
        toPosix(resolve(srcDir, "components/schedule")),
      ],
    },
    {
      name: "news",
      patterns: [
        toPosix(resolve(srcDir, "pages/News.tsx")),
        toPosix(resolve(srcDir, "pages/NewsDetail.tsx")),
        toPosix(resolve(srcDir, "components/NewsCard.tsx")),
      ],
    },
    {
      name: "messenger",
      patterns: [
        toPosix(resolve(srcDir, "pages/Messenger.tsx")),
        toPosix(resolve(srcDir, "components/messenger")),
      ],
    },
    {
      name: "events",
      patterns: [
        toPosix(resolve(srcDir, "pages/Events.tsx")),
        toPosix(resolve(srcDir, "components/EventCard.tsx")),
        toPosix(resolve(srcDir, "components/EventDetail.tsx")),
      ],
    },
    {
      name: "profile",
      patterns: [
        toPosix(resolve(srcDir, "pages/Profile.tsx")),
        toPosix(resolve(srcDir, "components/profile")),
      ],
    },
    {
      name: "settings",
      patterns: [
        toPosix(resolve(srcDir, "pages/Settings.tsx")),
        toPosix(resolve(srcDir, "components/settings")),
      ],
    },
    {
      name: "auth",
      patterns: [
        toPosix(resolve(srcDir, "pages/Login.tsx")),
        toPosix(resolve(srcDir, "pages/Register.tsx")),
        toPosix(resolve(srcDir, "pages/ForgotPassword.tsx")),
        toPosix(resolve(srcDir, "pages/ResetPassword.tsx")),
      ],
    },
    {
      name: "admin",
      patterns: [
        toPosix(resolve(srcDir, "pages/AdminUsers.tsx")),
        toPosix(resolve(srcDir, "pages/AdminNotifications.tsx")),
        toPosix(resolve(srcDir, "pages/StoriesAdmin.tsx")),
      ],
    },
  ] as const

  return {
    base: "/",
    plugins,
    resolve: {
      alias: {
        "@": srcDir,
        "@mui/material/styles/CssVarsProvider": resolve(srcDir, "shims/muiCssVarsProvider.ts"),
        "@mui/material/styles/useColorScheme": resolve(srcDir, "shims/muiUseColorScheme.ts"),
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
    build: {
      sourcemap: true,
      chunkSizeWarningLimit: 768,
      rollupOptions: {
        output: {
          manualChunks(id) {
            const normalizedId = toPosix(id)
            for (const chunk of routeChunks) {
              if (chunk.patterns.some((pattern) => normalizedId.startsWith(pattern)))
                return chunk.name
            }
            if (!normalizedId.includes("node_modules")) return
            const uiMatchers = [
              /[/\\]react(?:-dom)?[/\\]/,
              /[/\\]scheduler[/\\]/,
              /@emotion/,
              /@mui/,
            ] as const
            if (uiMatchers.some((pattern) => pattern.test(normalizedId))) return "ui"
            if (normalizedId.includes("@tanstack")) return "react-query"
            if (normalizedId.includes("framer-motion")) return "motion"
            if (normalizedId.includes("react-router")) return "router"
            if (normalizedId.includes("dayjs")) return "dayjs"
            if (normalizedId.includes("zxcvbn")) return "zxcvbn"
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
