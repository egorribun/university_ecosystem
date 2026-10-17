import { expect, loginAs, test } from "./fixtures"

test.use({ trace: "off", screenshot: "off", video: "off" })

test("schedule reflows and remains keyboard-usable at a 200%-equivalent CSS viewport", async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "This is a desktop 200%-equivalent viewport check")

  // A 720x450 CSS viewport represents the content area available at 200% zoom
  // from a 1440x900 desktop viewport; it does not emulate browser chrome zoom.
  await page.setViewportSize({ width: 720, height: 450 })
  await loginAs(page, "student")
  await page.goto("/schedule")
  await expect.poll(() => new URL(page.url()).pathname).toBe("/schedule")

  await expect(page.getByRole("heading", { level: 1 })).toBeVisible()
  const dayTabs = page.getByRole("tablist")
  await expect(dayTabs).toBeVisible()
  const selectedDay = dayTabs.getByRole("tab", { selected: true })
  await expect(selectedDay).toBeVisible()
  await selectedDay.scrollIntoViewIfNeeded()
  await expect(selectedDay).toBeInViewport()

  const viewport = await page.evaluate(() => ({
    width: window.innerWidth,
    scrollWidth: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
  }))
  expect(viewport.width).toBe(720)
  expect(viewport.scrollWidth).toBeLessThanOrEqual(viewport.width + 1)

  const settingsButton = page.getByRole("button", { name: /настройки|settings/i })
  await expect(settingsButton).toBeVisible()
  await settingsButton.focus()
  await expect(settingsButton).toBeFocused()
  await page.keyboard.press("Enter")

  const settingsDialog = page.getByRole("dialog")
  await expect(settingsDialog).toBeVisible()
  await expect(settingsDialog.getByRole("heading", { level: 2 })).toBeVisible()
  const dialogBounds = await settingsDialog.boundingBox()
  expect(dialogBounds).not.toBeNull()
  if (dialogBounds) {
    expect(dialogBounds.x).toBeGreaterThanOrEqual(0)
    expect(dialogBounds.y).toBeGreaterThanOrEqual(0)
    expect(dialogBounds.x + dialogBounds.width).toBeLessThanOrEqual(720)
    expect(dialogBounds.y + dialogBounds.height).toBeLessThanOrEqual(450)
  }

  await page.keyboard.press("Tab")
  expect(await settingsDialog.evaluate((dialog) => dialog.contains(document.activeElement))).toBe(
    true
  )
  await page.keyboard.press("Escape")
  await expect(settingsDialog).toBeHidden()
  await expect(settingsButton).toBeFocused()
})
