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
