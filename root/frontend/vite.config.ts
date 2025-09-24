import { fileURLToPath } from "node:url"
import { defineConfig, loadEnv } from "vite"
import react from "@vitejs/plugin-react"
import { visualizer } from "rollup-plugin-visualizer"
import { VitePWA } from "vite-plugin-pwa"

const srcDir = fileURLToPath(new URL("./src", import.meta.url))

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
      strategies: "injectManifest",
      srcDir: "src/pwa",
      filename: "sw.ts",
      injectRegister: false,
      registerType: "autoUpdate",
      includeAssets: ["guu_logo.png"],
      manifest: false,
      devOptions: { enabled: mode === "development", suppressWarnings: true },
      injectManifest: {
        globPatterns: ["**/*.{js,css,html,ico,png,svg,webmanifest}"]
      }
    })
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
            if (id.includes("@mui/material")) return "mui-core"
            if (id.includes("@mui/icons-material")) return "mui-icons"
            if (id.includes("@mui/x-date-pickers")) return "mui-pickers"
            if (id.includes("react-router")) return "router"
            if (id.includes("dayjs")) return "dayjs"
            if (id.includes("zxcvbn")) return "zxcvbn"
            if (id.includes("jspdf")) return "pdf"
            if (id.includes("axios")) return "axios"
          },
        },
      },
    },
  }
})
