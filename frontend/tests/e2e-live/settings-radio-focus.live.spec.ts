import type { Page } from "@playwright/test"
import { expect, loginAs, test } from "./fixtures"

test.use({ trace: "off", screenshot: "off", video: "off" })

async function openThemeOptions(page: Page) {
  const accordion = page
    .locator("button:has(h3)")
    .filter({ hasText: /Тема|Theme/i })
    .first()
  await expect(accordion).toBeVisible()
  if ((await accordion.getAttribute("aria-expanded")) === "true") {
    await accordion.click()
  }
  await accordion.click()
  await expect(accordion).toHaveAttribute("aria-expanded", "true")
  return accordion
}

test("Settings radio has a visible keyboard focus style", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" })
  await loginAs(page, "student")
  await page.goto("/settings")
  await expect(page.getByRole("heading", { name: /Settings|Настройки/i })).toBeVisible()

  const accordion = await openThemeOptions(page)
  await expect(accordion).toBeFocused()

  const systemRadio = page.getByRole("radio", { name: /Система|System/i })
  await expect(systemRadio).toBeVisible()
  await expect(systemRadio).toBeChecked()
  const indicator = systemRadio
    .locator("xpath=ancestor::label")
    .locator('[class~="peer-focus-visible:shadow-focus"]')
  await expect(indicator).toHaveCount(1)
  await expect(indicator).toBeVisible()
  const boxShadow = () => indicator.evaluate((element) => getComputedStyle(element).boxShadow)
  const unfocusedShadow = await boxShadow()

  // Only focus changes: no radio selection or persisted setting is changed.
  await page.keyboard.press("Tab")
  await expect(systemRadio).toBeFocused()
  await expect
    .poll(() => systemRadio.evaluate((element) => element.matches(":focus-visible")))
    .toBe(true)
  await expect.poll(boxShadow).not.toBe(unfocusedShadow)
  const focusedShadow = await boxShadow()
  expect(focusedShadow).not.toBe(unfocusedShadow)
  expect(focusedShadow).not.toBe("none")

  await page.keyboard.press("Shift+Tab")
  await expect(accordion).toBeFocused()
  await expect.poll(boxShadow).toBe(unfocusedShadow)
  await expect(systemRadio).toBeChecked()
})
