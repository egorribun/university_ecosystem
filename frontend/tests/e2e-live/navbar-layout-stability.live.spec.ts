import { expect, loginAs, test } from "./fixtures"
import type { Page } from "@playwright/test"

declare global {
  interface Window {
    __navbarLayoutShiftObserver?: PerformanceObserver
    __navbarLayoutShiftObserverSupported?: boolean
    __navbarLayoutShiftValues?: number[]
  }
}

const NAVBAR_CLS_LIMIT = 0.1

async function assertDesktopNavbarSpacingMatrix(page: Page): Promise<void> {
  const liveBaseUrl = process.env.LIVE_BASE_URL
  if (!liveBaseUrl) throw new Error("LIVE_BASE_URL must be set by the live acceptance runner")

  const context = page.context()
  for (const locale of ["ru", "en"] as const) {
    for (const theme of ["light", "dark"] as const) {
      await context.addCookies([
        { name: "ue:language", value: locale, url: liveBaseUrl },
        { name: "ue-mode", value: theme, url: liveBaseUrl },
      ])
      await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" })
      await page.evaluate(
        ({ selectedLocale, selectedTheme }) => {
          localStorage.setItem("ue:language", selectedLocale)
          localStorage.setItem("ue-mode", selectedTheme)
        },
        { selectedLocale: locale, selectedTheme: theme }
      )

      const response = await page.goto("/news", { waitUntil: "domcontentloaded" })
      const preferenceLabel = locale + "/" + theme
      expect(response?.status(), preferenceLabel + " route status").toBe(200)
      await page.waitForFunction(() => window.__APP_HYDRATED === true)
      await expect(page.locator("html"), preferenceLabel + " locale").toHaveAttribute(
        "lang",
        locale
      )
      await expect(page.locator("html"), preferenceLabel + " theme").toHaveAttribute(
        "data-color-scheme",
        theme
      )
      await page.evaluate(() => document.fonts.ready)

      const navbar = page.locator("nav.vt-navbar")
      await expect(navbar, preferenceLabel + " navbar").toBeVisible()
      const mapLink = navbar.locator("#navbar-link-map")
      const overflowTrigger = navbar.locator(
        '.navbar-desktop-overflow button[aria-haspopup="menu"]'
      )
      const messenger = navbar.locator("#global-messenger-btn")
      const settings = navbar.locator("#navbar-settings-btn")
      const username = navbar.locator(".navbar-user-name button")

      for (const width of [1440, 1349, 1350]) {
        const label = preferenceLabel + "/" + width
        await page.setViewportSize({ width, height: 900 })
        await page.evaluate(
          () =>
            new Promise<void>((resolve) =>
              requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
            )
        )
        if (width < 1350) {
          await expect(overflowTrigger, label + " tablet overflow").toBeVisible()
          await expect(mapLink, label + " map moves to overflow").toHaveCount(0)
        } else {
          await expect(mapLink, label + " map link").toBeVisible()
          await expect(overflowTrigger, label + " full navigation").toHaveCount(0)
        }
        await expect(messenger, label + " messenger action").toBeVisible()
        await expect(settings, label + " settings action").toBeVisible()

        const reference = width < 1350 ? overflowTrigger : mapLink
        const referenceBox = await reference.boundingBox()
        const messengerBox = await messenger.boundingBox()
        const settingsBox = await settings.boundingBox()
        const nameBox = await navbar.locator(".navbar-user-name").boundingBox()
        const contentBox = await page.locator("nav.vt-navbar > div > div").boundingBox()
        if (!referenceBox || !messengerBox || !settingsBox || !nameBox || !contentBox) {
          throw new Error(label + " navbar geometry was unavailable")
        }
        const contentMetrics = await page
          .locator("nav.vt-navbar > div > div")
          .evaluate((element) => ({
            clientWidth: element.clientWidth,
            scrollWidth: element.scrollWidth,
          }))
        expect(
          messengerBox.x - (referenceBox.x + referenceBox.width),
          label + " reserved nav-to-action gap"
        ).toBeGreaterThanOrEqual(12)
        expect(
          nameBox.x + nameBox.width,
          label + " username stays before the settings control"
        ).toBeLessThanOrEqual(settingsBox.x + 1)
        expect(
          settingsBox.x + settingsBox.width,
          label + " settings stays inside the action layout"
        ).toBeLessThanOrEqual(contentBox.x + contentBox.width + 1)
        expect(
          contentMetrics.scrollWidth,
          label + " navbar content does not overflow horizontally"
        ).toBeLessThanOrEqual(contentMetrics.clientWidth + 1)

        if (width >= 1350) {
          // In-memory DOM text only; restore it before the next viewport or route.
          const realName = await username.textContent()
          try {
            await username.evaluate((element) => {
              element.textContent =
                "Synthetic profile name longer than the desktop nav width ".repeat(3)
            })
            await page.evaluate(
              () =>
                new Promise<void>((resolve) =>
                  requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
                )
            )
            const syntheticNameBox = await navbar.locator(".navbar-user-name").boundingBox()
            const syntheticReferenceBox = await reference.boundingBox()
            const syntheticMessengerBox = await messenger.boundingBox()
            const syntheticSettingsBox = await settings.boundingBox()
            const syntheticContentBox = await page
              .locator("nav.vt-navbar > div > div")
              .boundingBox()
            const syntheticMetrics = await page
              .locator("nav.vt-navbar > div > div")
              .evaluate((element) => ({
                clientWidth: element.clientWidth,
                scrollWidth: element.scrollWidth,
              }))
            if (
              !syntheticNameBox ||
              !syntheticReferenceBox ||
              !syntheticMessengerBox ||
              !syntheticSettingsBox ||
              !syntheticContentBox
            ) {
              throw new Error(label + " synthetic username geometry was unavailable")
            }
            expect(
              syntheticMessengerBox.x - (syntheticReferenceBox.x + syntheticReferenceBox.width),
              label + " long synthetic username preserves the nav-to-action gap"
            ).toBeGreaterThanOrEqual(12)
            expect(
              syntheticNameBox.x + syntheticNameBox.width,
              label + " long synthetic username stays before settings"
            ).toBeLessThanOrEqual(syntheticSettingsBox.x + 1)
            expect(
              syntheticSettingsBox.x + syntheticSettingsBox.width,
              label + " settings stays inside the action layout with long username"
            ).toBeLessThanOrEqual(syntheticContentBox.x + syntheticContentBox.width + 1)
            expect(
              syntheticMetrics.scrollWidth,
              label + " long synthetic username does not overflow the navbar"
            ).toBeLessThanOrEqual(syntheticMetrics.clientWidth + 1)
          } finally {
            await username.evaluate((element, value) => {
              element.textContent = value ?? ""
            }, realName)
          }
        }
      }
    }
  }
}

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
  await assertDesktopNavbarSpacingMatrix(page)
})

