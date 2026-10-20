import { expect, loginAs, test } from "./fixtures"

test("SearchDialog traps Tab and restores the original focus", async ({ page }) => {
  await page.addInitScript(() => {
    const state = window as Window & { __ueDeferredOverlaysReady?: boolean }
    state.__ueDeferredOverlaysReady = false
    window.addEventListener(
      "ue:deferred-global-overlays-ready",
      () => {
        state.__ueDeferredOverlaysReady = true
      },
      { once: true }
    )
  })
  await loginAs(page, "student")
  await page.goto("/dashboard")
  await page.evaluate(() => localStorage.removeItem("ue:recent-searches"))

  const originalFocus = page.locator("#navbar-logo-link")
  await expect(originalFocus).toBeVisible()
  await originalFocus.focus()
  await expect(originalFocus).toBeFocused()
  await page.waitForFunction(() => {
    const state = window as Window & { __ueDeferredOverlaysReady?: boolean }
    return state.__ueDeferredOverlaysReady === true
  })

  await page.keyboard.press("Control+k")
  const dialog = page.getByRole("dialog")
  const input = dialog.getByRole("textbox", { name: /Поиск по приложению|Search the application/u })
  await expect(dialog).toBeVisible()
  await expect(input).toBeFocused()
  await expect(dialog.getByRole("button")).toHaveCount(0)

  // One character reveals the clear button without enabling a search request.
  await page.keyboard.type("x")
  const clear = dialog.getByRole("button", { name: /Очистить поиск|Clear search/u })
  await expect(input).toBeFocused()
  await expect(clear).toBeVisible()
  await expect(dialog.getByRole("button")).toHaveCount(1)

  await page.keyboard.press("Tab")
  await expect(clear).toBeFocused()
  await page.keyboard.press("Tab")
  await expect(input).toBeFocused()
  await page.keyboard.press("Shift+Tab")
  await expect(clear).toBeFocused()
  await page.keyboard.press("Shift+Tab")
  await expect(input).toBeFocused()

  await page.keyboard.press("Escape")
  await expect(dialog).toHaveCount(0)
  await expect(originalFocus).toBeFocused()
})

test("compact navbar preserves native profile keyboard access", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await loginAs(page, "student")
  await page.goto("/news")
  await page.waitForFunction(() => window.__APP_HYDRATED === true)
  await expect(page.getByRole("main")).toBeVisible()

  const navbar = page.locator("nav.vt-navbar")
  const name = navbar.locator(".navbar-user-name button")
  const avatar = name.locator("xpath=../preceding-sibling::button[1]")
  const settings = navbar.locator("#navbar-settings-btn")
  await expect(navbar).toBeVisible()
  await expect(name).toHaveCount(1)
  await expect(avatar).toHaveCount(1)
  await expect(settings).toHaveCount(1)
  const scrollRange = await page.evaluate(
    () => document.documentElement.scrollHeight - window.innerHeight
  )
  expect(scrollRange).toBeGreaterThan(180)

  await page.evaluate(() => window.scrollTo(0, 0))
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0)
  await expect(name).toBeEnabled()
  await avatar.focus()
  await page.keyboard.press("Tab")
  await expect(name).toBeFocused()

  // Do not blur or redirect focus: native disabling must release the hidden name.
  await page.evaluate(() => window.scrollTo(0, 180))
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(180)
  await expect(name).toBeDisabled()
  await expect(name).toHaveAttribute("aria-hidden", "true")
  await expect(name).not.toBeFocused()

  await avatar.focus()
  await page.keyboard.press("Tab")
  await expect(settings).toBeFocused()
  await page.keyboard.press("Shift+Tab")
  await expect(avatar).toBeFocused()

  await page.evaluate(() => window.scrollTo(0, 0))
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0)
  await expect(name).toBeEnabled()
  await expect(name).toHaveAttribute("aria-hidden", "false")
  await avatar.focus()
  await page.keyboard.press("Tab")
  await expect(name).toBeFocused()
  await page.keyboard.press("Enter")
  await expect.poll(() => new URL(page.url()).pathname).toBe("/profile")
})
