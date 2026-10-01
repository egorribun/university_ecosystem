import { expect, loginAs, test } from "./fixtures"

declare global {
  interface Window {
    __navbarLayoutShiftObserver?: PerformanceObserver
    __navbarLayoutShiftObserverSupported?: boolean
    __navbarLayoutShiftValues?: number[]
  }
}

const NAVBAR_CLS_LIMIT = 0.1

test.use({ trace: "off", screenshot: "off", video: "off" })

test("navbar compact-on-scroll keeps layout shift below 0.1", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "Navbar CLS acceptance uses desktop Chromium")

  await page.setViewportSize({ width: 1440, height: 900 })
  await loginAs(page, "student")

  await page.addInitScript(() => {
    window.__navbarLayoutShiftValues = []
    const supported =
      typeof PerformanceObserver !== "undefined" &&
      (PerformanceObserver.supportedEntryTypes?.includes("layout-shift") ?? false)
    window.__navbarLayoutShiftObserverSupported = supported
    if (!supported) return

    const observer = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        const shift = entry as PerformanceEntry & { hadRecentInput?: boolean; value?: number }
        if (!shift.hadRecentInput) window.__navbarLayoutShiftValues?.push(shift.value ?? 0)
      }
    })
    observer.observe({ type: "layout-shift", buffered: true })
    window.__navbarLayoutShiftObserver = observer
  })

  await page.goto("/news")
  await expect(page.getByRole("main")).toBeVisible()

  const decodedNavbarImages = await page.evaluate(async () => {
    await document.fonts.ready
    const images = Array.from(document.querySelectorAll<HTMLImageElement>("nav.vt-navbar img"))
    await Promise.all(images.map((image) => image.decode()))
    await new Promise<void>((resolve) =>
      requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
    )
    return images.filter((image) => image.complete && image.naturalWidth > 0).length
  })
  expect(decodedNavbarImages).toBeGreaterThan(0)

  const navbar = page.locator("nav.vt-navbar")
  await expect(navbar).toBeVisible()
  const scrollRange = await page.evaluate(
    () => document.documentElement.scrollHeight - window.innerHeight
  )
  expect(scrollRange).toBeGreaterThan(180)

  const supported = await page.evaluate(() => window.__navbarLayoutShiftObserverSupported ?? false)
  expect(supported, "Chromium must expose layout-shift PerformanceObserver entries").toBe(true)

  const initialRect = await navbar.evaluate((element) => {
    const rect = element.getBoundingClientRect()
    return { top: rect.top, height: rect.height }
  })
  await page.evaluate(() => window.scrollTo(0, 180))
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(180)
  await page.waitForFunction(() =>
    document.querySelector("nav.vt-navbar > div")?.classList.contains("relative")
  )
  const compactRect = await navbar.evaluate((element) => {
    const rect = element.getBoundingClientRect()
    return { top: rect.top, height: rect.height }
  })

  await page.evaluate(() => window.scrollTo(0, 0))
  await page.waitForFunction(
    () => !document.querySelector("nav.vt-navbar > div")?.classList.contains("relative")
  )
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0)
  await page.evaluate(async () => {
    const pill = document.querySelector("nav.vt-navbar > div")
    await Promise.all(
      (pill?.getAnimations() ?? []).map((animation) => animation.finished.catch(() => undefined))
    )
    await new Promise<void>((resolve) =>
      requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
    )
  })

  const finalMetrics = await page.evaluate(() => {
    const observer = window.__navbarLayoutShiftObserver
    for (const entry of observer?.takeRecords() ?? []) {
      const shift = entry as PerformanceEntry & { hadRecentInput?: boolean; value?: number }
      if (!shift.hadRecentInput) window.__navbarLayoutShiftValues?.push(shift.value ?? 0)
    }
    observer?.disconnect()
    window.__navbarLayoutShiftObserver = undefined
    const rect = document.querySelector("nav.vt-navbar")?.getBoundingClientRect()
    return {
      cls: window.__navbarLayoutShiftValues?.reduce((total, value) => total + value, 0) ?? 0,
      top: rect?.top ?? Number.NaN,
      height: rect?.height ?? Number.NaN,
    }
  })

  expect(compactRect.top).toBeCloseTo(initialRect.top, 0)
  expect(compactRect.height).toBeCloseTo(initialRect.height, 0)
  expect(finalMetrics.top).toBeCloseTo(initialRect.top, 0)
  expect(finalMetrics.height).toBeCloseTo(initialRect.height, 0)
  expect(finalMetrics.cls).toBeLessThan(NAVBAR_CLS_LIMIT)
})