async function navbarShellRect(page: Page): Promise<{ top: number; height: number }> {
  return page.locator("nav.vt-navbar").evaluate((element) => {
    const rect = element.getBoundingClientRect()
    return { top: rect.top, height: rect.height }
  })
}

test("mobile drawer traps keyboard focus, closes with Escape, and releases scroll lock", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await loginAs(page, "student")

  for (const width of [390, 360]) {
    await page.setViewportSize({ width, height: 844 })
    await page.goto("/dashboard")
    await expect(page.getByRole("main")).toBeVisible()

    const menuTrigger = page.locator('button[aria-controls="mobile-drawer"]')
    await expect(menuTrigger).toBeVisible()
    const triggerSize = await menuTrigger.evaluate((element) => {
      const rect = element.getBoundingClientRect()
      return { width: rect.width, height: rect.height }
    })
    expect(triggerSize.width, `${width}px menu trigger width`).toBeGreaterThanOrEqual(44)
    expect(triggerSize.height, `${width}px menu trigger height`).toBeGreaterThanOrEqual(44)

    const previousBodyOverflow = await page.evaluate(() => document.body.style.overflow)
    await menuTrigger.click()

    const drawer = page.getByRole("dialog")
    await expect(drawer).toBeVisible()
    await expect(drawer).toHaveAttribute("aria-modal", "true")
    await expect(menuTrigger).toHaveAttribute("aria-expanded", "true")
    await expect.poll(() => page.evaluate(() => document.body.style.overflow)).toBe("hidden")

    const closeButton = drawer.getByRole("button").first()
    await expect(closeButton).toBeFocused()
    const closeSize = await closeButton.evaluate((element) => {
      const rect = element.getBoundingClientRect()
      return { width: rect.width, height: rect.height }
    })
    expect(closeSize.width, `${width}px drawer close width`).toBeGreaterThanOrEqual(44)
    expect(closeSize.height, `${width}px drawer close height`).toBeGreaterThanOrEqual(44)

    const firstNavigationLink = drawer.locator("a.mobile-nav-link").first()
    const lastNavigationLink = drawer.locator("a.mobile-nav-link").last()
    await expect(firstNavigationLink).toBeVisible()
    const navigationLinkSize = await firstNavigationLink.evaluate((element) => {
      const rect = element.getBoundingClientRect()
      return { width: rect.width, height: rect.height }
    })
    expect(navigationLinkSize.width, `${width}px drawer link width`).toBeGreaterThanOrEqual(44)
    expect(navigationLinkSize.height, `${width}px drawer link height`).toBeGreaterThanOrEqual(44)

    await page.keyboard.press("Shift+Tab")
    await expect(lastNavigationLink).toBeFocused()
    await page.keyboard.press("Tab")
    await expect(closeButton).toBeFocused()

    await page.keyboard.press("Escape")
    await expect(drawer).toBeHidden()
    await expect(menuTrigger).toHaveAttribute("aria-expanded", "false")
    await expect(menuTrigger).toBeFocused()
    await expect
      .poll(() => page.evaluate(() => document.body.style.overflow))
      .toBe(previousBodyOverflow)
  }
})

