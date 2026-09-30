import { defineConfig, devices } from "@playwright/test"

/**
 * Live acceptance lane: real backend, real database, seeded roles.
 *
 * Runs against the owned stand from `scripts/live_stand.py up` (and `seed`)
 * instead of mocked API routes. Nothing here starts a server; the stand must
 * already be up. Specs live in tests/e2e-live and share seeded data, so the
 * lane runs serially.
 */
function localURL(name: string, protocols: string[]): string {
  const value = process.env[name]
  if (!value) {
    throw new Error(`${name} must be set to the endpoint printed by scripts/live_stand.py`)
  }

  let parsed: URL
  try {
    parsed = new URL(value)
  } catch {
    throw new Error(`${name} must be a valid loopback URL`)
  }
  if (
    !protocols.includes(parsed.protocol) ||
    !["localhost", "127.0.0.1"].includes(parsed.hostname) ||
    parsed.username !== "" ||
    parsed.password !== "" ||
    !parsed.port ||
    Number(parsed.port) < 20_000 ||
    Number(parsed.port) > 45_000 ||
    parsed.pathname !== "/" ||
    parsed.search !== "" ||
    parsed.hash !== ""
  ) {
    throw new Error(`${name} must use an allowed protocol and an explicit live-stand loopback port`)
  }
  return parsed.toString().replace(/\/$/, "")
}

const BASE_URL = localURL("LIVE_BASE_URL", ["https:", "http:"])
localURL("LIVE_MAILPIT_URL", ["http:"])

export default defineConfig({
  testDir: "./tests/e2e-live",
  testMatch: /.*\.live\.spec\.ts$/,
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: BASE_URL,
    ignoreHTTPSErrors: true,
    locale: "ru-RU",
    actionTimeout: 15_000,
    navigationTimeout: 45_000,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
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
