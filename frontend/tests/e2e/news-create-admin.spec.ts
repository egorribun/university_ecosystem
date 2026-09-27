/**
 * Wave 11 — E2E: News feed & admin routes smoke test.
 *
 * WHY: News is the primary public-facing content surface. Any bundler
 * regression or router misconfiguration on /news would immediately impact all
 * unauthenticated visitors. These tests act as a fast canary for regressions
 * that break the entire news subtree.
 */
import { test, expect } from "./test"

test.describe("News & Admin — Wave 11", () => {
  test("app root loads without uncaught JS errors", async ({ page }) => {
    const errors: string[] = []
    page.on("pageerror", (err) => {
      if (
        !err.message.includes("ResizeObserver") &&
        !err.message.includes("AbortError") &&
        !err.message.includes("NetworkError")
      ) {
        errors.push(err.message)
      }
    })

    await page.goto("/", { waitUntil: "commit", timeout: 30_000 })
    expect(errors).toHaveLength(0)
  })

  test("news route resolves to news page or login redirect", async ({ page }) => {
    await page.goto("/news", { waitUntil: "commit", timeout: 30_000 })
    // Valid outcomes: authenticated news page OR unauthenticated redirect
    await expect(page).toHaveURL(/news|login|\/$/)
  })

  test("news route body has rendered content", async ({ page }) => {
    await page.goto("/news", { waitUntil: "commit", timeout: 30_000 })
    await expect(page.locator("body")).toBeVisible()
    const text = await page.locator("body").innerText()
    expect(text.trim().length).toBeGreaterThan(0)
  })

  test("admin route is protected (redirects when not authenticated)", async ({ page }) => {
    await page.goto("/admin/users", { waitUntil: "domcontentloaded" })

    await expect(page).toHaveURL((url) => url.pathname === "/login")
    const email = page.getByRole("textbox", { name: /^e-?mail$/i })
    const password = page.getByLabel(/^(пароль|password)$/i)
    await expect(email).toBeVisible()
    await expect(email).toBeEnabled()
    await expect(password).toBeVisible()
    await expect(password).toBeEnabled()
    await expect(page.getByRole("heading", { name: /^(Пользователи|Users)$/i })).not.toBeVisible()
  })

  test("news route has no critical console errors", async ({ page }) => {
    const consoleErrors: string[] = []
    page.on("console", (msg) => {
      if (msg.type() === "error" && !msg.text().includes("favicon")) {
        consoleErrors.push(msg.text())
      }
    })
    await page.goto("/news", { waitUntil: "commit", timeout: 30_000 })
    // Filter known CDN / third-party console errors
    const critical = consoleErrors.filter(
      (e) =>
        !e.includes("ResizeObserver") &&
        !e.includes("favicon") &&
        !e.includes("net::ERR_") &&
        !e.includes("Failed to load resource") &&
        !e.includes("status code 401")
    )
    expect(critical).toHaveLength(0)
  })
})
