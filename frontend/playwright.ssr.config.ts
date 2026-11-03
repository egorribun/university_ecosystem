import { defineConfig } from "@playwright/test"

import baseConfig from "./playwright.config"

// Keep the production-only documents out of the generic preview suite. A wrong
// invocation must fail, not silently skip the server-rendering assertions.
if (process.env.PRODUCTION_SERVER_E2E !== "true") {
  throw new Error("Production SSR tests require PRODUCTION_SERVER_E2E=true")
}
if (process.env.SKIP_WEBSERVER === "true" || !baseConfig.webServer) {
  throw new Error("Production SSR tests require the managed production server")
}

export default defineConfig({
  ...baseConfig,
  testDir: "./tests/e2e-live/production",
})
