import { expect, loginAs, test } from "./fixtures"
import type { Locator, Page } from "@playwright/test"

declare global {
  interface Window {
    __navbarLayoutShiftObserver?: PerformanceObserver
    __navbarLayoutShiftObserverSupported?: boolean
    __navbarLayoutShiftValues?: number[]
  }
}

const NAVBAR_CLS_LIMIT = 0.1
const NAVBAR_GEOMETRY_DIAGNOSTIC_LIMIT = 6
const NAVBAR_GEOMETRY_DIAGNOSTIC_COUNT_LIMIT = 99_999
const emittedNavbarGeometryRecords = new Set<string>()

interface NavbarGeometrySample {
  width: number
  contentRight: number
  settingsLeft: number
  settingsRight: number
  nameLeft: number
  nameRight: number
  messengerLeft: number
  referenceRight: number
  scrollWidth: number
  clientWidth: number
}

function boundedNavbarGeometryCount(value: number): number | undefined {
  if (!Number.isFinite(value)) return undefined
  const rounded = Math.round(value)
  return rounded >= 0 && rounded <= NAVBAR_GEOMETRY_DIAGNOSTIC_COUNT_LIMIT ? rounded : undefined
}

// Emits the exact geometry only when one of the spacing expectations below would fail.
function reportNavbarGeometryDiagnostic(sample: NavbarGeometrySample): void {
  try {
    const project = test.info().project.name
    if (project !== "desktop" && project !== "mobile") return
    const failing =
      sample.messengerLeft - sample.referenceRight < 12 ||
      sample.nameRight > sample.settingsLeft + 1 ||
      sample.settingsRight > sample.contentRight + 1 ||
      sample.scrollWidth > sample.clientWidth + 1
    if (!failing) return
    if (emittedNavbarGeometryRecords.size >= NAVBAR_GEOMETRY_DIAGNOSTIC_LIMIT) return

    const values = {
      width: boundedNavbarGeometryCount(sample.width),
      contentRight: boundedNavbarGeometryCount(sample.contentRight),
      settingsLeft: boundedNavbarGeometryCount(sample.settingsLeft),
      settingsRight: boundedNavbarGeometryCount(sample.settingsRight),
      nameLeft: boundedNavbarGeometryCount(sample.nameLeft),
      nameRight: boundedNavbarGeometryCount(sample.nameRight),
      messengerLeft: boundedNavbarGeometryCount(sample.messengerLeft),
      referenceRight: boundedNavbarGeometryCount(sample.referenceRight),
      scrollWidth: boundedNavbarGeometryCount(sample.scrollWidth),
      clientWidth: boundedNavbarGeometryCount(sample.clientWidth),
    }
    if (Object.values(values).some((value) => value === undefined)) return

    const record =
      "UE_LIVE_NAVBAR_GEOMETRY_V1 project=" +
      project +
      " width=" +
      values.width +
      " contentRight=" +
      values.contentRight +
      " settingsLeft=" +
      values.settingsLeft +
      " settingsRight=" +
      values.settingsRight +
      " nameLeft=" +
      values.nameLeft +
      " nameRight=" +
      values.nameRight +
      " messengerLeft=" +
      values.messengerLeft +
      " referenceRight=" +
      values.referenceRight +
      " scrollWidth=" +
      values.scrollWidth +
      " clientWidth=" +
      values.clientWidth +
      "\n"
    if (emittedNavbarGeometryRecords.has(record)) return
    emittedNavbarGeometryRecords.add(record)
    process.stdout.write(record)
  } catch {
    // Diagnostics must never replace the existing spacing assertions.
  }
}

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

      for (const width of [1440, 1349, 1350, 1920]) {
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
        const nameBox = await assertProfileNameGeometry(page, label, width)
        const contentBox = await page.locator("nav.vt-navbar > div > div").boundingBox()
        if (!referenceBox || !messengerBox || !settingsBox || !contentBox) {
          throw new Error(label + " navbar geometry was unavailable")
        }
        const contentMetrics = await page
          .locator("nav.vt-navbar > div > div")
          .evaluate((element) => ({
            clientWidth: element.clientWidth,
            scrollWidth: element.scrollWidth,
          }))
        reportNavbarGeometryDiagnostic({
          width,
          contentRight: contentBox.x + contentBox.width,
          settingsLeft: settingsBox.x,
          settingsRight: settingsBox.x + settingsBox.width,
          nameLeft: nameBox.x,
          nameRight: nameBox.x + nameBox.width,
          messengerLeft: messengerBox.x,
          referenceRight: referenceBox.x + referenceBox.width,
          scrollWidth: contentMetrics.scrollWidth,
          clientWidth: contentMetrics.clientWidth,
        })
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
            const syntheticNameBox = await assertProfileNameGeometry(page, label, width, true)
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
              // Name geometry has already been checked against the container width.
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
    await assertDrawerCloseReady(closeButton, width)
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

// Keep helpers below the live declarations: their line numbers identify diagnostic evidence.
async function assertProfileNameGeometry(
  page: Page,
  label: string,
  viewportWidth: number,
  synthetic = false
): Promise<{ x: number; width: number }> {
  const navbar = page.locator("nav.vt-navbar")
  const nameContainer = navbar.locator(".navbar-user-name")
  const username = nameContainer.locator("button")
  const avatar = username.locator("xpath=../preceding-sibling::button[1]")
  const profileActions = navbar.locator('[class~="@container/profile-actions"]')

  await expect(nameContainer, label + " username container").toHaveCount(1)
  await expect(username, label + " username").toHaveCount(1)
  await expect(profileActions, label + " profile actions").toHaveCount(1)
  await expect(avatar, label + " profile avatar").toBeVisible()
  await expect(avatar, label + " profile avatar").toHaveAccessibleName(/\S/u)
  await expect(username, label + " profile name").toHaveText(/\S/u)
  await expect(username, label + " profile name").toBeEnabled()

  const accessibleName = await username.getAttribute("aria-label")
  const nameText = (await username.textContent())?.trim()
  if (!accessibleName || !nameText) throw new Error(label + " profile identity was unavailable")
  if (!synthetic) expect(accessibleName, label + " profile identity").toContain(nameText)
  await expect(avatar, label + " profile identity fallback").toHaveAccessibleDescription(
    accessibleName
  )

  const actionsWidthRem = await profileActions.evaluate(
    (element) =>
      element.getBoundingClientRect().width /
      Number.parseFloat(getComputedStyle(document.documentElement).fontSize)
  )
  expect(actionsWidthRem, label + " profile action width").toBeGreaterThan(0)
  if (viewportWidth === 1920) {
    expect(actionsWidthRem, label + " wide profile actions").toBeGreaterThanOrEqual(18)
  }
  if (actionsWidthRem < 18) {
    await expect(nameContainer, label + " constrained username").toHaveCSS("display", "none")
    await expect(username, label + " constrained username").toBeHidden()
    expect(await nameContainer.boundingBox(), label + " hidden username box").toBeNull()
  } else {
    await expect(nameContainer, label + " expanded username").toHaveCSS("display", "block")
    await expect(username, label + " expanded username").toBeVisible()
  }

  // A CSS-hidden element has a real zero rectangle for the existing diagnostic.
  const rect = await nameContainer.evaluate((element) => {
    const box = element.getBoundingClientRect()
    return { x: box.x, width: box.width }
  })
  if (actionsWidthRem < 18) {
    expect(rect.width, label + " hidden username width").toBe(0)
  } else {
    expect(rect.width, label + " visible username width").toBeGreaterThan(0)
  }
  return rect
}

/** Check the focused layout box, then measure the physical target when stable. */
async function assertDrawerCloseReady(closeButton: Locator, viewportWidth: number): Promise<void> {
  await expect(closeButton).toBeFocused()
  const layout = await closeButton.evaluate((element) => {
    const style = getComputedStyle(element)
    const size = (value: string) => Number.parseFloat(value)
    const contentBox = style.boxSizing === "content-box"
    return {
      width:
        size(style.width) +
        (contentBox
          ? size(style.paddingLeft) +
            size(style.paddingRight) +
            size(style.borderLeftWidth) +
            size(style.borderRightWidth)
          : 0),
      height:
        size(style.height) +
        (contentBox
          ? size(style.paddingTop) +
            size(style.paddingBottom) +
            size(style.borderTopWidth) +
            size(style.borderBottomWidth)
          : 0),
    }
  })
  expect(layout.width, `${viewportWidth}px drawer close layout width`).toBeGreaterThanOrEqual(44)
  expect(layout.height, `${viewportWidth}px drawer close layout height`).toBeGreaterThanOrEqual(44)
  // The drawer's translate spring can transiently produce a fractional DOMRect.
  await closeButton.click({ trial: true })
  await expect(closeButton).toBeFocused()
}
