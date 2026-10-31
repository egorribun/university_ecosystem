/**
 * Wave 11 — E2E: News feed & admin routes smoke test.
 *
 * WHY: News and admin routes rely on router startup and authentication guards.
 * These tests act as a fast canary for broken entry routes and redirects.
 */
import { test, expect, type Page } from "./test"
import { pageErrorsThroughReady } from "./aud151-readiness.mjs"
import { collectNewsStartupErrors } from "./aud151-news-errors.mjs"

async function expectLoginReady(page: Page) {
  await expect(page).toHaveURL((url) => url.pathname === "/login")
  const email = page.getByRole("textbox", { name: /^e-?mail$/i })
  const password = page.getByLabel(/^(пароль|password)$/i)
  await expect(email).toBeVisible()
  await expect(email).toBeEnabled()
  await expect(password).toBeVisible()
  await expect(password).toBeEnabled()
  await expect(page).toHaveURL((url) => url.pathname === "/login")
}

test.describe("News & Admin — Wave 11", () => {
  test("app root loads without uncaught JS errors", async ({ page }) => {
    const errors = await pageErrorsThroughReady(page, () => expectLoginReady(page))
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

  test("unauthenticated news redirect has no startup errors", async ({ page }) => {
    const { consoleErrors, pageErrors } = await collectNewsStartupErrors(page, () =>
      expectLoginReady(page)
    )
    expect(consoleErrors).toEqual([])
    expect(pageErrors).toEqual([])
  })

  test("startup monitoring captures errors emitted during hydration", async ({ page }) => {
    await page.addInitScript(() => {
      window.addEventListener(
        "ue:app-hydrated",
        () => {
          console.error("AUD-151 hydration console control")
          throw new Error("AUD-151 hydration page error control")
        },
        { once: true }
      )
    })
    const { consoleErrors, pageErrors } = await collectNewsStartupErrors(page, () =>
      expectLoginReady(page)
    )
    expect(consoleErrors).toContain("AUD-151 hydration console control")
    expect(pageErrors).toContain("AUD-151 hydration page error control")
  })
})
