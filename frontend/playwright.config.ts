import { defineConfig, devices } from "@playwright/test"
import { fileURLToPath } from "node:url"
import { dirname } from "node:path"

const __dirname = dirname(fileURLToPath(import.meta.url))

// Wave 121 SW3 — URL_STATE_E2E auto-managed mode uses port 4175 (matches the
// `URL_STATE_E2E_BASE` default in `tests/e2e/url-state-persistence.spec.ts`)
// and a VITE_LHCI=true build, so authenticated routes resolve via the mock
// user instead of redirecting to /login. Default 5173 covers the normal
// dev preview used by a11y-public + a11y-cdn-axe.
const URL_STATE_E2E_MODE = process.env.URL_STATE_E2E === "true"
const PRODUCTION_SERVER_E2E_MODE = process.env.PRODUCTION_SERVER_E2E === "true"
const E2E_COVERAGE_MODE = process.env.E2E_COVERAGE === "true"
const PORT = Number(process.env.PLAYWRIGHT_PORT || (URL_STATE_E2E_MODE ? 4175 : 5173))
const HOST = process.env.PLAYWRIGHT_HOST || "127.0.0.1"
const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || `http://${HOST}:${PORT}`
const BUILD_COMMAND = E2E_COVERAGE_MODE
  ? "npx cross-env FRONTEND_BUILD_UNMINIFIED=true npm run build"
  : "npm run build"
const URL_STATE_BUILD_COMMAND = E2E_COVERAGE_MODE
  ? "npx cross-env VITE_LHCI=true FRONTEND_BUILD_UNMINIFIED=true npm run build"
  : "npx cross-env VITE_LHCI=true npm run build"

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
  // Wave 120 SW7 — `SKIP_WEBSERVER=true` lets specs that need a custom
  // dist (e.g. `url-state-persistence.spec.ts`) point at a separately-managed
  // `vite preview` instance. Wave 121 SW3 added a third mode:
  // `URL_STATE_E2E=true` auto-builds a VITE_LHCI=true dist via cross-env (the
  // missing dep that blocked Wave 120's auto-managed attempt) so the spec
  // runs without the 3-step manual flow. SKIP_WEBSERVER stays as fallback.
  webServer:
    process.env.SKIP_WEBSERVER === "true"
      ? undefined
      : PRODUCTION_SERVER_E2E_MODE
        ? {
            // The cache-policy contract must exercise the production Node
            // wrapper, not Vite's development preview middleware.
            command: `${BUILD_COMMAND} && npx cross-env HOST=${HOST} PORT=${PORT} npm run start`,
            url: BASE_URL,
            reuseExistingServer: false,
            timeout: 360_000,
            cwd: __dirname,
            env: {
              VITE_BACKEND_ORIGIN: process.env.VITE_BACKEND_ORIGIN ?? "",
              VITE_E2E_MODE: "1",
            },
          }
        : URL_STATE_E2E_MODE
          ? {
              // cross-env propagates VITE_LHCI=true to npm run build on every
              // platform (bash, zsh, cmd.exe, PowerShell). The rebuild is gated
              // by the env var — once dist/ is the LHCI build, vite preview is
              // env-independent. --strictPort fails fast on collision.
              command: `${URL_STATE_BUILD_COMMAND} && npm run preview -- --host ${HOST} --port ${PORT} --strictPort`,
              url: BASE_URL,
              reuseExistingServer: !process.env.CI,
              // Wave 125 polish — bumped from 240s. Phase 2 build is slower
              // than pre-W125 (~30-45s vs ~7s) due to TanStack Start runtime
              // additions + SSR pipeline (server build for prerender + post-
              // build shell post-processing). 240s was fine pre-W125 but
              // tight for Phase 2 cold-cache builds; 360s gives headroom for
              // CI runners under load (W125 close-out routine-e5 documented
              // CI Linux ~0.10-0.12 slower per request).
              timeout: 360_000,
              cwd: __dirname,
              env: {
                VITE_BACKEND_ORIGIN: process.env.VITE_BACKEND_ORIGIN ?? "",
                VITE_E2E_MODE: "1",
              },
            }
          : {
              command: `${BUILD_COMMAND} && npm run preview -- --host ${HOST} --port ${PORT}`,
              url: BASE_URL,
              reuseExistingServer: !process.env.CI,
              // Wave 125 polish — bumped from 180s. Phase 2 build is slower
              // than pre-W125 (~30-45s vs ~7s) due to TanStack Start runtime
              // additions + SSR pipeline; the previous 180s value caused
              // `Error: Timed out waiting 180000ms from config.webServer`
              // when first run on the W125 Phase 2 build. 360s gives ample
              // headroom even on cold-cache CI Linux runners.
              timeout: 360_000,
              cwd: __dirname,
              env: {
                VITE_BACKEND_ORIGIN: process.env.VITE_BACKEND_ORIGIN ?? "",
                // Wave 115 SW1 — signal Playwright e2e context so ParticleAuthBackground
                // skips its 1000-particle canvas loop. See src/components/ui/
                // ParticleAuthBackground.tsx + tests/e2e/a11y-public.spec.ts for the
                // WebKit renderer OOM that motivated this gate (A11Y-113-04 closure).
                VITE_E2E_MODE: "1",
              },
            },
})
