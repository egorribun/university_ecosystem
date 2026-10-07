import { defineConfig, devices } from "@playwright/test"
import { resolveLiveE2EOutputDirectory } from "./scripts/live-e2e-output-dir.mjs"

/**
 * Live acceptance lane: real backend, real database, seeded roles.
 *
 * Runs against the owned stand using `scripts/live_stand.py e2e`, which seeds
 * roles and passes one transient admin password into this child process.
 * Nothing here starts a server. Specs share seeded data, so the lane runs
 * serially.
 */
// Static analyzers also load Playwright config files. Keep endpoint validation
// in global setup so it runs before tests, without making config import depend
// on a live stand.
const BASE_URL = process.env.LIVE_BASE_URL

export default defineConfig({
  globalSetup: "./scripts/playwright-live-global-setup.mjs",
  testDir: "./tests/e2e-live",
  testMatch: /.*\.live\.spec\.ts$/,
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  failOnFlakyTests: Boolean(process.env.CI),
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: "list",
  outputDir: resolveLiveE2EOutputDirectory(),
  use: {
    baseURL: BASE_URL,
    ignoreHTTPSErrors: true,
    locale: "ru-RU",
    actionTimeout: 15_000,
    navigationTimeout: 45_000,
    trace: "off",
    screenshot: "off",
    video: "off",
  },
  projects: [
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
    {
      name: "mobile",
      use: { ...devices["Pixel 7"], viewport: { width: 390, height: 844 } },
    },
  ],
})
