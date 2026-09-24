import { expect, test, type Page } from "./test"
import { useMockApi } from "./utils/mockApi"
import { gotoWithTransientRetry } from "./utils/navigation"

/**
 * MVP spec §4: switching a News or Events category must not throw the page
 * back to the top. The category bar has to stay stuck above the list while
 * reading, and a narrower category first renders only the matches among the
 * loaded pages; the page may only settle at the final list's own maximum
 * scroll position.
 */
const settle = async (page: Page) => {
  let previous = -1
  await expect
    .poll(
      async () => {
        const height = await page.evaluate(() => document.documentElement.scrollHeight)
        const stable = height === previous
        previous = height
        return stable
      },
      { intervals: [400], timeout: 20_000 }
    )
    .toBe(true)
}

type ScrollProbeEvent = {
  kind: string
  at: number
  scrollY: number
  maxScroll: number
  search: string
  focus: string
  sameRoot: boolean
  sameBar: boolean
  stack?: string
}

type ScrollProbeWindow = Window & {
  __categoryScrollProbe?: {
    events: ScrollProbeEvent[]
    stop: () => void
  }
}

const startScrollProbe = async (page: Page, barSelector: string) => {
  await page.evaluate((selector) => {
    const probeWindow = window as ScrollProbeWindow
    const root = document.querySelector("[data-scroll-root]")
    const bar = document.querySelector(selector)
    const events: ScrollProbeEvent[] = []
    const startedAt = performance.now()
    let previousFrame = ""
    let frameCount = 0

    const record = (kind: string, stack?: string) => {
      const scrollY = Math.round(window.scrollY)
      const maxScroll = document.documentElement.scrollHeight - window.innerHeight
      const focus = document.activeElement?.tagName ?? "none"
      const sameRoot = document.querySelector("[data-scroll-root]") === root
      const sameBar = document.querySelector(selector) === bar
      const state = `${scrollY}|${maxScroll}|${location.search}|${focus}|${sameRoot}|${sameBar}`
      if (kind === "frame" && state === previousFrame) return
      previousFrame = state
      if (events.length < 200) {
        events.push({
          kind,
          at: Math.round(performance.now() - startedAt),
          scrollY,
          maxScroll,
          search: location.search,
          focus,
          sameRoot,
          sameBar,
          ...(stack ? { stack } : {}),
        })
      }
    }

    const originalScrollTo = window.scrollTo
    const originalScrollIntoView = Element.prototype.scrollIntoView
    window.scrollTo = ((...args: unknown[]) => {
      record("scrollTo", new Error().stack)
      Reflect.apply(originalScrollTo, window, args)
    }) as typeof window.scrollTo
    Element.prototype.scrollIntoView = function (this: Element, ...args: unknown[]) {
      record("scrollIntoView", new Error().stack)
      Reflect.apply(originalScrollIntoView, this, args)
    } as typeof Element.prototype.scrollIntoView

    const onScroll = () => record("scroll")
    const onFocus = () => record("focus")
    window.addEventListener("scroll", onScroll, { passive: true })
    document.addEventListener("focusin", onFocus)
    const frame = () => {
      record("frame")
      frameCount += 1
      if (frameCount < 120) requestAnimationFrame(frame)
    }
    requestAnimationFrame(frame)
    record("start")

    probeWindow.__categoryScrollProbe = {
      events,
      stop: () => {
        window.removeEventListener("scroll", onScroll)
        document.removeEventListener("focusin", onFocus)
        window.scrollTo = originalScrollTo
        Element.prototype.scrollIntoView = originalScrollIntoView
        record("stop")
      },
    }
  }, barSelector)
}

const stopScrollProbe = (page: Page) =>
  page.evaluate(() => {
    const probe = (window as ScrollProbeWindow).__categoryScrollProbe
    probe?.stop()
    return probe?.events ?? []
  })

const FEEDS = [
  { path: "/events", bar: ".events-sticky-categories" },
  { path: "/news", bar: ".news-sticky-categories" },
] as const

test.describe("Category filters keep the reading position", () => {
  for (const feed of FEEDS) {
    test(`${feed.path} categories never reset the scroll position to the top`, async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 })
      await useMockApi(page)
      await gotoWithTransientRetry(page, feed.path, { waitUntil: "commit", timeout: 30_000 })

      // Category pills only; the sort toggle carries an aria-label.
      const buttons = page.locator(`${feed.bar} button:not([aria-label])`)
      await expect(buttons.nth(1)).toBeVisible({ timeout: 30_000 })
      await settle(page)

      // The feed can briefly re-suspend while the mocked session settles.
      await expect(buttons.nth(1)).toBeVisible({ timeout: 30_000 })
      const count = await buttons.count()
      expect(count).toBeGreaterThan(2)
      for (let index = 1; index < count; index += 1) {
        await buttons.first().click()
        await settle(page)
        // Read well below the category bar (as deep as the mocked feed allows).
        await page.evaluate(() =>
          window.scrollTo(
            0,
            Math.min(1200, document.documentElement.scrollHeight - window.innerHeight)
          )
        )
        const before = await page.evaluate(() => Math.round(window.scrollY))
        expect(before).toBeGreaterThan(400)

        // The bar is stuck inside the viewport and on top of the cards, so the
        // click needs no scroll. Chromium hit-tests a sticky box against the
        // pre-scroll frame until the next frame, so wait until it is hittable.
        const barTop = await page
          .locator(feed.bar)
          .evaluate((bar) => bar.getBoundingClientRect().top)
        expect(barTop, `${feed.path} bar stuck`).toBeGreaterThanOrEqual(0)
        expect(barTop, `${feed.path} bar stuck`).toBeLessThan(200)
        await expect
          .poll(() =>
            buttons.nth(index).evaluate((button) => {
              const rect = button.getBoundingClientRect()
              const hit = document.elementFromPoint(
                rect.left + rect.width / 2,
                rect.top + rect.height / 2
              )
              return hit !== null && button.contains(hit)
            })
          )
          .toBe(true)

        const captureProbe = feed.path === "/news" && index === 1
        if (captureProbe) await startScrollProbe(page, feed.bar)
        await buttons.nth(index).click()
        await settle(page)

        const { scrollY, maxScroll } = await page.evaluate(() => ({
          scrollY: Math.round(window.scrollY),
          maxScroll: document.documentElement.scrollHeight - window.innerHeight,
        }))
        const expected = Math.min(before, maxScroll)
        if (captureProbe) {
          const events = await stopScrollProbe(page)
          if (Math.abs(scrollY - expected) > 2) {
            await test.info().attach("category-scroll-timeline", {
              body: Buffer.from(JSON.stringify(events, null, 2)),
              contentType: "application/json",
            })
          }
        }
        expect(
          Math.abs(scrollY - expected),
          `${feed.path} category ${index}: before=${before} after=${scrollY} max=${maxScroll}`
        ).toBeLessThanOrEqual(2)
        if (maxScroll > 0)
          expect(
            scrollY,
            `${feed.path} category ${index}: before=${before} after=${scrollY} max=${maxScroll}`
          ).toBeGreaterThan(0)
      }
    })
  }
})
