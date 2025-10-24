/// <reference types="vitest" />
import { defineConfig } from "vitest/config"
import react from "@vitejs/plugin-react"
import path from "node:path"
export default defineConfig({
  cacheDir: path.resolve(__dirname, ".vitest"),
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
      "@simplewebauthn/browser": path.resolve(__dirname, "src/tests/mocks/simplewebauthn.ts"),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["src/setupTests.ts"],
    globals: true,
    css: true,
    reporters: ["default"],
    exclude: ["node_modules", "dist", ".idea", ".git", ".cache", "tests/e2e/**"],
  },
})
