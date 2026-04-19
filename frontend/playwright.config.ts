import { defineConfig, devices } from "@playwright/test"
import { fileURLToPath } from "node:url"
import { dirname } from "node:path"

const __dirname = dirname(fileURLToPath(import.meta.url))

const PORT = Number(process.env.PLAYWRIGHT_PORT || 5173)
const HOST = process.env.PLAYWRIGHT_HOST || "127.0.0.1"
const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || `http://${HOST}:${PORT}`

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  timeout: 90_000,
  expect: {
    timeout: 10_000,
  },
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: process.env.CI ? "retain-on-failure" : "off",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    // Wave 112 — multi-browser coverage (Safari/WebKit surfaces iOS-specific
    // CSS/backdrop-filter/touch-events bugs not visible in Chromium).
    {
      name: "firefox",
      use: { ...devices["Desktop Firefox"] },
    },
    // Wave 115 SW1 — WebKit renderer has a smaller memory envelope than
    // Chromium/Firefox. Parallel axe-core `.analyze()` calls within a single
    // WebKit browser process exhaust the renderer; tests that pass in
    // isolation (verified via `--workers=1`) OOM under `fullyParallel: true`.
    // Serialising WebKit projects (one test at a time per project) removes
    // the pressure at the cost of ~20–30 s extra wall-time on the full suite.
    //
    // `retries: 2` absorbs cold-start flake: the FIRST axe-core injection in
    // a freshly-launched WebKit browser process can OOM even with the
    // canvas gate + legacy axe mode; the renderer holds more headroom on
    // subsequent retries because GC runs between tests. Observed in Wave
    // 115 SW1 verification: different tests fail across repeat runs, always
    // the first-in-sequence. 2 retries is enough for stability in every
    // observed case during this wave.
    {
      name: "webkit",
      use: { ...devices["Desktop Safari"] },
      fullyParallel: false,
      retries: 2,
    },
    {
      name: "mobile-webkit",
      use: { ...devices["iPhone 15"] },
      fullyParallel: false,
      retries: 2,
    },
  ],
  webServer: {
    command: `npm run build && npm run preview -- --host ${HOST} --port ${PORT}`,
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    cwd: __dirname,
    env: {
      VITE_BACKEND_ORIGIN: "",
      // Wave 115 SW1 — signal Playwright e2e context so ParticleAuthBackground
      // skips its 1000-particle canvas loop. See src/components/ui/
      // ParticleAuthBackground.tsx + tests/e2e/a11y-public.spec.ts for the
      // WebKit renderer OOM that motivated this gate (A11Y-113-04 closure).
      VITE_E2E_MODE: "1",
    },
  },
})
