import { mkdirSync, readFileSync, writeFileSync } from "node:fs"
import { resolve } from "node:path"
import { fileURLToPath } from "node:url"
import { defineConfig, loadEnv, PluginOption } from "vite"
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
  const analyze = mode === "analyze" || process.env.ANALYZE === "1"
  const manifest = loadManifest()

  const mk = (rewrite = false) => ({
    target,
    changeOrigin: true,
    secure: false,
    ws: true,
    ...(rewrite ? { rewrite: (p: string) => p.replace(/^\/api/, "") } : {}),
  })

  const proxy = {
    "/api": mk(true),
    "/auth": mk(),
    "/static/": mk(),
    "/media/": mk(),
    "/spotify": mk(),
    "/notifications": mk(),
    "/push": mk(),
  }

  const plugins: PluginOption[] = [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      injectRegister: "script",
      strategies: "injectManifest",
      srcDir: "src",
      filename: "sw.ts",
      includeAssets: ["offline.html"],
      workbox: {
        clientsClaim: true,
        skipWaiting: true,
        runtimeCaching: [
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
      },
      devOptions: {
        enabled: false,
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
  }

  const toPosix = (value: string) => value.replace(/\\/g, "/")
  const routeChunks = [
    { name: "map", patterns: [toPosix(resolve(srcDir, "pages/Map.tsx"))] },
    { name: "schedule", patterns: [toPosix(resolve(srcDir, "pages/Schedule.tsx"))] },
    {
      name: "news",
      patterns: [
        toPosix(resolve(srcDir, "pages/News.tsx")),
        toPosix(resolve(srcDir, "components/NewsCard.tsx")),
        toPosix(resolve(srcDir, "components/NewsDetail.tsx")),
      ],
    },
  ] as const

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
    modulepreload: { polyfill: false },
    build: {
      sourcemap: true,
      chunkSizeWarningLimit: 1024,
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
            if (normalizedId.includes("jspdf")) return "pdf"
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
