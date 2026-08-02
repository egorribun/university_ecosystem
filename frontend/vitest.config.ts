/// <reference types="vitest" />
import { defineConfig } from "vitest/config"
import react from "@vitejs/plugin-react"
import path from "node:path"
import { fileURLToPath } from "node:url"

// Vite's bundled config loader preserves import.meta.dirname, while the
// module-runner path remains compatible with older Node versions via the URL
// fallback. Avoid __dirname: this file is an ESM config.
const configDirectory = import.meta.dirname ?? path.dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  cacheDir: path.resolve(configDirectory, ".vitest"),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  plugins: [react() as any],
  resolve: {
    alias: {
      "@": path.resolve(configDirectory, "src"),
      // Wave 116 polish — removed dead aliases for @mui/material/styles/
      // CssVarsProvider + useColorScheme. MUI was uninstalled long ago;
      // these pointed to src/shims/ which doesn't exist. No source file
      // imports @mui/* (verified via grep). Legacy test-harness residue.
    },
  },
  test: {
    environment: "jsdom",
    testTimeout: 20000,
    environmentOptions: {
      url: "http://localhost/",
    },
    setupFiles: ["src/setupTests.ts"],
    globals: true,
    css: true,
    reporters: ["default"],
    exclude: [
      "node_modules",
      "dist",
      ".idea",
      ".git",
      ".cache",
      "tests/e2e/**",
      "scripts/**/*.test.mjs",
    ],
    coverage: {
      provider: "v8",
      reporter: ["text", "json", "lcov", "html"],
      reportsDirectory: "coverage",
      // Keep all authored production source in the denominator. Do not replace
      // this with a hand-selected allow-list to make a percentage look healthy.
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/tests/**/*",
        "src/**/__tests__/**/*",
        "src/**/*.test.{ts,tsx}",
        "src/**/*.stories.{ts,tsx}",
        "src/setupTests.ts",
        "src/routeTree.gen.ts",
        "src/api/generated/**/*",
        "**/*.d.ts",
        "src/workers/**/*",
        "src/server.ts",
        "src/main.tsx",
        "src/sw.ts",
        "src/test/**/*",
      ],
      // Repository quality-contract floors. They remain strict while the
      // source-wide suite is restored; a failing run is actionable evidence.
      thresholds: {
        statements: 91,
        branches: 82,
        functions: 82,
        lines: 91,
      },
    },
  },
})