test("mobile navbar shell geometry stays fixed through scrolling and route navigation", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await loginAs(page, "student")
  await page.goto("/news")
  await expect(page.getByRole("main")).toBeVisible()

  const navbar = page.locator("nav.vt-navbar")
  await expect(navbar).toBeVisible()
  const initial = await navbarShellRect(page)
  expect(initial.top).toBeCloseTo(0, 0)
  expect(initial.height).toBeGreaterThanOrEqual(64)

  await page.evaluate(() => window.scrollTo(0, 180))
  await expect.poll(() => page.evaluate(() => Math.round(window.scrollY))).toBe(180)
  const compact = await navbarShellRect(page)
  expect(compact.top).toBeCloseTo(initial.top, 0)
  expect(compact.height).toBeCloseTo(initial.height, 0)

  await page.locator('nav a[data-tab-key="/events"]').click()
  await expect(page).toHaveURL(/\/events\/?$/u)
  await expect(page.getByRole("main")).toBeVisible()
  await expect(page.locator('nav a[data-tab-key="/events"]')).toHaveAttribute(
    "aria-current",
    "page"
  )
  const afterNavigation = await navbarShellRect(page)
  expect(afterNavigation.top).toBeCloseTo(initial.top, 0)
  expect(afterNavigation.height).toBeCloseTo(initial.height, 0)

  await page.evaluate(() => window.scrollTo(0, 180))
  await expect.poll(() => page.evaluate(() => Math.round(window.scrollY))).toBe(180)
  const afterNavigationScroll = await navbarShellRect(page)
  expect(afterNavigationScroll.top).toBeCloseTo(initial.top, 0)
  expect(afterNavigationScroll.height).toBeCloseTo(initial.height, 0)
})

test("tablet overflow navigation is keyboard operable and restores focus on Escape", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1024, height: 900 })
  await loginAs(page, "student")
  await page.goto("/news")
  await expect(page.getByRole("main")).toBeVisible()

  const navbar = page.locator("nav.vt-navbar")
  await expect(navbar).toBeVisible()
  const drawerTrigger = page.locator('button[aria-controls="mobile-drawer"]')
  await expect(drawerTrigger).toBeVisible()
  await expect(drawerTrigger).toHaveAttribute("aria-expanded", "false")
  await expect(navbar.locator(".navbar-desktop-nav")).toHaveCount(0)
  const drawerTriggerSize = await drawerTrigger.evaluate((element) => {
    const rect = element.getBoundingClientRect()
    return { width: rect.width, height: rect.height }
  })
  expect(drawerTriggerSize.width).toBeGreaterThanOrEqual(44)
  expect(drawerTriggerSize.height).toBeGreaterThanOrEqual(44)

  const previousBodyOverflow = await page.evaluate(() => document.body.style.overflow)
  await drawerTrigger.click()
  const drawer = page.getByRole("dialog")
  await expect(drawer).toBeVisible()
  await expect(drawer).toHaveAttribute("aria-modal", "true")
  await expect(drawerTrigger).toHaveAttribute("aria-expanded", "true")
  await expect.poll(() => page.evaluate(() => document.body.style.overflow)).toBe("hidden")
  await page.keyboard.press("Escape")
  await expect(drawer).toBeHidden()
  await expect(drawerTrigger).toHaveAttribute("aria-expanded", "false")
  await expect(drawerTrigger).toBeFocused()
  await expect
    .poll(() => page.evaluate(() => document.body.style.overflow))
    .toBe(previousBodyOverflow)

  await page.setViewportSize({ width: 1025, height: 900 })
  await expect(drawerTrigger).toHaveCount(0)
  await expect(navbar.locator(".navbar-desktop-nav")).toBeVisible()

  const overflowTrigger = navbar.locator('.navbar-desktop-overflow button[aria-haspopup="menu"]')
  await expect(overflowTrigger).toBeVisible()
  const triggerSize = await overflowTrigger.evaluate((element) => {
    const rect = element.getBoundingClientRect()
    return { width: rect.width, height: rect.height }
  })
  expect(triggerSize.width).toBeGreaterThanOrEqual(44)
  expect(triggerSize.height).toBeGreaterThanOrEqual(44)

  await overflowTrigger.focus()
  await page.keyboard.press("Enter")
  const overflowMenu = page.getByRole("menu")
  await expect(overflowMenu).toBeVisible()
  const firstMenuItem = overflowMenu.getByRole("menuitem").first()
  await expect(firstMenuItem).toBeFocused()
  await page.keyboard.press("Escape")
  await expect(overflowMenu).toBeHidden()
  await expect(overflowTrigger).toBeFocused()
})
