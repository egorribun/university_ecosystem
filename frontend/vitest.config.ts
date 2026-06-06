/// <reference types="vitest" />
import { defineConfig } from "vitest/config"
import react from "@vitejs/plugin-react"
import path from "node:path"
export default defineConfig({
  cacheDir: path.resolve(__dirname, ".vitest"),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  plugins: [react() as any],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
      // Wave 116 polish — removed dead aliases for @mui/material/styles/
      // CssVarsProvider + useColorScheme. MUI was uninstalled long ago;
      // these pointed to src/shims/ which doesn't exist. No source file
      // imports @mui/* (verified via grep). Legacy test-harness residue.
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["src/setupTests.ts"],
    globals: true,
    css: true,
    reporters: ["default"],
    exclude: ["node_modules", "dist", ".idea", ".git", ".cache", "tests/e2e/**"],
    coverage: {
      provider: "v8",
      reporter: ["text", "json", "html"],
      include: ["src/**/*"],
      exclude: [
        "src/tests/**/*",
        "src/**/__tests__/**/*",
        "src/**/*.test.{ts,tsx}",
        "src/**/*.stories.{ts,tsx}",
        "src/setupTests.ts",
        "src/routeTree.gen.ts",
        "src/api/generated/**/*",
        "**/*.d.ts",
        "src/sw/**/*",
        "src/workers/**/*",
        "src/server.ts",
        "src/main.tsx",
        "src/utils/bootstrapFallback.ts",
        "src/utils/mapFallback.ts",
        "src/utils/performance.ts",
        "src/test/**/*",
        "src/routes/**/*",
        "src/pages/**/*",
        "src/push/**/*",
        "src/i18n/**/*",
        "src/utils/a11y.ts",
        "src/utils/categoryIcons.ts",
        "src/utils/buildingHours.ts",
        "src/utils/cryptoWorker.ts",
        "src/utils/prefetchRoutes.ts",
        "src/utils/roomStatus.ts",
        "src/utils/scrollUtils.ts",
        "src/utils/spotify.ts",
        "src/utils/workerChrome.ts",
      ],
      // Ratchet floors at measured reality. After the Activity-chart render
      // tests (features/activity/components): statements 66.01 / branches 71.71 /
      // functions 67.28 / lines 66.01. Branches raised 70→71 (0.71 buffer).
      // statements/lines HELD at 65 — measured 66.01 has no platform cushion
      // (local == CI), so a 66 floor would be a 0.01 knife-edge; functions HELD
      // at 66 (unchanged this wave). NO-REGRESSION floors, NOT the target —
      // raise incrementally as the campaign adds tests (target 90).
      thresholds: {
        statements: 65,
        branches: 71,
        functions: 66,
        lines: 65,
      },
    },
  },
})
