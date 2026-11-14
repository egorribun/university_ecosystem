import { expect, test } from "./test"
import { useMockApi } from "./utils/mockApi"
import { gotoWithTransientRetry } from "./utils/navigation"

// Structural geometry guards for two hosted-Linux layout failures:
// - the News header badge row overflowed the 360 px viewport;
// - the desktop navbar overflowed its pill between 1350 and 1439 px.
// Both assertions measure the rendered mock app, so they stay independent of
// the font metrics of the machine that runs them.

test.describe("News header at narrow widths", () => {
  for (const width of [360, 390]) {
    test(`keeps every header control inside the viewport at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 })
      const mock = await useMockApi(page)
      await mock.login(page)

      await gotoWithTransientRetry(page, "/news")
      const header = page.locator("main header").first()
      await expect(header.getByRole("heading", { level: 1 })).toBeVisible()

      const overflow = await page.evaluate(() => {
        const viewport = document.documentElement.clientWidth
        const header = document.querySelector("main header")
        if (!header) throw new Error("news header is missing")
        const offenders = Array.from(header.querySelectorAll<HTMLElement>("*"))
          .map((element) => ({
            tag: element.tagName.toLowerCase(),
            className: element.className.toString(),
            right: element.getBoundingClientRect().right,
            width: element.getBoundingClientRect().width,
          }))
          .filter((box) => box.width > 0 && box.right > viewport + 1)
        return {
          viewport,
          documentWidth: document.documentElement.scrollWidth,
          offenders,
        }
      })

      expect(overflow.offenders, `header elements past ${width}px`).toEqual([])
      expect(overflow.documentWidth).toBeLessThanOrEqual(width + 1)
    })
  }

  test("wraps the title group with flex-wrap so the count badge cannot overflow", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 360, height: 800 })
    const mock = await useMockApi(page)
    await mock.login(page)

    await gotoWithTransientRetry(page, "/news")
    const titleGroup = page.locator("main header h1").locator("..")
    await expect(titleGroup).toHaveClass(/\bflex-wrap\b/)
    await expect(titleGroup).toHaveClass(/\bmin-w-0\b/)
    await expect(page.locator("main header h1")).not.toHaveClass(/whitespace-nowrap/)
  })
})

test.describe("Desktop navbar between the tablet and wide breakpoints", () => {
  for (const width of [1350, 1439, 1440]) {
    test(`keeps every navbar control inside the pill at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 })
      const mock = await useMockApi(page)
      await mock.login(page)

      await gotoWithTransientRetry(page, "/news")
      const navbar = page.locator("nav.vt-navbar")
      await expect(navbar).toBeVisible()
      const settings = navbar.locator("#navbar-settings-btn")
      const mapLink = navbar.locator("#navbar-link-map")
      await expect(mapLink).toBeVisible()
      await expect(settings).toBeVisible()

      const metrics = await page.evaluate(() => {
        const content = document.querySelector<HTMLElement>("nav.vt-navbar > div > div")
        const settingsButton = document.querySelector<HTMLElement>("#navbar-settings-btn")
        if (!content || !settingsButton) throw new Error("navbar geometry is missing")
        const contentRect = content.getBoundingClientRect()
        const settingsRect = settingsButton.getBoundingClientRect()
        return {
          scrollWidth: content.scrollWidth,
          clientWidth: content.clientWidth,
          contentRight: contentRect.right,
          settingsRight: settingsRect.right,
          viewport: window.innerWidth,
        }
      })

      expect(metrics.scrollWidth, "navbar content overflow").toBeLessThanOrEqual(
        metrics.clientWidth + 1
      )
      expect(metrics.settingsRight, "settings inside the navbar pill").toBeLessThanOrEqual(
        metrics.contentRight + 1
      )
      expect(metrics.settingsRight, "settings inside the viewport").toBeLessThanOrEqual(
        metrics.viewport
      )
    })
  }

  test("collapses nav labels to icons at 1350px and keeps their accessible names", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1350, height: 900 })
    const mock = await useMockApi(page)
    await mock.login(page)

    await gotoWithTransientRetry(page, "/news")
    const mapLink = page.locator("nav.vt-navbar #navbar-link-map")
    await expect(mapLink).toBeVisible()
    const label = mapLink.locator("span").last()
    const labelWidth = await label.evaluate((element) => element.getBoundingClientRect().width)
    expect(labelWidth, "visible label is clipped to a screen-reader box").toBeLessThanOrEqual(1)
    const labelText = await mapLink.textContent()
    expect(labelText?.trim().length ?? 0).toBeGreaterThan(0)
  })

  test("keeps labelled navigation visible at 1440px", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    const mock = await useMockApi(page)
    await mock.login(page)

    await gotoWithTransientRetry(page, "/news")
    const mapLabel = page.locator("nav.vt-navbar #navbar-link-map span").last()
    await expect(mapLabel).toBeVisible()
    const labelWidth = await mapLabel.evaluate((element) => element.getBoundingClientRect().width)
    expect(labelWidth).toBeGreaterThan(20)
  })
})
