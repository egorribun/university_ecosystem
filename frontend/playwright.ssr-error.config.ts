import { defineConfig } from "@playwright/test"

import baseConfig from "./playwright.config"

// The spec starts the real wrapper with an isolated fixture cwd per test. It
// needs no build or shared web server, but is also collected by the regular
// production SSR config used in CI.
export default defineConfig({
  ...baseConfig,
  testDir: "./tests/e2e-live/production",
  testMatch: "ssr-error-recovery.spec.ts",
  webServer: undefined,
  projects: baseConfig.projects?.filter((project) => project.name === "chromium"),
})
