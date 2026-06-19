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
      // Ratchet floors at measured reality. SESSION-15 MAXIMAL whole-project sweep
      // (40 new test files / ~635 tests via Workflow orchestration: Lane F fresh
      // render/logic + .branches top-ups (api interceptors/client/mfa/queryClient,
      // events/news/messenger/schedule/profile/feedback/pwa components, EventsFeature
      // 99% + MapFeature 100% orchestrators), Lane D hook-tier (useAuthApi/useLoginFlow/
      // useSessionCrypto/usePushPreferences/keyboard-nav + events.ts 98%/news.ts 98%),
      // and the 3 hard hooks in the main loop — useChatWebSocket UN-SKIPPED (W113 ->
      // 32%→78.9% via a /ws/ticket MSW handler + frame-cache helpers + live frame
      // switch), useMessengerController.branches, useProfileSync.branches (fetchCurrentUser
      // + cross-tab sync): statements 91.35 / branches 80.60 / functions 82.39 / lines
      // 91.35 — a +5.36pp statement JUMP from the s14 floor (85.99). RAISED: statements
      // 85→90 + lines 85→90 (90.85 floor after the 0.5 no-cushion buffer) + functions
      // 74→81 (81.89 floor) + branches 75→80 (80.10 floor). NO-REGRESSION floors, NOT
      // the target — raise incrementally (target 90→95; local == CI, so there is no
      // integration cushion: keep ≥~0.5pp headroom before any raise; branches jitter
      // ±0.01 run-to-run from one async-timing map branch). REMAINING (s16 candidates):
      // useProfileSync initFn cached-restore paths (unreachable — readCachedEnvelope()
      // source bug always returns undefined), useChatWebSocket ping/reconnect-cap 30s
      // timer paths, api/client 429-retry loop, etagCache/sanitize/sw long-tail.
      thresholds: {
        statements: 90,
        branches: 80,
        functions: 81,
        lines: 90,
      },
    },
  },
})
