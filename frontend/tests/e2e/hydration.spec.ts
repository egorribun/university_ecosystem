import { expect, test } from "@playwright/test"
import { useMockApi } from "./utils/mockApi"

test.describe("React Hydration Verification", () => {
  let hydrationErrors: string[] = []

  test.beforeEach(({ page }) => {
    hydrationErrors = []

    // Capture console errors/warnings and unhandled exceptions
    page.on("console", (msg) => {
      const text = msg.text()
      if (
        msg.type() === "error" ||
        msg.type() === "warning" ||
        text.includes("hydration") ||
        text.includes("Hydration") ||
        text.includes("did not match") ||
        text.includes("Did not expect server HTML") ||
        text.includes("Text content did not match")
      ) {
        hydrationErrors.push(`[Console ${msg.type()}] ${text}`)
      }
    })

    page.on("pageerror", (err) => {
      hydrationErrors.push(`[Page Error] ${err.message}`)
    })
  })

  test("does not produce React hydration errors on main SSR entrypoints", async ({ page }) => {
    const mock = await useMockApi(page)

    // 1. Test public /login first (does not require login token)
    await page.goto("/login", { waitUntil: "domcontentloaded", timeout: 30_000 })
    expect(hydrationErrors.filter((err) => err.toLowerCase().includes("hydration"))).toEqual([])

    // 2. Log in mock student to access protected pages
    await mock.login(page)
    expect(hydrationErrors.filter((err) => err.toLowerCase().includes("hydration"))).toEqual([])

    // Clear capture list before navigating protected sections
    hydrationErrors = []

    const protectedUrls = ["/dashboard", "/events", "/news", "/schedule", "/settings"]

    for (const url of protectedUrls) {
      await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30_000 })
      // Assert no hydration-specific errors or mismatches
      const hydrationSpecific = hydrationErrors.filter(
        (err) =>
          err.toLowerCase().includes("hydration") || err.toLowerCase().includes("did not match")
      )
      expect(hydrationSpecific).toEqual([])
    }
  })
})
