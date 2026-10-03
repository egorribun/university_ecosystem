import { expect, test } from "./test"
import { useMockApi } from "./utils/mockApi"
import { gotoWithTransientRetry } from "./utils/navigation"

const isStaggerRowSettled = (element: Element): boolean => {
  const wrapper = element.closest(".css-stagger-item")
  if (!wrapper) {
    throw new Error("the selected event must be inside a staggered row")
  }

  const transform = getComputedStyle(wrapper).transform
  const translateY = transform === "none" ? 0 : new DOMMatrixReadOnly(transform).m42
  return translateY === 0
}

test("events back navigation restores the feed reading position", async ({ page }) => {
  await page.clock.setFixedTime(new Date("2026-06-27T10:00:00Z"))
  if (test.info().project.name !== "mobile-webkit") {
    await page.setViewportSize({ width: 1280, height: 800 })
  }
  await useMockApi(page)
  await gotoWithTransientRetry(page, "/events", { waitUntil: "commit", timeout: 30_000 })

  const eventLinks = page.locator(".events-card-title a")
  await expect(eventLinks).toHaveCount(12, { timeout: 30_000 })
  await page.evaluate(() => document.fonts.ready)

  const selectedEvent = eventLinks.nth(8)
  await selectedEvent.scrollIntoViewIfNeeded()
  await expect
    .poll(() => selectedEvent.evaluate(isStaggerRowSettled), {
      message: "the selected event row should finish entering before measuring its position",
    })
    .toBe(true)
  const selectedEventHref = (await selectedEvent.getAttribute("href")) ?? ""
  expect(selectedEventHref).toMatch(/^\/events\/uuid-\d+$/u)
  const selectedEventUrl = new URL(selectedEventHref, page.url()).href
  const title = (await selectedEvent.innerText()).trim()
  const originalPosition = await selectedEvent.evaluate((element) => ({
    scrollY: Math.round(window.scrollY),
    top: Math.round(element.getBoundingClientRect().top),
  }))
  expect(
    originalPosition.scrollY,
    "the chosen event must be below the initial viewport"
  ).toBeGreaterThan(0)

  await selectedEvent.click()
  await expect(page).toHaveURL(selectedEventUrl)
  await expect(page.getByRole("heading", { name: title, exact: true })).toBeVisible()

  await page.getByRole("button", { name: /Назад|Back/u }).click()
  await expect(page).toHaveURL(/\/events$/u)
  const restoredEvent = page.locator(".events-card-title a").nth(8)
  await expect(restoredEvent).toHaveText(title)
  await expect(restoredEvent).toHaveAttribute("href", selectedEventHref)
  await expect
    .poll(() => restoredEvent.evaluate(isStaggerRowSettled), {
      message: "the restored event row should finish entering before checking its position",
    })
    .toBe(true)
  await expect
    .poll(() => page.evaluate(() => Math.round(window.scrollY)), {
      message: "browser back should restore the events feed scroll position",
    })
    .toBe(originalPosition.scrollY)
  const restoredPosition = await restoredEvent.evaluate((element) =>
    Math.round(element.getBoundingClientRect().top)
  )
  expect(
    Math.abs(restoredPosition - originalPosition.top),
    "the selected event should return to the same viewport position"
  ).toBeLessThanOrEqual(3)
})
