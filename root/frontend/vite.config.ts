import { mkdirSync, readFileSync, writeFileSync } from "node:fs"
import { resolve } from "node:path"
import { fileURLToPath } from "node:url"
import { defineConfig, loadEnv } from "vite"
import react from "@vitejs/plugin-react"
import { VitePWA } from "vite-plugin-pwa"
import { visualizer } from "rollup-plugin-visualizer"
import type { OutputBundle, OutputChunk, PluginContext } from "rollup"
import { MASKABLE_ICON_BASE64 } from "./pwa-maskable-icons"

const srcDir = fileURLToPath(new URL("./src", import.meta.url))
const publicDir = fileURLToPath(new URL("./public", import.meta.url))

const normalizePath = (value: string) => value.replace(/\\/g, "/")
const srcDirNormalized = normalizePath(srcDir)

const performanceBudget = (limitKB: number) => ({
  name: "performance-budget",
  apply: "build" as const,
  generateBundle(this: PluginContext, _options: unknown, bundle: OutputBundle) {
    const limit = limitKB * 1024
    const oversized = Object.values(bundle)
      .filter((output): output is OutputChunk => output.type === "chunk")
      .map((chunk) => ({
        fileName: chunk.fileName,
        size: Buffer.byteLength(chunk.code, "utf8"),
      }))
      .filter(({ size }) => size > limit)

    if (oversized.length > 0) {
      const details = oversized
        .map(({ fileName, size }) => `  ${fileName}: ${(size / 1024).toFixed(2)}KB`)
        .join("\n")

      this.error(`[performance-budget] The following chunks exceed ${limitKB}KB:\n${details}`)
    }
  },
})

const ensureMaskableIcons = () => {
  for (const [filename, base64] of Object.entries(MASKABLE_ICON_BASE64)) {
    const destination = resolve(publicDir, filename)
    const expected = Buffer.from(base64.replace(/\s+/g, ""), "base64")

    let writeFile = true
    try {
      const current = readFileSync(destination)
      if (current.equals(expected)) {
        writeFile = false
      }
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") {
        throw error
      }
    }

    if (writeFile) {
      mkdirSync(publicDir, { recursive: true })
      writeFileSync(destination, expected)
    }
  }
}

ensureMaskableIcons()

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "")
  const target = (env.VITE_BACKEND_ORIGIN || "http://127.0.0.1:8000").replace(/\/$/, "")
  const analyze = mode === "analyze" || process.env.ANALYZE === "1"
  const chunkSizeLimitKB = 250

  const mk = (rewrite = false) => ({
    target,
    changeOrigin: true,
    ...(rewrite ? { rewrite: (p: string) => p.replace(/^\/api/, "") } : {}),
  })

  const proxy = {
    "/api": mk(true),
    "/auth": mk(),
    "/static": mk(),
    "/media": mk(),
    "/spotify": mk(),
    "/notifications": mk(),
    "/push": mk(),
  }

  const plugins = [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      injectRegister: "auto",
      strategies: "generateSW",
      includeAssets: [
        "guu_logo.png",
        "offline.html",
        "maskable-icon-192.png",
        "maskable-icon-512.png",
      ],
      manifest: {
        name: "Экосистема ГУУ",
        short_name: "ГУУ",
        description: "Экосистема ГУУ — личный кабинет со расписанием, событиями и уведомлениями.",
        theme_color: "#0b63f4",
        background_color: "#0b0d11",
        display: "standalone",
        lang: "ru",
        start_url: "/",
        scope: "/",
        icons: [
          {
            src: "/guu_logo.png",
            sizes: "192x192",
            type: "image/png",
          },
          {
            src: "/maskable-icon-192.png",
            sizes: "192x192",
            type: "image/png",
            purpose: "maskable any",
          },
          {
            src: "/guu_logo.png",
            sizes: "512x512",
            type: "image/png",
          },
          {
            src: "/maskable-icon-512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "maskable any",
          },
        ],
      },
      workbox: {
        globPatterns: ["**/*.{js,css,html,ico,png,svg,webp,json}"],
        navigateFallback: "/offline.html",
        navigateFallbackAllowlist: [/^\/[^_].*/],
        navigationPreload: true,
        cleanupOutdatedCaches: true,
        runtimeCaching: [
          {
            urlPattern: ({ sameOrigin, url }) =>
              sameOrigin && (url.pathname === "/" || url.pathname === "/login"),
            handler: "NetworkFirst",
            options: {
              cacheName: "app-shell",
              networkTimeoutSeconds: 5,
              plugins: [
                {
                  handlerDidError: async () => {
                    const cacheStorage = globalThis.caches
                    if (!cacheStorage) return undefined
                    const appShell = await cacheStorage.match("/index.html")
                    if (appShell) return appShell
                    return cacheStorage.match("/offline.html")
                  },
                },
              ],
            },
          },
          {
            urlPattern: ({ request }) => request.mode === "navigate",
            handler: "NetworkFirst",
            options: {
              cacheName: "html-cache",
              networkTimeoutSeconds: 5,
            },
          },
          {
            urlPattern: ({ request }) =>
              ["style", "script", "worker", "font"].includes(request.destination),
            handler: "CacheFirst",
            options: {
              cacheName: "static-resources",
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          {
            urlPattern: ({ request }) => request.destination === "image",
            handler: "CacheFirst",
            options: {
              cacheName: "image-assets",
              expiration: {
                maxEntries: 60,
                maxAgeSeconds: 60 * 60 * 24 * 30,
              },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          {
            urlPattern: ({ request, sameOrigin, url }) =>
              sameOrigin &&
              request.method === "GET" &&
              url.pathname.startsWith("/api") &&
              (/\b(list|lists|catalog|all)\b/.test(url.pathname) ||
                url.searchParams.has("page") ||
                url.searchParams.has("limit")),
            handler: "StaleWhileRevalidate",
            options: {
              cacheName: "api-lists",
              cacheableResponse: {
                statuses: [0, 200],
              },
            },
          },
          {
            urlPattern: ({ sameOrigin, url }) => sameOrigin && url.pathname.startsWith("/auth"),
            handler: "NetworkOnly",
          },
          {
            urlPattern: ({ url, sameOrigin }) => sameOrigin && url.pathname.startsWith("/api"),
            handler: "NetworkFirst",
            options: {
              cacheName: "api-cache",
              networkTimeoutSeconds: 10,
              cacheableResponse: {
                statuses: [0, 200],
              },
            },
          },
        ],
      },
    }),
    performanceBudget(chunkSizeLimitKB),
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
  }

  return {
    plugins,
    resolve: { alias: { "@": srcDir } },
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
      exclude: ["jspdf", "qrcode", "zxcvbn"],
    },
    build: {
      sourcemap: true,
      cssCodeSplit: true,
      reportCompressedSize: true,
      chunkSizeWarningLimit: chunkSizeLimitKB,
      rollupOptions: {
        output: {
          manualChunks(id) {
            const normalized = normalizePath(id)

            if (normalized.includes(`${srcDirNormalized}/pages/News`)) return "page-news"
            if (normalized.includes(`${srcDirNormalized}/components/NewsDetail`))
              return "page-news-detail"
            if (normalized.includes(`${srcDirNormalized}/pages/Map`)) return "page-map"

            if (!normalized.includes("node_modules")) return
            if (normalized.includes("framer-motion")) return "motion"
            if (normalized.includes("@mui")) return "mui"
            if (normalized.includes("react-router")) return "router"
            if (normalized.includes("dayjs")) return "dayjs"
            if (normalized.includes("zxcvbn")) return "zxcvbn"
            if (normalized.includes("jspdf")) return "pdf"
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
