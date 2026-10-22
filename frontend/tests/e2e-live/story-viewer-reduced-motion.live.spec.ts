import { expect, loginAs, test } from "./fixtures"

const SEEDED_STORY_TITLE = /(?:Сессия: советы по подготовке|Exam season: preparation tips)/u
const SYNTHETIC_STORY_IMAGE = '<svg xmlns="http://www.w3.org/2000/svg" width="2" height="3" />'
const MAX_REDUCED_MOTION_DURATION_MS = 10

function cssTimesInMilliseconds(value: string): number[] {
  return value.split(",").map((rawTime) => {
    const time = rawTime.trim()
    const parsed = Number.parseFloat(time)
    return time.endsWith("ms") ? parsed : parsed * 1000
  })
}

test("StoryViewer stays keyboard-operable without meaningful motion under reduced motion", async ({
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
  await trigger.click()

  const dialog = page.getByRole("dialog")
  await expect(dialog).toBeVisible()
  await expect(dialog).toHaveAccessibleName(SEEDED_STORY_TITLE)
  const closeButton = dialog.getByRole("button", {
    name: "Закрыть просмотр историй",
    exact: true,
  })
  await expect(closeButton).toBeVisible()
  await expect(closeButton).toBeEnabled()
  await expect(closeButton).toBeFocused()

  const motion = await page.evaluate(() => {
    const dialogElement = document.querySelector<HTMLElement>('[role="dialog"]')
    const viewer = dialogElement?.closest<HTMLElement>(".css-scale-in")
    const progressFill = dialogElement?.querySelector<HTMLElement>('[role="progressbar"] > div')
    if (!viewer || !progressFill) return null

    const readTiming = (element: HTMLElement) => {
      const style = getComputedStyle(element)
      return {
        transitionDuration: style.transitionDuration,
        transitionDelay: style.transitionDelay,
        animationDuration: style.animationDuration,
        animationDelay: style.animationDelay,
      }
    }

    return {
      reducedMotion: matchMedia("(prefers-reduced-motion: reduce)").matches,
      viewer: readTiming(viewer),
      progressFill: readTiming(progressFill),
    }
  })

  expect(motion).not.toBeNull()
  expect(motion?.reducedMotion).toBe(true)
  const durations = [
    ...cssTimesInMilliseconds(motion!.viewer.transitionDuration),
    ...cssTimesInMilliseconds(motion!.viewer.animationDuration),
    ...cssTimesInMilliseconds(motion!.progressFill.transitionDuration),
    ...cssTimesInMilliseconds(motion!.progressFill.animationDuration),
  ]
  const delays = [
    ...cssTimesInMilliseconds(motion!.viewer.transitionDelay),
    ...cssTimesInMilliseconds(motion!.viewer.animationDelay),
    ...cssTimesInMilliseconds(motion!.progressFill.transitionDelay),
    ...cssTimesInMilliseconds(motion!.progressFill.animationDelay),
  ]
  expect(durations.length).toBeGreaterThan(0)
  expect(durations.every((duration) => duration <= MAX_REDUCED_MOTION_DURATION_MS)).toBe(true)
  expect(delays.every((delay) => delay === 0)).toBe(true)

  await page.keyboard.press("Escape")
  await expect(dialog).toHaveCount(0)
  await expect(trigger).toBeFocused()
})
