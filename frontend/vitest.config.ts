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
    // Node 26 exposes an experimental process-global localStorage accessor
    // which warns before JSDOM can install its isolated implementation.  Tests
    // must use JSDOM storage, never a process-persistent cross-worker store.
    poolOptions: {
      threads: { execArgv: ["--no-experimental-webstorage"] },
      forks: { execArgv: ["--no-experimental-webstorage"] },
    },
    reporters: ["default"],
    exclude: [
      "node_modules",
      "dist",
      ".idea",
      ".git",
      ".cache",
      // Stryker copies the repository (including nested dependency tests) into
      // this directory. Vitest must never discover that sandbox as authored
      // project tests, especially after a bounded mutation run is interrupted.
      "stryker-tmp/**",
      ".stryker-tmp/**",
      "tests/e2e/**",
      "scripts/**/*.test.mjs",
    ],
    coverage: {
      provider: "v8",
      // Remap against the authored AST so generated Vite SSR import wrappers
      // cannot become phantom uncovered statements during cross-worker merges.
      experimentalAstAwareRemapping: true,
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
        "src/test/**/*",
      ],
      // Authored frontend source is held to complete aggregate coverage.
      thresholds: {
        statements: 100,
        branches: 100,
        functions: 100,
        lines: 100,
      },
    },
  },
})
