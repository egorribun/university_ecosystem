import { expect, loginAs, test } from "./fixtures"

const SEEDED_STORY_TITLE = /(?:Сессия: советы по подготовке|Exam season: preparation tips)/u
const SYNTHETIC_STORY_IMAGE = '<svg xmlns="http://www.w3.org/2000/svg" width="2" height="3" />'

test("a seeded story traps focus, closes with Escape, restores focus, and releases scroll lock", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" })
  await page.route("https://picsum.photos/**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "image/svg+xml",
      body: SYNTHETIC_STORY_IMAGE,
    })
  )

  await loginAs(page, "student")
  await page.goto("/dashboard")

  const trigger = page.getByRole("button", { name: SEEDED_STORY_TITLE })
  await expect(trigger).toBeVisible()
  const initialBodyOverflow = await page.locator("body").evaluate((body) => body.style.overflow)

  await trigger.click()

  const dialog = page.getByRole("dialog")
  const closeButton = dialog.getByRole("button", { name: "Закрыть просмотр историй", exact: true })
  await expect(dialog).toBeVisible()
  await expect(dialog).toHaveAccessibleName(SEEDED_STORY_TITLE)
  await expect(closeButton).toBeFocused()
  await expect
    .poll(() => page.locator("body").evaluate((body) => body.style.overflow))
    .toBe("hidden")

  const tabbableControls = dialog.locator(
    'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
  )
  const firstControl = tabbableControls.first()
  const lastControl = tabbableControls.last()
  await expect(firstControl).toBeVisible()
  await expect(lastControl).toBeVisible()
  await firstControl.focus()
  await page.keyboard.press("Shift+Tab")
  await expect(lastControl).toBeFocused()
  await page.keyboard.press("Tab")
  await expect(firstControl).toBeFocused()

  await page.keyboard.press("Escape")

  await expect(dialog).toHaveCount(0)
  await expect(trigger).toBeFocused()
  await expect
    .poll(() => page.locator("body").evaluate((body) => body.style.overflow))
    .toBe(initialBodyOverflow)
})

test("a seeded story pauses while hidden and resumes at the preserved progress", async ({
  page,
}) => {
  const STORY_HIDDEN_DURATION_MS = 7_000
  await page.route("https://picsum.photos/**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "image/svg+xml",
      body: SYNTHETIC_STORY_IMAGE,
    })
  )

  await loginAs(page, "student")
  await page.goto("/dashboard")

  const trigger = page.getByRole("button", { name: SEEDED_STORY_TITLE })
  await expect(trigger).toBeVisible()
  await trigger.click()

  const dialog = page.getByRole("dialog")
  await expect(dialog).toBeVisible()
  await expect(dialog).toHaveAccessibleName(SEEDED_STORY_TITLE)
  const activeProgress = dialog.locator('[role="progressbar"][aria-live="polite"]')
  const readProgress = async () => Number(await activeProgress.getAttribute("aria-valuenow"))
  await expect.poll(readProgress).toBeGreaterThan(0)
  const pausedProgress = await readProgress()
  expect(pausedProgress).toBeLessThan(100)

  const backgroundPage = await page.context().newPage()
  try {
    await backgroundPage.bringToFront()
    await expect.poll(() => page.evaluate(() => document.visibilityState)).toBe("hidden")
    // Keep the real page hidden beyond the normal story duration. After it
    // returns, it must still show the same story and continue from its saved
    // progress rather than advancing immediately.
    await page.waitForTimeout(STORY_HIDDEN_DURATION_MS)
    await expect.poll(() => page.evaluate(() => document.visibilityState)).toBe("hidden")

    await page.bringToFront()
    await expect.poll(() => page.evaluate(() => document.visibilityState)).toBe("visible")
    await expect(dialog).toHaveAccessibleName(SEEDED_STORY_TITLE)
    await expect.poll(readProgress).toBeGreaterThan(pausedProgress)
    await expect(dialog).toHaveAccessibleName(SEEDED_STORY_TITLE)
  } finally {
    await backgroundPage.close()
  }

  await page.keyboard.press("Escape")
  await expect(dialog).toHaveCount(0)
})
