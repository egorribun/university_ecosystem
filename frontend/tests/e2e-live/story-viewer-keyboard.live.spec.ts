import { expect, loginAs, ownedSessionOrigin, test } from "./fixtures"
import { openStoryBackgroundTab, storyVisibilityTest } from "./story-visibility-fixtures"

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

storyVisibilityTest(
  "a seeded story pauses while hidden and resumes at the preserved progress",
  async ({ page }) => {
    const STORY_HIDDEN_DURATION_MS = 7_000
    await page.route("https://picsum.photos/**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "image/svg+xml",
        body: SYNTHETIC_STORY_IMAGE,
      })
    )

    await loginAs(page, "student")
    await page.goto(new URL("/dashboard", ownedSessionOrigin()).toString())

    const trigger = page.getByRole("button", { name: SEEDED_STORY_TITLE })
    await expect(trigger).toBeVisible()
    await trigger.click()

    const dialog = page.getByRole("dialog")
    await expect(dialog).toBeVisible()
    await expect(dialog).toHaveAccessibleName(SEEDED_STORY_TITLE)
    const activeProgress = dialog.locator('[role="progressbar"][aria-live="polite"]')
    const readProgress = async () => Number(await activeProgress.getAttribute("aria-valuenow"))
    await expect.poll(readProgress).toBeGreaterThan(0)

    const backgroundPage = await openStoryBackgroundTab(page)
    try {
      await backgroundPage.bringToFront()
      await expect.poll(() => page.evaluate(() => document.visibilityState)).toBe("hidden")
      // Sample after the visibility transition, then prove the same story's
      // progress stays frozen throughout a full auto-advance interval.
      const pausedProgress = await readProgress()
      expect(pausedProgress).toBeGreaterThan(0)
      expect(pausedProgress).toBeLessThan(100)
      await page.waitForTimeout(STORY_HIDDEN_DURATION_MS)
      await expect.poll(() => page.evaluate(() => document.visibilityState)).toBe("hidden")
      await expect(dialog).toHaveAccessibleName(SEEDED_STORY_TITLE)
      expect(await readProgress()).toBe(pausedProgress)

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
  }
)

