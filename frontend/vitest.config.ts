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
      // Ratchet floors at measured reality. SESSION-14 multi-lane sweep
      // (31 files: Lane B fresh render/data/barrel + Lane C LOW-% partials &
      // branch top-ups + Lane A Tier-3 map internals — WeatherParticles 0→88%,
      // MapFeature 0→81%, MapLibreMap fresh): statements 85.98 / branches 76.1 /
      // functions 75.17 / lines 85.98 — a +6.55pp statement JUMP from the s13
      // floor (79.43). RAISED: statements 78→85 + lines 78→85 (85.48 floor after
      // the 0.5 no-cushion buffer) + functions 72→74 (74.67 floor) + branches
      // 74→75 (75.6 floor — render+partial tests finally moved branch coverage).
      // NO-REGRESSION floors, NOT the target — raise incrementally (target 90;
      // local == CI, so there is no integration cushion: keep ≥~0.5pp headroom
      // before any raise). DEFERRED to s15 (subagent session limit): Lane D
      // logic-hooks (useChatWebSocket un-skip — needs a /ws/ticket test handler
      // not currently in mocks/server.ts; useProfileSync hook + useMessengerController).
      thresholds: {
        statements: 85,
        branches: 75,
        functions: 74,
        lines: 85,
      },
    },
  },
})
