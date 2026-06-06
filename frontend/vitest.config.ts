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
      // Ratchet floors at measured reality. After the components/ui primitives
      // render-test slice (Badge, EmptyState, ProgressBar, Tooltip, Checkbox,
      // Switch — on top of the prior NotificationRelevanceScore/Spinner/...
      // slice): statements 67.09 / branches 72.34 / functions 67.86 / lines 67.09.
      // statements + lines + functions RAISED 66→67 (1.09 / 1.09 / 0.86 buffers,
      // all ≥ the ~0.5 no-cushion margin). branches HELD at 71 (72.34 → a 72
      // floor is only 0.34, < 0.5 — wait for a larger render slice). NO-REGRESSION
      // floors, NOT the target — raise incrementally (target 90; local == CI, so
      // there is no integration cushion: keep ≥~0.5pp headroom before any raise).
      thresholds: {
        statements: 67,
        branches: 71,
        functions: 67,
        lines: 67,
      },
    },
  },
})