storyVisibilityTest(
  "a seeded story preserves elapsed playback across a clock-controlled hidden tab",
  async ({ page }) => {
    const STORY_HIDDEN_DURATION_MS = 7_000
    const VISIBLE_WARMUP_MS = 1_300
    const VISIBLE_RESUME_MS = 650
    const MIN_RESUMED_ADVANCE = 7
    const MAX_RESUMED_ADVANCE = 13

    await page.emulateMedia({ reducedMotion: "no-preference" })
    // Install before navigation so the viewer and all of its frame callbacks
    // use the same clock; leave it running until login and hydration finish.
    await page.clock.install()
    try {
      await page.route("https://picsum.photos/**", (route) =>
        route.fulfill({
          status: 200,
          contentType: "image/svg+xml",
          body: SYNTHETIC_STORY_IMAGE,
        })
      )
      await loginAs(page, "student")
      await page.goto(new URL("/dashboard", ownedSessionOrigin()).toString())

      const trigger = page.getByRole("button", { name: SEEDED_STORY_TITLE })
      await expect(trigger).toBeVisible()
      await page.clock.pauseAt(await page.evaluate(() => Date.now() + 1_000))

      const dialog = page.getByRole("dialog")
      const activeProgress = dialog.locator('[role="progressbar"][aria-live="polite"]')
      const readProgress = async () => {
        const value = await activeProgress.getAttribute("aria-valuenow")
        expect(value).not.toBeNull()
        const progress = Number(value)
        expect(Number.isFinite(progress)).toBe(true)
        return progress
      }
      // React schedules work through MessageChannel; a frozen page clock must
      // not prevent visibility updates and their effects from being committed.
      const flushScheduledWork = async () => {
        await page.evaluate(async () => {
          for (let turn = 0; turn < 2; turn += 1) {
            await new Promise<void>((resolve) => {
              const channel = new MessageChannel()
              channel.port1.onmessage = () => {
                channel.port1.close()
                channel.port2.close()
                resolve()
              }
              channel.port2.postMessage(null)
            })
          }
        })
      }
      const openAtKnownProgress = async () => {
        await trigger.click()
        await expect(dialog).toBeVisible()
        await expect(dialog).toHaveAccessibleName(SEEDED_STORY_TITLE)
        await flushScheduledWork()
        await page.clock.runFor(VISIBLE_WARMUP_MS)
        await expect.poll(readProgress).toBeGreaterThan(15)
        expect(await readProgress()).toBeLessThan(25)
      }

      await openAtKnownProgress()
      const backgroundPage = await openStoryBackgroundTab(page)
      try {
        await backgroundPage.bringToFront()
        await expect.poll(() => page.evaluate(() => document.visibilityState)).toBe("hidden")
        await flushScheduledWork()
        const pausedProgress = await readProgress()
        expect(pausedProgress).toBeGreaterThan(15)
        expect(pausedProgress).toBeLessThan(25)

        const progressObservation = await activeProgress.evaluateHandle((element) => {
          let changes = 0
          const observer = new MutationObserver((records) => {
            changes += records.length
          })
          observer.observe(element, { attributes: true, attributeFilter: ["aria-valuenow"] })
          return {
            read: () => {
              changes += observer.takeRecords().length
              return changes
            },
            disconnect: () => observer.disconnect(),
          }
        })
        try {
          // A full story duration elapses in two checks while the real tab is
          // hidden. The negative control below checks that fake RAF can run.
          for (let checkpoint = 0; checkpoint < 2; checkpoint += 1) {
            await page.clock.fastForward(STORY_HIDDEN_DURATION_MS / 2)
            await flushScheduledWork()
            await expect.poll(() => page.evaluate(() => document.visibilityState)).toBe("hidden")
            await expect(dialog).toHaveAccessibleName(SEEDED_STORY_TITLE)
            expect(await readProgress()).toBe(pausedProgress)
            const hiddenProgressChanges = await page.evaluate(
              (observation) => observation.read(),
              progressObservation
            )
            expect(hiddenProgressChanges).toBe(0)
          }
        } finally {
          try {
            await page.evaluate((observation) => observation.disconnect(), progressObservation)
          } finally {
            await progressObservation.dispose()
          }
        }

        await page.bringToFront()
        await expect.poll(() => page.evaluate(() => document.visibilityState)).toBe("visible")
        await flushScheduledWork()
        await page.clock.runFor(VISIBLE_RESUME_MS)
        await expect.poll(readProgress).toBeGreaterThan(pausedProgress + MIN_RESUMED_ADVANCE)
        expect(await readProgress()).toBeLessThan(pausedProgress + MAX_RESUMED_ADVANCE)
        await expect(dialog).toHaveAccessibleName(SEEDED_STORY_TITLE)
        await page.keyboard.press("Escape")
        await expect(dialog).toHaveCount(0)

        // Negative control: suppress the app's next hidden visibility event.
        // The same real tab switch and fake clock must now show progress, so
        // browser background throttling cannot make the frozen check vacuous.
        const removeVisibilityBlocker = await page.evaluateHandle(() => {
          const blockHiddenVisibility = (event: Event) => {
            if (document.visibilityState === "hidden") event.stopImmediatePropagation()
          }
          document.addEventListener("visibilitychange", blockHiddenVisibility, true)
          return () => document.removeEventListener("visibilitychange", blockHiddenVisibility, true)
        })
        try {
          await openAtKnownProgress()
          const unpausedProgress = await readProgress()
          await backgroundPage.bringToFront()
          await expect.poll(() => page.evaluate(() => document.visibilityState)).toBe("hidden")
          await flushScheduledWork()
          await page.clock.fastForward(1_000)
          await expect.poll(readProgress).toBeGreaterThan(unpausedProgress + 10)
          await expect.poll(() => page.evaluate(() => document.visibilityState)).toBe("hidden")
          await expect(dialog).toHaveAccessibleName(SEEDED_STORY_TITLE)
        } finally {
          try {
            await page.evaluate((removeBlocker) => removeBlocker(), removeVisibilityBlocker)
          } finally {
            await removeVisibilityBlocker.dispose()
          }
        }
      } finally {
        await backgroundPage.close()
      }
    } finally {
      await page.clock.resume()
    }
  }
)
