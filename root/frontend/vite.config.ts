import { mkdirSync, readFileSync, writeFileSync } from "node:fs"
import { resolve } from "node:path"
import { fileURLToPath } from "node:url"
import { defineConfig, loadEnv } from "vite"
import react from "@vitejs/plugin-react"
import { VitePWA } from "vite-plugin-pwa"
import { visualizer } from "rollup-plugin-visualizer"
import { MASKABLE_ICON_BASE64 } from "./pwa-maskable-icons"

const srcDir = fileURLToPath(new URL("./src", import.meta.url))
const publicDir = fileURLToPath(new URL("./public", import.meta.url))

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
        description:
          "Экосистема ГУУ — личный кабинет со расписанием, событиями и уведомлениями.",
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
                    const cacheStorage = globalThis.caches;
                    if (!cacheStorage) return undefined;
                    const appShell = await cacheStorage.match("/index.html");
                    if (appShell) return appShell;
                    return cacheStorage.match("/offline.html");
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
            urlPattern: ({ url, sameOrigin }) =>
              sameOrigin && url.pathname.startsWith("/api"),
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
      chunkSizeWarningLimit: 1024,
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (!id.includes("node_modules")) return
            if (id.includes("framer-motion")) return "motion"
            if (id.includes("@mui")) return "mui"
            if (id.includes("react-router")) return "router"
            if (id.includes("dayjs")) return "dayjs"
            if (id.includes("zxcvbn")) return "zxcvbn"
            if (id.includes("jspdf")) return "pdf"
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
      snapshotFormat: {
        escapeString: true,
        printBasicPrototype: true,
      },
    },
  }
})
