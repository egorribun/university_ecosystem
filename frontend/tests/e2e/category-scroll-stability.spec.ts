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
  test("news category bar keeps the same height when it becomes sticky", async ({
    page,
    isMobile,
  }) => {
    if (!isMobile) await page.setViewportSize({ width: 1280, height: 800 })
    await useMockApi(page)
    await gotoWithTransientRetry(page, "/news", { waitUntil: "commit", timeout: 30_000 })

    const bar = page.locator(".news-sticky-categories")
    await expect(bar).toBeVisible()
    await expect(page.getByRole("link", { name: /Новость дня|News of the day/i })).toBeVisible()
    await page.evaluate(async () => {
      await document.fonts.ready
    })
    await settle(page)
    await expect(bar).toHaveAttribute("data-stuck", "false")
    const initialHeight = await bar.evaluate((element) => element.getBoundingClientRect().height)

    await page.evaluate(() => window.scrollTo(0, 450))
    await expect(bar).toHaveAttribute("data-stuck", "true")
    const stickyHeight = await bar.evaluate((element) => element.getBoundingClientRect().height)
    expect(
      Math.abs(stickyHeight - initialHeight),
      `news sticky bar: initial=${initialHeight}, sticky=${stickyHeight}`
    ).toBeLessThanOrEqual(2)
  })

  for (const feed of FEEDS) {
    test(`${feed.path} categories never reset the scroll position to the top`, async ({
      page,
      isMobile,
    }) => {
      // Mock events are anchored to June 2026; keep the browser's date in
      // that fixture window so the Upcoming list cannot decay into Empty.
      await page.clock.setFixedTime(new Date("2026-06-27T10:00:00Z"))
      if (!isMobile) await page.setViewportSize({ width: 1280, height: 800 })
      await useMockApi(page)
      await gotoWithTransientRetry(page, feed.path, { waitUntil: "commit", timeout: 30_000 })

      // Category pills only; the sort toggle carries an aria-label.
      const buttons = page.locator(`${feed.bar} button:not([aria-label])`)
      const expectedCategoryCount = feed.path === "/events" ? 8 : 7
      await expect(buttons).toHaveCount(expectedCategoryCount, { timeout: 30_000 })
      await settle(page)

      // A stable scrollHeight can still be the route's Loading shell.
      await expect(buttons).toHaveCount(expectedCategoryCount, { timeout: 30_000 })
      if (feed.path === "/events")
        await expect(page.locator(".events-card-title").first()).toBeVisible()
      const count = await buttons.count()
      expect(count).toBeGreaterThan(2)
      for (let index = 1; index < count; index += 1) {
        await buttons.first().click()
        if (feed.path === "/events")
          await expect(page.locator(".events-card-title").first()).toBeVisible()
        await settle(page)
        await page.evaluate(() => window.scrollTo(0, 0))
        // Stay inside the feed's containing block. A sticky bar cannot remain
        // visible after its short mocked list ends and the footer begins.
        await page.locator(feed.bar).evaluate((bar) => {
          const feedBottom = window.scrollY + bar.parentElement!.getBoundingClientRect().bottom
          const barDocumentTop = window.scrollY + bar.getBoundingClientRect().top
          const top = Number.parseFloat(getComputedStyle(bar).top)
          const barHeight = bar.getBoundingClientRect().height
          const maxScroll = document.documentElement.scrollHeight - window.innerHeight
          window.scrollTo(
            0,
            Math.min(1200, maxScroll, barDocumentTop + 300, feedBottom - top - barHeight - 40)
          )
        })

        // The bar is stuck inside the viewport and on top of the cards, so the
        // click needs no scroll. Chromium hit-tests a sticky box against the
        // pre-scroll frame until the next frame, so wait until it is hittable.
        await expect
          .poll(() => page.locator(feed.bar).evaluate((bar) => bar.getBoundingClientRect().top))
          .toBeGreaterThanOrEqual(0)
        const barTop = await page
          .locator(feed.bar)
          .evaluate((bar) => bar.getBoundingClientRect().top)
        expect(barTop, `${feed.path} bar stuck`).toBeLessThan(200)
        await buttons.nth(index).evaluate((button) => {
          const toolbar = button.parentElement!
          const buttonRect = button.getBoundingClientRect()
          const toolbarRect = toolbar.getBoundingClientRect()
          toolbar.scrollLeft +=
            buttonRect.left - toolbarRect.left - (toolbarRect.width - buttonRect.width) / 2
        })
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

        const before = await page.evaluate(() => Math.round(window.scrollY))
        expect(before).toBeGreaterThan(400)

        const captureProbe = feed.path === "/news"
        if (captureProbe) await startScrollProbe(page, feed.bar)
        // The element has already passed a real hit-test above. Playwright's
        // locator.click() still performs its own "scroll into view if needed"
        // on sticky elements in WebKit, which can reset the outer viewport
        // before the click handler runs. Use the actual user input path so
        // this assertion measures the product's scroll behavior, not an
        // actionability scroll injected by the test driver.
        const target = await buttons.nth(index).boundingBox()
        expect(target).not.toBeNull()
        const x = target!.x + target!.width / 2
        const y = target!.y + target!.height / 2
        // One real mobile tap covers the touch path. WebKit's synthetic touch
        // injection can silently drop later taps into a horizontally scrolled
        // sticky toolbar even while hit-testing reports the visible button;
        // use pointer input for the remaining exhaustive category matrix.
        if (isMobile && index === 1) await page.touchscreen.tap(x, y)
        else await page.mouse.click(x, y)
        try {
          await expect(buttons.nth(index)).toHaveAttribute("aria-current", "page")
        } catch (error) {
          if (captureProbe) {
            const events = await stopScrollProbe(page)
            console.error(
              "category scroll activation failure",
              JSON.stringify({ index, target, events })
            )
            await test.info().attach("category-scroll-activation-timeline", {
              body: Buffer.from(JSON.stringify({ index, target, events }, null, 2)),
              contentType: "application/json",
            })
          }
          throw error
        }
        if (feed.path === "/events")
          await expect(page.locator(".events-card-title").first()).toBeVisible()
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
